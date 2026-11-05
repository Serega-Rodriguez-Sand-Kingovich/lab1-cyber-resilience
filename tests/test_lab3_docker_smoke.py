"""Tests for the Docker smoke-check and model-integrity contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.docker_smoke import sample_digit, verify_sha256

ROOT = Path(__file__).resolve().parents[1]


def test_smoke_sample_has_valid_shape_and_range():
    sample = sample_digit()
    assert sample.shape == (1, 64)
    assert sample.min() >= 0
    assert sample.max() <= 16


def test_hash_validation_accepts_known_bytes(tmp_path):
    path = tmp_path / "model.bin"
    path.write_bytes(b"approved test bytes")
    expected = hashlib.sha256(b"approved test bytes").hexdigest()
    assert verify_sha256(path, expected) == expected


def test_hash_validation_rejects_modified_bytes(tmp_path):
    path = tmp_path / "model.bin"
    expected = hashlib.sha256(b"approved test bytes").hexdigest()
    path.write_bytes(b"tampered bytes")
    with pytest.raises(ValueError, match="SHA256 differs"):
        verify_sha256(path, expected)


def test_real_saved_model_matches_lab2_baseline():
    baseline = json.loads((ROOT / "metrics/baseline.json").read_text(encoding="utf-8"))
    expected = baseline["model_sha256"]
    assert verify_sha256(ROOT / "models/digits_baseline.joblib", expected) == expected
