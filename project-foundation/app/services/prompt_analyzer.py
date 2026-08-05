"""
Prompt Analyzer Service

Transforms a raw user prompt into a transparent, structured execution plan
that the user can review and approve before any crawling begins.

Reuses the existing PromptParser and PromptBuilder — adds a layer on top
that generates confidence scores, ambiguity warnings, quality scoring, and
a deterministic execution plan.

No LLM calls are required — all analysis is deterministic from the parsed
ParsedPromptIntent, making the endpoint fast (~10 ms) and free.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.logging import LoggerMixin
from app.services.prompt_builder import (
    AuthContext,
    ParsedPromptIntent,
    PromptParser,
    get_prompt_parser,
)


# ---------------------------------------------------------------------------
# Data structures returned by PromptAnalyzer
# ---------------------------------------------------------------------------


@dataclass
class ConfidenceItem:
    label: str
    value: int           # 0-100
    category: str        # "scope" | "exclude" | "coverage" | "output" | "auth"
    is_low: bool = False # True when value < 75


@dataclass
class ExecutionStep:
    step: int
    label: str
    description: str
    icon: str            # emoji / icon hint for UI


@dataclass
class CredentialStatus:
    username_detected: bool = False
    password_detected: bool = False
    login_url_detected: bool = False
    is_complete: bool = False
    warnings: list[str] = field(default_factory=list)


@dataclass
class PromptQuality:
    score: int                            # 0-100
    strengths: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


@dataclass
class Ambiguity:
    phrase: str
    message: str
    suggestions: list[str] = field(default_factory=list)


@dataclass
class ScopeSummary:
    included_modules: list[str] = field(default_factory=list)
    excluded_modules: list[str] = field(default_factory=list)
    included_pages: list[str] = field(default_factory=list)
    excluded_pages: list[str] = field(default_factory=list)


@dataclass
class EstimatedStats:
    modules_estimate: int = 0
    pages_range: str = "unknown"
    scenarios_range: str = "unknown"
    framework: str = "Playwright"
    requires_auth: bool = False
    estimated_runtime_minutes: int = 3


@dataclass
class PromptAnalysis:
    """
    Full analysis result returned to the frontend.
    Contains everything the user needs to understand what the AI will do.
    """

    analysis_id: str
    raw_prompt: str                          # redacted
    interpretation: dict[str, Any]
    confidence_scores: list[ConfidenceItem]
    execution_plan: list[ExecutionStep]
    quality: PromptQuality
    ambiguities: list[Ambiguity]
    credential_status: CredentialStatus
    scope_summary: ScopeSummary
    estimated: EstimatedStats
    reasoning_steps: list[str]              # in-order steps for live-reasoning animation
    parsed_intent: dict[str, Any]           # ParsedPromptIntent.to_dict() — for passing to run creation

    def to_dict(self) -> dict:
        return {
            "analysis_id": self.analysis_id,
            "raw_prompt": self.raw_prompt,
            "interpretation": self.interpretation,
            "confidence_scores": [
                {"label": c.label, "value": c.value, "category": c.category, "is_low": c.is_low}
                for c in self.confidence_scores
            ],
            "execution_plan": [
                {"step": s.step, "label": s.label, "description": s.description, "icon": s.icon}
                for s in self.execution_plan
            ],
            "quality": {
                "score": self.quality.score,
                "strengths": self.quality.strengths,
                "suggestions": self.quality.suggestions,
            },
            "ambiguities": [
                {"phrase": a.phrase, "message": a.message, "suggestions": a.suggestions}
                for a in self.ambiguities
            ],
            "credential_status": {
                "username_detected": self.credential_status.username_detected,
                "password_detected": self.credential_status.password_detected,
                "login_url_detected": self.credential_status.login_url_detected,
                "is_complete": self.credential_status.is_complete,
                "warnings": self.credential_status.warnings,
            },
            "scope_summary": {
                "included_modules": self.scope_summary.included_modules,
                "excluded_modules": self.scope_summary.excluded_modules,
                "included_pages": self.scope_summary.included_pages,
                "excluded_pages": self.scope_summary.excluded_pages,
            },
            "estimated": {
                "modules_estimate": self.estimated.modules_estimate,
                "pages_range": self.estimated.pages_range,
                "scenarios_range": self.estimated.scenarios_range,
                "framework": self.estimated.framework,
                "requires_auth": self.estimated.requires_auth,
                "estimated_runtime_minutes": self.estimated.estimated_runtime_minutes,
            },
            "reasoning_steps": self.reasoning_steps,
            "parsed_intent": self.parsed_intent,
        }


# ---------------------------------------------------------------------------
# Ambiguous phrase patterns
# ---------------------------------------------------------------------------

_AMBIGUOUS_PATTERNS: list[tuple[str, str, list[str]]] = [
    (
        r"\bimportant\s+pages?\b",
        "The phrase 'important pages' is ambiguous — the AI cannot determine which pages you consider important.",
        ["Reports", "Dashboard", "Orders", "Settings"],
    ),
    (
        r"\bmain\s+(?:pages?|features?|modules?)\b",
        "The phrase 'main features' is ambiguous without specifying which modules are primary.",
        ["Dashboard", "Reports", "Analytics"],
    ),
    (
        r"\bsome\s+(?:pages?|tests?|modules?)\b",
        "'Some' is not specific enough. Please list the modules you want tested.",
        [],
    ),
    (
        r"\bbasic\s+tests?\b",
        "'Basic tests' is vague. Did you mean smoke tests or functional tests?",
        ["smoke", "functional"],
    ),
    (
        r"\ball\s+pages?\b",
        "'All pages' will result in a full crawl with no scope restrictions. Confirm this is intentional.",
        [],
    ),
    (
        r"\beverything\b",
        "'Everything' means no exclusions. This may produce a large test plan. Consider narrowing scope.",
        [],
    ),
]


# ---------------------------------------------------------------------------
# Framework detection
# ---------------------------------------------------------------------------

_FRAMEWORK_PATTERNS: list[tuple[str, str]] = [
    (r"\bpage\s+object\s+model\b|\bpom\b", "Playwright + Page Object Model"),
    (r"\bselenium\b", "Selenium"),
    (r"\bcypress\b", "Cypress"),
    (r"\bpuppeteer\b", "Puppeteer"),
    (r"\bplaywright\b", "Playwright"),
    (r"\bjest\b", "Jest"),
    (r"\bvitest\b", "Vitest"),
]


# ---------------------------------------------------------------------------
# PromptAnalyzer
# ---------------------------------------------------------------------------


class PromptAnalyzer(LoggerMixin):
    """
    Converts a raw user prompt into a PromptAnalysis.

    Fast, deterministic, no LLM required.
    The parser is injected so callers can share the singleton.
    """

    def __init__(self, parser: PromptParser | None = None) -> None:
        super().__init__()
        self._parser = parser or get_prompt_parser()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, raw_prompt: str, project_name: str = "") -> PromptAnalysis:
        """
        Analyze the raw user prompt.

        Args:
            raw_prompt: The user's free-text instructions (may contain credentials).
            project_name: Optional project name for context.

        Returns:
            PromptAnalysis — never raises.
        """
        try:
            return self._analyze(raw_prompt, project_name)
        except Exception as e:
            self.logger.error("prompt_analysis_failed", error=str(e))
            # Return a safe minimal analysis so the endpoint never fails
            return self._empty_analysis(raw_prompt)

    # ------------------------------------------------------------------
    # Private implementation
    # ------------------------------------------------------------------

    def _analyze(self, raw_prompt: str, project_name: str) -> PromptAnalysis:
        analysis_id = str(uuid.uuid4())
        reasoning: list[str] = ["Analyzing instructions..."]

        # Step 1 — parse
        intent, auth = self._parser.parse(raw_prompt)
        reasoning.append("Parsing prompt structure...")

        # Step 2 — credential status
        cred_status = self._build_credential_status(auth, intent)
        if cred_status.is_complete:
            reasoning.append("Authentication detected...")
        elif cred_status.username_detected or cred_status.password_detected:
            reasoning.append("Partial credentials detected...")

        # Step 3 — scope summary
        scope = self._build_scope_summary(intent)
        if scope.included_modules:
            reasoning.append(f"{', '.join(scope.included_modules[:3])} module(s) selected...")
        if scope.excluded_modules:
            reasoning.append(f"{', '.join(scope.excluded_modules[:3])} module(s) excluded...")

        # Step 4 — coverage / output detection
        if intent.coverage_preferences:
            reasoning.append(f"Coverage strategy detected: {', '.join(intent.coverage_preferences)}...")
        if intent.output_preferences:
            reasoning.append(f"Output preferences: {', '.join(intent.output_preferences[:2])}...")

        # Step 5 — ambiguity detection
        ambiguities = self._detect_ambiguities(raw_prompt)
        if ambiguities:
            reasoning.append(f"Detected {len(ambiguities)} ambiguous instruction(s) — review required...")

        # Step 6 — confidence scores
        confidence = self._build_confidence_scores(intent, auth, scope)

        # Step 7 — quality score
        quality = self._build_quality_score(intent, auth, ambiguities, raw_prompt)

        # Step 8 — execution plan
        exec_plan = self._build_execution_plan(intent, auth, cred_status)
        reasoning.append("Execution plan created...")

        # Step 9 — estimates
        estimated = self._build_estimates(intent, auth, cred_status)

        # Step 10 — interpretation summary
        interpretation = self._build_interpretation(intent, auth, cred_status, scope, raw_prompt)

        return PromptAnalysis(
            analysis_id=analysis_id,
            raw_prompt=intent.raw_text,   # already redacted by parser
            interpretation=interpretation,
            confidence_scores=confidence,
            execution_plan=exec_plan,
            quality=quality,
            ambiguities=ambiguities,
            credential_status=cred_status,
            scope_summary=scope,
            estimated=estimated,
            reasoning_steps=reasoning,
            parsed_intent=intent.to_dict(),
        )

    # ------------------------------------------------------------------

    def _build_credential_status(self, auth: AuthContext, intent: ParsedPromptIntent) -> CredentialStatus:
        warnings: list[str] = []
        if auth.username and not auth.password:
            warnings.append("Password not detected. Crawler cannot log in without a password.")
        if auth.password and not auth.username:
            warnings.append("Username/email not detected. Crawler cannot log in without a username.")
        if auth.is_populated() and not auth.login_url:
            warnings.append("Login URL not specified. The crawler will attempt to detect the login page automatically.")

        return CredentialStatus(
            username_detected=bool(auth.username),
            password_detected=bool(auth.password),
            login_url_detected=bool(auth.login_url),
            is_complete=auth.is_populated(),
            warnings=warnings,
        )

    def _build_scope_summary(self, intent: ParsedPromptIntent) -> ScopeSummary:
        return ScopeSummary(
            included_modules=list(intent.focus_areas),
            excluded_modules=list(intent.excluded_modules),
            included_pages=list(intent.included_pages),
            excluded_pages=list(intent.excluded_pages),
        )

    def _detect_ambiguities(self, text: str) -> list[Ambiguity]:
        found: list[Ambiguity] = []
        lower = text.lower()
        for pattern, message, suggestions in _AMBIGUOUS_PATTERNS:
            if re.search(pattern, lower):
                # Extract the matched phrase
                m = re.search(pattern, lower)
                phrase = m.group(0) if m else pattern
                found.append(Ambiguity(phrase=phrase, message=message, suggestions=suggestions))
        return found

    def _build_confidence_scores(
        self,
        intent: ParsedPromptIntent,
        auth: AuthContext,
        scope: ScopeSummary,
    ) -> list[ConfidenceItem]:
        items: list[ConfidenceItem] = []
        uses_headers = bool(re.search(r"^#{1,3}\s+\w+", intent.raw_text, re.MULTILINE))

        for module in scope.included_modules:
            # Longer, more specific module names → higher confidence
            conf = min(99, 70 + len(module) * 2) if not uses_headers else 97
            items.append(ConfidenceItem(label=module, value=conf, category="scope", is_low=conf < 75))

        for module in scope.excluded_modules:
            conf = min(98, 72 + len(module) * 2) if not uses_headers else 96
            items.append(ConfidenceItem(label=f"Exclude: {module}", value=conf, category="exclude", is_low=conf < 75))

        for cov in intent.coverage_preferences:
            conf = 95 if uses_headers else 85
            items.append(ConfidenceItem(label=cov.capitalize(), value=conf, category="coverage", is_low=conf < 75))

        for out in intent.output_preferences:
            conf = 93 if uses_headers else 78
            items.append(ConfidenceItem(label=out, value=conf, category="output", is_low=conf < 75))

        # Framework detection (from custom_instructions + output_prefs)
        full_text = (intent.raw_text + " " + intent.custom_instructions).lower()
        for pattern, label in _FRAMEWORK_PATTERNS:
            if re.search(pattern, full_text, re.IGNORECASE):
                conf = 95 if "pom" in full_text or "page object" in full_text else 88
                if not any(c.label == label for c in items):
                    items.append(ConfidenceItem(label=label, value=conf, category="output", is_low=conf < 75))

        if auth.is_populated():
            items.append(ConfidenceItem(label="Credentials", value=100, category="auth", is_low=False))
        elif auth.username or auth.password:
            items.append(ConfidenceItem(label="Partial Credentials", value=60, category="auth", is_low=True))

        return items

    def _build_quality_score(
        self,
        intent: ParsedPromptIntent,
        auth: AuthContext,
        ambiguities: list[Ambiguity],
        raw_text: str,
    ) -> PromptQuality:
        score = 0
        strengths: list[str] = []
        suggestions: list[str] = []

        # Scoring dimensions (total = 100)
        if intent.focus_areas:
            score += 25
            strengths.append("Clear test scope defined")
        else:
            suggestions.append("Specify which modules or pages to test (e.g. 'Focus on Reports and Dashboard')")

        if intent.excluded_modules or intent.excluded_pages:
            score += 10
            strengths.append("Exclusions specified")
        else:
            suggestions.append("Consider specifying modules to skip to reduce test noise")

        if intent.coverage_preferences:
            score += 20
            strengths.append(f"Test type specified: {', '.join(intent.coverage_preferences)}")
        else:
            suggestions.append("Specify test type (e.g. 'Generate negative scenarios' or 'Smoke tests only')")

        if auth.is_populated():
            score += 20
            strengths.append("Complete credentials supplied")
        elif auth.username or auth.password:
            score += 8
            suggestions.append("Credentials are incomplete — provide both username and password")
        else:
            suggestions.append("If login is required, provide credentials via the Authentication fields")

        if intent.output_preferences:
            score += 10
            strengths.append("Output framework or style specified")
        else:
            suggestions.append("Specify framework preferences (e.g. 'Use Playwright Page Object Model')")

        prompt_len = len(raw_text.strip())
        if 50 <= prompt_len <= 3000:
            score += 10
            strengths.append("Appropriate instruction length")
        elif prompt_len < 50:
            suggestions.append("Prompt is very short — add more detail for better test coverage")
        else:
            suggestions.append("Prompt is very long — consider using section headers (## Focus Areas, etc.) for clarity")

        # Uses section headers
        uses_headers = bool(re.search(r"^#{1,3}\s+\w+", intent.raw_text, re.MULTILINE))
        if uses_headers:
            score += 5
            strengths.append("Uses structured section headers")
        else:
            suggestions.append("Using '## Focus Areas', '## Exclude', '## Coverage' section headers improves parsing accuracy")

        # Penalise ambiguities
        if ambiguities:
            score = max(0, score - len(ambiguities) * 5)
            suggestions.append(f"Resolve {len(ambiguities)} ambiguous phrase(s) highlighted below")

        return PromptQuality(score=min(100, score), strengths=strengths, suggestions=suggestions)

    def _build_execution_plan(
        self,
        intent: ParsedPromptIntent,
        auth: AuthContext,
        cred_status: CredentialStatus,
    ) -> list[ExecutionStep]:
        steps: list[ExecutionStep] = []
        n = 1

        steps.append(ExecutionStep(
            step=n, label="Project Setup",
            description="Initialise workspace, validate target URL, prepare browser context.",
            icon="🗂️",
        ))
        n += 1

        if cred_status.is_complete:
            steps.append(ExecutionStep(
                step=n, label="Login",
                description=f"Authenticate using detected credentials{' at ' + auth.login_url if auth.login_url else ' (auto-detect login page)'}.",
                icon="🔐",
            ))
            n += 1

        scope_desc = "Crawl application"
        if intent.focus_areas:
            scope_desc = f"Crawl application — focused on: {', '.join(intent.focus_areas[:3])}"
        if intent.excluded_pages or intent.excluded_modules:
            excl = list(intent.excluded_modules) + list(intent.excluded_pages)
            scope_desc += f" — skipping: {', '.join(excl[:3])}"
        steps.append(ExecutionStep(
            step=n, label="Crawl Application",
            description=scope_desc + ".",
            icon="🕷️",
        ))
        n += 1

        if intent.excluded_modules:
            steps.append(ExecutionStep(
                step=n, label="Apply Scope Filter",
                description=f"Tag excluded modules in inventory: {', '.join(intent.excluded_modules[:3])}.",
                icon="🚫",
            ))
            n += 1

        steps.append(ExecutionStep(
            step=n, label="Generate Inventory",
            description="Aggregate discovered pages, forms, APIs, and navigation graph.",
            icon="📋",
        ))
        n += 1

        focus_desc = "Generate test scenarios"
        if intent.coverage_preferences:
            focus_desc += f" — coverage: {', '.join(intent.coverage_preferences)}"
        if intent.focus_areas:
            focus_desc += f" — focus: {', '.join(intent.focus_areas[:2])}"
        steps.append(ExecutionStep(
            step=n, label="Design Test Plan",
            description=focus_desc + ".",
            icon="🧠",
        ))
        n += 1

        steps.append(ExecutionStep(
            step=n, label="Human Review",
            description="Display generated test scenarios for your approval before code generation.",
            icon="👤",
        ))
        n += 1

        code_desc = "Generate Playwright test files"
        framework_hints: list[str] = []
        full_text = (intent.raw_text + " " + intent.custom_instructions).lower()
        for pattern, label in _FRAMEWORK_PATTERNS:
            if re.search(pattern, full_text, re.IGNORECASE):
                framework_hints.append(label)
                break
        if framework_hints:
            code_desc += f" using {framework_hints[0]}"
        if intent.output_preferences:
            code_desc += f" — style: {', '.join(intent.output_preferences[:2])}"
        steps.append(ExecutionStep(
            step=n, label="Generate Tests",
            description=code_desc + ".",
            icon="💻",
        ))
        n += 1

        steps.append(ExecutionStep(
            step=n, label="Execute Tests",
            description="Run generated Playwright tests and collect results.",
            icon="▶️",
        ))

        return steps

    def _build_estimates(
        self,
        intent: ParsedPromptIntent,
        auth: AuthContext,
        cred_status: CredentialStatus,
    ) -> EstimatedStats:
        mod_count = max(1, len(intent.focus_areas)) if intent.focus_areas else 3
        base_pages = mod_count * 4
        pages_range = f"{max(1, base_pages - 3)}–{base_pages + 5}"

        base_scenarios = mod_count * 6
        if "negative" in intent.coverage_preferences:
            base_scenarios = int(base_scenarios * 1.5)
        if "security" in intent.coverage_preferences:
            base_scenarios += 5
        scenarios_range = f"{max(1, base_scenarios - 4)}–{base_scenarios + 8}"

        framework = "Playwright"
        full_text = (intent.raw_text + " " + intent.custom_instructions).lower()
        for pattern, label in _FRAMEWORK_PATTERNS:
            if re.search(pattern, full_text, re.IGNORECASE):
                framework = label
                break

        runtime = max(1, mod_count * 2)
        if cred_status.is_complete:
            runtime += 1

        return EstimatedStats(
            modules_estimate=mod_count,
            pages_range=pages_range,
            scenarios_range=scenarios_range,
            framework=framework,
            requires_auth=cred_status.is_complete or cred_status.username_detected,
            estimated_runtime_minutes=runtime,
        )

    def _build_interpretation(
        self,
        intent: ParsedPromptIntent,
        auth: AuthContext,
        cred_status: CredentialStatus,
        scope: ScopeSummary,
        raw_text: str,
    ) -> dict[str, Any]:
        """Build the human-readable interpretation summary."""
        return {
            "scope": scope.included_modules,
            "excluded": scope.excluded_modules,
            "included_pages": scope.included_pages,
            "excluded_pages": scope.excluded_pages,
            "authentication": {
                "required": cred_status.is_complete or cred_status.username_detected,
                "complete": cred_status.is_complete,
                "strategy": auth.auth_strategy,
            },
            "coverage": intent.coverage_preferences,
            "output": intent.output_preferences,
            "custom_instructions": intent.custom_instructions,
            "has_section_headers": bool(re.search(r"^#{1,3}\s+\w+", raw_text, re.MULTILINE)),
        }

    @staticmethod
    def _empty_analysis(raw_prompt: str) -> PromptAnalysis:
        return PromptAnalysis(
            analysis_id=str(uuid.uuid4()),
            raw_prompt=raw_prompt[:200],
            interpretation={},
            confidence_scores=[],
            execution_plan=[],
            quality=PromptQuality(score=0, strengths=[], suggestions=["Could not parse prompt."]),
            ambiguities=[],
            credential_status=CredentialStatus(),
            scope_summary=ScopeSummary(),
            estimated=EstimatedStats(),
            reasoning_steps=["Analysis failed."],
            parsed_intent={},
        )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_analyzer_singleton: PromptAnalyzer | None = None


def get_prompt_analyzer() -> PromptAnalyzer:
    global _analyzer_singleton
    if _analyzer_singleton is None:
        _analyzer_singleton = PromptAnalyzer()
    return _analyzer_singleton
