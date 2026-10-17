"""Bài đăng và số liệu theo ngày của Trang (Bước 7)."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    BigInteger,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, updated_at_col, uuid_pk, workspace_fk

EXCERPT_MAX = 200


class PagePost(Base):
    """`type`: photo | video | reel | link | status. `views` NULL khi Meta không trả."""

    __tablename__ = "page_posts"
    __table_args__ = (
        UniqueConstraint("workspace_id", "fb_post_id"),
        ForeignKeyConstraint(
            ["workspace_id", "page_id"],
            ["pages.workspace_id", "pages.id"],
            ondelete="CASCADE",
            name="fk_page_posts_page",
        ),
        Index("ix_page_posts_page_created", "page_id", "created_time"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    page_id: Mapped[uuid.UUID]
    fb_post_id: Mapped[str] = mapped_column(String(80))
    created_time: Mapped[dt.datetime]
    type: Mapped[str] = mapped_column(String(16))
    excerpt: Mapped[str | None] = mapped_column(String(EXCERPT_MAX))
    permalink: Mapped[str | None] = mapped_column(String(500))
    reactions: Mapped[int] = mapped_column(Integer, server_default="0")
    comments: Mapped[int] = mapped_column(Integer, server_default="0")
    shares: Mapped[int] = mapped_column(Integer, server_default="0")
    views: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[dt.datetime] = created_at_col()
    updated_at: Mapped[dt.datetime] = updated_at_col()


class PageInsightDaily(Base):
    __tablename__ = "page_insights_daily"
    __table_args__ = (
        UniqueConstraint("workspace_id", "page_id", "date"),
        ForeignKeyConstraint(
            ["workspace_id", "page_id"],
            ["pages.workspace_id", "pages.id"],
            ondelete="CASCADE",
            name="fk_page_insights_daily_page",
        ),
        Index("ix_page_insights_daily_page_date", "page_id", "date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT")
    )
    page_id: Mapped[uuid.UUID]
    date: Mapped[dt.date] = mapped_column(Date)
    followers: Mapped[int | None] = mapped_column(Integer)
    new_follows: Mapped[int | None] = mapped_column(Integer)
    views: Mapped[int | None] = mapped_column(Integer)
    reach: Mapped[int | None] = mapped_column(Integer)
    engagements: Mapped[int | None] = mapped_column(Integer)
    video_views: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[dt.datetime] = updated_at_col()
