# Protocol Notes

> Status (2026-04-15): TunerStudio decompiled-source observations below
> are still useful reference for what the incumbent tool supports. The
> C++ desktop implementation follows the architectural separation
> observed here, not the Java class structure. The "Python rewrite
> approach" section below is historical — the C++ native port has
> superseded it; see `docs/architecture.md` for the current shape.

## Source observations

The decompiled Java application ships five distinct transport mechanisms:

### Serial
- `jssc.SerialPort` (jssc-2.8, two versions bundled: `jssc/` and `jssc2.8/`) — primary serial implementation on modern installs
- `gnu.io.RXTXPort` / `RXTXCommDriver` (RXTXcomm) — legacy serial fallback
- `com.ftdi.FTDevice` / `FTD2XX` via JNA (JavaFTD2XX) — direct FTDI USB chip access, bypasses the OS serial driver entirely; ships native `.dll`/`.so` via JNA extraction

### Network
- TCP and UDP via Apache `commons-net-3.6`
- `com/efiAnalytics/tunerStudio/search/ContinuousIpSearchPanel.java` confirms active IP/device discovery on the network

### Bluetooth
- `bluecove-2.1.1` (JSR-82 `javax.bluetooth` API) — Windows/macOS Bluetooth stack
- `bluecove-bluez-2.1.1` — Linux BlueZ binding for the same JSR-82 API

### CAN / XCP
- CAN routing and XCP transport live in obfuscated packages (`Z`, `B`, `bQ`, `aV`)
- XCP CRC confirmed in `com/efiAnalytics/xcp/master/responseProcessors/CrcProcessor.java`

### Protocol separation confirmed
At the plugin API level, burn and parameter-write are explicitly separate operations:
- `ControllerParameterServer.updateParameter(...)` — writes to ECU RAM
- `BurnExecutor.burnData(configName)` — burns RAM to flash
- `OnlineExecution.goOnline()` / `goOffline()` — connection lifecycle distinct from data operations

Representative source references from the decompiled tree:

- `com/efiAnalytics/xcp/master/responseProcessors/CrcProcessor.java`
- `com/efiAnalytics/tunerStudio/search/ContinuousIpSearchPanel.java`
- transport-heavy packages `Z`, `B`, `bQ`, `aV`

## Architectural approach (C++ native port)

The port follows the separation observed in the decompiled Java and
Python-reference trees:

- `tuner_core::transport` defines the raw byte I/O boundary (serial, TCP, mock)
- `tuner_core::speeduino_framing` + `speeduino_protocol` handle framing and packet shapes
- `tuner_core::speeduino_controller::SpeeduinoController` owns per-protocol connect/read/write/burn lifecycle
- `tuner_core::xcp_packets` + `xcp_simulator` cover the XCP side (packet layer done; workspace wiring pending)
- Mock transport in `transport::MockTransport` for deterministic protocol tests

## Future runtime telemetry requirements

Later generator, evidence, and autotune phases will need runtime channels that are not just useful for dashboards, but also for validating conservative forced-induction assumptions.

Future telemetry priorities:

- boost pressure
- compressor efficiency estimate
- turbo spool estimation
- boost ramp rate

These signals are intended to support:

- autotune gating and context
- confidence scoring
- VE generator refinement against real behavior

They should stay in the output-channel / runtime-evidence path, not be conflated with tune constants.

## Open questions

Resolved:

- ~~exact project file format and persistence layout~~ — shipped as `.tunerproj` (JSON); see `tuner_core::project_file`.
- ~~tune file encoding details~~ — shipped as `.tuner` (JSON, schema v1.1 with slot metadata and definition hash); see `tuner_core::native_format`.
- ~~controller packet formats by transport~~ — Speeduino raw protocol (legacy 6-byte `'f'`, 43-byte `'K'` FW-003 since Slice 14B) + framed variant (TCP/Airbear with u16 LE length + CRC32). See `tuner_core::speeduino_protocol` + `speeduino_framing`.

Still open:

- XCP workspace integration — packet layer done (`xcp_packets` + `xcp_simulator`); presenter-side page read/write/burn routing not wired into `EcuConnection` yet.
- FTDI direct-access path — not ported; the Java tree's FTD2XX-JNA path is platform-specific and the C++ app uses standard Win32 serial + Winsock TCP instead.
- Boost/spool/compressor runtime channels — partially addressed by the compressor-map modeling service; boost pressure is a standard channel; spool estimation and dynamic compressor efficiency remain derivation targets for a future analysis service.
