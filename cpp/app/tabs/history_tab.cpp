// SPDX-License-Identifier: MIT

#include "tabs/history_tab.hpp"

#include "theme.hpp"
#include "ui/styles.hpp"

#include <QLabel>
#include <QScrollArea>
#include <QString>
#include <QVBoxLayout>
#include <QWidget>

#include <cstdio>

namespace tt = tuner_theme;

QWidget* build_history_tab() {
    auto* scroll = new QScrollArea;
    scroll->setWidgetResizable(true);
    scroll->setStyleSheet("QScrollArea { border: none; }");
    auto* container = new QWidget;
    auto* layout = new QVBoxLayout(container);
    layout->setContentsMargins(tt::space_lg, tt::space_lg, tt::space_lg, tt::space_lg);
    layout->setSpacing(tt::space_md);

    layout->addWidget(make_tab_header(
        "About",
        "Project info \xc2\xb7 keyboard shortcuts \xc2\xb7 resources"));

    // App identity card.
    {
        char body[512];
        std::snprintf(body, sizeof(body),
            "<span style='font-size: %dpx; font-weight: bold; color: %s;'>"
            "TUNER</span><br>"
            "<span style='color: %s; font-size: %dpx;'>"
            "A modern workstation for Speeduino engines.<br>"
            "The same information legacy tools show, organized around what "
            "the operator is trying to accomplish.</span>",
            tt::font_heading, tt::text_primary,
            tt::text_secondary, tt::font_body);
        auto* card = make_info_card("", body, tt::accent_primary);
        if (auto* lbl = card->findChild<QLabel*>()) {
            lbl->setTextFormat(Qt::RichText);
            lbl->setText(QString::fromUtf8(body));
        }
        layout->addWidget(card);
    }

    // Quick-start reference.
    layout->addWidget(make_info_card(
        "Getting Started",
        "1. File \xe2\x86\x92 New Project \xe2\x80\x94 creates a project directory + runs the Engine Setup Wizard\n"
        "2. Review the generated tables on the TUNE tab (Alt+1)\n"
        "3. Connect to the ECU (File \xe2\x86\x92 Connect to ECU)\n"
        "4. Write to RAM (Ctrl+W) \xe2\x80\x94 changes take effect immediately\n"
        "5. Burn to Flash (Ctrl+B) \xe2\x80\x94 permanent, survives power cycle\n"
        "6. Use LOGGING to capture data while driving\n"
        "7. Use ASSIST \xe2\x86\x92 VE Analyze to refine the tune from logged data",
        tt::accent_ok));

    // Tab reference.
    layout->addWidget(make_info_card(
        "Tabs",
        "\xf0\x9f\x94\xa7  TUNE     \xe2\x80\x94 Edit scalars, tables, curves. Review + Write + Burn.\n"
        "\xf0\x9f\x93\x8a  LIVE     \xe2\x80\x94 Runtime gauges, indicators, hardware test panel.\n"
        "\xe2\x9a\xa1  FLASH    \xe2\x80\x94 Firmware preflight + flash execution.\n"
        "\xe2\x9a\x99  SETUP    \xe2\x80\x94 Engine Setup Wizard + generator previews + guided hardware cards.\n"
        "\xf0\x9f\xa7\xaa  ASSIST   \xe2\x80\x94 VE Analyze, WUE Analyze, Virtual Dyno.\n"
        "\xf0\x9f\x94\x8d  TRIGGERS \xe2\x80\x94 Trigger log capture, CSV import, oscilloscope view.\n"
        "\xf0\x9f\x93\x9d  LOGGING  \xe2\x80\x94 Datalog capture, profiles, timeline replay.",
        tt::text_muted));

    // Keyboard shortcuts (compact version of the F1 cheat sheet).
    layout->addWidget(make_info_card(
        "Keyboard Shortcuts",
        "Alt+1..7  \xe2\x80\x94 Jump to tab\n"
        "Ctrl+K    \xe2\x80\x94 Command palette\n"
        "Ctrl+R    \xe2\x80\x94 Review staged changes\n"
        "Ctrl+W    \xe2\x80\x94 Write to RAM\n"
        "Ctrl+B    \xe2\x80\x94 Burn to Flash\n"
        "Ctrl+S    \xe2\x80\x94 Save tune\n"
        "Ctrl+O    \xe2\x80\x94 Open project\n"
        "F1 / ?    \xe2\x80\x94 Full shortcut cheat sheet\n"
        "F11       \xe2\x80\x94 Fullscreen dashboard\n"
        "+/-       \xe2\x80\x94 Increment/decrement table cells\n"
        "I / S / F \xe2\x80\x94 Interpolate / Smooth / Fill table selection",
        tt::accent_primary));

    // Native file formats.
    layout->addWidget(make_info_card(
        "File Formats",
        ".tuner      \xe2\x80\x94 Native tune file (JSON). All parameters + table data.\n"
        ".tunerdef   \xe2\x80\x94 Native definition (JSON). Describes every tunable parameter.\n"
        ".tunerproj  \xe2\x80\x94 Project metadata (JSON). Links definition + tune + settings.\n"
        ".ini        \xe2\x80\x94 Legacy Speeduino/TunerStudio definition. Import supported.\n"
        ".msq        \xe2\x80\x94 Legacy TunerStudio tune. Import supported.",
        tt::text_muted));

    layout->addStretch(1);
    scroll->setWidget(container);
    return scroll;
}
