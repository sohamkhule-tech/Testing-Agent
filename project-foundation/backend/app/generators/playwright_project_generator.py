"""
Playwright Project Generator

Orchestrates generation of complete Playwright test automation project.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.artifact_writer import ArtifactWriter
from app.core.code_validator import CodeValidator
from app.core.interfaces import ILLMClient
from app.core.prompt_builder import PromptBuilder
from app.core.template_manager import TemplateManager
from app.logging import LoggerMixin
from app.schemas.code_generation import (
    CodeGenerationMetadata,
    CodeGenerationStatus,
    FileType,
    GeneratedFile,
    GeneratedProject,
    PageObjectMetadata,
    TestFileMetadata,
)
from app.schemas.review import ApprovedTestPlan


class PlaywrightProjectGenerator(LoggerMixin):
    """
    Generates complete Playwright test automation project.
    
    Responsibilities:
    - Orchestrate project generation
    - Create project structure
    - Generate page objects
    - Generate test files
    - Generate fixtures and utilities
    - Generate config files
    - Validate generated code
    - Write artifacts to filesystem
    """

    def __init__(
        self,
        llm_client: ILLMClient,
        template_manager: TemplateManager,
        artifact_writer: ArtifactWriter,
        code_validator: CodeValidator,
        prompt_builder: PromptBuilder,
    ) -> None:
        """
        Initialize project generator.

        Args:
            llm_client: LLM client for code generation
            template_manager: Template provider
            artifact_writer: Filesystem writer
            code_validator: Code validator
            prompt_builder: Prompt builder
        """
        super().__init__()
        self.llm_client = llm_client
        self.template_manager = template_manager
        self.artifact_writer = artifact_writer
        self.code_validator = code_validator
        self.prompt_builder = prompt_builder

    async def generate_project(
        self,
        approved_plan: ApprovedTestPlan,
        output_path: Path,
        base_url: str = "http://localhost:3000",
        overwrite: bool = False,
    ) -> GeneratedProject:
        """
        Generate complete Playwright project from approved test plan.

        Args:
            approved_plan: Approved test plan
            output_path: Output directory path
            base_url: Application base URL
            overwrite: Whether to overwrite existing project

        Returns:
            GeneratedProject with metadata

        Raises:
            FileExistsError: If project exists and overwrite is False
            ValidationError: If validation fails
        """
        start_time = datetime.now(timezone.utc)
        self.logger.info("generating_playwright_project", output_path=str(output_path))

        try:
            # Create project structure
            self.artifact_writer.create_project_structure(output_path)

            # Generate all components
            config_files = await self._generate_config_files(output_path, base_url)
            page_objects = await self._generate_page_objects(approved_plan, output_path)
            test_files = await self._generate_test_files(approved_plan, output_path, page_objects)
            fixtures = await self._generate_fixtures(output_path, approved_plan)
            utilities = await self._generate_utilities(output_path)
            data_files = await self._generate_test_data(approved_plan, output_path)
            doc_files = await self._generate_documentation(output_path)

            # Build metadata
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            metadata = self._build_metadata(
                approved_plan=approved_plan,
                output_path=output_path,
                page_objects=page_objects,
                test_files=test_files,
                fixtures=fixtures,
                utilities=utilities,
                duration=duration,
            )

            # Validate generated project
            is_valid, validation_issues = self.code_validator.validate_project(output_path)
            metadata.validation_status = "passed" if is_valid else "failed"
            metadata.validation_issues = validation_issues

            if not is_valid:
                self.logger.warning(
                    "validation_failed",
                    error_count=len([i for i in validation_issues if i.severity == "error"])
                )

            # Write metadata
            metadata_path = self.artifact_writer.write_metadata(output_path, metadata)

            # Build project result
            project = GeneratedProject(
                project_path=str(output_path),
                package_json_path=str(output_path / "package.json"),
                playwright_config_path=str(output_path / "playwright.config.ts"),
                tsconfig_path=str(output_path / "tsconfig.json"),
                env_example_path=str(output_path / ".env.example"),
                readme_path=str(output_path / "README.md"),
                page_objects=page_objects,
                test_files=test_files,
                fixtures=fixtures,
                utilities=utilities,
                data_files=data_files,
                metadata=metadata,
                status=CodeGenerationStatus.COMPLETED,
            )

            self.logger.info(
                "project_generation_complete",
                duration=duration,
                files_generated=metadata.files_generated,
                validation_status=metadata.validation_status,
            )

            return project

        except Exception as e:
            self.logger.error("project_generation_failed", error=str(e))
            raise

    async def _generate_config_files(
        self,
        output_path: Path,
        base_url: str
    ) -> list[GeneratedFile]:
        """Generate configuration files."""
        self.logger.info("generating_config_files")

        config_files = []

        # package.json
        package_json = self.template_manager.get_package_json_template()
        config_files.append(
            self.artifact_writer.write_config_file(output_path, "package.json", package_json)
        )

        # playwright.config.ts
        playwright_config = self.template_manager.get_playwright_config_template()
        config_files.append(
            self.artifact_writer.write_config_file(output_path, "playwright.config.ts", playwright_config)
        )

        # tsconfig.json
        tsconfig = self.template_manager.get_tsconfig_template()
        config_files.append(
            self.artifact_writer.write_config_file(output_path, "tsconfig.json", tsconfig)
        )

        # .env.example
        env_example = self.template_manager.get_env_example_template()
        # Substitute base URL
        env_example = env_example.replace("http://localhost:3000", base_url)
        config_files.append(
            self.artifact_writer.write_config_file(output_path, ".env.example", env_example)
        )

        # .gitignore
        config_files.append(
            self.artifact_writer.create_gitignore(output_path)
        )

        self.logger.info("config_files_generated", count=len(config_files))
        return config_files

    async def _generate_page_objects(
        self,
        approved_plan: ApprovedTestPlan,
        output_path: Path
    ) -> list[GeneratedFile]:
        """Generate page object files."""
        self.logger.info("generating_page_objects")

        page_objects = []

        # Generate BasePage
        base_page_content = self.template_manager.get_base_page_template()
        page_objects.append(
            self.artifact_writer.write_page_object(output_path, "BasePage", base_page_content)
        )

        # Group scenarios by module
        scenarios_by_module = self._group_scenarios_by_module(approved_plan)

        # Generate page object for each module
        for module_name, scenarios in scenarios_by_module.items():
            try:
                page_object_content = await self._generate_page_object_code(
                    module_name, scenarios
                )
                
                class_name = self._module_to_class_name(module_name)
                page_object_file = self.artifact_writer.write_page_object(
                    output_path, class_name, page_object_content
                )
                page_objects.append(page_object_file)

            except Exception as e:
                self.logger.error(
                    "page_object_generation_failed",
                    module=module_name,
                    error=str(e)
                )
                # Continue with other modules

        self.logger.info("page_objects_generated", count=len(page_objects))
        return page_objects

    async def _generate_page_object_code(
        self,
        module_name: str,
        scenarios: list[Any]
    ) -> str:
        """Generate page object code using LLM."""
        class_name = self._module_to_class_name(module_name)
        
        # Build context for prompt
        context = {
            "module_name": module_name,
            "class_name": class_name,
            "scenarios": [
                {
                    "title": s.metadata.title,
                    "target_page": s.metadata.target_page,
                    "steps": s.metadata.test_steps,
                    "priority": s.metadata.priority.value,
                }
                for s in scenarios
            ],
        }

        prompt = self.prompt_builder.build_file_generation_prompt("page_object", context)

        # Generate with LLM
        response = await self.llm_client.generate_response(prompt)

        # Extract code from response
        code = self._extract_code_from_response(response)

        return code

    async def _generate_test_files(
        self,
        approved_plan: ApprovedTestPlan,
        output_path: Path,
        page_objects: list[GeneratedFile]
    ) -> list[GeneratedFile]:
        """Generate test specification files."""
        self.logger.info("generating_test_files")

        test_files = []

        # Group scenarios by module
        scenarios_by_module = self._group_scenarios_by_module(approved_plan)

        # Generate test file for each module
        for module_name, scenarios in scenarios_by_module.items():
            try:
                test_content = await self._generate_test_code(
                    module_name, scenarios, page_objects
                )
                
                test_file = self.artifact_writer.write_test_file(
                    output_path, module_name.lower().replace(" ", "-"), test_content
                )
                test_files.append(test_file)

            except Exception as e:
                self.logger.error(
                    "test_file_generation_failed",
                    module=module_name,
                    error=str(e)
                )

        self.logger.info("test_files_generated", count=len(test_files))
        return test_files

    async def _generate_test_code(
        self,
        module_name: str,
        scenarios: list[Any],
        page_objects: list[GeneratedFile]
    ) -> str:
        """Generate test code using LLM."""
        context = {
            "module_name": module_name,
            "scenarios": [
                {
                    "id": s.metadata.id,
                    "title": s.metadata.title,
                    "description": s.metadata.description,
                    "priority": s.metadata.priority.value,
                    "steps": s.metadata.test_steps,
                    "expected_result": s.metadata.expected_result,
                    "preconditions": s.metadata.preconditions,
                    "required_data": s.metadata.required_test_data,
                }
                for s in scenarios
            ],
            "page_objects": [po.file_path for po in page_objects],
        }

        prompt = self.prompt_builder.build_file_generation_prompt("test", context)

        # Generate with LLM
        response = await self.llm_client.generate_response(prompt)

        # Extract code from response
        code = self._extract_code_from_response(response)

        return code

    async def _generate_fixtures(
        self,
        output_path: Path,
        approved_plan: ApprovedTestPlan
    ) -> list[GeneratedFile]:
        """Generate fixture files."""
        self.logger.info("generating_fixtures")

        fixtures = []

        # Base fixture
        base_fixture_content = self.template_manager.get_base_fixture_template()
        fixtures.append(
            self.artifact_writer.write_fixture_file(output_path, "base.fixture", base_fixture_content)
        )

        # Generate auth fixture if authentication is required
        if approved_plan.test_plan.application_summary.authentication_required:
            auth_fixture_content = await self._generate_auth_fixture()
            fixtures.append(
                self.artifact_writer.write_fixture_file(output_path, "auth.fixture", auth_fixture_content)
            )

        self.logger.info("fixtures_generated", count=len(fixtures))
        return fixtures

    async def _generate_auth_fixture(self) -> str:
        """Generate authentication fixture."""
        return """import { test as base } from '@playwright/test';
