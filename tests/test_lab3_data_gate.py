"""Behavioral tests for the CI data quality gate."""

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/data_gate.py"


def run_gate(dataset: Path, report: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--data", str(dataset), "--report", str(report)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_data_gate_accepts_pinned_dataset(tmp_path: Path) -> None:
    report = tmp_path / "accepted.json"
    completed = run_gate(ROOT / "data/digits.csv", report)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(report.read_text(encoding="utf-8"))
    assert result["passed"] is True
    assert result["row_count"] == 1740
    assert len(result["class_counts"]) == 10


def test_data_gate_rejects_schema_change_without_modifying_original(
    tmp_path: Path,
) -> None:
    frame = pd.read_csv(ROOT / "data/digits.csv")
    broken = tmp_path / "broken_copy.csv"
    frame.drop(columns=["pixel_0_0"]).to_csv(broken, index=False)
    report = tmp_path / "rejected.json"
    completed = run_gate(broken, report)
    assert completed.returncode != 0
    result = json.loads(report.read_text(encoding="utf-8"))
    assert result["passed"] is False
    assert any("schema mismatch" in error for error in result["errors"])


def test_data_gate_rejects_pixel_out_of_range(tmp_path: Path) -> None:
    frame = pd.read_csv(ROOT / "data/digits.csv")
    frame.loc[0, "pixel_0_0"] = 17
    broken = tmp_path / "broken_pixel.csv"
    frame.to_csv(broken, index=False)
    report = tmp_path / "rejected.json"
    completed = run_gate(broken, report)
    assert completed.returncode != 0
    result = json.loads(report.read_text(encoding="utf-8"))
    assert result["passed"] is False
    assert any("Pixel values outside" in error for error in result["errors"])


def test_data_gate_rejects_missing_file(tmp_path: Path) -> None:
    report = tmp_path / "rejected.json"
    completed = run_gate(tmp_path / "absent.csv", report)
    assert completed.returncode != 0
    assert json.loads(report.read_text(encoding="utf-8"))["passed"] is False
