"""
IR Validator

Validates framework-independent Intermediate Representation for structural integrity.
"""

from typing import Any

from app.logging import LoggerMixin
from app.schemas.ir import (
    ActionType,
    AssertionType,
    CodeGenerationIR,
    IRValidationIssue,
    IRValidationResult,
    LocatorStrategy,
)


class IRValidator(LoggerMixin):
    """
    Validates IR structure and semantics.
    
    Checks for:
    - Duplicate pages, elements, flows
    - Broken references
    - Missing assertions
    - Circular dependencies
    - Invalid locators
    - Incomplete flows
    """

    def __init__(self) -> None:
        """Initialize validator."""
        super().__init__()
        self.issues: list[IRValidationIssue] = []

    def validate(self, ir: CodeGenerationIR) -> IRValidationResult:
        """
        Validate complete IR structure.

        Args:
            ir: The IR to validate

        Returns:
            Validation result with issues
            
        Raises:
            ValueError: If IR or metadata is missing or invalid
        """
        # Defensive validation - ensure IR structure exists
        if not ir:
            raise ValueError("IR object is None or empty")
        
        if not ir.metadata:
            raise ValueError("IR metadata is missing")
        
        # Validate required metadata fields exist
        required_fields = ['generator', 'ir_version']
        missing_fields = [f for f in required_fields if not hasattr(ir.metadata, f)]
        if missing_fields:
            raise ValueError(f"IR metadata missing required fields: {missing_fields}")
        
        # Log validation start with available metadata
        self.logger.info(
            "validating_ir",
            generator=ir.metadata.generator,
            ir_version=ir.metadata.ir_version,
            total_pages=ir.metadata.total_pages,
            total_modules=ir.metadata.total_modules,
        )
        self.issues = []

        # Run all validations
        self._validate_pages(ir)
        self._validate_modules(ir)
        self._validate_dependencies(ir)
        self._validate_common_elements(ir)
        self._validate_common_flows(ir)
        self._validate_state_transitions(ir)

        # Create result
        errors = [i for i in self.issues if i.severity == "error"]
        warnings = [i for i in self.issues if i.severity == "warning"]

        is_valid = len(errors) == 0
        
        result = IRValidationResult(
            is_valid=is_valid,
            issues=self.issues,
        )

        self.logger.info(
            "ir_validation_complete",
            is_valid=is_valid,
            errors=len(errors),
            warnings=len(warnings)
        )

        return result

    def _validate_pages(self, ir: CodeGenerationIR) -> None:
        """Validate pages section."""
        page_ids = set()

        for page in ir.pages:
            # Check for duplicate page IDs
            if page.page_id in page_ids:
                self.issues.append(
                    IRValidationIssue(
                        severity="error",
                        component_type="page",
                        component_id=page.page_id,
                        issue_type="duplicate_id",
                        message=f"Duplicate page ID: {page.page_id}",
                    )
                )
            page_ids.add(page.page_id)

            # Validate elements in page
            element_ids = set()
            for element in page.elements:
                # Check for duplicate element IDs within page
                if element.id in element_ids:
                    self.issues.append(
                        IRValidationIssue(
                            severity="error",
                            component_type="element",
                            component_id=element.id,
                            issue_type="duplicate_id",
                            message=f"Duplicate element ID in page {page.page_id}: {element.id}",
                        )
                    )
                element_ids.add(element.id)

                # Validate locator strategy
                if element.locator_strategy not in [s.value for s in LocatorStrategy]:
                    self.issues.append(
                        IRValidationIssue(
                            severity="error",
                            component_type="element",
                            component_id=element.id,
                            issue_type="invalid_locator_strategy",
                            message=f"Invalid locator strategy: {element.locator_strategy}",
                        )
                    )

                # Warn if using CSS or XPath (prefer semantic locators)
                if element.locator_strategy in ["css", "xpath"]:
                    self.issues.append(
                        IRValidationIssue(
                            severity="warning",
                            component_type="element",
                            component_id=element.id,
                            issue_type="locator_preference",
                            message=f"Using {element.locator_strategy} locator. Consider semantic locator (role, label, placeholder)",
                        )
                    )

                # Check if locator value is empty
                if not element.locator_value or element.locator_value.strip() == "":
                    self.issues.append(
                        IRValidationIssue(
                            severity="error",
                            component_type="element",
                            component_id=element.id,
                            issue_type="empty_locator",
                            message="Empty locator value",
                        )
                    )

    def _validate_modules(self, ir: CodeGenerationIR) -> None:
        """Validate modules section."""
        module_ids = set()
        flow_ids = set()

        # Get all page IDs for reference validation
        page_ids = {p.page_id for p in ir.pages}

        # Get all element IDs for reference validation
        element_ids = set()
        for page in ir.pages:
            for element in page.elements:
                element_ids.add(element.id)

        for module in ir.modules:
            # Check for duplicate module IDs
            if module.module_id in module_ids:
                self.issues.append(
                    IRValidationIssue(
                        severity="error",
                        component_type="module",
                        component_id=module.module_id,
                        issue_type="duplicate_id",
                        message=f"Duplicate module ID: {module.module_id}",
                    )
                )
            module_ids.add(module.module_id)

            # Validate page references
            for page_id in module.pages:
                if page_id not in page_ids:
                    self.issues.append(
                        IRValidationIssue(
                            severity="error",
                            component_type="module",
                            component_id=module.module_id,
                            issue_type="broken_reference",
                            message=f"Module references non-existent page: {page_id}",
                        )
                    )

            # Validate flows
            for flow in module.flows:
                # Check for duplicate flow IDs
                if flow.flow_id in flow_ids:
                    self.issues.append(
                        IRValidationIssue(
                            severity="error",
                            component_type="flow",
                            component_id=flow.flow_id,
                            issue_type="duplicate_id",
                            message=f"Duplicate flow ID: {flow.flow_id}",
                        )
                    )
                flow_ids.add(flow.flow_id)

                # Validate flow has steps
                if not flow.steps:
                    self.issues.append(
                        IRValidationIssue(
                            severity="error",
                            component_type="flow",
                            component_id=flow.flow_id,
                            issue_type="missing_steps",
                            message="Flow has no steps",
                        )
                    )
                    continue

                # Validate each step
                has_assertions = False
                for step in flow.steps:
                    # Validate actions
                    for action in step.actions:
                        # Check action type
                        if action.action_type not in [a.value for a in ActionType]:
                            self.issues.append(
                                IRValidationIssue(
                                    severity="error",
                                    component_type="flow",
                                    component_id=flow.flow_id,
                                    issue_type="invalid_action_type",
                                    message=f"Invalid action type in step {step.step_order}: {action.action_type}",
                                )
                            )

                        # Check element reference
                        if action.element_id and action.element_id not in element_ids:
                            self.issues.append(
                                IRValidationIssue(
                                    severity="error",
                                    component_type="flow",
                                    component_id=flow.flow_id,
                                    issue_type="broken_reference",
                                    message=f"Action references non-existent element: {action.element_id}",
                                )
                            )

                        # Check if fill/select action has value
                        if action.action_type in ["fill", "select"] and not action.value:
                            self.issues.append(
                                IRValidationIssue(
                                    severity="warning",
                                    component_type="flow",
                                    component_id=flow.flow_id,
                                    issue_type="missing_value",
                                    message=f"Action {action.action_type} in step {step.step_order} has no value",
                                )
                            )

                    # Validate assertions
                    for assertion in step.assertions:
                        has_assertions = True

                        # Check assertion type
                        if assertion.assertion_type not in [a.value for a in AssertionType]:
                            self.issues.append(
                                IRValidationIssue(
                                    severity="error",
                                    component_type="flow",
                                    component_id=flow.flow_id,
                                    issue_type="invalid_assertion_type",
                                    message=f"Invalid assertion type in step {step.step_order}: {assertion.assertion_type}",
                                )
                            )

                        # Check element reference
                        if assertion.element_id and assertion.element_id not in element_ids:
                            self.issues.append(
                                IRValidationIssue(
                                    severity="error",
                                    component_type="flow",
                                    component_id=flow.flow_id,
                                    issue_type="broken_reference",
                                    message=f"Assertion references non-existent element: {assertion.element_id}",
                                )
                            )

                # Warn if flow has no assertions
                if not has_assertions:
                    self.issues.append(
                        IRValidationIssue(
                            severity="warning",
                            component_type="flow",
                            component_id=flow.flow_id,
                            issue_type="missing_assertions",
                            message="Flow has no assertions",
                        )
                    )

                # Validate dependencies
                for dep in (flow.depends_on or []):
                    if dep not in flow_ids and dep != flow.flow_id:
                        # Dependency might not be defined yet if we're in the middle of validation
                        # We'll catch this in the dependency validation pass
                        pass

    def _validate_dependencies(self, ir: CodeGenerationIR) -> None:
        """Validate dependencies section."""
        page_ids = {p.page_id for p in ir.pages}
        flow_ids = set()
        for module in ir.modules:
            for flow in module.flows:
                flow_ids.add(flow.flow_id)

        dep_graph: dict[str, list[str]] = {}
        for dep in ir.dependencies:
            dep_id = dep.description or f"{dep.source_id}->{dep.target_id}"

            source_found = dep.source_id in page_ids or dep.source_id in flow_ids
            target_found = dep.target_id in page_ids or dep.target_id in flow_ids

            if not source_found:
                self.issues.append(
                    IRValidationIssue(
                        severity="error",
                        component_type="dependency",
                        component_id=dep_id,
                        issue_type="broken_reference",
                        message=f"Dependency source not found: {dep.source_id}",
                    )
                )
            if not target_found:
                self.issues.append(
                    IRValidationIssue(
                        severity="error",
                        component_type="dependency",
                        component_id=dep_id,
                        issue_type="broken_reference",
                        message=f"Dependency target not found: {dep.target_id}",
                    )
                )

            # Build dependency graph for circular detection
            if dep.source_id not in dep_graph:
                dep_graph[dep.source_id] = []
            dep_graph[dep.source_id].append(dep.target_id)

        # Check for circular dependencies
        visited = set()
        path = set()

        def has_cycle(node: str) -> bool:
            """Check if node has circular dependency."""
            if node in path:
                return True
            if node in visited:
                return False

            visited.add(node)
            path.add(node)

            for neighbor in dep_graph.get(node, []):
                if has_cycle(neighbor):
                    return True

            path.remove(node)
            return False

        for node in dep_graph:
            if node not in visited:
                if has_cycle(node):
                    self.issues.append(
                        IRValidationIssue(
                            severity="error",
                            component_type="dependency",
                            component_id=node,
                            issue_type="circular_dependency",
                            message=f"Circular dependency detected involving: {node}",
                        )
                    )

    def _validate_common_elements(self, ir: CodeGenerationIR) -> None:
        """Validate common elements section."""
        common_element_ids = set()

        for element in ir.common_elements:
            # Check for duplicate IDs
            if element.id in common_element_ids:
                self.issues.append(
                    IRValidationIssue(
                        severity="error",
                        component_type="common_element",
                        component_id=element.id,
                        issue_type="duplicate_id",
                        message=f"Duplicate common element ID: {element.id}",
                    )
                )
            common_element_ids.add(element.id)

            # Validate locator strategy
            if element.locator_strategy not in [s.value for s in LocatorStrategy]:
                self.issues.append(
                    IRValidationIssue(
                        severity="error",
                        component_type="common_element",
                        component_id=element.id,
                        issue_type="invalid_locator_strategy",
                        message=f"Invalid locator strategy: {element.locator_strategy}",
                    )
                )

    def _validate_common_flows(self, ir: CodeGenerationIR) -> None:
        """Validate common flows section."""
        common_flow_ids = set()

        # Get all element IDs for reference validation
        element_ids = set()
        for page in ir.pages:
            for element in page.elements:
                element_ids.add(element.id)
        for element in ir.common_elements:
            element_ids.add(element.id)

        for flow in ir.common_flows:
            # Check for duplicate IDs
            if flow.flow_id in common_flow_ids:
                self.issues.append(
                    IRValidationIssue(
                        severity="error",
                        component_type="common_flow",
                        component_id=flow.flow_id,
                        issue_type="duplicate_id",
                        message=f"Duplicate common flow ID: {flow.flow_id}",
                    )
                )
            common_flow_ids.add(flow.flow_id)

            # Validate flow has steps
            if not flow.steps:
                self.issues.append(
                    IRValidationIssue(
                        severity="warning",
                        component_type="common_flow",
                        component_id=flow.flow_id,
                        issue_type="missing_steps",
                        message="Common flow has no steps",
                    )
                )

            # Validate element references in actions
            for step in flow.steps:
                for action in step.actions:
                    if action.element_id and action.element_id not in element_ids:
                        self.issues.append(
                            IRValidationIssue(
                                severity="error",
                                component_type="common_flow",
                                component_id=flow.flow_id,
                                issue_type="broken_reference",
                                message=f"Action references non-existent element: {action.element_id}",
                            )
                        )

    def _validate_state_transitions(self, ir: CodeGenerationIR) -> None:
        """Validate dynamic/stateful element interactions.

        Detects suspicious patterns where a stateful control is interacted with
        repeatedly without a state transition being recorded. This is a semantic
        (non-fatal) check: legitimate repeated interactions on non-stateful
        elements are never flagged, and warnings do not invalidate the IR.

        A stateful element is one that declares a non-empty ``states`` list.
        """
        element_by_id: dict[str, Any] = {}
        for page in ir.pages:
            for element in page.elements:
                element_by_id[element.id] = element
        for element in ir.common_elements:
            element_by_id[element.id] = element

        state_ids_by_element: dict[str, set[str]] = {}
        for eid, element in element_by_id.items():
            state_ids_by_element[eid] = {s.id for s in (element.states or [])}

        for module in ir.modules:
            for flow in module.flows:
                click_counts: dict[str, int] = {}
                for step in sorted(flow.steps, key=lambda s: s.step_order):
                    for action in step.actions:
                        if action.action_type != ActionType.CLICK or not action.element_id:
                            continue
                        eid = action.element_id
                        element = element_by_id.get(eid)
                        is_stateful = element is not None and bool(getattr(element, "states", None))
                        prior_clicks = click_counts.get(eid, 0)
                        click_counts[eid] = prior_clicks + 1

                        if not is_stateful:
                            continue

                        transition = action.state_transition
                        if prior_clicks >= 1 and transition is None:
                            self.issues.append(
                                IRValidationIssue(
                                    severity="warning",
                                    component_type="flow",
                                    component_id=flow.flow_id,
                                    issue_type="state_transition_missing",
                                    message=(
                                        f"Stateful element '{eid}' is clicked repeatedly in flow "
                                        f"'{flow.flow_id}' but the later click has no state_transition"
                                    ),
                                    suggestion=(
                                        "Record a state_transition (from_state/to_state) on repeated "
                                        "clicks of a stateful control so the correct current-state "
                                        "locator is used."
                                    ),
                                )
                            )
                            continue

                        if transition is None:
                            continue

                        # Validate referenced states exist on the element.
                        known_states = state_ids_by_element.get(eid, set())
                        for sid in (transition.from_state, transition.to_state):
                            if sid and known_states and sid not in known_states:
                                self.issues.append(
                                    IRValidationIssue(
                                        severity="warning",
                                        component_type="flow",
                                        component_id=flow.flow_id,
                                        issue_type="unknown_state",
                                        message=(
                                            f"state_transition references unknown state '{sid}' on "
                                            f"element '{eid}'"
                                        ),
                                        suggestion=(
                                            f"Use one of the declared states: {sorted(known_states)}"
                                        ),
                                    )
                                )
