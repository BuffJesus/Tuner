// SPDX-License-Identifier: MIT

#include "ui/styles.hpp"

#include <QFont>
#include <QLabel>
#include <QString>
#include <QVBoxLayout>
#include <QWidget>

#include <cstdio>

namespace tt = tuner_theme;

QLabel* make_tab_header(const char* title, const char* breadcrumb) {
    char html[512];
    tt::format_tab_header_html(html, sizeof(html), title, breadcrumb);
    auto* label = new QLabel(QString::fromUtf8(html));
    label->setTextFormat(Qt::RichText);
    label->setStyleSheet(QString::fromUtf8(tt::tab_header_style().c_str()));
    return label;
}

QWidget* make_info_card(const char* heading, const char* body,
                         const char* accent_color) {
    auto* w = new QWidget;
    auto* l = new QVBoxLayout(w);
    // Use elevated bg (not bg_panel) so info cards read as a tier above
    // regular content containers — matches their role as "attention
    // please" surfaces the operator should read before acting.
    l->setContentsMargins(tt::space_md + 2, tt::space_md, tt::space_md + 2, tt::space_md);
    l->setSpacing(tt::space_xs + 2);
    char style[256];
    std::snprintf(style, sizeof(style),
        "background-color: %s; border: 1px solid %s; "
        "border-left: 3px solid %s; border-radius: %dpx;",
        tt::bg_elevated, tt::border, accent_color, tt::radius_md);
    w->setStyleSheet(QString::fromUtf8(style));

    auto* h = new QLabel(QString::fromUtf8(heading));
    QFont hf = h->font();
    hf.setBold(true);
    hf.setPixelSize(tt::font_label);
    h->setFont(hf);
    char heading_style[96];
    std::snprintf(heading_style, sizeof(heading_style),
        "color: %s; border: none;", tt::text_primary);
    h->setStyleSheet(QString::fromUtf8(heading_style));
    l->addWidget(h);

    auto* b = new QLabel(QString::fromUtf8(body));
    b->setWordWrap(true);
    char body_style[96];
    std::snprintf(body_style, sizeof(body_style),
        "color: %s; border: none; font-size: %dpx;",
        tt::text_secondary, tt::font_body);
    b->setStyleSheet(QString::fromUtf8(body_style));
    l->addWidget(b);
    return w;
}
