// SPDX-License-Identifier: MIT

#include "tabs/triggers_simulate_panel.hpp"

#include "theme.hpp"
#include "ui/styles.hpp"

#include "tuner_core/bench_simulator_config_codec.hpp"
#include "tuner_core/bench_simulator_controller.hpp"
#include "tuner_core/bench_simulator_wheel_pattern_catalog.hpp"
#include "tuner_core/transport.hpp"

#include <QCheckBox>
#include <QComboBox>
#include <QGridLayout>
#include <QGroupBox>
#include <QHBoxLayout>
#include <QLabel>
#include <QListWidget>
#include <QPushButton>
#include <QSlider>
#include <QSpinBox>
#include <QString>
#include <QTimer>
#include <QVBoxLayout>
#include <QWidget>

#include <cstdio>
#include <exception>
#include <memory>
#include <string>
#include <vector>

namespace tt   = tuner_theme;
namespace bs   = tuner_core::bench_simulator;
namespace ctrl = tuner_core::bench_simulator::controller;

// ---------------------------------------------------------------
// Local style helpers — keep token references inline so the panel
// matches the rest of the TRIGGERS tab visually.
// ---------------------------------------------------------------

namespace {

QString button_style(const char* accent) {
    char buf[512];
    std::snprintf(buf, sizeof(buf),
        "QPushButton { background: %s; border: 1px solid %s; "
        "border-radius: %dpx; padding: 6px 14px; "
        "color: %s; font-size: %dpx; font-weight: bold; } "
        "QPushButton:hover { background: %s; } "
        "QPushButton:disabled { background: %s; color: %s; border-color: %s; }",
        tt::bg_elevated, accent,
        tt::radius_sm, tt::text_primary, tt::font_body,
        tt::fill_primary_mid,
        tt::bg_elevated, tt::text_dim, tt::border);
    return QString::fromUtf8(buf);
}

QString combo_style() {
    char buf[256];
    std::snprintf(buf, sizeof(buf),
        "QComboBox { background: %s; color: %s; border: 1px solid %s; "
        "border-radius: %dpx; padding: 4px 8px; font-size: %dpx; }",
        tt::bg_elevated, tt::text_primary, tt::border,
        tt::radius_sm, tt::font_body);
    return QString::fromUtf8(buf);
}

QString chip_style(const char* fg, const char* bg, const char* border) {
    char buf[256];
    std::snprintf(buf, sizeof(buf),
        "QLabel { color: %s; background: %s; border: 1px solid %s; "
        "border-radius: %dpx; padding: 2px 8px; font-size: %dpx; }",
        fg, bg, border, tt::radius_sm, tt::font_small);
    return QString::fromUtf8(buf);
}

QString group_box_style() {
    char buf[256];
    std::snprintf(buf, sizeof(buf),
        "QGroupBox { color: %s; border: 1px solid %s; "
        "border-radius: %dpx; margin-top: 12px; padding-top: 8px; "
        "font-size: %dpx; font-weight: bold; } "
        "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }",
        tt::text_secondary, tt::border, tt::radius_sm, tt::font_small);
    return QString::fromUtf8(buf);
}

}  // namespace

// ---------------------------------------------------------------
// Panel state — owned via shared_ptr so every lambda capture sees
// the same transport, the same last-read config, and the same
// connection flag. Lambda lifetimes outlive any single button
// click, so by-value capture of the shared_ptr is the right
// pattern.
// ---------------------------------------------------------------

namespace {

struct SimState {
    std::unique_ptr<tuner_core::transport::SerialTransport> transport;
    bs::BenchSimulatorConfig last_config{};
    std::uint8_t  wire_version    = bs::kSchemaVersionV2;
    bool          connected       = false;
    std::uint8_t  cylinder_filter = 0;   // 0 = no filter; show every pattern
    std::size_t   current_wheel   = 0;
};

}  // namespace

