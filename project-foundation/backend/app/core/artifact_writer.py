"""
Artifact Writer for Code Generation

Handles filesystem operations for generated code artifacts.
"""

import json
from pathlib import Path
from typing import Any

from app.logging import LoggerMixin
from app.schemas.code_generation import CodeGenerationMetadata, FileType, GeneratedFile


class ArtifactWriter(LoggerMixin):
    """
    Writes generated code artifacts to filesystem.
    
    Responsibilities:
    - Create project folder structure
    - Write generated code files
    - Persist metadata
    - Handle file encoding
    - Create empty directories
    - Maintain file permissions
    """

    def __init__(self) -> None:
        """Initialize artifact writer."""
        super().__init__()

    def create_project_structure(self, project_path: Path) -> None:
        """
        Create complete Playwright project folder structure.

        Args:
            project_path: Root path for project

        Raises:
            OSError: If directory creation fails
        """
        self.logger.info("creating_project_structure", project_path=str(project_path))

        directories = [
            "",  # Root
            "pages",
            "tests",
            "fixtures",
            "utils",
            "data",
            "reports",
            "screenshots",
            "traces",
            "test-results",
        ]

        for directory in directories:
            dir_path = project_path / directory
            try:
                dir_path.mkdir(parents=True, exist_ok=True)
                self.logger.debug("directory_created", path=str(dir_path))
            except OSError as e:
                self.logger.error(
                    "directory_creation_failed",
                    path=str(dir_path),
                    error=str(e)
                )
                raise

        self.logger.info("project_structure_created", project_path=str(project_path))

    def write_file(
        self,
        file_path: Path,
        content: str,
        file_type: FileType = FileType.DOCUMENTATION,
        overwrite: bool = False
    ) -> GeneratedFile:
        """
        Write content to file.

        Args:
            file_path: Path to write file
            content: File content
            file_type: Type of file
            overwrite: Whether to overwrite existing file

        Returns:
            GeneratedFile metadata

        Raises:
            FileExistsError: If file exists and overwrite is False
            OSError: If file write fails
        """
        self.logger.debug("writing_file", file_path=str(file_path), file_type=file_type)

        if file_path.exists() and not overwrite:
            raise FileExistsError(f"File already exists: {file_path}")

        try:
            # Ensure parent directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Write file
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            # Calculate metadata
            size_bytes = file_path.stat().st_size
            lines_of_code = len(content.splitlines())

            generated_file = GeneratedFile(
                file_path=str(file_path),
                file_type=file_type,
                size_bytes=size_bytes,
                lines_of_code=lines_of_code,
            )

            self.logger.debug(
                "file_written",
                file_path=str(file_path),
                size_bytes=size_bytes,
                lines=lines_of_code
            )

            return generated_file

        except Exception as e:
            self.logger.error("file_write_failed", file_path=str(file_path), error=str(e))
            raise

    def write_json_file(
        self,
        file_path: Path,
        data: dict[str, Any],
        overwrite: bool = False
    ) -> GeneratedFile:
        """
        Write JSON data to file.

        Args:
            file_path: Path to write file
            data: Data to serialize as JSON
            overwrite: Whether to overwrite existing file

        Returns:
            GeneratedFile metadata

        Raises:
            FileExistsError: If file exists and overwrite is False
            OSError: If file write fails
        """
        self.logger.debug("writing_json_file", file_path=str(file_path))

        content = json.dumps(data, indent=2, ensure_ascii=False)
        return self.write_file(file_path, content, FileType.DATA, overwrite)

    def write_metadata(
        self,
        project_path: Path,
        metadata: CodeGenerationMetadata
    ) -> Path:
        """
        Write generation metadata to JSON file.

        Args:
            project_path: Project root path
            metadata: Metadata to persist

        Returns:
            Path to metadata file
        """
        self.logger.info("writing_metadata", project_path=str(project_path))

        metadata_path = project_path / "code-generation-metadata.json"

        try:
            metadata_dict = metadata.model_dump(mode="json")
            self.write_json_file(metadata_path, metadata_dict, overwrite=True)

            self.logger.info("metadata_written", path=str(metadata_path))
            return metadata_path

        except Exception as e:
            self.logger.error("metadata_write_failed", error=str(e))
            raise

    def write_config_file(
        self,
        project_path: Path,
        filename: str,
        content: str
    ) -> GeneratedFile:
        """
        Write configuration file.

        Args:
            project_path: Project root path
            filename: Config filename
            content: File content

        Returns:
            GeneratedFile metadata
        """
        file_path = project_path / filename
        return self.write_file(file_path, content, FileType.CONFIG, overwrite=True)

    def write_page_object(
        self,
        project_path: Path,
        class_name: str,
        content: str
    ) -> GeneratedFile:
        """
        Write page object file.

        Args:
            project_path: Project root path
            class_name: Page object class name
            content: TypeScript code

        Returns:
            GeneratedFile metadata
        """
        filename = f"{class_name}.ts"
        file_path = project_path / "pages" / filename
        return self.write_file(file_path, content, FileType.PAGE_OBJECT, overwrite=True)

    def write_test_file(
        self,
        project_path: Path,
        module_name: str,
        content: str
    ) -> GeneratedFile:
        """
        Write test specification file.

        Args:
            project_path: Project root path
            module_name: Module/feature name
            content: TypeScript test code

        Returns:
            GeneratedFile metadata
        """
        filename = f"{module_name}.spec.ts"
        file_path = project_path / "tests" / filename
        return self.write_file(file_path, content, FileType.TEST_SPEC, overwrite=True)

    def write_fixture_file(
        self,
        project_path: Path,
        filename: str,
        content: str
    ) -> GeneratedFile:
        """
        Write fixture file.

        Args:
            project_path: Project root path
            filename: Fixture filename
            content: TypeScript fixture code

        Returns:
            GeneratedFile metadata
        """
        if not filename.endswith(".ts"):
            filename = f"{filename}.ts"
        file_path = project_path / "fixtures" / filename
        return self.write_file(file_path, content, FileType.FIXTURE, overwrite=True)

    def write_utility_file(
        self,
        project_path: Path,
        filename: str,
        content: str
    ) -> GeneratedFile:
        """
        Write utility file.

        Args:
            project_path: Project root path
            filename: Utility filename
            content: TypeScript utility code

        Returns:
            GeneratedFile metadata
        """
        if not filename.endswith(".ts"):
            filename = f"{filename}.ts"
        file_path = project_path / "utils" / filename
        return self.write_file(file_path, content, FileType.UTILITY, overwrite=True)

    def write_data_file(
        self,
        project_path: Path,
        filename: str,
        content: str | dict[str, Any]
    ) -> GeneratedFile:
        """
        Write test data file.

        Args:
            project_path: Project root path
            filename: Data filename
            content: Data content (string or dict for JSON)

        Returns:
            GeneratedFile metadata
        """
        file_path = project_path / "data" / filename

        if isinstance(content, dict):
            return self.write_json_file(file_path, content, overwrite=True)
        else:
            return self.write_file(file_path, content, FileType.DATA, overwrite=True)

    def write_documentation(
        self,
        project_path: Path,
        filename: str,
        content: str
    ) -> GeneratedFile:
        """
        Write documentation file.

        Args:
            project_path: Project root path
            filename: Documentation filename
            content: Documentation content

        Returns:
            GeneratedFile metadata
        """
        file_path = project_path / filename
        return self.write_file(file_path, content, FileType.DOCUMENTATION, overwrite=True)

    def create_gitignore(self, project_path: Path) -> GeneratedFile:
        """
        Create .gitignore file for Playwright project.

        Args:
            project_path: Project root path

        Returns:
            GeneratedFile metadata
        """
        gitignore_content = """# Node
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*
package-lock.json
yarn.lock

# Playwright
test-results/
playwright-report/
reports/
screenshots/
traces/
videos/

# Environment
.env
.env.local
.env.*.local

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# Build
dist/
build/
*.tsbuildinfo
"""
        return self.write_documentation(project_path, ".gitignore", gitignore_content)

    def get_file_stats(self, file_path: Path) -> dict[str, Any]:
        """
        Get file statistics.

        Args:
            file_path: Path to file

        Returns:
            Dictionary with file stats
        """
        if not file_path.exists():
            return {"exists": False}

        stat = file_path.stat()

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                lines = len(content.splitlines())
                chars = len(content)
        except Exception:
            lines = 0
            chars = 0

        return {
            "exists": True,
            "size_bytes": stat.st_size,
            "lines_of_code": lines,
            "characters": chars,
            "is_file": file_path.is_file(),
            "is_dir": file_path.is_dir(),
        }

    def clean_project(self, project_path: Path, keep_structure: bool = True) -> None:
        """
        Clean generated project artifacts.

        Args:
            project_path: Project root path
            keep_structure: If True, keep folder structure but delete files
        """
        self.logger.info("cleaning_project", project_path=str(project_path), keep_structure=keep_structure)

        if not project_path.exists():
            return

        if keep_structure:
            # Delete files but keep folders
            for item in project_path.rglob("*"):
                if item.is_file():
                    try:
                        item.unlink()
                        self.logger.debug("file_deleted", path=str(item))
                    except OSError as e:
                        self.logger.warning("file_deletion_failed", path=str(item), error=str(e))
        else:
            # Delete entire project
            import shutil
            try:
                shutil.rmtree(project_path)
                self.logger.info("project_deleted", path=str(project_path))
            except OSError as e:
                self.logger.error("project_deletion_failed", path=str(project_path), error=str(e))
                raise
