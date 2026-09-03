"""
Test Design Agent

AI Agent responsible for analyzing application inventory and
producing a comprehensive, structured test plan.
"""

import asyncio
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.core.interfaces import IAgent, ILLMClient
from app.exceptions import AgentExecutionError
from app.logging import LoggerMixin
from app.prompts import get_prompt
from app.schemas.inventory import Inventory
from app.schemas.test_plan import (
    ApplicationSummary,
    CoverageSummary,
    Priority,
    Risk,
    ScenarioDependencies,
    ScenarioMetadata,
    TestAssumptions,
    TestCategory,
    TestModule,
    TestPlan,
    TestPriorities,
    TestScenario,
    renumber_scenario_ids,
)
from app.services.test_design_service import TestDesignService


_CATEGORY_SYNONYMS: dict[str, str] = {
    "error_handling": "negative",
    "error": "negative",
    "errors": "negative",
    "auth": "authentication",
    "access": "accessibility",
    "positive": "happy_path",
    "happy": "happy_path",
    "sanity": "smoke",
}


def _coerce_enum(raw: Any, enum_cls: Any, default: Any, synonyms: dict[str, str] | None = None) -> Any:
    """Coerce an arbitrary LLM-produced value into a valid enum member.

    LLM outputs are free-form and may not match the schema enum exactly
    (e.g. ``error_handling``). This maps the value to the closest valid enum
    member and falls back to ``default`` so schema validation never fails.
    """
    if isinstance(raw, dict):
        raw = raw.get("value", raw.get("name"))
    if raw is None:
        return default
    val = str(raw).strip().lower().replace(" ", "_").replace("-", "_")
    for member in enum_cls:
        if member.value == val:
            return member
    if synonyms:
        canonical = synonyms.get(val)
        if canonical:
            for member in enum_cls:
                if member.value == canonical:
                    return member
    return default


