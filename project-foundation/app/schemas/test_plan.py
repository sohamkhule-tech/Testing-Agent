from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


def generate_test_case_id(index: int) -> str:
    """Generate a zero-padded sequential test case identifier.

    Args:
        index: 1-based scenario index.

    Returns:
        Zero-padded ID string, e.g. ``TC-001`` for index=1, ``TC-099`` for index=99.
    """
    return f"TC-{index:03d}"


def renumber_scenario_ids(modules: list[dict], all_scenarios: list[dict], test_priorities: dict, regression_candidates: list[str], dependencies_scenario_ids: list[str]) -> None:
    """Renumber scenario IDs sequentially across all modules.

    Mutates the input dicts in place so that scenario metadata IDs are continuous
    (TC-001, TC-002, ...) regardless of what the LLM returned.  Also updates
    priority lists, regression candidates, dependency refs, and each scenario's
    own ``dependencies`` field to match the new IDs.

    Performs a replacement within all ID-containing structures so downstream
    consumers (Excel export, markdown, event emission) see the corrected values
    without needing to read from a separate mapping.
    """

    old_to_new: dict[str, str] = {}
    scenario_index = 0

    # ── Renumber IDs in module-nested scenarios & collect mapping ──
    for mod in modules:
        for sc in mod.get("scenarios", []):
            meta = sc.get("metadata", {})
            old_id = meta.get("id", "")
            scenario_index += 1
            new_id = generate_test_case_id(scenario_index)
            old_to_new[old_id] = new_id
            meta["id"] = new_id

    # ── Renumber IDs in flat test_scenarios too (if populated) ──
    for sc in all_scenarios:
        meta = sc.get("metadata", {})
        old_id = meta.get("id", "")
        if old_id and old_id not in old_to_new:
            scenario_index += 1
            new_id = generate_test_case_id(scenario_index)
            old_to_new[old_id] = new_id
            meta["id"] = new_id

    # ── Remap dependencies in module-nested scenarios ──
    for mod in modules:
        for sc in mod.get("scenarios", []):
            meta = sc.get("metadata", {})
            old_deps = meta.get("dependencies", []) or []
            new_deps = [old_to_new.get(dep, dep) for dep in old_deps]
            if new_deps != old_deps:
                meta["dependencies"] = new_deps

    # ── Remap dependencies in flat scenarios ──
    for sc in all_scenarios:
        meta = sc.get("metadata", {})
        old_deps = meta.get("dependencies", []) or []
        new_deps = [old_to_new.get(dep, dep) for dep in old_deps]
        if new_deps != old_deps:
            meta["dependencies"] = new_deps

    # ── Update priority buckets ──
    for bucket in ("critical_paths", "high_priority", "medium_priority", "low_priority"):
        ids = test_priorities.get(bucket, []) or []
        new_ids = [old_to_new.get(i, i) for i in ids]
        if new_ids != ids:
            test_priorities[bucket] = new_ids

    # ── Update regression candidates ──
    if regression_candidates:
        new_reg = [old_to_new.get(i, i) for i in regression_candidates]
        if new_reg != regression_candidates:
            regression_candidates[:] = new_reg

    # ── Update global dependencies.scenario_ids ──
    if dependencies_scenario_ids:
        new_dep_ids = [old_to_new.get(i, i) for i in dependencies_scenario_ids]
        if new_dep_ids != dependencies_scenario_ids:
            dependencies_scenario_ids[:] = new_dep_ids


