// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::MsqParser. Mirror the Python
// MsqParser/MsqWriteService test surface so the cross-validation
// (see tests/unit/test_cpp_msq_parser_parity.py on the Python side)
// can lean on identical fixtures.

#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include "doctest.h"

#include "tuner_core/msq_parser.hpp"

#include <map>
#include <string>

namespace {

constexpr std::string_view kSampleMsq = R"(<?xml version="1.0" encoding="ISO-8859-1"?>
<msq xmlns="http://www.msefi.com/:msq">
  <versionInfo signature="speeduino 202501-T41" fileFormat="2" nPages="1"/>
  <page number="1">
    <constant name="reqFuel" units="ms" digits="1">8.5</constant>
    <constant name="nCylinders" units="cyl">4</constant>
    <constant name="veTable" units="%" rows="2" cols="2" digits="1">
         50 55
         60 65
      </constant>
  </page>
</msq>
)";

}  // namespace

TEST_CASE("parse_msq_text reads versionInfo metadata") {
    auto doc = tuner_core::parse_msq_text(kSampleMsq);
    CHECK(doc.signature == "speeduino 202501-T41");
    CHECK(doc.file_format == "2");
    CHECK(doc.page_count == 1);
}

TEST_CASE("parse_msq_text returns one entry per <constant>") {
    auto doc = tuner_core::parse_msq_text(kSampleMsq);
    REQUIRE(doc.constants.size() == 3);

    auto by_name = [&](std::string_view name) -> const tuner_core::MsqConstant* {
        for (const auto& c : doc.constants) {
            if (c.name == name) return &c;
        }
        return nullptr;
    };

    auto* req = by_name("reqFuel");
    REQUIRE(req != nullptr);
    CHECK(req->units == "ms");
    CHECK(req->digits == 1);
    CHECK(req->text == "8.5");

    auto* ve = by_name("veTable");
    REQUIRE(ve != nullptr);
    CHECK(ve->rows == 2);
    CHECK(ve->cols == 2);
    CHECK(ve->units == "%");
    // Inner text preserved verbatim including the leading newline + indent.
    CHECK(ve->text.find("50 55") != std::string::npos);
    CHECK(ve->text.find("60 65") != std::string::npos);
}

TEST_CASE("write_msq_text without updates is byte-stable") {
    std::map<std::string, std::string> updates;
    std::string rewritten = tuner_core::write_msq_text(kSampleMsq, updates);
    CHECK(rewritten == std::string(kSampleMsq));
}

TEST_CASE("write_msq_text replaces inner text for known constants") {
    std::map<std::string, std::string> updates{
        {"reqFuel", "9.5"},
    };
    std::string rewritten = tuner_core::write_msq_text(kSampleMsq, updates);
    CHECK(rewritten.find(">9.5<") != std::string::npos);
    CHECK(rewritten.find(">8.5<") == std::string::npos);
    // Other constants untouched
    CHECK(rewritten.find(">4<") != std::string::npos);
}

TEST_CASE("write_msq_text replaces multi-line table payload verbatim") {
    std::map<std::string, std::string> updates{
        {"veTable", "\n         70 75\n         80 85\n      "},
    };
    std::string rewritten = tuner_core::write_msq_text(kSampleMsq, updates);
    CHECK(rewritten.find("70 75") != std::string::npos);
    CHECK(rewritten.find("80 85") != std::string::npos);
    CHECK(rewritten.find("50 55") == std::string::npos);
}

TEST_CASE("write_msq_text drops updates for unknown constants") {
    // Mirrors the documented Python MsqWriteService default
    // (insert_missing=False) — names that don't exist in the source
    // XML are silently dropped instead of injected.
    std::map<std::string, std::string> updates{
        {"sparkTable", "1 2 3 4"},
    };
    std::string rewritten = tuner_core::write_msq_text(kSampleMsq, updates);
    CHECK(rewritten.find("sparkTable") == std::string::npos);
    CHECK(rewritten == std::string(kSampleMsq));
}

TEST_CASE("write_msq_text leaves the entire document tail intact") {
    std::map<std::string, std::string> updates{{"reqFuel", "1.0"}};
    std::string rewritten = tuner_core::write_msq_text(kSampleMsq, updates);
    CHECK(rewritten.rfind("</msq>") != std::string::npos);
    CHECK(rewritten.rfind("</page>") != std::string::npos);
}

TEST_CASE("parse_msq_text rejects truly malformed input gracefully") {
    // Unterminated <constant> must throw a clear runtime_error so the
    // Python wrapper can surface it as a ValueError.
    constexpr std::string_view broken = R"(<msq><constant name="x">unclosed)";
    CHECK_THROWS_AS(tuner_core::parse_msq_text(broken), std::runtime_error);
}

// ---------------------------------------------------------------------------
// Sub-slice 89: insert_missing mode
// ---------------------------------------------------------------------------

namespace {

constexpr std::string_view kMinimalMsq = R"(<?xml version="1.0" encoding="ISO-8859-1"?>
<msq xmlns="http://www.msefi.com/:msq">
  <versionInfo signature="speeduino 202501-T41" fileFormat="2" nPages="1"/>
  <page number="1">
    <constant name="reqFuel" units="ms" digits="1">8.5</constant>
  </page>
</msq>
)";

}  // namespace

TEST_CASE("format_msq_scalar renders integers without a decimal") {
    CHECK(tuner_core::format_msq_scalar(6.0) == "6");
    CHECK(tuner_core::format_msq_scalar(0.0) == "0");
    CHECK(tuner_core::format_msq_scalar(-3.0) == "-3");
    // Non-integer floats keep their decimal part and strip trailing zeros.
    CHECK(tuner_core::format_msq_scalar(8.5) == "8.5");
    CHECK(tuner_core::format_msq_scalar(1.25) == "1.25");
}

