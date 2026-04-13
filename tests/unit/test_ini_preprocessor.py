"""Unit tests for the INI preprocessor (#if/#else/#endif/#set/#unset)."""
from __future__ import annotations

from tuner.parsers.common import preprocess_ini_lines


def _lines(text: str) -> list[str]:
    return text.splitlines()


# ---------------------------------------------------------------------------
# Basic #if / #else / #endif
# ---------------------------------------------------------------------------

def test_if_false_skips_block() -> None:
    lines = _lines("""\
before
#if MISSING_SYMBOL
inside_if
#endif
after
""")
    result = preprocess_ini_lines(lines)
    assert "inside_if" not in "\n".join(result)
    assert "before" in "\n".join(result)
    assert "after" in "\n".join(result)


def test_if_true_includes_block() -> None:
    lines = _lines("""\
#if MY_FLAG
inside_if
#endif
""")
    result = preprocess_ini_lines(lines, active_settings=frozenset({"MY_FLAG"}))
    assert "inside_if" in "\n".join(result)


def test_else_taken_when_if_false() -> None:
    lines = _lines("""\
#if MISSING
if_branch
#else
else_branch
#endif
""")
    result = preprocess_ini_lines(lines)
    text = "\n".join(result)
    assert "if_branch" not in text
    assert "else_branch" in text


def test_else_skipped_when_if_true() -> None:
    lines = _lines("""\
#if FLAG
if_branch
#else
else_branch
#endif
""")
    result = preprocess_ini_lines(lines, active_settings=frozenset({"FLAG"}))
    text = "\n".join(result)
    assert "if_branch" in text
    assert "else_branch" not in text


def test_nested_if_both_false() -> None:
    lines = _lines("""\
#if OUTER
outer_only
#if INNER
inner_only
#endif
#endif
after
""")
    result = preprocess_ini_lines(lines)
    text = "\n".join(result)
    assert "outer_only" not in text
    assert "inner_only" not in text
    assert "after" in text


def test_nested_if_outer_true_inner_false() -> None:
    lines = _lines("""\
#if OUTER
outer_only
#if INNER
inner_only
#endif
outer_after_inner
#endif
""")
    result = preprocess_ini_lines(lines, active_settings=frozenset({"OUTER"}))
    text = "\n".join(result)
    assert "outer_only" in text
    assert "inner_only" not in text
    assert "outer_after_inner" in text


# ---------------------------------------------------------------------------
# #set / #unset at file scope
# ---------------------------------------------------------------------------

def test_unset_at_file_scope_disables_symbol() -> None:
    """#unset at file scope should disable the symbol for subsequent #if checks."""
    lines = _lines("""\
#unset MY_FLAG
#if MY_FLAG
should_be_hidden
#endif
visible
""")
    result = preprocess_ini_lines(lines)
    text = "\n".join(result)
    assert "should_be_hidden" not in text
    assert "visible" in text


def test_set_at_file_scope_enables_symbol() -> None:
    lines = _lines("""\
#set MY_FLAG
#if MY_FLAG
should_be_visible
#endif
""")
    result = preprocess_ini_lines(lines)
    assert "should_be_visible" in "\n".join(result)


# ---------------------------------------------------------------------------
# active_settings override file-scope #unset
# ---------------------------------------------------------------------------

def test_active_settings_override_file_unset() -> None:
    """User project settings (#active_settings) must override file-level #unset."""
    lines = _lines("""\
#unset MY_FLAG
#if MY_FLAG
visible_via_user_setting
#endif
""")
    result = preprocess_ini_lines(lines, active_settings=frozenset({"MY_FLAG"}))
    assert "visible_via_user_setting" in "\n".join(result)


def test_active_settings_do_not_override_explicit_unset_for_unflagged() -> None:
    """Symbols not in active_settings stay unset even if not mentioned in file."""
    lines = _lines("""\
#if NOT_SET
hidden
#endif
visible
""")
    result = preprocess_ini_lines(lines)
    text = "\n".join(result)
    assert "hidden" not in text
    assert "visible" in text


# ---------------------------------------------------------------------------
# #define lines are preserved
# ---------------------------------------------------------------------------

def test_define_lines_are_kept() -> None:
    lines = _lines("""\
#define myMacro = "A", "B", "C"
normal_line
""")
    result = preprocess_ini_lines(lines)
    text = "\n".join(result)
    assert "#define myMacro" in text
    assert "normal_line" in text


def test_define_inside_inactive_if_is_dropped() -> None:
    lines = _lines("""\
#if MISSING
#define hiddenMacro = "X"
#endif
""")
    result = preprocess_ini_lines(lines)
    assert "hiddenMacro" not in "\n".join(result)
