from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.auth import PublicConfig

router = APIRouter(prefix="/api", tags=["public"])


@router.get("/config", response_model=PublicConfig)
async def public_config() -> PublicConfig:
    """Thông tin giao diện cần trước khi đăng nhập (ví dụ hiện nhãn "Dữ liệu mẫu")."""
    s = get_settings()
    return PublicConfig(mock_mode=s.mock_mode, app_env=s.app_env)
