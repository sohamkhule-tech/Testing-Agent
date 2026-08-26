from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.agents import TestDesignAgent
from app.core.interfaces import ILLMClient
from pydantic import BaseModel
from app.exceptions import AgentExecutionError, ValidationError
from app.schemas.inventory import (
    ButtonRecord,
    FormRecord,
    InputRecord,
    Inventory,
    InventoryMetadata,
    InventoryNavigation,
    InventoryStatistics,
    NavigationEdge,
    PageRecord,
    TableRecord,
)
from app.schemas.test_plan import TestPlan
from app.services import TestDesignService


class MockLLMClient(ILLMClient):
    """Mock LLM client for testing."""

    def __init__(self, response: str = "") -> None:
        self.response = response
        self.last_prompt = None
        self.last_system_prompt = None
        self.default_max_tokens = 16384

    async def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> str:
        self.last_prompt = prompt
        self.last_system_prompt = system_prompt
        return self.response

    async def complete_structured(
        self,
        prompt: str,
        response_model: type[BaseModel],
        system_prompt: str | None = None,
        **kwargs,
    ) -> BaseModel:
        """Return a parsed Pydantic model from the mock response."""
        self.last_prompt = prompt
        self.last_system_prompt = system_prompt
        # If empty response, return an empty model instance
        if not self.response:
            return response_model()

        try:
            return response_model.model_validate_json(self.response)
        except Exception:
            # Fallback: return an empty instance instead of failing tests
            return response_model()

    async def stream_complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs,
    ):
        """Async generator yielding the full response as a single chunk."""
        self.last_prompt = prompt
        self.last_system_prompt = system_prompt
        # Yield the response in one piece for simplicity
        if self.response is None:
            return
        yield self.response


SAMPLE_TEST_PLAN_JSON = """{
  "application_summary": {
    "name": "Test App",
    "total_pages": 2,
    "total_forms": 1,
    "total_apis": 0,
    "authentication_required": false,
    "auth_method": "none"
  },
  "modules": [
    {
      "name": "Navigation",
      "description": "Navigation module tests",
      "pages": ["https://example.com/"],
      "scenarios": [
        {
          "metadata": {
            "id": "TC-001",
            "title": "Verify home page loads",
            "description": "Verify home page loads correctly",
            "priority": "critical",
            "category": "smoke",
            "module": "Navigation",
            "target_page": "https://example.com/",
            "preconditions": ["User is authenticated"],
            "test_steps": ["Navigate to home page", "Verify page loads"],
            "expected_result": "Home page loads successfully",
            "required_test_data": [],
            "tags": ["smoke", "critical"],
            "dependencies": [],
            "risk_level": "high"
          },
          "use_cases": ["UC-001"]
        },
        {
          "metadata": {
            "id": "TC-002",
            "title": "Verify form submission",
            "description": "Verify contact form submits",
            "priority": "high",
            "category": "functional",
            "module": "Navigation",
            "target_page": "https://example.com/contact",
            "preconditions": ["Form is visible"],
            "test_steps": ["Fill form fields", "Submit form"],
            "expected_result": "Form submits successfully",
            "required_test_data": ["valid_email", "valid_message"],
            "tags": ["functional"],
            "dependencies": ["TC-001"],
            "risk_level": "medium"
          }
        }
      ]
    }
  ],
  "dependencies": {
    "scenario_ids": ["TC-001", "TC-002"],
    "required_data": ["valid_email", "valid_message"],
    "required_state": ["authenticated"]
  },
  "test_priorities": {
    "critical_paths": ["TC-001"],
    "high_priority": ["TC-002"],
    "medium_priority": [],
    "low_priority": []
  },
  "assumptions": {
    "assumptions": ["Application is deployed"],
    "constraints": ["Test environment only"],
    "risks": ["Network latency"]
  },
  "high_risk_areas": ["Authentication"],
  "regression_candidates": ["TC-001"],
  "accessibility_recommendations": ["Add ARIA labels"],
  "performance_recommendations": ["Optimize image loading"]
}"""


