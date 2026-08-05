"""
Crawler Schemas

Pydantic models for crawler request/response following crawl-package.json contract.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class CrawlSummary(BaseModel):
    """Crawl execution summary."""

    start_time: datetime = Field(..., description="Crawl start timestamp")
    end_time: datetime = Field(..., description="Crawl end timestamp")
    duration: int = Field(..., ge=0, description="Duration in milliseconds")
    status: Literal["completed", "partial", "timeout", "error"] = Field(
        ..., description="Final crawl status"
    )
    pages_visited: int = Field(default=0, ge=0, description="Pages visited count")
    pages_skipped: int = Field(default=0, ge=0, description="Pages skipped count")
    total_links: int = Field(default=0, ge=0, description="Total unique links discovered")
    crawl_depth_reached: int = Field(default=0, ge=0, description="Maximum depth reached")


class PageRecord(BaseModel):
    """Single page visited during crawl."""

    page_id: UUID = Field(..., description="Unique page identifier")
    url: str = Field(..., min_length=1, max_length=2048, description="Full page URL")
    title: str | None = Field(None, max_length=1024, description="HTML title tag content")
    status_code: int = Field(..., ge=100, le=599, description="HTTP response status code")
    content_type: str | None = Field(None, max_length=128, description="MIME content type")
    content_length: int = Field(default=0, ge=0, description="Page body size in bytes")
    response_time: int = Field(default=0, ge=0, description="Response time in milliseconds")
    depth: int = Field(default=0, ge=0, description="Link-following depth")
    parent_page_id: UUID | None = Field(None, description="Parent page ID")
    discovered_at: datetime = Field(..., description="Discovery timestamp")
    cached_content_path: str | None = Field(
        None, max_length=512, description="Cached HTML path"
    )


class NavigationEdge(BaseModel):
    """Navigation graph edge."""

    source_page_id: UUID = Field(..., description="Source page ID")
    target_page_id: UUID = Field(..., description="Target page ID")
    link_text: str | None = Field(None, max_length=512, description="Hyperlink visible text")
    link_url: str | None = Field(None, max_length=2048, description="Raw href value")
    relationship: Literal["navigation", "form", "api", "static", "unknown"] = Field(
        default="navigation", description="Relationship type"
    )


class NavigationGraph(BaseModel):
    """Navigation graph structure."""

    edges: list[NavigationEdge] = Field(default_factory=list, description="Navigation edges")
    root_page_id: UUID | None = Field(None, description="Entry point page ID")


class AssetRecord(BaseModel):
    """External asset reference."""

    url: str = Field(..., min_length=1, max_length=2048, description="Asset URL")
    type: str | None = Field(None, max_length=64, description="MIME type")
    size: int = Field(default=0, ge=0, description="Asset size in bytes")
    external: bool = Field(default=False, description="External domain indicator")
    first_seen_on_page_id: UUID | None = Field(None, description="First discovery page ID")


class AssetsCollection(BaseModel):
    """Grouped assets by type."""

    stylesheets: list[AssetRecord] = Field(default_factory=list, description="CSS files")
    scripts: list[AssetRecord] = Field(default_factory=list, description="JavaScript files")
    images: list[AssetRecord] = Field(default_factory=list, description="Image files")
    fonts: list[AssetRecord] = Field(default_factory=list, description="Font files")


class CookieRecord(BaseModel):
    """Browser cookie."""

    name: str = Field(..., min_length=1, max_length=256, description="Cookie name")
    domain: str = Field(..., min_length=1, max_length=256, description="Cookie domain")
    path: str | None = Field(None, max_length=1024, description="URL path scope")
    http_only: bool = Field(default=False, description="HttpOnly flag")
    secure: bool = Field(default=False, description="Secure flag")
    same_site: Literal["strict", "lax", "none"] | None = Field(None, description="SameSite")
    redacted: bool = Field(default=False, description="Value redacted indicator")


class RedirectRecord(BaseModel):
    """HTTP redirect."""

    from_url: str = Field(..., alias="from", min_length=1, max_length=2048)
    to_url: str = Field(..., alias="to", min_length=1, max_length=2048)
    status_code: Literal[301, 302, 303, 307, 308] = Field(..., description="Redirect status")
    page_id: UUID | None = Field(None, description="Page ID where redirect occurred")


class SessionInfo(BaseModel):
    """Browser session information."""

    authenticated: bool = Field(default=False, description="Authenticated session indicator")
    auth_method: Literal["form", "api", "basic", "oauth", "sso", "none", "unknown"] = Field(
        default="none", description="Authentication method"
    )
    auth_page_id: UUID | None = Field(None, description="Login page ID")
    cookies: list[CookieRecord] = Field(default_factory=list, description="Session cookies")
    redirects: list[RedirectRecord] = Field(default_factory=list, description="Redirects")


class CrawlEvent(BaseModel):
    """Crawl warning or error event."""

    code: str = Field(..., min_length=1, max_length=64, description="Machine-readable code")
    message: str = Field(..., max_length=2000, description="Human-readable message")
    page_id: UUID | None = Field(None, description="Associated page ID")
    url: str | None = Field(None, max_length=2048, description="Associated URL")
    timestamp: datetime = Field(..., description="Event timestamp")


class ResponseTimeStats(BaseModel):
    """Response time statistics."""

    average: int = Field(default=0, ge=0, description="Average response time (ms)")
    median: int = Field(default=0, ge=0, description="Median response time (ms)")
    max: int = Field(default=0, ge=0, description="Maximum response time (ms)")
    min: int = Field(default=0, ge=0, description="Minimum response time (ms)")


class CrawlStatistics(BaseModel):
    """Aggregated crawl statistics."""

    response_time_ms: ResponseTimeStats = Field(
        default_factory=ResponseTimeStats, description="Response time stats"
    )
    pages_by_status_code: dict[str, int] = Field(
        default_factory=dict, description="Pages by status code"
    )
    pages_by_content_type: dict[str, int] = Field(
        default_factory=dict, description="Pages by content type"
    )
    unique_domains: int = Field(default=0, ge=0, description="Unique domains count")
    bytes_downloaded: int = Field(default=0, ge=0, description="Total bytes downloaded")


class FormRecord(BaseModel):
    """Form discovered on a page."""

    page_id: UUID = Field(..., description="Page ID where form was found")
    form_id: str | None = Field(None, max_length=256, description="Form HTML id or name")
    action: str | None = Field(None, max_length=2048, description="Form action URL")
    method: Literal["GET", "POST", "DIALOG"] | None = Field(None, description="HTTP method")
    inputs: list["InputRecord"] = Field(default_factory=list, description="Form input fields")
    buttons: list["ButtonRecord"] = Field(default_factory=list, description="Form buttons")
    label: str | None = Field(None, max_length=512, description="Form visible label")


class InputRecord(BaseModel):
    """Input field discovered on a page."""

    page_id: UUID = Field(..., description="Page ID where input was found")
    input_type: str = Field(..., max_length=64, description="HTML input type")
    name: str | None = Field(None, max_length=256, description="Input name attribute")
    label: str | None = Field(None, max_length=512, description="Visible label text")
    placeholder: str | None = Field(None, max_length=256, description="Placeholder text")
    required: bool = Field(default=False, description="Required field indicator")
    disabled: bool = Field(default=False, description="Disabled field indicator")
    max_length: int | None = Field(None, ge=1, description="Max length constraint")


class ButtonRecord(BaseModel):
    """Button discovered on a page."""

    page_id: UUID = Field(..., description="Page ID where button was found")
    text: str | None = Field(None, max_length=256, description="Button visible text")
    button_type: Literal["submit", "reset", "button", "menu"] | None = Field(None, description="Button type")
    disabled: bool = Field(default=False, description="Disabled indicator")


class CheckboxRecord(BaseModel):
    """Checkbox input discovered on a page."""

    page_id: UUID = Field(..., description="Page ID where checkbox was found")
    name: str | None = Field(None, max_length=256, description="Checkbox name")
    label: str | None = Field(None, max_length=512, description="Associated label")
    checked: bool = Field(default=False, description="Default checked state")
    required: bool = Field(default=False, description="Required indicator")


class RadioRecord(BaseModel):
    """Radio button discovered on a page."""

    page_id: UUID = Field(..., description="Page ID where radio was found")
    name: str | None = Field(None, max_length=256, description="Radio group name")
    label: str | None = Field(None, max_length=512, description="Associated label")
    value: str | None = Field(None, max_length=256, description="Radio value")
    checked: bool = Field(default=False, description="Default checked state")


class DropdownRecord(BaseModel):
    """Dropdown/select discovered on a page."""

    page_id: UUID = Field(..., description="Page ID where dropdown was found")
    name: str | None = Field(None, max_length=256, description="Select name")
    label: str | None = Field(None, max_length=512, description="Associated label")
    options: list[str] = Field(default_factory=list, description="Available options")
    multiple: bool = Field(default=False, description="Multi-select indicator")


class TableRecord(BaseModel):
    """Table discovered on a page."""

    page_id: UUID = Field(..., description="Page ID where table was found")
    table_id: str | None = Field(None, max_length=256, description="Table HTML id")
    caption: str | None = Field(None, max_length=512, description="Table caption")
    headers: list[str] = Field(default_factory=list, description="Column headers")
    row_count: int = Field(default=0, ge=0, description="Number of data rows")
    column_count: int = Field(default=0, ge=0, description="Number of columns")


class DialogRecord(BaseModel):
    """Dialog or modal discovered on a page."""

    page_id: UUID = Field(..., description="Page ID where dialog was found")
    dialog_type: Literal["alert", "confirm", "prompt", "modal", "popup"] = Field(..., description="Dialog type")
    title: str | None = Field(None, max_length=512, description="Dialog title")
    message: str | None = Field(None, max_length=2048, description="Dialog message text")
    trigger_element: str | None = Field(None, max_length=128, description="Trigger element type")


class UploadRecord(BaseModel):
    """File upload field discovered on a page."""

    page_id: UUID = Field(..., description="Page ID where upload was found")
    name: str | None = Field(None, max_length=256, description="Upload field name")
    label: str | None = Field(None, max_length=512, description="Associated label")
    accept: list[str] = Field(default_factory=list, description="Accepted MIME types")
    multiple: bool = Field(default=False, description="Multi-file indicator")
    required: bool = Field(default=False, description="Required indicator")


class DownloadRecord(BaseModel):
    """Download link discovered on a page."""

    page_id: UUID = Field(..., description="Page ID where download was found")
    url: str = Field(..., min_length=1, max_length=2048, description="Download URL")
    text: str | None = Field(None, max_length=512, description="Link text")
    file_extension: str | None = Field(None, max_length=32, description="File extension")
    content_type: str | None = Field(None, max_length=128, description="MIME type")


class AuthRecord(BaseModel):
    """Authentication information discovered during crawl."""

    page_id: UUID | None = Field(None, description="Login page ID")
    auth_type: Literal["form", "api", "basic", "oauth", "sso", "none", "unknown"] = Field(
        default="unknown", description="Authentication type"
    )
    login_url: str | None = Field(None, max_length=2048, description="Login URL")
    logout_url: str | None = Field(None, max_length=2048, description="Logout URL")
    username_field: str | None = Field(None, max_length=128, description="Username field name")
    password_field: str | None = Field(None, max_length=128, description="Password field name")
    requires_authentication: bool = Field(default=False, description="Auth required flag")


class ApiCallRecord(BaseModel):
    """API call discovered during crawl."""

    page_id: UUID | None = Field(None, description="Page ID where call was found")
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = Field(..., description="HTTP method")
    endpoint: str = Field(..., max_length=2048, description="API endpoint URL")
    request_body_type: str | None = Field(None, max_length=64, description="Content type")
    description: str | None = Field(None, max_length=512, description="Call description")


class UserFlowRecord(BaseModel):
    """User flow discovered during crawl."""

    flow_id: UUID = Field(..., description="Unique flow identifier")
    name: str | None = Field(None, max_length=256, description="Flow name")
    description: str | None = Field(None, max_length=1024, description="Flow description")
    steps: list[dict] = Field(default_factory=list, description="Flow steps")
    start_url: str | None = Field(None, max_length=2048, description="Starting URL")


class ScreenshotRecord(BaseModel):
    """Screenshot captured during crawl."""

    page_id: UUID = Field(..., description="Associated page ID")
    url: str = Field(..., max_length=2048, description="URL at capture time")
    path: str = Field(..., max_length=512, description="Screenshot file path")
    captured_at: datetime = Field(..., description="Capture timestamp")
    width: int = Field(default=0, ge=0, description="Viewport width")
    height: int = Field(default=0, ge=0, description="Viewport height")


class CrawlPackage(BaseModel):
    """
    Complete crawl package output.
    
    Canonical contract following crawl-package.json schema.
    """

    run_id: UUID = Field(..., description="Test run identifier")
    request_id: UUID = Field(..., description="Request correlation ID")
    application_id: UUID | None = Field(None, description="Application identifier")
    
    crawl_summary: CrawlSummary = Field(..., description="Crawl summary")
    visited_pages: list[PageRecord] = Field(default_factory=list, description="Visited pages")
    navigation_graph: NavigationGraph = Field(
        default_factory=NavigationGraph, description="Navigation graph"
    )
    
    assets: AssetsCollection | None = Field(None, description="Discovered assets")
    session: SessionInfo | None = Field(None, description="Session information")

    forms: list[FormRecord] = Field(default_factory=list, description="Discovered forms")
    inputs: list[InputRecord] = Field(default_factory=list, description="Discovered inputs")
    buttons: list[ButtonRecord] = Field(default_factory=list, description="Discovered buttons")
    checkboxes: list[CheckboxRecord] = Field(default_factory=list, description="Discovered checkboxes")
    radios: list[RadioRecord] = Field(default_factory=list, description="Discovered radio buttons")
    dropdowns: list[DropdownRecord] = Field(default_factory=list, description="Discovered dropdowns")
    tables: list[TableRecord] = Field(default_factory=list, description="Discovered tables")
    dialogs: list[DialogRecord] = Field(default_factory=list, description="Discovered dialogs")
    uploads: list[UploadRecord] = Field(default_factory=list, description="Discovered uploads")
    downloads: list[DownloadRecord] = Field(default_factory=list, description="Discovered downloads")
    authentication: list[AuthRecord] = Field(default_factory=list, description="Discovered auth")
    api_calls: list[ApiCallRecord] = Field(default_factory=list, description="Discovered API calls")
    user_flows: list[UserFlowRecord] = Field(default_factory=list, description="Discovered user flows")
    screenshots: list[ScreenshotRecord] = Field(default_factory=list, description="Captured screenshots")

    warnings: list[CrawlEvent] = Field(default_factory=list, description="Non-fatal warnings")
    errors: list[CrawlEvent] = Field(default_factory=list, description="Fatal errors")
    
    statistics: CrawlStatistics | None = Field(None, description="Aggregated statistics")

    class Config:
        populate_by_name = True


class CrawlRequest(BaseModel):
    """Internal crawler request."""

    run_id: UUID = Field(..., description="Run identifier")
    request_id: UUID = Field(..., description="Request correlation ID")
    workspace_path: str = Field(..., description="Workspace directory")
    target_url: str = Field(..., description="Target application URL")
    max_depth: int = Field(default=3, ge=1, le=10, description="Maximum crawl depth")
    max_pages: int = Field(default=50, ge=1, le=1000, description="Maximum pages to crawl")
    timeout: int = Field(default=30000, ge=1000, description="Navigation timeout (ms)")
    max_retries: int = Field(default=2, ge=0, le=5, description="Maximum retries per page")
    browser: Literal["chromium", "firefox", "webkit"] = Field(
        default="chromium", description="Browser engine"
    )
    headless: bool = Field(default=True, description="Headless mode")
    screenshot: bool = Field(default=True, description="Capture screenshots")
