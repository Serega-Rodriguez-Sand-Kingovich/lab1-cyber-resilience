"""Validate a pinned Digits CSV before training or model evaluation.

Exit status: 0 means all required checks pass, 1 means gate failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def evaluate(data: Path, policy: dict) -> dict:
    errors: list[str] = []
    result: dict = {
        "dataset": str(data),
        "dataset_version": policy["dataset_version"],
        "expected_sha256": policy["sha256"],
        "actual_sha256": None,
        "row_count": None,
        "class_counts": {},
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "passed": False,
        "errors": errors,
    }

    if not data.is_file():
        errors.append("Dataset file is missing")
        return result
    if data.stat().st_size > policy["max_file_bytes"]:
        errors.append("Dataset file exceeds max_file_bytes")
        return result

    actual_hash = hashlib.sha256(data.read_bytes()).hexdigest()
    result["actual_sha256"] = actual_hash
    if actual_hash != policy["sha256"]:
        errors.append("SHA256 mismatch: the file differs from the pinned dataset")

    try:
        frame = pd.read_csv(data)
    except (
        OSError,
        ValueError,
        pd.errors.ParserError,
        pd.errors.EmptyDataError,
    ) as exc:
        errors.append(f"CSV cannot be parsed: {type(exc).__name__}")
        return result

    features = [
        f"pixel_{r}_{c}"
        for r in range(policy["image_height"])
        for c in range(policy["image_width"])
    ]
    expected_columns = features + [policy["label_column"]]
    actual_columns = frame.columns.tolist()
    if actual_columns != expected_columns:
        missing = sorted(set(expected_columns) - set(actual_columns))
        extra = sorted(set(actual_columns) - set(expected_columns))
        errors.append(
            f"CSV schema mismatch: missing={missing}, extra={extra}, "
            f"order_mismatch={not (missing or extra)}"
        )

    result["row_count"] = len(frame)
    if not policy["min_rows"] <= len(frame) <= policy["max_rows"]:
        errors.append(f"Row count {len(frame)} outside permitted range")

    if actual_columns == expected_columns:
        if frame.isna().to_numpy().any():
            errors.append("Missing/NaN values are not allowed")

        numeric_features = (
            frame[features]
            .apply(pd.to_numeric, errors="coerce")
            .to_numpy(dtype=np.float64)
        )
        if not np.isfinite(numeric_features).all():
            errors.append("Feature values must be numeric and finite (no NaN/Inf)")
        elif (
            (numeric_features < policy["min_pixel"])
            | (numeric_features > policy["max_pixel"])
        ).any():
            errors.append("Pixel values outside permitted range")

        labels = pd.to_numeric(
            frame[policy["label_column"]], errors="coerce"
        ).to_numpy(dtype=np.float64)
        if not np.isfinite(labels).all() or (labels != np.floor(labels)).any():
            errors.append("Class labels must be finite integers")
        else:
            counts = Counter(int(v) for v in labels)
            result["class_counts"] = {
                str(k): counts.get(k, 0) for k in policy["labels"]
            }
            if set(counts) != set(policy["labels"]):
                errors.append("Class labels differ from the expected 0..9 set")
            if any(
                counts.get(k, 0) < policy["min_per_class"]
                or counts.get(k, 0) > policy["max_per_class"]
                for k in policy["labels"]
            ):
                errors.append("Class distribution outside configured limits")

    result["passed"] = not errors
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Dataset quality gate for ML CI")
    parser.add_argument(
        "--policy", type=Path, default=ROOT / "config/data_quality_policy.json"
    )
    parser.add_argument("--data", type=Path, default=None)
    parser.add_argument(
        "--report", type=Path, default=ROOT / "reports/lab3/data_gate.json"
    )
    args = parser.parse_args()

    try:
        policy = json.loads(args.policy.read_text(encoding="utf-8"))
        data_path = (
            args.data if args.data is not None else ROOT / policy["dataset_path"]
        )
        result = evaluate(data_path, policy)
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
        result = {
            "passed": False,
            "errors": [
                f"Gate configuration/runtime error: {type(exc).__name__}: {exc}"
            ],
        }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if result["passed"]:
        print(f"DATA GATE PASS: {result['row_count']} rows, SHA256 OK, 10 classes")
        print(f"Report: {args.report}")
        return 0
    print("DATA GATE FAIL:", file=sys.stderr)
    for err in result["errors"]:
        print(f"  - {err}", file=sys.stderr)
    print(f"Report: {args.report}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
