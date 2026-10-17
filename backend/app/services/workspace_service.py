"""Tạo workspace (chỉ chạy bằng tài khoản quản trị: CLI, seed)."""

from __future__ import annotations

import datetime as dt
import re
import unicodedata

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import ScoreFormula, Workspace, WorkspaceSettings


def slugify(text: str) -> str:
    """`Phần Mềm Giá Rẻ` → `phan-mem-gia-re`."""
    text = text.replace("đ", "d").replace("Đ", "D")
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug[:100] or "workspace"


async def create_workspace(db: AsyncSession, name: str, slug: str | None = None) -> Workspace:
    s = get_settings()
    ws = Workspace(name=name, slug=slug or slugify(name), timezone=s.app_timezone)
    db.add(ws)
    await db.flush()
    db.add(
        WorkspaceSettings(
            workspace_id=ws.id,
            work_start=s.work_hours_start,
            work_end=s.work_hours_end,
            slow_reply_minutes=s.slow_reply_minutes,
            result_deadline_hours=s.result_deadline_hours,
            lead_session_gap_days=s.lead_session_gap_days,
            posts_per_week_target=s.posts_per_week_target,
            min_leads_for_ranking=s.min_leads_for_ranking,
        )
    )
    # Công thức điểm mặc định (CLAUDE.md mục 3), phiên bản 1.
    db.add(
        ScoreFormula(
            workspace_id=ws.id,
            version=1,
            min_leads=s.min_leads_for_ranking,
            posts_per_week_target=s.posts_per_week_target,
            effective_from=dt.datetime.now(dt.UTC),
        )
    )
    await db.flush()
    return ws
