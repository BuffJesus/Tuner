// SPDX-License-Identifier: MIT
//
// Composed widget-factory helpers used across multiple tab builders.
// `theme.hpp` owns the design tokens (colors, fonts, spacing) and the
// pure stylesheet-string helpers; this file owns the small QWidget*
// factories that wrap a few tokens with Qt construction so the tab
// builders don't repeat the same QLabel + QVBoxLayout + setStyleSheet
// boilerplate at every call site.

#pragma once

#include "theme.hpp"

class QLabel;
class QWidget;

// Hero title + breadcrumb label used by FLASH / ASSIST / TRIGGERS /
// LOGGING tabs. Returns a QLabel ready to be addWidget'd into the
// tab's top-of-page layout.
QLabel* make_tab_header(const char* title, const char* breadcrumb);

// "Attention please" card with bold heading + body text and a coloured
// left-edge accent bar. Used for context hints, recovery guidance,
// preflight checks, and similar on-tab call-outs.
QWidget* make_info_card(const char* heading, const char* body,
                         const char* accent_color = tuner_theme::accent_primary);
