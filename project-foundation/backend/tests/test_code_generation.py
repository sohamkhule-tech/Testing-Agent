"""
Unit tests for Code Generation components.
"""

import json
from pathlib import Path
from uuid import uuid4

import pytest

from app.core.artifact_writer import ArtifactWriter
from app.core.code_validator import CodeValidator
from app.core.prompt_builder import PromptBuilder
from app.core.template_manager import TemplateManager
from app.schemas.code_generation import (
    CodeGenerationMetadata,
    FileType,
    GeneratedFile,
    PageObjectMetadata,
    ValidationIssue,
)
from app.schemas.review import ApprovedTestPlan, ReviewMetadata, ReviewStatus
from app.schemas.test_plan import (
    Priority,
    Risk,
    ScenarioMetadata,
    TestCategory,
    TestPlan,
    TestScenario,
)


class TestPromptBuilder:
    """Tests for PromptBuilder."""

    def test_build_generation_prompt_basic(self):
        """Test building basic generation prompt."""
        # Arrange
        builder = PromptBuilder()
        
        scenario = TestScenario(
            metadata=ScenarioMetadata(
                id="test-001",
                title="Test Login",
                description="Test user login functionality",
                priority=Priority.HIGH,
                category=TestCategory.AUTHENTICATION,
                module="Login",
                expected_result="User successfully logged in",
            )
        )
        
        test_plan = TestPlan(
            run_id=uuid4(),
            request_id=uuid4(),
            generated_at="2024-01-01T00:00:00Z",
            modules=[],
            test_scenarios=[scenario],
        )
        
        approved_plan = ApprovedTestPlan(
            run_id=uuid4(),
            request_id=uuid4(),
            generated_at="2024-01-01T00:00:00Z",
            approved_at="2024-01-01T00:00:00Z",
            review_status=ReviewStatus.APPROVED,
            reviewer_name="tester",
            test_plan_data={
                "test_scenarios": [scenario.model_dump(mode="json")],
                "application_summary": {}
            }
        )

        # Act
        prompt = builder.build_generation_prompt(approved_plan)

        # Assert
        assert "Playwright Test Automation Code Generation" in prompt
        assert "Test Login" in prompt
        assert "authentication" in prompt.lower()
        assert "high" in prompt.lower()

    def test_build_file_generation_prompt_page_object(self):
        """Test building page object generation prompt."""
        # Arrange
        builder = PromptBuilder()
        context = {
            "module_name": "Login",
            "scenarios": [
                {"title": "Login with valid credentials"},
                {"title": "Login with invalid credentials"},
            ],
        }

        # Act
        prompt = builder.build_file_generation_prompt("page_object", context)

        # Assert
        assert "Page Object" in prompt
        assert "Login" in prompt
        assert "Locator API" in prompt


class TestTemplateManager:
    """Tests for TemplateManager."""

    def test_get_package_json_template(self):
        """Test getting package.json template."""
        # Arrange
        manager = TemplateManager()

        # Act
        template = manager.get_package_json_template()

        # Assert
        assert "@playwright/test" in template
        assert '"test":' in template
        assert "typescript" in template
        assert "allure-playwright" in template
        assert "allure-commandline" in template
        data = json.loads(template)
        assert "scripts" in data
        assert "devDependencies" in data
        assert "allure-playwright" in data["devDependencies"]
        assert "allure-commandline" in data["devDependencies"]

    def test_get_playwright_config_template(self):
        """Test getting playwright config template."""
        # Arrange
        manager = TemplateManager()

        # Act
        template = manager.get_playwright_config_template()

        # Assert
        assert "defineConfig" in template
        assert "chromium" in template
        assert "firefox" in template
        assert "webkit" in template
        assert "retries" in template
        assert "allure-playwright" in template
        assert "ALLURE_RESULTS_DIR" in template

    def test_get_base_page_template(self):
        """Test getting BasePage template."""
        # Arrange
        manager = TemplateManager()

        # Act
        template = manager.get_base_page_template()

        # Assert
        assert "export abstract class BasePage" in template
        assert "protected readonly page: Page" in template
        assert "async goto" in template

    def test_substitute_variables(self):
        """Test variable substitution."""
        # Arrange
        manager = TemplateManager()
        template = "Hello {name}, your age is {age}"
        variables = {"name": "John", "age": 30}

        # Act
        result = manager.substitute_variables(template, variables)

        # Assert
        assert result == "Hello John, your age is 30"


