"""
Instruction Builder for IR Generation Prompts

Builds instructions for LLM to generate framework-independent IR.
Schema details are rendered from the Pydantic models, never hardcoded.
"""

from app.core.ir.schema_renderer import SchemaRenderer
from app.logging import LoggerMixin
from app.schemas.ir import CodeGenerationIR


class InstructionBuilder(LoggerMixin):
    """
    Builds instruction section of prompts.

    Single Responsibility: Generate instructions for IR creation.
    """

    def __init__(self, schema_renderer: SchemaRenderer | None = None) -> None:
        """Initialize instruction builder."""
        super().__init__()
        self.schema_renderer = schema_renderer or SchemaRenderer()

    def build_ir_system_prompt(self) -> str:
        """Build the system prompt for IR generation and refinement."""
        return """You are an expert test automation architect. You convert approved test scenarios into a framework-independent Intermediate Representation (IR) as a strict JSON document.

## Rules

1. The IR JSON MUST conform EXACTLY to the schema given in the user message. Do not add extra top-level keys and do not omit required fields.
2. Every enum field MUST use one of the exact allowed values listed in the schema. NEVER invent, translate, or abbreviate enum values. For example, do not use values like "title", "id", "name", "default", or "custom" for locator_strategy, action_type, or assertion_type — only the listed values are valid.
3. Never set a required (non-nullable) field to null. Only fields the schema marks as optional may be null.
4. Represent every approved scenario in the plan. Do not drop or merge scenarios, steps, or assertions.
5. Never fabricate information that is not derivable from the plan or environment (navigation targets, element IDs, expected values). Prefer consistent, minimal values anchored in the plan and the application base URL.
6. Prefer semantic locators (role, label, placeholder, testId) over css/xpath.
6a. When a role locator is used (e.g. a submit button), always include its accessible name from the plan whenever the plan identifies the control by visible text — never emit a bare role like "button" without a name.
6b. Only emit assertion types that carry real expected values from the plan: do NOT emit "toHaveTitle"/"toHaveURL" with an invented title or URL. If the plan does not state an exact expected title/URL, omit the assertion or mark the step as requiring review.
6c. Every flow that interacts with a page must begin with an explicit navigation step targeting that page's URL (from the crawler/inventory) so a generated test never acts on a blank page.
7. Declare any dynamic test data (credentials, IDs, passwords) in environment.variables and reference it from fill actions with a dollar-prefixed UPPER_SNAKE_CASE name (e.g. "$VALID_ID"). Never use curly-brace placeholders.
8. Return ONLY the JSON object. No markdown, no code fences, no explanations, no trailing prose."""

    def build_ir_generation_instructions(self) -> str:
        """Build instructions for generating IR from test plans.

        Returns:
            Formatted instruction text
        """
        schema_docs = self.schema_renderer.render_schema_documentation(CodeGenerationIR)
        example = self.schema_renderer.render_json_example(CodeGenerationIR)

        return f"""# Intermediate Representation (IR) Generation

You are an expert test automation architect. Your task is to convert the approved test scenarios below into a **framework-independent Intermediate Representation (IR)**.

## Critical Requirements

1. **Framework Independence**: The IR MUST NOT contain any Playwright, Selenium, or framework-specific code
2. **Complete Representation**: Include all pages, elements, flows, actions, and assertions described in the plan
3. **Structured JSON**: Generate valid, well-structured JSON matching the IR schema EXACTLY
4. **Locator Strategy**: Prefer semantic locators (role, label, placeholder, testId) over CSS/XPath
5. **Modularity**: Group tests by logical modules
6. **Dependencies**: Identify and document flow dependencies with proper structure
7. **Reusability**: Extract common elements and flows where they are shared across modules
8. **No Invented Values**: Only use enum values listed in the schema. Never set required fields to null
9. **No Fabricated Assertions**: Never invent page titles, URLs, or expected values. Only emit toHaveTitle/toHaveURL when the approved scenario explicitly states an expected value
10. **Navigation First**: Start each flow with the navigation step to the page it interacts with, using the page URL discovered by the crawler
11. **Named Roles**: When role locators are used, provide the accessible name (e.g. `button:Login`) — never a bare role without a name

## Locator Priority

1. **role** - Button, Link, Textbox, etc.
2. **label** - Form field labels
3. **placeholder** - Input placeholders
4. **text** - Visible text
5. **testId** - data-testid attributes
6. **css** - CSS selectors (last resort)
7. **xpath** - XPath (avoid if possible)

## IR Schema

{schema_docs}

## Schema-Conformant JSON Template

The JSON template below is generated from the IR schema. Use it as the shape to follow. Replace placeholders with values from the test plan. All fields shown as required must be present; arrays may be empty but never null.

```json
{example}
```

## Instructions

1. Analyze each approved scenario
2. Identify all pages and UI elements
3. Define clear locator strategies (prefer semantic)
4. Map test steps to flow steps
5. Convert assertions to IR assertion types
6. Group flows by module
7. Identify dependencies between flows
8. Extract reusable elements/flows
9. Generate complete, valid JSON IR conforming to the schema

## CRITICAL Reminders

- Match the schema EXACTLY — no missing required fields, no extra fields
- Enum fields (locator_strategy, action_type, assertion_type) MUST use only the allowed values listed in the schema
- Required fields MUST NOT be null
- ALL arrays must be present (can be empty [], never null)
- Return ONLY valid JSON, no markdown, no code fences, no explanations"""

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
