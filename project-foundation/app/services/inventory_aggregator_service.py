from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from app.exceptions import StorageError, ValidationError
from app.logging import LoggerMixin
from app.schemas.crawler import (
    AuthRecord,
    CrawlPackage,
)
from app.schemas.inventory import (
    Inventory,
    InventoryMetadata,
    InventoryNavigation,
    InventoryStatistics,
)
from app.utils import load_file, save_file


class InventoryAggregatorService(LoggerMixin):
    """
    Aggregates crawler outputs into a canonical inventory.

    Deterministic service — no LLM, no reasoning, no test generation.
    """

    def __init__(self) -> None:
        super().__init__()

    async def aggregate(
        self,
        run_id: UUID,
        workspace_path: str,
        crawl_package: CrawlPackage | None = None,
        excluded_modules: list[str] | None = None,
    ) -> Inventory:
        """
        Load, aggregate, deduplicate, and return inventory.

        Args:
            run_id: Run identifier
            workspace_path: Run workspace directory path
            crawl_package: Optional pre-loaded crawl package (for testing)

        Returns:
            Normalized Inventory

        Raises:
            ValidationError: If required artifacts are missing or malformed
            StorageError: If file operations fail
        """
        workspace = Path(workspace_path)
        if not workspace.exists():
            raise ValidationError(f"Workspace not found: {workspace_path}")

        errors: list[str] = []
        source_files: list[str] = []

        # Load crawl package
        if crawl_package is None:
            crawl_package = await self._load_crawl_package(workspace)
        source_files.append("contracts/crawl-package.json")

        # Validate crawl package
        self._validate_crawl_package(crawl_package, errors)

        excluded_modules = excluded_modules or []

        # Aggregate pages (deduplicate by URL)
        pages, dup_pages = self._aggregate_pages(crawl_package)

        # Partition pages into included vs excluded based on prompt scope
        if excluded_modules:
            included_pages, excluded_page_count = self._apply_scope_filter(pages, excluded_modules)
        else:
            included_pages, excluded_page_count = pages, 0

        # Aggregate navigation (deduplicate edges)
        navigation, dup_links = self._aggregate_navigation(crawl_package)

        # Aggregate links (flatten from navigation for convenience)
        links = self._aggregate_links(crawl_package, pages)

        # Aggregate screenshots
        screenshots = self._aggregate_screenshots(crawl_package)

        # Collect stats
        auth_method = "none"
        authenticated = False
        if crawl_package.session:
            authenticated = crawl_package.session.authenticated
            auth_method = crawl_package.session.auth_method.value if hasattr(crawl_package.session.auth_method, "value") else crawl_package.session.auth_method

        avg_response_time = 0.0
        max_depth = 0
        if crawl_package.statistics:
            avg_response_time = float(crawl_package.statistics.response_time_ms.average)
        if crawl_package.crawl_summary:
            max_depth = crawl_package.crawl_summary.crawl_depth_reached

        pages = included_pages

        stats = InventoryStatistics(
            total_pages=len(pages),
            total_forms=len(crawl_package.forms),
            total_buttons=len(crawl_package.buttons),
            total_inputs=len(crawl_package.inputs),
            total_links=len(links),
            total_tables=len(crawl_package.tables),
            total_dialogs=len(crawl_package.dialogs),
            total_uploads=len(crawl_package.uploads),
            total_downloads=len(crawl_package.downloads),
            total_api_calls=len(crawl_package.api_calls),
            total_user_flows=len(crawl_package.user_flows),
            total_screenshots=len(screenshots),
            average_response_time_ms=avg_response_time,
            max_depth_reached=max_depth,
            authenticated=authenticated,
            auth_method=auth_method,
        )

        # Build metadata
        metadata = InventoryMetadata(
            run_id=run_id,
            request_id=crawl_package.request_id,
            application_id=crawl_package.application_id,
            generated_at=datetime.now(timezone.utc),
            source_files=source_files,
            page_count=len(pages),
            form_count=len(crawl_package.forms),
            link_count=len(links),
            button_count=len(crawl_package.buttons),
            input_count=len(crawl_package.inputs),
            table_count=len(crawl_package.tables),
            api_call_count=len(crawl_package.api_calls),
            user_flow_count=len(crawl_package.user_flows),
            screenshot_count=len(screenshots),
            duplicate_pages_removed=dup_pages,
            duplicate_links_removed=dup_links,
            excluded_modules=excluded_modules,
            excluded_page_count=excluded_page_count,
            errors=errors,
        )

        inventory = Inventory(
            metadata=metadata,
            pages=pages,
            navigation=navigation,
            forms=crawl_package.forms,
            inputs=crawl_package.inputs,
            dropdowns=crawl_package.dropdowns,
            checkboxes=crawl_package.checkboxes,
            radio_buttons=crawl_package.radios,
            buttons=crawl_package.buttons,
            links=links,
            tables=crawl_package.tables,
            dialogs=crawl_package.dialogs,
            uploads=crawl_package.uploads,
            downloads=crawl_package.downloads,
            authentication=[self._session_to_auth(crawl_package.session)] if crawl_package.session else [],
            api_calls=crawl_package.api_calls,
            user_flows=crawl_package.user_flows,
            screenshots=screenshots,
            statistics=stats,
        )

        return inventory

    async def aggregate_and_persist(
        self,
        run_id: UUID,
        workspace_path: str,
        crawl_package: CrawlPackage | None = None,
        excluded_modules: list[str] | None = None,
    ) -> Inventory:
        """
        Aggregate crawler outputs and persist inventory.json.

        Args:
            run_id: Run identifier
            workspace_path: Run workspace directory path
            crawl_package: Optional pre-loaded crawl package (for testing)
            excluded_modules: Module/page names to exclude per user prompt

        Returns:
            Persisted Inventory

        Raises:
            ValidationError: If required artifacts are missing or malformed
            StorageError: If file operations fail
        """
        inventory = await self.aggregate(run_id, workspace_path, crawl_package, excluded_modules)
        await self._persist_inventory(Path(workspace_path), inventory)
        return inventory

    async def _load_crawl_package(self, workspace: Path) -> CrawlPackage:
        """Load and parse crawl-package.json from workspace."""
        crawl_package_path = workspace / "contracts" / "crawl-package.json"
        if not crawl_package_path.exists():
            raise ValidationError(f"Crawl package not found: {crawl_package_path}")

        try:
            data = await load_file(crawl_package_path)
            return CrawlPackage(**data)
        except Exception as e:
            raise ValidationError(f"Invalid crawl package: {str(e)}")

    def _validate_crawl_package(
        self, pkg: CrawlPackage, errors: list[str]
    ) -> None:
        """Validate crawl package, collecting non-fatal errors."""
        if not pkg.run_id:
            errors.append("Missing run_id in crawl package")
        if not pkg.request_id:
            errors.append("Missing request_id in crawl package")

        seen_ids: set[str] = set()
        for page in pkg.visited_pages:
            pid = str(page.page_id)
            if pid in seen_ids:
                errors.append(f"Duplicate page_id in crawl package: {pid}")
            seen_ids.add(pid)

    @staticmethod
    def _apply_scope_filter(
        pages: list,
        excluded_modules: list[str],
    ) -> tuple[list, int]:
        """Remove pages whose URL or title matches an excluded module name (case-insensitive)."""
        lower_excluded = [m.lower() for m in excluded_modules]
        included, excluded_count = [], 0
        for page in pages:
            haystack = f"{page.url} {page.title or ''}".lower()
            if any(mod in haystack for mod in lower_excluded):
                excluded_count += 1
            else:
                included.append(page)
        return included, excluded_count

    def _aggregate_pages(
        self, pkg: CrawlPackage
    ) -> tuple[list, int]:
        """Aggregate pages, removing duplicates by URL."""
        seen_urls: set[str] = set()
        unique_pages: list = []
        duplicates = 0

        for page in sorted(pkg.visited_pages, key=lambda p: p.depth):
            key = page.url.rstrip("/").lower()
            if key not in seen_urls:
                seen_urls.add(key)
                unique_pages.append(page)
            else:
                duplicates += 1

        return unique_pages, duplicates

    def _aggregate_navigation(
        self, pkg: CrawlPackage
    ) -> tuple[InventoryNavigation, int]:
        """Aggregate navigation edges, removing duplicates."""
        seen_edges: set[tuple[str, str]] = set()
        unique_edges: list = []
        duplicates = 0

        for edge in pkg.navigation_graph.edges:
            key = (str(edge.source_page_id), str(edge.target_page_id))
            if key not in seen_edges:
                seen_edges.add(key)
                unique_edges.append(edge)
            else:
                duplicates += 1

        nav = InventoryNavigation(
            edges=unique_edges,
            root_page_id=pkg.navigation_graph.root_page_id,
            total_edges=len(unique_edges),
        )
        return nav, duplicates

    def _aggregate_links(
        self, pkg: CrawlPackage, pages: list
    ) -> list[tuple[str, str, str]]:
        """Aggregate links from navigation edges with page URL mapping."""
        page_map = {str(p.page_id): p.url for p in pkg.visited_pages}
        seen_links: set[str] = set()
        links: list[tuple[str, str, str]] = []

        for edge in pkg.navigation_graph.edges:
            target_url = edge.link_url or ""
            text = edge.link_text or ""
            source_url = page_map.get(str(edge.source_page_id), str(edge.source_page_id))
            key = (target_url.rstrip("/").lower(), source_url.rstrip("/").lower())
            if key not in seen_links:
                seen_links.add(key)
                links.append((target_url, text, source_url))

        return links

    def _aggregate_screenshots(self, pkg: CrawlPackage) -> list:
        """Aggregate screenshot records from crawl package."""
        return list(pkg.screenshots)

    def _session_to_auth(self, session) -> AuthRecord:
        """Convert SessionInfo to AuthRecord."""
        from app.schemas.crawler import SessionInfo

        auth_type = session.auth_method.value if hasattr(session.auth_method, "value") else session.auth_method
        return AuthRecord(
            page_id=session.auth_page_id,
            auth_type=auth_type,
            requires_authentication=session.authenticated,
        )

    async def _persist_inventory(
        self, workspace: Path, inventory: Inventory
    ) -> None:
        """Write inventory.json to workspace contracts directory."""
        contracts_dir = workspace / "contracts"
        contracts_dir.mkdir(parents=True, exist_ok=True)
        output_path = contracts_dir / "inventory.json"

        try:
            data = inventory.model_dump(mode="json")
            await save_file(output_path, data)
            self.logger.info(
                "inventory_persisted",
                path=str(output_path),
                pages=len(inventory.pages),
                forms=len(inventory.forms),
            )
        except Exception as e:
            raise StorageError(f"Failed to persist inventory: {str(e)}")
