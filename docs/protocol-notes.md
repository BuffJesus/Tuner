# Protocol Notes

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

## Python rewrite approach

- define raw `Transport` objects first
- place framing and packet logic in `comms`
- keep per-protocol concerns behind `ControllerClient`
- add a deterministic `MockTransport` for protocol tests

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

- exact project file format and persistence layout
- tune file encoding details
- controller packet formats by transport (framing bytes, command set)
- XCP dialect specifics and CAN routing topology
- firmware-specific quirks currently hidden in obfuscated classes
- conditions under which FTDI direct-access path is selected vs serial driver path
- jssc vs RXTX selection logic (version negotiation or platform-based?)
- which runtime channels are available or derivable for boost pressure, spool estimation, and compressor-efficiency approximations across supported controllers
