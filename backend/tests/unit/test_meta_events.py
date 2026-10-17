from __future__ import annotations

import datetime as dt
import json
import pickle
from pathlib import Path

from app.meta.events import (
    IgnoredEvent,
    LeadgenEvent,
    MessageEvent,
    ReferralEvent,
    WebhookPayload,
    parse_payload,
)
from app.meta.leadgen import keep_needed_fields, mock_field_data

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "meta" / "sample_payload.json"


def _events() -> list[object]:
    return list(parse_payload(json.loads(FIXTURE.read_text("utf-8"))))


def test_parses_every_kind_in_order() -> None:
    kinds = [type(e).__name__ for e in _events()]
    assert kinds == [
        "MessageEvent",
        "MessageEvent",
        "MessageEvent",
        "ReferralEvent",
        "IgnoredEvent",
        "IgnoredEvent",
        "LeadgenEvent",
        "IgnoredEvent",
    ]


def test_inbound_message() -> None:
    ev = _events()[0]
    assert isinstance(ev, MessageEvent)
    assert ev.kind == "in"
    assert ev.psid == "7000000000000001"
    assert ev.fb_page_id == "100000000000001"
    assert ev.mid == "m_fake_in_1"
    assert ev.sent_at == dt.datetime.fromtimestamp(1791000000, tz=dt.UTC)
    assert ev.dedupe_key == "mid:m_fake_in_1"


def test_echo_takes_psid_from_recipient_and_keeps_app_id() -> None:
    ev = _events()[1]
    assert isinstance(ev, MessageEvent)
    assert ev.kind == "echo"
    assert ev.psid == "7000000000000001"
    assert ev.app_id == "123456789"
    assert ev.metadata == "auto"


def test_attachment_only_message_with_ad_referral() -> None:
    ev = _events()[2]
    assert isinstance(ev, MessageEvent)
    assert ev.text is None
    assert ev.has_attachments
    assert ev.referral is not None
    assert ev.referral["ad_id"] == "23800000000000001"


def test_messaging_referral() -> None:
    ev = _events()[3]
    assert isinstance(ev, ReferralEvent)
    assert ev.psid == "7000000000000003"
    assert ev.referral["ad_id"] == "23800000000000002"
    assert ev.dedupe_key == "ref:7000000000000003:1791000500000"


def test_delivery_read_and_feed_are_ignored() -> None:
    ignored = [e for e in _events() if isinstance(e, IgnoredEvent)]
    assert [e.kind for e in ignored] == ["delivery", "read", "feed"]


def test_leadgen() -> None:
    ev = _events()[6]
    assert isinstance(ev, LeadgenEvent)
    assert ev.leadgen_id == "444000000000001"
    assert ev.form_id == "900000000000001"
    assert ev.fb_ad_id == "23800000000000003"
    assert ev.created_time == dt.datetime.fromtimestamp(1791000800, tz=dt.UTC)


def test_non_page_object_and_garbage_are_skipped() -> None:
    assert parse_payload({"object": "instagram", "entry": [{"id": "1"}]}) == []
    assert parse_payload({"object": "page", "entry": ["x", {"messaging": []}]}) == []
    garbage = {"object": "page", "entry": [{"id": "1", "messaging": [{"message": {}}]}]}
    assert parse_payload(garbage) == [IgnoredEvent("1", "unknown_messaging")]


def test_payload_repr_hides_content_and_survives_pickle() -> None:
    payload = WebhookPayload(json.loads(FIXTURE.read_text("utf-8")))
    assert "Khách" not in repr(payload)
    assert repr(payload) == "<WebhookPayload entries=1>"
    assert pickle.loads(pickle.dumps(payload)) == payload  # noqa: S301 — dữ liệu tự tạo


def test_leadgen_keeps_only_needed_fields() -> None:
    kept = keep_needed_fields(
        [
            {"name": "full_name", "values": ["[Khách 1]"]},
            {"name": "phone_number", "values": ["0900000001"]},
            {"name": "city", "values": ["[Tỉnh]"]},
            {"name": "email", "values": []},
        ]
    )
    assert kept == {"full_name": "[Khách 1]", "phone_number": "0900000001"}
    assert mock_field_data("900000000000001") == {
        "full_name": "[Khách 1042]",
        "phone_number": "+84900000142",
    }
    assert mock_field_data("không-có") is None