import { Page } from '@playwright/test';

type AuthFixtures = {
  authenticatedPage: Page;
};

export const test = base.extend<AuthFixtures>({
  authenticatedPage: async ({ page }, use) => {
    // Perform authentication
    await page.goto('/login');
    await page.getByLabel('Username').fill(process.env.TEST_USERNAME || 'testuser');
    await page.getByLabel('Password').fill(process.env.TEST_PASSWORD || 'password');
    await page.getByRole('button', { name: 'Log in' }).click();
    await page.waitForURL(/\\/dashboard/);

    await use(page);
  },
});

export { expect } from '@playwright/test';
"""

    async def _generate_utilities(self, output_path: Path) -> list[GeneratedFile]:
        """Generate utility files."""
        self.logger.info("generating_utilities")

        utilities = []

        # waits.ts
        waits_content = self.template_manager.get_waits_utility_template()
        utilities.append(
            self.artifact_writer.write_utility_file(output_path, "waits", waits_content)
        )

        # helpers.ts
        helpers_content = self.template_manager.get_helpers_utility_template()
        utilities.append(
            self.artifact_writer.write_utility_file(output_path, "helpers", helpers_content)
        )

        # constants.ts
        constants_content = self.template_manager.get_constants_utility_template()
        utilities.append(
            self.artifact_writer.write_utility_file(output_path, "constants", constants_content)
        )

        # logger.ts
        logger_content = self.template_manager.get_logger_utility_template()
        utilities.append(
            self.artifact_writer.write_utility_file(output_path, "logger", logger_content)
        )

        self.logger.info("utilities_generated", count=len(utilities))
        return utilities

    async def _generate_test_data(
        self,
        approved_plan: ApprovedTestPlan,
        output_path: Path
    ) -> list[GeneratedFile]:
        """Generate test data files."""
        self.logger.info("generating_test_data")

        data_files = []

        # test-data.json
        test_data_content = self.template_manager.get_test_data_template()
        data_files.append(
            self.artifact_writer.write_data_file(output_path, "test-data.json", test_data_content)
        )

        self.logger.info("test_data_generated", count=len(data_files))
        return data_files

    async def _generate_documentation(self, output_path: Path) -> list[GeneratedFile]:
        """Generate documentation files."""
        self.logger.info("generating_documentation")

        doc_files = []

        # README.md
        readme_content = self.template_manager.get_readme_template()
        doc_files.append(
            self.artifact_writer.write_documentation(output_path, "README.md", readme_content)
        )

        self.logger.info("documentation_generated", count=len(doc_files))
        return doc_files

    def _group_scenarios_by_module(self, approved_plan: ApprovedTestPlan) -> dict[str, list[Any]]:
        """Group scenarios by module."""
        scenarios_by_module: dict[str, list[Any]] = {}

        for scenario in approved_plan.test_scenarios:
            module = scenario.metadata.module
            if module not in scenarios_by_module:
                scenarios_by_module[module] = []
            scenarios_by_module[module].append(scenario)

        return scenarios_by_module

    def _module_to_class_name(self, module_name: str) -> str:
        """Convert module name to class name."""
        # Remove special characters and convert to PascalCase
        words = module_name.replace("-", " ").replace("_", " ").split()
        class_name = "".join(word.capitalize() for word in words)
        
        # Ensure it ends with "Page"
        if not class_name.endswith("Page"):
            class_name += "Page"
            
        return class_name

    def _extract_code_from_response(self, response: str) -> str:
        """Extract code from LLM response."""
        # Remove markdown code blocks if present
        import re
        
        # Try to find code block with typescript or ts
        patterns = [
            r"```typescript\n(.*?)\n```",
            r"```ts\n(.*?)\n```",
            r"```\n(.*?)\n```",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, response, re.DOTALL)
            if match:
                return match.group(1).strip()
        
        # If no code block found, return entire response
        return response.strip()

    def _build_metadata(
        self,
        approved_plan: ApprovedTestPlan,
        output_path: Path,
        page_objects: list[GeneratedFile],
        test_files: list[GeneratedFile],
        fixtures: list[GeneratedFile],
        utilities: list[GeneratedFile],
        duration: float,
    ) -> CodeGenerationMetadata:
        """Build generation metadata."""
        # Build page object metadata
        page_object_metadata = []
        for po in page_objects:
            if "BasePage" not in po.file_path:
                page_object_metadata.append(
                    PageObjectMetadata(
                        name=Path(po.file_path).stem,
                        file_path=po.file_path,
                        locator_count=0,  # TODO: Parse and count
                        action_count=0,
                        assertion_count=0,
                    )
                )

        # Build test file metadata
        test_file_metadata = []
        for tf in test_files:
            test_file_metadata.append(
                TestFileMetadata(
                    name=Path(tf.file_path).name,
                    file_path=tf.file_path,
                    test_count=0,  # TODO: Parse and count
                    page_objects_used=[],
                    scenarios_covered=[],
                )
            )

        # Count total files and LOC
        all_files = page_objects + test_files + fixtures + utilities
        total_files = len(all_files)
        total_loc = sum(f.lines_of_code for f in all_files)

        # Get modules covered
        scenarios_by_module = self._group_scenarios_by_module(approved_plan)
        modules_covered = list(scenarios_by_module.keys())

        metadata = CodeGenerationMetadata(
            model=self.llm_client.get_model_name(),
            project_path=str(output_path),
            files_generated=total_files,
            total_lines_of_code=total_loc,
            page_objects=page_object_metadata,
            test_files=test_file_metadata,
            fixture_count=len(fixtures),
            utility_count=len(utilities),
            scenarios_implemented=len(approved_plan.test_scenarios),
            modules_covered=modules_covered,
            duration_seconds=duration,
        )

        return metadata