class TestDesignAgent(IAgent, LoggerMixin):
    """
    Test Design Agent - analyzes inventory and generates structured test plans.

    Responsibilities:
    - Load and validate application inventory
    - Analyze navigation, forms, APIs, authentication, UI components
    - Infer workflows and business flows
    - Generate comprehensive test plan with structured scenarios
    - Persist test-plan.json contract
    - Never generate executable code or interact with browsers
    """

    def __init__(
        self,
        service: TestDesignService,
        llm_client: ILLMClient,
    ) -> None:
        """
        Initialize test design agent.

        Args:
            service: Test design service for inventory loading and persistence
            llm_client: LLM client for AI-powered analysis
        """
        super().__init__()
        self.service = service
        self.llm_client = llm_client

    @staticmethod
    def _extract_json(text: str) -> dict:
        """Extract and parse JSON from LLM response, handling common formatting issues."""
        import re as _re
        text = text.strip()
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            text = text[first_brace:last_brace+1]
        text = _re.sub(r",\s*}", "}", text)
        text = _re.sub(r",\s*]", "]", text)
        text = _re.sub(r"```json\s*", "", text)
        text = _re.sub(r"```\s*", "", text)
        if not text:
            raise AgentExecutionError("LLM returned empty response after JSON extraction")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            text = _re.sub(r":\s+'([^']+)'\s*([,}\]])", r': "\1"\2', text)
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                text = _re.sub(r"'", '"', text)
                try:
                    return json.loads(text)
                except json.JSONDecodeError as e:
                    raise AgentExecutionError(f"LLM returned invalid JSON: {str(e)}. Raw: {text[:500]}")

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        Execute test design agent logic.

        Args:
            input_data: Input data containing inventory, workspace, run_id

        Returns:
            Agent output with test plan result

        Raises:
            AgentExecutionError: If execution fails
        """
        try:
            self.logger.info("test_design_agent_started")

            # Extract input parameters
            run_id_str = input_data.get("run_id")
            request_id_str = input_data.get("request_id")
            workspace_path = input_data.get("workspace_path")

            if not run_id_str:
                raise AgentExecutionError("Missing 'run_id' in input data")
            if not workspace_path:
                raise AgentExecutionError("Missing 'workspace_path' in input data")

            # Parse UUIDs
            try:
                run_id = UUID(run_id_str) if isinstance(run_id_str, str) else run_id_str
                request_id = UUID(request_id_str) if isinstance(request_id_str, str) else (
                    request_id_str if request_id_str else run_id
                )
            except (ValueError, TypeError) as e:
                raise AgentExecutionError(f"Invalid UUID format: {str(e)}") from e

            # Load inventory via service
            inventory = await self.service.load_inventory(workspace_path)

            # Generate test plan via LLM (pass user_prompt and execution_plan for scope)
            user_prompt_text = input_data.get("user_prompt") or ""
            test_plan = await self._generate_test_plan(run_id, request_id, inventory, user_prompt_text, input_data)

            # Persist test plan (JSON)
            test_plan_path = await self.service.persist_test_plan(workspace_path, test_plan)

            # Generate markdown summary
            test_plan_md_path = await self.service.generate_markdown_summary(workspace_path, test_plan)

            self.logger.info(
                "test_design_agent_completed",
                run_id=str(run_id),
                scenarios=test_plan.coverage_summary.total_scenarios,
                path=test_plan_path,
                markdown_path=test_plan_md_path,
            )

            # Return output
            return {
                "success": True,
                "run_id": str(run_id),
                "request_id": str(request_id),
                "workspace_path": workspace_path,
                "test_plan_path": test_plan_path,
                "test_plan_md_path": test_plan_md_path,
                "scenario_count": test_plan.coverage_summary.total_scenarios,
                "modules": len(test_plan.modules),
                "message": f"Generated {test_plan.coverage_summary.total_scenarios} test scenarios across {len(test_plan.modules)} modules",
            }

        except AgentExecutionError:
            raise
        except Exception as e:
            self.logger.error("test_design_agent_failed", error=str(e))
            raise AgentExecutionError(f"Test design agent execution failed: {str(e)}")

    MAX_JSON_RETRIES = 3

    async def _complete_and_parse_json(self, user_prompt: str, system_prompt: str, model: str | None = None) -> dict:
        """Call the LLM and parse its JSON output, retrying on malformed JSON.

        Models — especially smaller ones — occasionally emit invalid JSON on long,
        exhaustive generations. A single bad response must not hard-fail the run,
        so the call is retried a bounded number of times before giving up. The raw
        response is never logged; only parse status is.
        """
        last_error = ""
        for attempt in range(1, self.MAX_JSON_RETRIES + 1):
            try:
                response = await self.llm_client.complete(
                    prompt=user_prompt,
                    system_prompt=system_prompt,
                    temperature=0.7,
                    max_tokens=self.llm_client.default_max_tokens,
                    model=model,
                )
            except Exception as e:
                raise AgentExecutionError(f"LLM analysis failed: {str(e)}") from e

            if not response:
                last_error = "LLM returned empty response"
            else:
                try:
                    return self._extract_json(response)
                except AgentExecutionError as e:
                    last_error = str(e)

            if attempt < self.MAX_JSON_RETRIES:
                self.logger.warning(
                    "test_design_json_retry",
                    attempt=attempt,
                    max_attempts=self.MAX_JSON_RETRIES,
                    error=last_error,
                )
                await asyncio.sleep(0.5 * attempt)

        raise AgentExecutionError(
            f"LLM returned invalid JSON after {self.MAX_JSON_RETRIES} attempts: {last_error}"
        )

    async def _generate_test_plan(
        self,
        run_id: UUID,
        request_id: UUID,
        inventory: Inventory,
        user_prompt_text: str = "",
        input_data: dict[str, Any] | None = None,
    ) -> TestPlan:
        """
        Generate test plan using LLM analysis of inventory.

        Phase 2: builds ParsedPromptIntent from ExecutionPlan.workflow_scope
        (single source of truth) instead of re-parsing the user prompt.

        Args:
            run_id: Run identifier
            request_id: Request correlation ID
            inventory: Application inventory
            user_prompt_text: Raw user prompt string (for LLM context only)
            input_data: Full execute() input dict (contains execution_plan)

        Returns:
            Generated TestPlan

        Raises:
            AgentExecutionError: If LLM analysis fails
        """
        # Phase 2: build ParsedPromptIntent from ExecutionPlan (single source of truth)
        # instead of re-parsing the user prompt or prompt_context directly.
        from app.services.prompt_builder import (
            ParsedPromptIntent,
            PromptBuildContext,
            get_prompt_builder,
        )
        execution_plan_dict = (input_data or {}).get("execution_plan") or {}
        selected_model = (input_data or {}).get("model")
        if isinstance(execution_plan_dict, dict):
            ws = execution_plan_dict.get("workflow_scope") or {}
        else:
            ws = {}
        parsed_intent = ParsedPromptIntent(
            raw_text=user_prompt_text,
            focus_areas=list(ws.get("included_modules") or []),
            excluded_modules=list(ws.get("excluded_modules") or []),
            included_pages=list(ws.get("included_pages") or []),
            excluded_pages=list(ws.get("excluded_pages") or []),
            coverage_preferences=list(ws.get("coverage_preferences") or []),
            output_preferences=list(ws.get("output_preferences") or []),
        )

        # Execution Scope Enforcement (Phase 5): the LLM must never receive the
        # complete inventory when the ExecutionPlan restricts scope. Filter the
        # inventory through the same resolver used by the crawler.
        from app.execution_scope.filtering import apply_execution_scope

        if execution_plan_dict:
            inventory = apply_execution_scope(inventory, execution_plan_dict)

        build_ctx = PromptBuildContext(
            agent_role="test-design-agent",
            user_prompt_raw=user_prompt_text,
            parsed_intent=parsed_intent,
        )
        final_prompt = get_prompt_builder().build(build_ctx)
        system_prompt = final_prompt.system_message
        # Prepend the builder's user-intent section to the inventory message

        # Build user prompt with inventory context
        inventory_json = inventory.model_dump(mode="json")
        inventory_summary = {
            "page_count": inventory.metadata.page_count,
            "form_count": inventory.metadata.form_count,
            "link_count": inventory.metadata.link_count,
            "button_count": inventory.metadata.button_count,
            "input_count": inventory.metadata.input_count,
            "table_count": inventory.metadata.table_count,
            "api_call_count": inventory.metadata.api_call_count,
            "user_flow_count": inventory.metadata.user_flow_count,
            "authenticated": inventory.statistics.authenticated if inventory.statistics else False,
            "auth_method": inventory.statistics.auth_method if inventory.statistics else "none",
            "max_depth_reached": inventory.statistics.max_depth_reached if inventory.statistics else 0,
        }

        # Build page listing for LLM
        pages_summary = []
        for page in inventory.pages:
            pages_summary.append({
                "id": str(page.page_id),
                "url": page.url,
                "title": page.title,
                "depth": page.depth,
            })

        # Build form listing
        forms_summary = []
        for form in inventory.forms:
            forms_summary.append({
                "page_id": str(form.page_id),
                "form_id": form.form_id,
                "action": form.action,
                "method": str(form.method) if form.method else None,
                "input_count": len(form.inputs),
            })

        # Build API listing
        api_summary = []
        for api in inventory.api_calls:
            api_summary.append({
                "method": str(api.method),
                "endpoint": api.endpoint,
                "page_id": str(api.page_id) if api.page_id else None,
            })

        # Build JSON strings for sections that contain dict literals (Python 3.12+ f-string compatibility)
        navigation_json = json.dumps(
            [{"source": str(e.source_page_id), "target": str(e.target_page_id), "text": e.link_text} for e in inventory.navigation.edges],
            indent=2,
        )
        user_flows_json = json.dumps(
            [{"name": u.name, "steps": len(u.steps)} for u in inventory.user_flows],
            indent=2,
        )
        inputs_json = json.dumps(
            [{"page_id": str(i.page_id), "type": i.input_type, "name": i.name, "required": i.required} for i in inventory.inputs],
            indent=2,
        )
        buttons_json = json.dumps(
            [{"page_id": str(b.page_id), "text": b.text, "type": str(b.button_type) if b.button_type else None} for b in inventory.buttons],
            indent=2,
        )
        tables_json = json.dumps(
            [{"page_id": str(t.page_id), "caption": t.caption, "rows": t.row_count, "cols": t.column_count} for t in inventory.tables],
            indent=2,
        )
        dialogs_json = json.dumps(
            [{"page_id": str(d.page_id), "type": str(d.dialog_type), "title": d.title} for d in inventory.dialogs],
            indent=2,
        )

        test_instructions_section = ""
        # Phase 5: PromptBuilder already assembled a user_message with parsed intent sections;
        # prepend it so the inventory context follows after.
        if final_prompt.user_message:
            test_instructions_section = f"\n{final_prompt.user_message}\n"
        elif user_prompt_text.strip():
            test_instructions_section = f"""
