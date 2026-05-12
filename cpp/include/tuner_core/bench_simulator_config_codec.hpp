// SPDX-License-Identifier: MIT
//
// tuner_core::bench_simulator::config_codec — port of the byte
// (de)serializer for the `configTable` PODs exchanged over the
// Ardu-Stim host serial protocol via the `c` (host→firmware) and
// `C` (firmware→host) commands.
//
// Phase 17 Slice B. Pure bytes — no I/O. Slice C (`protocol`) wraps
// these helpers in the `c`/`C` command shapes, and Slice D
// (`controller`) sequences them over `SerialTransport`.
//
// Mirrors `resources/Ardu-Stim-master/ardustim/ardustim/globals.h`:
//
//     struct configTable {
//       uint8_t version;
//       uint8_t wheel = FOUR_TWENTY_A;
//       uint8_t mode;             // LINEAR_SWEPT_RPM=0, FIXED_RPM=1, POT_RPM=2
//       uint16_t fixed_rpm = 2500;
//       uint16_t sweep_low_rpm = 250;
//       uint16_t sweep_high_rpm = 4000;
//       uint16_t sweep_interval = 1000;
//       //11    <-- v1 cuts off here (11 bytes total)
//       bool useCompression = false;
//       uint8_t compressionType = 0;
//       uint16_t compressionRPM = 400;
//       uint16_t compressionOffset = 0;
//       bool compressionDynamic = false;
//     } __attribute__ ((packed));
//
// All multi-byte integers are AVR-native **little-endian** on the
// wire. `bool` is one byte (the firmware uses Arduino `bool` ⇒
// uint8_t under the hood, 0 = false / non-zero = true).
//
// Version negotiation: the leading byte of every dump from the
// firmware is the schema version. v1 (Speeduino upstream) is 11
// bytes; v2 (modified fork with compression-cycle simulator) is 18
// bytes. `decode_auto` picks the right path by the buffer size and
// the leading version byte.

#pragma once

#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>
#include <vector>

namespace tuner_core::bench_simulator {

// RPM-source mode constants from upstream `enums.h`. These are the
// raw integer values the firmware writes to `config.mode`.
enum class RpmMode : std::uint8_t {
    LINEAR_SWEPT_RPM = 0,
    FIXED_RPM        = 1,
    POT_RPM          = 2,
};

// Compression simulator type constants from upstream `globals.h`.
// Two of the entries are reserved by the firmware but declared
// "not initially supported" (the firmware accepts the constant but
// the ISR path doesn't yet simulate the per-stroke timing).
enum class CompressionType : std::uint8_t {
    CYL1_4STROKE = 0,  // firmware-reserved, not yet simulated
    CYL2_4STROKE = 1,
    CYL3_4STROKE = 2,  // firmware-reserved, not yet simulated
    CYL4_4STROKE = 3,
    CYL6_4STROKE = 4,
    CYL8_4STROKE = 5,
};

// Returns true when the firmware currently simulates this
// compression type (i.e. excludes the two reserved-but-unsupported
// entries). Use for UI gating before staging a compression-enable
// command.
bool is_compression_type_firmware_supported(CompressionType type) noexcept;

// Wizard cross-link helper: given an engine cylinder count, return
// the matching `CompressionType` if (and only if) the firmware
// supports the simulation for that count. Returns `nullopt` for
// counts the firmware doesn't yet handle (1, 3, anything else).
//
// Operator UX intent: when SETUP wizard step 4 records "8 cyl",
// this returns CYL8_4STROKE and the TRIGGERS Simulate panel
// pre-selects it.
std::optional<CompressionType> compression_type_from_cylinders(std::uint8_t cyl) noexcept;

// Schema version constants. The leading byte of the firmware's
// `C` dump.
inline constexpr std::uint8_t kSchemaVersionV1 = 1;
inline constexpr std::uint8_t kSchemaVersionV2 = 2;
inline constexpr std::size_t  kV1ByteSize      = 11;
inline constexpr std::size_t  kV2ByteSize      = 18;

// In-memory mirror of `configTable`. Always-18-byte structurally
// even when decoded from v1; the compression fields stay at their
// default values when v1 is loaded. `version` reflects what was
// observed in the source bytes, so a v1-load → v2-encode round
// trip won't silently upgrade firmware that only speaks v1.
struct BenchSimulatorConfig {
    std::uint8_t  version             = kSchemaVersionV2;
    std::uint8_t  wheel               = 0;       // index into wheel_pattern_catalog
    RpmMode       mode                = RpmMode::LINEAR_SWEPT_RPM;
    std::uint16_t fixed_rpm           = 2500;
    std::uint16_t sweep_low_rpm       = 250;
    std::uint16_t sweep_high_rpm      = 4000;
    std::uint16_t sweep_interval      = 1000;
    // v2-only fields below. Encode/decode for v1 leaves these at
    // their defaults.
    bool             use_compression     = false;
    CompressionType  compression_type    = CompressionType::CYL1_4STROKE;
    std::uint16_t    compression_rpm     = 400;
    std::uint16_t    compression_offset  = 0;
    bool             compression_dynamic = false;
};

// Encode an 18-byte v2 payload. Always emits 18 bytes regardless
// of `config.version`. Use this when you know the firmware speaks
// v2.
std::vector<std::uint8_t> encode_v2(const BenchSimulatorConfig& config);

// Encode an 11-byte v1 payload (compression fields dropped). Use
// this when sending to legacy upstream firmware.
std::vector<std::uint8_t> encode_v1(const BenchSimulatorConfig& config);

// Decode an exactly-18-byte v2 payload. Returns nullopt on size
// mismatch or unknown version byte (≠ 2).
std::optional<BenchSimulatorConfig> decode_v2(std::span<const std::uint8_t> bytes);

// Decode an exactly-11-byte v1 payload. Returns nullopt on size
// mismatch or unknown version byte (≠ 1).
std::optional<BenchSimulatorConfig> decode_v1(std::span<const std::uint8_t> bytes);

// Version-aware decoder. Picks v1 or v2 by buffer size:
//   - 11 bytes  → decode_v1
//   - 18 bytes  → decode_v2
//   - anything else → nullopt
// The leading version byte is also validated against the chosen
// schema; a mismatched (size=18, version=1) buffer returns nullopt.
std::optional<BenchSimulatorConfig> decode_auto(std::span<const std::uint8_t> bytes);

}  // namespace tuner_core::bench_simulator
