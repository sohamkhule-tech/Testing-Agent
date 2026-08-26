"""Shared scope filters applied to inventory and test plans.

Every downstream consumer (inventory aggregator, test design, code generation)
applies the SAME ExecutionScopeResolver so that no stage ever receives data
outside ExecutionPlan scope.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.execution_scope.resolver import ExecutionScopeResolver, coerce_resolver
from app.schemas.inventory import (
    Inventory,
    InventoryMetadata,
    InventoryNavigation,
    InventoryStatistics,
)
from app.schemas.review import ApprovedTestPlan


def _canon_page_key(url: str) -> str:
    return (url or "").rstrip("/").lower()


def apply_execution_scope(
    inventory: Inventory,
    plan: Any = None,
    *,
    scope: dict[str, Any] | None = None,
    resolver: ExecutionScopeResolver | None = None,
) -> Inventory:
    """Return a filtered copy of the inventory restricted to ExecutionPlan scope.

    Filters pages, all page-keyed elements, navigation edges, links, API calls,
    user flows and screenshots. Returns the inventory unchanged when the plan
    imposes no scope restriction.
    """
    scope_resolver = coerce_resolver(plan, scope=scope, resolver=resolver)
    if scope_resolver.is_unconstrained():
        return inventory

    allowed_pages = []
    allowed_ids: set[UUID] = set()
    blocked_ids: set[UUID] = set()
    allowed_urls: set[str] = set()
    blocked_urls: set[str] = set()

    for page in inventory.pages:
        decision = scope_resolver.evaluate(page.url, title=page.title)
        if decision.allowed:
            allowed_pages.append(page)
            allowed_ids.add(page.page_id)
            allowed_urls.add(_canon_page_key(page.url))
        else:
            blocked_ids.add(page.page_id)
            blocked_urls.add(_canon_page_key(page.url))

    def _page_id_ok(page_id: UUID | None) -> bool:
        if page_id is None:
            return True
        return page_id in allowed_ids

    forms = [f for f in inventory.forms if _page_id_ok(f.page_id)]
    inputs = [i for i in inventory.inputs if _page_id_ok(i.page_id)]
    buttons = [b for b in inventory.buttons if _page_id_ok(b.page_id)]
    checkboxes = [c for c in inventory.checkboxes if _page_id_ok(c.page_id)]
    radio_buttons = [r for r in inventory.radio_buttons if _page_id_ok(r.page_id)]
    dropdowns = [d for d in inventory.dropdowns if _page_id_ok(d.page_id)]
    tables = [t for t in inventory.tables if _page_id_ok(t.page_id)]
    dialogs = [d for d in inventory.dialogs if _page_id_ok(d.page_id)]
    uploads = [u for u in inventory.uploads if _page_id_ok(u.page_id)]
    downloads = [d for d in inventory.downloads if _page_id_ok(d.page_id)]
    screenshots = [s for s in inventory.screenshots if _page_id_ok(s.page_id)]
    api_calls = [a for a in inventory.api_calls if _page_id_ok(a.page_id)]
    authentication = [a for a in inventory.authentication if _page_id_ok(a.page_id)]

    def _edge_ok(edge: Any) -> bool:
        return (
            edge.source_page_id in allowed_ids
            and edge.target_page_id in allowed_ids
        )

    edges = [e for e in inventory.navigation.edges if _edge_ok(e)]
    navigation = InventoryNavigation(
        edges=edges,
        root_page_id=(
            inventory.navigation.root_page_id
            if inventory.navigation.root_page_id in allowed_ids
            else (allowed_pages[0].page_id if allowed_pages else None)
        ),
        total_edges=len(edges),
    )

    links = []
    for target_url, text, source_url in inventory.links:
        source_key = _canon_page_key(source_url)
        target_key = _canon_page_key(target_url)
        source_allowed = (
            source_url and (source_key in allowed_urls or source_key not in blocked_urls)
        )
        target_allowed = (
            target_url
            and (target_key in allowed_urls or scope_resolver.evaluate(target_url).allowed)
        )
        if source_allowed and target_allowed:
            links.append((target_url, text, source_url))

    user_flows = []
    for flow in inventory.user_flows:
        if flow.start_url:
            if scope_resolver.evaluate(flow.start_url).allowed:
                user_flows.append(flow)
        else:
            user_flows.append(flow)

    total_links = len(links)
    avg_response = 0.0
    if allowed_pages:
        avg_response = sum(p.response_time for p in allowed_pages) / len(allowed_pages)
    max_depth = max((p.depth for p in allowed_pages), default=0)
    stats = inventory.statistics or InventoryStatistics()
    statistics = InventoryStatistics(
        total_pages=len(allowed_pages),
        total_forms=len(forms),
        total_buttons=len(buttons),
        total_inputs=len(inputs),
        total_links=total_links,
        total_tables=len(tables),
        total_dialogs=len(dialogs),
        total_uploads=len(uploads),
        total_downloads=len(downloads),
        total_api_calls=len(api_calls),
        total_user_flows=len(user_flows),
        total_screenshots=len(screenshots),
        average_response_time_ms=round(avg_response, 2),
        max_depth_reached=max_depth,
        authenticated=stats.authenticated,
        auth_method=stats.auth_method,
    )

    metadata = inventory.metadata
    filtered_metadata = InventoryMetadata(
        run_id=metadata.run_id,
        request_id=metadata.request_id,
        application_id=metadata.application_id,
        generated_at=metadata.generated_at,
        source_files=list(metadata.source_files),
        page_count=len(allowed_pages),
        form_count=len(forms),
        link_count=total_links,
        button_count=len(buttons),
        input_count=len(inputs),
        table_count=len(tables),
        api_call_count=len(api_calls),
        user_flow_count=len(user_flows),
        screenshot_count=len(screenshots),
        duplicate_pages_removed=metadata.duplicate_pages_removed,
        duplicate_links_removed=metadata.duplicate_links_removed,
        excluded_modules=list(metadata.excluded_modules),
        excluded_page_count=len(blocked_ids),
        errors=list(metadata.errors),
    )

    return Inventory(
        metadata=filtered_metadata,
        pages=allowed_pages,
        navigation=navigation,
        forms=forms,
        inputs=inputs,
        dropdowns=dropdowns,
        checkboxes=checkboxes,
        radio_buttons=radio_buttons,
        buttons=buttons,
        links=links,
        tables=tables,
        dialogs=dialogs,
        uploads=uploads,
        downloads=downloads,
        authentication=authentication,
        api_calls=api_calls,
        user_flows=user_flows,
        screenshots=screenshots,
        statistics=statistics,
    )


def _scenario_module(scenario: dict[str, Any]) -> str:
    meta = scenario.get("metadata") or {}
    return str(meta.get("module") or "")


def filter_scenarios_by_scope(
    modules: list[dict[str, Any]],
    scenarios: list[dict[str, Any]],
    resolver: ExecutionScopeResolver,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Drop modules/scenarios outside ExecutionPlan scope (before object build)."""
    # Collect scenarios from modules if top-level list is empty
    if not scenarios:
        scenarios = []
        for mod in modules:
            scenarios.extend(mod.get("scenarios") or [])

    if resolver.is_unconstrained():
        return modules, scenarios

    kept_modules: list[dict[str, Any]] = []
    kept_scenarios: list[dict[str, Any]] = []

    for mod in modules:
        mod_name = str(mod.get("name") or "")
        if not resolver.module_allowed(mod_name):
            continue

        mod_scenarios: list[dict[str, Any]] = []
        for s in (mod.get("scenarios") or []):
            meta = s.get("metadata") or {}
            target_page = str(meta.get("target_page") or "")
            mod_field = str(meta.get("module") or mod_name)
            # Scenario is kept if its module is allowed OR its target_page is allowed OR by default when module matches
            if resolver.module_allowed(mod_field) or (target_page and resolver.evaluate(target_page).allowed) or resolver.module_allowed(mod_name):
                mod_scenarios.append(s)
                if s not in kept_scenarios:
                    kept_scenarios.append(s)

        kept_modules.append({**mod, "scenarios": mod_scenarios})

    return kept_modules, kept_scenarios


