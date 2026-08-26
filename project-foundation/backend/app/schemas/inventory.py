from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.crawler import (
    ApiCallRecord,
    AuthRecord,
    ButtonRecord,
    CheckboxRecord,
    CrawlStatistics,
    DialogRecord,
    DownloadRecord,
    DropdownRecord,
    FormRecord,
    InputRecord,
    NavigationEdge,
    PageRecord,
    RadioRecord,
    ScreenshotRecord,
    TableRecord,
    UploadRecord,
    UserFlowRecord,
)


class InventoryMetadata(BaseModel):
    """Inventory metadata."""

    run_id: UUID = Field(..., description="Test run identifier")
    request_id: UUID = Field(..., description="Request correlation ID")
    application_id: UUID | None = Field(None, description="Application identifier")
    generated_at: datetime = Field(..., description="Inventory generation timestamp")
    source_files: list[str] = Field(default_factory=list, description="Source file paths")
    page_count: int = Field(default=0, ge=0, description="Total aggregated pages")
    form_count: int = Field(default=0, ge=0, description="Total aggregated forms")
    link_count: int = Field(default=0, ge=0, description="Total aggregated links")
    button_count: int = Field(default=0, ge=0, description="Total aggregated buttons")
    input_count: int = Field(default=0, ge=0, description="Total aggregated inputs")
    table_count: int = Field(default=0, ge=0, description="Total aggregated tables")
    api_call_count: int = Field(default=0, ge=0, description="Total aggregated API calls")
    user_flow_count: int = Field(default=0, ge=0, description="Total aggregated user flows")
    screenshot_count: int = Field(default=0, ge=0, description="Total aggregated screenshots")
    duplicate_pages_removed: int = Field(default=0, ge=0, description="Duplicate pages removed")
    duplicate_links_removed: int = Field(default=0, ge=0, description="Duplicate links removed")
    excluded_modules: list[str] = Field(default_factory=list, description="Modules excluded per user prompt")
    excluded_page_count: int = Field(default=0, ge=0, description="Pages excluded from testing scope")
    errors: list[str] = Field(default_factory=list, description="Aggregation errors")


class InventoryNavigation(BaseModel):
    """Aggregated navigation structure."""

    edges: list[NavigationEdge] = Field(default_factory=list, description="Navigation edges")
    root_page_id: UUID | None = Field(None, description="Entry point page ID")
    total_edges: int = Field(default=0, ge=0, description="Total unique edges")


class InventoryStatistics(BaseModel):
    """Aggregated inventory statistics."""

    total_pages: int = Field(default=0, ge=0, description="Total unique pages")
    total_forms: int = Field(default=0, ge=0, description="Total forms")
    total_buttons: int = Field(default=0, ge=0, description="Total buttons")
    total_inputs: int = Field(default=0, ge=0, description="Total input fields")
    total_links: int = Field(default=0, ge=0, description="Total unique links")
    total_tables: int = Field(default=0, ge=0, description="Total tables")
    total_dialogs: int = Field(default=0, ge=0, description="Total dialogs")
    total_uploads: int = Field(default=0, ge=0, description="Total upload fields")
    total_downloads: int = Field(default=0, ge=0, description="Total download links")
    total_api_calls: int = Field(default=0, ge=0, description="Total API calls")
    total_user_flows: int = Field(default=0, ge=0, description="Total user flows")
    total_screenshots: int = Field(default=0, ge=0, description="Total screenshots")
    average_response_time_ms: float = Field(default=0, ge=0, description="Average response time")
    max_depth_reached: int = Field(default=0, ge=0, description="Maximum crawl depth")
    authenticated: bool = Field(default=False, description="Authenticated session")
    auth_method: str = Field(default="none", description="Authentication method")


class Inventory(BaseModel):
    """Canonical inventory output - single source of truth for downstream agents."""

    metadata: InventoryMetadata = Field(..., description="Inventory metadata")

    pages: list[PageRecord] = Field(default_factory=list, description="Aggregated pages")
    navigation: InventoryNavigation = Field(
        default_factory=InventoryNavigation, description="Navigation structure"
    )
    forms: list[FormRecord] = Field(default_factory=list, description="Aggregated forms")
    inputs: list[InputRecord] = Field(default_factory=list, description="Aggregated inputs")
    dropdowns: list[DropdownRecord] = Field(default_factory=list, description="Aggregated dropdowns")
    checkboxes: list[CheckboxRecord] = Field(default_factory=list, description="Aggregated checkboxes")
    radio_buttons: list[RadioRecord] = Field(default_factory=list, description="Aggregated radio buttons")
    buttons: list[ButtonRecord] = Field(default_factory=list, description="Aggregated buttons")
    links: list[tuple[str, str, str]] = Field(default_factory=list, description="Aggregated links (url, text, source_page_url)")
    tables: list[TableRecord] = Field(default_factory=list, description="Aggregated tables")
    dialogs: list[DialogRecord] = Field(default_factory=list, description="Aggregated dialogs")
    uploads: list[UploadRecord] = Field(default_factory=list, description="Aggregated uploads")
    downloads: list[DownloadRecord] = Field(default_factory=list, description="Aggregated downloads")
    authentication: list[AuthRecord] = Field(default_factory=list, description="Aggregated auth")
    api_calls: list[ApiCallRecord] = Field(default_factory=list, description="Aggregated API calls")
    user_flows: list[UserFlowRecord] = Field(default_factory=list, description="Aggregated user flows")
    screenshots: list[ScreenshotRecord] = Field(default_factory=list, description="Aggregated screenshots")
    statistics: InventoryStatistics = Field(
        default_factory=InventoryStatistics, description="Inventory statistics"
    )

    model_config = {"frozen": False}
