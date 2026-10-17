from __future__ import annotations

import hashlib
import hmac

from app.meta.signature import sign, verify_signature

SECRET = "app-secret-for-tests"
BODY = b'{"object":"page","entry":[]}'


def test_sign_matches_meta_format() -> None:
    expected = "sha256=" + hmac.new(SECRET.encode(), BODY, hashlib.sha256).hexdigest()
    assert sign(BODY, SECRET) == expected


def test_valid_signature() -> None:
    assert verify_signature(BODY, sign(BODY, SECRET), SECRET)


def test_uppercase_hex_is_accepted() -> None:
    header = sign(BODY, SECRET)
    assert verify_signature(BODY, "sha256=" + header.removeprefix("sha256=").upper(), SECRET)


def test_rejects_tampered_body_wrong_secret_and_bad_headers() -> None:
    header = sign(BODY, SECRET)
    assert not verify_signature(BODY + b" ", header, SECRET)
    assert not verify_signature(BODY, header, "other-secret")
    assert not verify_signature(BODY, None, SECRET)
    assert not verify_signature(BODY, "", SECRET)
    assert not verify_signature(BODY, header.replace("sha256=", "sha1="), SECRET)
    # Chưa cấu hình app secret thì không bao giờ hợp lệ, kể cả chữ ký tính bằng chuỗi rỗng.
    assert not verify_signature(BODY, sign(BODY, ""), "")
