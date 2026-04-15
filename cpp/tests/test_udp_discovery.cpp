// SPDX-License-Identifier: MIT
//
// doctest cases for `udp_discovery.hpp` — pure-logic announcement parser.

#include "doctest.h"

#include "tuner_core/udp_discovery.hpp"

using namespace tuner_core::udp_discovery;

TEST_CASE("parse_announcement parses the canonical Airbear 0.2.0 packet") {
    const char* pkt =
        "slave:Dropbear\n"
        "id:0.2.0\n"
        "serial:AA:BB:CC:DD:EE:FF\n"
        "port:2000\n"
        "protocol:TCP\n"
        "connectionState:1\n"
        "projectName:Dropbear\n"
        "name:Dropbear v2.0.1\n";
    auto d = parse_announcement(pkt);
    REQUIRE(d.has_value());
    CHECK(d->slave == "Dropbear");
    CHECK(d->id == "0.2.0");
    CHECK(d->serial == "AA:BB:CC:DD:EE:FF");
    CHECK(d->port == 2000);
    CHECK(d->protocol == "TCP");
    CHECK(d->connection_state == 1);
    CHECK(d->project_name == "Dropbear");
    CHECK(d->name == "Dropbear v2.0.1");
    CHECK(d->raw.size() == std::string(pkt).size());
}

TEST_CASE("parse_announcement returns nullopt without a slave key") {
    CHECK_FALSE(parse_announcement("id:0.2.0\nport:2000\n").has_value());
    CHECK_FALSE(parse_announcement("").has_value());
    CHECK_FALSE(parse_announcement("garbage without colons\n").has_value());
}

TEST_CASE("parse_announcement tolerates trailing whitespace and CRLF") {
    auto d = parse_announcement("slave: Dropbear  \r\n  id:  0.2.0  \r\n");
    REQUIRE(d.has_value());
    CHECK(d->slave == "Dropbear");
    CHECK(d->id == "0.2.0");
}

TEST_CASE("parse_announcement ignores unknown keys but preserves raw") {
    auto d = parse_announcement("slave:Dropbear\nfoo:bar\nport:2000\n");
    REQUIRE(d.has_value());
    CHECK(d->port == 2000);
    CHECK(d->raw.find("foo:bar") != std::string::npos);
}

TEST_CASE("parse_announcement handles malformed port gracefully") {
    auto d = parse_announcement("slave:Dropbear\nport:notanumber\n");
    REQUIRE(d.has_value());
    CHECK(d->port == 0);
}

TEST_CASE("parse_announcement handles a single-line probe (no newline)") {
    auto d = parse_announcement("slave:Dropbear");
    REQUIRE(d.has_value());
    CHECK(d->slave == "Dropbear");
}

TEST_CASE("parse_announcement preserves values containing colons") {
    auto d = parse_announcement("slave:Dropbear\nserial:AA:BB:CC:DD:EE:FF\n");
    REQUIRE(d.has_value());
    CHECK(d->serial == "AA:BB:CC:DD:EE:FF");
}

TEST_CASE("display_label formats name + ip:port") {
    DiscoveredDevice d;
    d.name = "Dropbear v2.0.1";
    d.source_ip = "192.168.1.50";
    d.port = 2000;
    CHECK(d.display_label() == "Dropbear v2.0.1 @ 192.168.1.50:2000");
}

TEST_CASE("display_label falls back to slave and handles missing port") {
    DiscoveredDevice d;
    d.slave = "Dropbear";
    d.source_ip = "192.168.1.50";
    CHECK(d.display_label() == "Dropbear @ 192.168.1.50");
}

TEST_CASE("display_label handles fully empty device") {
    DiscoveredDevice d;
    CHECK(d.display_label() == "Unknown device");
}

TEST_CASE("merge_device dedupes by serial") {
    std::vector<DiscoveredDevice> out;
    DiscoveredDevice a;
    a.slave = "Dropbear";
    a.serial = "AA:BB:CC:DD:EE:FF";
    a.source_ip = "192.168.1.50";
    merge_device(out, a);

    DiscoveredDevice b;
    b.slave = "Dropbear";
    b.serial = "AA:BB:CC:DD:EE:FF";
    b.source_ip = "192.168.1.99";  // moved networks
    merge_device(out, b);

    REQUIRE(out.size() == 1);
    CHECK(out[0].source_ip == "192.168.1.99");
}

TEST_CASE("merge_device dedupes by source_ip+port when serial missing") {
    std::vector<DiscoveredDevice> out;
    DiscoveredDevice a;
    a.slave = "Dropbear";
    a.source_ip = "192.168.1.50";
    a.port = 2000;
    merge_device(out, a);

    DiscoveredDevice b;
    b.slave = "Dropbear";
    b.source_ip = "192.168.1.50";
    b.port = 2000;
    b.name = "Dropbear v2.0.1";
    merge_device(out, b);

    REQUIRE(out.size() == 1);
    CHECK(out[0].name == "Dropbear v2.0.1");
}

TEST_CASE("merge_device keeps distinct devices") {
    std::vector<DiscoveredDevice> out;
    DiscoveredDevice a;
    a.slave = "Dropbear";
    a.serial = "AA:AA:AA:AA:AA:AA";
    merge_device(out, a);

    DiscoveredDevice b;
    b.slave = "Dropbear";
    b.serial = "BB:BB:BB:BB:BB:BB";
    merge_device(out, b);

    CHECK(out.size() == 2);
}
