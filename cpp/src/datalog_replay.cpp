// SPDX-License-Identifier: MIT
#include "tuner_core/datalog_replay.hpp"

#include <algorithm>
#include <cstdio>
#include <stdexcept>
#include <string>

namespace tuner_core::datalog_replay {

SelectionSnapshot select_row(const std::vector<Record>& records, int index) {
    if (records.empty())
        throw std::invalid_argument("Datalog is empty.");

    int bounded = std::clamp(index, 0, static_cast<int>(records.size()) - 1);
    const auto& rec = records[bounded];

    // Preview: first 8 channels.
    std::string preview;
    int lim = std::min(static_cast<int>(rec.values.size()), 8);
    for (int i = 0; i < lim; ++i) {
        if (i > 0) preview += ", ";
        char buf[64];
        std::snprintf(buf, sizeof(buf), "%s=%g", rec.values[i].first.c_str(), rec.values[i].second);
        preview += buf;
    }

    char summary[256];
    std::snprintf(summary, sizeof(summary),
        "Replay row %d of %d with %d channel(s) at %s.",
        bounded + 1, static_cast<int>(records.size()),
        static_cast<int>(rec.values.size()), rec.timestamp_iso.c_str());

    return {bounded, static_cast<int>(records.size()),
            static_cast<int>(rec.values.size()), summary, preview};
}

}  // namespace tuner_core::datalog_replay
