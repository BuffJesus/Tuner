// SPDX-License-Identifier: MIT
//
// tuner_core::NativeFormat implementation. Uses nlohmann/json (vendored
// single-header at cpp/third_party/nlohmann/json.hpp). Field ordering
// in the emitted JSON matches the Python `dataclasses.asdict()` order
// of `NativeDefinition`/`NativeTune` so the parity harness can compare
// byte-for-byte against the Python serializer.

#include "tuner_core/native_format.hpp"

#include "nlohmann/json.hpp"

#include <fstream>
#include <sstream>

namespace tuner_core {

namespace {

using json = nlohmann::ordered_json;

// JSON5 preprocessor — strips features that nlohmann/json can't parse:
//   - // line comments
//   - /* block comments */
//   - trailing commas before ] and }
// This lets us accept JSON5 input without a separate parser library.
// The output is valid strict JSON that nlohmann/json can parse.
std::string strip_json5(std::string_view input) {
    std::string out;
    out.reserve(input.size());
    std::size_t i = 0;
    bool in_string = false;
    while (i < input.size()) {
        char c = input[i];
        // Track string boundaries (skip escaped quotes).
        if (c == '"' && (i == 0 || input[i - 1] != '\\')) {
            in_string = !in_string;
            out += c;
            ++i;
            continue;
        }
        if (in_string) {
            out += c;
            ++i;
            continue;
        }
        // Line comment: // ... \n
        if (c == '/' && i + 1 < input.size() && input[i + 1] == '/') {
            i += 2;
            while (i < input.size() && input[i] != '\n') ++i;
            continue;
        }
        // Block comment: /* ... */
        if (c == '/' && i + 1 < input.size() && input[i + 1] == '*') {
            i += 2;
            while (i + 1 < input.size() && !(input[i] == '*' && input[i + 1] == '/'))
                ++i;
            if (i + 1 < input.size()) i += 2;  // skip */
            continue;
        }
        out += c;
        ++i;
    }
    // Strip trailing commas before ] and }.
    // Walk backwards from each ] or } and remove the preceding comma
    // (skipping whitespace).
    std::string result;
    result.reserve(out.size());
    for (std::size_t j = 0; j < out.size(); ++j) {
        char ch = out[j];
        if (ch == ']' || ch == '}') {
            // Remove trailing comma from result.
            std::size_t k = result.size();
            while (k > 0 && (result[k - 1] == ' ' || result[k - 1] == '\t'
                             || result[k - 1] == '\n' || result[k - 1] == '\r'))
                --k;
            if (k > 0 && result[k - 1] == ',')
                result.erase(k - 1, 1);
        }
        result += ch;
    }
    return result;
}

std::string read_file(const std::filesystem::path& path) {
    std::ifstream stream(path, std::ios::binary);
    if (!stream) {
        throw std::runtime_error("Native file not found: " + path.string());
    }
    std::ostringstream out;
    out << stream.rdbuf();
    return out.str();
}

// Schema-version gate. Mirrors `NativeFormatService._check_version`
// in the Python service: missing/unparsable raises, future major
// raises, forward-compatible minor accepted. Missing version now
// defaults to "1.0" for backwards compatibility with early fixture
// tunes authored before the field existed — the base-tune fixture
// shipped without it and the app rejected the operator's project.
void check_version(const std::string& raw) {
    if (raw.empty()) {
        std::fprintf(stderr,
            "[native_format] schema_version missing — treating as 1.0\n");
        return;
    }
    auto dot = raw.find('.');
    std::string major_str = (dot == std::string::npos) ? raw : raw.substr(0, dot);
    int major = 0;
    try {
        major = std::stoi(major_str);
    } catch (...) {
        throw NativeFormatVersionError(
            "Native file has unparsable schema_version " + raw + ".");
    }
    int bundled_major = 0;
    try {
        std::string bundled = kNativeSchemaVersion;
        auto bdot = bundled.find('.');
        bundled_major = std::stoi(
            bdot == std::string::npos ? bundled : bundled.substr(0, bdot));
    } catch (...) {
        bundled_major = 1;
    }
    if (major > bundled_major) {
        throw NativeFormatVersionError(
            "Native file schema " + raw + " is newer than supported (" +
            kNativeSchemaVersion + "). Upgrade the application.");
    }
}

// ----- helpers for optional<string> ↔ JSON null/string -----

void put_optional_string(json& obj, const char* key, const std::optional<std::string>& value) {
    if (value.has_value()) {
        obj[key] = *value;
    } else {
        obj[key] = nullptr;
    }
}

void put_optional_double(json& obj, const char* key, const std::optional<double>& value) {
    if (value.has_value()) {
        obj[key] = *value;
    } else {
        obj[key] = nullptr;
    }
}

std::optional<std::string> get_optional_string(const json& obj, const char* key) {
    if (!obj.contains(key) || obj[key].is_null()) return std::nullopt;
    return obj[key].get<std::string>();
}

std::optional<double> get_optional_double(const json& obj, const char* key) {
    if (!obj.contains(key) || obj[key].is_null()) return std::nullopt;
    return obj[key].get<double>();
}

// ----- NativeParameter ↔ JSON -----

json parameter_to_json(const NativeParameter& p) {
    json out = json::object();
    out["semantic_id"] = p.semantic_id;
    out["legacy_name"] = p.legacy_name;
    put_optional_string(out, "label", p.label);
    put_optional_string(out, "units", p.units);
    out["kind"] = p.kind;
    put_optional_double(out, "min_value", p.min_value);
    put_optional_double(out, "max_value", p.max_value);
    put_optional_string(out, "default", p.default_value);
    return out;
}

NativeParameter parameter_from_json(const json& obj) {
    NativeParameter p;
    p.semantic_id = obj.at("semantic_id").get<std::string>();
    p.legacy_name = obj.at("legacy_name").get<std::string>();
    p.label = get_optional_string(obj, "label");
    p.units = get_optional_string(obj, "units");
    p.kind = obj.value("kind", std::string("scalar"));
    p.min_value = get_optional_double(obj, "min_value");
    p.max_value = get_optional_double(obj, "max_value");
    p.default_value = get_optional_string(obj, "default");
    return p;
}

// ----- NativeAxis ↔ JSON -----

json axis_to_json(const NativeAxis& a) {
    json out = json::object();
    out["semantic_id"] = a.semantic_id;
    out["legacy_name"] = a.legacy_name;
    out["length"] = a.length;
    put_optional_string(out, "units", a.units);
    return out;
}

// Read an integer field tolerantly. Older semantic `.tunerdef` files
// sometimes carry a [width, height] array in fields that downstream
// code wants as a scalar count (e.g. `point_count` on a CurveEditor
// with a display-size hint). Return 0 when the key is missing or the
// value isn't a scalar number — surviving the load is more useful
// than failing the whole definition parse on a cosmetic hint.
static int read_int_tolerant(const json& obj, const char* key) {
    if (!obj.contains(key)) return 0;
    const auto& v = obj[key];
    if (v.is_number_integer()) return v.get<int>();
    if (v.is_number_float())   return static_cast<int>(v.get<double>());
    return 0;
}

NativeAxis axis_from_json(const json& obj) {
    NativeAxis a;
    a.semantic_id = obj.at("semantic_id").get<std::string>();
    a.legacy_name = obj.at("legacy_name").get<std::string>();
    a.length = read_int_tolerant(obj, "length");
    a.units = get_optional_string(obj, "units");
    return a;
}

// ----- NativeTable ↔ JSON -----

json table_to_json(const NativeTable& t) {
    json out = json::object();
    out["semantic_id"] = t.semantic_id;
    out["legacy_name"] = t.legacy_name;
    out["rows"] = t.rows;
    out["columns"] = t.columns;
    put_optional_string(out, "label", t.label);
    put_optional_string(out, "units", t.units);
    put_optional_string(out, "x_axis_id", t.x_axis_id);
    put_optional_string(out, "y_axis_id", t.y_axis_id);
    return out;
}

NativeTable table_from_json(const json& obj) {
    NativeTable t;
    t.semantic_id = obj.at("semantic_id").get<std::string>();
    t.legacy_name = obj.at("legacy_name").get<std::string>();
    t.rows = read_int_tolerant(obj, "rows");
    t.columns = read_int_tolerant(obj, "columns");
    t.label = get_optional_string(obj, "label");
    t.units = get_optional_string(obj, "units");
    t.x_axis_id = get_optional_string(obj, "x_axis_id");
    t.y_axis_id = get_optional_string(obj, "y_axis_id");
    return t;
}

// ----- NativeCurve ↔ JSON -----

json curve_to_json(const NativeCurve& c) {
    json out = json::object();
    out["semantic_id"] = c.semantic_id;
    out["legacy_name"] = c.legacy_name;
    out["point_count"] = c.point_count;
    put_optional_string(out, "label", c.label);
    put_optional_string(out, "units", c.units);
    put_optional_string(out, "x_axis_id", c.x_axis_id);
    return out;
}

NativeCurve curve_from_json(const json& obj) {
    NativeCurve c;
    c.semantic_id = obj.at("semantic_id").get<std::string>();
    c.legacy_name = obj.at("legacy_name").get<std::string>();
    c.point_count = read_int_tolerant(obj, "point_count");
    c.label = get_optional_string(obj, "label");
    c.units = get_optional_string(obj, "units");
    c.x_axis_id = get_optional_string(obj, "x_axis_id");
    return c;
}

// ----- NativeTuneValue (variant) ↔ JSON -----

json tune_value_to_json(const NativeTuneValue& value) {
    if (std::holds_alternative<double>(value)) {
        return json(std::get<double>(value));
    }
    if (std::holds_alternative<std::string>(value)) {
        return json(std::get<std::string>(value));
    }
    return json(std::get<std::vector<double>>(value));
}

NativeTuneValue tune_value_from_json(const json& v) {
    if (v.is_array()) {
        // Handle both flat arrays [1.0, 2.0, ...] and nested 2D arrays
        // [[row0], [row1], ...] by flattening into a single vector.
        // The improved .tuner format writes 2D tables as array-of-rows
        // for human readability; the in-memory representation stays flat.
        std::vector<double> flat;
        for (const auto& elem : v) {
            if (elem.is_array()) {
                // Nested row — flatten.
                for (const auto& cell : elem) {
                    flat.push_back(cell.get<double>());
                }
            } else {
                flat.push_back(elem.get<double>());
            }
        }
        return flat;
    }
    if (v.is_string()) {
        return v.get<std::string>();
    }
    if (v.is_number()) {
        return v.get<double>();
    }
    throw std::runtime_error("Unsupported NativeTune value type in JSON.");
}

}  // namespace

// ---------------------------------------------------------------------
// Public serialization API
// ---------------------------------------------------------------------

std::string dump_definition(const NativeDefinition& definition, int indent) {
    json doc = json::object();
    doc["schema_version"] = definition.schema_version;
    doc["name"] = definition.name;
    put_optional_string(doc, "firmware_signature", definition.firmware_signature);

    json parameters = json::array();
    for (const auto& p : definition.parameters) {
        parameters.push_back(parameter_to_json(p));
    }
    doc["parameters"] = std::move(parameters);

    json axes = json::array();
    for (const auto& a : definition.axes) {
        axes.push_back(axis_to_json(a));
    }
    doc["axes"] = std::move(axes);

    json tables = json::array();
    for (const auto& t : definition.tables) {
        tables.push_back(table_to_json(t));
    }
    doc["tables"] = std::move(tables);

    json curves = json::array();
    for (const auto& c : definition.curves) {
        curves.push_back(curve_to_json(c));
    }
    doc["curves"] = std::move(curves);

    return doc.dump(indent);
}

std::string dump_tune(const NativeTune& tune, int indent) {
    json doc = json::object();
    doc["schema_version"] = tune.schema_version;
    put_optional_string(doc, "definition_signature", tune.definition_signature);

    // Slot metadata (v1.1+) — only emitted when present. Pre-v1.1
    // readers ignore unknown keys, so the file stays backwards-
    // compatible. A tune with no slot fields loads as slot 0.
    if (tune.slot_index.has_value()) {
        doc["slot_index"] = *tune.slot_index;
    }
    put_optional_string(doc, "slot_name", tune.slot_name);
    // Firmware definition hash (P16-1) — only emitted when captured
    // at save time from a hash-aware ECU.
    put_optional_string(doc, "definition_hash", tune.definition_hash);

    json values = json::object();
    for (const auto& [key, value] : tune.values) {
        values[key] = tune_value_to_json(value);
    }
    doc["values"] = std::move(values);

    return doc.dump(indent);
}

NativeDefinition load_definition(std::string_view text) {
    json data;
    try {
        auto clean = strip_json5(text);
        data = json::parse(clean);
    } catch (const json::parse_error& e) {
        throw std::runtime_error(std::string("Invalid native JSON/JSON5: ") + e.what());
    }
    if (!data.is_object()) {
        throw std::runtime_error("Native file root must be a JSON object.");
    }
    std::string version = data.value("schema_version", std::string());
    check_version(version);
    if (version.empty()) version = "1.0";  // pre-schema-version file

    NativeDefinition definition;
    definition.schema_version = version;
    definition.name = data.value("name", std::string());
    definition.firmware_signature = get_optional_string(data, "firmware_signature");

    if (data.contains("parameters")) {
        for (const auto& p : data["parameters"]) {
            definition.parameters.push_back(parameter_from_json(p));
        }
    }
    if (data.contains("axes")) {
        for (const auto& a : data["axes"]) {
            definition.axes.push_back(axis_from_json(a));
        }
    }
    if (data.contains("tables")) {
        for (const auto& t : data["tables"]) {
            definition.tables.push_back(table_from_json(t));
        }
    }
    if (data.contains("curves")) {
        for (const auto& c : data["curves"]) {
            definition.curves.push_back(curve_from_json(c));
        }
    }
    return definition;
}

NativeTune load_tune(std::string_view text) {
    json data;
    try {
        auto clean = strip_json5(text);
        data = json::parse(clean);
    } catch (const json::parse_error& e) {
        throw std::runtime_error(std::string("Invalid native JSON: ") + e.what());
    }
    if (!data.is_object()) {
        throw std::runtime_error("Native file root must be a JSON object.");
    }
    std::string version = data.value("schema_version", std::string());
    check_version(version);
    if (version.empty()) version = "1.0";  // pre-schema-version file

    NativeTune tune;
    tune.schema_version = version;
    tune.definition_signature = get_optional_string(data, "definition_signature");
    // Fallback for pre-schema-version fixtures that stored the
    // signature under "definition" (shorter key, same semantic).
    if (!tune.definition_signature.has_value())
        tune.definition_signature = get_optional_string(data, "definition");

    // Slot metadata (v1.1+). Absent fields stay nullopt; consumers
    // treat that as "legacy tune, target slot 0".
    if (data.contains("slot_index") && data["slot_index"].is_number_integer()) {
        tune.slot_index = data["slot_index"].get<int>();
    }
    tune.slot_name = get_optional_string(data, "slot_name");
    tune.definition_hash = get_optional_string(data, "definition_hash");

    if (data.contains("values") && data["values"].is_object()) {
        for (auto it = data["values"].begin(); it != data["values"].end(); ++it) {
            tune.values[it.key()] = tune_value_from_json(it.value());
        }
    }
    return tune;
}

NativeDefinition load_definition_file(const std::filesystem::path& path) {
    return load_definition(read_file(path));
}

NativeTune load_tune_file(const std::filesystem::path& path) {
    return load_tune(read_file(path));
}

// =====================================================================
// v2 full-definition format — NativeEcuDefinition ↔ JSON
// =====================================================================

namespace {

// Helper: serialize bytes to colon-separated hex string "45:01:00".
std::string bytes_to_hex(const std::vector<std::uint8_t>& data) {
    std::string s;
    for (std::size_t i = 0; i < data.size(); ++i) {
        char buf[4];
        std::snprintf(buf, sizeof(buf), "%02x", data[i]);
        if (i > 0) s += ':';
        s += buf;
    }
    return s;
}

// Helper: deserialize hex string back to bytes.
std::vector<std::uint8_t> hex_to_bytes(const std::string& hex) {
    std::vector<std::uint8_t> result;
    std::istringstream iss(hex);
    std::string byte_str;
    while (std::getline(iss, byte_str, ':')) {
        if (!byte_str.empty())
            result.push_back(static_cast<std::uint8_t>(
                std::stoul(byte_str, nullptr, 16)));
    }
    return result;
}

// Helper: optional<T> → json (null if empty).
template<typename T>
json opt_to_json(const std::optional<T>& v) {
    return v.has_value() ? json(*v) : json(nullptr);
}

// Helper: json → optional<T>.
template<typename T>
std::optional<T> json_to_opt(const json& j, const char* key) {
    if (j.contains(key) && !j[key].is_null())
        return j[key].get<T>();
    return std::nullopt;
}

}  // anon

// Humanize a camelCase firmware identifier to a readable label.
// "aseTaperTime" → "ASE Taper Time", "wueRates" → "WUE Rates"
static std::string humanize_name(const std::string& raw) {
    std::string result;
    for (std::size_t i = 0; i < raw.size(); ++i) {
        char c = raw[i];
        if (c == '_') { result += ' '; continue; }
        if (i > 0) {
            bool prev_lower = std::islower(static_cast<unsigned char>(raw[i-1]));
            bool curr_upper = std::isupper(static_cast<unsigned char>(c));
            bool prev_alpha = std::isalpha(static_cast<unsigned char>(raw[i-1]));
            bool curr_digit = std::isdigit(static_cast<unsigned char>(c));
            if ((prev_lower && curr_upper) || (prev_alpha && curr_digit))
                result += ' ';
        }
        result += c;
    }
    if (!result.empty())
        result[0] = static_cast<char>(std::toupper(static_cast<unsigned char>(result[0])));
    return result;
}

std::string dump_definition_v2(const NativeEcuDefinition& def, int indent) {
    json doc;
    doc["schema_version"] = "2.0";

    // --- constants ---
    {
        json scalars = json::array();
        for (const auto& s : def.constants.scalars) {
            json j;
            j["name"] = s.name;
            j["data_type"] = s.data_type;
            j["units"] = opt_to_json(s.units);
            j["page"] = opt_to_json(s.page);
            j["offset"] = opt_to_json(s.offset);
            j["scale"] = opt_to_json(s.scale);
            j["translate"] = opt_to_json(s.translate);
            j["digits"] = opt_to_json(s.digits);
            j["min_value"] = opt_to_json(s.min_value);
            j["max_value"] = opt_to_json(s.max_value);
            if (!s.options.empty()) j["options"] = s.options;
            j["bit_offset"] = opt_to_json(s.bit_offset);
            j["bit_length"] = opt_to_json(s.bit_length);
            scalars.push_back(std::move(j));
        }
        json arrays = json::array();
        for (const auto& a : def.constants.arrays) {
            json j;
            j["name"] = a.name;
            j["data_type"] = a.data_type;
            j["rows"] = a.rows;
            j["columns"] = a.columns;
            j["units"] = opt_to_json(a.units);
            j["page"] = opt_to_json(a.page);
            j["offset"] = opt_to_json(a.offset);
            j["scale"] = opt_to_json(a.scale);
            j["translate"] = opt_to_json(a.translate);
            j["digits"] = opt_to_json(a.digits);
            j["min_value"] = opt_to_json(a.min_value);
            j["max_value"] = opt_to_json(a.max_value);
            arrays.push_back(std::move(j));
        }
        doc["constants"] = {{"scalars", std::move(scalars)}, {"arrays", std::move(arrays)}};
    }

    // --- output_channels ---
    {
        json channels = json::array();
        for (const auto& ch : def.output_channels.channels) {
            json j;
            j["name"] = ch.name;
            j["data_type"] = ch.data_type;
            j["offset"] = ch.offset;
            j["units"] = opt_to_json(ch.units);
            j["scale"] = opt_to_json(ch.scale);
            j["translate"] = opt_to_json(ch.translate);
            j["digits"] = opt_to_json(ch.digits);
            j["bit_offset"] = opt_to_json(ch.bit_offset);
            j["bit_length"] = opt_to_json(ch.bit_length);
            if (!ch.options.empty()) j["options"] = ch.options;
            channels.push_back(std::move(j));
        }
        json formula_channels = json::array();
        for (const auto& fc : def.output_channels.formula_channels) {
            json j;
            j["name"] = fc.name;
            j["formula"] = fc.formula_expression;
            j["units"] = opt_to_json(fc.units);
            j["digits"] = opt_to_json(fc.digits);
            formula_channels.push_back(std::move(j));
        }
        doc["output_channels"] = {
            {"channels", std::move(channels)},
            {"formula_channels", std::move(formula_channels)}};
    }

    // --- gauge_configurations ---
    {
        json gauges = json::array();
        for (const auto& g : def.gauge_configurations.gauges) {
            json j;
            j["name"] = g.name;
            j["channel"] = g.channel;
            j["title"] = g.title;
            j["units"] = g.units;
            j["lo"] = opt_to_json(g.lo);
            j["hi"] = opt_to_json(g.hi);
            j["lo_danger"] = opt_to_json(g.lo_danger);
            j["lo_warn"] = opt_to_json(g.lo_warn);
            j["hi_warn"] = opt_to_json(g.hi_warn);
            j["hi_danger"] = opt_to_json(g.hi_danger);
            j["value_digits"] = g.value_digits;
            j["label_digits"] = g.label_digits;
            j["category"] = opt_to_json(g.category);
            gauges.push_back(std::move(j));
        }
        doc["gauge_configurations"] = std::move(gauges);
    }

    // --- front_page ---
    {
        json fp;
        fp["gauges"] = def.front_page.gauges;
        json indicators = json::array();
        for (const auto& ind : def.front_page.indicators) {
            json j;
            j["expression"] = ind.expression;
            j["off_label"] = ind.off_label;
            j["on_label"] = ind.on_label;
            j["off_bg"] = ind.off_bg;
            j["off_fg"] = ind.off_fg;
            j["on_bg"] = ind.on_bg;
            j["on_fg"] = ind.on_fg;
            indicators.push_back(std::move(j));
        }
        fp["indicators"] = std::move(indicators);
        doc["front_page"] = std::move(fp);
    }

    // --- controller_commands ---
    {
        json cmds = json::array();
        for (const auto& cmd : def.controller_commands.commands) {
            json j;
            j["name"] = cmd.name;
            j["payload"] = bytes_to_hex(cmd.payload);
            cmds.push_back(std::move(j));
        }
        doc["controller_commands"] = std::move(cmds);
    }

    // --- logger_definitions ---
    {
        json loggers = json::array();
        for (const auto& lg : def.logger_definitions.loggers) {
            json j;
            j["name"] = lg.name;
            j["display_name"] = lg.display_name;
            j["kind"] = lg.kind;
            j["data_read_command"] = bytes_to_hex(lg.data_read_command);
            j["data_read_timeout_ms"] = lg.data_read_timeout_ms;
            j["record_header_len"] = lg.record_header_len;
            j["record_len"] = lg.record_len;
            j["record_count"] = lg.record_count;
            json fields = json::array();
            for (const auto& f : lg.record_fields) {
                fields.push_back({
                    {"name", f.name}, {"header", f.header},
                    {"start_bit", f.start_bit}, {"bit_count", f.bit_count},
                    {"scale", f.scale}, {"units", f.units}});
            }
            j["record_fields"] = std::move(fields);
            loggers.push_back(std::move(j));
        }
        doc["logger_definitions"] = std::move(loggers);
    }

    // --- setting_groups ---
    {
        json groups = json::array();
        for (const auto& g : def.setting_groups.groups) {
            json j;
            j["symbol"] = g.symbol;
            j["label"] = g.label;
            json opts = json::array();
            for (const auto& o : g.options)
                opts.push_back({{"symbol", o.symbol}, {"label", o.label}});
            j["options"] = std::move(opts);
            groups.push_back(std::move(j));
        }
        doc["setting_groups"] = std::move(groups);
    }

    // --- setting_context_help ---
    doc["setting_context_help"] = def.setting_context_help.help_by_name;

    // --- constants_extensions ---
    doc["constants_extensions"] = {
        {"requires_power_cycle", json(std::vector<std::string>(
            def.constants_extensions.requires_power_cycle.begin(),
            def.constants_extensions.requires_power_cycle.end()))}};

    // --- menus ---
    {
        json menus = json::array();
        for (const auto& m : def.menus.menus) {
            json jm;
            jm["title"] = m.title;
            json items = json::array();
            for (const auto& it : m.items) {
                json ji;
                ji["target"] = it.target;
                ji["label"] = opt_to_json(it.label);
                ji["page"] = opt_to_json(it.page);
                ji["visibility_expression"] = opt_to_json(it.visibility_expression);
                items.push_back(std::move(ji));
            }
            jm["items"] = std::move(items);
            menus.push_back(std::move(jm));
        }
        doc["menus"] = std::move(menus);
    }

    // --- dialogs ---
    {
        json dialogs = json::array();
        for (const auto& d : def.dialogs.dialogs) {
            json jd;
            jd["dialog_id"] = d.dialog_id;
            jd["title"] = d.title;
            json fields = json::array();
            for (const auto& f : d.fields) {
                fields.push_back({
                    {"label", f.label}, {"parameter_name", f.parameter_name},
                    {"visibility_expression", f.visibility_expression},
                    {"is_static_text", f.is_static_text}});
            }
            jd["fields"] = std::move(fields);
            json panels = json::array();
            for (const auto& p : d.panels) {
                panels.push_back({
                    {"target", p.target}, {"position", p.position},
                    {"visibility_expression", p.visibility_expression}});
            }
            jd["panels"] = std::move(panels);
            dialogs.push_back(std::move(jd));
        }
        doc["dialogs"] = std::move(dialogs);
    }

    // --- table_editors ---
    {
        json editors = json::array();
        for (const auto& e : def.table_editors.editors) {
            json je;
            je["table_id"] = e.table_id;
            je["map_id"]   = e.map_id;
            je["title"]    = e.title;
            je["page"]     = opt_to_json(e.page);
            put_optional_string(je, "x_bins", e.x_bins);
            put_optional_string(je, "y_bins", e.y_bins);
            put_optional_string(je, "z_bins", e.z_bins);
            put_optional_string(je, "x_channel", e.x_channel);
            put_optional_string(je, "y_channel", e.y_channel);
            put_optional_string(je, "x_label", e.x_label);
            put_optional_string(je, "y_label", e.y_label);
            put_optional_string(je, "topic_help", e.topic_help);
            put_optional_double(je, "grid_height", e.grid_height);
            if (e.grid_orient.has_value()) {
                je["grid_orient"] = json::array({
                    (*e.grid_orient)[0], (*e.grid_orient)[1], (*e.grid_orient)[2]});
            } else {
                je["grid_orient"] = nullptr;
            }
            put_optional_string(je, "up_label", e.up_label);
            put_optional_string(je, "down_label", e.down_label);
            editors.push_back(std::move(je));
        }
        doc["table_editors"] = std::move(editors);
    }

    // --- curve_editors ---
    {
        json curves = json::array();
        for (const auto& c : def.curve_editors.curves) {
            json jc;
            jc["name"] = c.name;
            jc["title"] = c.title;
            jc["x_bins_param"] = c.x_bins_param;
            put_optional_string(jc, "x_channel", c.x_channel);
            json yb = json::array();
            for (const auto& y : c.y_bins_list) {
                json jy;
                jy["param"] = y.param;
                put_optional_string(jy, "label", y.label);
                yb.push_back(std::move(jy));
            }
            jc["y_bins_list"] = std::move(yb);
            jc["x_label"] = c.x_label;
            jc["y_label"] = c.y_label;
            auto range_to_json = [](const CurveAxisRange& r) {
                return json{{"min", r.min}, {"max", r.max}, {"steps", r.steps}};
            };
            if (c.x_axis.has_value()) jc["x_axis"] = range_to_json(*c.x_axis);
            else                       jc["x_axis"] = nullptr;
            if (c.y_axis.has_value()) jc["y_axis"] = range_to_json(*c.y_axis);
            else                       jc["y_axis"] = nullptr;
            put_optional_string(jc, "topic_help", c.topic_help);
            put_optional_string(jc, "gauge", c.gauge);
            if (c.size.has_value()) {
                jc["size"] = json::array({(*c.size)[0], (*c.size)[1]});
            } else {
                jc["size"] = nullptr;
            }
            curves.push_back(std::move(jc));
        }
        doc["curve_editors"] = std::move(curves);
    }

    // Tools / reference_tables / autotune_sections stay minimal —
    // they're runtime-optional catalog-ish sections the workspace
    // doesn't need to route tree pages.
    doc["tools"] = json::array();
    doc["reference_tables"] = json::array();
    doc["autotune_sections"] = json::array();

    return doc.dump(indent);
}

NativeEcuDefinition load_definition_v2(std::string_view text) {
    auto clean = strip_json5(text);
    json data;
    try { data = json::parse(clean); }
    catch (const json::parse_error& e) {
        throw std::runtime_error(
            std::string("Invalid native JSON5: ") + e.what());
    }

    std::string version = data.value("schema_version", "");
    if (version.empty() || version[0] < '2') {
        throw std::runtime_error(
            "Not a v2 definition (schema_version=" + version + ")");
    }

    NativeEcuDefinition def;

    // --- constants ---
    if (data.contains("constants")) {
        const auto& c = data["constants"];
        if (c.contains("scalars")) {
            for (const auto& j : c["scalars"]) {
                IniScalar s;
                s.name = j.value("name", "");
                s.data_type = j.value("data_type", "U08");
                s.units = json_to_opt<std::string>(j, "units");
                s.page = json_to_opt<int>(j, "page");
                s.offset = json_to_opt<int>(j, "offset");
                s.scale = json_to_opt<double>(j, "scale");
                s.translate = json_to_opt<double>(j, "translate");
                s.digits = json_to_opt<int>(j, "digits");
                s.min_value = json_to_opt<double>(j, "min_value");
                s.max_value = json_to_opt<double>(j, "max_value");
                if (j.contains("options")) s.options = j["options"].get<std::vector<std::string>>();
                s.bit_offset = json_to_opt<int>(j, "bit_offset");
                s.bit_length = json_to_opt<int>(j, "bit_length");
                def.constants.scalars.push_back(std::move(s));
            }
        }
        if (c.contains("arrays")) {
            for (const auto& j : c["arrays"]) {
                IniArray a;
                a.name = j.value("name", "");
                a.data_type = j.value("data_type", "U08");
                a.rows = j.value("rows", 0);
                a.columns = j.value("columns", 0);
                a.units = json_to_opt<std::string>(j, "units");
                a.page = json_to_opt<int>(j, "page");
                a.offset = json_to_opt<int>(j, "offset");
                a.scale = json_to_opt<double>(j, "scale");
                a.translate = json_to_opt<double>(j, "translate");
                a.digits = json_to_opt<int>(j, "digits");
                a.min_value = json_to_opt<double>(j, "min_value");
                a.max_value = json_to_opt<double>(j, "max_value");
                def.constants.arrays.push_back(std::move(a));
            }
        }
    }

    // --- output_channels ---
    if (data.contains("output_channels")) {
        const auto& oc = data["output_channels"];
        if (oc.contains("channels")) {
            for (const auto& j : oc["channels"]) {
                IniOutputChannel ch;
                ch.name = j.value("name", "");
                ch.data_type = j.value("data_type", "U08");
                ch.offset = j.value("offset", 0);
                ch.units = json_to_opt<std::string>(j, "units");
                ch.scale = json_to_opt<double>(j, "scale");
                ch.translate = json_to_opt<double>(j, "translate");
                ch.digits = json_to_opt<int>(j, "digits");
                ch.bit_offset = json_to_opt<int>(j, "bit_offset");
                ch.bit_length = json_to_opt<int>(j, "bit_length");
                if (j.contains("options")) ch.options = j["options"].get<std::vector<std::string>>();
                def.output_channels.channels.push_back(std::move(ch));
            }
        }
        if (oc.contains("formula_channels")) {
            for (const auto& j : oc["formula_channels"]) {
                IniFormulaOutputChannel fc;
                fc.name = j.value("name", "");
                fc.formula_expression = j.value("formula", "");
                fc.units = json_to_opt<std::string>(j, "units");
                fc.digits = json_to_opt<int>(j, "digits");
                def.output_channels.formula_channels.push_back(std::move(fc));
            }
        }
    }

    // --- gauge_configurations ---
    if (data.contains("gauge_configurations")) {
        for (const auto& j : data["gauge_configurations"]) {
            IniGaugeConfiguration g;
            g.name = j.value("name", "");
            g.channel = j.value("channel", "");
            g.title = j.value("title", "");
            g.units = j.value("units", "");
            g.lo = json_to_opt<double>(j, "lo");
            g.hi = json_to_opt<double>(j, "hi");
            g.lo_danger = json_to_opt<double>(j, "lo_danger");
            g.lo_warn = json_to_opt<double>(j, "lo_warn");
            g.hi_warn = json_to_opt<double>(j, "hi_warn");
            g.hi_danger = json_to_opt<double>(j, "hi_danger");
            g.value_digits = j.value("value_digits", 0);
            g.label_digits = j.value("label_digits", 0);
            g.category = json_to_opt<std::string>(j, "category");
            def.gauge_configurations.gauges.push_back(std::move(g));
        }
    }

    // --- front_page ---
    if (data.contains("front_page")) {
        const auto& fp = data["front_page"];
        if (fp.contains("gauges"))
            def.front_page.gauges = fp["gauges"].get<std::vector<std::string>>();
        if (fp.contains("indicators")) {
            for (const auto& j : fp["indicators"]) {
                IniFrontPageIndicator ind;
                ind.expression = j.value("expression", "");
                ind.off_label = j.value("off_label", "");
                ind.on_label = j.value("on_label", "");
                ind.off_bg = j.value("off_bg", "white");
                ind.off_fg = j.value("off_fg", "black");
                ind.on_bg = j.value("on_bg", "green");
                ind.on_fg = j.value("on_fg", "black");
                def.front_page.indicators.push_back(std::move(ind));
            }
        }
    }

    // --- controller_commands ---
    if (data.contains("controller_commands")) {
        for (const auto& j : data["controller_commands"]) {
            IniControllerCommand cmd;
            cmd.name = j.value("name", "");
            cmd.payload = hex_to_bytes(j.value("payload", ""));
            def.controller_commands.commands.push_back(std::move(cmd));
        }
    }

    // --- logger_definitions ---
    if (data.contains("logger_definitions")) {
        for (const auto& j : data["logger_definitions"]) {
            IniLoggerDefinition lg;
            lg.name = j.value("name", "");
            lg.display_name = j.value("display_name", "");
            lg.kind = j.value("kind", "");
            lg.data_read_command = hex_to_bytes(j.value("data_read_command", ""));
            lg.data_read_timeout_ms = j.value("data_read_timeout_ms", 5000);
            lg.record_header_len = j.value("record_header_len", 0);
            lg.record_len = j.value("record_len", 0);
            lg.record_count = j.value("record_count", 0);
            if (j.contains("record_fields")) {
                for (const auto& fj : j["record_fields"]) {
                    IniLoggerRecordField f;
                    f.name = fj.value("name", "");
                    f.header = fj.value("header", "");
                    f.start_bit = fj.value("start_bit", 0);
                    f.bit_count = fj.value("bit_count", 0);
                    f.scale = fj.value("scale", 1.0);
                    f.units = fj.value("units", "");
                    lg.record_fields.push_back(std::move(f));
                }
            }
            def.logger_definitions.loggers.push_back(std::move(lg));
        }
    }

    // --- setting_groups ---
    if (data.contains("setting_groups")) {
        for (const auto& j : data["setting_groups"]) {
            IniSettingGroup g;
            g.symbol = j.value("symbol", "");
            g.label = j.value("label", "");
            if (j.contains("options")) {
                for (const auto& oj : j["options"]) {
                    IniSettingGroupOption o;
                    o.symbol = oj.value("symbol", "");
                    o.label = oj.value("label", "");
                    g.options.push_back(std::move(o));
                }
            }
            def.setting_groups.groups.push_back(std::move(g));
        }
    }

    // --- setting_context_help ---
    if (data.contains("setting_context_help") && data["setting_context_help"].is_object()) {
        for (auto& [key, val] : data["setting_context_help"].items())
            def.setting_context_help.help_by_name[key] = val.get<std::string>();
    }

    // --- constants_extensions ---
    if (data.contains("constants_extensions")) {
        const auto& ce = data["constants_extensions"];
        if (ce.contains("requires_power_cycle")) {
            for (const auto& s : ce["requires_power_cycle"])
                def.constants_extensions.requires_power_cycle.insert(s.get<std::string>());
        }
    }

    // --- menus ---
    if (data.contains("menus")) {
        for (const auto& jm : data["menus"]) {
            IniMenu m;
            m.title = jm.value("title", "");
            if (jm.contains("items")) {
                for (const auto& ji : jm["items"]) {
                    IniMenuItem it;
                    it.target = ji.value("target", "");
                    it.label = json_to_opt<std::string>(ji, "label");
                    it.page = json_to_opt<int>(ji, "page");
                    it.visibility_expression = json_to_opt<std::string>(ji, "visibility_expression");
                    m.items.push_back(std::move(it));
                }
            }
            def.menus.menus.push_back(std::move(m));
        }
    }

    // --- dialogs ---
    if (data.contains("dialogs")) {
        for (const auto& jd : data["dialogs"]) {
            IniDialog d;
            d.dialog_id = jd.value("dialog_id", "");
            d.title = jd.value("title", "");
            if (jd.contains("fields")) {
                for (const auto& jf : jd["fields"]) {
                    IniDialogField f;
                    f.label = jf.value("label", "");
                    f.parameter_name = jf.value("parameter_name", "");
                    f.visibility_expression = jf.value("visibility_expression", "");
                    f.is_static_text = jf.value("is_static_text", false);
                    d.fields.push_back(std::move(f));
                }
            }
            if (jd.contains("panels")) {
                for (const auto& jp : jd["panels"]) {
                    IniDialogPanelRef p;
                    p.target = jp.value("target", "");
                    p.position = jp.value("position", "");
                    p.visibility_expression = jp.value("visibility_expression", "");
                    d.panels.push_back(std::move(p));
                }
            }
            def.dialogs.dialogs.push_back(std::move(d));
        }
    }

    // --- table_editors ---
    if (data.contains("table_editors")) {
        for (const auto& je : data["table_editors"]) {
            IniTableEditor e;
            e.table_id = je.value("table_id", "");
            e.map_id   = je.value("map_id", "");
            e.title    = je.value("title", "");
            e.page     = json_to_opt<int>(je, "page");
            e.x_bins   = get_optional_string(je, "x_bins");
            e.y_bins   = get_optional_string(je, "y_bins");
            e.z_bins   = get_optional_string(je, "z_bins");
            e.x_channel = get_optional_string(je, "x_channel");
            e.y_channel = get_optional_string(je, "y_channel");
            e.x_label  = get_optional_string(je, "x_label");
            e.y_label  = get_optional_string(je, "y_label");
            e.topic_help = get_optional_string(je, "topic_help");
            e.grid_height = get_optional_double(je, "grid_height");
            if (je.contains("grid_orient") && je["grid_orient"].is_array()
                && je["grid_orient"].size() == 3) {
                std::array<double, 3> go{{
                    je["grid_orient"][0].get<double>(),
                    je["grid_orient"][1].get<double>(),
                    je["grid_orient"][2].get<double>()}};
                e.grid_orient = go;
            }
            e.up_label   = get_optional_string(je, "up_label");
            e.down_label = get_optional_string(je, "down_label");
            def.table_editors.editors.push_back(std::move(e));
        }
    }

    // --- curve_editors ---
    if (data.contains("curve_editors")) {
        for (const auto& jc : data["curve_editors"]) {
            IniCurveEditor c;
            c.name = jc.value("name", "");
            c.title = jc.value("title", "");
            c.x_bins_param = jc.value("x_bins_param", "");
            c.x_channel = get_optional_string(jc, "x_channel");
            if (jc.contains("y_bins_list")) {
                for (const auto& jy : jc["y_bins_list"]) {
                    CurveYBins yb;
                    yb.param = jy.value("param", "");
                    yb.label = get_optional_string(jy, "label");
                    c.y_bins_list.push_back(std::move(yb));
                }
            }
            c.x_label = jc.value("x_label", "");
            c.y_label = jc.value("y_label", "");
            auto range_from_json = [](const json& jr) {
                CurveAxisRange r;
                r.min = jr.value("min", 0.0);
                r.max = jr.value("max", 0.0);
                r.steps = jr.value("steps", 0);
                return r;
            };
            if (jc.contains("x_axis") && jc["x_axis"].is_object())
                c.x_axis = range_from_json(jc["x_axis"]);
            if (jc.contains("y_axis") && jc["y_axis"].is_object())
                c.y_axis = range_from_json(jc["y_axis"]);
            c.topic_help = get_optional_string(jc, "topic_help");
            c.gauge = get_optional_string(jc, "gauge");
            if (jc.contains("size") && jc["size"].is_array()
                && jc["size"].size() == 2) {
                std::array<int, 2> sz{{
                    jc["size"][0].get<int>(),
                    jc["size"][1].get<int>()}};
                c.size = sz;
            }
            def.curve_editors.curves.push_back(std::move(c));
        }
    }

    return def;
}

NativeEcuDefinition load_definition_v2_file(const std::filesystem::path& path) {
    return load_definition_v2(read_file(path));
}

}  // namespace tuner_core
