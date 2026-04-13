"""Tests for the EcuDefinition endianness consumer (Fragile area #3).

The INI parser already reads ``endianness = big|little`` into
``EcuDefinition.endianness``, but until now there was no consumer of
the value. ``is_little_endian()`` and ``byte_order()`` are the canonical
helpers future byte-order-aware code paths must use.
"""
from __future__ import annotations

from tuner.domain.ecu_definition import EcuDefinition


def test_default_is_little_endian() -> None:
    """Definitions with no explicit endianness must default to little
    (the historical Speeduino assumption). Flipping this default later
    would require auditing every byte path, so it must stay locked
    behind a test."""
    defn = EcuDefinition(name="speeduino")
    assert defn.is_little_endian() is True
    assert defn.byte_order() == "little"


def test_explicit_little_endian() -> None:
    defn = EcuDefinition(name="x", endianness="little")
    assert defn.is_little_endian() is True
    assert defn.byte_order() == "little"


def test_explicit_big_endian() -> None:
    defn = EcuDefinition(name="x", endianness="big")
    assert defn.is_little_endian() is False
    assert defn.byte_order() == "big"


def test_case_insensitive_and_whitespace_tolerant() -> None:
    for raw in ("BIG", " Big ", "BIG\n", "big"):
        defn = EcuDefinition(name="x", endianness=raw)
        assert defn.is_little_endian() is False, f"failed for {raw!r}"
        assert defn.byte_order() == "big"


def test_unknown_value_falls_back_to_little() -> None:
    """A typo or unsupported value must NOT silently flip byte order
    on existing fixtures — it falls back to the safe default."""
    defn = EcuDefinition(name="x", endianness="middle-endian")
    assert defn.is_little_endian() is True
    assert defn.byte_order() == "little"


def test_byte_order_matches_struct_format_strings() -> None:
    """The string returned by ``byte_order()`` is the form Python's
    ``int.from_bytes`` and ``int.to_bytes`` accept directly."""
    little = EcuDefinition(name="x", endianness="little")
    big = EcuDefinition(name="x", endianness="big")
    payload = b"\x01\x00"
    assert int.from_bytes(payload, little.byte_order()) == 1
    assert int.from_bytes(payload, big.byte_order()) == 256
