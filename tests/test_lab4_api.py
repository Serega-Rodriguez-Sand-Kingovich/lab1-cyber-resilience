"""Real HTTP-level tests for Lab 4; no retraining and no external network."""

# Application secrets used only in this isolated test process.
import os
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("APP_API_TOKEN", "test-api-token-local-only")
os.environ.setdefault("APP_METRICS_TOKEN", "test-metrics-token-local-only")

from src import webapp

TOKEN = "test-api-token-local-only"
METRICS = "test-metrics-token-local-only"
SAMPLE = [
    [0, 0, 5, 13, 9, 1, 0, 0],
    [0, 0, 13, 15, 10, 15, 5, 0],
    [0, 3, 15, 2, 0, 11, 8, 0],
    [0, 4, 12, 0, 0, 8, 8, 0],
    [0, 5, 8, 0, 0, 9, 8, 0],
    [0, 4, 11, 0, 1, 12, 7, 0],
    [0, 2, 14, 5, 10, 12, 0, 0],
    [0, 0, 6, 13, 10, 0, 0, 0],
]


class FakeDigitsModel:
    def predict(self, array):
        return np.zeros(len(array), dtype=np.int64)


class SlowModel:
    def predict(self, array):
        time.sleep(1.0)
        return np.zeros(len(array), dtype=np.int64)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(webapp, "_load_trusted_model", FakeDigitsModel)
    cfg = webapp.Settings(api_token=TOKEN, metrics_token=METRICS, rate_limit=12)
    with TestClient(webapp.create_app(cfg)) as api:
        yield api


def headers(token=TOKEN):
    return {"Authorization": f"Bearer {token}"}


def test_health_and_static_page(client):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "healthy"
    assert health.json()["model_version"].startswith("lab2-")
    page = client.get("/")
    assert page.status_code == 200
    assert "Распознавание рукописных цифр" in page.text
    assert client.get("/static/app.js").status_code == 200


def test_valid_prediction_and_contract(client):
    response = client.post("/predict", headers=headers(), json={"pixels": SAMPLE})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["prediction"] == 0
    assert result["predictions"] == [0]
    assert len(result["request_id"]) == 32
    assert result["model_version"].startswith("lab2-")
    assert response.headers["X-Request-ID"] == result["request_id"]


def test_no_token_and_wrong_token_return_401_without_inference(client):
    runtime = client.app.state.runtime
    before = runtime.predict_sent
    for auth in ({}, headers("definitely-wrong-token")):
        res = client.post("/predict", headers=auth, json={"pixels": SAMPLE})
        assert res.status_code == 401
        assert "traceback" not in res.text.lower()
    assert runtime.predict_sent == before


@pytest.mark.parametrize("body", [{}, {"pixels": []}, {"pixels": [[1, 2]]},
                                    {"pixels": [["x"] * 8 for _ in range(8)]},
                                    {"pixels": [True] * 64},
                                    {"pixels": [[17] * 8 for _ in range(8)]},
                                    {"pixels": [[-1] * 8 for _ in range(8)]},
                                    {"pixels": [1] * 64, "target": 0}])
def test_invalid_schema_and_pixels_never_reach_model(client, body):
    before = client.app.state.runtime.predict_sent
    response = client.post("/predict", headers=headers(), json=body)
    assert response.status_code == 422
    assert client.app.state.runtime.predict_sent == before


def test_not_supported_file_type(client):
    res = client.post("/predict", headers={**headers(), "Content-Type": "image/png"}, content=b"not-a-png")
    assert res.status_code == 415


def test_corrupt_json_and_nan_rejected(client):
    for content in (b"{not valid JSON", b'{"pixels":[NaN]}', b'{"pixels":[Infinity]}'):
        res = client.post("/predict", headers={**headers(), "Content-Type": "application/json"}, content=content)
        assert res.status_code == 400


def test_oversized_request_is_413_before_model(client):
    before = client.app.state.runtime.predict_sent
    payload = b"X" * (webapp.MAX_BODY_BYTES + 1)
    res = client.post("/predict", headers={**headers(), "Content-Type": "application/json"}, content=payload)
    assert res.status_code == 413
    assert client.app.state.runtime.predict_sent == before


def test_decoded_array_batch_limit(client):
    res = client.post("/predict", headers=headers(), json={"pixels": [SAMPLE] * 33})
    assert res.status_code == 422


