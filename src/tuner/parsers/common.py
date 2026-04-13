from __future__ import annotations

from pathlib import Path


def parse_key_value_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return parse_key_value_lines(path.read_text(encoding="utf-8", errors="ignore").splitlines())


def parse_key_value_lines(lines: list[str]) -> dict[str, str]:
    data: dict[str, str] = {}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith(("#", ";", "//")):
            continue
        if "=" in line:
            key, value = line.split("=", 1)
        elif ":" in line:
            key, value = line.split(":", 1)
        else:
            continue
        data[key.strip()] = value.strip()
    return data


def preprocess_ini_lines(
    raw_lines: list[str],
    active_settings: frozenset[str] = frozenset(),
) -> list[str]:
    """Evaluate ``#if``/``#else``/``#endif`` and ``#set``/``#unset`` directives.

    Returns only the lines that belong to active conditional branches.
    ``#define`` lines are kept so downstream macro-expansion still works.
    ``#set``/``#unset`` are consumed (not emitted).

    **Priority**: ``active_settings`` represents user/project-level choices and
    takes precedence over file-level ``#set``/``#unset`` defaults.  The file is
    scanned in two passes: the first collects the file's own ``#set``/``#unset``
    directives (at file scope only), the second evaluates conditionals using
    ``effective = file_defaults | active_settings``.

    Nesting is supported.  Unknown ``#``-directives are treated as comments and
    dropped when inside an inactive branch.
    """
    # --- Phase 1: collect file-scope #set / #unset defaults ---
    file_settings: set[str] = set()
    nesting = 0  # depth inside #if blocks; #set/#unset outside these are "file scope"
    for line in raw_lines:
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split(None, 1)
        d = parts[0]
        if d == "#if":
            nesting += 1
        elif d == "#endif":
            nesting = max(0, nesting - 1)
        elif d in ("#set", "#unset") and nesting == 0:
            symbol = parts[1].strip() if len(parts) > 1 else ""
            if d == "#set":
                file_settings.add(symbol)
            else:
                file_settings.discard(symbol)

    # --- Effective settings: user wins over file defaults ---
    settings: set[str] = (file_settings - set()) | set(active_settings)

    # --- Phase 2: evaluate conditionals with fixed effective settings ---
    result: list[str] = []
    # Stack of (branch_active, has_seen_else)
    # branch_active already folds in parent-branch activity.
    stack: list[tuple[bool, bool]] = []

    def _in_active_branch() -> bool:
        return all(active for active, _ in stack)

    for line in raw_lines:
        stripped = line.strip()
        if not stripped:
            if _in_active_branch():
                result.append(line)
            continue

        parts = stripped.split(None, 1)
        directive = parts[0]

        if directive == "#if":
            symbol = parts[1].strip() if len(parts) > 1 else ""
            branch_active = _in_active_branch() and symbol in settings
            stack.append((branch_active, False))
            continue

        if directive == "#else":
            if stack:
                was_active, seen_else = stack[-1]
                if not seen_else:
                    parent_active = all(a for a, _ in stack[:-1])
                    stack[-1] = (parent_active and not was_active, True)
            continue

        if directive == "#endif":
            if stack:
                stack.pop()
            continue

        if directive in ("#set", "#unset"):
            # Consumed in phase 1; drop silently here.
            continue

        # All other # lines (comments, #define, unrecognised) — include
        # only when inside an active branch.
        if stripped.startswith("#") and not _in_active_branch():
            continue

        if _in_active_branch():
            result.append(line)

    return result