TEST_CASE("format_msq_table produces Python-style multi-line layout") {
    auto text = tuner_core::format_msq_table({50, 55, 60, 65}, 2, 2);
    // Leading newline, each row prefixed with 9 spaces + space-joined
    // values + trailing space + newline, tail "      " indent line.
    CHECK(text == "\n         50 55 \n         60 65 \n      ");
}

TEST_CASE("format_msq_table handles single-row tables") {
    auto text = tuner_core::format_msq_table({10, 20, 30}, 1, 3);
    CHECK(text == "\n         10 20 30 \n      ");
}

TEST_CASE("write_msq_text_with_insertions is a no-op when insertions empty") {
    std::map<std::string, std::string> updates;
    std::vector<tuner_core::MsqInsertion> insertions;
    auto out = tuner_core::write_msq_text_with_insertions(kMinimalMsq, updates, insertions);
    CHECK(out == std::string(kMinimalMsq));
}

TEST_CASE("write_msq_text_with_insertions injects a missing table constant") {
    std::vector<tuner_core::MsqInsertion> insertions;
    insertions.push_back(tuner_core::MsqInsertion{
        "veTable",
        tuner_core::format_msq_table({50, 55, 60, 65}, 2, 2),
        "%", 2, 2, -1,
    });
    auto out = tuner_core::write_msq_text_with_insertions(kMinimalMsq, {}, insertions);
    // New constant lands inside the first <page> element.
    auto ve_pos = out.find("name=\"veTable\"");
    REQUIRE(ve_pos != std::string::npos);
    auto page_close = out.find("</page>");
    CHECK(ve_pos < page_close);
    // Attributes landed correctly.
    CHECK(out.find("units=\"%\"") != std::string::npos);
    CHECK(out.find("rows=\"2\" cols=\"2\"") != std::string::npos);
    // Table values landed in the inner text.
    CHECK(out.find("50 55") != std::string::npos);
    CHECK(out.find("60 65") != std::string::npos);
    // Reqfuel preserved untouched.
    CHECK(out.find("reqFuel") != std::string::npos);
    CHECK(out.find(">8.5<") != std::string::npos);
}

TEST_CASE("write_msq_text_with_insertions injects a missing scalar") {
    std::vector<tuner_core::MsqInsertion> insertions;
    insertions.push_back(tuner_core::MsqInsertion{
        "nCylinders",
        tuner_core::format_msq_scalar(6.0),
        "", 0, 0, -1,
    });
    auto out = tuner_core::write_msq_text_with_insertions(kMinimalMsq, {}, insertions);
    CHECK(out.find("name=\"nCylinders\"") != std::string::npos);
    CHECK(out.find(">6<") != std::string::npos);
    // No rows/cols attributes for scalar entries.
    auto ncyl_start = out.find("name=\"nCylinders\"");
    auto ncyl_end = out.find(">", ncyl_start);
    std::string opening_tag = out.substr(ncyl_start, ncyl_end - ncyl_start);
    CHECK(opening_tag.find("rows=") == std::string::npos);
    CHECK(opening_tag.find("cols=") == std::string::npos);
}

TEST_CASE("write_msq_text_with_insertions skips names already present") {
    // An insertion named `reqFuel` must be ignored — reqFuel already
    // exists in the source and the Python loop has a pre-skip clause.
    std::vector<tuner_core::MsqInsertion> insertions;
    insertions.push_back(tuner_core::MsqInsertion{
        "reqFuel", "9999", "ms", 0, 0, 1,
    });
    auto out = tuner_core::write_msq_text_with_insertions(kMinimalMsq, {}, insertions);
    // The original inner text is preserved; the bogus 9999 never appears.
    CHECK(out.find("9999") == std::string::npos);
    CHECK(out.find(">8.5<") != std::string::npos);
    // And there's still exactly one reqFuel entry.
    std::size_t first = out.find("name=\"reqFuel\"");
    std::size_t second = out.find("name=\"reqFuel\"", first + 1);
    CHECK(second == std::string::npos);
}

TEST_CASE("write_msq_text_with_insertions is idempotent on re-save") {
    // Inserting, then re-running with the same insertions on the new
    // output must be a no-op (insertions are already present).
    std::vector<tuner_core::MsqInsertion> insertions;
    insertions.push_back(tuner_core::MsqInsertion{
        "sparkTable",
        tuner_core::format_msq_table({15, 18, 22, 26}, 2, 2),
        "deg", 2, 2, -1,
    });
    auto first_pass = tuner_core::write_msq_text_with_insertions(kMinimalMsq, {}, insertions);
    auto second_pass = tuner_core::write_msq_text_with_insertions(first_pass, {}, insertions);
    CHECK(first_pass == second_pass);
}

TEST_CASE("write_msq_text_with_insertions composes with update pass") {
    // updates modify existing inner text, insertions inject new nodes —
    // both layers apply in one call without interfering.
    std::map<std::string, std::string> updates{{"reqFuel", "9.0"}};
    std::vector<tuner_core::MsqInsertion> insertions;
    insertions.push_back(tuner_core::MsqInsertion{
        "nCylinders",
        tuner_core::format_msq_scalar(8.0),
        "", 0, 0, -1,
    });
    auto out = tuner_core::write_msq_text_with_insertions(kMinimalMsq, updates, insertions);
    CHECK(out.find(">9.0<") != std::string::npos);
    CHECK(out.find(">8.5<") == std::string::npos);
    CHECK(out.find("name=\"nCylinders\"") != std::string::npos);
    CHECK(out.find(">8<") != std::string::npos);
}
