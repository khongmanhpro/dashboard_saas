from __future__ import annotations

import time

from app.core.ids import uuid7


def test_version_and_variant() -> None:
    value = uuid7()
    assert value.version == 7
    assert value.variant == "specified in RFC 4122"


def test_timestamp_prefix_matches_now() -> None:
    before = time.time_ns() // 1_000_000
    value = uuid7()
    after = time.time_ns() // 1_000_000
    ts = value.int >> 80
    assert before <= ts <= after


def test_ids_sort_by_creation_time() -> None:
    first = uuid7()
    time.sleep(0.002)
    second = uuid7()
    assert first < second


def test_unique() -> None:
    assert len({uuid7() for _ in range(10_000)}) == 10_000
