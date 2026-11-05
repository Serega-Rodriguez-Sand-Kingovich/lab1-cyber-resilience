"""Safely verify committed Lab 2 data/model baselines and show a prediction."""
from __future__ import annotations

import json

from .config import METRICS_DIR, MODEL_PATH
from .data import load_and_check_data
from .inference import load_verified_model, predict_digits


def main() -> None:
    X, y, checks = load_and_check_data()
    model = load_verified_model()
    baseline = json.loads((METRICS_DIR / "baseline.json").read_text(encoding="utf-8"))
    if checks["data_version"] != baseline["data_version"]:
        raise ValueError("Metrics are not associated with the verified dataset")
    prediction = predict_digits(model, X[0].reshape(8, 8))
    print("Lab 1 data checksums OK")
    print("Lab 2 model checksum OK")
    print(f"Model path: {MODEL_PATH}")
    print(f"Model can be reloaded; first input: label={y[0]}, prediction={int(prediction[0])}")
    print(f"Saved held-out accuracy: {baseline['accuracy']:.4f}")


if __name__ == "__main__":
    main()
