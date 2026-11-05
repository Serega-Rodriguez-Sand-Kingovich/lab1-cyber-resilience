"""Validate the original Lab 1 CSV bytes and analyze the balanced sample.

No training occurs if data integrity or the 65-column data contract fails.
The original dataset is never silently changed or repaired.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from .config import (
    CLASSES, DATA_MANIFEST, DATA_PATH, EXPECTED_DATA_HASHES,
    FEATURE_COLUMNS, LABEL_COLUMN, ORIGINAL_PATH, ROOT, SEED, TEST_SIZE,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_lab1_data() -> dict[str, str]:
    """Require both recorded Lab 1 hashes, including the old manifest."""
    if not DATA_MANIFEST.is_file():
        raise FileNotFoundError(f"Missing Lab 1 checksum manifest: {DATA_MANIFEST}")
    recorded: dict[str, str] = {}
    pattern = re.compile(r"^([a-fA-F0-9]{64})  (data/[^/]+\.csv)$")
    for line in DATA_MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        match = pattern.fullmatch(line)
        if match is None:
            raise ValueError("Malformed Lab 1 checksum manifest")
        expected_hash, rel = match.groups()
        if rel in recorded:
            raise ValueError("Duplicate manifest entry")
        recorded[rel] = expected_hash.lower()
    if recorded != EXPECTED_DATA_HASHES:
        raise ValueError("Lab 1 checksum manifest differs from the trusted reference")
    result: dict[str, str] = {}
    for rel, expected in EXPECTED_DATA_HASHES.items():
        path = ROOT / rel
        if not path.is_file():
            raise FileNotFoundError(f"Dataset is missing: {path}")
        actual = sha256_file(path)
        if actual != expected:
            raise ValueError(f"SHA256 does not match Lab 1: {rel}; actual={actual}")
        result[rel] = actual
    return result


def load_and_check_data() -> tuple[np.ndarray, np.ndarray, dict]:
    """Return X, y and a serializable, audit-friendly data-quality record."""
    hashes = verify_lab1_data()
    frame = pd.read_csv(DATA_PATH)
    original = pd.read_csv(ORIGINAL_PATH)
    expected_columns = list(FEATURE_COLUMNS) + [LABEL_COLUMN]
    if frame.columns.tolist() != expected_columns:
        raise ValueError("Balanced data has unexpected columns, order or names")
    if original.columns.tolist() != expected_columns:
        raise ValueError("Original data has unexpected columns, order or names")

    # The original and balanced datasets are both checked without modifying either.
    original_missing = int(original.isna().sum().sum())
    original_duplicates = int(original.duplicated().sum())
    original_feature_duplicates = int(original.duplicated(subset=list(FEATURE_COLUMNS)).sum())
    original_numeric = original.select_dtypes(include="number").columns.tolist()
    if set(original_numeric) != set(expected_columns):
        raise ValueError("Original data contains nonnumeric columns")
    original_values = original[list(FEATURE_COLUMNS)].to_numpy(dtype=np.float64)
    original_targets = original[LABEL_COLUMN].to_numpy(dtype=np.float64)
    if (original_missing or original_duplicates or original_feature_duplicates
            or not np.isfinite(original_values).all() or not np.isfinite(original_targets).all()):
        raise ValueError("Original data has missing, duplicated, NaN or Inf values")
    if (np.any((original_values < 0) | (original_values > 16))
            or not np.array_equal(original_values, np.floor(original_values))
            or not np.array_equal(original_targets, np.floor(original_targets))):
        raise ValueError("Original image pixels or labels violate the Digits schema")
    unique_orig_labels, unique_orig_counts = np.unique(original_targets.astype(np.int64), return_counts=True)
    if not np.array_equal(unique_orig_labels, np.array(CLASSES)):
        raise ValueError("Original labels must be exactly 0 through 9")

    missing_by_column = frame.isna().sum()
    missing = int(missing_by_column.sum())
    duplicated_full = int(frame.duplicated().sum())
    duplicated_features = int(frame.duplicated(subset=list(FEATURE_COLUMNS)).sum())
    numeric_columns = frame.select_dtypes(include="number").columns.tolist()
    invalid_dtype = [column for column in expected_columns if column not in numeric_columns]
    if invalid_dtype:
        raise ValueError(f"Non-numeric columns: {invalid_dtype}")
    if missing:
        raise ValueError(f"Missing values found ({missing}); no implicit imputation")
    if duplicated_full or duplicated_features:
        raise ValueError("Duplicate digit vectors found; manually review possible leakage")

    X = frame[list(FEATURE_COLUMNS)].to_numpy(dtype=np.float64, copy=True)
    raw_y = frame[LABEL_COLUMN].to_numpy(dtype=np.float64)
    if not np.isfinite(X).all() or not np.isfinite(raw_y).all():
        raise ValueError("NaN or Inf in dataset")
    if np.any((X < 0) | (X > 16)):
        raise ValueError("Digits pixel values must be between 0 and 16")
    if not np.array_equal(X, np.floor(X)):
        raise ValueError("The frozen Lab 1 dataset has unexpected non-integral pixels")
    if not np.array_equal(raw_y, np.floor(raw_y)):
        raise ValueError("The dataset has non-integral labels")
    y = raw_y.astype(np.int64)
    classes, counts = np.unique(y, return_counts=True)
    if not np.array_equal(classes, np.array(CLASSES)):
        raise ValueError("Class labels must be exactly 0 through 9")
    if not np.all(counts == 174) or len(y) != 1740:
        raise ValueError("Lab 1 balanced dataset is not 174 objects per class")
    if len(original) != 1797:
        raise ValueError("Lab 1 original dataset must contain 1797 objects")

    unique_original = original.drop_duplicates()
    membership = frame.merge(unique_original, on=expected_columns, how="left", indicator=True)
    if len(membership) != len(frame) or not (membership["_merge"] == "both").all():
        raise ValueError("Balanced dataset contains values absent from original data")

    summary = {
        "data_version": hashes["data/digits.csv"],
        "original_version": hashes["data/digits_original.csv"],
        "rows_original": int(len(original)),
        "rows_balanced": int(len(frame)),
        "rows_removed_in_lab1": int(len(original) - len(frame)),
        "original_class_counts": {str(k): int(v) for k, v in zip(unique_orig_labels, unique_orig_counts)},
        "original_missing_total": original_missing,
        "original_duplicate_complete_rows": original_duplicates,
        "original_duplicate_feature_vectors": original_feature_duplicates,
        "n_features": int(X.shape[1]),
        "input_shape": [8, 8],
        "classes": {str(k): int(v) for k, v in zip(classes, counts)},
        "max_class_ratio": float(counts.max() / counts.min()),
        "missing_total": missing,
        "missing_by_column_nonzero": {k: int(v) for k, v in missing_by_column.items() if v != 0},
        "duplicate_complete_rows": duplicated_full,
        "duplicate_feature_vectors": duplicated_features,
        "nan_inf_total": 0,
        "outside_pixel_range": 0,
        "non_integral_pixel_values": 0,
        "feature_dtype": "float64",
        "label_dtype": "int64",
        "rows_removed_in_lab2": 0,
        "imputed_values_in_lab2": 0,
        "features_used": list(FEATURE_COLUMNS),
        "limitations": [
            "Small normalized 8x8 grayscale digits, not real photos or handwriting on forms.",
            "CSV does not contain writer/source/group identifiers; group-exclusive split cannot be verified.",
            "Balanced selection in Lab 1 removed 57 examples and may alter population frequencies.",
        ],
    }
    return X, y, summary


def split_data(X: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    indices = np.arange(len(y), dtype=np.int64)
    train_idx, test_idx = train_test_split(
        indices, test_size=TEST_SIZE, random_state=SEED, stratify=y
    )
    train_vectors = {tuple(row.tolist()) for row in X[train_idx]}
    test_vectors = {tuple(row.tolist()) for row in X[test_idx]}
    if train_vectors.intersection(test_vectors):
        raise ValueError("Overlapping feature vectors between train and test")
    if set(train_idx.tolist()).intersection(test_idx.tolist()):
        raise ValueError("Overlapping training/test row indices")
    if sorted(np.concatenate((train_idx, test_idx)).tolist()) != list(range(len(y))):
        raise ValueError("Split is not a partition of all rows")
    return train_idx, test_idx


def save_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
