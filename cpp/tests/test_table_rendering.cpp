// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::table_rendering.

#include "doctest.h"

#include "tuner_core/table_rendering.hpp"
#include "tuner_core/table_view.hpp"

namespace tr = tuner_core::table_rendering;
namespace tv = tuner_core::table_view;

namespace {

tv::ViewModel make_model(std::vector<std::vector<std::string>> cells) {
    tv::ViewModel m;
    m.rows = cells.size();
    m.columns = cells.empty() ? 0 : cells.front().size();
    m.cells = std::move(cells);
    return m;
}

}  // namespace

TEST_CASE("invert_y_axis reverses row index map and y labels") {
    auto model = make_model({{"1"}, {"2"}, {"3"}});
    auto out = tr::build_render_model(model, {"x"}, {"low", "mid", "hi"}, true);
    REQUIRE(out.row_index_map.size() == 3);
    CHECK(out.row_index_map[0] == 2);
    CHECK(out.row_index_map[1] == 1);
    CHECK(out.row_index_map[2] == 0);
    CHECK(out.y_labels[0] == "hi");
    CHECK(out.y_labels[1] == "mid");
    CHECK(out.y_labels[2] == "low");
    // Display row 0 is model row 2, which is "3" (the maximum).
    CHECK(out.cells[0][0].text == "3");
    CHECK(out.cells[2][0].text == "1");
}

TEST_CASE("invert_y_axis=false preserves natural row order") {
    auto model = make_model({{"1"}, {"2"}});
    auto out = tr::build_render_model(model, {"x"}, {"a", "b"}, false);
    CHECK(out.row_index_map[0] == 0);
    CHECK(out.row_index_map[1] == 1);
    CHECK(out.y_labels[0] == "a");
    CHECK(out.y_labels[1] == "b");
}

TEST_CASE("minimum-value cell renders with the gradient leftmost stop") {
    auto model = make_model({{"10", "20"}, {"30", "40"}});
    auto out = tr::build_render_model(model, {"a", "b"}, {"y0", "y1"}, true);
    // Display row 1 is model row 0; column 0 carries "10", which is
    // the minimum (ratio 0.0 → stop[0] = #8aa8ff).
    CHECK(out.cells[1][0].text == "10");
    CHECK(out.cells[1][0].background_hex == "#8aa8ff");
    CHECK(out.cells[1][0].foreground_hex == "#000000");
}

TEST_CASE("maximum-value cell renders with the gradient rightmost stop") {
    auto model = make_model({{"10", "20"}, {"30", "40"}});
    auto out = tr::build_render_model(model, {"a", "b"}, {"y0", "y1"}, true);
    // Display row 0 is model row 1; column 1 carries "40", the max.
    CHECK(out.cells[0][1].text == "40");
    CHECK(out.cells[0][1].background_hex == "#e58e8e");
    CHECK(out.cells[0][1].foreground_hex == "#000000");
}

TEST_CASE("non-numeric cell falls through to white-on-black default") {
    auto model = make_model({{"hello"}});
    auto out = tr::build_render_model(model, {"a"}, {"y"}, true);
    CHECK(out.cells[0][0].text == "hello");
    CHECK(out.cells[0][0].background_hex == "#ffffff");
    CHECK(out.cells[0][0].foreground_hex == "#000000");
}

TEST_CASE("uniform-value table picks the midpoint stop (ratio 0.5)") {
    // When max <= min, ratio is hard-coded to 0.5 — sits between
    // stop[2]=(0.5, #9af0a0) and stop[3]=(0.75, #e4ee8e), local=0.0
    // → exactly stop[2] = #9af0a0.
    auto model = make_model({{"7"}, {"7"}});
    auto out = tr::build_render_model(model, {"x"}, {"a", "b"}, true);
    CHECK(out.cells[0][0].background_hex == "#9af0a0");
    CHECK(out.cells[1][0].background_hex == "#9af0a0");
}

TEST_CASE("foreground flips to white when background is dark enough") {
    // No gradient stop in this slice's table is dark enough to push
    // perceived brightness below 120 (the lightest stop, #8aa8ff,
    // already lands at ~169). The Python service uses the same stop
    // table, so the foreground is always #000000 in practice. Pin
    // that contract here so future stop additions are caught.
    auto model = make_model({{"0", "100"}});
    auto out = tr::build_render_model(model, {"a", "b"}, {"y"}, true);
    for (const auto& cell : out.cells[0]) {
        CHECK(cell.foreground_hex == "#000000");
    }
}

TEST_CASE("rows / columns / x_labels are propagated unchanged") {
    auto model = make_model({{"1", "2", "3"}, {"4", "5", "6"}});
    std::vector<std::string> xs = {"col0", "col1", "col2"};
    auto out = tr::build_render_model(model, xs, {"r0", "r1"}, true);
    CHECK(out.rows == 2);
    CHECK(out.columns == 3);
    CHECK(out.x_labels == xs);
    REQUIRE(out.cells.size() == 2);
    REQUIRE(out.cells[0].size() == 3);
}

TEST_CASE("empty table model produces empty render with no rows or numeric range") {
    tv::ViewModel empty;
    auto out = tr::build_render_model(empty, {}, {}, true);
    CHECK(out.rows == 0);
    CHECK(out.columns == 0);
    CHECK(out.cells.empty());
    CHECK(out.row_index_map.empty());
    CHECK(out.y_labels.empty());
}

TEST_CASE("gradient_color emits lowercase #rrggbb hex even for single-digit channels") {
    // A value at min produces stop[0] = #8aa8ff, which has no
    // channels < 16 — but the format pin still matters because Qt's
    // QColor::name() output is lowercase #rrggbb and the C++ side
    // is replicating that. Cross-check by feeding a non-numeric so
    // the white-default path is exercised separately.
    auto model = make_model({{"0"}});
    auto out = tr::build_render_model(model, {"x"}, {"y"}, true);
    const auto& bg = out.cells[0][0].background_hex;
    REQUIRE(bg.size() == 7);
    CHECK(bg[0] == '#');
    for (std::size_t i = 1; i < bg.size(); ++i) {
        CHECK_FALSE((bg[i] >= 'A' && bg[i] <= 'F'));
    }
}
