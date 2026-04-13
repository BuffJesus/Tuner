// SPDX-License-Identifier: MIT
//
// tuner_core::speeduino_live_data_decoder — pure-logic port of the
// runtime telemetry decode loop in `SpeeduinoControllerClient.read_runtime`.
// Fifth sub-slice of the Phase 14 comms-layer port (Slice 3).
//
// The decoder takes a list of output-channel layouts (each carrying a
// name, units, and the scalar codec layout fields), figures out how
// many bytes the runtime packet needs to hold, and decodes a payload
// buffer into a vector of `{name, value, units}` snapshots — exactly
// the shape `OutputChannelSnapshot` carries on the Python side.
//
// No Qt / I/O dependency. The future C++ runtime service will issue
// the actual `runtime_request` (already ported in
// `speeduino_protocol`), feed the response bytes into this decoder,
// and forward the snapshot to the dashboard / live VE Analyze
// pipeline.

#pragma once

#include "tuner_core/speeduino_param_codec.hpp"

#include <cstddef>
#include <span>
#include <string>
#include <vector>

namespace tuner_core::speeduino_live_data_decoder {

struct OutputChannelLayout {
    std::string name;
    std::string units;
    speeduino_param_codec::ScalarLayout layout;
};

struct OutputChannelValue {
    std::string name;
    double value = 0.0;
    std::string units;
};

// Compute the minimum runtime packet length that covers every channel
// in `channels`. Mirrors the `max(offset + data_size)` calculation in
// `read_runtime`. Channels are scanned in input order; missing data
// types throw via the underlying value codec.
std::size_t runtime_packet_size(std::span<const OutputChannelLayout> channels);

// Decode `payload` against `channels` and return one
// `OutputChannelValue` per channel. Mirrors the list comprehension in
// `read_runtime` — channels are decoded via `decode_scalar` and the
// result carries the original `name` / `units` from the layout.
//
// Throws via the underlying scalar codec if `payload` is shorter than
// `runtime_packet_size(channels)`.
std::vector<OutputChannelValue> decode_runtime_packet(
    std::span<const OutputChannelLayout> channels,
    std::span<const std::uint8_t> payload);

}  // namespace tuner_core::speeduino_live_data_decoder