@pytest.fixture
def service():
    return TestDesignService()


@pytest.fixture
def mock_llm() -> MockLLMClient:
    return MockLLMClient(response=SAMPLE_TEST_PLAN_JSON)


@pytest.fixture
def agent(service, mock_llm):
    return TestDesignAgent(service=service, llm_client=mock_llm)


@pytest.fixture
def run_id():
    return uuid4()


@pytest.fixture
def sample_inventory(run_id):
    page_id = uuid4()
    return Inventory(
        metadata=InventoryMetadata(
            run_id=run_id,
            request_id=uuid4(),
            generated_at=datetime.now(timezone.utc),
            page_count=2,
            form_count=1,
            link_count=1,
            button_count=1,
            input_count=2,
            table_count=0,
            api_call_count=0,
            user_flow_count=0,
            screenshot_count=0,
        ),
        pages=[
            PageRecord(
                page_id=page_id,
                url="https://example.com/",
                title="Home",
                status_code=200,
                content_type="text/html",
                content_length=100,
                response_time=50,
                depth=0,
                discovered_at=datetime.now(timezone.utc),
            ),
        ],
        navigation=InventoryNavigation(
            edges=[],
            total_edges=0,
        ),
        forms=[
            FormRecord(
                page_id=page_id,
                form_id="contact-form",
                action="/submit",
                method="POST",
                inputs=[],
                submit_text="Submit",
            ),
        ],
        inputs=[
            InputRecord(
                page_id=page_id,
                input_type="text",
                name="email",
                required=True,
            ),
        ],
        buttons=[
            ButtonRecord(
                page_id=page_id,
                text="Submit",
                button_type="submit",
            ),
        ],
        tables=[],
        dialogs=[],
        uploads=[],
        downloads=[],
        authentication=[],
        api_calls=[],
        user_flows=[],
        screenshots=[],
        statistics=InventoryStatistics(
            total_pages=1,
            total_forms=1,
            total_buttons=1,
            total_inputs=1,
            total_links=0,
            total_tables=0,
            total_dialogs=0,
            total_uploads=0,
            total_downloads=0,
            total_api_calls=0,
            total_user_flows=0,
            total_screenshots=0,
            authenticated=False,
            auth_method="none",
        ),
    )