## User's Test Instructions

Focus specifically on these areas. The user wants:
{user_prompt_text}

Generate test scenarios that directly address these instructions.
"""

        user_prompt = f"""Analyze the following application inventory and generate a comprehensive test plan.{test_instructions_section}

## Inventory Summary
{json.dumps(inventory_summary, indent=2)}

## Pages
{json.dumps(pages_summary, indent=2)}

## Forms
{json.dumps(forms_summary, indent=2)}

## API Endpoints
{json.dumps(api_summary, indent=2)}

## Navigation Edges ({inventory.navigation.total_edges} total)
{navigation_json}

## User Flows ({len(inventory.user_flows)} total)
{user_flows_json}

## Input Fields ({inventory.metadata.input_count} total)
{inputs_json}

## Buttons ({inventory.metadata.button_count} total)
{buttons_json}

## Tables ({inventory.metadata.table_count} total)
{tables_json}

## Dialogs ({len(inventory.dialogs)} total)
{dialogs_json}

## Screenshots ({inventory.metadata.screenshot_count} total)

Generate a complete test plan as VALID JSON with this structure (use double quotes for strings, NOT single quotes):
{{
  "application_summary": {{
    "name": "...",
    "total_pages": N,
    "total_forms": N,
    "total_apis": N,
    "authentication_required": bool,
    "auth_method": "..."
  }},
  "modules": [
    {{
      "name": "...",
      "description": "...",
      "pages": ["..."],
      "scenarios": [
        {{
          "metadata": {{
            "id": "TC-001",
            "title": "...",
            "description": "...",
            "priority": "critical|high|medium|low",
            "category": "navigation|smoke|happy_path|functional|crud|validation|boundary|negative|authentication|authorization|session|accessibility|performance|regression|security|usability",
            "module": "...",
            "target_page": "...",
            "preconditions": ["..."],
            "test_steps": ["..."],
            "expected_result": "...",
            "required_test_data": ["..."],
            "tags": ["..."],
            "dependencies": ["..."],
            "risk_level": "high|medium|low"
          }},
          "use_cases": ["..."]
        }}
      ]
    }}
  ],
  "dependencies": {{
    "scenario_ids": ["..."],
    "required_data": ["..."],
    "required_state": ["..."]
  }},
  "test_priorities": {{
    "critical_paths": ["TC-..."],
    "high_priority": ["TC-..."],
    "medium_priority": ["TC-..."],
    "low_priority": ["TC-..."]
  }},
  "assumptions": {{
    "assumptions": ["..."],
    "constraints": ["..."],
    "risks": ["..."]
  }},
  "high_risk_areas": ["..."],
  "regression_candidates": ["TC-..."],
  "accessibility_recommendations": ["..."],
  "performance_recommendations": ["..."]
}}

