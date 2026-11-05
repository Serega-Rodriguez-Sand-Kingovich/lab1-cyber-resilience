"""Train once on the Lab 1 balanced digits and freeze an unbiased baseline.

The hold-out test is touched only after the model definition has been fixed.
There is no hyperparameter search, and the scaler is fitted only on X_train.
"""
from __future__ import annotations

import platform
import time
from datetime import UTC, datetime

import joblib
import matplotlib
import numpy as np
import pandas as pd
import sklearn
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .config import (
    CLASSES,
    FIGURES_DIR,
    METRICS_DIR,
    MODEL_MANIFEST,
    MODEL_PATH,
    SEED,
    TEST_SIZE,
)
from .data import load_and_check_data, save_json, sha256_file, split_data
from .figures import (
    plot_class_f1,
    plot_class_split,
    plot_confusion,
    plot_wrong_predictions,
)
from .inference import load_verified_model, predict_digits


def predict_many(model: object, X: np.ndarray, batch_size: int = 32) -> np.ndarray:
    """Ensure evaluation and later serving pass through the same gateway."""
    outputs = []
    for begin in range(0, len(X), batch_size):
        outputs.append(predict_digits(model, X[begin:begin + batch_size], batch_size))
    return np.concatenate(outputs)


def run_training() -> dict:
    X, y, data_summary = load_and_check_data()
    train_idx, test_idx = split_data(X, y)
    X_train, X_test = X[train_idx], X[test_idx]
    y_train, y_test = y[train_idx], y[test_idx]
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)

    split_info = {
        "data_version": data_summary["data_version"],
        "random_state": SEED,
        "test_size_fraction": TEST_SIZE,
        "method": "train_test_split(stratify=y)",
        "n_train": len(train_idx),
        "n_test": len(test_idx),
        "train_indices": train_idx.tolist(),
        "test_indices": test_idx.tolist(),
        "train_class_counts": {str(k): int(v) for k, v in zip(*np.unique(y_train, return_counts=True))},
        "test_class_counts": {str(k): int(v) for k, v in zip(*np.unique(y_test, return_counts=True))},
        "no_shared_feature_vectors": True,
        "source_group_limit": "Writer and original series IDs absent from the CSV; group leakage cannot be independently audited.",
    }
    save_json(METRICS_DIR / "data_quality.json", data_summary)
    save_json(METRICS_DIR / "split_indices.json", split_info)

    # Logistic regression is a transparent and lightweight image baseline.
    # StandardScaler is INSIDE the fitted pipeline, not fitted on all data.
    model = Pipeline([
        ("scaler", StandardScaler()),
        ("classifier", LogisticRegression(
            C=1.0, solver="lbfgs", max_iter=2000, random_state=SEED,
        )),
    ])
    started = time.perf_counter()
    model.fit(X_train, y_train)
    fit_seconds = time.perf_counter() - started

    # Persist this very model, without fitting on the test split.
    joblib.dump(model, MODEL_PATH, compress=3)
    MODEL_PATH.chmod(0o600)  # Локальный файл доступен только mluser.
    model_sha256 = sha256_file(MODEL_PATH)
    MODEL_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MODEL_MANIFEST.write_text(
        f"{model_sha256}  models/{MODEL_PATH.name}\n", encoding="ascii"
    )
    MODEL_MANIFEST.chmod(0o600)
    verified_model = load_verified_model()
    predictions = predict_many(verified_model, X_test)
    if not np.array_equal(predictions, model.predict(X_test)):
        raise RuntimeError("Deserialized and original model predictions differ")

    reference = DummyClassifier(strategy="most_frequent")
    reference.fit(X_train, y_train)
    reference_predictions = reference.predict(X_test)
    detailed_report = classification_report(
        y_test, predictions, labels=list(CLASSES), output_dict=True,
        zero_division=0,
    )
    training_settings = {
        "algorithm": "scikit-learn Pipeline(StandardScaler, LogisticRegression)",
        "scaler": "StandardScaler; parameters fitted only on X_train",
        "classifier": "LogisticRegression",
        "classifier_settings": {"C": 1.0, "solver": "lbfgs", "max_iter": 2000, "random_state": SEED},
        "validation_strategy": "No tuning; fixed configuration and one stratified train/test split",
        "reference": "DummyClassifier(strategy=most_frequent)",
        "data_version": data_summary["data_version"],
        "split_seed": SEED,
        "test_fraction": TEST_SIZE,
        "fit_seconds": fit_seconds,
        "model_path": "models/digits_baseline.joblib",
        "model_sha256": model_sha256,
        "training_utc": datetime.now(UTC).isoformat(),
        "versions": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scikit_learn": sklearn.__version__,
            "joblib": joblib.__version__,
            "matplotlib": matplotlib.__version__,
        },
        "security_note": "joblib is pickle-based; load only the project-owned artifact after verification against an independently trusted checksum.",
    }
    save_json(METRICS_DIR / "training_config.json", training_settings)

    metrics = {
        "primary_metric_name": "accuracy",
        "primary_metric_value": float(accuracy_score(y_test, predictions)),
        "data_version": data_summary["data_version"],
        "model_sha256": model_sha256,
        "n_train": len(y_train),
        "n_test": len(y_test),
        "accuracy": float(accuracy_score(y_test, predictions)),
        "precision_macro": float(precision_score(y_test, predictions, average="macro", zero_division=0)),
        "recall_macro": float(recall_score(y_test, predictions, average="macro", zero_division=0)),
        "f1_macro": float(f1_score(y_test, predictions, average="macro", zero_division=0)),
        "precision_weighted": float(precision_score(y_test, predictions, average="weighted", zero_division=0)),
        "recall_weighted": float(recall_score(y_test, predictions, average="weighted", zero_division=0)),
        "f1_weighted": float(f1_score(y_test, predictions, average="weighted", zero_division=0)),
        "reference_majority_accuracy": float(accuracy_score(y_test, reference_predictions)),
        "wrong_predictions": int(np.count_nonzero(y_test != predictions)),
        "averaging": "Macro: arithmetic mean over 10 classes; weighted: weighted by test class support",
        "per_class": {
            str(i): {
                "precision": float(detailed_report[str(i)]["precision"]),
                "recall": float(detailed_report[str(i)]["recall"]),
                "f1": float(detailed_report[str(i)]["f1-score"]),
                "support": int(detailed_report[str(i)]["support"]),
            }
            for i in CLASSES
        },
    }
    save_json(METRICS_DIR / "baseline.json", metrics)
    cm = confusion_matrix(y_test, predictions, labels=list(CLASSES))
    pd.DataFrame(cm, index=CLASSES, columns=CLASSES).to_csv(
        METRICS_DIR / "confusion_matrix.csv", index_label="true_class"
    )
    pd.DataFrame({
        "dataset_row_index": test_idx,
        "true_label": y_test,
        "predicted_label": predictions,
        "correct": y_test == predictions,
    }).to_csv(METRICS_DIR / "test_predictions.csv", index=False)

    figures = [
        plot_class_split(y_train, y_test),
        plot_confusion(y_test, predictions),
        plot_class_f1(detailed_report),
        plot_wrong_predictions(X_test, y_test, predictions),
    ]
    print("Lab 2 training complete")
    print(f"Training: {len(train_idx)}, test: {len(test_idx)}, classes: {len(CLASSES)}")
    print(f"Data SHA256: {data_summary['data_version']}")
    print(f"Model SHA256: {model_sha256}")
    print(f"Accuracy={metrics['accuracy']:.4f}; macro F1={metrics['f1_macro']:.4f}")
    print(f"Majority baseline accuracy={metrics['reference_majority_accuracy']:.4f}")
    print(f"Training seconds={fit_seconds:.3f}")
    print(f"Figures saved: {len([path for path in figures if path is not None])}")
    print(f"Metrics file: {METRICS_DIR / 'baseline.json'}")
    return metrics


if __name__ == "__main__":
    run_training()