QWidget* build_triggers_simulate_panel() {
    auto state = std::make_shared<SimState>();

    auto* card = new QWidget;
    {
        char cs[256];
        std::snprintf(cs, sizeof(cs),
            "QWidget { background: %s; border: 1px solid %s; "
            "border-radius: %dpx; }",
            tt::bg_panel, tt::border, tt::radius_sm);
        card->setStyleSheet(QString::fromUtf8(cs));
    }
    auto* layout = new QVBoxLayout(card);
    layout->setContentsMargins(tt::space_md, tt::space_md, tt::space_md, tt::space_md);
    layout->setSpacing(tt::space_sm + 2);

    // ----- 1. Header strip ----------------------------------------------
    {
        char hbuf[512];
        std::snprintf(hbuf, sizeof(hbuf),
            "<span style='font-size: %dpx; font-weight: bold; color: %s;'>"
            "Bench simulator</span> "
            "<span style='color: %s; font-size: %dpx;'>"
            "\xe2\x80\x94 drive an Ardu-stim crank/cam generator</span>",
            tt::font_label, tt::text_primary,
            tt::text_muted, tt::font_small);
        auto* hdr = new QLabel(QString::fromUtf8(hbuf));
        hdr->setTextFormat(Qt::RichText);
        layout->addWidget(hdr);
    }

    // ----- 2. Connection row --------------------------------------------
    auto* conn_row = new QHBoxLayout;
    conn_row->setSpacing(tt::space_sm);

    auto* port_combo = new QComboBox;
    port_combo->setStyleSheet(combo_style());
    for (const auto& p : list_serial_ports()) {
        port_combo->addItem(QString::fromStdString(p));
    }
    if (port_combo->count() == 0) port_combo->addItem(QString::fromUtf8("COM3"));

    auto* refresh_btn = new QPushButton(QString::fromUtf8("\xe2\x86\xbb"));
    refresh_btn->setToolTip(QString::fromUtf8("Refresh port list"));
    refresh_btn->setCursor(Qt::PointingHandCursor);
    refresh_btn->setFixedWidth(32);
    refresh_btn->setStyleSheet(button_style(tt::border));

    auto* connect_btn = new QPushButton(QString::fromUtf8("Connect"));
    connect_btn->setCursor(Qt::PointingHandCursor);
    connect_btn->setStyleSheet(button_style(tt::accent_ok));

    auto* fw_chip = new QLabel(QString::fromUtf8("not connected"));
    fw_chip->setStyleSheet(chip_style(tt::text_dim, tt::bg_elevated, tt::border));

    conn_row->addWidget(new QLabel(QString::fromUtf8("Port:")));
    conn_row->addWidget(port_combo);
    conn_row->addWidget(refresh_btn);
    conn_row->addWidget(connect_btn);
    conn_row->addWidget(fw_chip);
    conn_row->addStretch(1);
    layout->addLayout(conn_row);

    QObject::connect(refresh_btn, &QPushButton::clicked, [port_combo]() {
        auto current = port_combo->currentText();
        port_combo->clear();
        for (const auto& p : list_serial_ports()) {
            port_combo->addItem(QString::fromStdString(p));
        }
        if (port_combo->count() == 0) port_combo->addItem(QString::fromUtf8("COM3"));
        int idx = port_combo->findText(current);
        if (idx >= 0) port_combo->setCurrentIndex(idx);
    });

    // ----- 3. Cylinder filter chip strip -------------------------------
    auto* cyl_row = new QHBoxLayout;
    cyl_row->setSpacing(tt::space_sm);
    cyl_row->addWidget(new QLabel(QString::fromUtf8("Cylinders:")));

    auto* pattern_list = new QListWidget;  // forward-declare for filter closures
    {
        char ls[256];
        std::snprintf(ls, sizeof(ls),
            "QListWidget { background: %s; color: %s; border: 1px solid %s; "
            "border-radius: %dpx; font-size: %dpx; }",
            tt::bg_inset, tt::text_primary, tt::border, tt::radius_sm, tt::font_small);
        pattern_list->setStyleSheet(QString::fromUtf8(ls));
        pattern_list->setMinimumHeight(180);
    }

    auto refresh_pattern_list = [pattern_list, state]() {
        pattern_list->clear();
        std::vector<std::size_t> indices;
        if (state->cylinder_filter == 0) {
            indices.reserve(bs::kPatternCount);
            for (std::size_t i = 0; i < bs::kPatternCount; ++i) indices.push_back(i);
        } else {
            indices = bs::filter_by_cylinder_count(state->cylinder_filter);
        }
        for (auto idx : indices) {
            const auto& p = bs::patterns()[idx];
            char row[256];
            // Badge prefix shows decoder support: [S] [R] [SR] [--]
            const char* badge =
                (p.decoder_speeduino && p.decoder_rusefi) ? "[SR]"
                : p.decoder_speeduino ? "[S\xc2\xb7]"
                : p.decoder_rusefi    ? "[\xc2\xb7R]"
                : "[--]";
            std::snprintf(row, sizeof(row), "%s %s",
                          badge, std::string(p.friendly_name).c_str());
            auto* item = new QListWidgetItem(QString::fromUtf8(row));
            item->setData(Qt::UserRole, static_cast<qulonglong>(idx));
            pattern_list->addItem(item);
        }
    };

    for (std::uint8_t cyl : {0u, 4u, 6u, 8u, 10u, 12u}) {
        const char* label =
            cyl == 0 ? "All" :
            cyl == 4 ? "4" :
            cyl == 6 ? "6" :
            cyl == 8 ? "8" :
            cyl == 10 ? "10" : "12";
        auto* btn = new QPushButton(QString::fromUtf8(label));
        btn->setCursor(Qt::PointingHandCursor);
        btn->setCheckable(true);
        if (cyl == state->cylinder_filter) btn->setChecked(true);
        btn->setStyleSheet(button_style(cyl == state->cylinder_filter ? tt::accent_primary : tt::border));
        btn->setFixedWidth(40);

        // Capture-by-value of cyl so each chip remembers its own count.
        std::uint8_t cyl_v = cyl;
        QObject::connect(btn, &QPushButton::clicked,
                         [btn, cyl_v, state, refresh_pattern_list, cyl_row]() {
            state->cylinder_filter = cyl_v;
            refresh_pattern_list();
            // Visually un-toggle siblings; uncheck-then-recheck pattern.
            for (int i = 0; i < cyl_row->count(); ++i) {
                if (auto* w = cyl_row->itemAt(i)->widget()) {
                    if (auto* b = qobject_cast<QPushButton*>(w)) {
                        b->setChecked(b == btn);
                        b->setStyleSheet(button_style(b == btn ? tt::accent_primary : tt::border));
                    }
                }
            }
        });
        cyl_row->addWidget(btn);
    }
    cyl_row->addStretch(1);
    layout->addLayout(cyl_row);

    // ----- 4. Pattern picker --------------------------------------------
    layout->addWidget(pattern_list);
    refresh_pattern_list();

    // ----- 5. RPM controls (fixed + sweep) ------------------------------
    auto* rpm_group = new QGroupBox(QString::fromUtf8("RPM control"));
    rpm_group->setStyleSheet(group_box_style());
    auto* rpm_layout = new QVBoxLayout(rpm_group);
    rpm_layout->setSpacing(tt::space_sm);

    // 5a. Fixed RPM row
    auto* fixed_row = new QHBoxLayout;
    fixed_row->addWidget(new QLabel(QString::fromUtf8("Fixed:")));
    auto* fixed_slider = new QSlider(Qt::Horizontal);
    fixed_slider->setRange(200, 9000);  // TMP_RPM_CAP = 9000 per globals.h
    fixed_slider->setValue(2500);
    fixed_slider->setSingleStep(50);
    fixed_slider->setPageStep(500);
    auto* fixed_spin = new QSpinBox;
    fixed_spin->setRange(200, 9000);
    fixed_spin->setValue(2500);
    fixed_spin->setSuffix(QString::fromUtf8(" RPM"));
    fixed_spin->setFixedWidth(110);
    QObject::connect(fixed_slider, &QSlider::valueChanged, fixed_spin, &QSpinBox::setValue);
    QObject::connect(fixed_spin, qOverload<int>(&QSpinBox::valueChanged),
                     fixed_slider, &QSlider::setValue);
    fixed_row->addWidget(fixed_slider, 1);
    fixed_row->addWidget(fixed_spin);
    rpm_layout->addLayout(fixed_row);

    // 5b. Sweep row
    auto* sweep_row = new QHBoxLayout;
    sweep_row->addWidget(new QLabel(QString::fromUtf8("Sweep:")));
    auto* sweep_lo = new QSpinBox;
    sweep_lo->setRange(0, 9000);
    sweep_lo->setValue(250);
    sweep_lo->setPrefix(QString::fromUtf8("lo "));
    sweep_lo->setFixedWidth(110);
    auto* sweep_hi = new QSpinBox;
    sweep_hi->setRange(0, 9000);
    sweep_hi->setValue(4000);
    sweep_hi->setPrefix(QString::fromUtf8("hi "));
    sweep_hi->setFixedWidth(110);
    auto* sweep_int = new QSpinBox;
    sweep_int->setRange(0, 60000);
    sweep_int->setValue(1000);
    sweep_int->setSuffix(QString::fromUtf8(" ms"));
    sweep_int->setFixedWidth(110);
    sweep_row->addWidget(sweep_lo);
    sweep_row->addWidget(sweep_hi);
    sweep_row->addWidget(sweep_int);
    sweep_row->addStretch(1);
    rpm_layout->addLayout(sweep_row);

    // 5c. Apply buttons
    auto* apply_row = new QHBoxLayout;
    auto* apply_fixed_btn  = new QPushButton(QString::fromUtf8("Apply fixed"));
    auto* apply_sweep_btn  = new QPushButton(QString::fromUtf8("Apply sweep"));
    auto* set_wheel_btn    = new QPushButton(QString::fromUtf8("Apply wheel"));
    apply_fixed_btn->setCursor(Qt::PointingHandCursor);
    apply_sweep_btn->setCursor(Qt::PointingHandCursor);
    set_wheel_btn->setCursor(Qt::PointingHandCursor);
    apply_fixed_btn->setStyleSheet(button_style(tt::accent_primary));
    apply_sweep_btn->setStyleSheet(button_style(tt::accent_primary));
    set_wheel_btn->setStyleSheet(button_style(tt::accent_primary));
    apply_fixed_btn->setEnabled(false);
    apply_sweep_btn->setEnabled(false);
    set_wheel_btn->setEnabled(false);
    apply_row->addWidget(apply_fixed_btn);
    apply_row->addWidget(apply_sweep_btn);
    apply_row->addWidget(set_wheel_btn);
    apply_row->addStretch(1);
    rpm_layout->addLayout(apply_row);

    layout->addWidget(rpm_group);

    // ----- 6. Compression-cycle card (v2 only) --------------------------
    auto* comp_group = new QGroupBox(QString::fromUtf8("Compression simulator (v2 firmware)"));
    comp_group->setStyleSheet(group_box_style());
    auto* comp_layout = new QGridLayout(comp_group);
    comp_layout->setColumnStretch(3, 1);

    auto* comp_enable = new QCheckBox(QString::fromUtf8("Enable"));
    auto* comp_type_combo = new QComboBox;
    comp_type_combo->setStyleSheet(combo_style());
    comp_type_combo->addItem(QString::fromUtf8("2-cyl 4-stroke"),
                              static_cast<int>(bs::CompressionType::CYL2_4STROKE));
    comp_type_combo->addItem(QString::fromUtf8("4-cyl 4-stroke"),
                              static_cast<int>(bs::CompressionType::CYL4_4STROKE));
    comp_type_combo->addItem(QString::fromUtf8("6-cyl 4-stroke"),
                              static_cast<int>(bs::CompressionType::CYL6_4STROKE));
    comp_type_combo->addItem(QString::fromUtf8("8-cyl 4-stroke"),
                              static_cast<int>(bs::CompressionType::CYL8_4STROKE));
    comp_type_combo->setCurrentIndex(3);  // default to 8-cyl (the headline use case)

    auto* comp_rpm = new QSpinBox;
    comp_rpm->setRange(0, 9000);
    comp_rpm->setValue(400);
    comp_rpm->setSuffix(QString::fromUtf8(" RPM"));
    auto* comp_offset = new QSpinBox;
    comp_offset->setRange(0, 9000);
    comp_offset->setValue(0);
    auto* comp_dynamic = new QCheckBox(QString::fromUtf8("Dynamic"));

    auto* apply_comp_btn = new QPushButton(QString::fromUtf8("Apply compression"));
    apply_comp_btn->setCursor(Qt::PointingHandCursor);
    apply_comp_btn->setStyleSheet(button_style(tt::accent_primary));
    apply_comp_btn->setEnabled(false);

    comp_layout->addWidget(comp_enable,                       0, 0);
    comp_layout->addWidget(new QLabel(QString::fromUtf8("Type:")),   0, 1);
    comp_layout->addWidget(comp_type_combo,                          0, 2);
    comp_layout->addWidget(new QLabel(QString::fromUtf8("Target:")), 1, 0);
    comp_layout->addWidget(comp_rpm,                                 1, 1);
    comp_layout->addWidget(new QLabel(QString::fromUtf8("Offset:")), 1, 2);
    comp_layout->addWidget(comp_offset,                              1, 3);
    comp_layout->addWidget(comp_dynamic,                             2, 0);
    comp_layout->addWidget(apply_comp_btn,                           2, 1, 1, 2);

    layout->addWidget(comp_group);
    comp_group->setEnabled(false);  // enabled only after v2 firmware detected

    // ----- 7. Save to EEPROM + status row -------------------------------
    auto* save_row = new QHBoxLayout;
    auto* save_btn = new QPushButton(QString::fromUtf8("Save to EEPROM (s)"));
    save_btn->setCursor(Qt::PointingHandCursor);
    save_btn->setToolTip(QString::fromUtf8(
        "Persist current firmware config across power-cycle"));
    save_btn->setStyleSheet(button_style(tt::accent_warning));
    save_btn->setEnabled(false);

    auto* live_status = new QLabel(QString::fromUtf8(""));
    live_status->setStyleSheet(chip_style(tt::text_secondary, tt::bg_elevated, tt::border));

    save_row->addWidget(save_btn);
    save_row->addStretch(1);
    save_row->addWidget(live_status);
    layout->addLayout(save_row);

    // ----- Helpers ------------------------------------------------------

    auto set_enabled_action_buttons = [=](bool on) {
        apply_fixed_btn->setEnabled(on);
        apply_sweep_btn->setEnabled(on);
        set_wheel_btn->setEnabled(on);
        save_btn->setEnabled(on);
        // Compression card stays in v2-only mode.
        if (state->wire_version == bs::kSchemaVersionV2) {
            comp_group->setEnabled(on);
            apply_comp_btn->setEnabled(on);
        } else {
            comp_group->setEnabled(false);
        }
    };

    auto refresh_fw_chip = [=]() {
        if (!state->connected) {
            fw_chip->setText(QString::fromUtf8("not connected"));
            fw_chip->setStyleSheet(chip_style(tt::text_dim, tt::bg_elevated, tt::border));
            return;
        }
        char buf[64];
        std::snprintf(buf, sizeof(buf), "firmware v%u", state->wire_version);
        fw_chip->setText(QString::fromUtf8(buf));
        fw_chip->setStyleSheet(chip_style(tt::accent_ok, tt::bg_elevated, tt::accent_ok));
    };

    // ----- Connect / disconnect lifecycle -------------------------------
    // Capture state by value (shared_ptr copies cheaply). The `=`
    // default captures every other widget pointer and `state` together;
    // no `&state` ref because `state` is local and the lambda outlives
    // this function.
    QObject::connect(connect_btn, &QPushButton::clicked,
                     [=]() {
        if (state->connected) {
            // Disconnect path.
            if (state->transport) state->transport->close();
            state->transport.reset();
            state->connected = false;
            connect_btn->setText(QString::fromUtf8("Connect"));
            connect_btn->setStyleSheet(button_style(tt::accent_ok));
            set_enabled_action_buttons(false);
            live_status->setText(QString::fromUtf8(""));
            refresh_fw_chip();
            return;
        }

        // Connect path.
        auto port = port_combo->currentText().toStdString();
        try {
            state->transport = std::make_unique<tuner_core::transport::SerialTransport>(
                port, static_cast<int>(bs::kBaudRate));
            state->transport->open();
            state->transport->clear_buffers();
        } catch (const std::exception& e) {
            char err[256];
            std::snprintf(err, sizeof(err), "connect failed: %s", e.what());
            fw_chip->setText(QString::fromUtf8(err));
            fw_chip->setStyleSheet(chip_style(tt::accent_danger, tt::bg_elevated, tt::accent_danger));
            state->transport.reset();
            return;
        }

        // First-read sniff: pull current config, detect schema version.
        auto cfg = ctrl::read_config(*state->transport, 0.5);
        if (!cfg.has_value()) {
            fw_chip->setText(QString::fromUtf8("no response — wrong port?"));
            fw_chip->setStyleSheet(chip_style(tt::accent_warning, tt::bg_elevated, tt::accent_warning));
            state->transport->close();
            state->transport.reset();
            return;
        }
        state->last_config  = *cfg;
        state->wire_version = cfg->version;
        state->current_wheel = cfg->wheel;
        state->connected     = true;

        connect_btn->setText(QString::fromUtf8("Disconnect"));
        connect_btn->setStyleSheet(button_style(tt::accent_danger));
        set_enabled_action_buttons(true);
        refresh_fw_chip();

        // Reflect firmware state in the controls.
        fixed_slider->setValue(cfg->fixed_rpm);
        fixed_spin->setValue(cfg->fixed_rpm);
        sweep_lo->setValue(cfg->sweep_low_rpm);
        sweep_hi->setValue(cfg->sweep_high_rpm);
        sweep_int->setValue(cfg->sweep_interval);
        if (state->wire_version == bs::kSchemaVersionV2) {
            comp_enable->setChecked(cfg->use_compression);
            int ct_idx = comp_type_combo->findData(
                static_cast<int>(cfg->compression_type));
            if (ct_idx >= 0) comp_type_combo->setCurrentIndex(ct_idx);
            comp_rpm->setValue(cfg->compression_rpm);
            comp_offset->setValue(cfg->compression_offset);
            comp_dynamic->setChecked(cfg->compression_dynamic);
        }
        // Highlight the firmware's currently-selected pattern in the list.
        for (int i = 0; i < pattern_list->count(); ++i) {
            auto* it = pattern_list->item(i);
            if (it->data(Qt::UserRole).toULongLong() ==
                static_cast<qulonglong>(cfg->wheel)) {
                pattern_list->setCurrentRow(i);
                break;
            }
        }
    });

    // ----- Apply-wheel button -------------------------------------------
    QObject::connect(set_wheel_btn, &QPushButton::clicked, [=]() {
        if (!state->connected || !state->transport) return;
        auto* it = pattern_list->currentItem();
        if (!it) return;
        auto idx = static_cast<std::uint8_t>(it->data(Qt::UserRole).toULongLong());
        try {
            ctrl::set_wheel(*state->transport, idx);
            state->current_wheel = idx;
        } catch (...) {
            // Silent on transport hiccup; chip will reflect on next poll.
        }
    });

    // ----- Apply-fixed-RPM button ---------------------------------------
    QObject::connect(apply_fixed_btn, &QPushButton::clicked, [=]() {
        if (!state->connected || !state->transport) return;
        auto cfg = state->last_config;
        cfg.mode      = bs::RpmMode::FIXED_RPM;
        cfg.fixed_rpm = static_cast<std::uint16_t>(fixed_spin->value());
        try {
            ctrl::send_config(*state->transport, cfg, state->wire_version);
            state->last_config = cfg;
        } catch (...) {}
    });

    // ----- Apply-sweep button -------------------------------------------
    QObject::connect(apply_sweep_btn, &QPushButton::clicked, [=]() {
        if (!state->connected || !state->transport) return;
        auto lo  = static_cast<std::uint16_t>(sweep_lo->value());
        auto hi  = static_cast<std::uint16_t>(sweep_hi->value());
        auto it_ = static_cast<std::uint16_t>(sweep_int->value());
        try {
            ctrl::set_sweep(*state->transport, lo, hi, it_);
            state->last_config.mode           = bs::RpmMode::LINEAR_SWEPT_RPM;
            state->last_config.sweep_low_rpm  = lo;
            state->last_config.sweep_high_rpm = hi;
            state->last_config.sweep_interval = it_;
        } catch (...) {}
    });

    // ----- Apply-compression button -------------------------------------
    QObject::connect(apply_comp_btn, &QPushButton::clicked, [=]() {
        if (!state->connected || !state->transport) return;
        if (state->wire_version != bs::kSchemaVersionV2) return;
        auto cfg = state->last_config;
        cfg.use_compression    = comp_enable->isChecked();
        cfg.compression_type   = static_cast<bs::CompressionType>(
            comp_type_combo->currentData().toInt());
        cfg.compression_rpm    = static_cast<std::uint16_t>(comp_rpm->value());
        cfg.compression_offset = static_cast<std::uint16_t>(comp_offset->value());
        cfg.compression_dynamic = comp_dynamic->isChecked();
        try {
            ctrl::send_config(*state->transport, cfg, state->wire_version);
            state->last_config = cfg;
        } catch (...) {}
    });

    // ----- Save-to-EEPROM button ----------------------------------------
    QObject::connect(save_btn, &QPushButton::clicked, [=]() {
        if (!state->connected || !state->transport) return;
        try {
            ctrl::save_to_eeprom(*state->transport);
        } catch (...) {}
    });

    // ----- Polling timer — live RPM + current wheel name ----------------
    auto* poll = new QTimer(card);
    QObject::connect(poll, &QTimer::timeout, [=]() {
        if (!state->connected || !state->transport) return;
        auto rpm = ctrl::read_current_rpm(*state->transport, 0.15);
        if (rpm.has_value()) {
            const auto& p = bs::patterns()[state->current_wheel];
            char buf[160];
            std::snprintf(buf, sizeof(buf),
                          "%s \xc2\xb7 %u RPM",
                          std::string(p.friendly_name).c_str(),
                          static_cast<unsigned>(*rpm));
            live_status->setText(QString::fromUtf8(buf));
            live_status->setStyleSheet(
                chip_style(tt::accent_ok, tt::bg_elevated, tt::accent_ok));
        }
    });
    poll->start(500);

    return card;
}
