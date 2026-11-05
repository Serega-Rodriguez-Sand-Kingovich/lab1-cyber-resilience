"""Tests for the fail-closed Trivy report policy (no real vulnerabilities)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.security_gate import SecurityGateError, evaluate_trivy_report

ROOT = Path(__file__).resolve().parents[1]


def sample(vulnerabilities=None):
    return {
        "SchemaVersion": 2,
        "Results": [{"Target": "simulated-test", "Vulnerabilities": vulnerabilities}],
    }


def issue(severity):
    return {"VulnerabilityID": "SIMULATED-1", "PkgName": "demo", "Severity": severity}


def test_clean_image_passes():
    assert evaluate_trivy_report(sample(None))["passed"] is True


@pytest.mark.parametrize("severity", ["LOW", "MEDIUM", "HIGH"])
def test_noncritical_findings_pass(severity):
    assert evaluate_trivy_report(sample([issue(severity)]))["passed"] is True


@pytest.mark.parametrize("severity", ["CRITICAL", "UNKNOWN"])
def test_critical_and_unknown_block(severity):
    outcome = evaluate_trivy_report(sample([issue(severity)]))
    assert outcome["passed"] is False
    assert outcome["blocking_findings"][0]["severity"] == severity


@pytest.mark.parametrize(
    "invalid",
    [{}, [], {"SchemaVersion": 2}, {"SchemaVersion": 2, "Results": []}],
)
def test_missing_scan_metadata_fails_closed(invalid):
    with pytest.raises(SecurityGateError):
        evaluate_trivy_report(invalid)


def test_missing_severity_fails_closed():
    with pytest.raises(SecurityGateError):
        evaluate_trivy_report(sample([{"VulnerabilityID": "SIMULATED-1"}]))


def test_cli_returns_failure_and_writes_report(tmp_path):
    source = ROOT / "tests/fixtures/security_gate_critical_example.json"
    out = tmp_path / "security_gate.json"
    done = subprocess.run(
        [sys.executable, "scripts/security_gate.py", "--report", str(source), "--output", str(out)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert done.returncode == 1
    assert json.loads(out.read_text())["exit_code"] == 1


def test_cli_clean_fixture_passes(tmp_path):
    source = tmp_path / "clean_fixture.json"
    source.write_text(json.dumps(sample(None)), encoding="utf-8")
    out = tmp_path / "security_gate.json"
    done = subprocess.run(
        [sys.executable, "scripts/security_gate.py", "--report", str(source), "--output", str(out)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert done.returncode == 0
    assert json.loads(out.read_text())["passed"] is True
