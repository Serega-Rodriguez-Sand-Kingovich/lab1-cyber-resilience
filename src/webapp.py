"""Lab 4: local-only, monitored API for the frozen Lab 2 digits classifier.

The model is checked against an independently pinned hash before joblib loading.
One Linux child process executes predictions; timeouts terminate that worker.
Only JSON numeric pixels are accepted; never deserialize client-provided models.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import multiprocessing as mp
import os
import threading
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

from src.config import MODEL_MANIFEST, MODEL_PATH, ROOT
from src.data import sha256_file
from src.inference import (
    InputValidationError,
    load_verified_model,
    predict_digits,
    validate_digits,
)

LOGGER = logging.getLogger("lab4.api")
if not LOGGER.handlers:
    LOGGER.addHandler(logging.StreamHandler())
LOGGER.setLevel(logging.INFO)
LOGGER.propagate = False

# Independent reference: committed Lab 2/3 model and known trusted fingerprint.
TRUSTED_MODEL_SHA256 = "655ada9ced68462b56dc298ad18bba5e2c2b4fe9783181aef8067ffd3467c9a9"
MODEL_VERSION = f"lab2-{TRUSTED_MODEL_SHA256[:12]}"
MAX_BODY_BYTES = 24 * 1024
MODEL_BATCH_LIMIT = 32
READ_TIMEOUT_SEC = 3.0
INFERENCE_TIMEOUT_SEC = 3.0
BUSY_TIMEOUT_SEC = 0.5
ALLOWED_PATHS = {"/", "/predict", "/health", "/metrics", "/detection", "/static"}


def _env_int(name: str, default: int, low: int, high: int) -> int:
    value = int(os.getenv(name, str(default)))
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}")
    return value


@dataclass(frozen=True)
class Settings:
    api_token: str
    metrics_token: str
    rate_limit: int = 5
    rate_window_seconds: int = 60
    detection_threshold: int = 4
    detection_window_seconds: int = 60

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            api_token=os.getenv("APP_API_TOKEN", ""),
            metrics_token=os.getenv("APP_METRICS_TOKEN", ""),
            rate_limit=_env_int("APP_RATE_LIMIT", 5, 1, 100),
            rate_window_seconds=_env_int("APP_RATE_WINDOW", 60, 2, 3600),
            detection_threshold=_env_int("APP_DETECT_THRESHOLD", 4, 1, 100),
            detection_window_seconds=_env_int("APP_DETECT_WINDOW", 60, 2, 3600),
        )


def _load_trusted_model() -> Any:
    """Fail closed: check a pinned value and both independent manifests first."""
    baseline_path = ROOT / "metrics" / "baseline.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    if baseline.get("model_sha256") != TRUSTED_MODEL_SHA256:
        raise ValueError("Baseline checksum disagrees with pinned Lab 2 reference")
    reference = f"{TRUSTED_MODEL_SHA256}  models/digits_baseline.joblib"
    if MODEL_MANIFEST.read_text(encoding="ascii").strip() != reference:
        raise ValueError("Model manifest does not match the trusted reference")
    if sha256_file(MODEL_PATH) != TRUSTED_MODEL_SHA256:
        raise ValueError("Model artifact SHA256 mismatch")
    return load_verified_model(path=MODEL_PATH, manifest=MODEL_MANIFEST)


def _worker_loop(conn: Any, model: Any) -> None:
    """No HTTP and no network; child only receives already validated numeric arrays."""
    try:
        while True:
            try:
                data = conn.recv()
            except EOFError:
                break
            if data is None:
                break
            try:
                result = predict_digits(model, data, max_batch_size=MODEL_BATCH_LIMIT)
                conn.send(("ok", [int(v) for v in result.tolist()]))
            except Exception:  # noqa: BLE001
                conn.send(("error", None))
    finally:
        conn.close()


class Runtime:
    """One supervised prediction process with a real kill-on-timeout deadline.

    A spawned Linux worker receives the trusted model once at startup, not per
    request. This is a teaching implementation, not a multi-worker API.
    """

    def __init__(self) -> None:
        self.ready = False
        self.parent_conn: Any = None
        self.worker: Any = None
        self.predict_sent = 0
        self.ipc_lock = threading.Lock()

    def start(self) -> None:
        if os.name != "posix":
            raise RuntimeError("Inference subprocess requires Ubuntu/Linux")
        model = _load_trusted_model()
        ctx = mp.get_context("spawn")
        parent, child = ctx.Pipe(duplex=True)
        worker = ctx.Process(target=_worker_loop, args=(child, model), daemon=True)
        worker.start()
        child.close()
        self.parent_conn = parent
        self.worker = worker
        self.ready = worker.is_alive()
        if not self.ready:
            self.close()
            raise RuntimeError("Inference child did not start")

    def is_ready(self) -> bool:
        return bool(self.ready and self.worker is not None and self.worker.is_alive())

    def close(self) -> None:
        self.ready = False
        if self.worker is not None:
            if self.worker.is_alive():
                self.worker.terminate()
            self.worker.join(timeout=1)
            if self.worker.is_alive():
                self.worker.kill()
                self.worker.join(timeout=1)
            self.worker = None
        if self.parent_conn is not None:
            self.parent_conn.close()
            self.parent_conn = None

    def predict(self, checked: Any) -> list[int]:
        """Called in a thread: IPC poll times out and kills an unresponsive child."""
        with self.ipc_lock:
            if not self.is_ready():
                raise RuntimeError("Prediction service unavailable")
            try:
                self.predict_sent += 1
                self.parent_conn.send(checked)
                if not self.parent_conn.poll(INFERENCE_TIMEOUT_SEC):
                    self.close()
                    raise TimeoutError("Prediction deadline exceeded; child terminated")
                state, payload = self.parent_conn.recv()
                if state != "ok":
                    raise RuntimeError("Prediction failed")
                return payload
            except (EOFError, BrokenPipeError, OSError) as exc:
                self.close()
                raise RuntimeError("Prediction worker disconnected") from exc


class SlidingWindow:
    """Single-process state: bounded IP keys, no forwarding headers trusted."""

    def __init__(self, limit: int, window_sec: int) -> None:
        self.limit = limit
        self.window_sec = window_sec
        self.entries: dict[str, deque[float]] = defaultdict(deque)
        self.guard = threading.Lock()

    def allow(self, key: str) -> bool:
        with self.guard:
            now = time.monotonic()
            # Bound memory when clients change frequently; never store forwarded IPs.
            if len(self.entries) > 512:
                self.entries.clear()
            times = self.entries[key]
            while times and now - times[0] >= self.window_sec:
                times.popleft()
            if len(times) >= self.limit:
                return False
            times.append(now)
            return True


class Detector:
    def __init__(self, threshold: int, window_sec: int) -> None:
        self.threshold = threshold
        self.window_sec = window_sec
        self.events: deque[float] = deque()
        self.lock = threading.Lock()

    def register(self) -> None:
        with self.lock:
            self.events.append(time.monotonic())
            self._expire(time.monotonic())

    def _expire(self, now: float) -> None:
        while self.events and now - self.events[0] >= self.window_sec:
            self.events.popleft()

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            self._expire(time.monotonic())
            count = len(self.events)
        return {
            "rule": "401_or_429_within_window",
            "window_seconds": self.window_sec,
            "threshold": self.threshold,
            "observed": count,
            "alert": count >= self.threshold,
        }


def _parse_json(data: bytes) -> Any:
    def forbidden_constant(_: str) -> None:
        raise ValueError("NaN and Infinity are forbidden")
    return json.loads(data.decode("utf-8"), parse_constant=forbidden_constant)


def create_app(settings: Settings | None = None) -> FastAPI:
    configured = settings or Settings.from_env()
    if len(configured.api_token) < 16 or len(configured.metrics_token) < 16:
        raise RuntimeError("Set APP_API_TOKEN and APP_METRICS_TOKEN (16+ characters)")
    if hmac.compare_digest(configured.api_token, configured.metrics_token):
        raise RuntimeError("API and metrics tokens must be different")

    registry = CollectorRegistry()
    total = Counter("lab4_requests", "HTTP requests", ["route", "status"], registry=registry)
    seconds = Histogram(
        "lab4_request_duration_seconds", "HTTP response latency", ["route"],
        buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 3, 5, 10), registry=registry,
    )
    rejected = Counter(
        "lab4_rejections", "Rejected API requests", ["reason"], registry=registry,
    )
    rate_limit = SlidingWindow(configured.rate_limit, configured.rate_window_seconds)
    detector = Detector(configured.detection_threshold, configured.detection_window_seconds)
    runtime = Runtime()
    prediction_slot = asyncio.Lock()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        try:
            runtime.start()
            LOGGER.info(json.dumps({"event": "model_startup", "ready": True, "model_version": MODEL_VERSION}))
        except Exception:  # noqa: BLE001
            # No traceback, paths or model bytes leave the service.
            LOGGER.error(json.dumps({"event": "model_startup", "ready": False, "model_version": MODEL_VERSION}))
        application.state.runtime = runtime
        try:
            yield
        finally:
            runtime.close()

    app = FastAPI(title="Lab 4 protected digits API", version="lab4-v1", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.runtime = runtime
    app.state.detector = detector
    app.state.registry = registry

    def fail(request: Request, code: int, reason: str, message: str) -> JSONResponse:
        request.state.failure_type = reason
        if code in (401, 429):
            detector.register()
        return JSONResponse(
            status_code=code,
            content={"error": message, "request_id": request.state.request_id},
            headers={"Cache-Control": "no-store"},
        )

    @app.middleware("http")
    async def telemetry(request: Request, call_next: Any) -> Response:
        started = time.perf_counter()
        request.state.request_id = uuid.uuid4().hex
        request.state.failure_type = "none"
        path = request.url.path
        route = path if path in ALLOWED_PATHS else "/static" if path.startswith("/static/") else "other"
        try:
            response = await call_next(request)
        except Exception:  # noqa: BLE001
            request.state.failure_type = "internal_error"
            response = JSONResponse(status_code=500, content={"error": "Internal service error", "request_id": request.state.request_id})
        elapsed = time.perf_counter() - started
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'"
        total.labels(route=route, status=str(response.status_code)).inc()
        seconds.labels(route=route).observe(elapsed)
        if request.state.failure_type != "none":
            rejected.labels(reason=request.state.failure_type).inc()
        LOGGER.info(json.dumps({
            "ts": datetime.now(UTC).isoformat(),
            "request_id": request.state.request_id,
            "route": route,
            "status": response.status_code,
            "duration_ms": round(elapsed * 1000, 3),
            "model_version": MODEL_VERSION,
            "failure_type": request.state.failure_type,
        }, separators=(",", ":")))
        return response

    static_dir = Path(__file__).resolve().parents[1] / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(static_dir / "index.html", media_type="text/html")

    @app.get("/health")
    async def health() -> Response:
        if not runtime.is_ready():
            return JSONResponse(status_code=503, content={"status": "unavailable", "model_version": MODEL_VERSION})
        return JSONResponse(content={"status": "healthy", "model_version": MODEL_VERSION})

    def check_metrics_token(request: Request) -> bool:
        provided = request.headers.get("X-Metrics-Token", "")
        return hmac.compare_digest(provided, configured.metrics_token)

    @app.get("/metrics")
    async def metrics(request: Request) -> Response:
        if not check_metrics_token(request):
            return fail(request, 401, "metrics_auth", "Access denied")
        return Response(content=generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

    @app.get("/detection")
    async def detection(request: Request) -> Response:
        if not check_metrics_token(request):
            return fail(request, 401, "metrics_auth", "Access denied")
        return JSONResponse(detector.snapshot())

    @app.post("/predict")
    async def predict(request: Request) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        if not rate_limit.allow(client_ip):
            return fail(request, 429, "rate_limit", "Too many requests; retry later")
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or not hmac.compare_digest(auth[7:], configured.api_token):
            return fail(request, 401, "auth", "Invalid or missing API token")
        if not runtime.is_ready():
            return fail(request, 503, "not_ready", "Model is not ready")
        content_type = request.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            return fail(request, 415, "media_type", "Only application/json is accepted")
        content_length = request.headers.get("Content-Length")
        if content_length is not None:
            try:
                if int(content_length) > MAX_BODY_BYTES:
                    return fail(request, 413, "request_size", "Request body is too large")
            except ValueError:
                return fail(request, 400, "request_headers", "Invalid Content-Length")
        buffer = bytearray()
        try:
            async with asyncio.timeout(READ_TIMEOUT_SEC):
                async for part in request.stream():
                    if len(buffer) + len(part) > MAX_BODY_BYTES:
                        return fail(request, 413, "request_size", "Request body is too large")
                    buffer.extend(part)
        except TimeoutError:
            return fail(request, 408, "read_timeout", "Request body read timeout")
        except Exception:  # noqa: BLE001
            return fail(request, 400, "request_body", "Unable to read request body")
        try:
            payload = _parse_json(bytes(buffer))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return fail(request, 400, "json", "Invalid JSON or forbidden numeric constant")
        if not isinstance(payload, dict) or set(payload) != {"pixels"}:
            return fail(request, 422, "schema", "JSON object must contain exactly 'pixels'")
        try:
            checked = validate_digits(payload["pixels"], max_batch_size=MODEL_BATCH_LIMIT)
        except (InputValidationError, ValueError, TypeError):
            return fail(request, 422, "validation", "Expected numeric 8x8 or N x 8x8 pixels in [0,16]")
        try:
            await asyncio.wait_for(prediction_slot.acquire(), timeout=BUSY_TIMEOUT_SEC)
        except TimeoutError:
            return fail(request, 503, "busy", "Service is busy")
        try:
            output = await asyncio.to_thread(runtime.predict, checked)
        except TimeoutError:
            return fail(request, 503, "inference_timeout", "Prediction timed out; service unavailable")
        except Exception:  # noqa: BLE001
            return fail(request, 503, "inference_error", "Prediction service unavailable")
        finally:
            prediction_slot.release()
        return JSONResponse({
            "prediction": output[0] if len(output) == 1 else None,
            "predictions": output,
            "model_version": MODEL_VERSION,
            "request_id": request.state.request_id,
        })

    return app


# Requires secrets before import; the shell and CI set them as environment values.
app = create_app()
