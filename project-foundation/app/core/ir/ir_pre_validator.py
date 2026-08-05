"""
IR Pre-validation and Auto-repair

Validates raw JSON before Pydantic validation and attempts auto-repair.
"""

import json
from datetime import datetime
from typing import Any

from app.logging import LoggerMixin


class IRPreValidator(LoggerMixin):
    """
    Pre-validates IR JSON before Pydantic validation.
    
    Checks for:
    - Required top-level keys
    - Required nested keys
    - Type mismatches
    - Missing required arrays
    """

    def __init__(self) -> None:
        """Initialize pre-validator."""
        super().__init__()
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def validate(self, ir_data: dict[str, Any]) -> tuple[bool, list[str], list[str]]:
        """
        Pre-validate IR data.

        Args:
            ir_data: Parsed JSON data

        Returns:
            Tuple of (is_valid, errors, warnings)
        """
        self.errors = []
        self.warnings = []

        self._check_required_top_level_keys(ir_data)
        self._check_metadata(ir_data.get("metadata"))
        self._check_environment(ir_data.get("environment"))
        self._check_pages(ir_data.get("pages"))
        self._check_modules(ir_data.get("modules"))
        self._check_dependencies(ir_data.get("dependencies"))

        is_valid = len(self.errors) == 0

        self.logger.info(
            "pre_validation_complete",
            is_valid=is_valid,
            errors=len(self.errors),
            warnings=len(self.warnings)
        )

        return is_valid, self.errors, self.warnings

    def _check_required_top_level_keys(self, data: dict[str, Any]) -> None:
        """Check for required top-level keys."""
        required_keys = ["metadata", "environment", "pages", "modules", "dependencies"]
        
        for key in required_keys:
            if key not in data:
                self.errors.append(f"Missing required top-level key: {key}")
            elif data[key] is None:
                self.errors.append(f"Top-level key '{key}' is null (must be object/array)")

    def _check_metadata(self, metadata: Any) -> None:
        """Check metadata section."""
        if not isinstance(metadata, dict):
            self.errors.append("metadata must be an object")
            return

        required_fields = {
            "generator": str,
            "ir_version": str,
        }

        for field, expected_type in required_fields.items():
            if field not in metadata:
                self.errors.append(f"metadata.{field} is missing (required)")
            elif metadata[field] is None:
                self.errors.append(f"metadata.{field} is null (must be {expected_type.__name__})")
            elif not isinstance(metadata[field], expected_type):
                self.errors.append(
                    f"metadata.{field} has wrong type (expected {expected_type.__name__}, got {type(metadata[field]).__name__})"
                )

        # Warn if generator is not the expected value
        if metadata.get("generator") and metadata["generator"] != "IRGenerationAgent":
            self.warnings.append(f"metadata.generator should be 'IRGenerationAgent', got '{metadata['generator']}'")

    def _check_environment(self, environment: Any) -> None:
        """Check environment section."""
        if not isinstance(environment, dict):
            self.errors.append("environment must be an object")
            return

        required_fields = {
            "base_url": str,
            "auth_required": bool,
        }

        for field, expected_type in required_fields.items():
            if field not in environment:
                self.errors.append(f"environment.{field} is missing (required)")
            elif environment[field] is None and expected_type != type(None):
                self.errors.append(f"environment.{field} is null (must be {expected_type.__name__})")

    def _check_pages(self, pages: Any) -> None:
        """Check pages array."""
        if not isinstance(pages, list):
            self.errors.append("pages must be an array")
            return

        for idx, page in enumerate(pages):
            if not isinstance(page, dict):
                self.errors.append(f"pages[{idx}] must be an object")
                continue

            required_fields = ["page_id", "name", "description", "elements"]
            for field in required_fields:
                if field not in page:
                    self.errors.append(f"pages[{idx}].{field} is missing")

            # Check elements array
            elements = page.get("elements")
            if not isinstance(elements, list):
                self.errors.append(f"pages[{idx}].elements must be an array")
            else:
                self._check_elements(elements, f"pages[{idx}].elements")

    def _check_elements(self, elements: list[Any], context: str) -> None:
        """Check elements array."""
        for idx, element in enumerate(elements):
            if not isinstance(element, dict):
                self.errors.append(f"{context}[{idx}] must be an object")
                continue

            required_fields = ["id", "name", "locator_strategy", "locator_value"]
            for field in required_fields:
                if field not in element:
                    self.errors.append(f"{context}[{idx}].{field} is missing")

            # Check locator_strategy is valid
            valid_strategies = ["role", "label", "placeholder", "text", "testId", "css", "xpath"]
            strategy = element.get("locator_strategy")
            if strategy and strategy not in valid_strategies:
                self.errors.append(
                    f"{context}[{idx}].locator_strategy '{strategy}' is invalid (must be one of: {', '.join(valid_strategies)})"
                )

    def _check_modules(self, modules: Any) -> None:
        """Check modules array."""
        if not isinstance(modules, list):
            self.errors.append("modules must be an array")
            return

        for idx, module in enumerate(modules):
            if not isinstance(module, dict):
                self.errors.append(f"modules[{idx}] must be an object")
                continue

            required_fields = ["module_id", "name", "description", "flows"]
            for field in required_fields:
                if field not in module:
                    self.errors.append(f"modules[{idx}].{field} is missing")

            # Check flows array
            flows = module.get("flows")
            if not isinstance(flows, list):
                self.errors.append(f"modules[{idx}].flows must be an array")
            else:
                self._check_flows(flows, f"modules[{idx}].flows")

    def _check_flows(self, flows: list[Any], context: str) -> None:
        """Check flows array."""
        for idx, flow in enumerate(flows):
            if not isinstance(flow, dict):
                self.errors.append(f"{context}[{idx}] must be an object")
                continue

            required_fields = ["flow_id", "name", "description", "steps"]
            for field in required_fields:
                if field not in flow:
                    self.errors.append(f"{context}[{idx}].{field} is missing")

            # Check steps array
            steps = flow.get("steps")
            if not isinstance(steps, list):
                self.errors.append(f"{context}[{idx}].steps must be an array")
            elif len(steps) == 0:
                self.warnings.append(f"{context}[{idx}] has no steps (should have at least 1)")

    def _check_dependencies(self, dependencies: Any) -> None:
        """Check dependencies array."""
        if not isinstance(dependencies, list):
            self.errors.append("dependencies must be an array")
            return

        for idx, dep in enumerate(dependencies):
            if not isinstance(dep, dict):
                self.errors.append(f"dependencies[{idx}] must be an object")
                continue

            required_fields = ["source_id", "target_id", "dependency_type"]
            for field in required_fields:
                if field not in dep:
                    self.errors.append(f"dependencies[{idx}].{field} is missing (required)")
                elif dep[field] is None:
                    self.errors.append(f"dependencies[{idx}].{field} is null (must be string)")
                elif not isinstance(dep[field], str):
                    self.errors.append(f"dependencies[{idx}].{field} must be a string")


