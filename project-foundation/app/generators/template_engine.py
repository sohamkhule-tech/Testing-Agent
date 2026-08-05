"""
Template Engine for Deterministic Code Generation

Generates Playwright project from IR without LLM involvement.
"""

import json
import time
from pathlib import Path
from typing import Any

from app.core.event_bus import EventType, WorkflowEvent, get_event_bus
from app.logging import LoggerMixin
from app.schemas.ir import (
    ActionIR,
    ActionType,
    AssertionIR,
    AssertionType,
    CodeGenerationIR,
    ElementIR,
    LocatorStrategy,
    ModuleIR,
    PageIR,
    TestFlowIR,
)


def _folder_for_file_type(file_type: str) -> str:
    mapping = {
        "package_json": "root",
        "playwright_config": "root",
        "tsconfig": "root",
        "env": "root",
        "gitignore": "root",
        "readme": "root",
        "page_object": "pages",
        "fixture": "fixtures",
        "test_spec": "tests",
        "utility": "utils",
    }
    return mapping.get(file_type, "root")


def _emit_sync(run_id: str, event_type: str, data: dict[str, Any] | None = None) -> None:
    bus = get_event_bus()
    event = WorkflowEvent(type=event_type, run_id=run_id, data=data or {})
    bus.publish_sync(event)