def test_metrics_protected_and_logged(client):
    assert client.get("/metrics").status_code == 401
    res = client.post("/predict", headers=headers(), json={"pixels": []})
    assert res.status_code == 422
    output = client.get("/metrics", headers={"X-Metrics-Token": METRICS})
    assert output.status_code == 200
    text = output.text
    assert 'lab4_requests_total{route="/predict",status="422"}' in text
    assert 'lab4_rejections_total{reason="validation"}' in text
    assert "lab4_request_duration_seconds_bucket" in text
    assert "request_id=" not in text


def test_detection_and_limiter_recovery(monkeypatch):
    monkeypatch.setattr(webapp, "_load_trusted_model", FakeDigitsModel)
    cfg = webapp.Settings(
        api_token=TOKEN, metrics_token=METRICS,
        rate_limit=3, rate_window_seconds=2,
        detection_threshold=2, detection_window_seconds=2,
    )
    with TestClient(webapp.create_app(cfg)) as client:
        for _ in range(3):
            assert client.post("/predict", headers=headers("wrong"), json={"pixels": SAMPLE}).status_code == 401
        assert client.post("/predict", headers=headers(), json={"pixels": SAMPLE}).status_code == 429
        alert = client.get("/detection", headers={"X-Metrics-Token": METRICS}).json()
        assert alert["alert"] is True
        assert alert["observed"] >= 2
        assert client.get("/detection").status_code == 401
        time.sleep(2.1)
        assert client.post("/predict", headers=headers(), json={"pixels": SAMPLE}).status_code == 200
        assert client.get("/detection", headers={"X-Metrics-Token": METRICS}).json()["alert"] is False


def test_missing_or_corrupt_model_stays_unhealthy(monkeypatch):
    def broken_model():
        raise ValueError("SHA256 mismatch")
    monkeypatch.setattr(webapp, "_load_trusted_model", broken_model)
    cfg = webapp.Settings(api_token=TOKEN, metrics_token=METRICS)
    with TestClient(webapp.create_app(cfg)) as client:
        assert client.get("/health").status_code == 503
        result = client.post("/predict", headers=headers(), json={"pixels": SAMPLE})
        assert result.status_code == 503
        assert "SHA256" not in result.text


def test_prediction_deadline_kills_child(monkeypatch):
    monkeypatch.setattr(webapp, "_load_trusted_model", SlowModel)
    monkeypatch.setattr(webapp, "INFERENCE_TIMEOUT_SEC", 0.05)
    cfg = webapp.Settings(api_token=TOKEN, metrics_token=METRICS)
    with TestClient(webapp.create_app(cfg)) as client:
        assert client.post("/predict", headers=headers(), json={"pixels": SAMPLE}).status_code == 503
        assert client.get("/health").status_code == 503


def test_real_hash_mismatch_prevents_deserialization(tmp_path, monkeypatch):
    """Corrupted bytes must be rejected before any joblib deserialization."""
    (tmp_path / "metrics").mkdir()
    (tmp_path / "integrity").mkdir()
    (tmp_path / "models").mkdir()
    (tmp_path / "metrics/baseline.json").write_text(
        '{"model_sha256":"' + webapp.TRUSTED_MODEL_SHA256 + '"}', encoding="utf-8",
    )
    (tmp_path / "integrity/model.sha256").write_text(
        webapp.TRUSTED_MODEL_SHA256 + "  models/digits_baseline.joblib\n", encoding="ascii",
    )
    (tmp_path / "models/digits_baseline.joblib").write_bytes(b"tampered model")
    monkeypatch.setattr(webapp, "ROOT", tmp_path)
    monkeypatch.setattr(webapp, "MODEL_PATH", tmp_path / "models/digits_baseline.joblib")
    monkeypatch.setattr(webapp, "MODEL_MANIFEST", tmp_path / "integrity/model.sha256")

    def no_deserialize(**kwargs):
        raise AssertionError("Model must not be loaded when SHA256 differs")

    monkeypatch.setattr(webapp, "load_verified_model", no_deserialize)
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        webapp._load_trusted_model()
    cfg = webapp.Settings(api_token=TOKEN, metrics_token=METRICS)
    with TestClient(webapp.create_app(cfg)) as client:
        assert client.get("/health").status_code == 503


def test_chunked_body_without_content_length_is_limited(client):
    before = client.app.state.runtime.predict_sent

    def chunks():
        for _ in range(8):
            yield b"x" * 4096

    response = client.post(
        "/predict", headers={**headers(), "Content-Type": "application/json"}, content=chunks(),
    )
    assert response.status_code == 413
    assert client.app.state.runtime.predict_sent == before
