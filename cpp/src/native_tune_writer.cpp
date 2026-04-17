// SPDX-License-Identifier: MIT
#include "tuner_core/native_tune_writer.hpp"

#include <nlohmann/json.hpp>
#include <stdexcept>
#include <string>

namespace tuner_core::native_tune_writer {

namespace {

nlohmann::ordered_json value_to_json(const Value& v) {
    if (std::holds_alternative<double>(v))
        return std::get<double>(v);
    if (std::holds_alternative<std::string>(v))
        return std::get<std::string>(v);
    if (std::holds_alternative<std::vector<double>>(v)) {
        auto arr = nlohmann::ordered_json::array();
        for (double d : std::get<std::vector<double>>(v))
            arr.push_back(d);
        return arr;
    }
    return nullptr;
}

Value json_to_value(const nlohmann::json& j) {
    if (j.is_number()) return j.get<double>();
    if (j.is_string()) return j.get<std::string>();
    if (j.is_array()) {
        // Handle both flat [1, 2, ...] and nested [[row], [row], ...]
        // arrays — the improved .tuner format writes 2D tables as
        // array-of-rows for readability; flatten to a single vector.
        std::vector<double> vals;
        for (const auto& elem : j) {
            if (elem.is_array()) {
                for (const auto& cell : elem)
                    vals.push_back(cell.get<double>());
            } else if (elem.is_number()) {
                vals.push_back(elem.get<double>());
            }
        }
        return vals;
    }
    return 0.0;
}

}  // namespace

std::string export_json(const TunerTune& tune) {
    nlohmann::ordered_json j;
    j["format"] = tune.format;
    j["definition"] = tune.definition_signature;
    j["created"] = tune.created_iso;
    j["modified"] = tune.modified_iso;
    if (tune.slot_index.has_value()) j["slot_index"] = *tune.slot_index;
    if (tune.slot_name.has_value())  j["slot_name"]  = *tune.slot_name;
    if (tune.definition_hash.has_value())
        j["definition_hash"] = *tune.definition_hash;

    nlohmann::ordered_json values;
    for (const auto& [name, val] : tune.values)
        values[name] = value_to_json(val);
    j["values"] = values;

    if (tune.operator_context) {
        nlohmann::ordered_json ctx;
        const auto& c = *tune.operator_context;
        if (c.displacement_cc) ctx["displacement_cc"] = *c.displacement_cc;
        if (c.cylinder_count) ctx["cylinder_count"] = *c.cylinder_count;
        if (c.compression_ratio) ctx["compression_ratio"] = *c.compression_ratio;
        if (c.cam_duration_deg) ctx["cam_duration_deg"] = *c.cam_duration_deg;
        if (!c.head_flow_class.empty()) ctx["head_flow_class"] = c.head_flow_class;
        if (!c.intake_manifold_style.empty()) ctx["intake_manifold_style"] = c.intake_manifold_style;
        if (c.forced_induction_topology != generator_types::ForcedInductionTopology::NA)
            ctx["forced_induction"] = generator_types::topology_value_str(c.forced_induction_topology);
        j["operator_context"] = ctx;
    }

    return j.dump(2);
}

TunerTune import_json(const std::string& json_text) {
    nlohmann::json j;
    try { j = nlohmann::json::parse(json_text); }
    catch (...) { throw std::invalid_argument("Invalid .tuner JSON"); }

    if (!j.is_object()) throw std::invalid_argument("Root must be an object");

    TunerTune tune;
    tune.format = j.value("format", "tuner-tune-v1");
    tune.definition_signature = j.value("definition", "");
    tune.created_iso = j.value("created", "");
    tune.modified_iso = j.value("modified", "");

    if (j.contains("slot_index") && j["slot_index"].is_number_integer())
        tune.slot_index = j["slot_index"].get<int>();
    if (j.contains("slot_name") && j["slot_name"].is_string())
        tune.slot_name = j["slot_name"].get<std::string>();
    if (j.contains("definition_hash") && j["definition_hash"].is_string())
        tune.definition_hash = j["definition_hash"].get<std::string>();

    if (j.contains("values") && j["values"].is_object()) {
        for (auto& [key, val] : j["values"].items())
            tune.values.push_back({key, json_to_value(val)});
    }

    if (j.contains("operator_context") && j["operator_context"].is_object()) {
        auto& ctx_j = j["operator_context"];
        operator_engine_context::OperatorEngineContext ctx;
        if (ctx_j.contains("displacement_cc")) ctx.displacement_cc = ctx_j["displacement_cc"].get<double>();
        if (ctx_j.contains("cylinder_count")) ctx.cylinder_count = ctx_j["cylinder_count"].get<int>();
        if (ctx_j.contains("compression_ratio")) ctx.compression_ratio = ctx_j["compression_ratio"].get<double>();
        if (ctx_j.contains("cam_duration_deg")) ctx.cam_duration_deg = ctx_j["cam_duration_deg"].get<double>();
        if (ctx_j.contains("head_flow_class")) ctx.head_flow_class = ctx_j["head_flow_class"].get<std::string>();
        tune.operator_context = ctx;
    }

    return tune;
}

TunerTune from_edit_service(
    const local_tune_edit::EditService& edit,
    const std::string& definition_signature,
    const operator_engine_context::OperatorEngineContext* ctx)
{
    TunerTune tune;
    tune.definition_signature = definition_signature;
    tune.created_iso = "2026-04-10T00:00:00Z";
    tune.modified_iso = "2026-04-10T00:00:00Z";

    // get_all_values returns every value type (double, string,
    // vector<double>) with staged overlays applied. The prior
    // get_scalar_values_dict dropped strings and arrays — saving a
    // tune after editing one scalar silently lost all table data and
    // string-typed parameters.
    tune.values = edit.get_all_values();

    if (ctx) tune.operator_context = *ctx;
    return tune;
}

}  // namespace tuner_core::native_tune_writer