class TemplateEngine(LoggerMixin):
    """
    Deterministic template-based code generator.

    Transforms IR to Playwright TypeScript code.
    No LLM involvement - purely template-based.
    """

    def __init__(self, run_id: str | None = None) -> None:
        """Initialize template engine."""
        super().__init__()
        self._run_id = run_id
        self._start_time = 0.0
        self._file_queue: list[tuple[str, str, str]] = []
        self._files_generated = 0

    def _elapsed_ms(self) -> int:
        return int((time.time() - self._start_time) * 1000)

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        if self._run_id:
            _emit_sync(self._run_id, event_type, data)

    def _emit_file(self, file_type: str, filepath: Path, content: str) -> None:
        if not self._run_id:
            return
        rel = str(filepath)
        lines = content.count("\n") + (1 if content else 0)
        self._emit(EventType.FILE_GENERATED, {
            "path": rel, "name": filepath.name,
            "file_type": file_type,
            "size_bytes": len(content.encode("utf-8")),
            "lines_of_code": lines,
        })

    def _write_and_emit_progress(
        self,
        filepath: Path,
        content: str,
        file_type: str,
        label: str,
        module: str | None = None,
        scenario: str | None = None,
    ) -> None:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        self._files_generated += 1
        folder = _folder_for_file_type(file_type)
        elapsed_ms = self._elapsed_ms()

        # Emit file started event with current activity
        self._emit(EventType.CURRENT_ACTIVITY_UPDATE, {
            "activity": f"Generating {label}",
            "current_file": filepath.name,
            "current_module": module,
            "current_scenario": scenario,
            "file_type": file_type,
        })

        self._emit(EventType.FILE_STARTED, {
            "label": f"Generating {label}",
            "filename": filepath.name,
            "folder": folder,
            "file_type": file_type,
            "module": module,
            "scenario": scenario,
            "elapsed_ms": elapsed_ms,
            "files_generated": self._files_generated,
            "total_files": len(self._file_queue),
        })
        
        # Write file
        filepath.write_text(content, encoding="utf-8")

        # Small pause for realistic real-time streaming feel
        time.sleep(0.06)

        # Emit file completed event
        lines = content.count("\n") + (1 if content else 0)
        size_bytes = len(content.encode("utf-8"))
        
        self._emit(EventType.FILE_COMPLETED, {
            "filename": filepath.name,
            "folder": folder,
            "file_type": file_type,
            "module": module,
            "scenario": scenario,
            "path": str(filepath),
            "size_bytes": size_bytes,
            "lines_of_code": lines,
            "elapsed_ms": elapsed_ms,
            "files_generated": self._files_generated,
            "total_files": len(self._file_queue),
            "content": content,
        })

        # Keep legacy FILE_GENERATED event for compatibility
        self._emit_file(file_type, filepath, content)

    def _write_and_emit(self, filepath: Path, content: str, file_type: str, label: str = "") -> None:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")
        self._emit_file(file_type, filepath, content)

    def _build_file_queue(self, ir: CodeGenerationIR, output_dir: Path) -> list[tuple[str, str, Path]]:
        """Pre-compute ordered list of files to generate."""
        queue: list[tuple[str, str, Path]] = []
        # Config/root files
        queue.append(("package_json", "Config", output_dir / "package.json"))
        queue.append(("playwright_config", "Config", output_dir / "playwright.config.ts"))
        queue.append(("tsconfig", "Config", output_dir / "tsconfig.json"))
        queue.append(("env", "Config", output_dir / ".env"))
        queue.append(("gitignore", "Config", output_dir / ".gitignore"))
        # Page objects
        for page in ir.pages:
            queue.append(("page_object", page.name, output_dir / "pages" / f"{page.page_id.replace('_', '-')}.page.ts"))
        # Fixtures
        queue.append(("fixture", "Fixtures", output_dir / "fixtures" / "index.ts"))
        # Test specs
        for module in ir.modules:
            queue.append(("test_spec", module.name, output_dir / "tests" / f"{module.module_id.replace('_', '-')}.spec.ts"))
        # Utils + README
        queue.append(("utility", "Utilities", output_dir / "utils" / "helpers.ts"))
        queue.append(("readme", "Documentation", output_dir / "README.md"))
        return queue

    def generate_project(
        self,
        ir: CodeGenerationIR,
        output_dir: Path
    ) -> dict[str, Path]:
        """
        Generate complete Playwright project from IR.

        Args:
            ir: Code generation IR
            output_dir: Output directory

        Returns:
            Dictionary mapping file type to file paths
        """
        self._start_time = time.time()
        self.logger.info("generating_project_from_ir", output_dir=str(output_dir))

        self._emit(EventType.PLANNING_PROJECT_STRUCTURE, {
            "label": "Planning project structure",
            "pages": len(ir.pages),
            "modules": len(ir.modules),
            "total_tests": sum(len(m.flows) for m in ir.modules),
        })

        generated_files: dict[str, Path] = {}

        # Pre-compute queue for progress reporting
        file_queue = self._build_file_queue(ir, output_dir)
        total_files = len(file_queue)
        self._file_queue = [(ft, label, str(fp)) for ft, label, fp in file_queue]
        self._files_generated = 0

        # Create directory structure
        self._create_directory_structure(output_dir)

        # Generate configuration files
        generated_files["package.json"] = self._generate_package_json(ir, output_dir)
        generated_files["playwright.config"] = self._generate_playwright_config(ir, output_dir)
        generated_files["tsconfig"] = self._generate_tsconfig(output_dir)
        generated_files[".env"] = self._generate_env_file(ir, output_dir)
        generated_files[".gitignore"] = self._generate_gitignore(output_dir)

        # Generate page objects
        page_files = self._generate_page_objects(ir, output_dir)
        generated_files.update(page_files)

        # Generate fixtures
        generated_files["fixtures"] = self._generate_fixtures(ir, output_dir)

        # Generate tests
        test_files = self._generate_test_files(ir, output_dir)
        generated_files.update(test_files)

        # Generate utilities
        generated_files["utils"] = self._generate_utils(output_dir)

        # Generate README
        generated_files["readme"] = self._generate_readme(ir, output_dir)

        elapsed_ms = self._elapsed_ms()
        self.logger.info(
            "project_generated",
            file_count=len(generated_files),
            output_dir=str(output_dir)
        )

        self._emit(EventType.PACKAGING_PROJECT, {
            "label": "Packaging generated project",
            "total_files": len(generated_files),
            "elapsed_ms": elapsed_ms,
        })

        return generated_files

    def _create_directory_structure(self, output_dir: Path) -> None:
        """Create project directory structure."""
        dirs = [
            output_dir / "pages",
            output_dir / "tests",
            output_dir / "fixtures",
            output_dir / "utils",
            output_dir / "test-results",
            output_dir / "playwright-report",
        ]
        for dir_path in dirs:
            dir_path.mkdir(parents=True, exist_ok=True)

    def _generate_package_json(self, ir: CodeGenerationIR, output_dir: Path) -> Path:
        """Generate package.json."""
        package_json = {
            "name": "playwright-tests",
            "version": "1.0.0",
            "description": "Playwright test automation",
            "scripts": {
                "test": "playwright test",
                "test:headed": "playwright test --headed",
                "test:debug": "playwright test --debug",
                "test:ui": "playwright test --ui",
                "report": "playwright show-report",
                "codegen": "playwright codegen"
            },
            "devDependencies": {
                "@playwright/test": "^1.40.0",
                "@types/node": "^20.0.0",
                "typescript": "^5.0.0",
                "dotenv": "^16.0.0"
            }
        }

        file_path = output_dir / "package.json"
        self._write_and_emit_progress(file_path, json.dumps(package_json, indent=2), "package_json", "package.json")
        return file_path

    def _generate_playwright_config(self, ir: CodeGenerationIR, output_dir: Path) -> Path:
        """Generate playwright.config.ts."""
        browsers = ir.environment.browsers or ["chromium"]
        base_url = ir.environment.base_url

        config = f"""import {{ defineConfig, devices }} from '@playwright/test';
import dotenv from 'dotenv';

dotenv.config();

export default defineConfig({{
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [
    ['html'],
    ['json', {{ outputFile: 'test-results/results.json' }}],
    ['junit', {{ outputFile: 'test-results/junit.xml' }}]
  ],
  use: {{
    baseURL: process.env.BASE_URL || '{base_url}',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  }},
  projects: [
"""

        # Add browser projects
        for browser in browsers:
            if browser == "chromium":
                config += """    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
"""
            elif browser == "firefox":
                config += """    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
"""
            elif browser == "webkit":
                config += """    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
"""

        config += """  ],
});
"""

        file_path = output_dir / "playwright.config.ts"
        self._write_and_emit_progress(file_path, config, "playwright_config", "playwright.config.ts")
        return file_path

    def _generate_tsconfig(self, output_dir: Path) -> Path:
        """Generate tsconfig.json."""
        tsconfig = {
            "compilerOptions": {
                "target": "ES2020",
                "module": "commonjs",
                "lib": ["ES2020"],
                "types": ["node", "@playwright/test"],
                "strict": True,
                "esModuleInterop": True,
                "skipLibCheck": True,
                "forceConsistentCasingInFileNames": True,
                "resolveJsonModule": True,
                "outDir": "./dist"
            },
            "include": ["**/*.ts"],
            "exclude": ["node_modules", "dist", "test-results", "playwright-report"]
        }

        file_path = output_dir / "tsconfig.json"
        self._write_and_emit_progress(file_path, json.dumps(tsconfig, indent=2), "tsconfig", "tsconfig.json")
        return file_path

    def _generate_env_file(self, ir: CodeGenerationIR, output_dir: Path) -> Path:
        """Generate .env file."""
        env_content = f"""# Environment Configuration
BASE_URL={ir.environment.base_url}

# Authentication (if required)
"""
        if ir.environment.auth_required:
            env_content += """USERNAME=your_username
PASSWORD=your_password
"""

        env_content += """
# Browser Configuration
HEADLESS=true

# Timeouts
DEFAULT_TIMEOUT=30000
NAVIGATION_TIMEOUT=30000
"""

        file_path = output_dir / ".env"
        self._write_and_emit_progress(file_path, env_content, "env", ".env")
        return file_path

    def _generate_gitignore(self, output_dir: Path) -> Path:
        """Generate .gitignore."""
        gitignore = """node_modules/
dist/
test-results/
playwright-report/
playwright/.cache/
.env.local
*.log
.DS_Store
"""
        file_path = output_dir / ".gitignore"
        self._write_and_emit_progress(file_path, gitignore, "gitignore", ".gitignore")
        return file_path

    def _generate_page_objects(
        self,
        ir: CodeGenerationIR,
        output_dir: Path
    ) -> dict[str, Path]:
        """Generate page object files."""
        page_files = {}

        for page in ir.pages:
            file_path = self._generate_page_object(page, output_dir)
            page_files[f"page_{page.page_id}"] = file_path

        return page_files

    def _generate_page_object(self, page: PageIR, output_dir: Path) -> Path:
        """Generate single page object file."""
        class_name = self._to_pascal_case(page.page_id)
        
        code = f"""import {{ Page, Locator }} from '@playwright/test';

/**
 * {page.name}
 * {page.description}
 */
export class {class_name} {{
  readonly page: Page;
"""

        # Generate element locators
        for element in page.elements:
            locator_code = self._generate_locator(element)
            code += f"\n  readonly {self._to_camel_case(element.id)}: Locator;\n"

        # Constructor
        code += f"""
  constructor(page: Page) {{
    this.page = page;
"""

        for element in page.elements:
            locator_code = self._generate_locator_expression(element)
            code += f"    this.{self._to_camel_case(element.id)} = {locator_code};\n"

        code += "  }\n"

        # Navigation method
        if page.url_pattern:
            code += f"""
  async goto() {{
    await this.page.goto('{page.url_pattern}');
"""
            if page.page_load_selector:
                code += f"    await this.page.waitForSelector('{page.page_load_selector}');\n"
            code += "  }\n"

        code += "}\n"

        file_path = output_dir / "pages" / f"{page.page_id.replace('_', '-')}.page.ts"
        self._write_and_emit_progress(file_path, code, "page_object", page.name, module=page.name)
        return file_path

    def _generate_locator(self, element: ElementIR) -> str:
        """Generate locator declaration."""
        return f"readonly {self._to_camel_case(element.id)}: Locator;"

    def _generate_locator_expression(self, element: ElementIR) -> str:
        """Generate locator expression."""
        strategy = element.locator_strategy
        value = element.locator_value

        if strategy == LocatorStrategy.ROLE:
            # Parse role format: "button:Login" or just "button"
            if ":" in value:
                role, name = value.split(":", 1)
                return f"this.page.getByRole('{role}', {{ name: '{name}' }})"
            return f"this.page.getByRole('{value}')"
        
        elif strategy == LocatorStrategy.LABEL:
            return f"this.page.getByLabel('{value}')"
        
        elif strategy == LocatorStrategy.PLACEHOLDER:
            return f"this.page.getByPlaceholder('{value}')"
        
        elif strategy == LocatorStrategy.TEXT:
            return f"this.page.getByText('{value}')"
        
        elif strategy == LocatorStrategy.TEST_ID:
            return f"this.page.getByTestId('{value}')"
        
        elif strategy == LocatorStrategy.CSS:
            return f"this.page.locator('{value}')"
        
        elif strategy == LocatorStrategy.XPATH:
            return f"this.page.locator('{value}')"
        
        else:
            return f"this.page.locator('{value}')"

    def _generate_fixtures(self, ir: CodeGenerationIR, output_dir: Path) -> Path:
        """Generate fixtures file."""
        requires_auth = any(page.requires_auth for page in ir.pages)

        code = """import { test as base, Page } from '@playwright/test';

"""

        if requires_auth:
            code += """/**
 * Authenticated test fixture
 */
export const test = base.extend<{ authenticatedPage: Page }>({
  authenticatedPage: async ({ page }, use) => {
    // Perform authentication
    const username = process.env.USERNAME || '';
    const password = process.env.PASSWORD || '';

    if (username && password) {
      // TODO: Implement authentication logic
      // await page.goto('/login');
      // await page.fill('[name="username"]', username);
      // await page.fill('[name="password"]', password);
      // await page.click('button[type="submit"]');
      // await page.waitForURL('/dashboard');
    }

    await use(page);
  },
});

export { expect } from '@playwright/test';
"""
        else:
            code += """export { test, expect } from '@playwright/test';
"""

        file_path = output_dir / "fixtures" / "index.ts"
        self._write_and_emit_progress(file_path, code, "fixture", "Fixtures")
        return file_path

    def _generate_test_files(
        self,
        ir: CodeGenerationIR,
        output_dir: Path
    ) -> dict[str, Path]:
        """Generate test files."""
        test_files = {}

        for module in ir.modules:
            file_path = self._generate_module_test_file(module, ir, output_dir)
            test_files[f"test_{module.module_id}"] = file_path

        return test_files

    def _generate_module_test_file(
        self,
        module: ModuleIR,
        ir: CodeGenerationIR,
        output_dir: Path
    ) -> Path:
        """Generate test file for module."""
        code = f"""import {{ test, expect }} from '../fixtures';
"""

        # Import page objects used in this module
        page_ids = set(module.pages)
        for page_id in page_ids:
            page = next((p for p in ir.pages if p.page_id == page_id), None)
            if page:
                class_name = self._to_pascal_case(page_id)
                file_name = page_id.replace('_', '-')
                code += f"import {{ {class_name} }} from '../pages/{file_name}.page';\n"

        code += f"""
/**
 * {module.name}
 * {module.description}
 */
test.describe('{module.name}', () => {{
"""

        # Generate test cases
        for flow in module.flows:
            code += self._generate_test_case(flow, ir)

        code += "});\n"

        file_path = output_dir / "tests" / f"{module.module_id.replace('_', '-')}.spec.ts"
        self._write_and_emit_progress(file_path, code, "test_spec", module.name, module=module.name)
        return file_path

    def _generate_test_case(self, flow: TestFlowIR, ir: CodeGenerationIR) -> str:
        """Generate single test case."""
        tags = " ".join(f"@{tag}" for tag in flow.tags)
        
        code = f"""
  test('{flow.name} {tags}', async ({{ page }}) => {{
"""

        # Initialize page objects used in flow
        page_objects_used = self._find_page_objects_in_flow(flow, ir)
        for page_id in page_objects_used:
            class_name = self._to_pascal_case(page_id)
            var_name = self._to_camel_case(page_id)
            code += f"    const {var_name} = new {class_name}(page);\n"

        code += "\n"

        # Generate steps
        for step in sorted(flow.steps, key=lambda s: s.step_order):
            code += self._generate_step_code(step, ir)

        code += "  });\n"

        return code

    def _find_page_objects_in_flow(self, flow: TestFlowIR, ir: CodeGenerationIR) -> set[str]:
        """Find page objects used in flow."""
        page_ids = set()

        for step in flow.steps:
            # Find page by elements used in actions/assertions
            for action in step.actions:
                if action.element_id:
                    page_id = self._find_page_for_element(action.element_id, ir)
                    if page_id:
                        page_ids.add(page_id)

            for assertion in step.assertions:
                if assertion.element_id:
                    page_id = self._find_page_for_element(assertion.element_id, ir)
                    if page_id:
                        page_ids.add(page_id)

        return page_ids

    def _find_page_for_element(self, element_id: str, ir: CodeGenerationIR) -> str | None:
        """Find which page contains an element."""
        for page in ir.pages:
            if any(e.id == element_id for e in page.elements):
                return page.page_id
        return None

    def _generate_step_code(self, step: "FlowStepIR", ir: CodeGenerationIR) -> str:
        """Generate code for a flow step."""
        code = f"    // Step {step.step_order}: {step.description}\n"

        # Navigation
        if step.navigation:
            target = step.navigation.target
            if target.startswith('/'):
                code += f"    await page.goto('{target}');\n"
            else:
                # Navigation to a page object
                page_var = self._to_camel_case(target)
                code += f"    await {page_var}.goto();\n"

        # Actions
        for action in step.actions:
            code += self._generate_action_code(action, ir)

        # Assertions
        for assertion in step.assertions:
            code += self._generate_assertion_code(assertion, ir)

        code += "\n"
        return code

    def _generate_action_code(self, action: ActionIR, ir: CodeGenerationIR) -> str:
        """Generate code for an action."""
        if not action.element_id:
            return f"    // TODO: {action.description}\n"

        page_id = self._find_page_for_element(action.element_id, ir)
        if not page_id:
            return f"    // TODO: Element {action.element_id} not found\n"

        page_var = self._to_camel_case(page_id)
        element_var = self._to_camel_case(action.element_id)
        locator = f"{page_var}.{element_var}"

        action_type = action.action_type

        if action_type == ActionType.CLICK:
            return f"    await {locator}.click();\n"
        
        elif action_type == ActionType.FILL:
            value = action.value or ""
            # Check if value is an environment variable
            if value.startswith("$"):
                env_var = value[1:]
                return f"    await {locator}.fill(process.env.{env_var} || '');\n"
            return f"    await {locator}.fill('{value}');\n"
        
        elif action_type == ActionType.SELECT:
            return f"    await {locator}.selectOption('{action.value}');\n"
        
        elif action_type == ActionType.CHECK:
            return f"    await {locator}.check();\n"
        
        elif action_type == ActionType.UNCHECK:
            return f"    await {locator}.uncheck();\n"
        
        elif action_type == ActionType.HOVER:
            return f"    await {locator}.hover();\n"
        
        elif action_type == ActionType.DOUBLE_CLICK:
            return f"    await {locator}.dblclick();\n"
        
        elif action_type == ActionType.CLEAR:
            return f"    await {locator}.clear();\n"
        
        else:
            return f"    // TODO: Action {action_type} on {locator}\n"

    def _generate_assertion_code(self, assertion: AssertionIR, ir: CodeGenerationIR) -> str:
        """Generate code for an assertion."""
        assertion_type = assertion.assertion_type

        # URL/Title assertions don't need element
        if assertion_type == AssertionType.HAS_URL:
            return f"    await expect(page).toHaveURL('{assertion.expected_value}');\n"
        
        if assertion_type == AssertionType.HAS_TITLE:
            return f"    await expect(page).toHaveTitle('{assertion.expected_value}');\n"

        # Element assertions
        if not assertion.element_id:
            return f"    // TODO: {assertion.description}\n"

        page_id = self._find_page_for_element(assertion.element_id, ir)
        if not page_id:
            return f"    // TODO: Element {assertion.element_id} not found\n"

        page_var = self._to_camel_case(page_id)
        element_var = self._to_camel_case(assertion.element_id)
        locator = f"{page_var}.{element_var}"

        if assertion_type == AssertionType.VISIBLE:
            return f"    await expect({locator}).toBeVisible();\n"
        
        elif assertion_type == AssertionType.HIDDEN:
            return f"    await expect({locator}).toBeHidden();\n"
        
        elif assertion_type == AssertionType.ENABLED:
            return f"    await expect({locator}).toBeEnabled();\n"
        
        elif assertion_type == AssertionType.DISABLED:
            return f"    await expect({locator}).toBeDisabled();\n"
        
        elif assertion_type == AssertionType.CHECKED:
            return f"    await expect({locator}).toBeChecked();\n"
        
        elif assertion_type == AssertionType.HAS_TEXT:
            return f"    await expect({locator}).toHaveText('{assertion.expected_value}');\n"
        
        elif assertion_type == AssertionType.HAS_VALUE:
            return f"    await expect({locator}).toHaveValue('{assertion.expected_value}');\n"
        
        elif assertion_type == AssertionType.CONTAINS_TEXT:
            return f"    await expect({locator}).toContainText('{assertion.expected_value}');\n"
        
        else:
            return f"    // TODO: Assertion {assertion_type} on {locator}\n"

    def _generate_utils(self, output_dir: Path) -> Path:
        """Generate utils file."""
        code = """/**
 * Utility functions for tests
 */

export function generateRandomEmail(): string {
  return `test_${Date.now()}@example.com`;
}

export function generateRandomString(length: number = 10): string {
  return Math.random().toString(36).substring(2, length + 2);
}

export async function waitForCondition(
  condition: () => Promise<boolean>,
  timeout: number = 5000
): Promise<void> {
  const startTime = Date.now();
  while (Date.now() - startTime < timeout) {
    if (await condition()) {
      return;
    }
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error('Condition not met within timeout');
}
"""
        file_path = output_dir / "utils" / "helpers.ts"
        self._write_and_emit_progress(file_path, code, "utility", "Utilities")
        return file_path

    def _generate_readme(self, ir: CodeGenerationIR, output_dir: Path) -> Path:
        """Generate README.md."""
        readme = f"""# Playwright Test Automation

Generated test automation for {ir.environment.base_url}

## Project Structure

```
.
├── pages/           # Page Object Models
├── tests/           # Test specifications
├── fixtures/        # Test fixtures and setup
├── utils/           # Utility functions
├── test-results/    # Test execution results
└── playwright-report/  # HTML reports
```

## Setup

1. Install dependencies:
```bash
npm install
```

2. Install Playwright browsers:
```bash
npx playwright install
```

3. Configure environment:
```bash
cp .env .env.local
# Edit .env.local with your configuration
```

## Running Tests

```bash
# Run all tests
npm test

# Run tests in headed mode
npm run test:headed

# Run tests in UI mode
npm run test:ui

# Debug tests
npm run test:debug

# View last test report
npm run report
```

## Test Modules

"""
        for module in ir.modules:
            readme += f"- **{module.name}**: {module.description} ({len(module.flows)} tests)\n"

        readme += f"""
## Configuration

- Base URL: `{ir.environment.base_url}`
- Browsers: {', '.join(ir.environment.browsers)}
- Parallel execution: Enabled
- Retries: 2 (in CI), 0 (locally)

## Generated Files

- Total Pages: {len(ir.pages)}
- Total Tests: {sum(len(m.flows) for m in ir.modules)}
- Total Modules: {len(ir.modules)}

## Generated by

AI Testing Platform - Phase 7 (IR-driven Code Generation)
Generated: {str(ir.metadata.generated_at)}
"""

        file_path = output_dir / "README.md"
        self._write_and_emit_progress(file_path, readme, "readme", "README")
        return file_path

    def _to_pascal_case(self, text: str) -> str:
        """Convert text to PascalCase."""
        return "".join(word.capitalize() for word in text.replace("-", "_").split("_"))

    def _to_camel_case(self, text: str) -> str:
        """Convert text to camelCase."""
        words = text.replace("-", "_").split("_")
        return words[0].lower() + "".join(word.capitalize() for word in words[1:])
