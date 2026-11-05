"""Immutable project settings and trusted Lab 1 data fingerprints."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "digits.csv"
ORIGINAL_PATH = ROOT / "data" / "digits_original.csv"
DATA_MANIFEST = ROOT / "integrity" / "datasets.sha256"
MODEL_PATH = ROOT / "models" / "digits_baseline.joblib"
MODEL_MANIFEST = ROOT / "integrity" / "model.sha256"
METRICS_DIR = ROOT / "metrics"
FIGURES_DIR = ROOT / "reports" / "figures"
EVIDENCE_DIR = ROOT / "reports" / "evidence"

EXPECTED_DATA_HASHES = {
    "data/digits_original.csv": "59834b81e5525fe3152c7416217c7790c2213c0da554e89ae96dddef27b35bda",
    "data/digits.csv": "4b55658bf1299c5e4bdce02ae154081e2694f74e22eca2c5bc8b7a5c8d67419e",
}
FEATURE_COLUMNS = tuple(f"pixel_{row}_{col}" for row in range(8) for col in range(8))
LABEL_COLUMN = "target"
CLASSES = tuple(range(10))
SEED = 42
ROBUSTNESS_SEED = 2026
TEST_SIZE = 0.20
MAX_BATCH = 32
MAX_ARRAY_BYTES = 64 * MAX_BATCH * 8
PIXEL_MIN = 0.0
PIXEL_MAX = 16.0
