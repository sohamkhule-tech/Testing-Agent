#!/usr/bin/env python3
"""
Setup Script

Initializes project structure and dependencies.
"""

import os
import subprocess
import sys
from pathlib import Path


def main():
    """Initialize project."""
    project_root = Path(__file__).parent.parent

    print("Initializing project structure...")

    # Create directories
    directories = [
        "storage/artifacts",
        "storage/logs",
        "prompts",
        "contracts",
    ]

    for directory in directories:
        dir_path = project_root / directory
        dir_path.mkdir(parents=True, exist_ok=True)
        # Create .gitkeep
        (dir_path / ".gitkeep").touch()

    print("✓ Directories created")

    # Copy .env.example to .env if not exists
    env_example = project_root / ".env.example"
    env_file = project_root / ".env"

    if env_example.exists() and not env_file.exists():
        env_file.write_text(env_example.read_text())
        print("✓ Created .env from .env.example")
    else:
        print("✓ .env already exists")

    # Install dependencies with uv
    print("\nInstalling dependencies...")
    try:
        subprocess.run(
            ["uv", "pip", "install", "-e", ".[dev]"],
            cwd=project_root,
            check=True,
        )
        print("✓ Dependencies installed")
    except FileNotFoundError:
        print("⚠ uv not found. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh")
        print("  Or use: pip install -e .[dev]")
    except subprocess.CalledProcessError:
        print("✗ Failed to install dependencies")
        sys.exit(1)

    print("\n" + "="*60)
    print("Setup complete! Next steps:")
    print("1. Edit .env with your configuration")
    print("2. Run development server: python scripts/dev.py")
    print("3. Run tests: python scripts/test.py")
    print("="*60)


if __name__ == "__main__":
    main()
