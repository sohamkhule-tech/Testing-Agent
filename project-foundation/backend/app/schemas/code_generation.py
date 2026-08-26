"""
Code Generation Schemas

Data structures for AI-generated Playwright test automation code.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CodeGenerationStatus(str, Enum):
    """Status of code generation process."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    VALIDATION_FAILED = "validation_failed"


class FileType(str, Enum):
    """Types of generated files."""
    PAGE_OBJECT = "page_object"
    TEST_SPEC = "test_spec"
    FIXTURE = "fixture"
    UTILITY = "utility"
    CONFIG = "config"
    DATA = "data"
    DOCUMENTATION = "documentation"


class ValidationIssue(BaseModel):
    """Validation issue found in generated code."""
    severity: str = Field(..., description="Issue severity: error, warning, info")
    file_path: str = Field(..., description="File with the issue")
    line: int | None = Field(None, description="Line number if applicable")
    message: str = Field(..., description="Issue description")
    rule: str = Field(..., description="Validation rule that triggered")


class GeneratedFile(BaseModel):
    """Metadata for a generated file."""
    file_path: str = Field(..., description="Relative path to generated file")
    file_type: FileType = Field(..., description="Type of file")
    size_bytes: int = Field(default=0, ge=0, description="File size in bytes")
    lines_of_code: int = Field(default=0, ge=0, description="Number of lines of code")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Creation timestamp")


class PageObjectMetadata(BaseModel):
    """Metadata for a generated Page Object."""
    name: str = Field(..., description="Page object class name")
    file_path: str = Field(..., description="Path to page object file")
    target_page: str | None = Field(None, description="Target page URL")
    locator_count: int = Field(default=0, ge=0, description="Number of locators")
    action_count: int = Field(default=0, ge=0, description="Number of actions")
    assertion_count: int = Field(default=0, ge=0, description="Number of assertions")


class TestFileMetadata(BaseModel):
    """Metadata for a generated test file."""
    name: str = Field(..., description="Test file name")
    file_path: str = Field(..., description="Path to test file")
    test_count: int = Field(default=0, ge=0, description="Number of test cases")
    page_objects_used: list[str] = Field(default_factory=list, description="Page objects referenced")
    scenarios_covered: list[str] = Field(default_factory=list, description="Scenario IDs covered")


class CodeGenerationMetadata(BaseModel):
    """Complete metadata for generated Playwright project."""
    
    # Generator info
    generator: str = Field(default="CodeGenerationAgent", description="Generator name")
    model: str = Field(..., description="LLM model used")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Generation timestamp")
    duration_seconds: float = Field(default=0.0, ge=0, description="Generation duration")
    version: str = Field(default="1.0.0", description="Generator version")
    
    # Project structure
    project_path: str = Field(..., description="Path to generated project")
    files_generated: int = Field(default=0, ge=0, description="Total files generated")
    total_lines_of_code: int = Field(default=0, ge=0, description="Total lines of code")
    
    # Component counts
    page_objects: list[PageObjectMetadata] = Field(
        default_factory=list,
        description="Generated page objects"
    )
    test_files: list[TestFileMetadata] = Field(
        default_factory=list,
        description="Generated test files"
    )
    fixture_count: int = Field(default=0, ge=0, description="Number of fixtures")
    utility_count: int = Field(default=0, ge=0, description="Number of utility files")
    
    # Coverage
    scenarios_implemented: int = Field(default=0, ge=0, description="Scenarios implemented")
    modules_covered: list[str] = Field(default_factory=list, description="Test modules covered")
    
    # Validation
    validation_status: str = Field(default="passed", description="Validation status")
    validation_issues: list[ValidationIssue] = Field(
        default_factory=list,
        description="Validation issues found"
    )
    warnings: list[str] = Field(default_factory=list, description="Generation warnings")
    
    # Additional metadata
    approved_test_plan_path: str | None = Field(
        None,
        description="Path to approved test plan used"
    )
    notes: str | None = Field(None, description="Additional notes")


class GeneratedProject(BaseModel):
    """Complete generated Playwright project structure."""
    
    project_path: str = Field(..., description="Root path of generated project")
    
    # Core config files
    package_json_path: str | None = Field(None, description="Path to package.json")
    playwright_config_path: str | None = Field(None, description="Path to playwright.config.ts")
    tsconfig_path: str | None = Field(None, description="Path to tsconfig.json")
    env_example_path: str | None = Field(None, description="Path to .env.example")
    readme_path: str | None = Field(None, description="Path to README.md")
    
    # Generated code
    page_objects: list[GeneratedFile] = Field(default_factory=list, description="Page object files")
    test_files: list[GeneratedFile] = Field(default_factory=list, description="Test files")
    fixtures: list[GeneratedFile] = Field(default_factory=list, description="Fixture files")
    utilities: list[GeneratedFile] = Field(default_factory=list, description="Utility files")
    data_files: list[GeneratedFile] = Field(default_factory=list, description="Test data files")
    
    # Metadata
    metadata: CodeGenerationMetadata = Field(..., description="Generation metadata")
    
    # Status
    status: CodeGenerationStatus = Field(
        default=CodeGenerationStatus.COMPLETED,
        description="Project generation status"
    )
    error_message: str | None = Field(None, description="Error message if failed")


class CodeGenerationRequest(BaseModel):
    """Request to generate Playwright project."""
    
    run_id: str = Field(..., description="Workflow run ID")
    workspace_path: str = Field(..., description="Workspace path")
    approved_test_plan_path: str = Field(..., description="Path to approved test plan")
    output_path: str | None = Field(None, description="Custom output path")
    model: str = Field(default="gpt-4", description="LLM model to use")
    overwrite: bool = Field(default=False, description="Overwrite existing project")


class CodeGenerationResult(BaseModel):
    """Result of code generation process."""
    
    status: CodeGenerationStatus = Field(..., description="Generation status")
    project: GeneratedProject | None = Field(None, description="Generated project")
    metadata_path: str | None = Field(None, description="Path to metadata file")
    error_message: str | None = Field(None, description="Error if failed")
    duration_seconds: float = Field(default=0.0, ge=0, description="Total duration")
    warnings: list[str] = Field(default_factory=list, description="Warnings")
