"""Giả lập webhook Meta cho 4 Trang demo và kiểm tra số phút trả lời (MOCK_MODE).

    make simulate        # = docker compose run --rm migrate python -m app.mock.simulate

Đọc kịch bản trong `tests/fixtures/meta/simulate_scenarios.json`, ký từng payload bằng
`META_APP_SECRET`, POST vào `/webhooks/meta` của backend đang chạy, chờ worker xử lý xong rồi
đọc DB để so với kết quả mong đợi. Mỗi lần chạy dùng PSID và mid mới.

Cần `make seed` trước. Chỉ chạy khi MOCK_MODE=true và không phải production/staging.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import re
import secrets
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from arq.jobs import Job
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.webhooks import job_id_for
from app.core.config import get_settings
from app.core.db import admin_sessionmaker, dispose_engines
from app.core.queue import close_queue, get_queue
from app.meta.signature import SIGNATURE_HEADER, sign
from app.mock import payloads as p
from app.mock.seed import DemoWorkspace, load_demo_workspace
from app.models import (
    Campaign,
    Contact,
    Lead,
    LeadgenSubmission,
    Message,
    Page,
    WorkspaceMember,
)
from app.services.assignment import assign_page
from app.services.phone import mask_phone
from app.workers.meta_sync import sync_meta

SCENARIOS_FILE = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "meta" / "simulate_scenarios.json"
)
DEFAULT_URL = "http://backend:8000/webhooks/meta"
BASE_DAYS_AGO = 40
JOB_TIMEOUT_SECONDS = 30

_RELATIVE = re.compile(r"^(\d+) (\d{1,2}):(\d{2})(?::(\d{2}))?$")
_NOW = re.compile(r"^now-(\d+)s$")

# post(body, signature) -> mã HTTP; wait(job_id) chờ worker xử lý xong job.
PostFn = Callable[[bytes, str], Awaitable[int]]
WaitFn = Callable[[str], Awaitable[None]]


class SimulationError(Exception):
    pass


@dataclass
class Check:
    scenario: str
    expected: str
    actual: str
    ok: bool


@dataclass
class Simulator:
    demo: DemoWorkspace
    sessions: async_sessionmaker[AsyncSession]
    post: PostFn
    wait: WaitFn
    secret: str
    now: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.UTC))
    run_id: str = field(default_factory=lambda: secrets.token_hex(3))
    _seq: int = 0

    # ------------------------------------------------------------ thời gian và ID

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.demo.workspace.timezone)

    def at(self, spec: str) -> dt.datetime:
        if m := _NOW.match(spec):
            return self.now - dt.timedelta(seconds=int(m.group(1)))
        m = _RELATIVE.match(spec)
        if m is None:
            raise SimulationError(f"thời điểm không hợp lệ: {spec}")
        base = self.now.astimezone(self.tz).date() - dt.timedelta(days=BASE_DAYS_AGO)
        day = base + dt.timedelta(days=int(m.group(1)))
        clock = dt.time(int(m.group(2)), int(m.group(3)), int(m.group(4) or 0))
        return dt.datetime.combine(day, clock, tzinfo=self.tz)

    def next_id(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}{self.run_id}{self._seq:04d}"

    def psid(self, scenario: str, customer: str) -> str:
        return f"sim{self.run_id}-{scenario}-{customer}"

    # ------------------------------------------------------------ gửi

    async def deliver(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        status = await self.post(body, sign(body, self.secret))
        if status != 200:
            raise SimulationError(f"webhook trả {status}")
        await self.wait(job_id_for(body))

    async def run_scenario(self, sc: dict[str, Any]) -> dict[str, str]:
        """Chạy các bước. Trả về nhãn khách → PSID (hoặc leadgen_id với form)."""
        page = self.demo.pages[sc["page"]]
        fb = page.fb_page_id
        refs: dict[str, str] = {}
        last: dict[str, Any] | None = None
        resend = 0
        for step in sc["steps"]:
            if "assign" in step:
                await self._assign(page, self.demo.members[step["assign"]], self.at(step["at"]))
                continue
            kind = step["send"]
            if kind == "resend":
                if last is None:
                    raise SimulationError("resend phải đứng sau một bước gửi")
                # Body khác (time khác) nhưng cùng mid: chỉ worker chặn được, không phải hàng đợi.
                resend += 1
                again = json.loads(json.dumps(last))
                again["entry"][0]["time"] += resend
                await self.deliver(again)
                continue
            at = self.at(step["at"])
            customer = step["customer"]
            if kind == "leadgen":
                leadgen_id = refs.setdefault(customer, self.next_id("sim"))
                change = p.leadgen(fb, leadgen_id, step["form_id"], at, ad_id=step.get("ad_id"))
                last = p.page_payload(fb, changes=[change], at=self.now)
            else:
                psid = refs.setdefault(customer, self.psid(sc["key"], customer))
                if kind == "in":
                    item = p.inbound(fb, psid, self.next_id("m_sim_"), at, ad_id=step.get("ad_id"))
                elif kind == "echo":
                    item = p.echo(fb, psid, self.next_id("m_sim_"), at, app_id=step.get("app_id"))
                elif kind == "referral":
                    item = p.referral(fb, psid, at, step["ad_id"])
                else:
                    raise SimulationError(f"bước không hỗ trợ: {kind}")
                last = p.page_payload(fb, messaging=[item], at=self.now)
            await self.deliver(last)
        return refs

    async def _assign(self, page: Page, member: WorkspaceMember, at: dt.datetime) -> None:
        async with self.sessions() as db:
            fresh_page = await db.get(Page, page.id)
            fresh_member = await db.get(WorkspaceMember, member.id)
            assert fresh_page is not None and fresh_member is not None  # noqa: S101
            await assign_page(db, fresh_page, fresh_member, at, reason="[Giả lập]")
            await db.commit()

    # ------------------------------------------------------------ kiểm tra

    def _member_key(self, member_id: Any) -> str | None:
        for key, member in self.demo.members.items():
            if member.id == member_id:
                return key
        return None

    async def evaluate(self, sc: dict[str, Any], refs: dict[str, str]) -> list[Check]:
        page = self.demo.pages[sc["page"]]
        checks = []
        async with self.sessions() as db:
            for exp in sc["expect"]:
                ref = refs.get(exp["customer"], "")
                actual = await self._observe(db, page, ref, exp)
                expected = {k: v for k, v in exp.items() if k != "customer"}
                ok = all(actual.get(k) == v for k, v in expected.items())
                label = sc["title"] + (f" [{exp['customer']}]" if len(sc["expect"]) > 1 else "")
                checks.append(
                    Check(
                        label,
                        _describe(expected),
                        _describe({k: actual.get(k) for k in expected}),
                        ok,
                    )
                )
        return checks

    async def _observe(
        self, db: AsyncSession, page: Page, ref: str, exp: dict[str, Any]
    ) -> dict[str, Any]:
        if exp.get("source") == "leadgen":
            lead = await db.scalar(
                select(Lead)
                .join(LeadgenSubmission, LeadgenSubmission.lead_id == Lead.id)
                .where(LeadgenSubmission.leadgen_id == ref)
            )
            leads = [lead] if lead else []
            message_count = 0
        else:
            contact = await db.scalar(
                select(Contact).where(Contact.page_id == page.id, Contact.psid == ref)
            )
            if contact is None:
                return {}
            leads = list(
                await db.scalars(
                    select(Lead).where(Lead.contact_id == contact.id).order_by(Lead.episode_no)
                )
            )
            message_count = int(
                await db.scalar(
                    select(func.count())
                    .select_from(Message)
                    .where(Message.contact_id == contact.id)
                )
                or 0
            )
        if not leads:
            return {"episodes": 0}
        lead = leads[-1]
        seconds = lead.response_business_seconds
        return {
            "minutes": None if seconds is None else round(seconds / 60, 2),
            "owner": self._member_key(lead.owner_member_id),
            "status": lead.status.value,
            "episodes": len(leads),
            "messages": message_count,
            "source": lead.source.value,
            "phone": lead.phone,
            "fb_ad_id": lead.fb_ad_id,
            "campaign": await db.scalar(
                select(Campaign.name).where(Campaign.id == lead.campaign_id)
            )
            if lead.campaign_id
            else None,
        }

    async def run_all(self, scenarios: list[dict[str, Any]]) -> list[Check]:
        checks: list[Check] = []
        for sc in scenarios:
            try:
                refs = await self.run_scenario(sc)
            except Exception as exc:
                checks.append(Check(sc["title"], "chạy được", f"lỗi: {exc}", False))
                continue
            checks.extend(await self.evaluate(sc, refs))
        return checks


def _describe(values: dict[str, Any]) -> str:
    parts = []
    for key, value in values.items():
        if key == "minutes":
            parts.append("chưa trả lời" if value is None else f"{value:g} phút")
        elif key == "owner":
            parts.append(f"phụ trách: {value or 'chưa có'}")
        elif key == "phone":
            parts.append(f"SĐT {mask_phone(value) if value else '—'}")
        elif key == "episodes":
            parts.append(f"{value} đợt")
        elif key == "messages":
            parts.append(f"{value} tin")
        elif key == "campaign":
            parts.append(f"chiến dịch {value or '—'}")
        else:
            parts.append(f"{value}")
    return ", ".join(parts)


def load_scenarios(keys: list[str] | None = None) -> list[dict[str, Any]]:
    data = json.loads(SCENARIOS_FILE.read_text("utf-8"))
    scenarios: list[dict[str, Any]] = data["scenarios"]
    if keys:
        scenarios = [sc for sc in scenarios if sc["key"] in keys]
    return scenarios


def print_report(checks: list[Check]) -> None:
    width = max(len(c.scenario) for c in checks)
    for c in checks:
        mark = "OK  " if c.ok else "FAIL"
        print(f"{mark}  {c.scenario:<{width}}  mong đợi: {c.expected}")
        if not c.ok:
            print(f"      {'':<{width}}  thực tế:  {c.actual}")
    passed = sum(c.ok for c in checks)
    print(f"\n{passed}/{len(checks)} tình huống đúng.")


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Giả lập webhook Meta cho 4 Trang demo")
    parser.add_argument("--url", default=os.environ.get("SIMULATE_URL", DEFAULT_URL))
    parser.add_argument("--only", nargs="*", help="chỉ chạy các kịch bản có key này")
    args = parser.parse_args(argv)

    s = get_settings()
    if not s.mock_mode or s.is_production_like:
        print("Chỉ chạy giả lập khi MOCK_MODE=true và không phải production/staging.")
        return 2
    secret = s.meta_app_secret.get_secret_value()
    if not secret:
        print(
            "META_APP_SECRET trống. Đặt một chuỗi ngẫu nhiên trong .env rồi khởi động lại backend."
        )
        return 2

    sessions = admin_sessionmaker()
    async with sessions() as db:
        demo = await load_demo_workspace(db)
    if demo is None:
        print("Chưa có dữ liệu demo. Chạy `make seed` trước.")
        return 2
    # Quảng cáo phải có trong DB thì khách từ QC mới gắn được chiến dịch (client Graph giả).
    await sync_meta({})

    queue = await get_queue()

    async def wait(job_id: str) -> None:
        await Job(job_id, queue).result(timeout=JOB_TIMEOUT_SECONDS, poll_delay=0.2)

    async with httpx.AsyncClient(timeout=10) as http:

        async def post(body: bytes, signature: str) -> int:
            resp = await http.post(
                args.url,
                content=body,
                headers={"Content-Type": "application/json", SIGNATURE_HEADER: signature},
            )
            return resp.status_code

        sim = Simulator(demo, sessions, post, wait, secret)
        print(f"Giả lập lần chạy {sim.run_id}, gửi tới {args.url}\n")
        checks = await sim.run_all(load_scenarios(args.only))

    await close_queue()
    await dispose_engines()
    print_report(checks)
    return 0 if checks and all(c.ok for c in checks) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
