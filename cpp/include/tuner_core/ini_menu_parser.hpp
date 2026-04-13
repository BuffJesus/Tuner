// SPDX-License-Identifier: MIT
//
// tuner_core::IniMenuParser — port of `IniParser._parse_menus`.
// Parses the `[Menu]` section that defines the operator's top-level
// navigation structure: which menus exist, what items each menu
// holds, and what those items target (table editors, curve editors,
// dialog panels, etc.).
//
// `[Menu]` is a stateful grammar like the previous parser slices:
// `menu = "Title"` opens a new menu, then a sequence of `subMenu =`
// or `groupChildMenu =` lines populate items into the active menu.
// Items targeting `std_separator` are dropped (legacy uses
// these as visual dividers, not selectable nodes).
//
// Item lines carry up to four fields after the target:
//   subMenu = target, "Label", page_number, {visibility_expression}
// Where `page_number` and `{visibility_expression}` are both
// optional and may appear in either order. The label defaults to
// the target when missing.
//
// Why this slice matters: the menu catalog is the bridge between
// the section parsers (which produce table/curve/dialog metadata)
// and the workspace navigator UI. Every page the operator can
// navigate to in legacy is reachable from a `[Menu]` entry,
// and the visibility expressions on menu items are how features
// like "show LAMBDA-only pages only when LAMBDA is set" work.

#pragma once

#include "tuner_core/ini_defines_parser.hpp"

#include <optional>
#include <set>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core {

// One item inside a menu. Mirrors `MenuItemDefinition` field-for-field.
struct IniMenuItem {
    std::string target;                            // page id (e.g. "veTblTbl"), dialog id, etc.
    std::optional<std::string> label;              // operator-facing label; defaults to target
    std::optional<int> page;                       // optional page number override
    std::optional<std::string> visibility_expression;  // {expression} from the INI
};

// One top-level menu. Mirrors `MenuDefinition`.
struct IniMenu {
    std::string title;
    std::vector<IniMenuItem> items;
};

struct IniMenuSection {
    std::vector<IniMenu> menus;
};

// Parse `[Menu]` from pre-preprocessed INI text. The optional
// `defines` map is currently unused (`[Menu]` doesn't have
// `$macroName` option lists) but the parameter is present so the
// signature is consistent with the other section parsers.
IniMenuSection parse_menu_section(
    std::string_view text,
    const IniDefines& defines = {});

IniMenuSection parse_menu_lines(
    const std::vector<std::string>& lines,
    const IniDefines& defines = {});

// Composed pipeline: preprocess + collect defines + parse, mirroring
// the Python `IniParser.parse()` flow.
IniMenuSection parse_menu_section_preprocessed(
    std::string_view text,
    const std::set<std::string>& active_settings = {});

}  // namespace tuner_core
