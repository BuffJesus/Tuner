// SPDX-License-Identifier: MIT
//
// tuner_core::curve_page_classifier — port of
// `CurvePageService._classify` and `_summary`. Twenty-third sub-slice
// of the Phase 14 workspace-services port (Slice 4).
//
// The full `CurvePageService.build_curve_pages` orchestrator depends
// on `TuningPage` / `TuningPageGroup` / `TuningPageParameter` PODs
// that haven't landed in C++ yet. The classifier and summary are
// the algorithmic meat — keyword-driven group assignment plus the
// operator-facing one-line summary string. Both are pure logic and
// directly useful from any future C++ curve consumer.

#pragma once

#include <string>
#include <string_view>

namespace tuner_core::curve_page_classifier {

struct GroupAssignment {
    int order = 99;
    std::string group_id;
    std::string group_title;
};

// Mirror `CurvePageService._classify`. Joins the curve's name and
// title with a space, lowercases the result, then walks the same
// 8-rule keyword table the Python service uses. Returns the first
// match; falls through to `(99, "other", "Other")` if nothing
// matches. Keyword matching uses word-boundary semantics
// (`\bkw\b`).
GroupAssignment classify(std::string_view name, std::string_view title);

// Mirror `CurvePageService._summary`. Returns
// `"Curve · {N lines | 1D}[ · live: {channel}]"`.
std::string summary(int y_bins_count, std::string_view x_channel);

}  // namespace tuner_core::curve_page_classifier