class TestTestDesignService:
    """Tests for TestDesignService."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_load_inventory_success(self, service, sample_inventory, tmp_path):
        contracts = tmp_path / "contracts"
        contracts.mkdir(parents=True)
        from app.utils import save_file
        await save_file(contracts / "inventory.json", sample_inventory.model_dump(mode="json"))

        inventory = await service.load_inventory(str(tmp_path))
        assert isinstance(inventory, Inventory)
        assert inventory.metadata.page_count == 2

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_load_inventory_missing(self, service, tmp_path):
        with pytest.raises(ValidationError, match="Inventory not found"):
            await service.load_inventory(str(tmp_path))

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_load_inventory_invalid_json(self, service, tmp_path):
        contracts = tmp_path / "contracts"
        contracts.mkdir(parents=True)
        (contracts / "inventory.json").write_text("invalid json")

        with pytest.raises(ValidationError):
            await service.load_inventory(str(tmp_path))

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_persist_test_plan(self, service, run_id, tmp_path):
        from app.schemas.test_plan import (
            ApplicationSummary,
            CoverageSummary,
            TestPlan,
        )

        test_plan = TestPlan(
            run_id=run_id,
            request_id=run_id,
            generated_at=datetime.now(timezone.utc),
            application_summary=ApplicationSummary(name="Test App"),
            coverage_summary=CoverageSummary(total_scenarios=2),
        )

        path = await service.persist_test_plan(str(tmp_path), test_plan)
        assert Path(path).exists()

        from app.utils import load_file
        data = await load_file(Path(path))
        assert data["application_summary"]["name"] == "Test App"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_markdown_summary(self, service, run_id, tmp_path):
        from app.schemas.test_plan import (
            ApplicationSummary,
            CoverageSummary,
            ScenarioDependencies,
            ScenarioMetadata,
            TestAssumptions,
            TestModule,
            TestPlan,
            TestPriorities,
            TestScenario,
        )

        test_plan = TestPlan(
            run_id=run_id,
            request_id=run_id,
            generated_at=datetime.now(timezone.utc),
            application_summary=ApplicationSummary(
                name="Test App",
                total_pages=2,
                total_forms=1,
                authentication_required=False,
            ),
            modules=[
                TestModule(
                    name="Navigation",
                    description="Navigation tests",
                    pages=["https://example.com"],
                    scenarios=[
                        TestScenario(
                            metadata=ScenarioMetadata(
                                id="TC-001",
                                title="Test navigation",
                                description="Verify navigation works",
                                priority="high",
                                category="navigation",
                                module="Navigation",
                                expected_result="Navigation successful",
                            ),
                        )
                    ],
                )
            ],
            coverage_summary=CoverageSummary(
                total_scenarios=1,
                by_priority={"high": 1},
                by_category={"navigation": 1},
            ),
            dependencies=ScenarioDependencies(),
            test_priorities=TestPriorities(critical_paths=["TC-001"]),
            assumptions=TestAssumptions(
                assumptions=["Test environment available"],
                constraints=["Limited test data"],
                risks=["Network connectivity"],
            ),
            high_risk_areas=["Authentication"],
            regression_candidates=["TC-001"],
            accessibility_recommendations=["Add ARIA labels"],
            performance_recommendations=["Optimize loading"],
        )

        md_path = await service.generate_markdown_summary(str(tmp_path), test_plan)
        assert Path(md_path).exists()
        
        content = Path(md_path).read_text(encoding="utf-8")
        assert "# Test Plan Summary" in content
        assert "Test App" in content
        assert "TC-001" in content
        assert "Navigation" in content
        assert "Accessibility Recommendations" in content

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_load_inventory_missing_workspace(self, service):
        with pytest.raises(ValidationError, match="Workspace not found"):
            await service.load_inventory("/nonexistent/path")


class TestTestDesignAgent:
    """Tests for TestDesignAgent."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_agent_initialization(self, agent):
        assert agent is not None
        assert agent.service is not None
        assert agent.llm_client is not None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_agent_execute_success(self, agent, sample_inventory, tmp_path):
        contracts = tmp_path / "contracts"
        contracts.mkdir(parents=True)
        from app.utils import save_file
        await save_file(contracts / "inventory.json", sample_inventory.model_dump(mode="json"))

        result = await agent.execute({
            "run_id": str(uuid4()),
            "request_id": str(uuid4()),
            "workspace_path": str(tmp_path),
        })

        assert result["success"] is True
        assert "test_plan_path" in result
        assert "test_plan_md_path" in result
        assert "scenario_count" in result
        assert result["scenario_count"] == 2
        assert Path(result["test_plan_path"]).exists()
        assert Path(result["test_plan_md_path"]).exists()
        assert (contracts / "test-plan.json").exists()
        assert (contracts / "test-plan.md").exists()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_agent_execute_missing_run_id(self, agent):
        with pytest.raises(AgentExecutionError, match="Missing 'run_id'"):
            await agent.execute({"workspace_path": "/tmp"})

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_agent_execute_missing_workspace(self, agent):
        with pytest.raises(AgentExecutionError, match="Missing 'workspace_path'"):
            await agent.execute({"run_id": str(uuid4())})

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_agent_get_system_prompt(self, agent):
        prompt = agent.get_system_prompt()
        assert "Test Design Agent" in prompt
        assert "Specification Driven Development" in prompt

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_agent_with_empty_inventory(self, service, mock_llm, tmp_path):
        empty_inventory_response = """{
  "application_summary": {
    "name": "Empty App",
    "total_pages": 0,
    "total_forms": 0,
    "total_apis": 0,
    "authentication_required": false,
    "auth_method": "none"
  },
  "modules": [],
  "dependencies": {"scenario_ids": [], "required_data": [], "required_state": []},
  "test_priorities": {
    "critical_paths": [],
    "high_priority": [],
    "medium_priority": [],
    "low_priority": []
  },
  "assumptions": {"assumptions": [], "constraints": [], "risks": []},
  "high_risk_areas": [],
  "regression_candidates": [],
  "accessibility_recommendations": [],
  "performance_recommendations": []
}"""
        mock_empty = MockLLMClient(response=empty_inventory_response)
        agent = TestDesignAgent(service=service, llm_client=mock_empty)

        run_id = uuid4()
        empty_inv = Inventory(
            metadata=InventoryMetadata(
                run_id=run_id,
                request_id=uuid4(),
                generated_at=datetime.now(timezone.utc),
                page_count=0,
            ),
            pages=[],
            navigation=InventoryNavigation(),
            statistics=InventoryStatistics(),
        )

        contracts = tmp_path / "contracts"
        contracts.mkdir(parents=True)
        from app.utils import save_file
        await save_file(contracts / "inventory.json", empty_inv.model_dump(mode="json"))

        result = await agent.execute({
            "run_id": str(run_id),
            "workspace_path": str(tmp_path),
        })

        assert result["success"] is True
        assert result["scenario_count"] == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_agent_llm_malformed_response(self, service, tmp_path):
        bad_llm = MockLLMClient(response="not valid json at all")
        agent = TestDesignAgent(service=service, llm_client=bad_llm)

        run_id = uuid4()
        inv = Inventory(
            metadata=InventoryMetadata(
                run_id=run_id,
                request_id=uuid4(),
                generated_at=datetime.now(timezone.utc),
                page_count=1,
            ),
            pages=[
                PageRecord(
                    page_id=uuid4(),
                    url="https://example.com/",
                    title="Home",
                    status_code=200,
                    content_type="text/html",
                    content_length=100,
                    response_time=50,
                    depth=0,
                    discovered_at=datetime.now(timezone.utc),
                ),
            ],
            navigation=InventoryNavigation(),
            statistics=InventoryStatistics(),
        )

        contracts = tmp_path / "contracts"
        contracts.mkdir(parents=True)
        from app.utils import save_file
        await save_file(contracts / "inventory.json", inv.model_dump(mode="json"))

        with pytest.raises(AgentExecutionError, match="LLM returned invalid JSON"):
            await agent.execute({
                "run_id": str(run_id),
                "workspace_path": str(tmp_path),
            })

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_agent_llm_empty_response(self, service, tmp_path):
        empty_llm = MockLLMClient(response="")
        agent = TestDesignAgent(service=service, llm_client=empty_llm)

        run_id = uuid4()
        inv = Inventory(
            metadata=InventoryMetadata(
                run_id=run_id,
                request_id=uuid4(),
                generated_at=datetime.now(timezone.utc),
                page_count=1,
            ),
            pages=[
                PageRecord(
                    page_id=uuid4(),
                    url="https://example.com/",
                    title="Home",
                    status_code=200,
                    content_type="text/html",
                    content_length=100,
                    response_time=50,
                    depth=0,
                    discovered_at=datetime.now(timezone.utc),
                ),
            ],
            navigation=InventoryNavigation(),
            statistics=InventoryStatistics(),
        )

        contracts = tmp_path / "contracts"
        contracts.mkdir(parents=True)
        from app.utils import save_file
        await save_file(contracts / "inventory.json", inv.model_dump(mode="json"))

        with pytest.raises(AgentExecutionError, match="LLM returned empty response"):
            await agent.execute({
                "run_id": str(run_id),
                "workspace_path": str(tmp_path),
            })

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_agent_recovers_from_transient_bad_json(self, service, tmp_path):
        """Regression: one malformed LLM response is retried, not fatal to the run."""
        valid_response = """{
  "application_summary": {
    "name": "App",
    "total_pages": 1,
    "total_forms": 0,
    "total_apis": 0,
    "authentication_required": false,
    "auth_method": "none"
  },
  "modules": [
    {
      "name": "Core",
      "description": "Core functionality",
      "pages": ["https://example.com/"],
      "scenarios": [
        {
          "metadata": {
            "id": "TC-001",
            "title": "Verify app loads",
            "description": "Smoke",
            "priority": "critical",
            "category": "smoke",
            "module": "Core",
            "target_page": "https://example.com/",
            "preconditions": [],
            "test_steps": ["Load the app"],
            "expected_result": "App loads",
            "required_test_data": [],
            "tags": ["smoke"],
            "dependencies": [],
            "risk_level": "low"
          },
          "use_cases": []
        }
      ]
    }
  ],
  "dependencies": {"scenario_ids": [], "required_data": [], "required_state": []},
  "test_priorities": {
    "critical_paths": ["TC-001"],
    "high_priority": [],
    "medium_priority": [],
    "low_priority": []
  },
  "assumptions": {"assumptions": [], "constraints": [], "risks": []},
  "high_risk_areas": [],
  "regression_candidates": [],
  "accessibility_recommendations": [],
  "performance_recommendations": []
}"""

        class FlakyLLM(MockLLMClient):
            def __init__(self):
                super().__init__()
                self.calls = 0

            async def complete(self, prompt, system_prompt=None, temperature=0.7, max_tokens=4096, **kwargs):
                self.calls += 1
                return "not valid json at all" if self.calls == 1 else valid_response

        agent = TestDesignAgent(service=service, llm_client=FlakyLLM())

        run_id = uuid4()
        inv = Inventory(
            metadata=InventoryMetadata(
                run_id=run_id,
                request_id=uuid4(),
                generated_at=datetime.now(timezone.utc),
                page_count=1,
            ),
            pages=[
                PageRecord(
                    page_id=uuid4(),
                    url="https://example.com/",
                    title="Home",
                    status_code=200,
                    content_type="text/html",
                    content_length=100,
                    response_time=50,
                    depth=0,
                    discovered_at=datetime.now(timezone.utc),
                ),
            ],
            navigation=InventoryNavigation(),
            statistics=InventoryStatistics(),
        )

        contracts = tmp_path / "contracts"
        contracts.mkdir(parents=True)
        from app.utils import save_file
        await save_file(contracts / "inventory.json", inv.model_dump(mode="json"))

        result = await agent.execute({
            "run_id": str(run_id),
            "workspace_path": str(tmp_path),
        })

        assert result["success"] is True
        assert result["scenario_count"] == 1


