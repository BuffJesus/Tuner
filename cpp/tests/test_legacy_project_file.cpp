// SPDX-License-Identifier: MIT
//
// doctest cases for `legacy_project_file.hpp`.

#include "doctest.h"

#include "tuner_core/legacy_project_file.hpp"

using namespace tuner_core::legacy_project_file;

TEST_CASE("parse_key_value_lines: skips empty + comment lines, splits on =") {
    std::vector<std::string> lines = {
        "",
        "# leading comment",
        "; semicolon comment",
        "// double-slash comment",
        "projectName=My Project",
        "ecuDefinition=defs/speeduino.ini",
        "  spaced.key  =  spaced value  ",
    };
    auto m = parse_key_value_lines(lines);
    REQUIRE(m.size() == 3);
    CHECK(m["projectName"] == "My Project");
    CHECK(m["ecuDefinition"] == "defs/speeduino.ini");
    CHECK(m["spaced.key"] == "spaced value");
}

TEST_CASE("parse_key_value_lines: falls back to ':' when '=' is absent") {
    std::vector<std::string> lines = {
        "key1: value1",
        "key2 = value2",
        "no-separator-line",
    };
    auto m = parse_key_value_lines(lines);
    REQUIRE(m.size() == 2);
    CHECK(m["key1"] == "value1");
    CHECK(m["key2"] == "value2");
}

TEST_CASE("parse_key_value_lines: '=' wins over ':' when both present") {
    auto m = parse_key_value_lines({"a=b:c"});
    CHECK(m["a"] == "b:c");
}

TEST_CASE("parse_default_connection_profile: returns nullopt for empty metadata") {
    std::map<std::string, std::string> meta;
    CHECK(parse_default_connection_profile(meta) == std::nullopt);
}

TEST_CASE("parse_default_connection_profile: ignores non-prefix keys") {
    std::map<std::string, std::string> meta = {
        {"projectName", "X"},
        {"ecuDefinition", "Y"},
    };
    CHECK(parse_default_connection_profile(meta) == std::nullopt);
}

TEST_CASE("parse_default_connection_profile: full TCP profile") {
    std::map<std::string, std::string> meta = {
        {"connection.default.name",      "Speeduino TCP"},
        {"connection.default.transport", "tcp"},
        {"connection.default.protocol",  "speeduino"},
        {"connection.default.host",      "192.168.4.1"},
        {"connection.default.port",      "2000"},
        {"connection.default.baudRate",  "115200"},
    };
    auto p = parse_default_connection_profile(meta);
    REQUIRE(p.has_value());
    CHECK(p->name == "Speeduino TCP");
    CHECK(p->transport == "tcp");
    REQUIRE(p->protocol.has_value());
    CHECK(*p->protocol == "speeduino");
    REQUIRE(p->host.has_value());
    CHECK(*p->host == "192.168.4.1");
    REQUIRE(p->port.has_value());
    CHECK(*p->port == 2000);
    REQUIRE(p->baud_rate.has_value());
    CHECK(*p->baud_rate == 115200);
    CHECK(!p->serial_port.has_value());
}

TEST_CASE("parse_default_connection_profile: defaults name and transport") {
    std::map<std::string, std::string> meta = {
        {"connection.default.host", "localhost"},
    };
    auto p = parse_default_connection_profile(meta);
    REQUIRE(p.has_value());
    CHECK(p->name == "Default");
    CHECK(p->transport == "mock");
}

TEST_CASE("parse_default_connection_profile: malformed port falls back to nullopt") {
    std::map<std::string, std::string> meta = {
        {"connection.default.name", "X"},
        {"connection.default.port", "not-a-number"},
        {"connection.default.baudRate", "115200abc"},
    };
    auto p = parse_default_connection_profile(meta);
    REQUIRE(p.has_value());
    CHECK(!p->port.has_value());
    CHECK(!p->baud_rate.has_value());
}