def _recompute_coverage(test_plan_data: dict[str, Any]) -> None:
    scenarios = test_plan_data.get("test_scenarios") or []
    by_category: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    by_module: dict[str, int] = {}
    for s in scenarios:
        meta = s.get("metadata") or {}
        cat = str(meta.get("category") or "functional")
        pri = str(meta.get("priority") or "medium")
        mod = str(meta.get("module") or "unknown")
        by_category[cat] = by_category.get(cat, 0) + 1
        by_priority[pri] = by_priority.get(pri, 0) + 1
        by_module[mod] = by_module.get(mod, 0) + 1
    coverage = test_plan_data.setdefault("coverage_summary", {})
    coverage["total_scenarios"] = len(scenarios)
    coverage["by_category"] = by_category
    coverage["by_priority"] = by_priority
    coverage["by_module"] = by_module
    coverage["estimated_duration_minutes"] = len(scenarios) * 5
    test_plan_data["coverage_summary"] = coverage


def filter_approved_plan_by_scope(
    plan_data: dict[str, Any],
    plan: Any = None,
    *,
    scope: dict[str, Any] | None = None,
    resolver: ExecutionScopeResolver | None = None,
) -> dict[str, Any]:
    """Filter an approved plan's modules/scenarios to ExecutionPlan scope."""
    scope_resolver = coerce_resolver(plan, scope=scope, resolver=resolver)
    if scope_resolver.is_unconstrained():
        return plan_data

    modules = plan_data.get("modules") or []
    scenarios = plan_data.get("test_scenarios") or []
    kept_modules, kept_scenarios = filter_scenarios_by_scope(modules, scenarios, scope_resolver)
    plan_data["modules"] = kept_modules
    plan_data["test_scenarios"] = kept_scenarios
    _recompute_coverage(plan_data)
    return plan_data


def filter_approved_plan_object(
    approved_plan: ApprovedTestPlan,
    plan: Any = None,
    *,
    scope: dict[str, Any] | None = None,
    resolver: ExecutionScopeResolver | None = None,
) -> ApprovedTestPlan:
    """Filter an ApprovedTestPlan object in place and return it."""
    filter_approved_plan_by_scope(
        approved_plan.test_plan_data,
        plan=plan,
        scope=scope,
        resolver=resolver,
    )
    return approved_plan
