"""Read-only smoke check of the approved Lab 2 model inside a non-root image.

The joblib file is only deserialized after comparing its SHA256 to a trusted
baseline. This detects accidental substitution but does not make pickle safe
against an attacker who can change both files simultaneously.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Real 8x8 digit sample (digit 0) from the public scikit-learn digits set.
DIGIT_ZERO = (
    (0, 0, 5, 13, 9, 1, 0, 0),
    (0, 0, 13, 15, 10, 15, 5, 0),
    (0, 3, 15, 2, 0, 11, 8, 0),
    (0, 4, 12, 0, 0, 8, 8, 0),
    (0, 5, 8, 0, 0, 9, 8, 0),
    (0, 4, 11, 0, 1, 12, 7, 0),
    (0, 2, 14, 5, 10, 12, 0, 0),
    (0, 0, 6, 13, 10, 0, 0, 0),
)


def verify_sha256(path: Path, expected: str) -> str:
    """Fail before model deserialization if the pinned hash is invalid/mismatched."""
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("Baseline model SHA256 is missing or malformed")
    if not path.is_file():
        raise FileNotFoundError(f"Missing approved model: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    actual = digest.hexdigest()
    if actual != expected:
        raise ValueError("Model SHA256 differs from trusted baseline - refuse to load")
    return actual


def sample_digit() -> object:
    """Provide a validated N x 64 numeric example to the application API."""
    import numpy as np

    sample = np.asarray(DIGIT_ZERO, dtype=np.float64).reshape(1, 64)
    if sample.shape != (1, 64) or not np.isfinite(sample).all():
        raise ValueError("Invalid smoke sample")
    if (sample < 0).any() or (sample > 16).any():
        raise ValueError("Smoke sample outside allowed 0..16 intensity range")
    return sample


def main() -> int:
    import joblib
    import numpy as np

    from src.inference import predict_digits

    uid = os.getuid()
    if uid == 0:
        raise RuntimeError("SMOKE FAIL: inference must not execute as root")

    baseline = json.loads((ROOT / "metrics/baseline.json").read_text(encoding="utf-8"))
    if baseline.get("primary_metric_name") != "accuracy":
        raise ValueError("Unexpected baseline format")
    model_path = ROOT / "models/digits_baseline.joblib"
    digest = verify_sha256(model_path, baseline.get("model_sha256", ""))

    # joblib/pickle can execute code. Never load unknown or unverified files.
    model = joblib.load(model_path)
    output = np.asarray(predict_digits(model, sample_digit()))
    if output.shape != (1,) or not np.issubdtype(output.dtype, np.integer):
        raise RuntimeError(
            "SMOKE FAIL: model returned a non-integer or wrong-sized result"
        )
    digit = int(output[0])
    if not 0 <= digit <= 9:
        raise RuntimeError("SMOKE FAIL: predicted class outside 0..9")

    print(f"SMOKE PASS: uid={uid}, prediction={digit}, model_sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
