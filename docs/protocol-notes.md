# Protocol Notes

> Status (2026-05-11): TunerStudio decompiled-source observations below
> are kept as a **historical parity oracle** for what the incumbent
> tool supported. The C++ desktop implementation follows the
> architectural separation observed here, not the Java class structure.
> The "Python rewrite approach" section below is historical — the C++
> native port has superseded it; see `docs/architecture.md` for the
> current shape.
>
> **Focus shift (Phase 18, see `tuning-roadmap.md`):** the product
> targets **Speeduino + RusEFI** only. XCP, FTDI-direct, and Bluetooth
> transport sections below are kept as reference but are **not** part
> of the shipped product. The `tuner_core::xcp_packets` +
> `tuner_core::xcp_simulator` clusters are slated for deletion in
> Phase 18 — they were built speculatively (sub-slices 104–105) and
> never wired into `EcuConnection` or any Qt tab.

## Source observations

The decompiled Java application ships five distinct transport mechanisms:

### Serial
- `jssc.SerialPort` (jssc-2.8, two versions bundled: `jssc/` and `jssc2.8/`) — primary serial implementation on modern installs
- `gnu.io.RXTXPort` / `RXTXCommDriver` (RXTXcomm) — legacy serial fallback
- `com.ftdi.FTDevice` / `FTD2XX` via JNA (JavaFTD2XX) — direct FTDI USB chip access, bypasses the OS serial driver entirely; ships native `.dll`/`.so` via JNA extraction

### Network
- TCP and UDP via Apache `commons-net-3.6`
- `com/efiAnalytics/tunerStudio/search/ContinuousIpSearchPanel.java` confirms active IP/device discovery on the network

### Bluetooth (reference only — not in shipped product)
- `bluecove-2.1.1` (JSR-82 `javax.bluetooth` API) — Windows/macOS Bluetooth stack
- `bluecove-bluez-2.1.1` — Linux BlueZ binding for the same JSR-82 API
- **Not implemented in our desktop tuner.** Wireless to the ECU is via Airbear (WiFi/TCP or BLE-via-NUS to a phone) or via a user-wired HC-05 on Speeduino's UART1 (transparent USB-serial bridge). See "Speeduino + RusEFI wireless story" below

### CAN / XCP (reference only — not in shipped product)
- CAN routing and XCP transport live in obfuscated packages (`Z`, `B`, `bQ`, `aV`)
- XCP CRC confirmed in `com/efiAnalytics/xcp/master/responseProcessors/CrcProcessor.java`
- **Out of scope for our product.** Neither Speeduino nor RusEFI uses XCP; the speculative C++ XCP packet+simulator clusters are slated for deletion in Phase 18

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
- ~~`tuner_core::xcp_packets` + `xcp_simulator`~~ **slated for deletion in Phase 18** — speculative, never wired into `EcuConnection` or any Qt tab
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

- ~~XCP workspace integration~~ **Cut in Phase 18.** XCP is not a Speeduino or RusEFI protocol; the packet+simulator layers are slated for deletion.
- ~~FTDI direct-access path~~ **Cut in Phase 18.** Win32 serial via the standard COM port enumerator handles every USB-serial chip operators actually use (FTDI, CH340, CP210x, native USB CDC on Teensy/STM32); the FTD2XX-JNA path was a TunerStudio internal implementation detail, not an operator feature.

## Speeduino + RusEFI wireless story

For posterity, since the strip plan touches transport assumptions in three places:

- **Speeduino firmware** ships **no Bluetooth driver code**. The only mentions in the firmware source are passive: `speeduino/globals.h:774` documents that Page 2 is "configured by USBserial/bluetooth" (implying an external bridge), and `speeduino/init.cpp:2448-2449` designates STM32 pins `PA9 / PA10` (UART1 TX/RX) as the wiring point for an HC-05/HC-06 module. Wireless on Speeduino is BYO — the operator solders or plugs a serial-to-BT module onto the free UART, and the desktop tuner sees a regular COM port.
- **Airbear** does the heavy lifting for built-in wireless. The ESP32-C3-SuperMini firmware ships both WiFi/TCP (already in production via `TcpTransport`) **and** BLE-via-NUS (`Airbear-main/src/ble-uart.{cpp,h}`, Nordic UART Service `6E400001-B5A3-F393-E0A9-E50E24DCCA9E`). The BLE side is meant for phone/tablet gauge clients running a native app over `bleak`-style libs, not for the desktop tuner.
- **RusEFI firmware** (snapshot at `resources/speeduino-202501.6/Resources/rusefi-2026-03-17/`) supports BLE on selected Hellen boards via the platform's native BT stack, but again the desktop tuner connects over USB serial; BLE-to-phone is a separate gauge path.
- **Desktop tuner** therefore needs only `SerialTransport` + `TcpTransport`. There is no operator scenario where adding `BleTransport` to the C++ tree makes sense, because every BLE termination is either a phone client (Airbear NUS) or already-transparent via a USB-serial bridge (HC-05).
- Boost/spool/compressor runtime channels — partially addressed by the compressor-map modeling service; boost pressure is a standard channel; spool estimation and dynamic compressor efficiency remain derivation targets for a future analysis service.
