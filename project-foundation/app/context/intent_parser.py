"""
Hybrid Intent Parser — deterministic regex + LLM augmentation

Combines two extraction strategies into a single :class:`ParsedIntent`:

1. **Deterministic (regex)** — always runs and never fails. Extracts
   values that must be exact: target URL, credentials, browser, environment.
   Reuses the existing ``PromptParser`` heuristics for focus areas,
   exclusions and coverage preferences so behaviour stays backward compatible.

2. **LLM (structured)** — runs only when ``intent_engine_enabled`` is on and
   an LLM client is available. Extracts goal, included/excluded modules,
   priorities, testing strategy, business objective and success criteria as
   structured JSON. Never receives credentials (the redacted text is used).

The LLM path is best-effort: any failure falls back to the deterministic
result so the pipeline never blocks on the model.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field

from app.agent.config import get_agent_config
from app.core.interfaces import ILLMClient
from app.logging import LoggerMixin
from app.services.prompt_builder import (
    AuthContext,
    ParsedPromptIntent,
    PromptParser,
    get_prompt_parser,
)

_URL_PATTERN = r"https?://[^\s\"'<>]+"

# Supplementary inline credential patterns (e.g. "username admin password
# secret123"). Complementary to (not replacing) the shared _CRED_PATTERNS.
_INLINE_CRED_PATTERNS: list[tuple[str, str]] = [
    ("username", r"\b(?:username|email|login\s+name)\b\s+([A-Za-z0-9_.@+-]+)"),
    ("password", r"\b(?:password|pass|pwd)\b\s+([A-Za-z0-9!@#$%^&*_\-.]{1,64})"),
]

# Words that are not credential values (avoid over-redaction of structural text)
_INLINE_CRED_STOPWORDS = {
    "field", "fields", "input", "box", "section", "reset", "change", "type",
    "is", "are", "to", "on", "the", "a", "an", "for", "and", "page",
}

_BROWSER_KEYWORDS: list[str] = [
    "chromium", "chrome", "firefox", "webkit", "safari", "edge", "playwright",
]

_ENVIRONMENT_KEYWORDS: list[tuple[str, list[str]]] = [
    ("staging", ["staging", "stage"]),
    ("production", ["production", "prod", "live"]),
    ("qa", ["qa"]),
    ("uat", ["uat", "user acceptance"]),
    ("dev", ["dev", "development", "localhost"]),
    ("test", ["test"]),
]

_LLM_SYSTEM_PROMPT = (
    "You are an intent-extraction engine for a test-automation platform. "
    "Given a user's instructions, return STRICT JSON (no markdown) matching "
    "exactly this schema:\n"
    "{\n"
    '  "goal": string | null,\n'
    '  "included_modules": string[],\n'
    '  "excluded_modules": string[],\n'
    '  "priorities": string[],\n'
    '  "testing_strategy": string[],\n'
    '  "business_objective": string | null,\n'
    '  "success_criteria": string[]\n'
    "}\n"
    "Rules:\n"
    "- included_modules: the pages/modules the user explicitly wants tested.\n"
    "- excluded_modules: the pages/modules the user explicitly wants skipped.\n"
    "- testing_strategy: test types implied (e.g. negative, boundary, security, smoke).\n"
    "- priorities: what should be prioritised (e.g. critical paths, login flow).\n"
    "- success_criteria: concrete conditions that mean the test run succeeded.\n"
    "- Only use information present in the instructions. Use [] for unknown lists and null for unknown strings."
)


class LLMIntentSchema(BaseModel):
    """Fields extracted by the LLM. Deliberately excludes credentials."""

    goal: str | None = None
    included_modules: list[str] = Field(default_factory=list)
    excluded_modules: list[str] = Field(default_factory=list)
    priorities: list[str] = Field(default_factory=list)
    testing_strategy: list[str] = Field(default_factory=list)
    business_objective: str | None = None
    success_criteria: list[str] = Field(default_factory=list)


class ParsedIntent(BaseModel):
    """Unified output of the Hybrid Intent Parser."""

    # LLM / heuristic fields
    goal: str | None = None
    included_modules: list[str] = Field(default_factory=list)
    excluded_modules: list[str] = Field(default_factory=list)
    priorities: list[str] = Field(default_factory=list)
    testing_strategy: list[str] = Field(default_factory=list)
    business_objective: str | None = None
    success_criteria: list[str] = Field(default_factory=list)

    # Deterministic fields
    target_url: str | None = None
    browser: str | None = None
    environment: str | None = None
    credentials: dict[str, Any] = Field(
        default_factory=dict,
        description="SECURITY: in-memory credentials — never log, emit, or persist",
    )
    redacted_text: str | None = Field(None, description="Prompt with credentials redacted")

    # Provenance
    confidence: float = Field(default=0.0, description="0.0–1.0 extraction confidence")
    source: str = Field(default="regex", description="regex | llm | hybrid")

    # Backward-compatible ParsedPromptIntent.to_dict() shape
    prompt_context: dict[str, Any] = Field(
        default_factory=dict,
        description="ParsedPromptIntent.to_dict() compatible dict for existing consumers",
    )

    def safe_dict(self) -> dict[str, Any]:
        """Serialise without credentials (safe to log/emit/store)."""
        data = self.model_dump()
        data.pop("credentials", None)
        return data


class HybridIntentParser(LoggerMixin):
    """
    Hybrid intent extraction.

    Args:
        llm_client: Optional ILLMClient used only when intent_engine_enabled.
        parser: Optional PromptParser (defaults to the shared singleton).
    """

    def __init__(self, llm_client: ILLMClient | None = None, parser: PromptParser | None = None) -> None:
        super().__init__()
        self._llm = llm_client
        self._parser = parser or get_prompt_parser()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def parse(self, raw_text: str, *, use_llm: bool | None = None) -> ParsedIntent:
        """
        Parse a raw user prompt into a structured :class:`ParsedIntent`.

        Args:
            raw_text: The user's free-text instructions.
            use_llm: Override the ``intent_engine_enabled`` flag. When None the
                feature flag is consulted.

        Returns:
            ParsedIntent — never raises; falls back to deterministic parsing.
        """
        if not raw_text or not raw_text.strip():
            return ParsedIntent(redacted_text="", prompt_context=ParsedPromptIntent().to_dict())

        deterministic = self._extract_deterministic(raw_text)

        should_use_llm = get_agent_config().intent_engine_enabled if use_llm is None else bool(use_llm)
        if should_use_llm and self._llm:
            llm_part = await self._try_llm(deterministic.redacted_text)
            if llm_part is not None:
                return self._merge(deterministic, llm_part, source="hybrid")

        return self._merge(deterministic, None, source="regex")

    # ------------------------------------------------------------------
    # Deterministic extraction
    # ------------------------------------------------------------------

    def _extract_deterministic(self, raw_text: str) -> ParsedIntent:
        # Credentials + redaction reuse the battle-tested PromptParser rules,
        # then are supplemented with inline "username x password y" patterns.
        parsed, auth = self._parser.parse(raw_text)
        auth = self._supplement_credentials(raw_text, auth)
        auth = self._supplement_login_url(raw_text, auth)
        redacted = self._redact_credentials(raw_text)

        return ParsedIntent(
            goal=None,
            included_modules=list(parsed.focus_areas),
            excluded_modules=list(parsed.excluded_modules),
            priorities=[],
            testing_strategy=list(parsed.coverage_preferences),
            business_objective=None,
            success_criteria=[],
            target_url=self._extract_url(raw_text, login_url=auth.login_url),
            browser=self._extract_browser(raw_text),
            environment=self._extract_environment(raw_text),
            credentials=self._auth_to_dict(auth),
            redacted_text=redacted,
            confidence=0.7,
            source="regex",
            prompt_context=parsed.to_dict(),
        )

    @staticmethod
    def _supplement_credentials(text: str, auth: Any) -> Any:
        """Fill credential fields the shared parser missed (inline forms)."""
        for field_name, pattern in _INLINE_CRED_PATTERNS:
            existing = getattr(auth, field_name, None)
            # "login with username" mis-parses the field label as its own value;
            # treat a value equal to the field name as unpopulated.
            if existing and existing != field_name:
                continue
            m = re.search(pattern, text, re.IGNORECASE)
            if m and m.group(1).lower() not in _INLINE_CRED_STOPWORDS:
                setattr(auth, field_name, m.group(1))
        return auth

    @staticmethod
    def _supplement_login_url(text: str, auth: Any) -> Any:
        """Detect a login-page URL even without an explicit ``login url:`` prefix."""
        if auth.login_url:
            return auth
        for u in re.findall(_URL_PATTERN, text):
            u = re.sub(r"[.,;:!?\"')\]]+$", "", u)
            low = u.lower()
            if any(k in low for k in ("/login", "/signin", "/sign-in", "/auth", "login.", "auth.")):
                auth.login_url = u
                break
        return auth

    @classmethod
    def _redact_credentials(cls, text: str) -> str:
        """Redact credentials using both the shared and inline patterns."""
        redacted = text
        # Shared patterns first so inline rules never re-match their output.
        from app.services.prompt_builder import _CRED_PATTERNS as shared_patterns
        for _field, pattern in shared_patterns:
            redacted = re.sub(
                pattern,
                lambda m: m.group(0).replace(m.group(1), "[CREDENTIAL REDACTED]"),
                redacted,
                flags=re.IGNORECASE,
            )
        for _field, pattern in _INLINE_CRED_PATTERNS:
            def _repl(m: re.Match[str]) -> str:
                if m.group(1).lower() in _INLINE_CRED_STOPWORDS:
                    return m.group(0)
                return m.group(0).replace(m.group(1), "[CREDENTIAL REDACTED]")
            redacted = re.sub(
                pattern, _repl, redacted, flags=re.IGNORECASE,
            )
        return redacted

    @staticmethod
    def _extract_url(text: str, login_url: str | None = None) -> str | None:
        """
        Pick the application URL from the prompt.

        Strips trailing punctuation and prefers a non-login URL when multiple
        URLs are present (the login page is usually not the target app).
        """
        urls = [re.sub(r"[.,;:!?\"')\]]+$", "", u) for u in re.findall(_URL_PATTERN, text)]
        urls = [u for u in urls if u]
        if not urls:
            return None
        for u in urls:
            if u == login_url:
                continue
            low = u.lower()
            if any(k in low for k in ("/login", "/signin", "/sign-in", "/auth", "login.", "auth.")):
                continue
            return u
        return urls[0]

    @staticmethod
    def _extract_browser(text: str) -> str | None:
        lower = text.lower()
        for kw in _BROWSER_KEYWORDS:
            if kw in lower:
                return kw
        return None

    @staticmethod
    def _extract_environment(text: str) -> str | None:
        lower = text.lower()
        for env, keywords in _ENVIRONMENT_KEYWORDS:
            if any(kw in lower for kw in keywords):
                return env
        return None

    @staticmethod
    def _auth_to_dict(auth: AuthContext) -> dict[str, Any]:
        return {
            "username": auth.username,
            "password": auth.password,
            "login_url": auth.login_url,
            "auth_strategy": auth.auth_strategy,
        }

    # ------------------------------------------------------------------
    # LLM extraction (best-effort)
    # ------------------------------------------------------------------

    async def _try_llm(self, redacted_text: str) -> LLMIntentSchema | None:
        """
        Ask the LLM for structured intent. Returns None on any failure so the
        caller can fall back to the deterministic result.
        """
        if not redacted_text or not redacted_text.strip():
            return None
        try:
            prompt = (
                "Extract structured intent from the user's test instructions.\n\n"
                f"## User Instructions\n{redacted_text.strip()}"
            )
            response = await self._llm.complete(
                prompt=prompt,
                system_prompt=_LLM_SYSTEM_PROMPT,
                temperature=0.2,
                max_tokens=1200,
            )
            if not response:
                return None
            data = self._extract_json(response)
            return LLMIntentSchema(**data)
        except Exception as e:  # noqa: BLE001 — best-effort LLM; never block the pipeline
            self.logger.warning(
                "hybrid_intent_llm_fallback",
                error=str(e)[:200],
            )
            return None

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        """Extract and parse a JSON object, tolerating markdown fences."""
        cleaned = text.strip()
        first_brace = cleaned.find("{")
        last_brace = cleaned.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            cleaned = cleaned[first_brace:last_brace + 1]
        cleaned = re.sub(r",\s*}", "}", cleaned)
        cleaned = re.sub(r",\s*]", "]", cleaned)
        cleaned = re.sub(r"```json\s*", "", cleaned)
        cleaned = re.sub(r"```\s*", "", cleaned)
        if not cleaned:
            raise ValueError("No JSON object found in LLM response")
        return json.loads(cleaned)

    # ------------------------------------------------------------------
    # Merge
    # ------------------------------------------------------------------

    @staticmethod
    def _merge(deterministic: ParsedIntent, llm_part: LLMIntentSchema | None, *, source: str) -> ParsedIntent:
        merged = ParsedIntent(
            goal=(llm_part.goal if llm_part and llm_part.goal else None),
            included_modules=(
                list(llm_part.included_modules) if llm_part and llm_part.included_modules
                else list(deterministic.included_modules)
            ),
            excluded_modules=(
                list(llm_part.excluded_modules) if llm_part and llm_part.excluded_modules
                else list(deterministic.excluded_modules)
            ),
            priorities=list(llm_part.priorities) if llm_part else [],
            testing_strategy=(
                list(llm_part.testing_strategy) if llm_part and llm_part.testing_strategy
                else list(deterministic.testing_strategy)
            ),
            business_objective=(
                llm_part.business_objective if llm_part and llm_part.business_objective else None
            ),
            success_criteria=list(llm_part.success_criteria) if llm_part else [],
            target_url=deterministic.target_url,
            browser=deterministic.browser,
            environment=deterministic.environment,
            credentials=dict(deterministic.credentials),
            redacted_text=deterministic.redacted_text,
            confidence=0.9 if source == "hybrid" else 0.7,
            source=source,
            prompt_context=dict(deterministic.prompt_context),
        )

        # Keep prompt_context backward compatible: reflect LLM module choices.
        if merged.included_modules:
            merged.prompt_context["focus_areas"] = list(merged.included_modules)
        if merged.excluded_modules:
            merged.prompt_context["excluded_modules"] = list(merged.excluded_modules)
        if merged.testing_strategy:
            merged.prompt_context["coverage_preferences"] = list(merged.testing_strategy)
        merged.prompt_context["has_credentials"] = bool(merged.credentials.get("username") and merged.credentials.get("password"))
        return merged


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_intent_parser_singleton: HybridIntentParser | None = None


def get_hybrid_intent_parser(
    llm_client: ILLMClient | None = None,
    parser: PromptParser | None = None,
) -> HybridIntentParser:
    """
    Return the process-wide HybridIntentParser singleton.

    When a fresh instance is desired (e.g. with a mock LLM in tests), pass
    ``llm_client``/``parser`` explicitly — a dedicated instance is created.
    """
    global _intent_parser_singleton
    if llm_client is not None or parser is not None:
        return HybridIntentParser(llm_client=llm_client, parser=parser)
    if _intent_parser_singleton is None:
        _intent_parser_singleton = HybridIntentParser()
    return _intent_parser_singleton
