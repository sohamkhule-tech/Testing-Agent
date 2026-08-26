"""
Code Validator for Generated Projects

Validates structure and quality of generated Playwright code.
"""

import json
import re
from pathlib import Path
from typing import Any

from app.logging import LoggerMixin
from app.schemas.code_generation import ValidationIssue


class CodeValidator(LoggerMixin):
    """
    Validates generated Playwright project structure and code quality.
    
    Responsibilities:
    - Validate folder structure
    - Check for required files
    - Validate JSON/TypeScript syntax
    - Check for duplicate files
    - Validate imports
    - Check for missing assertions
    - Report validation issues
    """

    def __init__(self) -> None:
        """Initialize code validator."""
        super().__init__()
        self.issues: list[ValidationIssue] = []

    def validate_project(self, project_path: Path) -> tuple[bool, list[ValidationIssue]]:
        """
        Validate complete generated project.

        Args:
            project_path: Path to generated project root

        Returns:
            Tuple of (is_valid, issues_list)
        """
        self.logger.info("validating_project", project_path=str(project_path))
        self.issues = []

        # Run validation checks
        self._validate_folder_structure(project_path)
        self._validate_required_files(project_path)
        self._validate_config_files(project_path)
        self._validate_typescript_files(project_path)
        self._validate_imports(project_path)
        self._check_for_duplicates(project_path)

        # Determine if valid (no critical errors)
        has_errors = any(issue.severity == "error" for issue in self.issues)
        is_valid = not has_errors

        self.logger.info(
            "project_validation_complete",
            is_valid=is_valid,
            error_count=len([i for i in self.issues if i.severity == "error"]),
            warning_count=len([i for i in self.issues if i.severity == "warning"]),
        )

        return is_valid, self.issues

    def _validate_folder_structure(self, project_path: Path) -> None:
        """Validate expected folder structure exists."""
        required_folders = [
            "pages",
            "tests",
            "fixtures",
            "utils",
            "data",
            "reports",
            "screenshots",
        ]

        for folder in required_folders:
            folder_path = project_path / folder
            if not folder_path.exists():
                self.issues.append(
                    ValidationIssue(
                        severity="error",
                        file_path=str(folder_path),
                        message=f"Required folder missing: {folder}",
                        rule="folder_structure",
                    )
                )
            elif not folder_path.is_dir():
                self.issues.append(
                    ValidationIssue(
                        severity="error",
                        file_path=str(folder_path),
                        message=f"Path exists but is not a directory: {folder}",
                        rule="folder_structure",
                    )
                )

    def _validate_required_files(self, project_path: Path) -> None:
        """Validate required files exist."""
        required_files = [
            "package.json",
            "playwright.config.ts",
            "tsconfig.json",
            ".env.example",
            "README.md",
            "pages/BasePage.ts",
            "fixtures/base.fixture.ts",
        ]

        for file_path_str in required_files:
            file_path = project_path / file_path_str
            if not file_path.exists():
                self.issues.append(
                    ValidationIssue(
                        severity="error",
                        file_path=str(file_path),
                        message=f"Required file missing: {file_path_str}",
                        rule="required_files",
                    )
                )
            elif not file_path.is_file():
                self.issues.append(
                    ValidationIssue(
                        severity="error",
                        file_path=str(file_path),
                        message=f"Path exists but is not a file: {file_path_str}",
                        rule="required_files",
                    )
                )

    def _validate_config_files(self, project_path: Path) -> None:
        """Validate configuration files."""
        # Validate package.json
        package_json = project_path / "package.json"
        if package_json.exists():
            try:
                with open(package_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    
                # Check required fields
                if "name" not in data:
                    self.issues.append(
                        ValidationIssue(
                            severity="warning",
                            file_path=str(package_json),
                            message="package.json missing 'name' field",
                            rule="package_json_validation",
                        )
                    )
                
                if "scripts" not in data:
                    self.issues.append(
                        ValidationIssue(
                            severity="error",
                            file_path=str(package_json),
                            message="package.json missing 'scripts' field",
                            rule="package_json_validation",
                        )
                    )
                elif "test" not in data.get("scripts", {}):
                    self.issues.append(
                        ValidationIssue(
                            severity="warning",
                            file_path=str(package_json),
                            message="package.json missing 'test' script",
                            rule="package_json_validation",
                        )
                    )
                
                if "devDependencies" not in data:
                    self.issues.append(
                        ValidationIssue(
                            severity="error",
                            file_path=str(package_json),
                            message="package.json missing 'devDependencies'",
                            rule="package_json_validation",
                        )
                    )
                elif "@playwright/test" not in data.get("devDependencies", {}):
                    self.issues.append(
                        ValidationIssue(
                            severity="error",
                            file_path=str(package_json),
                            message="package.json missing @playwright/test dependency",
                            rule="package_json_validation",
                        )
                    )
                    
            except json.JSONDecodeError as e:
                self.issues.append(
                    ValidationIssue(
                        severity="error",
                        file_path=str(package_json),
                        message=f"Invalid JSON: {str(e)}",
                        rule="json_syntax",
                    )
                )

        # Validate tsconfig.json
        tsconfig_json = project_path / "tsconfig.json"
        if tsconfig_json.exists():
            try:
                with open(tsconfig_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    
                if "compilerOptions" not in data:
                    self.issues.append(
                        ValidationIssue(
                            severity="error",
                            file_path=str(tsconfig_json),
                            message="tsconfig.json missing 'compilerOptions'",
                            rule="tsconfig_validation",
                        )
                    )
                    
            except json.JSONDecodeError as e:
                self.issues.append(
                    ValidationIssue(
                        severity="error",
                        file_path=str(tsconfig_json),
                        message=f"Invalid JSON: {str(e)}",
                        rule="json_syntax",
                    )
                )

    def _validate_typescript_files(self, project_path: Path) -> None:
        """Validate TypeScript files for basic syntax issues."""
        ts_files = list(project_path.rglob("*.ts"))
        
        if not ts_files:
            self.issues.append(
                ValidationIssue(
                    severity="error",
                    file_path=str(project_path),
                    message="No TypeScript files found in project",
                    rule="typescript_files",
                )
            )
            return

        for ts_file in ts_files:
            if "node_modules" in str(ts_file):
                continue
                
            try:
                with open(ts_file, "r", encoding="utf-8") as f:
                    content = f.read()
                    
                # Check for basic syntax issues
                self._check_typescript_syntax(ts_file, content)
                
                # Check for test files
                if "spec.ts" in ts_file.name:
                    self._validate_test_file(ts_file, content)
                
                # Check for page objects
                if ts_file.parent.name == "pages" and ts_file.name != "BasePage.ts":
                    self._validate_page_object(ts_file, content)
                    
            except Exception as e:
                self.issues.append(
                    ValidationIssue(
                        severity="error",
                        file_path=str(ts_file),
                        message=f"Error reading file: {str(e)}",
                        rule="file_access",
                    )
                )

    def _check_typescript_syntax(self, file_path: Path, content: str) -> None:
        """Check for basic TypeScript syntax issues."""
        # Check for unmatched braces
        open_braces = content.count("{")
        close_braces = content.count("}")
        if open_braces != close_braces:
            self.issues.append(
                ValidationIssue(
                    severity="error",
                    file_path=str(file_path),
                    message=f"Unmatched braces: {open_braces} open, {close_braces} close",
                    rule="typescript_syntax",
                )
            )

        # Check for unmatched parentheses
        open_parens = content.count("(")
        close_parens = content.count(")")
        if open_parens != close_parens:
            self.issues.append(
                ValidationIssue(
                    severity="error",
                    file_path=str(file_path),
                    message=f"Unmatched parentheses: {open_parens} open, {close_parens} close",
                    rule="typescript_syntax",
                )
            )

        # Check for common issues
        if "any" in content and "// @ts-ignore" not in content:
            # Count occurrences for warning
            any_count = len(re.findall(r'\bany\b', content))
            if any_count > 2:  # Allow a few any types
                self.issues.append(
                    ValidationIssue(
                        severity="warning",
                        file_path=str(file_path),
                        message=f"Excessive use of 'any' type ({any_count} occurrences)",
                        rule="typescript_quality",
                    )
                )

    def _validate_test_file(self, file_path: Path, content: str) -> None:
        """Validate test specification file."""
        # Check for test imports
        if "@playwright/test" not in content:
            self.issues.append(
                ValidationIssue(
                    severity="error",
                    file_path=str(file_path),
                    message="Test file missing @playwright/test import",
                    rule="test_file_structure",
                )
            )

        # Check for test definitions
        if "test(" not in content and "test.only(" not in content:
            self.issues.append(
                ValidationIssue(
                    severity="warning",
                    file_path=str(file_path),
                    message="Test file contains no test cases",
                    rule="test_file_structure",
                )
            )

        # Check for expect assertions
        if "expect(" not in content:
            self.issues.append(
                ValidationIssue(
                    severity="warning",
                    file_path=str(file_path),
                    message="Test file contains no assertions",
                    rule="test_file_assertions",
                )
            )

        # Warn about test.only
        if "test.only(" in content:
            self.issues.append(
                ValidationIssue(
                    severity="warning",
                    file_path=str(file_path),
                    message="Test file contains test.only() - remove before committing",
                    rule="test_file_quality",
                )
            )

    def _validate_page_object(self, file_path: Path, content: str) -> None:
        """Validate page object file."""
        # Check for Playwright imports
        if "Page" not in content or "Locator" not in content:
            self.issues.append(
                ValidationIssue(
                    severity="error",
                    file_path=str(file_path),
                    message="Page object missing Playwright imports",
                    rule="page_object_structure",
                )
            )

        # Check for class definition
        if "export class" not in content:
            self.issues.append(
                ValidationIssue(
                    severity="error",
                    file_path=str(file_path),
                    message="Page object missing exported class",
                    rule="page_object_structure",
                )
            )

        # Check for constructor
        if "constructor(page: Page)" not in content:
            self.issues.append(
                ValidationIssue(
                    severity="warning",
                    file_path=str(file_path),
                    message="Page object constructor doesn't accept Page parameter",
                    rule="page_object_structure",
                )
            )

    def _validate_imports(self, project_path: Path) -> None:
        """Validate imports in TypeScript files."""
        ts_files = list(project_path.rglob("*.ts"))

        for ts_file in ts_files:
            if "node_modules" in str(ts_file):
                continue

            try:
                with open(ts_file, "r", encoding="utf-8") as f:
                    content = f.read()

                # Find all import statements
                import_pattern = r"import\s+.*?\s+from\s+['\"](.+?)['\"]"
                imports = re.findall(import_pattern, content)

                for imported_path in imports:
                    # Skip node_modules imports
                    if not imported_path.startswith("."):
                        continue

                    # Resolve relative import
                    resolved_path = self._resolve_import_path(ts_file, imported_path)
                    if resolved_path and not resolved_path.exists():
                        self.issues.append(
                            ValidationIssue(
                                severity="error",
                                file_path=str(ts_file),
                                message=f"Import not found: {imported_path}",
                                rule="import_validation",
                            )
                        )

            except Exception as e:
                self.logger.warning("import_validation_error", file=str(ts_file), error=str(e))

    def _resolve_import_path(self, source_file: Path, import_path: str) -> Path | None:
        """Resolve relative import path to absolute path."""
        try:
            # Handle relative imports
            if import_path.startswith("."):
                base_dir = source_file.parent
                resolved = (base_dir / import_path).resolve()

                # Try with .ts extension
                if not resolved.suffix:
                    resolved = resolved.with_suffix(".ts")

                return resolved
        except Exception:
            pass

        return None

    def _check_for_duplicates(self, project_path: Path) -> None:
        """Check for duplicate file names or class names."""
        # Check for duplicate file names (case-insensitive)
        file_names: dict[str, list[str]] = {}

        for ts_file in project_path.rglob("*.ts"):
            if "node_modules" in str(ts_file):
                continue

            name_lower = ts_file.name.lower()
            if name_lower not in file_names:
                file_names[name_lower] = []
            file_names[name_lower].append(str(ts_file))

        for name, paths in file_names.items():
            if len(paths) > 1:
                self.issues.append(
                    ValidationIssue(
                        severity="warning",
                        file_path=", ".join(paths),
                        message=f"Duplicate file names found: {name}",
                        rule="duplicate_files",
                    )
                )

    def get_validation_summary(self) -> dict[str, Any]:
        """
        Get validation summary.

        Returns:
            Dictionary with validation summary
        """
        error_count = len([i for i in self.issues if i.severity == "error"])
        warning_count = len([i for i in self.issues if i.severity == "warning"])
        info_count = len([i for i in self.issues if i.severity == "info"])

        return {
            "total_issues": len(self.issues),
            "errors": error_count,
            "warnings": warning_count,
            "info": info_count,
            "is_valid": error_count == 0,
            "issues": [issue.model_dump() for issue in self.issues],
        }
