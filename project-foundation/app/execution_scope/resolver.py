"""ExecutionScopeResolver — turns ExecutionPlan business scope into crawl/test scope.

The resolver is the ONLY component that decides whether a URL, page title, or
module name is inside the ExecutionPlan scope. It is deliberately NOT hardcoded
to any application: matching is driven by generic language-level keywords and
token overlap, then reinforced by routes discovered during the crawl itself
(navigation graph / page titles / URL structure).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from app.graph.evidence_providers import build_observed_state
from app.graph.expected_state import (
    CompletionEvidence,
    ExpectedStateGraph,
    ObservedState,
    calculate_state_diff,
)
from app.graph.goal_completion_engine import GoalCompletionEngine
from app.reasoning.models import CompletionCriterion, CompletionResult

_STOP_WORDS: frozenset[str] = frozenset({
    "the", "a", "an", "of", "and", "or", "to", "for", "in", "on", "at", "by",
    "page", "pages", "module", "modules", "flow", "flows", "workflow",
    "test", "testing", "tests", "management", "only", "just", "with", "within",
    "new", "add", "view", "list", "form", "screen", "section", "menu", "tab",
})

# Generic language-level synonyms (NOT application-specific URLs). Each maps a
# canonical token to the set of words that can express the same concept.
_SYNONYMS: dict[str, frozenset[str]] = {
    "login": frozenset({
        "login", "signin", "sign-in", "sign_in", "logon", "log-in", "log_in",
        "auth", "authenticate", "authentication", "oauth", "sso", "session",
        "sessions", "credential", "credentials", "account",
    }),
    "report": frozenset({"report", "reports", "analytics", "insight", "insights", "export", "exports"}),
    "setting": frozenset({"setting", "settings", "preference", "preferences", "config", "configuration", "profile", "profiles"}),
    "dashboard": frozenset({"dashboard", "dashboards", "home", "overview", "index", "workspace", "main", "landing"}),
    "create": frozenset({"create", "creating", "new", "add", "adding", "make"}),
    "edit": frozenset({"edit", "editing", "update", "updating", "modify"}),
    "delete": frozenset({"delete", "deleting", "remove", "removing"}),
    "approval": frozenset({"approve", "approval", "approvals", "review", "authorize", "authorization", "authorisations"}),
    "payment": frozenset({"payment", "payments", "pay", "checkout", "billing", "invoice", "invoices"}),
    "workflow": frozenset({"workflow", "workflows", "process", "processes", "pipeline"}),
    "user": frozenset({"user", "users", "account", "accounts"}),
    "search": frozenset({"search", "searches", "query", "queries"}),
    "customer": frozenset({"customer", "customers", "client", "clients"}),
    "notification": frozenset({"notification", "notifications", "alert", "alerts"}),
}

# Map of strategy name → Playwright --grep terms (used by the execution stage).
_COVERAGE_GREP: dict[str, list[str]] = {
    "boundary": ["boundary"],
    "smoke": ["smoke", "happy_path", "happy path"],
    "positive": ["positive", "happy_path", "happy path", "functional"],
    "negative": ["negative", "error", "invalid"],
    "authentication": ["auth", "login"],
    "authorization": ["auth", "permission", "access"],
    "security": ["security", "xss", "sql", "injection"],
    "performance": ["performance", "load", "stress"],
}


@dataclass
class ScopeDecision:
    """Outcome of a scope evaluation, with a human-readable reason."""

    allowed: bool
    reason: str = ""
    matched_module: str | None = None


@dataclass
class ModuleProfile:
    """Keyword profile for one business module."""

    name: str
    display_name: str
    tokens: frozenset[str] = field(default_factory=frozenset)
    keywords: frozenset[str] = field(default_factory=frozenset)
    grep_terms: list[str] = field(default_factory=list)


def _singularize(token: str) -> str:
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("ses") and not token.endswith("sses"):
        return token[:-2]
    if token.endswith("s") and not token.endswith("ss") and len(token) > 3:
        return token[:-1]
    return token


def _tokenize(value: str) -> frozenset[str]:
    """Lower-case token set from arbitrary text (module names, titles, URLs)."""
    tokens: set[str] = set()
    for part in re.split(r"[^a-z0-9]+", value.lower()):
        part = _singularize(part)
        if part and part not in _STOP_WORDS and not part.isdigit():
            tokens.add(part)
    return frozenset(tokens)


def _url_path(url: str) -> str:
    try:
        return urlsplit(url).path or "/"
    except ValueError:
        return url


def _canonicalize(url: str) -> str:
    try:
        parts = urlsplit(url.strip())
        if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
            return ""
        host = (parts.hostname or "").lower()
        path = parts.path or "/"
        while "//" in path:
            path = path.replace("//", "/")
        if path != "/":
            path = path.rstrip("/")
        return f"{parts.scheme.lower()}://{host}{path}"
    except ValueError:
        return ""


def _compile(pattern: str) -> re.Pattern:
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error:
        return re.compile(re.escape(pattern), re.IGNORECASE)


def derive_url_patterns(modules: list[str]) -> list[str]:
    """Derive generic URL slug patterns for module names (not app-specific)."""
    patterns: list[str] = []
    for name in modules:
        slug = re.sub(r"[^a-z0-9]+", r"(?:-|_|)", name.strip().lower())
        slug = re.sub(r"\(\?:-\|_\|\)$", "", slug)
        if slug and slug not in patterns:
            patterns.append(slug)
    return patterns


def _build_profile(name: str) -> ModuleProfile:
    clean = " ".join(name.split())
    tokens = _tokenize(clean)
    keywords: set[str] = set(tokens)
    for token in tokens:
        keywords.update(_SYNONYMS.get(token, ()))
    grep_terms = list(dict.fromkeys(list(tokens) + list(keywords)))[:6]
    return ModuleProfile(
        name=clean,
        display_name=clean,
        tokens=tokens,
        keywords=frozenset(keywords),
        grep_terms=grep_terms,
    )


def _matches_profile(url: str | None, title: str | None, profile: ModuleProfile) -> bool:
    if url:
        url_tokens = _tokenize(_url_path(url))
        if url_tokens & profile.keywords:
            return True
        if profile.name.lower() in url.lower():
            return True
    if title:
        title_tokens = _tokenize(title)
        if title_tokens & profile.keywords:
            return True
        if profile.name.lower() in title.lower():
            return True
    return False


def _matches_text(text: str, profile: ModuleProfile) -> bool:
    text_tokens = _tokenize(text)
    if text_tokens & profile.keywords:
        return True
    if profile.name.lower() in text.lower() or text.lower() in profile.name.lower():
        return True
    return False


class ExecutionScopeResolver:
    """Authoritative scope decision maker built from an ExecutionPlan."""

    def __init__(
        self,
        plan: Any = None,
        *,
        scope: dict[str, Any] | None = None,
        stopping_conditions: list[str] | None = None,
        base_url: str = "",
        target_url: str = "",
    ) -> None:
        ws = self._extract_scope(plan, scope)
        self.included_modules = [m for m in (ws.get("included_modules") or []) if m]
        self.excluded_modules = [m for m in (ws.get("excluded_modules") or []) if m]
        self.included_pages = [p for p in (ws.get("included_pages") or []) if p]
        self.excluded_pages = [p for p in (ws.get("excluded_pages") or []) if p]
        self.coverage_preferences = list(ws.get("coverage_preferences") or [])
        self.output_preferences = list(ws.get("output_preferences") or [])
        self._constraints = list(ws.get("__reasoning_constraints__") or [])
        self.stopping_conditions = (
            stopping_conditions
            or self._extract_stopping(plan)
            or []
        )
        self.completion_criteria = self._extract_completion_criteria(plan, scope)
        self.expected_state_graph = self._extract_expected_state_graph(plan, scope)

        # Chronological completion evidence (intent-derived graph path).
        self._evidence_history: list[CompletionEvidence] = []
        self._last_observed: ObservedState | None = None

        self.base_url = base_url
        self.target_url = target_url

        self._included_profiles = [_build_profile(m) for m in self.included_modules]
        self._excluded_profiles = [_build_profile(m) for m in self.excluded_modules]
        self._included_regex = [_compile(p) for p in self.included_pages]
        self._excluded_regex = [_compile(p) for p in self.excluded_pages]
        self._learned_routes: dict[str, list[str]] = {}
        self._restricted = bool(self.included_modules or self.included_pages)

    @staticmethod
    def _extract_scope(plan: Any, scope: dict[str, Any] | None) -> dict[str, Any]:
        if scope is not None:
            return scope
        if plan is None:
            return {}
        if isinstance(plan, dict):
            return plan.get("workflow_scope") or {}
        return getattr(plan, "workflow_scope", None) or {}

    @staticmethod
    def _extract_stopping(plan: Any) -> list[str]:
        if plan is None:
            return []
        if isinstance(plan, dict):
            conds = plan.get("stopping_conditions") or []
            if conds:
                return list(conds)
            strategy = plan.get("execution_strategy") or {}
            return list(strategy.get("stopping_conditions") or [])
        conds = getattr(plan, "stopping_conditions", None) or []
        if conds:
            return list(conds)
        strategy = getattr(plan, "execution_strategy", None) or {}
        return list(strategy.get("stopping_conditions") or [])

    def is_unconstrained(self) -> bool:
        """True when the plan places no scope restriction at all."""
        return (
            not self._restricted
            and not self.excluded_modules
            and not self.excluded_pages
            and not self.stopping_conditions
        )

    @property
    def restricted(self) -> bool:
        return self._restricted

    def summary(self) -> dict[str, Any]:
        return {
            "included_modules": list(self.included_modules),
            "excluded_modules": list(self.excluded_modules),
            "included_pages": list(self.included_pages),
            "excluded_pages": list(self.excluded_pages),
            "stopping_conditions": list(self.stopping_conditions),
            "restricted": self._restricted,
        }

    def evaluate(self, url: str, *, title: str | None = None) -> ScopeDecision:
        """Decide whether a URL/page may be crawled. Always returns a reason."""
        canonical = _canonicalize(url)
        if not canonical:
            return ScopeDecision(allowed=False, reason="Invalid or non-HTTP URL")

        for profile in self._excluded_profiles:
            if _matches_profile(canonical, title, profile):
                return ScopeDecision(
                    allowed=False,
                    reason=f"ExecutionPlan excluded {profile.display_name} module.",
                    matched_module=profile.name,
                )
        if self._excluded_regex and any(r.search(canonical) for r in self._excluded_regex):
            return ScopeDecision(allowed=False, reason="Matches excluded page pattern.")

        if not self._restricted:
            return ScopeDecision(allowed=True, reason="No include scope — crawl all.")

        for profile in self._included_profiles:
            if _matches_profile(canonical, title, profile):
                return ScopeDecision(
                    allowed=True,
                    reason=f"Required by included module {profile.display_name}.",
                    matched_module=profile.name,
                )

        path = _url_path(canonical)
        for profile in self._included_profiles:
            for prefix in self._learned_routes.get(profile.name, []):
                if path.startswith(prefix):
                    return ScopeDecision(
                        allowed=True,
                        reason=f"Required by discovered route of module {profile.display_name}.",
                        matched_module=profile.name,
                    )

        if self._included_regex and any(r.search(canonical) for r in self._included_regex):
            return ScopeDecision(allowed=True, reason="Matches included page pattern.")

        return ScopeDecision(allowed=False, reason="Outside execution scope.")

    def learn(self, url: str, *, title: str | None = None) -> str | None:
        """Record a discovered in-scope route for an included module.

        Lets the crawler follow multi-step workflows (e.g. /rrf/create then
        /rrf/approve) discovered from navigation graph / URL structure rather
        than from a fixed mapping.
        """
        if not self._included_profiles:
            return None
        canonical = _canonicalize(url) or url
        for profile in self._included_profiles:
            if _matches_profile(canonical, title, profile):
                path = _url_path(canonical)
                routes = self._learned_routes.setdefault(profile.name, [])
                segments = [s for s in path.split("/") if s]
                for i in range(1, len(segments) + 1):
                    prefix = "/" + "/".join(segments[:i])
                    if prefix not in routes:
                        routes.append(prefix)
                return profile.name
        return None

    @staticmethod
    def _extract_completion_criteria(plan: Any, scope: dict[str, Any] | None) -> list[Any]:
        if scope and "completion_criteria" in scope:
            return scope["completion_criteria"] or []
        if plan is None:
            return []
        if isinstance(plan, dict):
            cc = plan.get("completion_criteria") or []
            if cc:
                return list(cc)
            strategy = plan.get("execution_strategy") or {}
            return list(strategy.get("completion_criteria") or [])
        cc = getattr(plan, "completion_criteria", None) or []
        if cc:
            return list(cc)
        strategy = getattr(plan, "execution_strategy", None) or {}
        if hasattr(strategy, "get"):
            return list(strategy.get("completion_criteria") or [])
        return list(getattr(strategy, "completion_criteria", None) or [])

    @staticmethod
    def _extract_expected_state_graph(plan: Any, scope: dict[str, Any] | None) -> ExpectedStateGraph | None:
        """Extract the intent-derived ExpectedStateGraph from the plan/scope.

        The graph is the authoritative completion contract. When absent, the
        resolver falls back to legacy caller-supplied completion criteria —
        scope enforcement is NEVER bypassed.
        """
        raw = None
        if scope and scope.get("expected_state_graph"):
            raw = scope["expected_state_graph"]
        elif plan is not None:
            if isinstance(plan, dict):
                raw = plan.get("expected_state_graph") or {}
            else:
                raw = getattr(plan, "expected_state_graph", None) or {}
        if not raw:
            return None
        if isinstance(raw, ExpectedStateGraph):
            return raw
        if isinstance(raw, dict):
            try:
                return ExpectedStateGraph(**raw)
            except Exception:
                return None
        return None

    def evaluate_completion(
        self,
        *,
        url: str | None = None,
        title: str | None = None,
        auth_succeeded: bool = False,
        form_submitted: bool = False,
        capability: str | None = None,
        observations: dict[str, Any] | None = None,
    ) -> CompletionResult:
        """Evaluate completion against current runtime state.

        When an intent-derived ExpectedStateGraph is present, evaluation flows
        through the semantics-free GoalCompletionEngine over a chronological
        evidence history. A capability executing successfully (e.g.
        ``authenticate()``) does NOT imply GOAL_COMPLETED — the graph decides
        whether the observed transition satisfies the expected transition.

        Otherwise (legacy caller-supplied criteria) the previous evaluator is
        used for backward compatibility.
        """
        if self.expected_state_graph is not None:
            return self._evaluate_graph(
                url=url, title=title, auth_succeeded=auth_succeeded,
                form_submitted=form_submitted, capability=capability,
                observations=observations,
            )

        if not self.completion_criteria:
            return CompletionResult(satisfied=False, matched_criteria=[], reason="No completion criteria defined")

        matched: list[str] = []
        failed: list[str] = []

        for item in self.completion_criteria:
            if isinstance(item, dict):
                criterion = CompletionCriterion(**item)
            elif isinstance(item, CompletionCriterion):
                criterion = item
            else:
                continue

            signal = criterion.signal
            pattern = criterion.target_pattern
            desc = criterion.description

            is_met = False

            if signal == "auth_success":
                is_met = auth_succeeded
            elif signal == "url_changed":
                if url:
                    is_met = not bool(re.search(pattern, url, re.IGNORECASE)) if pattern else True
                else:
                    is_met = auth_succeeded
            elif signal == "page_reached":
                text_to_check = f"{url or ''} {title or ''}"
                is_met = bool(re.search(pattern, text_to_check, re.IGNORECASE)) if pattern else False
            elif signal == "element_absent":
                is_met = auth_succeeded
            elif signal in ("form_submitted", "action_completed"):
                # form_submitted is kept for backward-compatible callers;
                # action_completed is the generic derived signal.
                is_met = form_submitted
            else:
                is_met = False

            if is_met:
                matched.append(desc)
            elif criterion.required:
                failed.append(desc)

        all_required_met = (len(failed) == 0) and (len(matched) > 0)
        reason = f"Matched: {', '.join(matched)}" if all_required_met else f"Pending required criteria: {', '.join(failed)}"

        return CompletionResult(
            satisfied=all_required_met,
            matched_criteria=matched,
            reason=reason,
        )

    def reset_completion_state(self) -> None:
        """Reset chronological completion evidence (new crawl run)."""
        self._evidence_history.clear()
        self._last_observed = None

    def record_action(
        self,
        capability: str,
        *,
        url: str | None = None,
        title: str | None = None,
        auth_succeeded: bool = False,
        form_submitted: bool = False,
        observations: dict[str, Any] | None = None,
    ) -> CompletionResult:
        """Record an executed capability as chronological evidence and evaluate."""
        return self.evaluate_completion(
            url=url,
            title=title,
            auth_succeeded=auth_succeeded,
            form_submitted=form_submitted,
            capability=capability,
            observations=observations,
        )

    def _evaluate_graph(
        self,
        *,
        url: str | None,
        title: str | None,
        auth_succeeded: bool,
        form_submitted: bool,
        capability: str | None,
        observations: dict[str, Any] | None,
    ) -> CompletionResult:
        """Graph path: build ObservedState, compute diff, append evidence, evaluate."""
        observations = observations or {}
        action_results = dict(observations.get("action_results") or {})
        if form_submitted:
            action_results["form_submitted"] = True

        current = build_observed_state(
            url=url,
            title=title,
            authenticated=auth_succeeded,
            dom_observations=observations.get("dom") or {},
            network_observations=observations.get("network") or [],
            storage_observations=observations.get("storage") or {},
            accessibility_observations=observations.get("accessibility") or {},
            browser_events=observations.get("browser_events") or [],
            screenshots=observations.get("screenshots") or [],
            action_results=action_results,
        )

        previous = self._last_observed or ObservedState(timestamp=0.0)
        diff = calculate_state_diff(previous, current)

        evidence = CompletionEvidence(
            timestamp=current.timestamp,
            source_state=previous,
            target_state=current,
            diff=diff,
            capability=capability or "",
            evidence=observations,
        )
        self._evidence_history.append(evidence)
        self._last_observed = current

        evaluation = GoalCompletionEngine.evaluate_history(
            self._evidence_history, self.expected_state_graph
        )

        return CompletionResult(
            satisfied=evaluation.goal_achieved,
            matched_criteria=list(evaluation.matched_transitions),
            reason=evaluation.reason,
        )

    def stopping_condition_hit(self, url: str, *, title: str | None = None) -> str | None:
        """Return the satisfied stopping condition, if any."""
        if not self.stopping_conditions:
            return None
        for condition in self.stopping_conditions:
            profile = _build_profile(condition)
            if _matches_profile(url, title, profile):
                return condition
        return None

    def module_allowed(self, module_name: str | None) -> bool:
        """Decide whether a test-plan module/scenario name is in scope."""
        if not module_name:
            return True
        for profile in self._excluded_profiles:
            if _matches_text(module_name, profile):
                return False
        if not self._restricted:
            return True
        for profile in self._included_profiles:
            if _matches_text(module_name, profile):
                return True
        return False

    def url_allowed(self, url: str) -> bool:
        return self.evaluate(url).allowed


def coerce_resolver(
    plan: Any = None,
    *,
    scope: dict[str, Any] | None = None,
    resolver: ExecutionScopeResolver | None = None,
) -> ExecutionScopeResolver:
    """Return the provided resolver or build one from an ExecutionPlan/scope."""
    if resolver is not None:
        return resolver
    return ExecutionScopeResolver(plan, scope=scope)


def build_scope_grep(plan: Any = None, *, scope: dict[str, Any] | None = None) -> str | None:
    """Build a Playwright --grep pattern from module + coverage scope."""
    resolver = coerce_resolver(plan, scope=scope)
    terms: list[str] = []
    if resolver._restricted:
        for profile in resolver._included_profiles:
            for term in profile.grep_terms:
                if term not in terms:
                    terms.append(term)
    for coverage in resolver.coverage_preferences:
        low = coverage.lower()
        if low in ("all", "full", "comprehensive", ""):
            continue
        for term in _COVERAGE_GREP.get(low, [low]):
            if term not in terms:
                terms.append(term)
    if not terms:
        return None
    return "|".join(terms)
