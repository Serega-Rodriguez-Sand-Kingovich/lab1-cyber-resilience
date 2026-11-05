"""Data leakage and model artifact regression checks."""
import hashlib
import json

import numpy as np
import pytest

from src.config import METRICS_DIR, MODEL_MANIFEST, MODEL_PATH
from src.data import load_and_check_data, sha256_file, split_data
from src.inference import load_verified_model, predict_digits


def test_unchanged_lab1_dataset_and_no_preprocessing_drops():
    X, y, report = load_and_check_data()
    assert X.shape == (1740, 64)
    assert y.shape == (1740,)
    assert set(y.tolist()) == set(range(10))
    assert all(value == 174 for value in report["classes"].values())
    assert report["missing_total"] == 0
    assert report["duplicate_feature_vectors"] == 0
    assert report["rows_removed_in_lab2"] == 0


def test_no_overlap_and_stratified_holdout():
    X, y, _ = load_and_check_data()
    train, test = split_data(X, y)
    assert len(train) == 1392
    assert len(test) == 348
    assert set(train).isdisjoint(set(test))
    assert all(x in (139, 140) for x in np.bincount(y[train], minlength=10))
    assert all(x in (34, 35) for x in np.bincount(y[test], minlength=10))
    assert not {tuple(row) for row in X[train]} & {tuple(row) for row in X[test]}


def test_artifact_reload_equals_recorded_metrics():
    X, y, report = load_and_check_data()
    model = load_verified_model()
    baseline = json.loads((METRICS_DIR / "baseline.json").read_text(encoding="utf-8"))
    assert baseline["data_version"] == report["data_version"]
    assert baseline["model_sha256"] == sha256_file(MODEL_PATH)
    assert 0 <= baseline["accuracy"] <= 1
    predictions = predict_digits(model, X[0].reshape(8, 8))
    assert predictions.shape == (1,)
    assert int(predictions[0]) in range(10)
    assert int(y[0]) in range(10)


def test_tampered_model_is_rejected_before_deserialization(tmp_path):
    model_path = tmp_path / "bad.joblib"
    manifest = tmp_path / "model.sha256"
    model_path.write_bytes(b"not a trusted pickle or joblib model")
    manifest.write_text("0" * 64 + "  models/bad.joblib\n", encoding="ascii")
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        load_verified_model(model_path, manifest)


def test_manifest_does_not_accept_path_traversal(tmp_path):
    model_path = tmp_path / "bad.joblib"
    manifest = tmp_path / "model.sha256"
    model_path.write_bytes(b"text data")
    digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
    manifest.write_text(digest + "  models/../bad.joblib\n", encoding="ascii")
    with pytest.raises(ValueError, match="unexpected format"):
        load_verified_model(model_path, manifest)


def test_pipeline_scaler_matches_training_data_only():
    X, y, _ = load_and_check_data()
    train_idx, test_idx = split_data(X, y)
    model = load_verified_model()
    scaler = model.named_steps["scaler"]
    assert np.allclose(scaler.mean_, X[train_idx].mean(axis=0), atol=1e-12)
    assert not np.allclose(scaler.mean_, X.mean(axis=0), atol=1e-12)
