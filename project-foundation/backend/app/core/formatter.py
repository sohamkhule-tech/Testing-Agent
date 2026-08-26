"""
Code Formatter

Formats generated TypeScript code for consistency.
"""

import re
from pathlib import Path

from app.logging import LoggerMixin


class CodeFormatter(LoggerMixin):
    """
    Formats TypeScript code.
    
    Provides basic formatting without external dependencies.
    """

    def __init__(self) -> None:
        """Initialize formatter."""
        super().__init__()

    def format_file(self, file_path: Path) -> None:
        """
        Format a single file.

        Args:
            file_path: Path to file to format
        """
        if not file_path.exists():
            self.logger.warning("file_not_found", path=str(file_path))
            return

        # Only format TypeScript files
        if file_path.suffix not in [".ts", ".js"]:
            return

        self.logger.debug("formatting_file", path=str(file_path))

        content = file_path.read_text(encoding="utf-8")
        formatted = self.format_code(content)
        
        if formatted != content:
            file_path.write_text(formatted, encoding="utf-8")
            self.logger.debug("file_formatted", path=str(file_path))

    def format_code(self, code: str) -> str:
        """
        Format TypeScript/JavaScript code.

        Args:
            code: Code to format

        Returns:
            Formatted code
        """
        # Normalize line endings
        code = code.replace("\r\n", "\n")

        # Remove trailing whitespace
        lines = [line.rstrip() for line in code.split("\n")]

        # Fix spacing around operators
        formatted_lines = []
        for line in lines:
            # Add space after commas (but not inside strings – best-effort)
            line = re.sub(r",(\S)", r", \1", line)

            # Fix assignment operator spacing — EXCLUDE => arrow functions
            # Negative lookahead for > (arrow) and lookbehind excludes =, !, <, >
            line = re.sub(r"([^=!<>])=([^=>])", r"\1 = \2", line)

            # Add space around comparison operators
            line = re.sub(r"([^=!<>])==([^=])", r"\1 == \2", line)
            line = re.sub(r"([^=!])!=([^=])", r"\1 != \2", line)

            formatted_lines.append(line)

        # Ensure imports are at the top
        formatted_lines = self._organize_imports(formatted_lines)

        # Remove multiple consecutive blank lines
        result_lines = []
        prev_blank = False
        for line in formatted_lines:
            is_blank = line.strip() == ""
            if is_blank and prev_blank:
                continue
            result_lines.append(line)
            prev_blank = is_blank

        # Ensure file ends with single newline
        code = "\n".join(result_lines)
        if not code.endswith("\n"):
            code += "\n"

        # Apply TypeScript-specific sanitization pass
        code = self._sanitize_typescript(code)

        return code

    def _sanitize_typescript(self, code: str) -> str:
        """
        Apply TypeScript-specific syntax sanitization.

        Fixes common LLM-generated code issues:
        - process.env.{placeholder} -> process.env.PLACEHOLDER
        - Broken arrow functions:  = >  ->  =>
        - ${placeholder} in regular strings -> process.env.PLACEHOLDER
        - Unmatched/broken string quotes from special chars in fill() calls

        Args:
            code: TypeScript source code

        Returns:
            Sanitized code
        """
        # 1. Fix broken arrow functions caused by formatter: "= >" -> "=>"
        #    Covers:  ")  = >",  "=>",  "async (x)  = >"  etc.
        code = re.sub(r"\)\s*=\s*>", ") =>", code)
        code = re.sub(r"\}\s*=\s*>", "} =>", code)

        # 2. Fix process.env.{placeholder_name}  ->  process.env.PLACEHOLDER_NAME
        def _fix_env_placeholder(m: re.Match) -> str:
            raw = m.group(1)          # e.g. "{valid_id}"
            name = raw.strip("{}")    # e.g. "valid_id"
            upper = name.upper()      # e.g. "VALID_ID"
            return f"process.env.{upper}"

        code = re.sub(r"process\.env\.\{([^}]+)\}", _fix_env_placeholder, code)

        # 3. Fix ${placeholder} inside single/double quoted strings  ->  process.env.PLACEHOLDER
        #    e.g.  fill('${valid_id}')  ->  fill(process.env.VALID_ID || '')
        def _fix_template_in_string(m: re.Match) -> str:
            name = m.group(1).strip()
            upper = name.upper()
            return f"process.env.{upper} || ''"

        code = re.sub(r"['\"]?\$\{([^}]+)\}['\"]?", _fix_template_in_string, code)

        # 4. Fix broken SQL injection test string literals
        #    e.g.  fill('' OR 1 = 1 --')  ->  fill("' OR 1=1 --")
        code = re.sub(
            r"fill\(''([^)]+)\)",
            lambda m: "fill(\"'\" + '{}')".format(m.group(1).strip("'")),
            code
        )

        # 5. Fix spaces inserted inside arrow function params by formatter
        #    e.g.  async ({ page })  = >  ->  async ({ page }) =>
        code = re.sub(r"(async\s*\([^)]*\))\s*=\s*>", r"\1 =>", code)

        return code

    def _organize_imports(self, lines: list[str]) -> list[str]:
        """
        Organize import statements.

        Args:
            lines: Code lines

        Returns:
            Lines with organized imports
        """
        import_lines = []
        other_lines = []
        in_imports = True

        for line in lines:
            stripped = line.strip()
            
            # Check if this is an import line
            if stripped.startswith("import "):
                import_lines.append(line)
            elif stripped == "" and in_imports:
                # Keep blank lines in import section
                import_lines.append(line)
            else:
                if in_imports and stripped != "":
                    in_imports = False
                other_lines.append(line)

        # Sort imports
        import_groups = self._group_imports(import_lines)
        
        # Combine with blank line between groups
        organized_imports = []
        for group in import_groups:
            if group:
                organized_imports.extend(group)
                organized_imports.append("")  # Blank line after group

        # Remove trailing blank lines from imports
        while organized_imports and organized_imports[-1] == "":
            organized_imports.pop()

        # Combine imports and other code
        if organized_imports and other_lines:
            organized_imports.append("")  # Blank line between imports and code

        return organized_imports + other_lines

    def _group_imports(self, import_lines: list[str]) -> list[list[str]]:
        """
        Group imports by type.

        Args:
            import_lines: Import lines

        Returns:
            Grouped imports: [playwright imports, local imports]
        """
        playwright_imports = []
        local_imports = []

        for line in import_lines:
            stripped = line.strip()
            if not stripped or not stripped.startswith("import "):
                continue

            # Categorize import
            if "@playwright/test" in stripped:
                playwright_imports.append(line)
            elif stripped.startswith("import {") or stripped.startswith("import "):
                # Check if it's a local import (starts with . or ../)
                if "from './" in stripped or "from '../" in stripped:
                    local_imports.append(line)
                else:
                    playwright_imports.append(line)

        # Sort each group
        playwright_imports.sort()
        local_imports.sort()

        return [playwright_imports, local_imports]

    def format_directory(self, directory: Path) -> int:
        """
        Format all TypeScript files in a directory.

        Args:
            directory: Directory to format

        Returns:
            Number of files formatted
        """
        self.logger.info("formatting_directory", path=str(directory))

        count = 0
        for file_path in directory.rglob("*.ts"):
            # Skip node_modules and test-results
            if "node_modules" in file_path.parts or "test-results" in file_path.parts:
                continue

            self.format_file(file_path)
            count += 1

        self.logger.info("directory_formatted", path=str(directory), file_count=count)
        return count
