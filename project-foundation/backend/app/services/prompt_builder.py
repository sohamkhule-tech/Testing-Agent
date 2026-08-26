"""
Prompt Builder Service

Centralizes all LLM prompt assembly. No agent may manually concatenate
prompts — everything flows through PromptBuilder.build().

Also contains:
 - PromptParser   : parses free-text user instructions into structured intent
 - CredentialStore: encrypts / decrypts run credentials (Fernet, file-backed)
 - AuthContext    : in-memory credential carrier (never logged, never in prompts)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.logging import LoggerMixin
from app.prompts import get_prompt

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

_CRED_PATTERNS: list[tuple[str, str]] = [
    ("username", r"\b(?:username|email|login|user(?:\s+id)?)\b\s*(?:[:\-=]|(?:is|are))\s*([^\s,;]+)"),
    ("username", r"\bid\b\s*[:\-=]\s*([^\s,;]+)"),
    ("password", r"\b(?:password|pass(?:word)?|pwd|passwd)\b\s*(?:[:\-=]|(?:is|are))\s*([^\s,;]+)"),
    ("login_url", r"(?:login\s+url|login\s+page|sign[- ]in\s+url)\s*[:\-=]\s*(https?://\S+)"),
    ("username", r"(?:use\s+username|with\s+username|as\s+user|use\s+email)\s+([^\s,;.]+)"),
    ("password", r"(?:use\s+password|with\s+password)\s+([^\s,;.]+)"),
    ("username", r"login\s+(?:with|using|as)\s+([^\s,;.]+)"),
]

_SECTION_HEADERS: dict[str, str] = {
    "focus": r"#+\s*(?:focus|focus areas?|test focus)",
    "credentials": r"#+\s*(?:credentials?|auth(?:entication)?|login)",
    "exclude": r"#+\s*(?:exclu(?:de|sions?)|skip|ignore)",
    "coverage": r"#+\s*(?:coverage|test type|scenario type)",
    "output": r"#+\s*(?:output|framework|style|format)",
}

_NOISE_WORDS = {"test", "focus", "go", "to", "the", "a", "an", "this", "these",
                "those", "all", "some", "any", "check", "for", "and", "or",
                "but", "then", "also", "its", "it", "of", "in", "on", "at",
                "whole", "entire", "every", "everything", "application", "app",
                "website", "site", "credentials", "credential", "cred"}

_LEADING_NOISE_PATTERN = (
    r"^(test|focus(?:\s+on)?|go\s+to|the|a|an|this|these|those|all|some|any|check|for)\s+"
)

# Phase 7: common application module names for keyword-based focus detection
_COMMON_MODULE_KEYWORDS: list[str] = [
    "dashboard", "reports", "analytics", "settings", "profile",
    "users", "login", "register", "signup", "billing", "payments",
    "orders", "inventory", "products", "catalog", "search",
    "notifications", "messages", "inbox", "calendar", "tasks",
    "admin", "api", "audit", "logs", "monitoring",
]


@dataclass
class AuthContext:
    """
    In-memory credential carrier.

    SECURITY RULE: This object must NEVER be:
    - serialised into any log entry
    - included in any LLM prompt string
    - sent via SSE events
    - included in report output
    """

    username: str | None = None
    password: str | None = None
    login_url: str | None = None
    auth_strategy: str = "form"  # form | api | basic | oauth

    def is_populated(self) -> bool:
        return bool(self.username and self.password)

    def has_auth_config(self) -> bool:
        """True when any actionable auth detail is present (form credentials or
        a supplied login URL entry point)."""
        return self.is_populated() or bool(self.login_url)

    def safe_summary(self) -> dict:
        """Returns a log-safe representation — no sensitive values."""
        return {
            "has_username": bool(self.username),
            "has_password": bool(self.password),
            "login_url": self.login_url,
            "auth_strategy": self.auth_strategy,
        }


@dataclass
class ParsedPromptIntent:
    """
    Structured intent extracted from the raw user prompt.

    All credential values are removed before storage.
    The original text with placeholders is kept in `raw_text`.
    """

    raw_text: str = ""                       # redacted (credentials replaced)
    focus_areas: list[str] = field(default_factory=list)
    excluded_modules: list[str] = field(default_factory=list)
    excluded_pages: list[str] = field(default_factory=list)
    included_pages: list[str] = field(default_factory=list)
    coverage_preferences: list[str] = field(default_factory=list)
    output_preferences: list[str] = field(default_factory=list)
    custom_instructions: str = ""
    has_credentials: bool = False

    def to_dict(self) -> dict:
        return {
            "raw_text": self.raw_text,
            "focus_areas": self.focus_areas,
            "excluded_modules": self.excluded_modules,
            "excluded_pages": self.excluded_pages,
            "included_pages": self.included_pages,
            "coverage_preferences": self.coverage_preferences,
            "output_preferences": self.output_preferences,
            "custom_instructions": self.custom_instructions,
            "has_credentials": self.has_credentials,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ParsedPromptIntent":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class PromptBuildContext:
    """All inputs needed to build a final LLM prompt."""

    agent_role: str                              # e.g. "test-design-agent"
    user_prompt_raw: str = ""
    parsed_intent: ParsedPromptIntent | None = None
    project_name: str = ""
    application_url: str = ""
    auth_type: str | None = None
    environment: str = "staging"
    inventory_summary: dict[str, Any] | None = None
    run_config: dict[str, Any] | None = None


@dataclass
class FinalPrompt:
    """Output of PromptBuilder — ready to send to the LLM."""

    system_message: str
    user_message: str
    metadata: dict = field(default_factory=dict)  # log-safe only


# ---------------------------------------------------------------------------
# PromptParser
# ---------------------------------------------------------------------------


class PromptParser(LoggerMixin):
    """
    Parses a free-text user prompt into ParsedPromptIntent and
    extracts credentials into AuthContext.

    The stored ParsedPromptIntent.raw_text has credentials replaced
    with [CREDENTIAL REDACTED] so it is safe to persist.
    """

    def parse(self, raw_text: str) -> tuple[ParsedPromptIntent, AuthContext]:
        """
        Parse raw user prompt.

        Returns:
            (ParsedPromptIntent with credentials redacted, AuthContext with actual values)
        """
        if not raw_text or not raw_text.strip():
            return ParsedPromptIntent(), AuthContext()

        auth = self._extract_credentials(raw_text)
        redacted = self._redact_credentials(raw_text)
        intent = self._parse_sections(redacted)
        intent.has_credentials = auth.is_populated()
        return intent, auth

    # ------------------------------------------------------------------
    # private
    # ------------------------------------------------------------------

    def _extract_credentials(self, text: str) -> AuthContext:
        auth = AuthContext()
        for field_name, pattern in _CRED_PATTERNS:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                setattr(auth, field_name, m.group(1))
        return auth

    def _redact_credentials(self, text: str) -> str:
        redacted = text
        for _field_name, pattern in _CRED_PATTERNS:
            redacted = re.sub(
                pattern,
                lambda m: m.group(0).replace(m.group(1), "[CREDENTIAL REDACTED]"),
                redacted,
                flags=re.IGNORECASE,
            )
        return redacted

    def _parse_sections(self, text: str) -> ParsedPromptIntent:
        intent = ParsedPromptIntent(raw_text=text.strip())

        # Try section-header based parsing first
        sections = self._split_into_sections(text)

        if sections:
            for section_key, content in sections.items():
                lines = [l.strip() for l in content.strip().splitlines() if l.strip()]
                if section_key == "focus":
                    intent.focus_areas = lines
                elif section_key == "credentials":
                    pass  # credentials already extracted from raw text before redaction
                elif section_key == "exclude":
                    intent.excluded_modules = lines
                elif section_key == "coverage":
                    intent.coverage_preferences = lines
                elif section_key == "output":
                    intent.output_preferences = lines
            remaining = self._extract_remaining(text, sections)
            intent.custom_instructions = remaining.strip()
        else:
            # No section headers — treat entire text as custom instructions + heuristic extraction
            intent.custom_instructions = text.strip()
            intent.focus_areas = self._heuristic_focus(text)
            intent.excluded_modules = self._heuristic_exclusions(text)
            intent.coverage_preferences = self._heuristic_coverage(text)

        # Phase 7: detect "only" / "just" scope restriction.
        # When the user says "test X only" or "just test X", all other modules
        # should be excluded and the crawl should be restricted to X's pages.
        if intent.focus_areas and self._has_only_constraint(text):
            intent.included_pages = self._focus_areas_to_url_patterns(intent.focus_areas)

        return intent

    def _split_into_sections(self, text: str) -> dict[str, str]:
        """Split text into named sections based on markdown headers."""
        result: dict[str, str] = {}
        current_key: str | None = None
        current_lines: list[str] = []

        for line in text.splitlines():
            matched_key = None
            for key, pattern in _SECTION_HEADERS.items():
                if re.match(pattern, line.strip(), re.IGNORECASE):
                    matched_key = key
                    break
            if matched_key:
                if current_key:
                    result[current_key] = "\n".join(current_lines)
                current_key = matched_key
                current_lines = []
            elif current_key:
                current_lines.append(line)

        if current_key:
            result[current_key] = "\n".join(current_lines)

        return result

    def _extract_remaining(self, text: str, sections: dict[str, str]) -> str:
        """Remove section content from text to find unstructured remainder."""
        remaining = text
        for _key, pattern in _SECTION_HEADERS.items():
            remaining = re.sub(
                rf"({pattern}[\s\S]*?)(?={pattern}|\Z)",
                "",
                remaining,
                flags=re.IGNORECASE,
            )
        return remaining.strip()

    def _heuristic_focus(self, text: str) -> list[str]:
        """Extract focus areas from unstructured text.

        Strategy:
        1. Named-phrase patterns: "test/go to/... the dashboard [page|module]"
        2. Fallback: whole-text keyword scan against _COMMON_MODULE_KEYWORDS.
        3. Post-process: extract the core module keyword from any compound phrase.
        """
        found: list[str] = []

        # Pattern 1 — verb phrase + module name, stopped by scope/keyword boundaries.
        _STOP = (
            r"(?:\.|,|\n|$"
            r"|\s+only\b|\s+just\b|\s+by\s|\s+using\s|\s+with\s+the\s"
            r"|\s+page\b|\s+pages\b|\s+module\b|\s+modules\b"
            r")"
        )
        pattern1 = (
            r"(?:test|focus\s+on|only\s+test|generate\s+(?:tests?\s+)?for|check|go\s+to)"
            r"\s+"
            r"([A-Za-z][A-Za-z\s]+?)"
            + _STOP
        )
        for m in re.finditer(pattern1, text, re.IGNORECASE):
            val = self._clean_focus_name(m.group(1).strip())
            if val and len(val) < 80 and val not in found:
                found.append(val)

        # Pattern 2 — "<name> page/module/section/feature"
        pattern2 = r"([A-Za-z][A-Za-z\s]+?)\s+(?:module|modules|page|pages|section|feature|dashboard|panel|view|screen)"
        for m in re.finditer(pattern2, text, re.IGNORECASE):
            val = self._clean_focus_name(m.group(1).strip())
            if val and len(val) < 80 and val not in found:
                found.append(val)

        # Fallback: keyword-based detection for common module names.
        # Runs regardless — the post-processing step deduplicates.
        lower_text = text.lower()
        for kw in _COMMON_MODULE_KEYWORDS:
            if kw in lower_text:
                cap = kw.capitalize()
                if cap not in found:
                    found.append(cap)

        # Post-process: extract the core module keyword from compound phrases.
        # "dashboard page"  → "Dashboard"
        # "test the dashboard" → "Dashboard"
        # "user management module" → "User Management"
        return self._extract_core_modules(found, lower_text)

    @staticmethod
    def _extract_core_modules(candidates: list[str], lower_text: str) -> list[str]:
        """Extract the most specific module name from each candidate phrase."""
        result: list[str] = []
        for candidate in candidates:
            core = PromptParser._resolve_core_module(candidate, lower_text)
            if core and core not in result:
                result.append(core)
        return result

    @staticmethod
    def _resolve_core_module(phrase: str, _lower_text: str) -> str | None:
        """Reduce a compound phrase to its core module name.

        Returns None if the phrase resolves to only noise words.
        """
        lower = phrase.lower().strip()
        if lower in _NOISE_WORDS:
            return None
        # If the phrase contains a common keyword, use it (longest match wins).
        best_match: str | None = None
        best_len = 0
        for kw in _COMMON_MODULE_KEYWORDS:
            if kw in lower:
                if len(kw) > best_len:
                    best_match = kw
                    best_len = len(kw)
        if best_match:
            return best_match.capitalize()
        # Strip leading noise words.
        cleaned = re.sub(_LEADING_NOISE_PATTERN, "", phrase, count=1, flags=re.IGNORECASE).strip()
        if not cleaned or cleaned.lower() in _NOISE_WORDS:
            return None
        # If still too verbose, take the last 2 words as the module name.
        words = cleaned.split()
        if len(words) > 3:
            cleaned = " ".join(words[-2:])
        # Re-check: after truncation, is the result all noise?
        final_words = cleaned.split()
        if all(w.lower() in _NOISE_WORDS for w in final_words):
            return None
        result = cleaned.title()
        return result if result.lower() not in _NOISE_WORDS else None

    @staticmethod
    def _clean_focus_name(name: str) -> str:
        """Normalise a raw focus area string into a clean module name."""
        cleaned = re.sub(_LEADING_NOISE_PATTERN, "", name.strip(), count=1, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    @staticmethod
    def _clean_focus_name(name: str) -> str:
        """Normalise a raw focus area string into a clean module name."""
        # Strip leading articles and common noise words
        cleaned = re.sub(r"^(the|a|an|this|these|those|all|some|any)\s+", "", name.strip(), flags=re.IGNORECASE)
        # Collapse extra whitespace
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def _heuristic_exclusions(self, text: str) -> list[str]:
        patterns = [
            r"(?:ignore|skip|exclude|don'?t\s+test)\s+([A-Za-z][A-Za-z\s]+?)(?:\.|,|\n|$)",
        ]
        found = []
        for p in patterns:
            for m in re.finditer(p, text, re.IGNORECASE):
                val = m.group(1).strip()
                if val and len(val) < 80 and val not in found:
                    found.append(val)
        return found

    def _heuristic_coverage(self, text: str) -> list[str]:
        keywords = ["negative", "boundary", "security", "functional", "smoke", "regression",
                    "accessibility", "api", "performance", "edge case", "positive", "validation",
                    "authentication", "authorization", "usability", "error handling"]
        found = []
        lower = text.lower()
        for kw in keywords:
            if kw in lower:
                found.append(kw)
        return found

    @staticmethod
    def _has_only_constraint(text: str) -> bool:
        """Detect if the user used 'only' / 'just' as a scope-restricting directive."""
        return bool(re.search(r"\b(?:only|just)\b", text, re.IGNORECASE))

    @staticmethod
    def _focus_areas_to_url_patterns(focus_areas: list[str]) -> list[str]:
        """Convert focus area names to URL path patterns for crawl restriction."""
        patterns: list[str] = []
        for area in focus_areas:
            # Convert "User Management" → "user-management", "user_management", "usermanagement"
            slug = re.sub(r"[^a-z0-9]+", r"(?:-|_|)", area.strip().lower())
            slug = re.sub(r"\(\?:-\|_\|\)$", "", slug)
            if slug:
                patterns.append(slug)
                # Also match the singular/plural variants
                # e.g. "dashboard" → also match "dashboards"
        return patterns


# ---------------------------------------------------------------------------
# CredentialStore (file-based, Fernet-encrypted)
# ---------------------------------------------------------------------------


class CredentialStore(LoggerMixin):
    """
    Encrypts run credentials and persists them in the run workspace.

    Uses Fernet symmetric encryption. The encryption key comes from
    settings (CREDENTIAL_ENCRYPTION_KEY env var). If the key is not
    set, a per-process key is derived (credentials survive the run
    but not server restarts — acceptable for dev mode).
    """

    _FILENAME = "run_credentials.enc"
    _fernet = None

    def __init__(self) -> None:
        super().__init__()
        self._fernet = self._get_fernet()

    # Stable per-process fallback key (derived once at class level so all
    # CredentialStore instances within one process share the same key).
    _FALLBACK_KEY: bytes | None = None

    @classmethod
    def _get_or_create_fallback_key(cls) -> bytes:
        if cls._FALLBACK_KEY is None:
            from cryptography.fernet import Fernet
            cls._FALLBACK_KEY = Fernet.generate_key()
        return cls._FALLBACK_KEY

    def _get_fernet(self):
        try:
            from cryptography.fernet import Fernet
            from app.config import get_settings
            settings = get_settings()
            key_str = getattr(getattr(settings, 'security', None), 'credential_encryption_key', None)
            if key_str:
                key = key_str.encode() if isinstance(key_str, str) else key_str
            else:
                # Use a stable class-level fallback so credentials written and
                # read within the same process can be decrypted.  This is only
                # for development; production MUST set CREDENTIAL_ENCRYPTION_KEY.
                self.logger.warning(
                    "credential_encryption_key_not_configured",
                    message="Using ephemeral per-process key. Set CREDENTIAL_ENCRYPTION_KEY for production.",
                )
                key = self._get_or_create_fallback_key()
            return Fernet(key)
        except ImportError:
            self.logger.warning(
                "cryptography_not_installed",
                message="pip install cryptography required. Credentials stored as plaintext (dev only).",
            )
            return None  # Fall back to plaintext — only safe in dev

    def save(self, workspace_path: str, auth: AuthContext) -> None:
        """Encrypt and save credentials to workspace."""
        if not auth.has_auth_config():
            return
        data = {
            "username": auth.username,
            "password": auth.password,
            "login_url": auth.login_url,
            "auth_strategy": auth.auth_strategy,
        }
        raw = json.dumps(data).encode()
        try:
            if self._fernet:
                encrypted = self._fernet.encrypt(raw)
                cred_path = Path(workspace_path) / self._FILENAME
                cred_path.write_bytes(encrypted)
            else:
                # Fallback: store as plaintext (dev-only warning)
                cred_path = Path(workspace_path) / "run_credentials.json"
                cred_path.write_text(json.dumps(data))
            self.logger.info("credentials_saved", workspace=workspace_path)
        except Exception as e:
            self.logger.error("credentials_save_failed", error=str(e))

    def load(self, workspace_path: str) -> AuthContext:
        """Load and decrypt credentials from workspace."""
        try:
            enc_path = Path(workspace_path) / self._FILENAME
            plain_path = Path(workspace_path) / "run_credentials.json"
            if enc_path.exists() and self._fernet:
                raw = self._fernet.decrypt(enc_path.read_bytes())
                data = json.loads(raw.decode())
            elif plain_path.exists():
                data = json.loads(plain_path.read_text())
            else:
                return AuthContext()
            return AuthContext(
                username=data.get("username"),
                password=data.get("password"),
                login_url=data.get("login_url"),
                auth_strategy=data.get("auth_strategy", "form"),
            )
        except Exception as e:
            self.logger.error("credentials_load_failed", error=str(e))
            return AuthContext()


# ---------------------------------------------------------------------------
# PromptBuilder
# ---------------------------------------------------------------------------


class PromptBuilder(LoggerMixin):
    """
    Assembles the final LLM prompt from all inputs.

    Security invariant: credentials (AuthContext) are NEVER included
    in the returned system_message or user_message.
    """

    def build(self, ctx: PromptBuildContext) -> FinalPrompt:
        system_message = self._build_system(ctx)
        user_message = self._build_user(ctx)
        metadata = {
            "agent_role": ctx.agent_role,
            "project_name": ctx.project_name,
            "has_user_prompt": bool(ctx.user_prompt_raw),
            "has_parsed_intent": ctx.parsed_intent is not None,
            "focus_areas": (ctx.parsed_intent.focus_areas if ctx.parsed_intent else []),
            "excluded_modules": (ctx.parsed_intent.excluded_modules if ctx.parsed_intent else []),
        }
        return FinalPrompt(system_message=system_message, user_message=user_message, metadata=metadata)

    # ------------------------------------------------------------------

    def _build_system(self, ctx: PromptBuildContext) -> str:
        try:
            base = get_prompt(ctx.agent_role)
        except Exception:
            base = ""

        parts = [base]

        if ctx.project_name or ctx.application_url:
            parts.append(
                f"\n## Project Context\n"
                f"Project: {ctx.project_name or 'Unknown'}\n"
                f"URL: {ctx.application_url or 'Unknown'}\n"
                f"Environment: {ctx.environment or 'staging'}\n"
                f"Auth Type: {ctx.auth_type or 'None'}"
            )

        if ctx.parsed_intent:
            if ctx.parsed_intent.excluded_modules:
                excl = ", ".join(ctx.parsed_intent.excluded_modules)
                parts.append(f"\n## Scope Constraints\nExclude these modules: {excl}")

            if ctx.parsed_intent.included_pages:
                incl = ", ".join(ctx.parsed_intent.included_pages)
                parts.append(f"Focus crawl on these URL patterns: {incl}")

            if ctx.parsed_intent.has_credentials:
                parts.append(
                    "\n## Authentication\n"
                    "Authentication credentials have been provided separately and will be used by "
                    "the crawler to log in before visiting protected pages. Assume the crawler is "
                    "authenticated. Generate test scenarios for both authenticated and "
                    "unauthenticated states where appropriate."
                )

        return "\n".join(parts).strip()

    def _build_user(self, ctx: PromptBuildContext) -> str:
        parts: list[str] = []

        # User instructions section
        if ctx.parsed_intent:
            intent = ctx.parsed_intent
            if intent.focus_areas:
                parts.append("## Focus Areas\n" + "\n".join(f"- {a}" for a in intent.focus_areas))
            if intent.coverage_preferences:
                parts.append("## Coverage Preferences\n" + "\n".join(f"- {p}" for p in intent.coverage_preferences))
            if intent.output_preferences:
                parts.append("## Output Preferences\n" + "\n".join(f"- {p}" for p in intent.output_preferences))
            if intent.custom_instructions:
                parts.append(f"## Additional Instructions\n{intent.custom_instructions}")
        elif ctx.user_prompt_raw and ctx.user_prompt_raw.strip():
            parts.append(f"## User Instructions\n{ctx.user_prompt_raw.strip()}")

        # Inventory section (injected by callers that have it)
        if ctx.inventory_summary:
            parts.append(f"## Application Inventory Summary\n{json.dumps(ctx.inventory_summary, indent=2)}")

        return "\n\n".join(parts).strip()


# ---------------------------------------------------------------------------
# Singleton accessors
# ---------------------------------------------------------------------------

_parser_singleton: PromptParser | None = None
_builder_singleton: PromptBuilder | None = None
_store_singleton: CredentialStore | None = None


def get_prompt_parser() -> PromptParser:
    global _parser_singleton
    if _parser_singleton is None:
        _parser_singleton = PromptParser()
    return _parser_singleton


def get_prompt_builder() -> PromptBuilder:
    global _builder_singleton
    if _builder_singleton is None:
        _builder_singleton = PromptBuilder()
    return _builder_singleton


def get_credential_store() -> CredentialStore:
    global _store_singleton
    if _store_singleton is None:
        _store_singleton = CredentialStore()
    return _store_singleton
