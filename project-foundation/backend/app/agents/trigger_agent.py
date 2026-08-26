"""
Trigger Agent

AI Agent responsible for test run initialization.
"""

from typing import Any
from uuid import UUID

from app.constants import RunStatus
from app.core.interfaces import IAgent
from app.domain import RunContext, RunEntity
from app.exceptions import AgentExecutionError
from app.logging import LoggerMixin
from app.schemas import CreateRunRequest
from app.services import TriggerService


class TriggerAgent(IAgent, LoggerMixin):
    """
    Trigger Agent - initializes test execution runs.

    Responsibilities:
    - Validate incoming requests
    - Generate run identifiers
    - Create execution workspace
    - Initialize run metadata
    - Produce test-run-request.json contract
    """

    def __init__(self, service: TriggerService) -> None:
        """
        Initialize trigger agent.

        Args:
            service: Trigger service for business logic
        """
        super().__init__()
        self.service = service

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        Execute trigger agent logic.

        Args:
            input_data: Input data containing run request

        Returns:
            Agent output with run details

        Raises:
            AgentExecutionError: If execution fails
        """
        try:
            self.logger.info("trigger_agent_started")

            # Parse input
            request_data = input_data.get("request")
            if not request_data:
                raise AgentExecutionError("Missing 'request' in input data")

            requested_by = input_data.get("requested_by")

            # Create request model
            request = CreateRunRequest(**request_data)

            # Execute trigger service
            entity, context = await self.service.create_run(
                request=request,
                requested_by=requested_by,
            )

            # Update status to running
            await self.service.update_status(
                run_id=entity.run_id,
                status=RunStatus.RUNNING,
                stage="trigger_completed",
                progress=10,
                message="Trigger agent completed successfully",
            )

            self.logger.info(
                "trigger_agent_completed",
                run_id=str(entity.run_id),
            )

            # Return output
            return {
                "success": True,
                "run_id": str(entity.run_id),
                "request_id": str(entity.request_id),
                "workspace_path": str(context.workspace_root),
                "status": entity.status.value if hasattr(entity.status, "value") else entity.status,
                "message": "Run initialized successfully",
            }

        except AgentExecutionError:
            raise
        except Exception as e:
            self.logger.error("trigger_agent_failed", error=str(e))
            raise AgentExecutionError(f"Trigger agent execution failed: {str(e)}")

    def get_system_prompt(self) -> str:
        """
        Get trigger agent system prompt.

        Returns:
            System prompt for trigger agent
        """
        return """You are the Trigger Agent of an Enterprise AI-Driven Testing Platform.

Your responsibility is to:
1. Validate incoming test requests
2. Generate unique run identifiers
3. Create execution workspaces
4. Initialize run metadata
5. Produce canonical test-run-request.json contracts

You are the first agent in the pipeline. Accuracy is critical.

Never crawl websites, discover DOM, design tests, generate code, or execute tests.
Your sole purpose is initialization and validation."""
