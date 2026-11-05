"""Evaluate a trusted Digits model and fail CI on a quality regression.

Real mode measures predictions on the pinned Lab 2 holdout. Demo mode
measures a weak constant predictor on the same examples (not a fake score).
Exit status: 0 if the policy passes, 1 for any policy/runtime failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from datetime import UTC, datetime
from numbers import Real
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class ModelGateError(Exception):
    """A mandatory model quality check could not be completed."""


def numeric_metric(value: object, label: str) -> float:
    """Accept finite scalar numbers, never bool/strings/NaN/Inf."""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ModelGateError(f"{label} must be a finite numeric value")
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 1:
        raise ModelGateError(f"{label} must be a finite number in [0, 1]")
    return number


def compare_metric(
    baseline: dict[str, Any],
    policy: dict[str, Any],
    candidate_value: object,
    candidate_data_version: str,
) -> dict[str, Any]:
    """Compare a real measured metric with an immutable Lab 2 baseline."""
    expected_name = policy.get("metric_name")
    if expected_name != "accuracy":
        raise ModelGateError("Only accuracy (higher is better) is supported")
    if baseline.get("primary_metric_name") != expected_name:
        raise ModelGateError("Baseline metric name is incompatible with policy")
    baseline_data_version = baseline.get("data_version")
    if baseline_data_version != policy.get("dataset_sha256"):
        raise ModelGateError("Baseline dataset version differs from pinned policy")
    if candidate_data_version != baseline_data_version:
        raise ModelGateError("Candidate and baseline dataset versions differ")

    baseline_value = numeric_metric(
        baseline.get("primary_metric_value"), "baseline accuracy"
    )
    candidate = numeric_metric(candidate_value, "candidate accuracy")
    if baseline_value == 0:
        raise ModelGateError("Zero baseline requires a separate absolute policy")
    degradation = policy.get("max_relative_drop")
    if isinstance(degradation, bool) or not isinstance(degradation, Real):
        raise ModelGateError("max_relative_drop must be numeric")
    degradation = float(degradation)
    if not math.isfinite(degradation) or not 0 <= degradation < 1:
        raise ModelGateError("max_relative_drop must be in [0, 1)")

    threshold = baseline_value * (1.0 - degradation)
    return {
        "metric_name": expected_name,
        "baseline": baseline_value,
        "candidate": candidate,
        "max_relative_drop": degradation,
        "threshold": threshold,
        "data_version": candidate_data_version,
        "passed": candidate >= threshold,
    }


def sha256(path: Path) -> str:
    """Return hash of a local, existing file."""
    if not path.is_file():
        raise ModelGateError(f"Missing file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def control_set(policy: dict[str, Any]) -> tuple[Any, Any, str]:
    """Recreate the exact 80/20 stratified Lab 2 split without retraining."""
    import numpy as np
    import pandas as pd
    from sklearn.model_selection import train_test_split

    path = ROOT / policy["dataset_path"]
    actual_hash = sha256(path)
    if actual_hash != policy["dataset_sha256"]:
        raise ModelGateError("Pinned dataset SHA256 mismatch; data gate must pass")
    frame = pd.read_csv(path)
    expected_columns = [f"pixel_{r}_{c}" for r in range(8) for c in range(8)]
    if list(frame.columns) != expected_columns + ["target"]:
        raise ModelGateError("CSV schema differs from Lab 2")
    features = frame[expected_columns].to_numpy(dtype=np.float64)
    labels = frame["target"].to_numpy(dtype=np.int64)
    if not np.isfinite(features).all() or features.shape != (1740, 64):
        raise ModelGateError("Invalid control features")
    indices = np.arange(len(labels))
    _, test_indices = train_test_split(
        indices,
        test_size=policy["test_size"],
        random_state=policy["random_state"],
        stratify=labels,
    )
    if len(test_indices) != policy["expected_test_rows"]:
        raise ModelGateError("Unexpected test split size")
    return features[test_indices], labels[test_indices], actual_hash


class WeakConstantPredictor:
    """Known weak predictor used only for an explicit failure demonstration."""

    def predict(self, features: Any) -> Any:
        import numpy as np

        return np.zeros(len(features), dtype=np.int64)


def calculate_accuracy(labels: Any, predictions: Any) -> float:
    """Calculate the same accuracy metric used in the Lab 2 baseline."""
    from sklearn.metrics import accuracy_score

    return float(accuracy_score(labels, predictions))


def candidate_accuracy(
    features: Any,
    labels: Any,
    model: Any,
    batch_size: int,
) -> float:
    """Compute accuracy through the same validated prediction API as Lab 2."""
    import numpy as np

    from src.inference import predict_digits

    if isinstance(batch_size, bool) or not isinstance(batch_size, int):
        raise ModelGateError("predict_batch_size must be an integer")
    if not 1 <= batch_size <= 32:
        raise ModelGateError("predict_batch_size must be between 1 and 32")
    batches = [
        np.asarray(predict_digits(model, features[start : start + batch_size]))
        for start in range(0, len(labels), batch_size)
    ]
    predictions = np.concatenate(batches)
    if predictions.shape != labels.shape:
        raise ModelGateError("Candidate prediction shape is invalid")
    if not np.isin(predictions, np.arange(10)).all():
        raise ModelGateError("Candidate returned an invalid class label")
    return calculate_accuracy(labels, predictions)


def current_commit() -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def run(
    policy_path: Path,
    demo_weak_candidate: bool,
    candidate_model_path: Path | None,
    expected_model_sha256: str | None,
) -> dict[str, Any]:
    import joblib

    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    baseline_path = ROOT / policy["baseline_path"]
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    features, labels, dataset_hash = control_set(policy)
    if baseline.get("n_test") != len(labels):
        raise ModelGateError("Baseline/control sample counts do not match")

    if demo_weak_candidate:
        if candidate_model_path is not None or expected_model_sha256 is not None:
            raise ModelGateError("Weak-demo mode cannot load an external model")
        model = WeakConstantPredictor()
        model_hash = None
        model_kind = "DEMO: weak constant class-0 predictor (real evaluation)"
    else:
        path = candidate_model_path or ROOT / policy["model_path"]
        model_hash = sha256(path)
        approved_hash = expected_model_sha256 or baseline.get("model_sha256")
        if not isinstance(approved_hash, str) or len(approved_hash) != 64:
            raise ModelGateError("Missing valid, approved model SHA256")
        if model_hash != approved_hash:
            raise ModelGateError("Model SHA256 differs from approved artifact")
        # joblib uses pickle; only load after matching a trusted, approved hash.
        model = joblib.load(path)
        model_kind = "approved serialized candidate"

    measured = candidate_accuracy(
        features, labels, model, policy["predict_batch_size"]
    )
    comparison = compare_metric(baseline, policy, measured, dataset_hash)
    return {
        **comparison,
        "model_kind": model_kind,
        "model_sha256": model_hash,
        "control_rows": len(labels),
        "expected_control_rows": policy["expected_test_rows"],
        "baseline_file": str(baseline_path.relative_to(ROOT)),
        "policy_file": str(policy_path),
        "note": "Repeated CI control is not a new independent final evaluation.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed ML model quality gate")
    parser.add_argument(
        "--policy", type=Path, default=ROOT / "config/model_quality_policy.json"
    )
    parser.add_argument(
        "--report", type=Path, default=ROOT / "reports/lab3/model_gate.json"
    )
    parser.add_argument(
        "--demo-weak-candidate", action="store_true",
        help="Evaluate a real weak constant predictor on the pinned data",
    )
    parser.add_argument("--model", type=Path, default=None)
    parser.add_argument(
        "--expected-model-sha256",
        type=str,
        default=None,
        help="SHA256 from a trusted candidate manifest for a non-baseline model",
    )
    args = parser.parse_args()
    report: dict[str, Any] = {
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "git_commit": current_commit(),
        "passed": False,
        "exit_code": 1,
        "errors": [],
    }
    try:
        outcome = run(
            args.policy,
            args.demo_weak_candidate,
            args.model,
            args.expected_model_sha256,
        )
        report.update(outcome)
        if not outcome["passed"]:
            report["errors"].append(
                "Candidate accuracy is below baseline * (1 - max_relative_drop)"
            )
    except Exception as exc:  # noqa: BLE001
        # CLI boundary: record any failure and keep a nonzero exit code.
        report["errors"].append(f"{type(exc).__name__}: {exc}")

    report["exit_code"] = 0 if report["passed"] else 1
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if report["passed"]:
        print(
            "MODEL GATE PASS: "
            f"accuracy={report['candidate']:.6f}, "
            f"baseline={report['baseline']:.6f}, "
            f"threshold={report['threshold']:.6f}"
        )
    else:
        print("MODEL GATE FAIL:", file=sys.stderr)
        if "candidate" in report and "threshold" in report:
            print(
                f"  candidate={report['candidate']:.6f}, "
                f"threshold={report['threshold']:.6f}",
                file=sys.stderr,
            )
        for error in report["errors"]:
            print(f"  - {error}", file=sys.stderr)
    print(f"Report: {args.report}")
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
