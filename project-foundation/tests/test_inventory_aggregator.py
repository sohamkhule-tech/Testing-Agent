from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.schemas.crawler import (
    CrawlPackage,
    CrawlStatistics,
    CrawlSummary,
    NavigationEdge,
    NavigationGraph,
    PageRecord,
    ResponseTimeStats,
    SessionInfo,
)
from app.schemas.inventory import Inventory
from app.services.inventory_aggregator_service import InventoryAggregatorService


@pytest.fixture
def service():
    return InventoryAggregatorService()


@pytest.fixture
def run_id():
    return uuid4()


@pytest.fixture
def sample_crawl_package(run_id):
    page1_id = uuid4()
    page2_id = uuid4()

    return CrawlPackage(
        run_id=run_id,
        request_id=uuid4(),
        application_id=uuid4(),
        crawl_summary=CrawlSummary(
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            duration=1000,
            status="completed",
            pages_visited=2,
            pages_skipped=0,
            total_links=2,
            crawl_depth_reached=2,
        ),
        visited_pages=[
            PageRecord(
                page_id=page1_id,
                url="https://example.com/",
                title="Home",
                status_code=200,
                content_type="text/html",
                content_length=100,
                response_time=50,
                depth=0,
                discovered_at=datetime.now(timezone.utc),
            ),
            PageRecord(
                page_id=page2_id,
                url="https://example.com/about",
                title="About",
                status_code=200,
                content_type="text/html",
                content_length=200,
                response_time=75,
                depth=1,
                discovered_at=datetime.now(timezone.utc),
            ),
        ],
        navigation_graph=NavigationGraph(
            edges=[
                NavigationEdge(
                    source_page_id=page1_id,
                    target_page_id=page2_id,
                    link_text="About Us",
                    link_url="https://example.com/about",
                    relationship="navigation",
                ),
            ],
            root_page_id=page1_id,
        ),
            statistics=CrawlStatistics(
                response_time_ms=ResponseTimeStats(min=50, max=75, average=62, median=62),
            ),
            session=SessionInfo(
                authenticated=False,
                auth_method="none",
                cookies=[],
            ),
        )


class TestInventoryAggregatorService:
    """Tests for the InventoryAggregatorService."""

    @pytest.mark.asyncio
    async def test_aggregate_creates_inventory(
        self, service, run_id, sample_crawl_package, tmp_path
    ):
        inventory = await service.aggregate(run_id, str(tmp_path), sample_crawl_package)

        assert isinstance(inventory, Inventory)
        assert len(inventory.pages) == 2
        assert len(inventory.navigation.edges) == 1
        assert len(inventory.links) == 1
        assert inventory.metadata.page_count == 2
        assert inventory.metadata.duplicate_pages_removed == 0

    @pytest.mark.asyncio
    async def test_aggregate_empty_crawl_package(
        self, service, run_id, tmp_path
    ):
        empty_pkg = CrawlPackage(
            run_id=run_id,
            request_id=uuid4(),
            crawl_summary=CrawlSummary(
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc),
                duration=0,
                status="completed",
                pages_visited=0,
                pages_skipped=0,
                total_links=0,
                crawl_depth_reached=0,
            ),
            visited_pages=[],
            navigation_graph=NavigationGraph(edges=[], root_page_id=None),
        )

        inventory = await service.aggregate(run_id, str(tmp_path), empty_pkg)

        assert len(inventory.pages) == 0
        assert len(inventory.navigation.edges) == 0
        assert len(inventory.links) == 0
        assert inventory.metadata.page_count == 0

    @pytest.mark.asyncio
    async def test_aggregate_deduplicates_duplicate_pages(
        self, service, run_id, tmp_path
    ):
        page_id = uuid4()
        dup_pkg = CrawlPackage(
            run_id=run_id,
            request_id=uuid4(),
            crawl_summary=CrawlSummary(
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc),
                duration=500,
                status="completed",
                pages_visited=2,
                pages_skipped=0,
                total_links=0,
                crawl_depth_reached=1,
            ),
            visited_pages=[
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
                PageRecord(
                    page_id=uuid4(),
                    url="https://example.com/",
                    title="Home Dup",
                    status_code=200,
                    content_type="text/html",
                    content_length=100,
                    response_time=50,
                    depth=1,
                    discovered_at=datetime.now(timezone.utc),
                ),
            ],
            navigation_graph=NavigationGraph(edges=[], root_page_id=page_id),
        )

        inventory = await service.aggregate(run_id, str(tmp_path), dup_pkg)

        assert len(inventory.pages) == 1
        assert inventory.metadata.duplicate_pages_removed == 1

    @pytest.mark.asyncio
    async def test_aggregate_and_persist_writes_file(
        self, service, run_id, sample_crawl_package, tmp_path
    ):
        inventory = await service.aggregate_and_persist(
            run_id, str(tmp_path), sample_crawl_package
        )

        inventory_path = tmp_path / "contracts" / "inventory.json"
        assert inventory_path.exists()

        import json
        data = json.loads(inventory_path.read_text())
        assert data["metadata"]["page_count"] == 2
        assert len(data["pages"]) == 2

    @pytest.mark.asyncio
    async def test_aggregate_missing_workspace_raises(
        self, service, run_id
    ):
        from app.exceptions import ValidationError

        with pytest.raises(ValidationError, match="Workspace not found"):
            await service.aggregate(run_id, "/nonexistent/path")

    @pytest.mark.asyncio
    async def test_aggregate_missing_crawl_package_file(
        self, service, run_id, tmp_path
    ):
        from app.exceptions import ValidationError

        with pytest.raises(ValidationError, match="Crawl package not found"):
            await service.aggregate(run_id, str(tmp_path))

    @pytest.mark.asyncio
    async def test_aggregate_corrupted_crawl_package_raises(
        self, service, run_id, tmp_path
    ):
        contracts_dir = tmp_path / "contracts"
        contracts_dir.mkdir(parents=True, exist_ok=True)
        (contracts_dir / "crawl-package.json").write_text("not valid json")

        from app.exceptions import ValidationError

        with pytest.raises(ValidationError, match="Invalid crawl package"):
            await service.aggregate(run_id, str(tmp_path))


