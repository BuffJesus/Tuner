// SPDX-License-Identifier: MIT
//
// tuner_core::tune_value_preview implementation.
//
// `format_scalar_python_repr` mirrors Python's `str(float)`. Python
// uses Steele/White-style shortest-roundtrip dtoa under the hood
// (Grisu/Ryu in modern CPython), and adds an explicit `.0` to
// whole-number values so they remain visually distinct from ints.
// C++17's `std::to_chars(double)` produces the same shortest-
// roundtrip representation; we then post-process the result to
// append `.0` when no decimal point or exponent is present.

#include "tuner_core/tune_value_preview.hpp"

#include <array>
#include <charconv>
#include <cstring>
#include <string>
#include <system_error>
#include <variant>

namespace tuner_core::tune_value_preview {

namespace {

bool string_has_dot_or_exp(std::string_view s) noexcept {
    for (char c : s) {
        if (c == '.' || c == 'e' || c == 'E') return true;
    }
    return false;
}

}  // namespace

std::string format_scalar_python_repr(double value) {
    // Shortest round-trip via std::to_chars. The buffer is sized to
    // accommodate any IEEE 754 double + optional sign + exponent.
    std::array<char, 64> buf{};
    auto result = std::to_chars(buf.data(), buf.data() + buf.size(), value);
    if (result.ec != std::errc{}) {
        // Should never happen for finite doubles; fall back gracefully.
        return std::string("?");
    }
    std::string out(buf.data(), result.ptr);

    // Python `str(nan)` → "nan", `str(inf)` → "inf", `str(-inf)` →
    // "-inf". `to_chars` produces "nan" / "inf" / "-inf" too, so no
    // post-processing needed for those cases.
    if (out == "nan" || out == "inf" || out == "-inf") return out;

    // Append `.0` if neither a decimal point nor an exponent is
    // present — matches Python `str(1.0)` → "1.0".
    if (!string_has_dot_or_exp(out)) {
        out += ".0";
    }
    return out;
}

std::string format_list_preview(std::span<const double> values) {
    // Mirror `_list_preview`: join the first 4 items with ", " and
    // append " ... (N values)" when there are more than 4.
    std::string out;
    const std::size_t shown = std::min<std::size_t>(values.size(), 4);
    for (std::size_t i = 0; i < shown; ++i) {
        if (i > 0) out += ", ";
        out += format_scalar_python_repr(values[i]);
    }
    if (values.size() > 4) {
        out += " ... (";
        out += std::to_string(values.size());
        out += " values)";
    }
    return out;
}

std::string format_value_preview(const ScalarOrList& value) {
    if (std::holds_alternative<double>(value)) {
        return format_scalar_python_repr(std::get<double>(value));
    }
    const auto& list = std::get<std::vector<double>>(value);
    return format_list_preview(std::span<const double>(list.data(), list.size()));
}

}  // namespace tuner_core::tune_value_preview
