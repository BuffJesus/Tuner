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
// raises, forward-compatible minor accepted.
void check_version(const std::string& raw) {
    if (raw.empty()) {
        throw NativeFormatVersionError(
            "Native file is missing the required `schema_version` field.");
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

NativeAxis axis_from_json(const json& obj) {
    NativeAxis a;
    a.semantic_id = obj.at("semantic_id").get<std::string>();
    a.legacy_name = obj.at("legacy_name").get<std::string>();
    a.length = obj.value("length", 0);
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
    t.rows = obj.value("rows", 0);
    t.columns = obj.value("columns", 0);
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
    c.point_count = obj.value("point_count", 0);
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

    NativeTune tune;
    tune.schema_version = version;
    tune.definition_signature = get_optional_string(data, "definition_signature");

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

}  // namespace tuner_core
