// SPDX-License-Identifier: MIT
//
// Tuner desktop — canonical design tokens.
//
// One place that names every color, font size, spacing value, and corner
// radius the app uses. Inline `build_*_tab` code in main.cpp should pull
// from these tokens instead of hard-coding hex literals so the palette
// stays coherent as surfaces evolve.
//
// Philosophy link (see docs/ux-design.md):
//
//   - "Don't over-animate — automotive tuning is precision work." The
//     palette is deliberately restrained: 5 background levels, 5 accents,
//     6 type sizes. No drift.
//   - "Progressive disclosure." The type scale has a clear hierarchy from
//     micro captions up to hero values so visual weight tracks importance.
//   - "Context over structure." Accents are named semantically
//     (primary/ok/warning/danger/special) not by hue, so surface code
//     reads like intent rather than color choices.
//
// Header-only. Safe to include from any translation unit. Zero runtime
// cost — every token is a `constexpr const char*` or `constexpr int`.

#pragma once

#include <string>

namespace tuner_theme {

// ---------------------------------------------------------------------------
// Background levels — darkest (outermost) → lightest (inset).
// ---------------------------------------------------------------------------
//
// The 10 near-black variants that used to drift through main.cpp collapse
// to these 5. If you need a new level, add it here with a rationale in a
// comment — don't inline-a-new-hex in a stylesheet.

constexpr const char* bg_deep     = "#0f1116";  // app shell, behind everything
constexpr const char* bg_base     = "#14171e";  // tab content backdrop
constexpr const char* bg_panel    = "#1a1d24";  // card / content container
constexpr const char* bg_elevated = "#20242c";  // header strip / hovered card
constexpr const char* bg_inset    = "#262a33";  // input, inset cell, chip

// ---------------------------------------------------------------------------
// Borders and dividers.
// ---------------------------------------------------------------------------

constexpr const char* border       = "#2f343d";  // primary 1px divider
constexpr const char* border_soft  = "#262a33";  // quiet internal divider
constexpr const char* border_accent = "#5a9ad6"; // focus / selection edge
// Scrollbar thumb hover — one step lighter than `border`. Deliberately
// a separate token rather than reusing one of the background levels
// because scrollbar-thumb-hover is the *only* surface in the palette
// that needs a value in this exact brightness band (between `border`
// and `text_dim`). Inlining it would re-introduce the drift the
// sub-slice 88 token system was built to kill.
constexpr const char* scroll_thumb_hover = "#404652";

// ---------------------------------------------------------------------------
// Text hierarchy.
// ---------------------------------------------------------------------------
//
// Four levels from loud → quiet. Pick the quietest level that still reads
// at a glance. Most body text should use `text_secondary`; reserve
// `text_primary` for titles and live values.

constexpr const char* text_primary   = "#e8edf5";  // titles, hero values
constexpr const char* text_secondary = "#c9d1e0";  // body text
constexpr const char* text_muted     = "#8a93a6";  // labels, field names
constexpr const char* text_dim       = "#6a7080";  // captions, separators
constexpr const char* text_inverse   = "#0f1116";  // text on bright chips

// ---------------------------------------------------------------------------
// Semantic accents. Exactly one per meaning.
// ---------------------------------------------------------------------------
//
// When you want a "safe" color, ask what it means:
//   - primary  → informational, selection, default accent
//   - ok       → value inside healthy zone
//   - warning  → attention needed, not urgent
//   - danger   → urgent, engine at risk
//   - special  → derived / computed / formula channel (rarely used — keep
//                it rare so it stays visually distinctive)
//
// Don't introduce new hues without a semantic reason.

constexpr const char* accent_primary = "#5a9ad6";  // blue
constexpr const char* accent_ok      = "#5ad687";  // green
constexpr const char* accent_warning = "#d6a55a";  // amber
constexpr const char* accent_danger  = "#d65a5a";  // red
constexpr const char* accent_special = "#9a7ad6";  // purple — computed/formula

// Subtle fills for highlighted regions (e.g. staged-change backgrounds).
constexpr const char* fill_primary_soft = "#1c3a5e";  // blue-tinted dark fill
constexpr const char* fill_primary_mid  = "#2a4a6e";  // brighter blue fill

// ---------------------------------------------------------------------------
// Type scale — pixel sizes.
// ---------------------------------------------------------------------------
//
// Six sizes. If you need a value between two, round to the nearer one
// rather than adding a new token. The scale is tuned for 100% DPI on a
// desktop monitor; high-DPI scaling handles everything else.

constexpr int font_micro   = 10;  // edge labels, tiny captions
constexpr int font_small   = 11;  // muted labels, dividers, chips
constexpr int font_body    = 12;  // body text
constexpr int font_medium  = 13;  // emphasised value, chip value
constexpr int font_label   = 14;  // header label
constexpr int font_heading = 18;  // section heading
constexpr int font_hero    = 28;  // gauge number, hero value

// ---------------------------------------------------------------------------
// Spacing scale (px).
// ---------------------------------------------------------------------------

constexpr int space_xs = 4;
constexpr int space_sm = 8;
constexpr int space_md = 12;
constexpr int space_lg = 16;
constexpr int space_xl = 24;

// ---------------------------------------------------------------------------
// Corner radius.
// ---------------------------------------------------------------------------

constexpr int radius_sm = 4;
constexpr int radius_md = 6;
constexpr int radius_lg = 10;

// ---------------------------------------------------------------------------
// Composed stylesheet helpers. Inline so the header stays self-contained.
// ---------------------------------------------------------------------------
//
// Usage:
//
//     widget->setStyleSheet(QString::fromUtf8(
//         tuner_theme::card_style(tuner_theme::accent_primary).c_str()));
//
// These are the three most-repeated patterns in main.cpp — card, header
// strip, and chip. Everything else should compose tokens inline rather
// than growing this API.

inline std::string card_style(const char* accent = nullptr) {
    std::string s;
    s.reserve(192);
    s += "background-color: "; s += bg_panel; s += "; ";
    s += "border: 1px solid ";  s += border;   s += "; ";
    if (accent) {
        s += "border-left: 3px solid ";
        s += accent;
        s += "; ";
    }
    s += "border-radius: 6px;";
    return s;
}

inline std::string header_strip_style() {
    std::string s;
    s.reserve(128);
    s += "background-color: "; s += bg_elevated; s += "; ";
    s += "border: 1px solid ";  s += border;      s += "; ";
    s += "border-radius: 6px; padding: 4px 12px;";
    return s;
}

// Tab header strip — used by FLASH / ASSIST / TRIGGERS / LOGGING tabs
// to introduce the current surface with a hero title plus a dim
// breadcrumb describing what the operator does on this tab. This is
// the visual grammar of "here's where you are, here's the workflow":
//
//   [ Tune Assist   ·  Review correction proposals, then apply ]
//
// Philosophy — progressive disclosure applied to navigation. The
// title lands loudest (bold, `text_primary`, `font_label`); the
// breadcrumb sits quietly (`text_dim`, `font_small`). Four tabs
// shared four identical copies of the inline stylesheet before this
// token landed — collapsing them into one helper means the header
// pattern is a first-class design primitive that future tabs can
// reuse without drifting the palette.
inline std::string tab_header_style() {
    std::string s;
    s.reserve(128);
    s += "background-color: "; s += bg_panel; s += "; ";
    s += "border: 1px solid ";  s += border;   s += "; ";
    s += "border-radius: "; s += std::to_string(radius_sm); s += "px; ";
    s += "padding: "; s += std::to_string(space_sm); s += "px "; s += std::to_string(space_md); s += "px;";
    return s;
}

// Composed HTML body for a tab header label. Produces the exact
// `<title> · <breadcrumb>` shape the FLASH / ASSIST / TRIGGERS /
// LOGGING tabs use — hero title in `text_primary` `font_label`,
// breadcrumb in `text_dim` `font_small` with a leading `·` divider.
// `buf` must be at least 512 bytes.
inline void format_tab_header_html(char* buf, std::size_t buf_size,
                                   const char* title,
                                   const char* breadcrumb) {
    std::snprintf(buf, buf_size,
        "<span style='font-size: %dpx; font-weight: bold; color: %s;'>%s</span>"
        "<span style='color: %s; font-size: %dpx;'>"
        "  \xc2\xb7  %s"
        "</span>",
        font_label, text_primary, title,
        text_dim, font_small, breadcrumb);
}

// ---------------------------------------------------------------------------
// LIVE-tab dashboard number card helpers (sub-slice 114)
// ---------------------------------------------------------------------------
//
// Number cards are the secondary LIVE surface: rectangular readouts
// with a coloured top bar whose hue tracks the current zone state
// (ok / warning / danger). Before this slice, every card built its
// own stylesheet inline and every zone dispatch hard-coded the four
// accent hues. Collapsing to these two helpers means the card look
// tunes in one place and the zone colors always match every other
// "ok/warning/danger" surface in the app.

// Stylesheet for a LIVE number card. `accent` is the top-bar color
// (typically one of `accent_primary` / `accent_ok` / `accent_warning`
// / `accent_danger`). `top_border_px` is the thickness of the top
// bar — the call site pulses this to 4px on danger-zone entry as
// an attention flash, then drops back to 2px on the next tick.
inline std::string number_card_style(const char* accent, int top_border_px = 2) {
    std::string s;
    s.reserve(224);
    s += "background-color: "; s += bg_panel; s += "; ";
    s += "border: 1px solid "; s += border; s += "; ";
    s += "border-top: "; s += std::to_string(top_border_px);
    s += "px solid "; s += accent; s += "; ";
    s += "border-radius: "; s += std::to_string(radius_md); s += "px; ";
    s += "padding: "; s += std::to_string(space_xs + 2); s += "px ";
    s += std::to_string(space_sm); s += "px;";
    return s;
}

// Composed HTML body for a LIVE number card. Three lines:
//   1. Hero value + optional alert icon (accent colour, `font_size`
//      pixels — caller picks the size so wide cells can use bigger)
//   2. Units string (muted, small)
//   3. Title (dim, micro)
// `buf` must be at least 384 bytes.
inline void format_number_card_html(char* buf, std::size_t buf_size,
                                    int value_font_size,
                                    const char* accent,
                                    double value,
                                    const char* alert_icon,
                                    const char* units,
                                    const char* title) {
    std::snprintf(buf, buf_size,
        "<div style='text-align: center;'>"
        "<span style='font-size: %dpx; font-weight: bold; color: %s;'>%.1f%s</span>"
        "<span style='color: %s; font-size: %dpx;'> %s</span><br>"
        "<span style='color: %s; font-size: %dpx;'>%s</span>"
        "</div>",
        value_font_size, accent, value, alert_icon,
        text_muted, font_small, units,
        text_dim, font_micro, title);
}

// Pick the accent colour for a zone name. Mirrors the string-dispatch
// pattern the LIVE-tab card update loop uses: the `GaugeColorZones`
// domain service returns zone names as strings (`"ok"` / `"warning"`
// / `"danger"`) rather than enum values, so the UI layer maps them
// to theme tokens here. Unknown zone name falls back to
// `accent_primary` so the card is never unpainted.
inline const char* zone_accent(const std::string& zone) {
    if (zone == "ok")      return accent_ok;
    if (zone == "warning") return accent_warning;
    if (zone == "danger")  return accent_danger;
    return accent_primary;
}

inline std::string chip_style(const char* accent = nullptr) {
    std::string s;
    s.reserve(160);
    s += "background-color: "; s += bg_inset; s += "; ";
    if (accent) {
        s += "border: 1px solid "; s += accent; s += "; ";
    } else {
        s += "border: 1px solid "; s += border; s += "; ";
    }
    s += "border-radius: 4px; padding: 2px 8px;";
    return s;
}

// ---------------------------------------------------------------------------
// TUNE-tab helpers (sub-slice 91)
// ---------------------------------------------------------------------------

// Three-state scalar editor stylesheet: the default `default` state
// (neutral chrome, no accent), the `ok` state (after a successful stage
// — blue tint), and the `warning` state (after a cross-parameter
// warning fires — amber tint). One composed stylesheet per state keeps
// the 3×75-character blocks in main.cpp from drifting.
enum class EditorState { Default, Ok, Warning };

inline std::string scalar_editor_style(EditorState state = EditorState::Default) {
    const char* accent;
    const char* text;
    const char* weight;
    switch (state) {
        case EditorState::Ok:
            accent = accent_primary;
            text = accent_primary;
            weight = "bold";
            break;
        case EditorState::Warning:
            accent = accent_warning;
            text = accent_warning;
            weight = "bold";
            break;
        default:
            accent = border;
            text = text_primary;
            weight = "normal";
            break;
    }
    std::string s;
    s.reserve(224);
    s += "background: "; s += bg_elevated; s += "; ";
    s += "border: 1px solid "; s += accent; s += "; ";
    s += "border-radius: 3px; padding: 3px 6px; ";
    s += "color: "; s += text; s += "; ";
    s += "font-size: "; s += std::to_string(font_small); s += "px; ";
    s += "font-weight: "; s += weight; s += ";";
    return s;
}

// QComboBox editor for enum/bits parameters. Same state pattern as
// scalar_editor_style — Default (neutral), Ok (blue, staged), Warning
// (amber). Includes the dropdown popup QSS so the list matches the
// dark theme instead of rendering with the OS system palette.
inline std::string combo_editor_style(EditorState state = EditorState::Default) {
    const char* accent;
    const char* text;
    const char* weight;
    switch (state) {
        case EditorState::Ok:
            accent = accent_primary; text = accent_primary; weight = "bold"; break;
        case EditorState::Warning:
            accent = accent_warning; text = accent_warning; weight = "bold"; break;
        default:
            accent = border; text = text_primary; weight = "normal"; break;
    }
    std::string s;
    s.reserve(512);
    s += "QComboBox { background: "; s += bg_elevated; s += "; ";
    s += "border: 1px solid "; s += accent; s += "; ";
    s += "border-radius: 3px; padding: 3px 6px; ";
    s += "color: "; s += text; s += "; ";
    s += "font-size: "; s += std::to_string(font_small); s += "px; ";
    s += "font-weight: "; s += weight; s += "; } ";
    s += "QComboBox::drop-down { border: none; width: 16px; } ";
    s += "QComboBox QAbstractItemView { background: "; s += bg_panel; s += "; ";
    s += "color: "; s += text_secondary; s += "; ";
    s += "border: 1px solid "; s += border; s += "; ";
    s += "selection-background-color: "; s += fill_primary_mid; s += "; ";
    s += "selection-color: "; s += text_primary; s += "; }";
    return s;
}

// Section header divider inside a scalar parameter form. Used between
// groups of related fields — the 1px top border + padding make the
// divider visible without drawing a heavy line that competes with the
// card border.
inline std::string section_header_style() {
    std::string s;
    s.reserve(128);
    s += "color: "; s += text_secondary; s += "; ";
    s += "font-weight: 600; ";
    s += "margin-top: "; s += std::to_string(space_md); s += "px; ";
    s += "padding-top: "; s += std::to_string(space_xs + 2); s += "px; ";
    s += "border-top: 1px solid "; s += border; s += ";";
    return s;
}

// Muted field label (left column of a scalar parameter row).
inline std::string field_label_style() {
    std::string s;
    s.reserve(96);
    s += "color: "; s += text_muted; s += "; ";
    s += "font-size: "; s += std::to_string(font_small); s += "px;";
    return s;
}

// Inline chip for a string-valued parameter (e.g. text constants).
inline std::string inline_value_chip_style() {
    std::string s;
    s.reserve(160);
    s += "color: "; s += text_secondary; s += "; ";
    s += "font-size: "; s += std::to_string(font_small); s += "px; ";
    s += "background: "; s += bg_inset; s += "; ";
    s += "border: 1px solid "; s += border; s += "; ";
    s += "border-radius: 3px; padding: 2px 8px;";
    return s;
}

// Dim units label (e.g. "ms", "%", "rpm") trailing a value.
inline std::string units_label_style() {
    std::string s;
    s.reserve(80);
    s += "color: "; s += text_dim; s += "; ";
    s += "font-size: "; s += std::to_string(font_micro); s += "px;";
    return s;
}

}  // namespace tuner_theme
