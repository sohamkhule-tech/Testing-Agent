from uuid import uuid4

from app.schemas.crawler import CrawlRequest
from app.services.crawler_service import CrawlerService


def test_canonicalize_url_collapses_duplicate_forms() -> None:
    canonicalize = CrawlerService._canonicalize_url

    assert canonicalize("HTTPS://Example.COM:443/app/") == "https://example.com/app"
    assert canonicalize("https://example.com/app#section") == "https://example.com/app"
    assert canonicalize("https://example.com/app?b=2&a=1") == "https://example.com/app?a=1&b=2"


def test_canonicalize_url_preserves_hash_router_routes() -> None:
    assert CrawlerService._canonicalize_url("https://example.com/#/settings/") == (
        "https://example.com/#/settings"
    )


def test_crawl_request_has_bounded_retries() -> None:
    request = CrawlRequest(
        run_id=uuid4(),
        request_id=uuid4(),
        workspace_path="storage/runs/example",
        target_url="https://example.com",
        max_retries=2,
    )

    assert request.max_retries == 2
