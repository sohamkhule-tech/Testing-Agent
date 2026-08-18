"""
Hybrid Intent Parser tests.

Covers deterministic (regex) extraction, LLM augmentation, fallback behaviour,
and credential redaction.
"""

import json

import pytest
from pydantic import BaseModel

from app.context.intent_parser import HybridIntentParser, get_hybrid_intent_parser
from app.core.interfaces import ILLMClient


class MockLLMClient(ILLMClient):
    """Minimal mock LLM for hybrid intent extraction tests."""

    def __init__(self, response: str = "") -> None:
        self.response = response
        self.last_prompt = None
        self.last_system_prompt = None
        self.default_max_tokens = 4096

    async def complete(self, prompt, system_prompt=None, temperature=0.7, max_tokens=4096, **kwargs) -> str:
        self.last_prompt = prompt
        self.last_system_prompt = system_prompt
        return self.response

    async def complete_structured(self, prompt, response_model: type[BaseModel], system_prompt=None, **kwargs):
        raise NotImplementedError

    async def stream_complete(self, prompt, system_prompt=None, **kwargs):
        raise NotImplementedError


@pytest.mark.unit
class TestHybridIntentParserDeterministic:
    """Regex path — always available, never fails, no LLM required."""

    async def test_extracts_credentials_url_browser_environment(self):
        parser = HybridIntentParser(llm_client=None)
        raw = (
            "Test the dashboard. Login with username admin and password secret123 at "
            "https://login.example.com/auth. Use Chromium browser on staging at "
            "https://app.example.com"
        )
        result = await parser.parse(raw, use_llm=False)

        assert result.target_url == "https://app.example.com"
        assert result.browser == "chromium"
        assert result.environment == "staging"
        assert result.credentials["username"] == "admin"
        assert result.credentials["password"] == "secret123"
        assert result.credentials["login_url"] == "https://login.example.com/auth"
        assert result.source == "regex"

    async def test_redacted_text_never_contains_credentials(self):
        parser = HybridIntentParser(llm_client=None)
        raw = "Login with username admin and password secret123, then test Reports."
        result = await parser.parse(raw, use_llm=False)

        assert "admin" not in result.redacted_text
        assert "secret123" not in result.redacted_text
        assert result.prompt_context["has_credentials"] is True

    async def test_empty_prompt_returns_empty_intent(self):
        parser = HybridIntentParser(llm_client=None)
        result = await parser.parse("")
        assert result.target_url is None
        assert result.included_modules == []
        assert result.prompt_context["raw_text"] == ""

    async def test_heuristic_modules_and_coverage_from_parser(self):
        parser = HybridIntentParser(llm_client=None)
        raw = "Focus on the Reports and Dashboard modules. Exclude Settings. Generate negative and security tests."
        result = await parser.parse(raw, use_llm=False)

        assert "Reports" in result.included_modules
        assert "Dashboard" in result.included_modules
        assert result.excluded_modules == ["Settings"]
        assert any("negative" in s for s in result.testing_strategy)


@pytest.mark.unit
class TestHybridIntentParserLLM:
    async def test_llm_augmentation_merges_structured_intent(self):
        llm = MockLLMClient(
            response=json.dumps({
                "goal": "Verify billing flows are stable",
                "included_modules": ["Billing", "Invoices"],
                "excluded_modules": ["Admin"],
                "priorities": ["critical-path", "payment failures"],
                "testing_strategy": ["negative", "security"],
                "business_objective": "Protect revenue",
                "success_criteria": ["No payment failures", "All invoices render"],
            })
        )
        parser = HybridIntentParser(llm_client=llm)
        raw = "Test billing and invoices, skip admin."
        result = await parser.parse(raw, use_llm=True)

        assert result.source == "hybrid"
        assert result.goal == "Verify billing flows are stable"
        assert result.included_modules == ["Billing", "Invoices"]
        assert result.excluded_modules == ["Admin"]
        assert result.priorities == ["critical-path", "payment failures"]
        assert result.business_objective == "Protect revenue"
        assert result.success_criteria == ["No payment failures", "All invoices render"]
        assert result.confidence == 0.9

        # LLM must not have received raw credentials
        assert "secret" not in (llm.last_prompt or "")

    async def test_falls_back_when_llm_returns_garbage(self):
        llm = MockLLMClient(response="this is not json")
        parser = HybridIntentParser(llm_client=llm)
        raw = "Focus on the dashboard."
        result = await parser.parse(raw, use_llm=True)

        # Deterministic fallback preserved modules from the regex path
        assert result.source == "regex"
        assert "Dashboard" in result.included_modules

    async def test_falls_back_when_llm_raises(self):
        class ExplodingLLM(MockLLMClient):
            async def complete(self, prompt, system_prompt=None, temperature=0.7, max_tokens=4096, **kwargs):
                raise RuntimeError("LLM down")

        parser = HybridIntentParser(llm_client=ExplodingLLM())
        result = await parser.parse("Test login", use_llm=True)
        assert result.source == "regex"
        assert result.redacted_text is not None

    async def test_deterministic_values_survive_llm_merge(self):
        llm = MockLLMClient(
            response=json.dumps({
                "goal": "g",
                "included_modules": [],
                "excluded_modules": [],
                "priorities": [],
                "testing_strategy": [],
                "business_objective": None,
                "success_criteria": [],
            })
        )
        parser = HybridIntentParser(llm_client=llm)
        raw = "Test https://app.example.com on production with firefox"
        result = await parser.parse(raw, use_llm=True)

        # Deterministic fields are always kept regardless of LLM output
        assert result.target_url == "https://app.example.com"
        assert result.environment == "production"
        assert result.browser == "firefox"

    async def test_prompt_context_remains_backward_compatible(self):
        llm = MockLLMClient(
            response=json.dumps({
                "goal": "g",
                "included_modules": ["Reports"],
                "excluded_modules": ["Settings"],
                "priorities": [],
                "testing_strategy": ["security"],
                "business_objective": None,
                "success_criteria": [],
            })
        )
        parser = HybridIntentParser(llm_client=llm)
        result = await parser.parse("Test reports, skip settings", use_llm=True)

        pc = result.prompt_context
        assert pc["focus_areas"] == ["Reports"]
        assert pc["excluded_modules"] == ["Settings"]
        assert "security" in pc["coverage_preferences"]
        assert "raw_text" in pc  # ParsedPromptIntent.to_dict() compatibility


@pytest.mark.unit
class TestHybridIntentParserSingleton:
    def test_singleton_default(self):
        parser = get_hybrid_intent_parser()
        assert isinstance(parser, HybridIntentParser)
        assert get_hybrid_intent_parser() is parser

    def test_fresh_instance_when_deps_given(self):
        dedicated = get_hybrid_intent_parser(llm_client=MockLLMClient())
        assert dedicated is not get_hybrid_intent_parser()
