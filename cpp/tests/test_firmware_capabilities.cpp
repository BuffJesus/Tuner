// SPDX-License-Identifier: MIT
#include <doctest.h>
#include "tuner_core/firmware_capabilities.hpp"

namespace fc = tuner_core::firmware_capabilities;

TEST_CASE("fw_cap: default has uncertain runtimeStatusA") {
    fc::Capabilities c;
    c.source = "test";
    auto groups = c.uncertain_channel_groups();
    CHECK(groups.count("runtimeStatusA") == 1);
    CHECK(groups.count("boardCapabilities") == 1);
}

TEST_CASE("fw_cap: trusted when supported") {
    fc::Capabilities c;
    c.source = "test";
    c.supports_runtime_status_a = true;
    c.supports_board_capabilities_channel = true;
    c.supports_spi_flash_health_channel = true;
    auto groups = c.uncertain_channel_groups();
    CHECK(groups.empty());
}

TEST_CASE("fw_cap: trust summary includes runtimeStatusA") {
    fc::Capabilities c;
    c.source = "test";
    c.supports_runtime_status_a = true;
    CHECK(c.runtime_trust_summary().find("trusted") != std::string::npos);
}

TEST_CASE("fw_cap: trust summary uncertain when not supported") {
    fc::Capabilities c;
    c.source = "test";
    CHECK(c.runtime_trust_summary().find("uncertain") != std::string::npos);
}

TEST_CASE("fw_cap: live_data_size in summary") {
    fc::Capabilities c;
    c.source = "test";
    c.live_data_size = 212;
    CHECK(c.runtime_trust_summary().find("212") != std::string::npos);
}
