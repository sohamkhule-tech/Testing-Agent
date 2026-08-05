"""
Discovery Domain ORM Models

crawl_packages, inventories
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, SmallInteger, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as SA_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database import Base, TimestampMixin, UUIDMixin
from app.models.enums import CrawlStatusType


# ===================================================================
# CrawlPackage
# ===================================================================


class CrawlPackage(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "crawl_packages"

    run_id: Mapped[UUID] = mapped_column(
        SA_UUID(as_uuid=True), ForeignKey("runs.run_id"), nullable=False
    )
    status: Mapped[str] = mapped_column(CrawlStatusType(32), nullable=False)
    pages_visited: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pages_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_links: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    crawl_depth_reached: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    bytes_downloaded: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    authenticated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auth_method: Mapped[str | None] = mapped_column(nullable=True)
    har_path: Mapped[str | None] = mapped_column(nullable=True)
    file_path: Mapped[str] = mapped_column(nullable=False)

    run: Mapped[Run] = relationship("Run", back_populates="crawl_packages")

    __table_args__ = (
        Index("idx_crawl_packages_run_id", "run_id", unique=True),
    )


# ===================================================================
# Inventory
# ===================================================================


class Inventory(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "inventories"

    run_id: Mapped[UUID] = mapped_column(
        SA_UUID(as_uuid=True), ForeignKey("runs.run_id"), nullable=False
    )
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    form_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    link_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    button_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    table_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    api_call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    user_flow_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    screenshot_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_pages_removed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_links_removed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    authenticated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auth_method: Mapped[str | None] = mapped_column(nullable=True)
    pages_data: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    elements_data: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    navigation_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    statistics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    errors: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    file_path: Mapped[str] = mapped_column(nullable=False)

    run: Mapped[Run] = relationship("Run", back_populates="inventories")

    __table_args__ = (
        Index("idx_inventories_run_id", "run_id", unique=True),
    )
