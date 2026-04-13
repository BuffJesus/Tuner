// SPDX-License-Identifier: MIT
#include "tuner_core/hardware_setup_summary.hpp"

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <string>

namespace tuner_core::hardware_setup_summary {

namespace {

std::string to_lower(const std::string& s) {
    std::string r = s;
    for (auto& c : r) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return r;
}

using KW = std::vector<std::string>;

std::string line_for(const Page& page, ValueGetter& gv, const KW& keywords) {
    for (const auto& p : page.parameters) {
        std::string h = to_lower(p.name + " " + p.label);
        for (const auto& kw : keywords) {
            if (h.find(kw) != std::string::npos) {
                auto val = gv(p.name);
                if (val) {
                    char buf[128];
                    std::snprintf(buf, sizeof(buf), "%s: %.4g", p.label.c_str(), *val);
                    return buf;
                }
                return p.label + ": not set";
            }
        }
    }
    return {};
}

Card build_injector(const Page& page, ValueGetter& gv) {
    std::vector<std::string> details;
    auto flow = line_for(page, gv, {"injectorflow", "injflow", "flow"});
    auto dead = line_for(page, gv, {"deadtime", "injopen", "opentime"});
    auto req  = line_for(page, gv, {"reqfuel"});
    if (!flow.empty()) details.push_back(flow);
    if (!dead.empty()) details.push_back(dead);
    if (!req.empty())  details.push_back(req);

    std::string summary;
    if (details.size() >= 2) summary = details[0] + " | " + details[1];
    else if (!details.empty()) summary = details[0];
    else summary = "Review injector flow, dead time, and required fuel.";

    if (details.empty()) details.push_back("No injector parameters found on this page.");
    return {"injector", "Injector Setup", summary, details, "info"};
}

Card build_ignition(const Page& page, ValueGetter& gv) {
    std::vector<std::string> details;
    auto mode  = line_for(page, gv, {"sparkmode", "ignitionmode", "coil"});
    auto dwell = line_for(page, gv, {"dwell", "sparkdur"});
    auto angle = line_for(page, gv, {"timing", "advance", "fixang", "triggerangle"});
    if (!mode.empty())  details.push_back(mode);
    if (!dwell.empty()) details.push_back(dwell);
    if (!angle.empty()) details.push_back(angle);

    std::string summary;
    if (details.size() >= 2) summary = details[0] + " | " + details[1];
    else summary = "Verify coil mode, dwell, and timing before writing.";

    if (details.empty()) details.push_back("No ignition parameters found on this page.");
    return {"ignition", "Ignition Setup", summary, details, "info"};
}

Card build_trigger(const Page& page, ValueGetter& gv) {
    std::vector<std::string> details;
    auto pattern = line_for(page, gv, {"trigpattern", "decoder", "pattern"});
    auto teeth   = line_for(page, gv, {"nteeth", "toothcount", "crankteeth"});
    auto missing = line_for(page, gv, {"missingteeth", "missingtooth"});
    if (!pattern.empty()) details.push_back(pattern);
    if (!teeth.empty())   details.push_back(teeth);
    if (!missing.empty()) details.push_back(missing);

    std::string summary;
    if (details.size() >= 2) summary = details[0] + " | " + details[1];
    else summary = "Confirm wheel geometry and timing references.";

    if (details.empty()) details.push_back("No trigger parameters found on this page.");
    return {"trigger", "Trigger Setup", summary, details, "info"};
}

Card build_sensor(const Page& page, ValueGetter& gv) {
    std::vector<std::string> details;
    auto ego  = line_for(page, gv, {"egotype", "afrsensortype", "o2sensortype"});
    auto clt  = line_for(page, gv, {"clt", "coolant", "thermistor"});
    auto map_s = line_for(page, gv, {"mapmin", "mapmax", "mapsensor"});
    if (!ego.empty())  details.push_back(ego);
    if (!clt.empty())  details.push_back(clt);
    if (!map_s.empty()) details.push_back(map_s);

    std::string summary;
    if (!details.empty()) summary = details[0];
    else summary = "Confirm sensor types and calibrations.";

    if (details.empty()) details.push_back("No sensor parameters found on this page.");
    return {"sensor", "Sensor Setup", summary, details, "info"};
}

}  // namespace

std::vector<Card> build_cards(const Page& page, ValueGetter get_value) {
    std::vector<Card> cards;
    if (page.page_kind == "injector") cards.push_back(build_injector(page, get_value));
    else if (page.page_kind == "ignition") cards.push_back(build_ignition(page, get_value));
    else if (page.page_kind == "trigger") cards.push_back(build_trigger(page, get_value));
    else if (page.page_kind == "sensor") cards.push_back(build_sensor(page, get_value));
    else {
        // Generic: try all four.
        auto inj = build_injector(page, get_value);
        if (inj.detail_lines.size() > 1 || (inj.detail_lines.size() == 1 && inj.detail_lines[0].find("not found") == std::string::npos))
            cards.push_back(inj);
    }
    return cards;
}

}  // namespace tuner_core::hardware_setup_summary
