"""Bounded and auditable detection demo against this project's own local service.

Run only after starting the app with short demo windows (APP_RATE_WINDOW=5,
APP_DETECT_WINDOW=5, APP_RATE_LIMIT=5, APP_DETECT_THRESHOLD=3).
Writes sanitized evidence (never prints or saves token values).
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from docker_smoke import DIGIT_ZERO

BASE = "http://127.0.0.1:8000"
OUTPUT = Path("reports/lab4")


def request(path: str, token: str | None = None, method: str = "GET", payload=None):
    headers = {}
    if path in ("/metrics", "/detection"):
        headers["X-Metrics-Token"] = os.environ["APP_METRICS_TOKEN"]
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(BASE + path, headers=headers, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode("utf-8")


def save(name: str, content: str):
    (OUTPUT / name).write_text(content, encoding="utf-8")


def main() -> int:
    secret = os.environ["APP_API_TOKEN"]
    if len(secret) < 16:
        raise SystemExit("APP_API_TOKEN is missing")
    if int(os.environ.get("APP_RATE_WINDOW", "60")) > 10:
        raise SystemExit("Use APP_RATE_WINDOW=5 and APP_DETECT_WINDOW=5 for a short classroom demo")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    started = datetime.now(UTC).isoformat()
    health_status, health = request("/health")
    if health_status != 200:
        raise SystemExit("Health is not 200; fix readiness first")
    save("health_before.json", health + "\n")
    _, before = request("/metrics")
    save("metrics_before.prom", before)
    _, detector_before = request("/detection")
    save("detection_before.json", detector_before + "\n")

    payload = {"pixels": DIGIT_ZERO}
    good_status, good_body = request("/predict", token=secret, method="POST", payload=payload)
    codes = []
    for _ in range(5):  # small number of requests, no load test
        code, _ = request("/predict", token="deliberately-invalid-token", method="POST", payload=payload)
        codes.append(code)
    _, detector_during = request("/detection")
    _, after = request("/metrics")
    save("metrics_after.prom", after)
    save("detection_after.json", detector_during + "\n")

    # Wait for the configured short window to expire; no DoS or brute force.
    wait = int(os.environ.get("APP_RATE_WINDOW", "5")) + 1
    time.sleep(wait)
    recovered_status, recovered_body = request("/predict", token=secret, method="POST", payload=payload)
    _, detector_recovered = request("/detection")
    save("detection_recovered.json", detector_recovered + "\n")
    save("health_after.json", request("/health")[1] + "\n")
    expected = good_status == 200 and codes.count(401) >= 3 and 429 in codes
    expected = expected and json.loads(detector_during)["alert"]
    expected = expected and recovered_status == 200 and not json.loads(detector_recovered)["alert"]
    result = {
        "time_start_utc": started,
        "time_finish_utc": datetime.now(UTC).isoformat(),
        "rule": json.loads(detector_during),
        "normal_prediction_status": good_status,
        "negative_status_codes": codes,
        "recovery_prediction_status": recovered_status,
        "recovered_alert": json.loads(detector_recovered),
        "normal_request_id": json.loads(good_body).get("request_id") if good_status == 200 else None,
        "recovery_request_id": json.loads(recovered_body).get("request_id") if recovered_status == 200 else None,
        "result": "PASS" if expected else "FAIL",
        "note": "Metrics show API errors, not proof of an actual attack or reduced model accuracy.",
    }
    save("scenario_summary.json", json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if expected else 1


if __name__ == "__main__":
    raise SystemExit(main())
