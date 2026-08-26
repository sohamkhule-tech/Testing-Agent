"""
Enterprise AI Agentic Testing Platform

Phase 0: Foundation Layer
"""

import asyncio
import sys

# Ensure WindowsProactorEventLoopPolicy is set at the earliest possible import time on Windows
# so that Uvicorn and Playwright background tasks always use ProactorEventLoop (required for subprocesses).
if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass

__version__ = "0.1.0"

from app.main import app

__all__ = ["app"]
