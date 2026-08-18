"""
Crawler Agent

AI Agent responsible for web application crawling and discovery.
"""

import asyncio
from typing import Any
from uuid import UUID

from app.constants import RunStatus
from app.core.interfaces import IAgent
from app.exceptions import AgentExecutionError
from app.logging import LoggerMixin
from app.prompts import get_prompt
from app.schemas import CrawlRequest
from app.services import CrawlerService


class CrawlerAgent(IAgent, LoggerMixin):
    """
    Crawler Agent - discovers application navigation and structure.
    
    Responsibilities:
    - Launch browser and navigate target application
    - Discover pages, URLs, navigation paths
    - Collect links, forms, buttons, menus
    - Capture screenshots and network traces
    - Generate crawl-package.json contract
    - Update graph state for downstream agents
    """

    def __init__(self, service: CrawlerService) -> None:
        """
        Initialize crawler agent.

        Args:
            service: Crawler service for execution
        """
        super().__init__()
        self.service = service
        self._execute_lock = asyncio.Lock()

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Serialize access to the stateful crawler service."""
        async with self._execute_lock:
            return await self._execute_impl(input_data)

    async def _execute_impl(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        Execute crawler agent logic.

        Args:
            input_data: Input data containing crawl parameters

        Returns:
            Agent output with crawl results

        Raises:
            AgentExecutionError: If execution fails
        """
        try:
            self.logger.info("crawler_agent_started")

            # Parse input from workflow state
            run_id_str = input_data.get("run_id")
            request_id_str = input_data.get("request_id")
            workspace_path = input_data.get("workspace_path")
            
            # Get crawl parameters from trigger output
            trigger_output = input_data.get("trigger_output", {})
            request_data = input_data.get("request_data", {})
            
            if not run_id_str:
                raise AgentExecutionError("Missing 'run_id' in input data")
            if not workspace_path:
                raise AgentExecutionError("Missing 'workspace_path' in input data")

            # Parse UUIDs
            try:
                run_id = UUID(run_id_str)
                request_id = UUID(request_id_str) if request_id_str else run_id
            except (ValueError, TypeError) as e:
                raise AgentExecutionError(f"Invalid UUID format: {str(e)}") from e

            # Extract crawl parameters (support both snake_case and camelCase keys)
            target_app = request_data.get("target_application", request_data.get("targetApplication", {}))
            execution_mode = request_data.get("execution_mode", request_data.get("executionMode", {}))
            
            target_url = target_app.get("base_url", target_app.get("url"))
            if not target_url:
                raise AgentExecutionError("Missing target URL in request data")

            max_depth = execution_mode.get("max_crawl_depth", execution_mode.get("maxCrawlDepth", 3))
            max_pages = execution_mode.get("max_pages", execution_mode.get("maxPages", 50))

            # Phase 5/6: apply scope overrides from user prompt
            scope_overrides = input_data.get("scope_overrides", {})
            auth_context_dict = input_data.get("auth_context", {})

            # Merge scope: prompt-level includes/excludes restrict the crawl
            exclude_patterns = scope_overrides.get("exclude_pages", [])
            include_patterns = scope_overrides.get("include_pages", [])

            # Execution Scope Enforcement: ExecutionPlan is the single source of
            # truth. Build the resolver from the serialised ExecutionPlan when
            # available; otherwise fall back to the legacy scope_overrides.
            from app.execution_scope.resolver import ExecutionScopeResolver
            execution_plan = input_data.get("execution_plan")
            if execution_plan:
                self.service._scope_resolver = ExecutionScopeResolver(execution_plan)
            else:
                self.service._scope_resolver = ExecutionScopeResolver(
                    scope={
                        "included_modules": [],
                        "excluded_modules": [],
                        "included_pages": include_patterns,
                        "excluded_pages": exclude_patterns,
                    }
                )

            # If the user specified include_pages, restrict max crawl to those paths
            effective_max_depth = max_depth
            effective_max_pages = max_pages

            # Build crawl request
            crawl_request = CrawlRequest(
                run_id=run_id,
                request_id=request_id,
                workspace_path=workspace_path,
                target_url=str(target_url),
                max_depth=effective_max_depth,
                max_pages=effective_max_pages,
                timeout=execution_mode.get("timeout", 30000),
                max_retries=execution_mode.get("max_retries", execution_mode.get("maxRetries", 2)),
                browser=execution_mode.get("browser", "chromium"),
                headless=execution_mode.get("headless", True),
                screenshot=True,
            )

            # Pass auth context to service for login (SECURITY: never logged)
            if auth_context_dict:
                from app.services.prompt_builder import AuthContext as _AC
                self.service._auth_context = _AC(
                    username=auth_context_dict.get("username"),
                    password=auth_context_dict.get("password"),
                    login_url=auth_context_dict.get("login_url"),
                    auth_strategy=auth_context_dict.get("auth_strategy", "form"),
                )
                self.logger.info("crawler_auth_configured", **self.service._auth_context.safe_summary())

            # Pass URL filters to service
            self.service._exclude_patterns = exclude_patterns
            self.service._include_patterns = include_patterns

            # Execution Scope Enforcement: log what the resolver concluded for
            # the crawl (visible in run traces / metrics).
            self.logger.info(
                "crawler_scope_resolver_configured",
                included_modules=self.service._scope_resolver.included_modules,
                excluded_modules=self.service._scope_resolver.excluded_modules,
                stopping_conditions=self.service._scope_resolver.stopping_conditions,
            )

            self.logger.info(
                "crawler_request_prepared",
                run_id=str(run_id),
                target_url=target_url,
                max_depth=crawl_request.max_depth,
                max_pages=crawl_request.max_pages,
            )

            # Execute crawl
            crawl_package = await self.service.crawl(crawl_request)

            self.logger.info(
                "crawler_agent_completed",
                run_id=str(run_id),
                pages_visited=crawl_package.crawl_summary.pages_visited,
                status=crawl_package.crawl_summary.status,
            )

            # Return output for graph state
            return {
                "success": True,
                "run_id": str(run_id),
                "request_id": str(request_id),
                "workspace_path": workspace_path,
                "crawl_status": crawl_package.crawl_summary.status,
                "pages_visited": crawl_package.crawl_summary.pages_visited,
                "total_links": crawl_package.crawl_summary.total_links,
                "crawl_depth_reached": crawl_package.crawl_summary.crawl_depth_reached,
                "message": f"Crawled {crawl_package.crawl_summary.pages_visited} pages successfully",
                "crawl_package_path": f"{workspace_path}/contracts/crawl-package.json",
                "scope_trace": list(crawl_package.scope_trace),
            }

        except AgentExecutionError:
            raise
        except Exception as e:
            self.logger.error("crawler_agent_failed", error=str(e))
            raise AgentExecutionError(f"Crawler agent execution failed: {str(e)}") from e

    def get_system_prompt(self) -> str:
        """
        Get crawler agent system prompt.

        Returns:
            System prompt string
        """
        return get_prompt("ai-crawler-agent")