class TestDesignEdgeCases:
    """Edge case tests for test design agent."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_duplicate_scenarios_handling(self, service, mock_llm, tmp_path):
        run_id = uuid4()
        page_id = uuid4()
        inv = Inventory(
            metadata=InventoryMetadata(
                run_id=run_id,
                request_id=uuid4(),
                generated_at=datetime.now(timezone.utc),
                page_count=2,
            ),
            pages=[
                PageRecord(
                    page_id=page_id,
                    url="https://example.com/",
                    title="Home",
                    status_code=200,
                    content_type="text/html",
                    content_length=100,
                    response_time=50,
                    depth=0,
                    discovered_at=datetime.now(timezone.utc),
                ),
            ],
            navigation=InventoryNavigation(),
            statistics=InventoryStatistics(max_depth_reached=0),
        )

        contracts = tmp_path / "contracts"
        contracts.mkdir(parents=True)
        from app.utils import save_file
        await save_file(contracts / "inventory.json", inv.model_dump(mode="json"))

        agent = TestDesignAgent(service=service, llm_client=mock_llm)
        result = await agent.execute({
            "run_id": str(run_id),
            "workspace_path": str(tmp_path),
        })

        assert result["success"] is True
        assert (contracts / "test-plan.json").exists()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_single_page_application(self, service, tmp_path):
        single_page_response = """{
  "application_summary": {
    "name": "SPA",
    "total_pages": 1,
    "total_forms": 0,
    "total_apis": 0,
    "authentication_required": false,
    "auth_method": "none"
  },
  "modules": [
    {
      "name": "Core",
      "description": "Core functionality",
      "pages": ["https://spa.example.com/"],
      "scenarios": [
        {
          "metadata": {
            "id": "TC-001",
            "title": "Verify SPA loads",
            "description": "Verify single page app loads",
            "priority": "critical",
            "category": "smoke",
            "module": "Core",
            "target_page": "https://spa.example.com/",
            "preconditions": [],
            "test_steps": ["Load application"],
            "expected_result": "App loads",
            "required_test_data": [],
            "tags": ["smoke"],
            "dependencies": [],
            "risk_level": "low"
          },
          "use_cases": []
        }
      ]
    }
  ],
  "dependencies": {"scenario_ids": ["TC-001"], "required_data": [], "required_state": []},
  "test_priorities": {
    "critical_paths": ["TC-001"],
    "high_priority": [],
    "medium_priority": [],
    "low_priority": []
  },
  "assumptions": {"assumptions": [], "constraints": [], "risks": []},
  "high_risk_areas": [],
  "regression_candidates": ["TC-001"],
  "accessibility_recommendations": [],
  "performance_recommendations": []
}"""
        mock_llm = MockLLMClient(response=single_page_response)
        agent = TestDesignAgent(service=service, llm_client=mock_llm)

        run_id = uuid4()
        inv = Inventory(
            metadata=InventoryMetadata(
                run_id=run_id,
                request_id=uuid4(),
                generated_at=datetime.now(timezone.utc),
                page_count=1,
            ),
            pages=[
                PageRecord(
                    page_id=uuid4(),
                    url="https://spa.example.com/",
                    title="SPA",
                    status_code=200,
                    content_type="text/html",
                    content_length=100,
                    response_time=50,
                    depth=0,
                    discovered_at=datetime.now(timezone.utc),
                ),
            ],
            navigation=InventoryNavigation(),
            statistics=InventoryStatistics(),
        )

        contracts = tmp_path / "contracts"
        contracts.mkdir(parents=True)
        from app.utils import save_file
        await save_file(contracts / "inventory.json", inv.model_dump(mode="json"))

        result = await agent.execute({
            "run_id": str(run_id),
            "workspace_path": str(tmp_path),
        })
        assert result["success"] is True
        assert result["scenario_count"] == 1


class TestPlatformWorkflowIntegration:
    """Integration tests for platform workflow with test design."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_workflow_state_has_test_plan_fields(self, sample_inventory, tmp_path):
        from app.workflows.trigger_workflow import PlatformWorkflowState

        state = PlatformWorkflowState(
            run_id=str(uuid4()),
            workspace_path=str(tmp_path),
        )
        assert hasattr(state, "test_plan_path")
        assert hasattr(state, "test_plan_summary")
        assert state.test_plan_path is None
        assert state.test_plan_summary is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_workflow_node_results_include_test_design(self):
        from app.workflows.trigger_workflow import PlatformWorkflowState

        state = PlatformWorkflowState(
            run_id=str(uuid4()),
        )
        state.test_plan_path = str(uuid4())
        state.test_plan_summary = {"scenario_count": 5}
        assert state.test_plan_path is not None
        assert state.test_plan_summary["scenario_count"] == 5
