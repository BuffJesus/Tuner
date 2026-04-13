// SPDX-License-Identifier: MIT
#include "tuner_core/native_definition_writer.hpp"

#include <nlohmann/json.hpp>
#include <string>

namespace tuner_core::native_definition_writer {

std::string export_json(const NativeEcuDefinition& def,
                         const std::string& firmware_name,
                         const std::string& version)
{
    nlohmann::ordered_json j;
    j["format"] = "tuner-definition-v1";
    j["firmware"] = firmware_name;
    if (!version.empty()) j["version"] = version;

    // Scalars.
    nlohmann::ordered_json scalars;
    for (const auto& s : def.constants.scalars) {
        nlohmann::ordered_json sc;
        sc["title"] = s.name;
        sc["type"] = s.data_type;
        if (s.units) sc["units"] = *s.units;
        if (s.min_value) sc["min"] = *s.min_value;
        if (s.max_value) sc["max"] = *s.max_value;
        if (s.digits) sc["digits"] = *s.digits;
        scalars[s.name] = sc;
    }
    j["scalars"] = scalars;

    // Tables (from table editors — the semantic view).
    nlohmann::ordered_json tables;
    for (const auto& ed : def.table_editors.editors) {
        nlohmann::ordered_json t;
        t["title"] = ed.title.empty() ? ed.table_id : ed.title;
        if (ed.z_bins) t["data"] = *ed.z_bins;
        if (ed.x_bins) {
            nlohmann::ordered_json xa;
            xa["source"] = *ed.x_bins;
            if (ed.x_label) xa["label"] = *ed.x_label;
            t["x_axis"] = xa;
        }
        if (ed.y_bins) {
            nlohmann::ordered_json ya;
            ya["source"] = *ed.y_bins;
            if (ed.y_label) ya["label"] = *ed.y_label;
            t["y_axis"] = ya;
        }
        // Find dimensions from arrays.
        for (const auto& arr : def.constants.arrays) {
            if (ed.z_bins && arr.name == *ed.z_bins) {
                t["rows"] = arr.rows;
                t["cols"] = arr.columns;
                break;
            }
        }
        tables[ed.table_id] = t;
    }
    j["tables"] = tables;

    // Curves.
    nlohmann::ordered_json curves;
    for (const auto& ce : def.curve_editors.curves) {
        nlohmann::ordered_json c;
        c["title"] = ce.title;
        c["x_bins"] = ce.x_bins_param;
        c["x_label"] = ce.x_label;
        c["y_label"] = ce.y_label;
        nlohmann::ordered_json ybins = nlohmann::ordered_json::array();
        for (const auto& yb : ce.y_bins_list)
            ybins.push_back(yb.param);
        c["y_bins"] = ybins;
        curves[ce.name] = c;
    }
    j["curves"] = curves;

    // Summary stats.
    nlohmann::ordered_json stats;
    stats["scalar_count"] = static_cast<int>(def.constants.scalars.size());
    stats["array_count"] = static_cast<int>(def.constants.arrays.size());
    stats["table_editor_count"] = static_cast<int>(def.table_editors.editors.size());
    stats["curve_count"] = static_cast<int>(def.curve_editors.curves.size());
    j["stats"] = stats;

    return j.dump(2);
}

std::string validate_json(const std::string& json_text) {
    try {
        auto j = nlohmann::json::parse(json_text);
        if (!j.is_object()) return "Root must be an object";
        if (!j.contains("format")) return "Missing 'format' field";
        if (j["format"] != "tuner-definition-v1") return "Unknown format: " + j["format"].get<std::string>();
        return "";
    } catch (const std::exception& e) {
        return std::string("JSON parse error: ") + e.what();
    }
}

}  // namespace tuner_core::native_definition_writer
