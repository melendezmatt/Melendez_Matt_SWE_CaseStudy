"""Run every quality check: lint, formatting, types, tests.

    python scripts/check.py

Runs them all, so you see every failure at once, and exits non-zero if any fail. The API tests
need Postgres (they're skipped without it); inside Docker: docker compose run --rm app python scripts/check.py
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CHECKS = [
    ("lint", ["ruff", "check", "."]),
    ("format", ["ruff", "format", "--check", "."]),
    ("types", ["mypy"]),
    ("tests", ["pytest", "-q"]),
]


def main() -> int:
    failed = []
    for name, args in CHECKS:
        print(f"\n== {name}: {' '.join(args)}", flush=True)
        if subprocess.run([sys.executable, "-m", *args], cwd=ROOT).returncode != 0:
            failed.append(name)
    print("\n" + (f"FAILED: {', '.join(failed)}" if failed else "All checks passed."))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