class Priority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Risk(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TestCategory(str, Enum):
    NAVIGATION = "navigation"
    SMOKE = "smoke"
    HAPPY_PATH = "happy_path"
    FUNCTIONAL = "functional"
    CRUD = "crud"
    VALIDATION = "validation"
    BOUNDARY = "boundary"
    NEGATIVE = "negative"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    SESSION = "session"
    ACCESSIBILITY = "accessibility"
    PERFORMANCE = "performance"
    REGRESSION = "regression"
    SECURITY = "security"
    USABILITY = "usability"


class ScenarioMetadata(BaseModel):
    id: str = Field(..., description="Unique scenario identifier")
    title: str = Field(..., description="Scenario title")
    description: str = Field(..., description="Scenario description")
    priority: Priority = Field(..., description="Test priority")
    category: TestCategory = Field(..., description="Test category")
    module: str = Field(..., description="Associated module name")
    target_page: str | None = Field(None, description="Target page URL")
    preconditions: list[str] = Field(default_factory=list, description="Required preconditions")
    test_steps: list[str] = Field(default_factory=list, description="High-level test steps")
    expected_result: str = Field(..., description="Expected outcome")
    required_test_data: list[str] = Field(default_factory=list, description="Required test data")
    tags: list[str] = Field(default_factory=list, description="Classification tags")
    dependencies: list[str] = Field(default_factory=list, description="Scenario dependencies")
    risk_level: Risk = Field(default=Risk.MEDIUM, description="Risk level")


class TestScenario(BaseModel):
    metadata: ScenarioMetadata = Field(..., description="Scenario metadata")
    use_cases: list[str] = Field(default_factory=list, description="Use case references")


class TestModule(BaseModel):
    name: str = Field(..., description="Module name")
    description: str = Field(..., description="Module description")
    pages: list[str] = Field(default_factory=list, description="Associated page URLs")
    scenarios: list[TestScenario] = Field(default_factory=list, description="Module scenarios")


class CoverageSummary(BaseModel):
    total_scenarios: int = Field(default=0, ge=0, description="Total test scenarios")
    by_category: dict[str, int] = Field(default_factory=dict, description="Scenarios per category")
    by_priority: dict[str, int] = Field(default_factory=dict, description="Scenarios per priority")
    by_module: dict[str, int] = Field(default_factory=dict, description="Scenarios per module")
    uncovered_modules: list[str] = Field(default_factory=list, description="Modules without tests")
    estimated_duration_minutes: int = Field(default=0, ge=0, description="Estimated execution time")


class ApplicationSummary(BaseModel):
    name: str = Field(default="Unknown", description="Application name")
    version: str | None = Field(None, description="Application version")
    total_pages: int = Field(default=0, ge=0, description="Total pages analyzed")
    total_forms: int = Field(default=0, ge=0, description="Total forms discovered")
    total_apis: int = Field(default=0, ge=0, description="Total API endpoints")
    authentication_required: bool = Field(default=False, description="Auth requirement")
    auth_method: str = Field(default="none", description="Authentication method")


class ScenarioDependencies(BaseModel):
    scenario_ids: list[str] = Field(default_factory=list, description="Dependent scenario IDs")
    required_data: list[str] = Field(default_factory=list, description="Required data inputs")
    required_state: list[str] = Field(default_factory=list, description="Required system state")


class TestPriorities(BaseModel):
    critical_paths: list[str] = Field(default_factory=list, description="Critical scenario IDs")
    high_priority: list[str] = Field(default_factory=list, description="High priority IDs")
    medium_priority: list[str] = Field(default_factory=list, description="Medium priority IDs")
    low_priority: list[str] = Field(default_factory=list, description="Low priority IDs")


class TestAssumptions(BaseModel):
    assumptions: list[str] = Field(default_factory=list, description="Test assumptions")
    constraints: list[str] = Field(default_factory=list, description="Test constraints")
    risks: list[str] = Field(default_factory=list, description="Known risks and mitigations")


class TestPlan(BaseModel):
    run_id: UUID = Field(..., description="Test run identifier")
    request_id: UUID = Field(..., description="Request correlation ID")
    generated_at: datetime = Field(..., description="Plan generation timestamp")
    application_summary: ApplicationSummary = Field(
        default_factory=ApplicationSummary, description="Application summary"
    )
    modules: list[TestModule] = Field(default_factory=list, description="Application modules")
    test_scenarios: list[TestScenario] = Field(default_factory=list, description="All scenarios")
    dependencies: ScenarioDependencies = Field(
        default_factory=ScenarioDependencies, description="Scenario dependencies"
    )
    test_priorities: TestPriorities = Field(
        default_factory=TestPriorities, description="Prioritization"
    )
    assumptions: TestAssumptions = Field(
        default_factory=TestAssumptions, description="Assumptions"
    )
    coverage_summary: CoverageSummary = Field(
        default_factory=CoverageSummary, description="Coverage summary"
    )
    high_risk_areas: list[str] = Field(default_factory=list, description="High risk areas")
    regression_candidates: list[str] = Field(default_factory=list, description="Regression test IDs")
    accessibility_recommendations: list[str] = Field(default_factory=list, description="A11y recommendations")
    performance_recommendations: list[str] = Field(default_factory=list, description="Performance recommendations")

    model_config = {"frozen": False}
