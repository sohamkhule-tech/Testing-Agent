#!/usr/bin/env python3
"""
Development Server Script

Runs FastAPI development server with auto-reload.
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def main():
    """Run development server."""
    import uvicorn

    # Load environment
    env_file = project_root / ".env"
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(env_file)

    # Run server
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=[str(project_root / "app")],
        reload_excludes=[".venv", "__pycache__", "*.pyc"],
        log_level="info",
    )


if __name__ == "__main__":
    main()
