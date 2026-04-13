// SPDX-License-Identifier: MIT
#include "tuner_core/dashboard_layout.hpp"

namespace tuner_core::dashboard_layout {

namespace {

Widget make_widget(const char* id, const char* kind, const char* title,
                    const char* source, const char* units,
                    double x, double y, double w, double h,
                    double lo, double hi,
                    std::vector<ColorZone> zones = {}) {
    Widget widget;
    widget.widget_id = id;
    widget.kind = kind;
    widget.title = title;
    widget.source = source;
    widget.units = units;
    widget.x = x;
    widget.y = y;
    widget.width = w;
    widget.height = h;
    widget.min_value = lo;
    widget.max_value = hi;
    widget.color_zones = std::move(zones);
    return widget;
}

}  // namespace

Layout default_layout() {
    Layout layout;
    layout.name = "Default Speeduino";
    layout.widgets.push_back(make_widget("rpm", "dial", "RPM", "rpm", "rpm",
        0, 0, 2, 2, 0, 8000,
        {{0, 3000, "ok"}, {3000, 6500, "warning"}, {6500, 8000, "danger"}}));
    layout.widgets.push_back(make_widget("map", "dial", "MAP", "map", "kPa",
        2, 0, 2, 2, 10, 260));
    layout.widgets.push_back(make_widget("tps", "bar", "TPS", "tps", "%",
        0, 2, 2, 1, 0, 100));
    layout.widgets.push_back(make_widget("afr", "number", "AFR", "afr", "AFR",
        2, 2, 1, 1, 10, 20,
        {{10, 11.5, "danger"}, {11.5, 13, "warning"}, {13, 16, "ok"},
         {16, 17, "warning"}, {17, 20, "danger"}}));
    layout.widgets.push_back(make_widget("advance", "number", "Advance", "advance", "deg",
        3, 2, 1, 1, -10, 45));
    layout.widgets.push_back(make_widget("clt", "number", "CLT", "clt", "\xc2\xb0""C",
        0, 3, 1, 1, -40, 130,
        {{-40, 0, "danger"}, {0, 70, "warning"}, {70, 100, "ok"},
         {100, 110, "warning"}, {110, 130, "danger"}}));
    layout.widgets.push_back(make_widget("iat", "number", "IAT", "iat", "\xc2\xb0""C",
        1, 3, 1, 1, -40, 80));
    layout.widgets.push_back(make_widget("batt", "number", "Battery", "batt", "V",
        2, 3, 1, 1, 8, 16,
        {{8, 11, "danger"}, {11, 12, "warning"}, {12, 15, "ok"},
         {15, 15.5, "warning"}, {15.5, 16, "danger"}}));
    layout.widgets.push_back(make_widget("pw1", "number", "PW1", "pw1", "ms",
        3, 3, 1, 1, 0, 25));
    layout.widgets.push_back(make_widget("dwell", "number", "Dwell", "dwell", "ms",
        0, 4, 1, 1, 0, 10,
        {{0, 5, "ok"}, {5, 7, "warning"}, {7, 10, "danger"}}));
    layout.widgets.push_back(make_widget("syncLoss", "number", "Sync Loss", "syncLossCounter", "count",
        1, 4, 1, 1, 0, 100,
        {{0, 1, "ok"}, {1, 5, "warning"}, {5, 100, "danger"}}));
    return layout;
}

}  // namespace tuner_core::dashboard_layout
