"""A small reproducible sensitivity check, not a certified adversarial test."""
from __future__ import annotations

import json

import numpy as np
from sklearn.neighbors import NearestNeighbors

from .config import METRICS_DIR, ROBUSTNESS_SEED
from .data import load_and_check_data, save_json, split_data
from .figures import plot_atypical, plot_perturbations, plot_robustness
from .inference import load_verified_model, predict_digits


def _predict_by_batches(model: object, batch: np.ndarray) -> np.ndarray:
    parts = [predict_digits(model, batch[i:i + 32]) for i in range(0, len(batch), 32)]
    return np.concatenate(parts)


def run_robustness() -> dict:
    X, y, data_quality = load_and_check_data()
    train_idx, test_idx = split_data(X, y)
    manifest_path = METRICS_DIR / "split_indices.json"
    if not manifest_path.is_file():
        raise FileNotFoundError("Train the model before running robustness analysis")
    split = json.loads(manifest_path.read_text(encoding="utf-8"))
    if split["data_version"] != data_quality["data_version"]:
        raise ValueError("Split data version does not match dataset")
    if split["train_indices"] != train_idx.tolist() or split["test_indices"] != test_idx.tolist():
        raise ValueError("Saved split does not match reproducible split")

    X_train, X_test, y_test = X[train_idx], X[test_idx], y[test_idx]
    model = load_verified_model()
    rng = np.random.default_rng(ROBUSTNESS_SEED)
    selected = np.concatenate([
        rng.choice(np.flatnonzero(y_test == digit), size=2, replace=False)
        for digit in range(10)
    ])
    clean = X_test[selected]
    truth = y_test[selected]
    noisy = np.clip(clean + rng.normal(loc=0, scale=0.8, size=clean.shape), 0, 16)
    brighter = np.clip(clean + 0.6, 0, 16)
    clean_pred = _predict_by_batches(model, clean)
    noise_pred = _predict_by_batches(model, noisy)
    brightness_pred = _predict_by_batches(model, brighter)

    def evaluate(changed: np.ndarray) -> dict:
        return {
            "accuracy": float(np.mean(changed == truth)),
            "changed_fraction": float(np.mean(changed != clean_pred)),
            "changed_count": int(np.count_nonzero(changed != clean_pred)),
        }

    nearest = NearestNeighbors(n_neighbors=1, algorithm="brute")
    nearest.fit(X_train)
    typical_distances = nearest.kneighbors(X_test, return_distance=True)[0][:, 0]
    atypical = np.full((8, 8), 16.0, dtype=np.float64)
    unusual_pred = predict_digits(model, atypical)
    atypical_distance = float(nearest.kneighbors(atypical.reshape(1, 64))[0][0, 0])
    percentile_95 = float(np.quantile(typical_distances, 0.95))
    unusual_outside = bool(atypical_distance > percentile_95)

    report = {
        "data_version": data_quality["data_version"],
        "n_examples": 20,
        "selected_test_indices": test_idx[selected].tolist(),
        "selection": "Two random examples per class from held-out test, seed 2026",
        "noise": {"type": "independent Gaussian pixel noise", "sigma": 0.8, "clipped_range": [0, 16]},
        "brightness": {"type": "constant pixel shift", "offset": 0.6, "clipped_range": [0, 16]},
        "variants": {
            "clean": evaluate(clean_pred),
            "noise": evaluate(noise_pred),
            "brightness": evaluate(brightness_pred),
        },
        "atypical_example": {
            "description": "A fully bright 8x8 matrix; syntactically valid but unlike handwritten digits",
            "prediction": int(unusual_pred[0]),
            "distance_to_nearest_training_example_l2": atypical_distance,
            "test_nearest_neighbor_distance_p95_l2": percentile_95,
            "exceeds_typical_test_p95": unusual_outside,
            "response": "Accepted by shape/range checks; model still returns a digit (no rejection option).",
            "caution": "This is evidence of atypicality for this dataset, not a universal OOD detector.",
        },
        "interpretation": (
            "20 examples are insufficient to claim general robustness. "
            "Small perturbations may flip labels even when each pixel remains within the allowed range. "
            "Shape validation cannot detect atypical but numerically valid pictures."
        ),
        "proposed_defense": "Investigate calibrated abstention or distance-based anomaly screening on a separate validation set.",
    }
    save_json(METRICS_DIR / "robustness.json", report)
    plot_perturbations(clean, noisy, truth, clean_pred, noise_pred)
    plot_robustness(report)
    plot_atypical(atypical, clean[0], int(unusual_pred[0]))
    print("Lab 2 robustness experiment complete")
    for label in ("clean", "noise", "brightness"):
        result = report["variants"][label]
        print(f"{label}: accuracy={result['accuracy']:.3f}; changed={result['changed_count']}/20")
    print(f"Atypical input: predicted={int(unusual_pred[0])}; neighbor-distance={atypical_distance:.2f}")
    print(f"Typical held-out nearest-neighbor 95th percentile={percentile_95:.2f}")
    return report


if __name__ == "__main__":
    run_robustness()
