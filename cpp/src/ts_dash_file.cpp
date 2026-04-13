// SPDX-License-Identifier: MIT
//
// Hand-rolled XML scanner for TSDash .dash files — same approach as
// the MSQ parser (no third-party XML library).  The .dash format is
// simple enough that a line scanner handles it well.

#include "tuner_core/ts_dash_file.hpp"

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>

namespace tuner_core::ts_dash_file {

namespace dl = tuner_core::dashboard_layout;

namespace {

std::string strip(const std::string& s) {
    auto a = s.find_first_not_of(" \t\r\n");
    if (a == std::string::npos) return {};
    return s.substr(a, s.find_last_not_of(" \t\r\n") - a + 1);
}

std::string to_lower(const std::string& s) {
    std::string r = s;
    for (auto& c : r) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return r;
}

double to_double(const std::string& s, double fallback) {
    try { return std::stod(s); } catch (...) { return fallback; }
}

// Strip XML namespace prefix from a tag: "{http://...}foo" → "foo".
std::string local_tag(const std::string& tag) {
    auto pos = tag.find('}');
    return (pos != std::string::npos) ? tag.substr(pos + 1) : tag;
}

// Simple XML attribute extractor — finds attr="value" in a tag string.
std::string attr_value(const std::string& tag_text, const std::string& attr_name) {
    std::string key = attr_name + "=\"";
    auto pos = tag_text.find(key);
    if (pos == std::string::npos) return {};
    pos += key.size();
    auto end = tag_text.find('"', pos);
    return (end != std::string::npos) ? tag_text.substr(pos, end - pos) : "";
}

// Map TSDash FQN class names to our widget kinds.
std::string kind_from_type(const std::string& type_fqn) {
    if (type_fqn.find("Gauge") != std::string::npos) return "dial";
    if (type_fqn.find("Indicator") != std::string::npos) return "indicator";
    if (type_fqn.find("DashLabel") != std::string::npos) return "label";
    if (type_fqn.find("HtmlDisplay") != std::string::npos) return "html";
    // Fallback: lowercased simple class name.
    auto dot = type_fqn.rfind('.');
    std::string simple = (dot != std::string::npos) ? type_fqn.substr(dot + 1) : type_fqn;
    return to_lower(simple);
}

std::string type_from_kind(const std::string& kind) {
    if (kind == "dial") return "com.efiAnalytics.apps.ts.dashboard.Gauge";
    if (kind == "indicator") return "com.efiAnalytics.apps.ts.dashboard.Indicator";
    if (kind == "label") return "com.efiAnalytics.apps.ts.dashboard.DashLabel";
    if (kind == "html") return "com.efiAnalytics.apps.ts.dashboard.HtmlDisplay";
    return "com.efiAnalytics.apps.ts.dashboard.Gauge";
}

// Slugify a title to make a widget ID.
std::string slugify(const std::string& s, int fallback_index) {
    std::string r;
    for (char c : s) {
        if (std::isalnum(static_cast<unsigned char>(c)))
            r += static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
        else if (!r.empty() && r.back() != '_')
            r += '_';
    }
    while (!r.empty() && r.back() == '_') r.pop_back();
    if (r.empty()) r = "widget_" + std::to_string(fallback_index);
    return r;
}

}  // namespace

// -----------------------------------------------------------------------
// parse_text — line-scanner approach
// -----------------------------------------------------------------------

dl::Layout parse_text(const std::string& xml_text) {
    // Look for <gaugeCluster> and <dashComp> elements.
    std::istringstream stream(xml_text);
    std::string line;

    std::string layout_name = "Imported Dashboard";
    std::vector<dl::Widget> widgets;

    bool in_dashcomp = false;
    std::string comp_type;
    std::map<std::string, std::string> comp_fields;
    int widget_index = 0;

    while (std::getline(stream, line)) {
        std::string trimmed = strip(line);

        // firmwareSignature in <versionInfo>
        if (trimmed.find("versionInfo") != std::string::npos) {
            auto sig = attr_value(trimmed, "firmwareSignature");
            if (!sig.empty()) layout_name = sig;
        }

        // <dashComp type="...">
        if (trimmed.find("<dashComp") != std::string::npos ||
            trimmed.find("<dsh:dashComp") != std::string::npos ||
            trimmed.find(":dashComp") != std::string::npos) {
            in_dashcomp = true;
            comp_type = attr_value(trimmed, "type");
            comp_fields.clear();
            continue;
        }

        // </dashComp>
        if (in_dashcomp && (trimmed.find("</dashComp") != std::string::npos ||
                            trimmed.find("</dsh:dashComp") != std::string::npos ||
                            (trimmed.find("/dashComp") != std::string::npos))) {
            in_dashcomp = false;

            // Build widget from accumulated fields.
            std::string kind = kind_from_type(comp_type);
            std::string title = comp_fields["Title"];
            std::string wid = slugify(title.empty() ? ("widget_" + std::to_string(widget_index)) : title, widget_index);

            double warn = to_double(comp_fields["HighWarning"], 0);
            double crit = to_double(comp_fields["HighCritical"], 0);
            double max_val = to_double(comp_fields["Max"], 100);
            std::vector<dl::ColorZone> zones;
            if (warn > 0 && warn < max_val)
                zones.push_back({warn, (crit > warn) ? crit : max_val, "warning"});
            if (crit > 0 && crit < max_val)
                zones.push_back({crit, max_val, "danger"});

            dl::Widget w;
            w.widget_id = wid;
            w.kind = kind;
            w.title = title.empty() ? wid : title;
            w.source = comp_fields["OutputChannel"];
            w.units = comp_fields["Units"];
            w.x = to_double(comp_fields["RelativeX"], 0);
            w.y = to_double(comp_fields["RelativeY"], 0);
            w.width = to_double(comp_fields["RelativeWidth"], 0.1);
            w.height = to_double(comp_fields["RelativeHeight"], 0.1);
            w.min_value = to_double(comp_fields["Min"], 0);
            w.max_value = max_val;
            w.color_zones = zones;
            widgets.push_back(std::move(w));
            ++widget_index;
            continue;
        }

        // Inside a dashComp: extract child element values.
        // Format: <FieldName type="...">value</FieldName>
        if (in_dashcomp && trimmed.size() > 2 && trimmed[0] == '<' && trimmed[1] != '/') {
            // Extract tag name.
            auto gt = trimmed.find('>');
            if (gt == std::string::npos) continue;
            auto tag_end = trimmed.find(' ');
            if (tag_end == std::string::npos || tag_end > gt) tag_end = gt;
            std::string tag = trimmed.substr(1, tag_end - 1);
            // Strip namespace prefix.
            auto colon = tag.find(':');
            if (colon != std::string::npos) tag = tag.substr(colon + 1);
            // Extract text content.
            auto close = trimmed.find('<', gt);
            if (close != std::string::npos) {
                std::string text = strip(trimmed.substr(gt + 1, close - gt - 1));
                comp_fields[tag] = text;
            }
        }
    }

    dl::Layout layout;
    layout.name = layout_name;
    layout.widgets = std::move(widgets);
    return layout;
}

// -----------------------------------------------------------------------
// export_text
// -----------------------------------------------------------------------

std::string export_text(const dl::Layout& layout) {
    std::string out;
    out += "<dsh xmlns=\"http://www.EFIAnalytics.com/:dsh\">\n";
    out += "  <bibliography author=\"Tuner\" company=\"Tuner\" writeDate=\"2026-04-10\"/>\n";
    char sig[256];
    std::snprintf(sig, sizeof(sig),
        "  <versionInfo fileFormat=\"3.0\" firmwareSignature=\"%s\"/>\n",
        layout.name.c_str());
    out += sig;
    out += "  <gaugeCluster clusterBackgroundColor=\"-16777216\" antiAliasing=\"true\">\n";

    for (const auto& w : layout.widgets) {
        std::string fqn = type_from_kind(w.kind);
        char buf[1024];
        std::snprintf(buf, sizeof(buf),
            "    <dashComp type=\"%s\">\n"
            "      <RelativeX type=\"double\">%.4f</RelativeX>\n"
            "      <RelativeY type=\"double\">%.4f</RelativeY>\n"
            "      <RelativeWidth type=\"double\">%.4f</RelativeWidth>\n"
            "      <RelativeHeight type=\"double\">%.4f</RelativeHeight>\n"
            "      <Title type=\"String\">%s</Title>\n"
            "      <Units type=\"String\">%s</Units>\n"
            "      <Min type=\"double\">%.1f</Min>\n"
            "      <Max type=\"double\">%.1f</Max>\n",
            fqn.c_str(), w.x, w.y, w.width, w.height,
            w.title.c_str(), w.units.c_str(), w.min_value, w.max_value);
        out += buf;

        double warn_lo = 0, crit_lo = 0;
        for (const auto& z : w.color_zones) {
            if (z.color == "warning") warn_lo = z.lo;
            if (z.color == "danger") crit_lo = z.lo;
        }
        std::snprintf(buf, sizeof(buf),
            "      <LowWarning type=\"double\">0.0</LowWarning>\n"
            "      <HighWarning type=\"double\">%.1f</HighWarning>\n"
            "      <LowCritical type=\"double\">0.0</LowCritical>\n"
            "      <HighCritical type=\"double\">%.1f</HighCritical>\n"
            "      <OutputChannel type=\"String\">%s</OutputChannel>\n"
            "    </dashComp>\n",
            warn_lo, crit_lo, w.source.c_str());
        out += buf;
    }

    out += "  </gaugeCluster>\n";
    out += "</dsh>\n";
    return out;
}

}  // namespace tuner_core::ts_dash_file
