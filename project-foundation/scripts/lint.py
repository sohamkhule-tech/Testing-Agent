#!/usr/bin/env python3
"""
Code Quality Check Script

Runs linting, formatting, and type checking.
"""

import subprocess
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent


def run_command(cmd: list[str], description: str) -> bool:
    """Run command and report results."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"{'='*60}")

    result = subprocess.run(cmd, cwd=project_root)
    return result.returncode == 0


def main():
    """Run code quality checks."""
    all_passed = True

    # Black formatting check
    if not run_command(
        ["black", "--check", "app", "tests"],
        "Black formatting check"
    ):
        all_passed = False

    # Ruff linting
    if not run_command(
        ["ruff", "check", "app", "tests"],
        "Ruff linting"
    ):
        all_passed = False

    # MyPy type checking
    if not run_command(
        ["mypy", "app"],
        "MyPy type checking"
    ):
        all_passed = False

    # Summary
    print(f"\n{'='*60}")
    if all_passed:
        print("✓ All quality checks passed!")
    else:
        print("✗ Some quality checks failed")
    print(f"{'='*60}\n")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