class IRAutoRepairer(LoggerMixin):
    """
    Attempts to auto-repair common IR issues.
    
    Repairs:
    - Missing metadata fields
    - Missing environment fields
    - Empty arrays (ensures they exist)
    - Type conversions
    """

    def __init__(self) -> None:
        """Initialize auto-repairer."""
        super().__init__()
        self.repairs_made: list[str] = []

    def repair(self, ir_data: dict[str, Any]) -> dict[str, Any]:
        """
        Attempt to repair IR data.

        Args:
            ir_data: Parsed JSON data

        Returns:
            Repaired data
        """
        self.repairs_made = []

        self._repair_metadata(ir_data)
        self._repair_environment(ir_data)
        self._ensure_arrays(ir_data)
        self._repair_dependencies(ir_data)

        self.logger.info(
            "auto_repair_complete",
            repairs=len(self.repairs_made)
        )

        return ir_data

    def _repair_metadata(self, data: dict[str, Any]) -> None:
        """Repair metadata section."""
        if "metadata" not in data or not isinstance(data["metadata"], dict):
            data["metadata"] = {}
            self.repairs_made.append("Created missing metadata object")

        metadata = data["metadata"]

        # Add required fields with defaults
        if "generator" not in metadata or not metadata["generator"]:
            metadata["generator"] = "IRGenerationAgent"
            self.repairs_made.append("Set metadata.generator to 'IRGenerationAgent'")

        if "generated_at" not in metadata or not metadata["generated_at"]:
            metadata["generated_at"] = datetime.utcnow().isoformat() + "Z"
            self.repairs_made.append("Set metadata.generated_at to current time")

        if "ir_version" not in metadata or not metadata["ir_version"]:
            metadata["ir_version"] = "1.0.0"
            self.repairs_made.append("Set metadata.ir_version to '1.0.0'")

        if "validation_status" not in metadata:
            metadata["validation_status"] = "pending"
            self.repairs_made.append("Set metadata.validation_status to 'pending'")

        # Set counts to 0 if missing
        count_fields = ["total_pages", "total_elements", "total_flows", "total_modules"]
        for field in count_fields:
            if field not in metadata or metadata[field] is None:
                metadata[field] = 0
                self.repairs_made.append(f"Set metadata.{field} to 0")

    def _repair_environment(self, data: dict[str, Any]) -> None:
        """Repair environment section."""
        if "environment" not in data or not isinstance(data["environment"], dict):
            data["environment"] = {}
            self.repairs_made.append("Created missing environment object")

        env = data["environment"]

        if "base_url" not in env or not env["base_url"]:
            env["base_url"] = "http://localhost:3000"
            self.repairs_made.append("Set environment.base_url to default")

        if "auth_required" not in env:
            env["auth_required"] = False
            self.repairs_made.append("Set environment.auth_required to false")

        if "browsers" not in env or not isinstance(env["browsers"], list):
            env["browsers"] = ["chromium"]
            self.repairs_made.append("Set environment.browsers to ['chromium']")

        if "variables" not in env:
            env["variables"] = {}
            self.repairs_made.append("Set environment.variables to {}")

        if "timeouts" not in env:
            env["timeouts"] = {}
            self.repairs_made.append("Set environment.timeouts to {}")

    def _ensure_arrays(self, data: dict[str, Any]) -> None:
        """Ensure all required arrays exist."""
        array_fields = [
            "pages",
            "modules",
            "dependencies",
            "common_elements",
            "common_flows",
        ]

        for field in array_fields:
            if field not in data or not isinstance(data[field], list):
                data[field] = []
                self.repairs_made.append(f"Created missing {field} array")

        # Ensure nested arrays in pages
        for page in data.get("pages", []):
            if isinstance(page, dict):
                if "elements" not in page or not isinstance(page["elements"], list):
                    page["elements"] = []
                    self.repairs_made.append(f"Created missing elements array in page {page.get('page_id', 'unknown')}")

        # Ensure nested arrays in modules
        for module in data.get("modules", []):
            if isinstance(module, dict):
                if "flows" not in module or not isinstance(module["flows"], list):
                    module["flows"] = []
                    self.repairs_made.append(f"Created missing flows array in module {module.get('module_id', 'unknown')}")
                
                for flow in module.get("flows", []):
                    if isinstance(flow, dict):
                        if "steps" not in flow or not isinstance(flow["steps"], list):
                            flow["steps"] = []
                            self.repairs_made.append(f"Created missing steps array in flow {flow.get('flow_id', 'unknown')}")

    def _repair_dependencies(self, data: dict[str, Any]) -> None:
        """Repair dependencies array."""
        deps = data.get("dependencies", [])
        
        # Remove invalid dependencies
        valid_deps = []
        for dep in deps:
            if not isinstance(dep, dict):
                self.repairs_made.append("Removed non-object dependency")
                continue
            
            # Ensure required fields exist
            if not dep.get("source_id") or not dep.get("target_id") or not dep.get("dependency_type"):
                self.repairs_made.append(f"Removed incomplete dependency: {dep}")
                continue
            
            valid_deps.append(dep)
        
        data["dependencies"] = valid_deps
