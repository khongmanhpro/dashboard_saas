from __future__ import annotations

import io
import json
import logging

import pytest

from app.core.logging import RedactingJsonFormatter, redact


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("khách để lại 0912345218 nhé", "khách để lại 09•• ••• 218 nhé"),
        ("sđt +84912345218", "sđt 09•• ••• 218"),
        ("sđt 84 912 345 218.", "sđt 09•• ••• 218."),
        ("gọi 0912.345.218", "gọi 09•• ••• 218"),
    ],
)
def test_masks_vietnamese_phone_numbers(raw: str, expected: str) -> None:
    assert redact(raw) == expected


def test_does_not_mask_unrelated_numbers() -> None:
    # Mã đơn 12 chữ số, số tiền: không phải SĐT.
    assert redact("đơn 123456789012, giá 2450000") == "đơn 123456789012, giá 2450000"


@pytest.mark.parametrize(
    "raw",
    [
        "token EAABsbCS1iHgBO0abcdefGHIJKLmnopQRSTuv",
        "GET /v23.0/me?access_token=abc123def456&fields=id",
        "Authorization: Bearer abc.def.ghi",
        'payload {"page_access_token": "secret-value-1234"}',
        'payload {"password": "hunter2-hunter2"}',
        "cipher gAAAAABlZ3VuX2ZlcnBldF9jaXBoZXJ0ZXh0X2V4YW1wbGU=",
        "cookie: fp_session=abcdef123456",
        "POST https://api.telegram.org/bot1234567890:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw/sendMessage",
    ],
)
def test_redacts_secrets(raw: str) -> None:
    out = redact(raw)
    for leaked in (
        "EAABsbCS1iHgBO0abcdef",
        "abc123def456",
        "abc.def.ghi",
        "secret-value-1234",
        "hunter2-hunter2",
        "X2ZlcnBldF9",
        "abcdef123456",
        "AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw",
    ):
        assert leaked not in out


def test_formatter_redacts_message_args_and_traceback() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(RedactingJsonFormatter())
    logger = logging.getLogger("test.redaction")
    logger.handlers[:] = [handler]
    logger.propagate = False
    try:
        raise ValueError("lỗi với 0987654321")
    except ValueError:
        logger.exception("khách %s gửi token %s", "0912345218", "EAAGm0PX4ZCpsBAxyzxyzxyzxyz")
    line = json.loads(stream.getvalue())
    blob = json.dumps(line, ensure_ascii=False)
    assert "0912345218" not in blob
    assert "0987654321" not in blob
    assert "EAAGm0PX4ZCps" not in blob
    assert "09•• ••• 218" in line["msg"]


def test_formatter_output_stays_valid_json_when_redacting_headers() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(RedactingJsonFormatter())
    logger = logging.getLogger("test.redaction.json")
    logger.handlers[:] = [handler]
    logger.propagate = False
    logger.warning("request cookie: fp_session=abc123; Authorization: Bearer xyz")
    line = json.loads(stream.getvalue())
    assert "abc123" not in line["msg"]
    assert "xyz" not in line["msg"]