TEST_CASE("sanitize_project_name: alnum + dash + underscore survive") {
    CHECK(sanitize_project_name("Speeduino-Project_42") == "Speeduino-Project_42");
}

TEST_CASE("sanitize_project_name: spaces and punctuation become underscores") {
    CHECK(sanitize_project_name("My Project Name") == "My_Project_Name");
    CHECK(sanitize_project_name("a/b\\c") == "a_b_c");
}

TEST_CASE("sanitize_project_name: leading and trailing underscores trimmed") {
    CHECK(sanitize_project_name("___leading") == "leading");
    CHECK(sanitize_project_name("trailing___") == "trailing");
    CHECK(sanitize_project_name("___both___") == "both");
}

TEST_CASE("sanitize_project_name: leading/trailing whitespace stripped first") {
    CHECK(sanitize_project_name("  spaced  ") == "spaced");
}

TEST_CASE("sanitize_project_name: empty result allowed") {
    CHECK(sanitize_project_name("") == "");
    CHECK(sanitize_project_name("   ") == "");
    CHECK(sanitize_project_name("___") == "");
    CHECK(sanitize_project_name("$$$") == "");
}

TEST_CASE("format_legacy_project_file: minimal model writes only projectName") {
    LegacyProjectModel m;
    m.name = "Bare";
    auto out = format_legacy_project_file(m);
    CHECK(out == "projectName=Bare\n");
}

TEST_CASE("format_legacy_project_file: full model writes every section in order") {
    LegacyProjectModel m;
    m.name = "Ford 300 Twin GT28";
    m.ecu_definition_path = "defs/speeduino.ini";
    m.tune_file_path = "tunes/base.msq";
    m.dashboards = {"primary", "secondary"};
    m.active_settings = {"LAMBDA", "mcu_teensy"};

    ConnectionProfile p;
    p.name = "Speeduino USB";
    p.transport = "serial";
    p.protocol = "speeduino";
    p.serial_port = "COM3";
    p.baud_rate = 115200;
    m.connection_profiles.push_back(p);

    m.metadata["customNote"] = "remember to recheck dwell";

    auto out = format_legacy_project_file(m);
    CHECK(out ==
        "projectName=Ford 300 Twin GT28\n"
        "ecuDefinition=defs/speeduino.ini\n"
        "tuneFile=tunes/base.msq\n"
        "dashboards=primary,secondary\n"
        "activeSettings=LAMBDA,mcu_teensy\n"
        "connection.default.name=Speeduino USB\n"
        "connection.default.transport=serial\n"
        "connection.default.protocol=speeduino\n"
        "connection.default.serialPort=COM3\n"
        "connection.default.baudRate=115200\n"
        "customNote=remember to recheck dwell\n");
}

TEST_CASE("format_legacy_project_file: active_settings sorted before joining") {
    LegacyProjectModel m;
    m.name = "X";
    m.active_settings = {"zeta", "alpha", "mike"};
    auto out = format_legacy_project_file(m);
    CHECK(out == "projectName=X\nactiveSettings=alpha,mike,zeta\n");
}

TEST_CASE("format_legacy_project_file: structured-field metadata keys are skipped from spillover") {
    LegacyProjectModel m;
    m.name = "Spillover";
    m.ecu_definition_path = "defs.ini";
    // These should NOT be written from metadata — the structured
    // field above already wrote ecuDefinition.
    m.metadata["projectName"] = "should-be-skipped";
    m.metadata["ecuDefinition"] = "should-be-skipped";
    m.metadata["tuneFile"] = "should-be-skipped";
    m.metadata["dashboards"] = "should-be-skipped";
    m.metadata["activeSettings"] = "should-be-skipped";
    m.metadata["connection.default.name"] = "should-be-skipped";
    m.metadata["customField"] = "kept";
    auto out = format_legacy_project_file(m);
    CHECK(out ==
        "projectName=Spillover\n"
        "ecuDefinition=defs.ini\n"
        "customField=kept\n");
}
