"""
Instruction Builder for IR Generation Prompts

Builds instructions for LLM to generate framework-independent IR.
"""

from app.logging import LoggerMixin


class InstructionBuilder(LoggerMixin):
    """
    Builds instruction section of prompts.
    
    Single Responsibility: Generate instructions for IR creation.
    """

    def __init__(self) -> None:
        """Initialize instruction builder."""
        super().__init__()

    def build_ir_generation_instructions(self) -> str:
        """
        Build instructions for generating IR from test plans.

        Returns:
            Formatted instruction text
        """
        return """# Intermediate Representation (IR) Generation

You are an expert test automation architect. Your task is to convert approved test scenarios into a **framework-independent Intermediate Representation (IR)**.

## Critical Requirements

1. **Framework Independence**: The IR must NOT contain any Playwright, Selenium, or framework-specific code
2. **Complete Representation**: Include all pages, elements, flows, actions, and assertions
3. **Structured JSON**: Generate valid, well-structured JSON matching the IR schema EXACTLY
4. **Locator Strategy**: Prefer semantic locators (role, label, placeholder) over CSS/XPath
5. **Modularity**: Group tests by logical modules
6. **Dependencies**: Identify and document flow dependencies with proper structure
7. **Reusability**: Extract common elements and flows

## IR Structure - COMPLETE SCHEMA

You MUST generate JSON with ALL these top-level sections. Do NOT omit any required field:

```json
{
  "metadata": {
    "generator": "IRGenerationAgent",
    "generated_at": "2024-01-01T00:00:00Z",
    "ir_version": "1.0.0",
    "source_test_plan": "/path/to/test-plan.json",
    "model_used": "gpt-4",
    "total_pages": 0,
    "total_elements": 0,
    "total_flows": 0,
    "total_modules": 0,
    "validation_status": "pending"
  },
  "environment": {
    "base_url": "http://localhost:3000",
    "auth_required": false,
    "auth_type": null,
    "variables": {},
    "timeouts": {},
    "browsers": ["chromium"]
  },
  "pages": [ /* page definitions */ ],
  "modules": [ /* test modules */ ],
  "dependencies": [ /* inter-component dependencies */ ],
  "common_elements": [],
  "common_flows": [],
  "retry_config": {},
  "parallel_config": {}
}
```

## CRITICAL: Metadata Section

You MUST include the metadata section with these REQUIRED fields:

- **generator**: MUST be the string "IRGenerationAgent"
- **generated_at**: ISO 8601 timestamp (e.g., "2024-01-01T12:00:00Z")
- **ir_version**: MUST be "1.0.0"
- **source_test_plan**: Path or identifier of source test plan (string or null)
- **model_used**: LLM model name (e.g., "gpt-4", "gpt-4o", "deepseek")
- **total_pages**: Number of pages (integer)
- **total_elements**: Total element count across all pages (integer)
- **total_flows**: Total number of flows (integer)
- **total_modules**: Number of modules (integer)
- **validation_status**: MUST be "pending" initially

## CRITICAL: Environment Section

You MUST include the environment section with these REQUIRED fields:

- **base_url**: The application base URL (e.g., "http://localhost:3000")
- **auth_required**: boolean (true if authentication needed)
- **auth_type**: string or null (e.g., "basic", "oauth", null)
- **variables**: object/dict (can be empty {})
- **timeouts**: object/dict (can be empty {})
- **browsers**: array of strings (e.g., ["chromium"] or ["chromium", "firefox"])

## CRITICAL: Dependencies Section

For each dependency between components, you MUST include ALL required fields:

```json
{
  "source_id": "flow-login",
  "target_id": "flow-dashboard",
  "dependency_type": "prerequisite",
  "description": "Dashboard flow requires successful login"
}
```

**REQUIRED fields per dependency:**
- **source_id**: ID of the source component (string, never null)
- **target_id**: ID of the target component (string, never null)  
- **dependency_type**: Type of dependency (string, never null)
  - Valid types: "prerequisite", "data_dependency", "page_dependency", "module_dependency"
- **description**: Human-readable description (string or null)

## Page Definition

For each page, define:
- **page_id**: Unique identifier (required, never null)
- **name**: Page name (required, never null)
- **url_pattern**: URL pattern or path (string or null)
- **description**: Page description (required, never null)
- **elements**: Array of UI elements (can be empty [], never null)
- **page_load_selector**: Selector to wait for (string or null)
- **requires_auth**: boolean (default false)

## Element Definition

For each element, you MUST include ALL required fields directly. Do NOT use `element_ref` as a field name.

**REQUIRED fields per element:**
- **id**: Unique element ID (e.g., "login-heading", "username-input") - required, never null
- **name**: Semantic display name (e.g., "Login Heading", "Username Input") - required, never null
- **locator_strategy**: MUST be one of: "role", "label", "placeholder", "text", "testId", "css", "xpath" - required, never null
- **locator_value**: The actual locator value (e.g., "heading:Login") - required, never null
- **description**: What the element is/does (string or null)
- **fallback_locators**: Array of objects (can be empty [], never null)
- **wait_for_visible**: boolean (default true)
- **timeout**: integer or null

## Flow Definition

For each test flow:
- **flow_id**: Unique identifier (required, never null)
- **name**: Flow name (required, never null)
- **description**: What the flow tests (required, never null)
- **tags**: Array of strings (can be empty [], never null)
- **steps**: Array of steps (required, never null or empty)
- **preconditions**: Array of strings (can be empty [], never null)
- **postconditions**: Array of strings (can be empty [], never null)
- **depends_on**: Array of flow IDs (can be empty [], never null)
- **timeout**: integer or null

## Action Types

You MUST use ONLY these exact action_type values. Do NOT use "custom" or any other value:
- click, fill, select, check, uncheck
- hover, focus, press, upload, clear
- doubleClick, rightClick

## Assertion Types

You MUST use ONLY these exact assertion_type values. Do NOT use "custom" or any other value:
- toBeVisible, toBeHidden, toBeEnabled, toBeDisabled
- toBeChecked, toBeUnchecked
- toHaveText, toHaveValue, toHaveURL, toHaveTitle
- toHaveCount, toContainText

## Locator Priority

1. **role** - Button, Link, Textbox, etc.
2. **label** - Form field labels
3. **placeholder** - Input placeholders
4. **text** - Visible text
5. **testId** - data-testid attributes
6. **css** - CSS selectors (last resort)
7. **xpath** - XPath (avoid if possible)

## COMPLETE Example IR

Here is a COMPLETE example showing ALL required sections and fields:

```json
{
  "metadata": {
    "generator": "IRGenerationAgent",
    "generated_at": "2024-01-15T10:30:00Z",
    "ir_version": "1.0.0",
    "source_test_plan": "/workspace/contracts/approved-test-plan.json",
    "model_used": "gpt-4",
    "total_pages": 2,
    "total_elements": 5,
    "total_flows": 2,
    "total_modules": 1,
    "validation_status": "pending"
  },
  "environment": {
    "base_url": "http://localhost:3000",
    "auth_required": true,
    "auth_type": "basic",
    "variables": {},
    "timeouts": {
      "default": 30000,
      "navigation": 60000
    },
    "browsers": ["chromium"]
  },
  "pages": [
    {
      "page_id": "login-page",
      "name": "Login Page",
      "url_pattern": "/login",
      "description": "User login page",
      "elements": [
        {
          "id": "username-input",
          "name": "Username Input",
          "locator_strategy": "label",
          "locator_value": "Username",
          "description": "Username input field",
          "fallback_locators": [],
          "wait_for_visible": true,
          "timeout": null
        },
        {
          "id": "password-input",
          "name": "Password Input",
          "locator_strategy": "label",
          "locator_value": "Password",
          "description": "Password input field",
          "fallback_locators": [],
          "wait_for_visible": true,
          "timeout": null
        },
        {
          "id": "login-button",
          "name": "Login Button",
          "locator_strategy": "role",
          "locator_value": "button:Login",
          "description": "Submit login button",
          "fallback_locators": [],
          "wait_for_visible": true,
          "timeout": null
        }
      ],
      "page_load_selector": null,
      "requires_auth": false
    },
    {
      "page_id": "dashboard-page",
      "name": "Dashboard Page",
      "url_pattern": "/dashboard",
      "description": "Main dashboard after login",
      "elements": [
        {
          "id": "welcome-message",
          "name": "Welcome Message",
          "locator_strategy": "role",
          "locator_value": "heading:Welcome",
          "description": "Welcome heading",
          "fallback_locators": [],
          "wait_for_visible": true,
          "timeout": null
        }
      ],
      "page_load_selector": null,
      "requires_auth": true
    }
  ],
  "modules": [
    {
      "module_id": "authentication",
      "name": "Authentication Module",
      "description": "Tests for user authentication flows",
      "pages": ["login-page", "dashboard-page"],
      "flows": [
        {
          "flow_id": "login-success",
          "name": "Successful Login",
          "description": "User can log in with valid credentials",
          "tags": ["auth", "smoke"],
          "steps": [
            {
              "step_order": 1,
              "description": "Navigate to login page",
              "navigation": {
                "target": "/login",
                "wait_for_load": true,
                "wait_for_selector": null,
                "description": "Go to login page"
              },
              "actions": [],
              "assertions": [
                {
                  "assertion_type": "toBeVisible",
                  "element_id": "login-button",
                  "expected_value": null,
                  "description": "Login button should be visible",
                  "timeout": null,
                  "negated": false
                }
              ],
              "wait_for_condition": null
            },
            {
              "step_order": 2,
              "description": "Enter credentials and login",
              "navigation": null,
              "actions": [
                {
                  "action_type": "fill",
                  "element_id": "username-input",
                  "value": "testuser",
                  "description": "Fill username",
                  "wait_before": null,
                  "wait_after": null
                },
                {
                  "action_type": "fill",
                  "element_id": "password-input",
                  "value": "password123",
                  "description": "Fill password",
                  "wait_before": null,
                  "wait_after": null
                },
                {
                  "action_type": "click",
                  "element_id": "login-button",
                  "value": null,
                  "description": "Click login button",
                  "wait_before": null,
                  "wait_after": 1000
                }
              ],
              "assertions": [
                {
                  "assertion_type": "toHaveURL",
                  "element_id": null,
                  "expected_value": "/dashboard",
                  "description": "Should navigate to dashboard",
                  "timeout": null,
                  "negated": false
                }
              ],
              "wait_for_condition": null
            }
          ],
          "preconditions": [],
          "postconditions": ["User is logged in", "Dashboard is visible"],
          "depends_on": [],
          "timeout": null,
          "priority": "high"
        },
        {
          "flow_id": "dashboard-access",
          "name": "Access Dashboard",
          "description": "Verify dashboard is accessible after login",
          "tags": ["auth", "smoke"],
          "steps": [
            {
              "step_order": 1,
              "description": "Verify welcome message appears",
              "navigation": null,
              "actions": [],
              "assertions": [
                {
                  "assertion_type": "toBeVisible",
                  "element_id": "welcome-message",
                  "expected_value": null,
                  "description": "Welcome message should be visible",
                  "timeout": null,
                  "negated": false
                }
              ],
              "wait_for_condition": null
            }
          ],
          "preconditions": ["User must be logged in"],
          "postconditions": ["Dashboard loaded successfully"],
          "depends_on": ["login-success"],
          "timeout": null,
          "priority": "medium"
        }
      ],
      "tags": ["authentication", "critical"],
      "priority": "high",
      "requires_auth": false
    }
  ],
  "dependencies": [
    {
      "source_id": "login-success",
      "target_id": "dashboard-access",
      "dependency_type": "prerequisite",
      "description": "Dashboard access requires successful login"
    }
  ],
  "common_elements": [],
  "common_flows": [],
  "retry_config": {},
  "parallel_config": {}
}
```

## Instructions

1. Analyze each approved scenario
2. Identify all pages and UI elements
3. Define clear locator strategies (prefer semantic)
4. Map test steps to flow steps
5. Convert assertions to IR assertion types
6. Group flows by module
7. Identify dependencies between flows (use proper schema!)
8. Extract reusable elements/flows
9. Generate complete, valid JSON IR with ALL required fields

## CRITICAL Reminders
- MUST include metadata section with generator="IRGenerationAgent"
- MUST include environment section with base_url
- Dependencies MUST have source_id, target_id, and dependency_type
- Elements MUST have `id`, `name`, `locator_strategy`, `locator_value` — never use `element_ref`
- Actions MUST use one of the listed action_type values — never use `custom`
- Assertions MUST use one of the listed assertion_type values — never use `custom`
- ALL arrays must be present (can be empty [], never null)
- Return ONLY valid JSON, no markdown, no code fences, no explanations

## CRITICAL: Environment Variables for Test Data

When tests need dynamic data (credentials, IDs, passwords), declare them in `environment.variables`:

```json
"environment": {
  "base_url": "http://localhost:3000",
  "variables": {
    "VALID_ID": "test_user",
    "VALID_PASSWORD": "password123",
    "MAX_LENGTH_ID": "a_fifty_char_user_id_example_padded_to_50chars",
    "MAX_LENGTH_PASSWORD": "a_very_long_128_char_password_placeholder",
    "MIN_ID": "u",
    "MIN_PASSWORD": "pass1234",
    "DISABLED_ID": "locked_user",
    "DISABLED_PASSWORD": "any_pass"
  }
}
```

For `fill` actions that use environment variables, set the `value` field using **dollar-prefix format**:

```json
{ "action_type": "fill", "element_id": "id-input", "value": "$VALID_ID" }
```

**NEVER use curly-brace placeholders like `{valid_id}` or `${valid_id}` — these are INVALID.**
**ALWAYS use uppercase SNAKE_CASE for env var names: `$VALID_ID`, `$VALID_PASSWORD`.**

Generate the complete IR now."""

    def build_validation_instructions(self) -> str:
        """
        Build instructions for IR validation.

        Returns:
            Validation instruction text
        """
        return """## IR Validation Requirements

Ensure the generated IR:

1. **Valid JSON**: Proper JSON syntax
2. **Complete**: All scenarios covered
3. **Unique IDs**: No duplicate page_id, element_id, flow_id
4. **Valid Locators**: Proper strategy and value pairs
5. **Complete Flows**: All steps have actions or assertions
6. **Valid References**: element_id references exist
7. **No Circular Deps**: No circular flow dependencies
8. **Semantic Locators**: Minimize CSS/XPath usage"""

    def build_quality_guidelines(self) -> str:
        """
        Build code quality guidelines for IR.

        Returns:
            Quality guidelines text
        """
        return """## Quality Guidelines

- **Descriptive Names**: Use clear, descriptive names for pages, elements, flows
- **Consistent Naming**: Follow consistent naming conventions
- **Proper Grouping**: Group related flows in same module
- **Minimal Duplication**: Reuse elements and flows where possible
- **Clear Dependencies**: Document why flows depend on each other
- **Explicit Assertions**: Include meaningful assertions in every flow
- **Error Handling**: Consider error scenarios in flows"""