class TestArtifactWriter:
    """Tests for ArtifactWriter."""

    def test_create_project_structure(self, tmp_path):
        """Test creating project structure."""
        # Arrange
        writer = ArtifactWriter()
        project_path = tmp_path / "playwright-project"

        # Act
        writer.create_project_structure(project_path)

        # Assert
        assert project_path.exists()
        assert (project_path / "pages").exists()
        assert (project_path / "tests").exists()
        assert (project_path / "fixtures").exists()
        assert (project_path / "utils").exists()
        assert (project_path / "data").exists()

    def test_write_file(self, tmp_path):
        """Test writing file."""
        # Arrange
        writer = ArtifactWriter()
        project_path = tmp_path / "project"
        file_path = project_path / "test.ts"
        content = "console.log('Hello');"

        # Act
        generated_file = writer.write_file(
            file_path, content, FileType.UTILITY
        )

        # Assert
        assert file_path.exists()
        assert file_path.read_text() == content
        assert generated_file.file_type == FileType.UTILITY
        assert generated_file.lines_of_code == 1

    def test_write_json_file(self, tmp_path):
        """Test writing JSON file."""
        # Arrange
        writer = ArtifactWriter()
        file_path = tmp_path / "data.json"
        data = {"name": "test", "value": 123}

        # Act
        generated_file = writer.write_json_file(file_path, data)

        # Assert
        assert file_path.exists()
        loaded_data = json.loads(file_path.read_text())
        assert loaded_data == data

    def test_write_page_object(self, tmp_path):
        """Test writing page object."""
        # Arrange
        writer = ArtifactWriter()
        project_path = tmp_path / "project"
        writer.create_project_structure(project_path)
        content = "export class LoginPage {}"

        # Act
        generated_file = writer.write_page_object(
            project_path, "LoginPage", content
        )

        # Assert
        page_path = project_path / "pages" / "LoginPage.ts"
        assert page_path.exists()
        assert generated_file.file_type == FileType.PAGE_OBJECT

    def test_create_gitignore(self, tmp_path):
        """Test creating .gitignore."""
        # Arrange
        writer = ArtifactWriter()

        # Act
        generated_file = writer.create_gitignore(tmp_path)

        # Assert
        gitignore_path = tmp_path / ".gitignore"
        assert gitignore_path.exists()
        content = gitignore_path.read_text()
        assert "node_modules" in content
        assert "test-results" in content


class TestCodeValidator:
    """Tests for CodeValidator."""

    def test_validate_project_missing_folders(self, tmp_path):
        """Test validation with missing folders."""
        # Arrange
        validator = CodeValidator()

        # Act
        is_valid, issues = validator.validate_project(tmp_path)

        # Assert
        assert not is_valid
        assert len(issues) > 0
        assert any("folder" in issue.message.lower() for issue in issues)

    def test_validate_project_missing_files(self, tmp_path):
        """Test validation with missing required files."""
        # Arrange
        validator = CodeValidator()
        
        # Create folders but not files
        (tmp_path / "pages").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "fixtures").mkdir()
        (tmp_path / "utils").mkdir()
        (tmp_path / "data").mkdir()
        (tmp_path / "reports").mkdir()
        (tmp_path / "screenshots").mkdir()

        # Act
        is_valid, issues = validator.validate_project(tmp_path)

        # Assert
        assert not is_valid
        error_issues = [i for i in issues if i.severity == "error"]
        assert len(error_issues) > 0

    def test_validate_project_invalid_package_json(self, tmp_path):
        """Test validation with invalid package.json."""
        # Arrange
        validator = CodeValidator()
        writer = ArtifactWriter()
        writer.create_project_structure(tmp_path)
        
        # Write invalid JSON
        (tmp_path / "package.json").write_text("{ invalid json }")

        # Act
        is_valid, issues = validator.validate_project(tmp_path)

        # Assert
        assert not is_valid
        json_issues = [i for i in issues if "JSON" in i.message]
        assert len(json_issues) > 0

    def test_validate_project_valid_structure(self, tmp_path):
        """Test validation with valid project structure."""
        # Arrange
        validator = CodeValidator()
        writer = ArtifactWriter()
        template_manager = TemplateManager()
        
        # Create complete valid structure
        writer.create_project_structure(tmp_path)
        writer.write_config_file(
            tmp_path, "package.json", template_manager.get_package_json_template()
        )
        writer.write_config_file(
            tmp_path, "playwright.config.ts", template_manager.get_playwright_config_template()
        )
        writer.write_config_file(
            tmp_path, "tsconfig.json", template_manager.get_tsconfig_template()
        )
        writer.write_config_file(
            tmp_path, ".env.example", template_manager.get_env_example_template()
        )
        writer.write_documentation(
            tmp_path, "README.md", template_manager.get_readme_template()
        )
        writer.write_page_object(
            tmp_path, "BasePage", template_manager.get_base_page_template()
        )
        writer.write_fixture_file(
            tmp_path, "base.fixture", template_manager.get_base_fixture_template()
        )

        # Act
        is_valid, issues = validator.validate_project(tmp_path)

        # Assert
        # May have warnings but should have no critical errors
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0


class TestCodeGenerationSchemas:
    """Tests for code generation schemas."""

    def test_validation_issue_creation(self):
        """Test creating ValidationIssue."""
        # Act
        issue = ValidationIssue(
            severity="error",
            file_path="/path/to/file.ts",
            line=10,
            message="Missing semicolon",
            rule="typescript_syntax",
        )

        # Assert
        assert issue.severity == "error"
        assert issue.line == 10

    def test_generated_file_creation(self):
        """Test creating GeneratedFile."""
        # Act
        generated_file = GeneratedFile(
            file_path="pages/LoginPage.ts",
            file_type=FileType.PAGE_OBJECT,
            size_bytes=1024,
            lines_of_code=50,
        )

        # Assert
        assert generated_file.file_type == FileType.PAGE_OBJECT
        assert generated_file.lines_of_code == 50

    def test_code_generation_metadata_creation(self):
        """Test creating CodeGenerationMetadata."""
        # Act
        metadata = CodeGenerationMetadata(
            model="gpt-4",
            project_path="/path/to/project",
            files_generated=20,
            page_objects=[
                PageObjectMetadata(
                    name="LoginPage",
                    file_path="pages/LoginPage.ts",
                    locator_count=5,
                    action_count=3,
                )
            ],
        )

        # Assert
        assert metadata.model == "gpt-4"
        assert metadata.files_generated == 20
        assert len(metadata.page_objects) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
