from __future__ import annotations

from zlib import crc32


def crc32_bytes(payload: bytes) -> int:
    return crc32(payload) & 0xFFFFFFFF
