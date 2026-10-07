"""Small shared helpers: ids, time, hashing, JSON."""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timedelta, timezone


def uuid7() -> str:
    """Time-ordered UUIDv7 string (RFC 9562)."""
    ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), "big")
    rand_a = rand >> 68 & 0xFFF
    rand_b = rand & ((1 << 62) - 1)
    value = (ms & ((1 << 48) - 1)) << 80 | 0x7 << 76 | rand_a << 64 | 0b10 << 62 | rand_b
    h = f"{value:032x}"
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None = None) -> str:
    dt = dt or utcnow()
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def iso_in_days(days: int) -> str:
    return iso(utcnow() + timedelta(days=days))


def parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).hexdigest()


def dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def loads(s: str | None):
    return None if s is None else json.loads(s)
