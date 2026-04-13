#!/usr/bin/env python3
"""Convert legacy INI/MSQ release artifacts to native .tunerdef / .tuner files.

Usage:
    python scripts/convert_to_native.py

Reads from C:/Users/Cornelio/Desktop/speeduino-202501.6/release/ and writes
native format files alongside the originals + into tests/fixtures/native/.

Formatting improvements over raw json.dumps:
  - Float precision trimmed to definition-declared digits (default 1)
  - 2D table arrays formatted as one row per line (e.g. 16 values per line
    for a 16-column table) so the operator can visually read the grid
  - 1D arrays (axes, curves) formatted on a single line when short
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict
from pathlib import Path

# Add project root to path.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from tuner.domain.ecu_definition import EcuDefinition
from tuner.domain.native_format import NativeDefinition, NativeTune
from tuner.parsers.ini_parser import IniParser
from tuner.parsers.msq_parser import MsqParser
from tuner.services.native_format_service import NativeFormatService

RELEASE_DIR = Path("C:/Users/Cornelio/Desktop/speeduino-202501.6/release")
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "native"


# ---------------------------------------------------------------------------
# Precision + shape lookup
# ---------------------------------------------------------------------------

def build_precision_map(definition: EcuDefinition) -> dict[str, int]:
    """Map parameter/table name → display digits from the INI definition."""
    precision: dict[str, int] = {}
    for scalar in definition.scalars:
        if scalar.digits is not None:
            precision[scalar.name] = scalar.digits
    for table in definition.tables:
        if hasattr(table, "digits") and table.digits is not None:
            precision[table.name] = table.digits
    return precision


def build_shape_map(definition: EcuDefinition) -> dict[str, tuple[int, int]]:
    """Map table/array name → (rows, columns) for 2D formatting."""
    shapes: dict[str, tuple[int, int]] = {}
    for table in definition.tables:
        if table.rows > 0 and table.columns > 0:
            shapes[table.name] = (table.rows, table.columns)
    return shapes


# ---------------------------------------------------------------------------
# Human-readable JSON formatter
# ---------------------------------------------------------------------------

def trim_float(value: float, digits: int) -> float:
    """Round a float to the given number of decimal places."""
    return round(value, digits)


def format_number(value: float, digits: int) -> str:
    """Format a number: integers as int, floats trimmed to digits."""
    rounded = trim_float(value, digits)
    if rounded == int(rounded) and abs(rounded) < 1e15:
        return str(int(rounded))
    return f"{rounded:.{digits}f}".rstrip("0").rstrip(".")


def format_compact_row(values: list[float], digits: int) -> str:
    """Format a list of numbers as a compact single-line array."""
    items = [format_number(v, digits) for v in values]
    return "[" + ", ".join(items) + "]"


def dump_tune_readable(
    tune: NativeTune,
    precision_map: dict[str, int],
    shape_map: dict[str, tuple[int, int]],
    default_digits: int = 1,
) -> str:
    """Serialize a NativeTune to human-readable JSON.

    - Scalars: trimmed precision
    - 1D arrays (≤20 elements): single compact line
    - 2D tables: one row per line, indented
    """
    lines: list[str] = []
    lines.append("{")
    lines.append(f'  "schema_version": "{tune.schema_version}",')
    lines.append(f'  "definition_signature": "{tune.definition_signature}",')
    lines.append('  "values": {')

    entries = list(tune.values.items())
    for i, (name, value) in enumerate(entries):
        digits = precision_map.get(name, default_digits)
        comma = "," if i < len(entries) - 1 else ""

        if isinstance(value, str):
            escaped = json.dumps(value)  # handles quotes, backslashes
            lines.append(f'    "{name}": {escaped}{comma}')
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            formatted = format_number(float(value), digits)
            lines.append(f'    "{name}": {formatted}{comma}')
        elif isinstance(value, list):
            shape = shape_map.get(name)
            if shape and shape[0] > 1 and shape[1] > 1:
                # 2D table — format as array of rows.
                rows, cols = shape
                lines.append(f'    "{name}": [')
                for r in range(rows):
                    start = r * cols
                    end = start + cols
                    row_vals = value[start:end] if end <= len(value) else value[start:]
                    row_str = format_compact_row(row_vals, digits)
                    row_comma = "," if r < rows - 1 else ""
                    lines.append(f'      {row_str}{row_comma}')
                lines.append(f'    ]{comma}')
            elif len(value) <= 20:
                # Short 1D array — single line.
                compact = format_compact_row(value, digits)
                lines.append(f'    "{name}": {compact}{comma}')
            else:
                # Long 1D array — multi-line but compact groups of 16.
                lines.append(f'    "{name}": [')
                chunk_size = 16
                for c in range(0, len(value), chunk_size):
                    chunk = value[c:c + chunk_size]
                    items = [format_number(v, digits) for v in chunk]
                    chunk_str = ", ".join(items)
                    chunk_comma = "," if c + chunk_size < len(value) else ""
                    lines.append(f'      {chunk_str}{chunk_comma}')
                lines.append(f'    ]{comma}')
        else:
            # Fallback: json.dumps for unknown types.
            lines.append(f'    "{name}": {json.dumps(value)}{comma}')

    lines.append("  }")
    lines.append("}")
    return "\n".join(lines) + "\n"


def dump_definition_readable(native_def: NativeDefinition) -> str:
    """Serialize a NativeDefinition with trimmed precision on min/max."""
    data = asdict(native_def)
    # Trim min_value/max_value precision in parameters.
    for p in data.get("parameters", []):
        for key in ("min_value", "max_value"):
            v = p.get(key)
            if isinstance(v, float):
                rounded = round(v, 4)
                p[key] = int(rounded) if rounded == int(rounded) else rounded
    return json.dumps(data, indent=2, sort_keys=False)


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------

def convert_pair(
    ini_path: Path,
    msq_path: Path,
    output_dir: Path,
    label: str,
) -> None:
    """Convert one INI+MSQ pair to .tunerdef + .tuner + .tunerproj."""
    print(f"\n{'='*60}")
    print(f"Converting: {label}")
    print(f"  INI: {ini_path.name}")
    print(f"  MSQ: {msq_path.name}")

    # Parse legacy artifacts.
    parser = IniParser()
    definition = parser.parse(ini_path)
    print(f"  Parsed INI: signature={definition.firmware_signature}, "
          f"{len(definition.scalars)} scalars, "
          f"{len(definition.tables)} tables, "
          f"{len(definition.curve_definitions)} curves")

    msq_parser = MsqParser()
    tune = msq_parser.parse(msq_path)
    print(f"  Parsed MSQ: signature={tune.signature}, "
          f"{len(tune.constants)} constants, "
          f"{len(tune.pc_variables)} pc_variables")

    # Build lookup maps for precision and shape.
    precision_map = build_precision_map(definition)
    shape_map = build_shape_map(definition)

    # Convert to native format.
    svc = NativeFormatService()
    native_def = svc.from_ecu_definition(definition)
    native_tune = svc.from_tune_file(tune, native_def)

    print(f"  Native definition: {len(native_def.parameters)} parameters, "
          f"{len(native_def.axes)} axes, "
          f"{len(native_def.tables)} tables, "
          f"{len(native_def.curves)} curves")
    print(f"  Native tune: {len(native_tune.values)} values")

    # Write files.
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = msq_path.stem

    # .tunerdef — readable definition.
    def_path = output_dir / f"{stem}.tunerdef"
    def_json = dump_definition_readable(native_def)
    def_path.write_text(def_json, encoding="utf-8")
    print(f"  Wrote: {def_path} ({len(def_json):,} bytes)")

    # .tuner — readable tune with compact tables.
    tune_path = output_dir / f"{stem}.tuner"
    tune_json = dump_tune_readable(native_tune, precision_map, shape_map)
    tune_path.write_text(tune_json, encoding="utf-8")
    print(f"  Wrote: {tune_path} ({len(tune_json):,} bytes)")

    # .tunerproj — project metadata.
    proj_path = output_dir / f"{stem}.tunerproj"
    proj = {
        "format": "tuner-project-v1",
        "name": label,
        "definition_file": def_path.name,
        "tune_file": tune_path.name,
        "firmware_signature": native_def.firmware_signature or "",
        "active_settings": [],
        "notes": f"Converted from {ini_path.name} + {msq_path.name}",
    }
    proj_json = json.dumps(proj, indent=2)
    proj_path.write_text(proj_json, encoding="utf-8")
    print(f"  Wrote: {proj_path} ({len(proj_json):,} bytes)")

    # Verify round-trip: the readable format must still parse as valid JSON
    # and survive the standard NativeFormatService loader.
    parsed_tune = json.loads(tune_json)
    assert parsed_tune["schema_version"] == native_tune.schema_version
    assert parsed_tune["definition_signature"] == native_tune.definition_signature
    assert len(parsed_tune["values"]) == len(native_tune.values)
    # Verify tune values parse back correctly.
    loaded_tune = svc.load_tune(tune_json)
    assert len(loaded_tune.values) == len(native_tune.values)
    # Verify definition round-trips.
    loaded_def = svc.load_definition(def_json)
    assert len(loaded_def.parameters) == len(native_def.parameters)
    print("  Round-trip verification: PASS")


def main():
    if not RELEASE_DIR.exists():
        print(f"Release directory not found: {RELEASE_DIR}")
        sys.exit(1)

    pairs = []

    # 1. Production: standard INI + Ford300 MSQ.
    std_ini = RELEASE_DIR / "speeduino-dropbear-v2.0.1.ini"
    ford_msq = RELEASE_DIR / "Ford300_TwinGT28_BaseStartup.msq"
    if std_ini.exists() and ford_msq.exists():
        pairs.append((std_ini, ford_msq, "Ford 300 Twin GT28 (production)"))

    # 2. Production: standard INI + base tune MSQ.
    base_msq = RELEASE_DIR / "speeduino-dropbear-v2.0.1-base-tune.msq"
    if std_ini.exists() and base_msq.exists():
        pairs.append((std_ini, base_msq, "Speeduino Base Tune (production)"))

    # 3. Experimental U16P2: experimental INI + Ford300 U16P2 MSQ.
    exp_ini = RELEASE_DIR / "speeduino-dropbear-v2.0.1-u16p2-experimental.ini"
    ford_exp_msq = RELEASE_DIR / "Ford300_TwinGT28_BaseStartup_u16p2_experimental.msq"
    if exp_ini.exists() and ford_exp_msq.exists():
        pairs.append((exp_ini, ford_exp_msq, "Ford 300 Twin GT28 (U16P2 experimental)"))

    # 4. Experimental U16P2: experimental INI + base tune MSQ.
    exp_base_msq = RELEASE_DIR / "speeduino-dropbear-v2.0.1-u16p2-experimental-base-tune.msq"
    if exp_ini.exists() and exp_base_msq.exists():
        pairs.append((exp_ini, exp_base_msq, "Speeduino Base Tune (U16P2 experimental)"))

    if not pairs:
        print("No valid INI+MSQ pairs found.")
        sys.exit(1)

    print(f"Found {len(pairs)} INI+MSQ pair(s) to convert.")

    for ini_path, msq_path, label in pairs:
        # Write to both the release dir and the test fixtures.
        convert_pair(ini_path, msq_path, RELEASE_DIR / "native", label)
        convert_pair(ini_path, msq_path, FIXTURE_DIR, label)

    print(f"\n{'='*60}")
    print(f"Done. {len(pairs)} pair(s) converted.")
    print(f"  Release output: {RELEASE_DIR / 'native'}")
    print(f"  Fixture output: {FIXTURE_DIR}")


if __name__ == "__main__":
    main()
