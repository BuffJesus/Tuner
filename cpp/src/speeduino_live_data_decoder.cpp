// SPDX-License-Identifier: MIT
//
// tuner_core::speeduino_live_data_decoder implementation. Pure-logic.

#include "tuner_core/speeduino_live_data_decoder.hpp"

#include "tuner_core/speeduino_value_codec.hpp"

#include <algorithm>

namespace tuner_core::speeduino_live_data_decoder {

namespace vc = speeduino_value_codec;

std::size_t runtime_packet_size(std::span<const OutputChannelLayout> channels) {
    std::size_t total = 0;
    for (const auto& ch : channels) {
        const auto size = vc::data_size_bytes(ch.layout.data_type);
        total = std::max(total, ch.layout.offset + size);
    }
    return total;
}

std::vector<OutputChannelValue> decode_runtime_packet(
    std::span<const OutputChannelLayout> channels,
    std::span<const std::uint8_t> payload) {
    std::vector<OutputChannelValue> out;
    out.reserve(channels.size());
    for (const auto& ch : channels) {
        OutputChannelValue v;
        v.name = ch.name;
        v.units = ch.units;
        v.value = speeduino_param_codec::decode_scalar(ch.layout, payload);
        out.push_back(std::move(v));
    }
    return out;
}

}  // namespace tuner_core::speeduino_live_data_decoder
