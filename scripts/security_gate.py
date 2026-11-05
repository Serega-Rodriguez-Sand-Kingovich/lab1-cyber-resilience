"""Fail-closed check for authentic Trivy image reports and reviewed findings.

Only a successful, parseable scan counts. CRITICAL and UNKNOWN findings block
unless an exact, independently documented, short-lived exception applies.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


class SecurityGateError(Exception):
    """The security policy cannot be safely evaluated."""


# Source: https://bugs.debian.org/1152790 (fixed in sqlite3 3.54.1-1).
# Keep these identifiers code-bound so editing only JSON cannot broaden policy.
REVIEWED_SQLITE_CVES = frozenset(
    {
        "CVE-2026-119371",
        "CVE-2026-119372",
        "CVE-2026-119374",
        "CVE-2026-119375",
        "CVE-2026-119376",
        "CVE-2026-119379",
    }
)
SQLITE_VERSION = "3.54.1-2"
SQLITE_POLICY_EXPIRY = date(2026, 12, 5)
SQLITE_SOURCE = "https://bugs.debian.org/1152790"


def validate_exception_policy(document: object, on_date: date | None = None) -> dict[str, Any]:
    """Accept only the exact source-reviewed package, CVEs and expiry."""
    if not isinstance(document, dict):
        raise SecurityGateError("Exception policy must be a JSON object")
    allowed_keys = {
        "schema_version", "package", "installed_version", "severity",
        "cve_ids", "expires_on", "source_url", "reason",
    }
    if set(document) != allowed_keys:
        raise SecurityGateError("Exception policy keys are missing or unexpected")
    if (
        document["schema_version"] != 1
        or document["package"] != "libsqlite3-0"
        or document["installed_version"] != SQLITE_VERSION
        or document["severity"] != "UNKNOWN"
        or document["source_url"] != SQLITE_SOURCE
        or document["expires_on"] != SQLITE_POLICY_EXPIRY.isoformat()
        or not isinstance(document["reason"], str)
        or not document["reason"].strip()
    ):
        raise SecurityGateError("Exception policy must match the reviewed Debian advisory")
    ids = document["cve_ids"]
    if not isinstance(ids, list) or len(ids) != len(REVIEWED_SQLITE_CVES):
        raise SecurityGateError("Exception policy CVE list must be exact")
    if any(not isinstance(item, str) for item in ids) or set(ids) != REVIEWED_SQLITE_CVES:
        raise SecurityGateError("Exception policy includes an unreviewed CVE")
    if (on_date or datetime.now(UTC).date()) > SQLITE_POLICY_EXPIRY:
        raise SecurityGateError("Reviewed SQLite exception expired; reassess vulnerabilities")
    return document


def evaluate_trivy_report(
    document: object,
    exception_policy: object = None,
    *,
    on_date: date | None = None,
) -> dict[str, Any]:
    """Inspect the raw report; preserve all blocking and reviewed findings."""
    if not isinstance(document, dict):
        raise SecurityGateError("Trivy report must be a JSON object")
    if document.get("SchemaVersion") != 2:
        raise SecurityGateError("Unexpected or missing Trivy SchemaVersion")
    results = document.get("Results")
    if not isinstance(results, list) or not results:
        raise SecurityGateError("Trivy Results is missing or empty")

    if exception_policy is not None:
        validate_exception_policy(exception_policy, on_date=on_date)

    findings: list[dict[str, str]] = []
    reviewed: list[dict[str, str]] = []
    scanned_targets = 0
    for result in results:
        if not isinstance(result, dict) or not isinstance(result.get("Target"), str):
            raise SecurityGateError("Trivy Result must identify its Target")
        scanned_targets += 1
        vulnerabilities = result.get("Vulnerabilities", [])
        if vulnerabilities is None:
            vulnerabilities = []
        if not isinstance(vulnerabilities, list):
            raise SecurityGateError("Vulnerabilities must be an array")
        for vulnerability in vulnerabilities:
            if not isinstance(vulnerability, dict):
                raise SecurityGateError("Invalid vulnerability entry")
            severity = vulnerability.get("Severity")
            if severity not in {"CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"}:
                raise SecurityGateError("Missing or unrecognized vulnerability severity")
            if severity not in {"CRITICAL", "UNKNOWN"}:
                continue

            finding = {
                "target": result["Target"],
                "id": str(vulnerability.get("VulnerabilityID", "UNKNOWN_ID")),
                "package": str(vulnerability.get("PkgName", "UNKNOWN_PACKAGE")),
                "installed": str(vulnerability.get("InstalledVersion", "")),
                "fixed": str(vulnerability.get("FixedVersion", "")),
                "severity": severity,
            }
            reviewed_sqlite = (
                exception_policy is not None
                and result.get("Class") == "os-pkgs"
                and result.get("Type") == "debian"
                and severity == "UNKNOWN"
                and finding["package"] == "libsqlite3-0"
                and finding["installed"] == SQLITE_VERSION
                and finding["id"] in REVIEWED_SQLITE_CVES
            )
            if reviewed_sqlite:
                reviewed.append(
                    {
                        **finding,
                        "reason": exception_policy["reason"],
                        "source_url": SQLITE_SOURCE,
                        "expires_on": SQLITE_POLICY_EXPIRY.isoformat(),
                    }
                )
            else:
                findings.append(finding)

    outcome: dict[str, Any] = {
        "passed": not findings,
        "targets": scanned_targets,
        "blocking_findings": findings,
    }
    if exception_policy is not None:
        outcome["reviewed_exceptions"] = reviewed
    return outcome


def main() -> int:
    parser = argparse.ArgumentParser(description="Trivy CRITICAL/UNKNOWN gate")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path("reports/ci/security_gate.json"))
    parser.add_argument("--exception-policy", type=Path)
    args = parser.parse_args()
    outcome: dict[str, Any] = {
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "source": str(args.report),
        "policy": "Block CRITICAL and UNKNOWN; fail closed on scanner/report errors",
        "passed": False,
        "exit_code": 1,
        "errors": [],
    }
    try:
        exception_policy = None
        if args.exception_policy is not None:
            exception_policy = json.loads(args.exception_policy.read_text(encoding="utf-8"))
            outcome["exception_policy_source"] = str(args.exception_policy)
        document = json.loads(args.report.read_text(encoding="utf-8"))
        outcome.update(evaluate_trivy_report(document, exception_policy))
    except (OSError, UnicodeError, ValueError, SecurityGateError) as exc:
        outcome["errors"].append(f"{type(exc).__name__}: {exc}")

    outcome["exit_code"] = 0 if outcome["passed"] else 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(outcome, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if outcome["passed"]:
        print(f"SECURITY GATE PASS: {outcome['targets']} Trivy targets checked")
        if outcome.get("reviewed_exceptions"):
            print(f"Reviewed SQLite findings: {len(outcome['reviewed_exceptions'])}")
    else:
        print("SECURITY GATE FAIL", file=sys.stderr)
        for finding in outcome.get("blocking_findings", []):
            print(f"- {finding['severity']} {finding['id']} ({finding['package']})", file=sys.stderr)
        for error in outcome["errors"]:
            print(f"- {error}", file=sys.stderr)
    print(f"Report: {args.output}")
    return outcome["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
