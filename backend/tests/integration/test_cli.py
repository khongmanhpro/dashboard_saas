from __future__ import annotations

import io
import json

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import cli
from app.core.config import get_settings
from app.core.security import verify_password
from app.models import MemberRole, User, WorkspaceMember

pytestmark = pytest.mark.integration

OWNER_PASSWORD = "Chu-so-huu-2026"


@pytest.fixture
def bootstrap_env(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings().model_copy(
        update={
            "bootstrap_workspace_name": "Công ty Thử Nghiệm",
            "bootstrap_owner_email": "Owner@Example.com",
            "bootstrap_owner_password": __import__("pydantic").SecretStr(OWNER_PASSWORD),
        }
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)


@pytest.mark.usefixtures("bootstrap_env")
async def test_bootstrap_owner_is_idempotent(
    admin_db: AsyncSession, capsys: pytest.CaptureFixture[str]
) -> None:
    first = await cli.bootstrap_owner()
    second = await cli.bootstrap_owner()
    assert "Đã tạo" in first and "đã tồn tại" in second

    user = await admin_db.scalar(select(User).where(User.email == "owner@example.com"))
    assert user is not None
    assert user.must_change_password
    assert verify_password(user.password_hash, OWNER_PASSWORD)
    owners = await admin_db.scalar(
        select(func.count()).where(WorkspaceMember.role == MemberRole.OWNER)
    )
    assert owners == 1
    out = capsys.readouterr()
    assert OWNER_PASSWORD not in out.out + out.err + first + second


async def test_bootstrap_requires_all_values() -> None:
    with pytest.raises(cli.CliError, match="BOOTSTRAP_"):
        await cli.bootstrap_owner()


async def test_bootstrap_rejects_weak_password(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings().model_copy(
        update={
            "bootstrap_workspace_name": "Công ty",
            "bootstrap_owner_email": "owner@example.com",
            "bootstrap_owner_password": __import__("pydantic").SecretStr("123"),
        }
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    with pytest.raises(cli.CliError, match="password_too_short"):
        await cli.bootstrap_owner()


async def test_e2e_seed_refuses_production(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings().model_copy(update={"app_env": "production"})
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    with pytest.raises(cli.CliError, match="development/test"):
        await cli.e2e_seed({"workspace": "x", "accounts": []})


async def test_e2e_seed_refuses_dev_database(
    monkeypatch: pytest.MonkeyPatch, admin_db: AsyncSession
) -> None:
    """Mục L: chạy nhầm `migrate python -m app.cli e2e-seed` (DB dev) bị chặn, không tạo gì."""
    monkeypatch.setattr(get_settings(), "postgres_db", "fanpage")
    with pytest.raises(cli.CliError, match="DB test"):
        await cli.e2e_seed({"workspace": "E2E", "accounts": []})
    assert await admin_db.scalar(select(func.count()).select_from(User)) == 0


async def test_e2e_seed_creates_and_resets_accounts(admin_db: AsyncSession) -> None:
    payload = {
        "workspace": "E2E",
        "accounts": [
            {
                "email": "e2e-staff@example.com",
                "full_name": "[Nhân viên 1]",
                "role": "staff",
                "password": "E2e-mat-khau-1",
            },
        ],
    }
    await cli.e2e_seed(payload)
    payload["accounts"][0]["password"] = "E2e-mat-khau-2"
    await cli.e2e_seed(payload)
    user = await admin_db.scalar(select(User).where(User.email == "e2e-staff@example.com"))
    assert user is not None and verify_password(user.password_hash, "E2e-mat-khau-2")


def test_cli_main_reports_errors_without_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def boom() -> str:
        raise cli.CliError("thiếu cấu hình")

    monkeypatch.setattr(cli, "bootstrap_owner", boom)
    assert cli.main(["bootstrap-owner"]) == 1
    assert "Lỗi: thiếu cấu hình" in capsys.readouterr().err


def test_cli_main_e2e_reads_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    async def fake(payload: dict[str, object]) -> str:
        seen.update(payload)
        return "ok"

    monkeypatch.setattr(cli, "e2e_seed", fake)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"workspace": "W", "accounts": []})))
    assert cli.main(["e2e-seed"]) == 0
    assert seen["workspace"] == "W"


async def test_e2e_seed_creates_fresh_leads_each_run(admin_db: AsyncSession) -> None:
    import json

    from sqlalchemy import func, select

    from app.models import Lead

    def payload(run: str) -> dict[str, object]:
        return {
            "workspace": "E2E Leads",
            "accounts": [
                {
                    "email": "e2e-s@example.com",
                    "full_name": "[NV]",
                    "role": "staff",
                    "password": "Mat-khau-dai-123",
                },
            ],
            "leads": [
                {
                    "key": "flow",
                    "owner": "e2e-s@example.com",
                    "fb_page_id": "100000000000991",
                    "page": "[Trang E2E]",
                    "psid": f"e2e-{run}",
                    "name": f"[Khách E2E {run}]",
                    "text": "số em 0900 000 999",
                },
            ],
        }

    first = json.loads(await cli.e2e_seed(payload("a")))
    second = json.loads(await cli.e2e_seed(payload("b")))
    assert first["leads"]["flow"] != second["leads"]["flow"]
    lead = await admin_db.get(Lead, first["leads"]["flow"])
    assert lead is not None
    assert lead.owner_member_id is not None
    assert lead.phone == "0900000999"
    assert await admin_db.scalar(select(func.count()).select_from(Lead)) == 2
