"""
Prompt Builder for Code Generation

Constructs comprehensive LLM prompts from approved test plans.
"""

from typing import Any

from app.logging import LoggerMixin
from app.schemas.review import ApprovedTestPlan
from app.schemas.test_plan import Priority, Risk, TestCategory


class PromptBuilder(LoggerMixin):
    """
    Builds structured LLM prompts for Playwright code generation.
    
    Responsibilities:
    - Load approved test plan
    - Extract relevant scenario details
    - Format test steps, assertions, locators
    - Build comprehensive generation prompt
    - Exclude internal metadata
    - Include business rules and flows
    """

    def __init__(self) -> None:
        """Initialize prompt builder."""
        super().__init__()

    def build_generation_prompt(
        self,
        approved_plan: ApprovedTestPlan,
        base_url: str = "http://localhost:3000"
    ) -> str:
        """
        Build complete LLM prompt for code generation.

        Args:
            approved_plan: Approved test plan
            base_url: Application base URL

        Returns:
            Formatted prompt string
        """
        self.logger.info("building_generation_prompt")

        prompt_parts = [
            self._build_header(),
            self._build_requirements(),
            self._build_application_context(approved_plan, base_url),
            self._build_test_scenarios(approved_plan),
            self._build_quality_rules(),
            self._build_output_structure(),
            self._build_examples(),
            self._build_footer(),
        ]

        prompt = "\n\n".join(part for part in prompt_parts if part)

        self.logger.info(
            "generation_prompt_built",
            prompt_length=len(prompt),
            scenario_count=len(approved_plan.test_scenarios)
        )

        return prompt

    def _build_header(self) -> str:
        """Build prompt header."""
        return """# Playwright Test Automation Code Generation

You are an expert QA automation engineer specializing in Playwright with TypeScript.

Your task is to generate a complete, production-ready Playwright test automation project.

Generate clean, maintainable, type-safe TypeScript code following best practices."""

    def _build_requirements(self) -> str:
        """Build requirements section."""
        return """## Requirements

- Use TypeScript with strict typing
- Implement Page Object Model (POM) pattern
- Use Playwright's modern Locator API
- Write async/await code throughout
- NO hardcoded waits (no page.waitForTimeout)
- Use proper assertions with expect()
- Create reusable fixtures
- Generate utility functions
- Include comprehensive test data
- Add clear comments and documentation"""

    def _build_application_context(
        self,
        approved_plan: ApprovedTestPlan,
        base_url: str
    ) -> str:
        """Build application context section."""
        data = approved_plan.test_plan_data if isinstance(approved_plan.test_plan_data, dict) else {}
        app_summary = data.get("application_summary", {}) or {}
        assumptions = data.get("test_assumptions") or data.get("assumptions") or {}

        context = f"""## Application Context

**Base URL:** `{base_url}`

**Application Summary:**
- Pages: {app_summary.get('total_pages', 0)}
- Forms: {app_summary.get('total_forms', 0)}
- APIs: {app_summary.get('total_apis', 0)}
- Authentication Required: {app_summary.get('authentication_required', False)}
- Auth Method: {app_summary.get('auth_method', 'None')}
"""

        if isinstance(assumptions, dict) and assumptions.get("assumptions"):
            context += "\n**Test Assumptions:**\n"
            for assumption in assumptions.get("assumptions", []):
                context += f"- {assumption}\n"

        if isinstance(assumptions, dict) and assumptions.get("constraints"):
            context += "\n**Constraints:**\n"
            for constraint in assumptions.get("constraints", []):
                context += f"- {constraint}\n"

        return context

    def _build_test_scenarios(self, approved_plan: ApprovedTestPlan) -> str:
        """Build test scenarios section."""
        scenarios = approved_plan.test_scenarios

        if not scenarios:
            return ""

        section = "## Approved Test Scenarios\n\n"
        section += f"Generate Playwright tests for the following {len(scenarios)} approved scenarios:\n\n"

        for idx, scenario in enumerate(scenarios, 1):
            if isinstance(scenario, dict):
                meta = scenario.get("metadata", {}) or {}
            else:
                meta = getattr(scenario, "metadata", None)

            if isinstance(meta, dict):
                title = meta.get("title", "")
                sc_id = meta.get("id", "")
                desc = meta.get("description", "")
                module = meta.get("module", "")
                priority = meta.get("priority", "medium")
                if hasattr(priority, "value"): priority = priority.value
                category = meta.get("category", "functional")
                if hasattr(category, "value"): category = category.value
                risk = meta.get("risk_level", "medium")
                if hasattr(risk, "value"): risk = risk.value
                target_page = meta.get("target_page")
                preconditions = meta.get("preconditions", [])
                test_steps = meta.get("test_steps", [])
                expected_result = meta.get("expected_result", "")
                test_data = meta.get("required_test_data", [])
                tags = meta.get("tags", [])
                deps = meta.get("dependencies", [])
            elif meta:
                title = meta.title
                sc_id = meta.id
                desc = meta.description
                module = meta.module
                priority = meta.priority.value if hasattr(meta.priority, "value") else meta.priority
                category = meta.category.value if hasattr(meta.category, "value") else meta.category
                risk = meta.risk_level.value if hasattr(meta.risk_level, "value") else meta.risk_level
                target_page = meta.target_page
                preconditions = meta.preconditions
                test_steps = meta.test_steps
                expected_result = meta.expected_result
                test_data = meta.required_test_data
                tags = meta.tags
                deps = meta.dependencies
            else:
                continue

            section += f"### Scenario {idx}: {title}\n\n"
            section += f"**ID:** `{sc_id}`\n"
            section += f"**Description:** {desc}\n"
            section += f"**Module:** {module}\n"
            section += f"**Priority:** {priority}\n"
            section += f"**Category:** {category}\n"
            section += f"**Risk Level:** {risk}\n"

            if target_page:
                section += f"**Target Page:** `{target_page}`\n"

            if preconditions:
                section += "\n**Preconditions:**\n"
                for precondition in preconditions:
                    section += f"- {precondition}\n"

            if test_steps:
                section += "\n**Test Steps:**\n"
                for step_idx, step in enumerate(test_steps, 1):
                    section += f"{step_idx}. {step}\n"

            section += f"\n**Expected Result:** {expected_result}\n"

            if test_data:
                section += "\n**Required Test Data:**\n"
                for data in test_data:
                    section += f"- {data}\n"

            if tags:
                section += f"\n**Tags:** {', '.join(tags)}\n"

            if deps:
                section += f"\n**Dependencies:** {', '.join(deps)}\n"

            section += "\n---\n\n"

        return section

    def _build_quality_rules(self) -> str:
        """Build code quality rules."""
        return """## Code Quality Rules

**TypeScript:**
- Use strict mode
- Define interfaces for all data structures
- Use proper types (avoid `any`)
- Export types for reuse

**Page Objects:**
- One class per page
- Locators as private readonly properties
- Public methods for actions
- Public methods for assertions
- Methods return Promise<void> or Promise<boolean>
- Use descriptive method names

**Tests:**
- One test file per module
- Use `test.describe()` for grouping
- Use `test()` for individual scenarios
- Follow AAA pattern (Arrange, Act, Assert)
- Clear test names describing behavior
- Use `test.beforeEach()` for setup
- Use `test.afterEach()` for cleanup

**Locators:**
- Prefer `getByRole()`, `getByLabel()`, `getByPlaceholder()`
- Use `getByTestId()` for dynamic elements
- Avoid CSS selectors and XPath unless necessary
- Make locators resilient to changes

**Assertions:**
- Use `expect()` from '@playwright/test'
- Use specific matchers (`toBeVisible()`, `toHaveText()`, `toBeEnabled()`)
- Add meaningful assertion messages
- Verify expected state before interactions

**Utilities:**
- Create helper functions for common operations
- Add retry logic for flaky operations
- Create wait utilities with timeout handling
- Add logging utilities

**Fixtures:**
- Create custom fixtures for common setup
- Use fixture composition
- Implement authentication fixtures
- Provide test data fixtures"""

    def _build_output_structure(self) -> str:
        """Build expected output structure."""
        return """## Output Structure

Generate a complete Playwright project with this structure:

```
playwright/
├── package.json                 # Dependencies and scripts
├── playwright.config.ts         # Playwright configuration
├── tsconfig.json               # TypeScript configuration
├── .env.example                # Environment variables template
├── README.md                   # Setup and usage instructions
├── pages/                      # Page Object Model
│   ├── BasePage.ts            # Base page class
│   ├── LoginPage.ts           # Login page (if needed)
│   └── [Module]Page.ts        # One page per module
├── tests/                      # Test specifications
│   └── [module].spec.ts       # One file per module
├── fixtures/                   # Custom fixtures
│   ├── base.fixture.ts        # Base fixture setup
│   └── auth.fixture.ts        # Authentication (if needed)
├── utils/                      # Utility functions
│   ├── waits.ts               # Wait utilities
│   ├── helpers.ts             # Common helpers
│   ├── logger.ts              # Logging utility
│   └── constants.ts           # Shared constants
├── data/                       # Test data
│   ├── test-data.json         # Test data sets
│   └── auth-data.json         # Auth credentials (if needed)
├── reports/                    # Test reports (empty)
├── screenshots/                # Screenshots (empty)
└── traces/                     # Traces (empty)
```

**Key Files to Generate:**

1. **package.json** - Include @playwright/test and necessary dependencies
2. **playwright.config.ts** - Configure browsers, retries, reporters, screenshots
3. **tsconfig.json** - TypeScript strict configuration
4. **.env.example** - Environment variables (BASE_URL, credentials if needed)
5. **README.md** - Installation and execution instructions
6. **pages/*.ts** - Page objects for each module
7. **tests/*.spec.ts** - Test files for each module
8. **fixtures/base.fixture.ts** - Base fixtures
9. **utils/*.ts** - Utility functions"""

    def _build_examples(self) -> str:
        """Build code examples."""
        return """## Code Examples

### Page Object Example

```typescript
import { Page, Locator } from '@playwright/test';

export class LoginPage {
  private readonly page: Page;
  private readonly usernameInput: Locator;
  private readonly passwordInput: Locator;
  private readonly loginButton: Locator;
  private readonly errorMessage: Locator;

  constructor(page: Page) {
    this.page = page;
    this.usernameInput = page.getByLabel('Username');
    this.passwordInput = page.getByLabel('Password');
    this.loginButton = page.getByRole('button', { name: 'Log in' });
    this.errorMessage = page.getByRole('alert');
  }

  async goto(): Promise<void> {
    await this.page.goto('/login');
  }

  async login(username: string, password: string): Promise<void> {
    await this.usernameInput.fill(username);
    await this.passwordInput.fill(password);
    await this.loginButton.click();
  }

  async isErrorVisible(): Promise<boolean> {
    return await this.errorMessage.isVisible();
  }
}
```

### Test Example

```typescript
import { test, expect } from '@playwright/test';
import { LoginPage } from '../pages/LoginPage';

test.describe('Login Functionality', () => {
  let loginPage: LoginPage;

  test.beforeEach(async ({ page }) => {
    loginPage = new LoginPage(page);
    await loginPage.goto();
  });

  test('should login with valid credentials', async ({ page }) => {
    // Arrange
    const username = 'testuser';
    const password = 'password123';

    // Act
    await loginPage.login(username, password);

    // Assert
    await expect(page).toHaveURL(/\\/dashboard/);
  });

  test('should show error with invalid credentials', async () => {
    // Arrange
    const username = 'invalid';
    const password = 'wrong';

    // Act
    await loginPage.login(username, password);

    // Assert
    const errorVisible = await loginPage.isErrorVisible();
    expect(errorVisible).toBe(true);
  });
});
```"""

    def _build_footer(self) -> str:
        """Build prompt footer."""
        return """## Generation Instructions

1. Generate ALL files listed in the output structure
2. Implement EVERY approved scenario as test cases
3. Create page objects for all modules
4. Use TypeScript with strict typing
5. Follow the Page Object Model pattern
6. Use Playwright's modern Locator API
7. Include proper error handling
8. Add clear comments
9. Make code production-ready and immediately runnable
10. Ensure all imports are correct

Generate the complete project now."""

    def build_file_generation_prompt(
        self,
        file_type: str,
        context: dict[str, Any]
    ) -> str:
        """
        Build prompt for generating specific file types.

        Args:
            file_type: Type of file to generate (page_object, test, config, etc.)
            context: Context data for generation

        Returns:
            Formatted prompt for specific file
        """
        self.logger.info("building_file_prompt", file_type=file_type)

        if file_type == "page_object":
            return self._build_page_object_prompt(context)
        elif file_type == "test":
            return self._build_test_prompt(context)
        elif file_type == "config":
            return self._build_config_prompt(context)
        elif file_type == "fixture":
            return self._build_fixture_prompt(context)
        else:
            return self._build_generic_prompt(file_type, context)

    def _build_page_object_prompt(self, context: dict[str, Any]) -> str:
        """Build page object generation prompt."""
        module_name = context.get("module_name", "Unknown")
        scenarios = context.get("scenarios", [])

        prompt = f"""Generate a TypeScript Page Object for the {module_name} module.

**Module:** {module_name}

**Scenarios to support:**
"""
        for scenario in scenarios:
            prompt += f"- {scenario.get('title', 'Unknown')}\n"

        prompt += """
**Requirements:**
- Use Playwright's Locator API
- Define locators as private readonly properties
- Implement public action methods
- Implement public assertion methods
- Use strict TypeScript types
- Add JSDoc comments

Return only the TypeScript code for the page object class.
"""
        return prompt

    def _build_test_prompt(self, context: dict[str, Any]) -> str:
        """Build test file generation prompt."""
        module_name = context.get("module_name", "Unknown")
        scenarios = context.get("scenarios", [])

        prompt = f"""Generate Playwright test specifications for the {module_name} module.

**Module:** {module_name}

**Test Scenarios:**
"""
        for idx, scenario in enumerate(scenarios, 1):
            prompt += f"\n{idx}. {scenario.get('title', 'Unknown')}\n"
            prompt += f"   Priority: {scenario.get('priority', 'medium')}\n"
            prompt += f"   Steps: {', '.join(scenario.get('steps', []))}\n"

        prompt += """
**Requirements:**
- Import page objects
- Use test.describe() for grouping
- Use test() for each scenario
- Follow AAA pattern
- Add meaningful assertions
- Use proper TypeScript types

Return only the TypeScript test code.
"""
        return prompt

    def _build_config_prompt(self, context: dict[str, Any]) -> str:
        """Build configuration file prompt."""
        return """Generate a production-ready playwright.config.ts file.

**Requirements:**
- Configure multiple browsers (chromium, firefox, webkit)
- Set up retries (2 retries)
- Configure reporters (html, json, junit)
- Enable screenshots on failure
- Enable video on first retry
- Enable trace on first retry
- Set reasonable timeouts
- Configure base URL from environment
- Set up parallel execution

Return only the TypeScript configuration code.
"""

    def _build_fixture_prompt(self, context: dict[str, Any]) -> str:
        """Build fixture generation prompt."""
        return """Generate a base.fixture.ts file with custom Playwright fixtures.

**Requirements:**
- Extend base test from @playwright/test
- Create custom fixtures for common setup
- Add authentication fixture if needed
- Implement test data fixtures
- Use TypeScript strict types

Return only the TypeScript fixture code.
"""

    def _build_generic_prompt(self, file_type: str, context: dict[str, Any]) -> str:
        """Build generic file prompt."""
        return f"""Generate a {file_type} file for the Playwright project.

**Context:**
{context}

Return only the code content.
"""
