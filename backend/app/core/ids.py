"""UUIDv7 (RFC 9562): tăng dần theo thời gian nên index B-tree gọn hơn UUIDv4."""

from __future__ import annotations

import os
import time
import uuid


def uuid7() -> uuid.UUID:
    ts_ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), "big")
    rand_a = rand >> 62 & 0xFFF  # 12 bit
    rand_b = rand & ((1 << 62) - 1)  # 62 bit
    value = (ts_ms & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76  # version 7
    value |= rand_a << 64
    value |= 0b10 << 62  # variant RFC 4122
    value |= rand_b
    return uuid.UUID(int=value)
