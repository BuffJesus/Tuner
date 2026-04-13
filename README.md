<p align="center">
  <strong style="font-size: 28px; letter-spacing: 4px;">TUNER</strong><br>
  <em>guided power for Speeduino engines</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/C%2B%2B-20-blue?style=flat-square" alt="C++20" />
  <img src="https://img.shields.io/badge/Qt-6.7-green?style=flat-square" alt="Qt 6.7" />
  <img src="https://img.shields.io/badge/tests-1395%20passing-brightgreen?style=flat-square" alt="Tests" />
  <img src="https://img.shields.io/badge/license-MIT-lightgrey?style=flat-square" alt="MIT" />
</p>

---

A native C++ Qt 6 desktop workstation for tuning [Speeduino](https://speeduino.com) engine management systems. Built as a complete, independent ecosystem — own file formats, own dashboard, own workflow. No legacy software dependencies.

## What It Does

| | |
|---|---|
| **Tune** | Edit scalars, tables, curves. Staged changes with review, undo, write-to-RAM, burn-to-flash. |
| **Live** | Configurable gauge dashboard with drag-and-drop, fullscreen (F11), 40+ status indicators. |
| **Analyze** | Import datalogs or run live VE sessions. Accumulate corrections, smooth, diagnose, apply. |
| **Log** | Real-time capture to CSV. Multi-profile with add/delete/switch. Replay with row navigation. |
| **Flash** | Board-aware firmware flashing (AVRDUDE / Teensy CLI / dfu-util). Progress bar + output log. |
| **Setup** | 6-step engine wizard: Engine, Induction, Injectors, Trigger & Ignition, Sensors, Review. |
| **Diagnose** | Trigger log capture (tooth / composite) — CSV import or live from ECU. Analysis pipeline. |
| **Connect** | Serial (USB) or TCP/WiFi via Airbear. EcuHub UDP auto-discovery. HTTP API on port 8080. |

## Supported Hardware

| Board | Status |
|-------|--------|
| Teensy 4.1 (DropBear) | Recommended — U16 high-resolution tables |
| Teensy 3.5 / 3.6 | Supported |
| Arduino Mega 2560 | Supported |
| STM32F407 (Black Pill) | Supported |
| Airbear ESP32-C3 | WiFi bridge — TCP framing on port 2000 |
| Raspberry Pi 3/4/5 | Dashboard display target (EGLFS) |

## Building

<details>
<summary><strong>Windows</strong> (primary development platform)</summary>

Prerequisites: MinGW UCRT 15.2, Qt 6.7.3 built from source.

```bash
cmake -B build/cpp -S cpp \
  -DCMAKE_PREFIX_PATH=C:/Qt/6.7.3-custom \
  -DTUNER_BUILD_APP=ON

cmake --build build/cpp --target tuner_app
```
</details>

<details>
<summary><strong>Raspberry Pi</strong> (in-vehicle dashboard)</summary>

Cross-compile with the included toolchain file.

```bash
cmake -B build/pi -S cpp \
  -DCMAKE_TOOLCHAIN_FILE=cpp/cmake/pi3-toolchain.cmake \
  -DCMAKE_PREFIX_PATH=/path/to/qt6-pi-sysroot \
  -DTUNER_BUILD_APP=ON

cmake --build build/pi --target tuner_app
```
</details>

<details>
<summary><strong>Tests</strong></summary>

```bash
cmake --build build/cpp --target tuner_core_tests
./build/cpp/tuner_core_tests
# 1395 tests · 10899 assertions · 0 failures
```
</details>

## Native File Formats

The app uses its own JSON5-based file formats. Legacy INI/MSQ files can be imported once via **File > Import Legacy INI**.

| Extension | Schema | Purpose |
|-----------|--------|---------|
| `.tunerdef` | JSON5 v2.0 | Firmware definition — parameters, gauges, channels, commands, menus |
| `.tuner` | JSON5 v1.0 | Tune data — all parameter values |
| `.tunerproj` | JSON | Project metadata |

```json5
// Example: native tune file with operator comments
{
  "schema_version": "1.0",
  "definition_signature": "speeduino 202501-T41",
  "values": {
    // Leaned out WOT row after dyno session
    "veTable": [78, 80, 82, ...],
    "reqFuel": 8.2,
  }
}
```

## Architecture

```
cpp/
  app/
    main.cpp        Qt 6 application shell (~12,500 lines)
    theme.hpp       Dark theme token system (40+ tokens)
  include/
    tuner_core/     130+ public headers
  src/              173 service implementations
  tests/            60+ doctest suites
  cmake/            Cross-compile toolchains
```

Built on the `tuner_core` static library — 98 services covering parsing, protocol, analysis, generation, and visualization. The library has zero Qt dependency; the app is the only Qt consumer.

## Ecosystem

<table>
<tr>
<td width="33%" align="center">
<strong>Speeduino</strong><br>
<sub>ECU firmware</sub><br>
<sub>Teensy · Arduino · STM32</sub>
</td>
<td width="33%" align="center">
<strong>Airbear</strong><br>
<sub>WiFi bridge</sub><br>
<sub>ESP32-C3 · TCP · REST · SSE</sub>
</td>
<td width="33%" align="center">
<strong>Tuner</strong><br>
<sub>Desktop workstation</sub><br>
<sub>C++ Qt 6 · Native format · HTTP API</sub>
</td>
</tr>
</table>

The native `.tunerdef` format is the source of truth for firmware definitions. Legacy INI is an import adapter — convert once, use native format from then on.

## License

MIT
