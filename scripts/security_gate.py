"""Fail-closed policy checker for real or explicitly simulated Trivy JSON.

Only a successful Trivy scan with parseable results counts as evidence.
Exit 1 on CRITICAL, UNKNOWN, malformed or missing vulnerability data.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class SecurityGateError(Exception):
    """The security policy could not be evaluated safely."""


def evaluate_trivy_report(document: object) -> dict[str, Any]:
    """Inspect a Trivy image report; do not silently accept invalid output."""
    if not isinstance(document, dict):
        raise SecurityGateError("Trivy report must be a JSON object")
    if document.get("SchemaVersion") != 2:
        raise SecurityGateError("Unexpected or missing Trivy SchemaVersion")
    results = document.get("Results")
    if not isinstance(results, list) or not results:
        raise SecurityGateError("Trivy Results is missing or empty")

    findings: list[dict[str, str]] = []
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
            if severity in {"CRITICAL", "UNKNOWN"}:
                findings.append(
                    {
                        "target": result["Target"],
                        "id": str(vulnerability.get("VulnerabilityID", "UNKNOWN_ID")),
                        "package": str(vulnerability.get("PkgName", "UNKNOWN_PACKAGE")),
                        "installed": str(vulnerability.get("InstalledVersion", "")),
                        "fixed": str(vulnerability.get("FixedVersion", "")),
                        "severity": severity,
                    }
                )
    return {"passed": not findings, "targets": scanned_targets, "blocking_findings": findings}


def main() -> int:
    parser = argparse.ArgumentParser(description="Trivy CRITICAL/UNKNOWN gate")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path("reports/ci/security_gate.json"))
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
        document = json.loads(args.report.read_text(encoding="utf-8"))
        outcome.update(evaluate_trivy_report(document))
    except (OSError, UnicodeError, ValueError, SecurityGateError) as exc:
        outcome["errors"].append(f"{type(exc).__name__}: {exc}")

    outcome["exit_code"] = 0 if outcome["passed"] else 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(outcome, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if outcome["passed"]:
        print(f"SECURITY GATE PASS: {outcome['targets']} Trivy targets checked")
    else:
        print("SECURITY GATE FAIL", file=sys.stderr)
        for finding in outcome.get("blocking_findings", []):
            print(
                f"- {finding['severity']} {finding['id']} ({finding['package']})",
                file=sys.stderr,
            )
        for error in outcome["errors"]:
            print(f"- {error}", file=sys.stderr)
    print(f"Report: {args.output}")
    return outcome["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
