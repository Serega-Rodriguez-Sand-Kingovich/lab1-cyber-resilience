"""Behavioral tests for tightly reviewed security exceptions."""

from __future__ import annotations

import copy
import json
from datetime import date
from pathlib import Path

import pytest

from scripts.security_gate import SecurityGateError, evaluate_trivy_report

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config" / "sqlite_exception_policy.json"
IDS = (
    "CVE-2026-119371", "CVE-2026-119372", "CVE-2026-119374",
    "CVE-2026-119375", "CVE-2026-119376", "CVE-2026-119379",
)


def policy():
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def report(ids=IDS, severity="UNKNOWN", version="3.54.1-2"):
    return {
        "SchemaVersion": 2,
        "Results": [{
            "Target": "ml-project:lab3 (debian 13.7)",
            "Class": "os-pkgs",
            "Type": "debian",
            "Vulnerabilities": [
                {
                    "VulnerabilityID": id_,
                    "PkgName": "libsqlite3-0",
                    "InstalledVersion": version,
                    "Severity": severity,
                }
                for id_ in ids
            ],
        }],
    }


def test_six_exact_unknowns_reviewed_and_reported():
    outcome = evaluate_trivy_report(report(), policy(), on_date=date(2026, 11, 5))
    assert outcome["passed"] is True
    assert outcome["blocking_findings"] == []
    assert len(outcome["reviewed_exceptions"]) == 6
    assert {x["id"] for x in outcome["reviewed_exceptions"]} == set(IDS)


def test_without_explicit_policy_still_blocks_all_unknowns():
    outcome = evaluate_trivy_report(report())
    assert outcome["passed"] is False
    assert len(outcome["blocking_findings"]) == 6


def test_unreviewed_cve_is_still_blocking():
    outcome = evaluate_trivy_report(
        report(ids=(*IDS, "CVE-2099-000001")), policy(), on_date=date(2026, 11, 5)
    )
    assert outcome["passed"] is False
    assert len(outcome["blocking_findings"]) == 1
    assert outcome["blocking_findings"][0]["id"] == "CVE-2099-000001"


def test_critical_for_reviewed_id_is_still_blocking():
    outcome = evaluate_trivy_report(
        report(ids=(IDS[0],), severity="CRITICAL"),
        policy(),
        on_date=date(2026, 11, 5),
    )
    assert outcome["passed"] is False


def test_other_package_version_is_still_blocking():
    outcome = evaluate_trivy_report(
        report(ids=(IDS[0],), version="3.46.1-7+deb13u2"),
        policy(),
        on_date=date(2026, 11, 5),
    )
    assert outcome["passed"] is False


def test_other_os_package_is_still_blocking():
    document = report(ids=(IDS[0],))
    document["Results"][0]["Type"] = "alpine"
    outcome = evaluate_trivy_report(document, policy(), on_date=date(2026, 11, 5))
    assert outcome["passed"] is False


def test_expired_policy_fails_closed():
    with pytest.raises(SecurityGateError, match="expired"):
        evaluate_trivy_report(report(), policy(), on_date=date(2026, 12, 6))


def test_policy_cannot_add_unreviewed_ids():
    changed = copy.deepcopy(policy())
    changed["cve_ids"].append("CVE-2099-000001")
    with pytest.raises(SecurityGateError):
        evaluate_trivy_report(report(), changed, on_date=date(2026, 11, 5))


def test_missing_or_invalid_scan_fails_closed():
    with pytest.raises(SecurityGateError):
        evaluate_trivy_report({"SchemaVersion": 2, "Results": []}, policy())
