// SPDX-License-Identifier: MIT
//
// doctest cases for `mdns_discovery.hpp` -- pure-logic normalization and
// merge behavior. The actual OS resolver call remains unmocked.

#include "doctest.h"

#include "tuner_core/mdns_discovery.hpp"

using namespace tuner_core::mdns_discovery;

TEST_CASE("normalize_hostname trims and lowercases .local names") {
    auto host = normalize_hostname("  Speeduino.LOCAL  ");
    REQUIRE(host.has_value());
    CHECK(*host == "speeduino.local");
}

TEST_CASE("normalize_hostname rejects non-local names") {
    CHECK_FALSE(normalize_hostname("").has_value());
    CHECK_FALSE(normalize_hostname("speeduino").has_value());
    CHECK_FALSE(normalize_hostname("example.com").has_value());
}

TEST_CASE("display_label renders hostname ip and port") {
    ResolvedHost host;
    host.hostname = "speeduino.local";
    host.ip_address = "192.168.1.50";
    host.port = 2000;
    CHECK(host.display_label() == "speeduino.local @ 192.168.1.50:2000 (mDNS)");
}

TEST_CASE("merge_result dedupes by ip and port") {
    std::vector<ResolvedHost> out;

    ResolvedHost first;
    first.hostname = "speeduino.local";
    first.ip_address = "192.168.1.50";
    first.port = 2000;
    merge_result(out, first);

    ResolvedHost second;
    second.hostname = "dropbear.local";
    second.ip_address = "192.168.1.50";
    second.port = 2000;
    merge_result(out, second);

    REQUIRE(out.size() == 1);
    CHECK(out[0].hostname == "dropbear.local");
}

TEST_CASE("merge_result falls back to normalized hostname when ip missing") {
    std::vector<ResolvedHost> out;

    ResolvedHost first;
    first.hostname = "Speeduino.LOCAL";
    first.port = 2000;
    merge_result(out, first);

    ResolvedHost second;
    second.hostname = " speeduino.local ";
    second.port = 2000;
    second.ip_address = "192.168.1.50";
    merge_result(out, second);

    REQUIRE(out.size() == 1);
    CHECK(out[0].hostname == "speeduino.local");
    CHECK(out[0].ip_address == "192.168.1.50");
}

TEST_CASE("merge_result keeps distinct hosts") {
    std::vector<ResolvedHost> out;

    ResolvedHost first;
    first.hostname = "speeduino.local";
    first.ip_address = "192.168.1.50";
    first.port = 2000;
    merge_result(out, first);

    ResolvedHost second;
    second.hostname = "other.local";
    second.ip_address = "192.168.1.51";
    second.port = 2000;
    merge_result(out, second);

    CHECK(out.size() == 2);
}
