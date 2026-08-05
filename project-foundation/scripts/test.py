#!/usr/bin/env python3
"""
Test Runner Script

Runs pytest with common options.
"""

import subprocess
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent


def main():
    """Run tests."""
    # Default pytest args
    args = [
        "pytest",
        "-v",
        "--tb=short",
        "--strict-markers",
        "-W", "ignore::DeprecationWarning",
    ]

    # Add coverage if requested
    if "--cov" in sys.argv:
        args.extend([
            "--cov=app",
            "--cov-report=html",
            "--cov-report=term",
        ])
        sys.argv.remove("--cov")

    # Add remaining args
    args.extend(sys.argv[1:])

    # Run pytest
    result = subprocess.run(args, cwd=project_root)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
