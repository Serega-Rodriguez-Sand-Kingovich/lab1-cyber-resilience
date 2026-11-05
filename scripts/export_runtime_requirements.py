"""Export only the actual pinned inference dependencies from the active venv.

Run once on the student's current Ubuntu; commit the resulting requirements-runtime.txt.
No downloads, model retraining, or changes to requirements.txt are performed.
"""

from __future__ import annotations

import argparse
import re
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PACKAGES = ("joblib", "numpy", "scikit-learn", "scipy", "threadpoolctl")


def make_lock() -> str:
    """Return exact installed versions of the five inference dependencies."""
    lines = ["# Lab 3 runtime-only dependencies; exported from the active Lab 2 venv."]
    for name in RUNTIME_PACKAGES:
        try:
            installed = version(name)
        except PackageNotFoundError as exc:
            raise RuntimeError(f"Required runtime dependency missing: {name}") from exc
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+!-]*", installed):
            raise ValueError(f"Unexpected version of {name}: {installed!r}")
        lines.append(f"{name}=={installed}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pin installed ML inference dependencies"
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "requirements-runtime.txt"
    )
    args = parser.parse_args()
    content = make_lock()
    args.output.write_text(content, encoding="utf-8")
    print(f"Wrote {args.output}: {len(RUNTIME_PACKAGES)} pinned packages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
