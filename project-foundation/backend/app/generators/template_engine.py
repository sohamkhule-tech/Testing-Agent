"""
Template Engine for Deterministic Code Generation

Generates Playwright project from IR without LLM involvement.
"""

import json
import re
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
    FlowStepIR,
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
        output_dir: Path,
        workspace_path: str | None = None,
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
        generated_files[".env"] = self._generate_env_file(ir, output_dir, workspace_path=workspace_path)
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
                "codegen": "playwright codegen",
                "allure:generate": "allure generate allure-results -o allure-report --clean",
                "allure:open": "allure open allure-report"
            },
            "devDependencies": {
                "@playwright/test": "^1.40.0",
                "@types/node": "^20.0.0",
                "typescript": "^5.0.0",
                "dotenv": "^16.0.0",
                "allure-commandline": "^2.29.0",
                "allure-playwright": "^2.15.1"
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

// CI is provided by the platform runner as the STRING "true"/"false".
// The naive truthiness check treats the string "false" as enabled,
// silently turning on retries + single worker on every local run.
const isCI = process.env.CI === 'true';

export default defineConfig({{
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: isCI,
  retries: isCI ? 2 : 0,
  workers: isCI ? 1 : undefined,
  preserveOutput: 'always',
  reporter: [
    ['html'],
    ['json', {{ outputFile: 'test-results/results.json' }}],
    ['junit', {{ outputFile: 'test-results/junit.xml' }}],
    ['allure-playwright', {{ outputFolder: process.env.ALLURE_RESULTS_DIR || 'allure-results' }}]
  ],
  use: {{
    baseURL: process.env.BASE_URL || '{base_url}',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'off',
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

    def _generate_env_file(
        self,
        ir: CodeGenerationIR,
        output_dir: Path,
        workspace_path: str | None = None,
    ) -> Path:
        """Generate .env file using actual credentials from CredentialStore when available."""
        # --- Load user-provided credentials from the credential store ---
        valid_username = ""
        valid_password = ""
        if workspace_path:
            try:
                from app.services.prompt_builder import get_credential_store
                cred_store = get_credential_store()
                auth = cred_store.load(workspace_path)
                valid_username = auth.username or ""
                valid_password = auth.password or ""
            except Exception:
                pass  # Fall through to empty defaults

        env_content = f"""# Environment Configuration
BASE_URL={ir.environment.base_url}

# Authentication Credentials
"""
        if ir.environment.auth_required or valid_username or valid_password:
            # Evidence-based routes for the authenticated fixture (crawler data).
            _auth_page = self._find_auth_page(ir)
            _landing_page = self._find_landing_page(ir, _auth_page)
            _login_url = _auth_page.url_pattern if _auth_page and _auth_page.url_pattern else ""
            _success_url = _landing_page.url_pattern if _landing_page and _landing_page.url_pattern else ""

            env_content += f"""VALID_IDENTITY={valid_username}
VALID_USERNAME={valid_username}
VALID_PASSWORD={valid_password}
INVALID_IDENTITY=invalid_user_xyz
INVALID_USERNAME=invalid_user_xyz
INVALID_PASSWORD=wrong_password_xyz
IDENTITY={valid_username}
USERNAME={valid_username}
PASSWORD={valid_password}
TEST_IDENTITY={valid_username}
TEST_USERNAME={valid_username}
TEST_PASSWORD={valid_password}
AUTH_LOGIN_URL={_login_url}
AUTH_SUCCESS_URL={_success_url}
"""

        env_content += f"""
# Boundary Test Values
MAX_LENGTH_USERNAME={'a' * 256}
MAX_LENGTH_PASSWORD={'b' * 256}

# Security Test Payloads
SQL_INJECTION_USERNAME=' OR '1'='1
SQL_INJECTION_PASSWORD=' OR '1'='1
SQL_INJECTION=' OR '1'='1
XSS_PAYLOAD_USERNAME=<script>alert('xss')</script>
XSS_PAYLOAD_PASSWORD=<script>alert('xss')</script>
XSS_SCRIPT=<script>alert('xss')</script>

# Locked / Expired Account
LOCKED_USERNAME=locked_user_test
EXPIRED_PASSWORD=OldPassword@123

# Case Sensitivity Test
CASE_SENSITIVE_USERNAME={valid_username.upper() if valid_username else 'ADMIN'}
CASE_SENSITIVE_PASSWORD={valid_password.lower() if valid_password else 'admin@123'}

# Special Characters Test
SPECIAL_CHARS_USERNAME={valid_username}@#$
SPECIAL_CHARS_PASSWORD={valid_password}!#$
"""

        # Append all variables declared in the IR so generated spec files can resolve them.
        if ir.environment.variables:
            existing_keys: set[str] = set()
            for line in env_content.splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    existing_keys.add(line.split("=", 1)[0].strip())
            ir_extras = "\n# Variables declared in the test IR\n"
            added = False
            for var_name, var_value in ir.environment.variables.items():
                if var_name not in existing_keys:
                    ir_extras += f"{var_name}={var_value}\n"
                    added = True
            if added:
                env_content += ir_extras

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

        # Generate per-state locators for dynamic/stateful elements
        for element in page.elements:
            for state in (element.states or []):
                code += f"\n  readonly {self._state_locator_name(element.id, state.id)}: Locator;\n"

        # Constructor
        code += f"""
  constructor(page: Page) {{
    this.page = page;
"""

        for element in page.elements:
            locator_code = self._generate_locator_expression(element)
            code += f"    this.{self._to_camel_case(element.id)} = {locator_code};\n"

        for element in page.elements:
            for state in (element.states or []):
                state_expr = self._generate_state_locator_expression(element, state)
                code += f"    this.{self._state_locator_name(element.id, state.id)} = {state_expr};\n"

        code += "  }\n"

        # Navigation method
        if page.url_pattern:
            code += f"""
  async goto() {{
    await this.page.goto('{page.url_pattern}');
    await this.page.waitForLoadState('networkidle');
  }}\n"""

        code += "}\n"

        file_path = output_dir / "pages" / f"{page.page_id.replace('_', '-')}.page.ts"
        self._write_and_emit_progress(file_path, code, "page_object", page.name, module=page.name)
        return file_path

    def _generate_locator(self, element: ElementIR) -> str:
        """Generate locator declaration."""
        return f"readonly {self._to_camel_case(element.id)}: Locator;"

    @staticmethod
    def _js_string(value: str) -> str:
        """Return ``value`` as a safely-escaped JavaScript string literal.

        Uses ``json.dumps`` so embedded single/double quotes, backslashes, and
        control characters are escaped correctly. This prevents generated code
        like ``this.page.locator('input[type='text']')`` where an unescaped
        quote inside a CSS/XPATH/placeholder value terminates the string and
        produces a TypeScript ``SyntaxError``.
        """
        return json.dumps(value)

    @staticmethod
    def _js_regex(value: str) -> str:
        r"""Return ``value`` safely escaped for embedding inside a JavaScript/TypeScript
        regex literal (i.e., between forward-slash delimiters: ``/…/i``).

        A plain forward slash ``/`` terminates the regex literal in TypeScript,
        so IR values such as ``"Email Address / User ID"`` must have their slashes
        escaped as ``\/``.  All other regex metacharacters are also escaped so
        that the literal text is matched rather than interpreted as a regex
        operator.

        Escape order: backslash first, then every other metacharacter, so that
        the escape character itself is not double-escaped.

        Characters escaped: \ / ^ $ . * + ? ( ) [ ] { } |
        """
        # re.escape escapes backslash first, then all metacharacters.
        # We then additionally escape '/' (the JS regex delimiter) which
        # Python's re.escape does not escape.
        escaped = re.escape(value)
        # re.escape uses \x2f on some versions but not on others for '/'
        # – handle both by replacing any literal '/' that survived.
        escaped = escaped.replace("/", "\\/")
        return escaped

    def _generate_locator_expression(
        self,
        element: ElementIR,
        strategy: Any | None = None,
        value: str | None = None,
        element_name: str | None = None,
    ) -> str:
        """Generate a resilient locator expression using multiple fallback strategies.

        LLM-generated IR may have approximate label/placeholder values that don't
        exactly match the live page. Using Playwright's .or() chaining gives us
        robust element resolution even when the primary strategy guesses wrong.

        ``strategy``/``value``/``element_name`` may override the element's own
        values so a specific state of a stateful element can be rendered with its
        own locator.
        """
        strategy = strategy if strategy is not None else element.locator_strategy
        value = value if value is not None else element.locator_value
        element_id = element.id.lower()

        if strategy == LocatorStrategy.ROLE:
            # Parse role format: "button:Login" or just "button"
            if ":" in value:
                role, name = value.split(":", 1)
                # alert/status roles carry LLM-generated names (e.g. "Error Message")
                # that don't exist as accessible names on real pages. Match by role only
                # and use a CSS fallback so the locator is resilient across frameworks.
                if role in ("alert", "status"):
                    return (
                        f"this.page.getByRole('{role}')"
                        f".or(this.page.locator({self._js_string(f'[role=\"{role}\"], [aria-live=\"assertive\"], [aria-live=\"polite\"]')}))"
                        f".first()"
                    )
                # For buttons, try exact name first, then partial (regex)
                return (
                    f"this.page.getByRole('{role}', {{ name: {self._js_string(name)} }})"
                    f".or(this.page.getByRole('{role}', {{ name: /{self._js_regex(name)}/i }}))"
                )
            # A bare role (e.g. getByRole('button')) matches every element of
            # that role on the page — unsafe. Ground the locator in the IR
            # element's own name (accessible-name partial match) whenever the
            # model provided one.
            element_name = (element_name if element_name is not None else element.name or "").strip()
            if element_name and element_name.lower() != value.strip().lower():
                # alert/status without a role:name split — same treatment
                if value.strip() in ("alert", "status"):
                    return (
                        f"this.page.getByRole('{value}')"
                        f".or(this.page.locator({self._js_string(f'[role=\"{value}\"], [aria-live=\"assertive\"], [aria-live=\"polite\"]')}))"
                        f".first()"
                    )
                return f"this.page.getByRole('{value}', {{ name: /{self._js_regex(element_name)}/i }})"
            return f"this.page.getByRole('{value}')"

        elif strategy == LocatorStrategy.LABEL:
            # LLM guesses label text — may not match exactly.
            # Build a resilient chain: getByLabel (partial) → getByPlaceholder (partial)
            # → input[type] heuristic based on element id semantics.
            label_lower = value.lower()
            label_escaped = self._js_regex(label_lower)

            # Checkbox fields: NEVER add text input fallbacks (input[type="text"])
            if any(k in element_id for k in ("checkbox", "remember", "check")) or "checkbox" in label_lower:
                return (
                    f"this.page.getByRole('checkbox', {{ name: /{label_escaped}/i }})"
                    f".or(this.page.getByLabel(/{label_escaped}/i))"
                    f".or(this.page.getByPlaceholder(/{label_escaped}/i))"
                    f".or(this.page.locator('input[type=\"checkbox\"]'))"
                )

            # Password fields: skip getByLabel — it matches both the <input type="password">
            # AND any "Show password" toggle button whose aria-label contains "password".
            # That causes a Playwright strict-mode violation on .fill() and .toBeVisible().
            # Use the CSS input selector first, falling back to placeholder.
            if any(k in element_id for k in ("password", "pwd", "pass")) and not any(k in element_id for k in ("show", "hide", "toggle")):
                return (
                    "this.page.locator('input[type=\"password\"]')"
                    f".or(this.page.getByPlaceholder(/{label_escaped}/i))"
                )
            elif any(k in element_id for k in ("email", "username", "user", "userid")) and not any(k in element_id for k in ("checkbox", "check", "button", "btn")):
                type_fallback = "this.page.locator('input[type=\"text\"], input[type=\"email\"]').first()"
                expr = f"this.page.getByLabel(/{label_escaped}/i)"
                expr += f".or(this.page.getByPlaceholder(/{label_escaped}/i))"
                expr += f".or({type_fallback})"
                return expr
            else:
                expr = f"this.page.getByLabel(/{label_escaped}/i)"
                expr += f".or(this.page.getByPlaceholder(/{label_escaped}/i))"
                return expr

        elif strategy == LocatorStrategy.PLACEHOLDER:
            return f"this.page.getByPlaceholder({self._js_string(value)})"

        elif strategy == LocatorStrategy.TEXT:
            # For password toggle buttons (Show password / Hide password)
            if any(k in element_id for k in ("show_password", "toggle_password", "password_toggle")) or value.strip().lower() in ("show password", "hide password"):
                return "this.page.getByRole('button', { name: /show password|hide password/i }).or(this.page.getByText(/show password|hide password/i))"
            return f"this.page.getByText({self._js_string(value)})"

        elif strategy == LocatorStrategy.TEST_ID:
            return f"this.page.getByTestId({self._js_string(value)})"

        elif strategy == LocatorStrategy.CSS:
            return f"this.page.locator({self._js_string(value)})"

        elif strategy == LocatorStrategy.XPATH:
            return f"this.page.locator({self._js_string(value)})"

        else:
            return f"this.page.locator({self._js_string(value)})"


    def _state_locator_name(self, element_id: str, state_id: str) -> str:
        """Return the page-object property name for a state locator."""
        return f"{self._to_camel_case(element_id)}_{self._to_camel_case(state_id)}"

    def _generate_state_locator_expression(self, element: ElementIR, state: Any) -> str:
        """Render a locator expression for a specific state of a stateful element.

        Uses the state's own locator strategy/value when provided, otherwise
        falls back to the element's primary locator.
        """
        strategy = getattr(state, "locator_strategy", None) or element.locator_strategy
        value = getattr(state, "locator_value", None)
        if value is None or value == "":
            value = element.locator_value
        return self._generate_locator_expression(
            element,
            strategy=strategy,
            value=value,
            element_name=element.name,
        )

    def _resolve_action_locator(self, action: ActionIR, ir: CodeGenerationIR) -> str:
        """Resolve the page-object locator property to use for an action.

        For a stateful element whose action records a ``state_transition``, use
        the locator for the state the element is currently in (``from_state``).
        Otherwise fall back to the element's primary locator.
        """
        page_id = self._find_page_for_element(action.element_id, ir)
        page_var = self._to_camel_case(page_id)
        element_var = self._to_camel_case(action.element_id)

        transition = getattr(action, "state_transition", None)
        from_state = getattr(transition, "from_state", None) if transition is not None else None
        if from_state:
            return f"{page_var}.{self._state_locator_name(action.element_id, from_state)}"
        return f"{page_var}.{element_var}"

    def _find_auth_page(self, ir: CodeGenerationIR) -> PageIR | None:
        """Find the page that carries the login form (evidence-based).

        A page is treated as the login page when it exposes at least one
        username-like and one password-like element — derived from the
        crawler/inventory-backed IR elements, never from hardcoded names.
        """
        for page in ir.pages:
            ids = [e.id.lower() for e in page.elements]
            has_user = any(
                any(k in _id for k in ("user", "email", "login", "name"))
                for _id in ids
            )
            has_pass = any(("pass" in _id or "pwd" in _id) for _id in ids)
            if has_user and has_pass:
                return page
        return None

    def _find_auth_field(
        self,
        page: PageIR | None,
        kind: str,
    ) -> ElementIR | None:
        """Find a username/password field element on a page (evidence-based)."""
        if page is None:
            return None
        for e in page.elements:
            _id = e.id.lower()
            if kind == "user" and any(k in _id for k in ("user", "email", "login", "name")):
                return e
            if kind == "password" and ("pass" in _id or "pwd" in _id):
                return e
        return None

    def _find_submit_element(self, page: PageIR | None) -> ElementIR | None:
        """Find the login/submit button element on a page (evidence-based)."""
        if page is None:
            return None
        for e in page.elements:
            _id = e.id.lower()
            name = (e.name or "").lower()
            value = (e.locator_value or "").lower()
            strategy = getattr(e.locator_strategy, "value", None) or str(e.locator_strategy or "")
            is_button = strategy == "role" and "button" in value
            if is_button or any(
                w in name or w in value for w in ("login", "sign in", "signin", "submit", "log in")
            ):
                return e
        return None

    def _find_landing_page(
        self,
        ir: CodeGenerationIR,
        auth_page: PageIR | None,
    ) -> PageIR | None:
        """Find a post-login landing page carrying a crawler-derived URL."""
        for page in ir.pages:
            if auth_page is not None and page.page_id == auth_page.page_id:
                continue
            if page.requires_auth and page.url_pattern:
                return page
        for page in ir.pages:
            if auth_page is not None and page.page_id == auth_page.page_id:
                continue
            if page.url_pattern:
                return page
        return None

    def _generate_fixtures(self, ir: CodeGenerationIR, output_dir: Path) -> Path:
        """Generate fixtures file."""
        requires_auth = any(page.requires_auth for page in ir.pages)

        code = """import { test as base, Page } from '@playwright/test';

"""

        if requires_auth:
            auth_page = self._find_auth_page(ir)
            username_el = self._find_auth_field(auth_page, "user")
            password_el = self._find_auth_field(auth_page, "password")
            submit_el = self._find_submit_element(auth_page)
            landing_page = self._find_landing_page(ir, auth_page)

            if auth_page is not None and username_el is not None and password_el is not None and submit_el is not None:
                auth_class = self._to_pascal_case(auth_page.page_id)
                auth_file = auth_page.page_id.replace("_", "-")
                auth_var = self._to_camel_case(auth_page.page_id)
                user_field = self._to_camel_case(username_el.id)
                pass_field = self._to_camel_case(password_el.id)
                submit_field = self._to_camel_case(submit_el.id)

                # Post-login wait grounded in the crawler-derived landing
                # pattern (or the login page's own URL when redirected).
                success_pattern = landing_page.url_pattern if landing_page else auth_page.url_pattern
                wait_code = ""
                if success_pattern:
                    escaped = re.escape(success_pattern)
                    wait_code = (
                        f"      await {auth_var}.page.waitForURL(new RegExp('{escaped}'));\n"
                    )

                code += (
                    f"""import {{ {auth_class} }} from '../pages/{auth_file}.page';

/**
 * Authenticated test fixture
 *
 * Logs in through the discovered login page object using the encrypted
 * credentials supplied by the platform (never hardcoded, never logged).
 */
export const test = base.extend<{{ authenticatedPage: Page }}>({{
  authenticatedPage: async ({{ page }}, use) => {{
    const username = process.env.TEST_USERNAME || '';
    const password = process.env.TEST_PASSWORD || '';

    if (username && password) {{
      const {auth_var} = new {auth_class}(page);
      await {auth_var}.goto();
      await {auth_var}.{user_field}.fill(username);
      await {auth_var}.{pass_field}.fill(password);
      await {auth_var}.{submit_field}.click();
{wait_code}    }}
    await use(page);
  }},
}});

export {{ expect }} from '@playwright/test';
"""
                )
            else:
                # Not enough crawler/inventory evidence to build the login
                # steps. Emit a documented, inert fixture so authenticated
                # tests still compile; the platform reports this gap rather
                # than fabricating selectors.
                code += """/**
 * Authenticated test fixture
 *
 * WARNING: the crawler did not capture enough evidence (username/password
 * fields + a submit control) to auto-generate the login steps. Log in
 * manually in a global-setup or extend this fixture with real selectors.
 */
export const test = base.extend<{ authenticatedPage: Page }>({
  authenticatedPage: async ({ page }, use) => {
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
        code = "import { test, expect } from '../fixtures';\n"

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
            code += self._generate_test_case(flow, module, ir)

        code += "});\n"

        file_path = output_dir / "tests" / f"{module.module_id.replace('_', '-')}.spec.ts"
        self._write_and_emit_progress(file_path, code, "test_spec", module.name, module=module.name)
        return file_path

    def _generate_test_case(self, flow: TestFlowIR, module: ModuleIR, ir: CodeGenerationIR) -> str:
        """Generate single test case."""
        tags = " ".join(f"@{tag}" for tag in flow.tags)

        # Modules that require authentication run against the authenticated
        # fixture; everything else uses the plain built-in page fixture.
        page_var = "authenticatedPage" if getattr(module, "requires_auth", False) else "page"

        code = f"""
  test('{flow.name} {tags}', async ({{ {page_var} }}) => {{
"""

        # Initialize page objects used in flow
        page_objects_used = self._find_page_objects_in_flow(flow, ir)

        # Navigation: every test must establish the target page's state before
        # interacting with it. If the flow did not already declare an explicit
        # navigation step, navigate through the flow's entry page object, whose
        # ``goto()`` uses the crawler-discovered ``url_pattern`` — never a
        # hardcoded application URL.
        entry_page = self._find_flow_entry_page(flow, module, ir)
        has_explicit_navigation = any(s.navigation is not None for s in (flow.steps or []))
        if entry_page is not None:
            page_objects_used.add(entry_page.page_id)

        for page_id in page_objects_used:
            class_name = self._to_pascal_case(page_id)
            var_name = self._to_camel_case(page_id)
            code += f"    const {var_name} = new {class_name}({page_var});\n"

        code += "\n"

        if entry_page is not None and not has_explicit_navigation:
            entry_var = self._to_camel_case(entry_page.page_id)
            code += f"    await {entry_var}.goto();\n\n"

        # Generate steps
        for step in sorted(flow.steps, key=lambda s: s.step_order):
            code += self._generate_step_code(step, ir, page_var=page_var)

        code += "  });\n"

        return code

    def _find_flow_entry_page(
        self,
        flow: TestFlowIR,
        module: ModuleIR,
        ir: CodeGenerationIR,
    ) -> PageIR | None:
        """Resolve the page a flow should navigate to before its first action.

        Deterministic and evidence-based: prefers the page that owns the first
        element referenced by the flow, falling back to the module's first page
        that carries a crawler-derived ``url_pattern``. Never invents a URL.
        """
        for step in sorted(flow.steps, key=lambda s: s.step_order):
            for action in step.actions or []:
                if action.element_id:
                    page = self._find_page_object_for_element(action.element_id, ir)
                    if page is not None and page.url_pattern:
                        return page
            for assertion in step.assertions or []:
                if assertion.element_id:
                    page = self._find_page_object_for_element(assertion.element_id, ir)
                    if page is not None and page.url_pattern:
                        return page

        for page_id in module.pages or []:
            page = next((p for p in ir.pages if p.page_id == page_id), None)
            if page is not None and page.url_pattern:
                return page
        return None

    def _find_page_object_for_element(self, element_id: str, ir: CodeGenerationIR) -> PageIR | None:
        """Return the PageIR owning an element, or None."""
        page_id = self._find_page_for_element(element_id, ir)
        if page_id:
            return next((p for p in ir.pages if p.page_id == page_id), None)
        return None

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

    def _generate_step_code(
        self,
        step: "FlowStepIR",
        ir: CodeGenerationIR,
        page_var: str = "page",
    ) -> str:
        """Generate code for a flow step."""
        code = f"    // Step {step.step_order}: {step.description}\n"

        # Navigation
        if step.navigation:
            target = step.navigation.target
            if target.startswith('/') or target.startswith('http://') or target.startswith('https://'):
                code += f"    await {page_var}.goto('{target}');\n"
            else:
                # Navigation to a page object
                page_var_name = self._to_camel_case(target)
                code += f"    await {page_var_name}.goto();\n"

        # Actions
        for action in step.actions:
            code += self._generate_action_code(action, ir)

        # Assertions
        for assertion in step.assertions:
            code += self._generate_assertion_code(assertion, ir, page_var=page_var)

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
            locator = self._resolve_action_locator(action, ir)
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

        elif action_type == ActionType.FOCUS:
            return f"    await {locator}.focus();\n"

        elif action_type == ActionType.PRESS:
            raw_val = action.value or "Enter"
            if raw_val.startswith("$"):
                raw_val = raw_val[1:]
            key = raw_val if raw_val else "Enter"
            return f"    await {locator}.press('{key}');\n"

        else:
            return f"    // TODO: Action {action_type} on {locator}\n"

    def _generate_assertion_code(
        self,
        assertion: AssertionIR,
        ir: CodeGenerationIR,
        page_var: str = "page",
    ) -> str:
        """Generate code for an assertion."""
        assertion_type = assertion.assertion_type

        # URL/Title assertions don't need element. No fabricated values: skip
        # assertions whose expected value is absent/empty instead of emitting a
        # made-up expectation that cannot be grounded in crawler evidence.
        if assertion_type == AssertionType.HAS_URL:
            if not assertion.expected_value:
                return f"    // TODO: {assertion.description} (no expected URL evidence)\n"
            return f"    await expect({page_var}).toHaveURL('{assertion.expected_value}');\n"

        if assertion_type == AssertionType.HAS_TITLE:
            if not assertion.expected_value:
                return f"    // TODO: {assertion.description} (no expected title evidence)\n"
            return f"    await expect({page_var}).toHaveTitle('{assertion.expected_value}');\n"

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
            val = assertion.expected_value or ""
            if isinstance(val, str) and val.startswith("$"):
                env_var = val[1:]
                return f"    await expect({locator}).toHaveText(process.env.{env_var} || '');\n"
            return f"    await expect({locator}).toHaveText('{val}');\n"
        
        elif assertion_type == AssertionType.HAS_VALUE:
            val = assertion.expected_value or ""
            if isinstance(val, str) and val.startswith("$"):
                env_var = val[1:]
                return f"    await expect({locator}).toHaveValue(process.env.{env_var} || '');\n"
            return f"    await expect({locator}).toHaveValue('{val}');\n"
        
        elif assertion_type == AssertionType.CONTAINS_TEXT:
            val = assertion.expected_value or ""
            if isinstance(val, str) and val.startswith("$"):
                env_var = val[1:]
                return f"    await expect({locator}).toContainText(process.env.{env_var} || '');\n"
            return f"    await expect({locator}).toContainText('{val}');\n"

        elif assertion_type == AssertionType.HAS_ATTRIBUTE or getattr(assertion_type, "value", None) == "toHaveAttribute":
            val = assertion.expected_value
            if isinstance(val, dict):
                attr_name = val.get("name", "type")
                attr_val = val.get("value", "")
            elif isinstance(val, (list, tuple)) and len(val) == 2:
                attr_name, attr_val = val
            elif isinstance(val, str) and "=" in val:
                attr_name, attr_val = val.split("=", 1)
            else:
                attr_name, attr_val = "type", str(val or "")
            return f"    await expect({locator}).toHaveAttribute('{attr_name}', '{attr_val}');\n"
        
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
- Retries: 2 (CI=true), 0 (local or CI=false)

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

    def _to_words(self, text: str) -> list[str]:
        """Split an identifier into words on separators and case boundaries.

        Handles snake_case, kebab-case AND already-camelCased ids so a field
        like ``loginButton`` stays ``loginButton`` instead of ``loginbutton``.
        """
        return [w for w in re.split(r"[_\-]+|(?<=[a-z0-9])(?=[A-Z])", text or "") if w]

    def _to_pascal_case(self, text: str) -> str:
        """Convert text to PascalCase."""
        return "".join(word.capitalize() for word in self._to_words(text))

    def _to_camel_case(self, text: str) -> str:
        """Convert text to camelCase."""
        words = self._to_words(text)
        return words[0].lower() + "".join(word.capitalize() for word in words[1:])