IMPORTANT — Evidence-First Rule (highest priority):
- The inventory above is the ONLY source of truth. ONLY generate scenarios for pages, forms, and behaviors that are DIRECTLY EVIDENCED in the inventory.
- Do NOT invent, assume, or hallucinate pages, UI elements, error messages, or behaviors that are absent from the inventory — even if the user's instructions mention them.
- If the user's instructions reference a page or feature NOT present in the inventory, record it in assumptions.risks and generate AT MOST 1 placeholder scenario with expected_result: "INSUFFICIENT_EVIDENCE — this page/feature was not observed during crawling. Re-run the crawler targeting this page directly."
- The minimum scenario counts below apply ONLY to pages and forms that are PRESENT in the inventory.

IMPORTANT — Coverage Requirements (apply only to evidenced pages and forms):
- Assign each scenario a unique sequential ID: TC-001, TC-002, TC-003, ...
- For EVERY page present in the inventory, generate a MINIMUM of 8 scenarios.
- For EVERY form present in the inventory, generate AT LEAST: 1 happy-path, 1 empty-submit, 1 invalid-data, 1 boundary-value, 1 SQL-injection / XSS scenario.
- Each of these categories MUST appear at least once in the plan: smoke, happy_path, negative, validation, boundary, authentication, security.
- If the user's instructions mention a specific page or module, generate EXTRA depth for that area ONLY IF EVIDENCED IN THE INVENTORY (minimum 10 scenarios dedicated to it).
- DO NOT stop early. Generate ALL scenarios. Produce a thorough, exhaustive test plan that a senior QA engineer would be proud of.
- Group related scenarios into clearly named modules (e.g. "Login Module", "Dashboard Module", "Forms Module").
- Identify the top high-risk areas and mark at least 30% of scenarios as regression candidates."""

        # Call LLM and parse its JSON with a bounded retry on malformed output.
        response_data = await self._complete_and_parse_json(user_prompt, system_prompt, model=selected_model)

        def _safe_str(val: Any, default: str = "") -> str:
            if isinstance(val, dict):
                return val.get("value", val.get("name", default))
            return str(val) if val is not None else default

        # ── Renumber scenario IDs sequentially across all modules ──────
        all_raw_scenarios = response_data.get("test_scenarios", [])
        if not isinstance(all_raw_scenarios, list) or not all_raw_scenarios:
            all_raw_scenarios = []
            for mod in response_data.get("modules", []):
                all_raw_scenarios.extend(mod.get("scenarios", []))
            response_data["test_scenarios"] = all_raw_scenarios

        priorities = response_data.get("test_priorities", {})
        reg_candidates = response_data.get("regression_candidates", [])
        dep_ids = (response_data.get("dependencies", {}) or {}).get("scenario_ids", [])
        renumber_scenario_ids(
            modules=response_data.get("modules", []),
            all_scenarios=all_raw_scenarios,
            test_priorities=priorities if isinstance(priorities, dict) else {},
            regression_candidates=reg_candidates if isinstance(reg_candidates, list) else [],
            dependencies_scenario_ids=dep_ids if isinstance(dep_ids, list) else [],
        )

        # Build modules
        modules_data = response_data.get("modules", [])

        # Execution Scope Enforcement (Phase 5): drop any LLM-generated module
        # or scenario that falls outside ExecutionPlan scope before building the
        # TestPlan object. Scope data is only visible through the intent above.
        if execution_plan_dict:
            from app.execution_scope.filtering import filter_scenarios_by_scope
            from app.execution_scope.resolver import ExecutionScopeResolver

            scope_resolver = ExecutionScopeResolver(execution_plan_dict)
            modules_data, filtered_scenarios = filter_scenarios_by_scope(
                modules_data,
                all_raw_scenarios if isinstance(all_raw_scenarios, list) else [],
                scope_resolver,
            )
            response_data["modules"] = modules_data
            if isinstance(all_raw_scenarios, list):
                response_data["test_scenarios"] = filtered_scenarios

        modules = []
        all_scenarios = []
        for mod in modules_data:
            scenarios = []
            for sc in mod.get("scenarios", []):
                meta = sc.get("metadata", {})
                scenario = TestScenario(
                    metadata=ScenarioMetadata(
                        id=_safe_str(meta.get("id", "")),
                        title=_safe_str(meta.get("title", "")),
                        description=_safe_str(meta.get("description", "")),
                        priority=_coerce_enum(meta.get("priority", "medium"), Priority, Priority.MEDIUM),
                        category=_coerce_enum(
                            meta.get("category", "functional"),
                            TestCategory,
                            TestCategory.FUNCTIONAL,
                            _CATEGORY_SYNONYMS,
                        ),
                        module=_safe_str(meta.get("module", mod.get("name", ""))),
                        target_page=_safe_str(meta.get("target_page")),
                        preconditions=meta.get("preconditions", []),
                        test_steps=meta.get("test_steps", []),
                        expected_result=_safe_str(meta.get("expected_result", "")),
                        required_test_data=meta.get("required_test_data", []),
                        tags=meta.get("tags", []),
                        dependencies=meta.get("dependencies", []),
                        risk_level=_coerce_enum(meta.get("risk_level", "medium"), Risk, Risk.MEDIUM),
                    ),
                    use_cases=sc.get("use_cases", []),
                )
                scenarios.append(scenario)
                all_scenarios.append(scenario)

            modules.append(TestModule(
                name=mod.get("name", ""),
                description=mod.get("description", ""),
                pages=mod.get("pages", []),
                scenarios=scenarios,
            ))

        # Compute coverage summary
        by_category: dict[str, int] = {}
        by_priority: dict[str, int] = {}
        by_module: dict[str, int] = {}
        for sc in all_scenarios:
            cat = sc.metadata.category.value if hasattr(sc.metadata.category, "value") else str(sc.metadata.category)
            pri = sc.metadata.priority.value if hasattr(sc.metadata.priority, "value") else str(sc.metadata.priority)
            by_category[cat] = by_category.get(cat, 0) + 1
            by_priority[pri] = by_priority.get(pri, 0) + 1
            mod_name = sc.metadata.module
            by_module[mod_name] = by_module.get(mod_name, 0) + 1

        coverage = CoverageSummary(
            total_scenarios=len(all_scenarios),
            by_category=by_category,
            by_priority=by_priority,
            by_module=by_module,
            estimated_duration_minutes=len(all_scenarios) * 5,
        )

        deps_data = response_data.get("dependencies", {})
        priorities_data = response_data.get("test_priorities", {})
        assumptions_data = response_data.get("assumptions", {})

        # Determine auth
        auth_required = inventory.statistics.authenticated if inventory.statistics else False
        auth_method = inventory.statistics.auth_method if inventory.statistics else "none"

        app_summary_data = response_data.get("application_summary", {})

        test_plan = TestPlan(
            run_id=run_id,
            request_id=request_id,
            generated_at=datetime.now(UTC),
            application_summary=ApplicationSummary(
                name=app_summary_data.get("name", "Unknown"),
                total_pages=app_summary_data.get("total_pages", len(inventory.pages)),
                total_forms=app_summary_data.get("total_forms", len(inventory.forms)),
                total_apis=app_summary_data.get("total_apis", len(inventory.api_calls)),
                authentication_required=app_summary_data.get("authentication_required", auth_required),
                auth_method=app_summary_data.get("auth_method", auth_method),
            ),
            modules=modules,
            test_scenarios=all_scenarios,
            dependencies=ScenarioDependencies(
                scenario_ids=deps_data.get("scenario_ids", []),
                required_data=deps_data.get("required_data", []),
                required_state=deps_data.get("required_state", []),
            ),
            test_priorities=TestPriorities(
                critical_paths=priorities_data.get("critical_paths", []),
                high_priority=priorities_data.get("high_priority", []),
                medium_priority=priorities_data.get("medium_priority", []),
                low_priority=priorities_data.get("low_priority", []),
            ),
            assumptions=TestAssumptions(
                assumptions=assumptions_data.get("assumptions", []),
                constraints=assumptions_data.get("constraints", []),
                risks=assumptions_data.get("risks", []),
            ),
            high_risk_areas=response_data.get("high_risk_areas", []),
            regression_candidates=response_data.get("regression_candidates", []),
            accessibility_recommendations=response_data.get("accessibility_recommendations", []),
            performance_recommendations=response_data.get("performance_recommendations", []),
            coverage_summary=coverage,
        )

        return test_plan

    def get_system_prompt(self) -> str:
        """
        Get test design agent system prompt.

        Returns:
            System prompt string
        """
        return get_prompt("test-design-agent")
