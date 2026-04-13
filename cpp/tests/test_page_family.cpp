// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::page_family.

#include "doctest.h"

#include "tuner_core/page_family.hpp"

#include <vector>

using namespace tuner_core::page_family;

namespace {

PageInput make_page(std::string id, std::string title, int page_number = -1) {
    PageInput p;
    p.page_id = std::move(id);
    p.title = std::move(title);
    if (page_number >= 0) p.page_number = page_number;
    return p;
}

}  // namespace

// ---------------------------------------------------------------------------
// family_id_for_title
// ---------------------------------------------------------------------------

TEST_CASE("family_id_for_title: known families") {
    CHECK(family_id_for_title("VE Table").value() == "fuel-tables");
    CHECK(family_id_for_title("Second Fuel Table").value() == "fuel-tables");
    CHECK(family_id_for_title("Spark Table").value() == "spark-tables");
    CHECK(family_id_for_title("Second Spark Table").value() == "spark-tables");
    CHECK(family_id_for_title("AFR Target Table").value() == "target-tables");
    CHECK(family_id_for_title("Lambda Target Table").value() == "target-tables");
    CHECK(family_id_for_title("VVT Target/Duty").value() == "vvt");
    CHECK(family_id_for_title("VVT2 Target/Duty").value() == "vvt");
    CHECK(family_id_for_title("VVT Control").value() == "vvt");
    CHECK(family_id_for_title("Sequential Fuel Trim (1-4)").value() == "fuel-trims");
    CHECK(family_id_for_title("Fuel Trim Table 2").value() == "fuel-trims");
}

TEST_CASE("family_id_for_title: unknown title") {
    CHECK_FALSE(family_id_for_title("Engine Constants").has_value());
    CHECK_FALSE(family_id_for_title("").has_value());
}

// ---------------------------------------------------------------------------
// family_title_for
// ---------------------------------------------------------------------------

TEST_CASE("family_title_for: display titles for every known family") {
    CHECK(family_title_for("fuel-trims") == "Fuel Trims");
    CHECK(family_title_for("fuel-tables") == "Fuel Tables");
    CHECK(family_title_for("spark-tables") == "Spark Tables");
    CHECK(family_title_for("target-tables") == "Target Tables");
    CHECK(family_title_for("vvt") == "VVT");
}

// ---------------------------------------------------------------------------
// tab_title_for
// ---------------------------------------------------------------------------

TEST_CASE("tab_title_for: fuel-trims sequential ranges") {
    CHECK(tab_title_for("fuel-trims", "Sequential Fuel Trim (1-4)") == "Seq 1-4");
    CHECK(tab_title_for("fuel-trims", "Sequential Fuel Trim (5-8)") == "Seq 5-8");
    CHECK(tab_title_for("fuel-trims", "Sequential Fuel Trim Settings") == "Settings");
}

TEST_CASE("tab_title_for: fuel-trims numbered tables use Trim N format") {
    CHECK(tab_title_for("fuel-trims", "Fuel Trim Table 2") == "Trim 2");
    CHECK(tab_title_for("fuel-trims", "Fuel Trim Table 7") == "Trim 7");
}

TEST_CASE("tab_title_for: fuel-tables Primary vs Secondary") {
    CHECK(tab_title_for("fuel-tables", "VE Table") == "Primary");
    CHECK(tab_title_for("fuel-tables", "Second Fuel Table") == "Secondary");
}

TEST_CASE("tab_title_for: spark-tables Primary vs Secondary") {
    CHECK(tab_title_for("spark-tables", "Spark Table") == "Primary");
    CHECK(tab_title_for("spark-tables", "Second Spark Table") == "Secondary");
}

TEST_CASE("tab_title_for: target-tables AFR vs Lambda") {
    CHECK(tab_title_for("target-tables", "AFR Target Table") == "AFR");
    CHECK(tab_title_for("target-tables", "Lambda Target Table") == "Lambda");
}

TEST_CASE("tab_title_for: vvt all three tabs") {
    CHECK(tab_title_for("vvt", "VVT Target/Duty") == "VVT1");
    CHECK(tab_title_for("vvt", "VVT2 Target/Duty") == "VVT2");
    CHECK(tab_title_for("vvt", "VVT Control") == "Control");
}

// ---------------------------------------------------------------------------
// build_index
// ---------------------------------------------------------------------------

TEST_CASE("build_index: empty list yields empty index") {
    auto idx = build_index({});
    CHECK(idx.empty());
}

TEST_CASE("build_index: singleton family is dropped") {
    auto idx = build_index({make_page("p1", "VE Table")});
    CHECK(idx.empty());
}

TEST_CASE("build_index: pair of fuel tables produces a family") {
    auto idx = build_index({
        make_page("p1", "VE Table"),
        make_page("p2", "Second Fuel Table"),
    });
    REQUIRE(idx.size() == 2);
    REQUIRE(idx.count("p1") == 1);
    REQUIRE(idx.count("p2") == 1);
    const auto& family = idx.at("p1");
    CHECK(family.family_id == "fuel-tables");
    CHECK(family.title == "Fuel Tables");
    REQUIRE(family.tabs.size() == 2);
    CHECK(family.tabs[0].title == "Primary");
    CHECK(family.tabs[1].title == "Secondary");
}

TEST_CASE("build_index: spark and target tables are independent families") {
    auto idx = build_index({
        make_page("p1", "Spark Table"),
        make_page("p2", "Second Spark Table"),
        make_page("p3", "AFR Target Table"),
        make_page("p4", "Lambda Target Table"),
    });
    REQUIRE(idx.size() == 4);
    CHECK(idx.at("p1").family_id == "spark-tables");
    CHECK(idx.at("p3").family_id == "target-tables");
}

TEST_CASE("build_index: vvt family with all three tabs sorted") {
    auto idx = build_index({
        make_page("p3", "VVT Control"),
        make_page("p1", "VVT Target/Duty"),
        make_page("p2", "VVT2 Target/Duty"),
    });
    REQUIRE(idx.size() == 3);
    const auto& family = idx.at("p1");
    REQUIRE(family.tabs.size() == 3);
    CHECK(family.tabs[0].title == "VVT1");
    CHECK(family.tabs[1].title == "VVT2");
    CHECK(family.tabs[2].title == "Control");
}

TEST_CASE("build_index: sort respects page_number first") {
    auto idx = build_index({
        make_page("late", "VE Table", 5),
        make_page("early", "Second Fuel Table", 1),
    });
    REQUIRE(idx.size() == 2);
    const auto& family = idx.at("early");
    REQUIRE(family.tabs.size() == 2);
    // Page 1 comes first regardless of tab_sort_key
    CHECK(family.tabs[0].page_id == "early");
    CHECK(family.tabs[1].page_id == "late");
}
