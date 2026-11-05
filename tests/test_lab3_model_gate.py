"""Behavioral tests for the Lab 3 model quality policy and metric."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.model_gate import (
    ModelGateError,
    calculate_accuracy,
    compare_metric,
    numeric_metric,
)

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads(
    (ROOT / "config/model_quality_policy.json").read_text(encoding="utf-8")
)
BASELINE = {
    "primary_metric_name": "accuracy",
    "primary_metric_value": 0.9741379310344828,
    "data_version": POLICY["dataset_sha256"],
}


def test_model_gate_allows_baseline_metric() -> None:
    comparison = compare_metric(
        BASELINE, POLICY, BASELINE["primary_metric_value"], POLICY["dataset_sha256"]
    )
    assert comparison["passed"] is True
    assert comparison["threshold"] == pytest.approx(0.92543103448)


def test_model_gate_rejects_five_percent_regression_beyond_threshold() -> None:
    comparison = compare_metric(BASELINE, POLICY, 0.92, POLICY["dataset_sha256"])
    assert comparison["passed"] is False
    assert comparison["candidate"] < comparison["threshold"]


def test_model_gate_rejects_wrong_dataset_version() -> None:
    with pytest.raises(ModelGateError, match="dataset versions differ"):
        compare_metric(BASELINE, POLICY, 0.99, "other-data-hash")


@pytest.mark.parametrize("invalid", [None, "0.99", float("nan"), float("inf"), True])
def test_model_gate_rejects_invalid_metrics(invalid: object) -> None:
    with pytest.raises(ModelGateError, match="candidate accuracy"):
        compare_metric(BASELINE, POLICY, invalid, POLICY["dataset_sha256"])


def test_model_gate_rejects_missing_baseline_value() -> None:
    missing = {
        key: value
        for key, value in BASELINE.items()
        if key != "primary_metric_value"
    }
    with pytest.raises(ModelGateError, match="baseline accuracy"):
        compare_metric(missing, POLICY, 0.97, POLICY["dataset_sha256"])


def test_accuracy_known_small_example() -> None:
    true_labels = [0, 1, 2, 3]
    predicted_labels = [0, 1, 8, 3]
    assert calculate_accuracy(true_labels, predicted_labels) == 0.75


def test_model_gate_rejects_unavailable_data() -> None:
    assert numeric_metric(1.0, "candidate accuracy") == 1.0
    with pytest.raises(ModelGateError, match="finite"):
        numeric_metric(float("-inf"), "candidate accuracy")


def test_gate_cli_fails_on_missing_policy(tmp_path: Path) -> None:
    report = tmp_path / "failure.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/model_gate.py"),
            "--policy",
            str(tmp_path / "absent.json"),
            "--report",
            str(report),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode != 0
    assert json.loads(report.read_text(encoding="utf-8"))["passed"] is False
