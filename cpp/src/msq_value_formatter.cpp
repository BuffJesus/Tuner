// SPDX-License-Identifier: MIT
#include "tuner_core/msq_value_formatter.hpp"

#include <cmath>
#include <cstdio>
#include <sstream>

namespace tuner_core::msq_value_formatter {

std::string format_scalar(double value) {
    if (std::floor(value) == value && std::abs(value) < 1e15)
        return std::to_string(static_cast<long long>(value));
    char buf[32];
    std::snprintf(buf, sizeof(buf), "%g", value);
    return buf;
}

std::string format_value(const Value& value, int rows, int cols) {
    if (std::holds_alternative<std::string>(value))
        return std::get<std::string>(value);

    if (std::holds_alternative<double>(value))
        return format_scalar(std::get<double>(value));

    const auto& list = std::get<std::vector<double>>(value);
    if (list.empty()) return "";

    int r = (rows > 0) ? rows : static_cast<int>(list.size());
    int c = (cols > 0) ? cols : 1;

    std::string out = "\n";
    for (int ri = 0; ri < r; ++ri) {
        out += "         ";
        int start = ri * c;
        int end = std::min(start + c, static_cast<int>(list.size()));
        for (int ci = start; ci < end; ++ci) {
            if (ci > start) out += " ";
            out += format_scalar(list[ci]);
        }
        out += " \n";
    }
    out += "      ";
    return out;
}

}  // namespace tuner_core::msq_value_formatter
