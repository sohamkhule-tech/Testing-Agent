"""
Startup Validation Checks

Validates that all required dependencies, imports, and configurations are available
before the application accepts requests. This prevents runtime NameErrors and other
late-discovered failures.
"""

import importlib
import sys
from typing import Any

from app.logging import get_logger

logger = get_logger("validation.startup")


class StartupValidationError(Exception):
    """Raised when a critical startup validation check fails."""
    pass


def validate_required_imports() -> None:
    """
    Validate that all critical imports are available.
    
    This catches missing imports at startup rather than at runtime when a specific
    code path is executed (e.g., after human review approval).
    
    Raises:
        StartupValidationError: If any required import is missing
    """
    required_modules = [
        # Standard library
        ("asyncio", "Core async runtime"),
        ("json", "JSON serialization"),
        ("pathlib", "Path utilities"),
        
        # Third-party dependencies
        ("fastapi", "Web framework"),
        ("uvicorn", "ASGI server"),
        ("pydantic", "Data validation"),
        ("langgraph", "Workflow orchestration"),
        ("openai", "LLM client"),
        ("playwright", "Browser automation"),
        ("jinja2", "Template engine"),
        ("tenacity", "Retry utilities"),
        
        # Application modules
        ("app.agents", "Agent implementations"),
        ("app.workflows", "Workflow definitions"),
        ("app.api", "API routes"),
        ("app.core.event_bus", "Event system"),
        ("app.llm", "LLM clients"),
    ]
    
    missing_modules = []
    
    for module_name, description in required_modules:
        try:
            importlib.import_module(module_name)
            logger.debug(f"startup_check_ok", module=module_name, description=description)
        except ImportError as e:
            missing_modules.append((module_name, description, str(e)))
            logger.error(
                "startup_check_failed",
                module=module_name,
                description=description,
                error=str(e)
            )
    
    if missing_modules:
        error_msg = "Missing required imports:\n"
        for module, desc, error in missing_modules:
            error_msg += f"  - {module} ({desc}): {error}\n"
        raise StartupValidationError(error_msg)


def validate_critical_imports_in_workflows() -> None:
    """
    Validate that workflow files have all required imports.
    
    Specifically checks for the asyncio import issue that caused runtime NameError.
    """
    critical_imports = [
        ("app.workflows.trigger_workflow", "asyncio", "Async utilities for timeout handling"),
        ("app.api.routes.trigger", "asyncio", "Async task creation"),
    ]
    
    for module_name, required_import, reason in critical_imports:
        try:
            module = importlib.import_module(module_name)
            if not hasattr(module, required_import.split(".")[-1]):
                # The module loaded, but doesn't have the expected attribute
                # This means the import statement is missing
                logger.error(
                    "critical_import_missing",
                    module=module_name,
                    missing_import=required_import,
                    reason=reason
                )
                raise StartupValidationError(
                    f"{module_name} is missing required import: {required_import} ({reason})"
                )
            logger.debug(
                "critical_import_ok",
                module=module_name,
                import_name=required_import,
                reason=reason
            )
        except ImportError as e:
            raise StartupValidationError(
                f"Failed to load {module_name} for import validation: {str(e)}"
            )


def validate_async_runtime() -> None:
    """
    Validate that the async runtime is available and properly configured.
    
    Raises:
        StartupValidationError: If async runtime is unavailable
    """
    try:
        import asyncio
        
        # Check that we can get an event loop (or create one)
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # No event loop in current thread - this is fine, uvicorn will create one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        if loop.is_closed():
            logger.warning("startup_event_loop_closed")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        logger.info("async_runtime_validated", event_loop_type=type(loop).__name__)
        
    except Exception as e:
        raise StartupValidationError(f"Async runtime validation failed: {str(e)}")


def validate_python_version() -> None:
    """
    Validate Python version meets requirements.
    
    Raises:
        StartupValidationError: If Python version is too old
    """
    required_version = (3, 12, 0)
    current_version = sys.version_info[:3]
    
    if current_version < required_version:
        raise StartupValidationError(
            f"Python {required_version[0]}.{required_version[1]}.{required_version[2]} or higher required, "
            f"but running {current_version[0]}.{current_version[1]}.{current_version[2]}"
        )
    
    logger.info(
        "python_version_validated",
        version=f"{current_version[0]}.{current_version[1]}.{current_version[2]}"
    )


def run_all_startup_checks() -> None:
    """
    Run all startup validation checks.
    
    Call this during application lifespan startup. If any check fails,
    the application will refuse to start.
    
    Raises:
        StartupValidationError: If any validation check fails
    """
    logger.info("running_startup_validation_checks")
    
    checks = [
        ("Python version", validate_python_version),
        ("Required imports", validate_required_imports),
        ("Critical workflow imports", validate_critical_imports_in_workflows),
        ("Async runtime", validate_async_runtime),
    ]
    
    for check_name, check_func in checks:
        try:
            check_func()
            logger.info(f"startup_check_passed", check=check_name)
        except StartupValidationError as e:
            logger.error(f"startup_check_failed", check=check_name, error=str(e))
            raise
    
    logger.info("all_startup_checks_passed")
