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
6. LOCATOR EVIDENCE IS THE SINGLE SOURCE OF TRUTH. When an "## Element Evidence" section is present in the prompt, you MUST derive every locator_strategy and locator_value exclusively from that evidence. The evidence lists the actual attributes discovered on the live application during crawling. Never invent a locator value from the scenario description text alone.
6a. Locator priority (use the first that has verified evidence for the element):
    1. label — use when the element has a verified label in the evidence (exact value from evidence, e.g. locator_strategy="label", locator_value="Email Address / User ID")
    2. placeholder — use when the element has a verified placeholder in the evidence (exact value from evidence)
    3. text — use for buttons/links when the button text is in the evidence (exact value from evidence)
    4. testId — use when data-testid is in the evidence
    5. role — ONLY use when the accessible name is explicitly present in the evidence; never use role with an invented name derived from the scenario description
    6. css — last resort when no semantic attribute is in evidence
    7. xpath — only when no other option exists
6b. If no element evidence is provided for a page, prefer conservative semantic locators and acknowledge uncertainty in the element description field. Do NOT make up placeholder text, label names, or aria-labels from the scenario step text.
6c. When a role locator is used, the locator_value must be the verified accessible name from the evidence — never a name guessed from the scenario description.
6d. Only emit assertions whose expected values are explicitly stated in the approved scenario's expected_result or test_steps fields. Do NOT emit any assertion (toHaveTitle, toHaveURL, toHaveText, toContainText, or any other type) with an invented, guessed, or assumed expected value. If a scenario's expected_result is conditional ("accepts OR rejects", "may redirect", "should show error"), emit ONLY the assertion for the path that is certain — never convert a conditional outcome to an unconditional assertion. When an expected value is not explicitly stated, omit the assertion entirely or add a descriptive comment step instead of asserting a fabricated value.
6e. Every flow that interacts with a page must begin with an explicit navigation step targeting that page's URL (from the crawler/inventory) so a generated test never acts on a blank page.
7. Declare any dynamic test data (credentials, IDs, passwords) in environment.variables and reference it from fill actions with a dollar-prefixed UPPER_SNAKE_CASE name (e.g. "$VALID_ID"). Never use curly-brace placeholders.
8. UI elements can change state after interaction (a toggle whose accessible name changes, an accordion that expands, a menu that opens). When you have evidence that an element changes state, model it as ONE logical element whose `states` list enumerates each observable state with its own locator and attributes. Never duplicate the element into multiple near-identical static elements.
9. When an action changes an element's state, record a `state_transition` on that action (`from_state` = state before, `to_state` = state after). A repeated interaction with the same stateful control must use the correct current-state locator via `from_state`.
10. Never invent state transitions that the crawl/inventory evidence does not support. If a control's dynamic behavior cannot be confirmed, leave `state_transition` absent (or set `evidence: "unknown"`) rather than fabricating before/after values.
11. Return ONLY the JSON object. No markdown, no code fences, no explanations, no trailing prose."""

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

## Locator Priority (Evidence-Based — highest to lowest)

When an **Element Evidence** section is present, derive every locator from that data ONLY.

1. **label** - Form field label text (exact value from evidence)
2. **placeholder** - Input placeholder text (exact value from evidence)
3. **text** - Visible button/link text (exact value from evidence)
4. **testId** - data-testid attribute (exact value from evidence)
5. **role** - ONLY when accessible name is verified in evidence (never invent the name)
6. **css** - CSS selectors (only when no semantic attribute in evidence)
7. **xpath** - Absolute last resort

> **IMPORTANT**: Never derive a locator value from the scenario description text alone.
> If evidence does not confirm an attribute, do not use it as a locator value.

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

    def build_state_transition_instructions(self) -> str:
        """
        Build instructions for modeling dynamic UI state transitions.

        Returns:
            State-transition instruction text
        """
        return """## Dynamic UI State & State Transitions

UI elements can change their locator or observable attributes after interaction. For example a
password visibility toggle's button accessible name may change from one value to another, an
accordion header may change aria-expanded, or a menu button may toggle open/closed. Model these
as a single logical element with multiple states rather than duplicated static elements.

1. **One logical element, many states** — when evidence shows an element changes state, add a
   `states` array to that element. Each state object has an `id`, an optional `name`/`description`,
   and (when the state changes the locator) its own `locator_strategy`/`locator_value`. Record
   observable differences in `attributes` (e.g. `accessible_name`, `input_type`, `aria_expanded`).

2. **Record state-changing actions** — when an action moves an element from one state to another,
   set the action's `state_transition`:
   - `from_state`: the element's state *before* the action (this state's locator is what identifies
     the element at that moment).
   - `to_state`: the element's state *after* the action.
   - `before`/`after`: optional observed/expected attribute dictionaries.
   - `evidence`: where the transition came from, or `"unknown"` when unverified.

3. **Repeated interaction uses the current state** — if a flow interacts with the same stateful
   control more than once, the later action MUST carry a `state_transition` whose `from_state`
   reflects the state the control is currently in (typically the previous action's `to_state`).
   Never repeat the same initial-state locator for a control whose state has changed.

4. **Evidence-based only** — do NOT invent state transitions. If the available crawl/inventory
   evidence does not confirm that a control changes state, model it as a plain single-state
   element and omit `state_transition`. A normal button clicked twice without any state change is
   valid and should NOT be given a `state_transition`."""
