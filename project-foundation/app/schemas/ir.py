"""
Intermediate Representation (IR) Schemas

Framework-independent representation of test automation structure.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class LocatorStrategy(str, Enum):
    """Locator strategy types."""
    ROLE = "role"
    LABEL = "label"
    PLACEHOLDER = "placeholder"
    TEXT = "text"
    TEST_ID = "testId"
    CSS = "css"
    XPATH = "xpath"


class ActionType(str, Enum):
    """Action types."""
    CLICK = "click"
    FILL = "fill"
    SELECT = "select"
    CHECK = "check"
    UNCHECK = "uncheck"
    HOVER = "hover"
    FOCUS = "focus"
    PRESS = "press"
    UPLOAD = "upload"
    CLEAR = "clear"
    DOUBLE_CLICK = "doubleClick"
    RIGHT_CLICK = "rightClick"


class AssertionType(str, Enum):
    """Assertion types."""
    VISIBLE = "toBeVisible"
    HIDDEN = "toBeHidden"
    ENABLED = "toBeEnabled"
    DISABLED = "toBeDisabled"
    CHECKED = "toBeChecked"
    UNCHECKED = "toBeUnchecked"
    HAS_TEXT = "toHaveText"
    HAS_VALUE = "toHaveValue"
    HAS_URL = "toHaveURL"
    HAS_TITLE = "toHaveTitle"
    HAS_COUNT = "toHaveCount"
    CONTAINS_TEXT = "toContainText"


class ElementIR(BaseModel):
    """IR for a UI element."""
    id: str = Field(..., description="Unique element identifier")
    name: str = Field(..., description="Element name")
    locator_strategy: LocatorStrategy = Field(..., description="Locator strategy")
    locator_value: str = Field(..., description="Locator value")
    description: str | None = Field(None, description="Element description")
    fallback_locators: list[dict[str, str]] = Field(
        default_factory=list,
        description="Fallback locator strategies"
    )
    wait_for_visible: bool = Field(True, description="Wait for visibility")
    timeout: int | None = Field(None, description="Custom timeout in ms")


class ActionIR(BaseModel):
    """IR for an action."""
    action_type: ActionType = Field(..., description="Type of action")
    element_id: str | None = Field(None, description="Target element ID")
    value: str | None = Field(None, description="Action value (for fill, select, etc.)")
    description: str = Field("", description="Action description")  # Optional — LLM may omit
    wait_before: int | None = Field(None, description="Wait before action (ms)")
    wait_after: int | None = Field(None, description="Wait after action (ms)")


class AssertionIR(BaseModel):
    """IR for an assertion."""
    assertion_type: AssertionType = Field(..., description="Type of assertion")
    element_id: str | None = Field(None, description="Target element ID")
    expected_value: Any | None = Field(None, description="Expected value")
    description: str = Field("", description="Assertion description")  # Optional — LLM may omit
    timeout: int | None = Field(None, description="Assertion timeout")
    negated: bool = Field(False, description="Negate the assertion")


class NavigationIR(BaseModel):
    """IR for navigation."""
    target: str = Field(..., description="Navigation target (URL or page ID)")
    wait_for_load: bool = Field(True, description="Wait for page load")
    wait_for_selector: str | None = Field(None, description="Wait for specific element")
    description: str = Field("", description="Navigation description")  # Optional — LLM may omit


class FlowStepIR(BaseModel):
    """IR for a flow step."""
    step_order: int = Field(..., description="Step order in flow")
    description: str = Field(..., description="Step description")
    navigation: NavigationIR | None = Field(None, description="Navigation action")
    actions: list[ActionIR] = Field(default_factory=list, description="Actions to perform")
    assertions: list[AssertionIR] = Field(default_factory=list, description="Assertions to check")
    wait_for_condition: str | None = Field(None, description="Condition to wait for")


class TestFlowIR(BaseModel):
    """IR for a complete test flow."""
    flow_id: str = Field(..., description="Unique flow identifier")
    name: str = Field(..., description="Flow name")
    description: str = Field(..., description="Flow description")
    tags: list[str] = Field(default_factory=list, description="Flow tags")
    steps: list[FlowStepIR] = Field(..., description="Flow steps")
    preconditions: list[str] = Field(default_factory=list, description="Required preconditions")
    postconditions: list[str] = Field(default_factory=list, description="Expected postconditions")
    depends_on: list[str] = Field(default_factory=list, description="Flow dependencies")
    timeout: int | None = Field(None, description="Flow timeout in ms")
    priority: str = Field("medium", description="Flow priority (low/medium/high)")


class PageIR(BaseModel):
    """IR for a page."""
    page_id: str = Field(..., description="Unique page identifier")
    name: str = Field(..., description="Page name")
    url_pattern: str | None = Field(None, description="URL pattern")
    description: str = Field(..., description="Page description")
    elements: list[ElementIR] = Field(default_factory=list, description="Page elements")
    page_load_selector: str | None = Field(None, description="Selector to wait for")
    requires_auth: bool = Field(False, description="Requires authentication")


class ModuleIR(BaseModel):
    """IR for a test module."""
    module_id: str = Field(..., description="Unique module identifier")
    name: str = Field(..., description="Module name")
    description: str = Field(..., description="Module description")
    pages: list[str] = Field(default_factory=list, description="Page IDs in module")
    flows: list[TestFlowIR] = Field(default_factory=list, description="Test flows")
    tags: list[str] = Field(default_factory=list, description="Module tags")
    priority: str = Field("medium", description="Module priority")
    requires_auth: bool = Field(False, description="Module requires authentication")


class EnvironmentIR(BaseModel):
    """IR for environment configuration."""
    base_url: str = Field(..., description="Application base URL")
    auth_required: bool = Field(False, description="Authentication required")
    auth_type: str | None = Field(None, description="Authentication type")
    variables: dict[str, str] = Field(default_factory=dict, description="Environment variables")
    timeouts: dict[str, int] = Field(default_factory=dict, description="Timeout configurations")
    browsers: list[str] = Field(
        default_factory=lambda: ["chromium"],
        description="Target browsers"
    )


class DependencyIR(BaseModel):
    """IR for dependencies between components."""
    source_id: str = Field(..., description="Source component ID")
    target_id: str = Field(..., description="Target component ID")
    dependency_type: str = Field(..., description="Type of dependency")
    description: str | None = Field(None, description="Dependency description")


class MetadataIR(BaseModel):
    """IR metadata."""
    generator: str = Field(..., description="Generator name")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Generation time")
    ir_version: str = Field(default="1.0.0", description="IR version")
    source_test_plan: str | None = Field(None, description="Source test plan path")
    model_used: str | None = Field(None, description="LLM model used")
    total_pages: int = Field(0, description="Total pages")
    total_elements: int = Field(0, description="Total elements")
    total_flows: int = Field(0, description="Total flows")
    total_modules: int = Field(0, description="Total modules")
    validation_status: str = Field("pending", description="Validation status")


class CodeGenerationIR(BaseModel):
    """Complete Intermediate Representation for code generation."""
    
    metadata: MetadataIR = Field(..., description="IR metadata")
    environment: EnvironmentIR = Field(..., description="Environment configuration")
    pages: list[PageIR] = Field(default_factory=list, description="All pages")
    modules: list[ModuleIR] = Field(default_factory=list, description="All modules")
    dependencies: list[DependencyIR] = Field(default_factory=list, description="Dependencies")
    
    # Global reusable components
    common_elements: list[ElementIR] = Field(
        default_factory=list,
        description="Reusable elements across pages"
    )
    common_flows: list[TestFlowIR] = Field(
        default_factory=list,
        description="Reusable flows across modules"
    )
    
    # Configuration
    retry_config: dict[str, Any] = Field(
        default_factory=dict,
        description="Retry configuration"
    )
    parallel_config: dict[str, Any] = Field(
        default_factory=dict,
        description="Parallel execution configuration"
    )


class IRValidationIssue(BaseModel):
    """Validation issue in IR."""
    severity: str = Field(..., description="error, warning, info")
    component_type: str = Field(..., description="Type of component")
    component_id: str = Field(..., description="Component ID")
    issue_type: str = Field(..., description="Type of issue")
    message: str = Field(..., description="Issue description")
    suggestion: str | None = Field(None, description="Fix suggestion")


class IRValidationResult(BaseModel):
    """IR validation result."""
    is_valid: bool = Field(..., description="Overall validation status")
    issues: list[IRValidationIssue] = Field(default_factory=list, description="Validation issues")
    summary: dict[str, Any] = Field(default_factory=dict, description="Validation summary")
    validated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Validation time")

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")
