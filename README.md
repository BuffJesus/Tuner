# Tuner — Speeduino Workstation

A native C++ Qt 6 desktop application for tuning Speeduino engine management systems. Designed as a complete, independent tuning ecosystem with its own file formats, dashboard, and workflow.

## Features

- **Full tuning workflow**: Connect → view live data → edit parameters → write to RAM → burn to flash
- **Native file format**: JSON5 `.tunerdef` definitions and `.tuner` tune files (legacy INI/MSQ import supported)
- **Live dashboard**: Configurable gauge cluster with drag-and-drop, fullscreen mode (F11), 40+ boolean indicators
- **VE Analyze**: Import datalogs or run live sessions to accumulate correction proposals, then apply with one click
- **Data logging**: Real-time capture to CSV with multi-profile support
- **Trigger diagnostics**: CSV import and live tooth/composite capture from ECU
- **Firmware flashing**: Board-aware flash tool (AVRDUDE/Teensy CLI/dfu-util) with QProcess subprocess
- **Engine Setup Wizard**: 6-step guided setup (Engine, Induction, Injectors, Trigger, Sensors, Review) with table generators
- **HTTP Live-Data API**: Port 8080 JSON endpoints for browser dashboards, Raspberry Pi, phones
- **EcuHub UDP discovery**: Auto-find Speeduino devices on the local network (port 21846)

## Supported Hardware

- **Teensy 4.1 (DropBear)** — recommended, supports U16 high-resolution tables
- **Teensy 3.5 / 3.6**
- **Arduino Mega 2560**
- **STM32F407 (Black Pill)**
- **Airbear ESP32-C3** WiFi bridge (TCP framing on port 2000)

## Building

### Windows (primary development platform)

```bash
# Prerequisites: MinGW UCRT 15.2, Qt 6.7.3 built from source
cmake -B build/cpp -S cpp \
  -DCMAKE_PREFIX_PATH=C:/Qt/6.7.3-custom \
  -DTUNER_BUILD_APP=ON
cmake --build build/cpp --target tuner_app
```

### Raspberry Pi 3/4/5

```bash
cmake -B build/pi -S cpp \
  -DCMAKE_TOOLCHAIN_FILE=cpp/cmake/pi3-toolchain.cmake \
  -DCMAKE_PREFIX_PATH=/path/to/qt6-pi-sysroot \
  -DTUNER_BUILD_APP=ON
cmake --build build/pi --target tuner_app
```

### Tests

```bash
cmake --build build/cpp --target tuner_core_tests
build/cpp/tuner_core_tests
# 1395 tests, 10899 assertions, 0 failures
```

## File Formats

| Extension | Format | Purpose |
|-----------|--------|---------|
| `.tunerdef` | JSON5 (schema 2.0) | Firmware definition — all parameters, gauges, channels, commands |
| `.tuner` | JSON5 (schema 1.0) | Tune data — parameter values |
| `.tunerproj` | JSON | Project metadata |
| `.ini` | Legacy INI | Import adapter only (File → Import Legacy INI) |
| `.msq` | Legacy XML | Import adapter only |

## Architecture

Native C++ Qt 6 application (`cpp/app/main.cpp`) built on the `tuner_core` static library (98 services, 173 source files). The library handles parsing, protocol, analysis, and generation; the app handles UI.

```
cpp/
  app/main.cpp          — Qt 6 desktop entry point (~12,500 lines)
  app/theme.hpp         — dark theme token system
  include/tuner_core/   — 130+ public headers
  src/                  — 173 service implementations
  tests/                — 60+ doctest files (1395 tests)
  cmake/                — Pi cross-compile toolchain
```

## Ecosystem

The application is part of a three-project ecosystem:

- **Speeduino firmware** — the ECU firmware running on Teensy/Arduino/STM32
- **Airbear** — ESP32-C3 WiFi bridge for wireless ECU access
- **Tuner** — this desktop application

The native `.tunerdef` format is designed to eventually replace the legacy INI as the source of truth for firmware definitions. Import Legacy INI converts once; the app uses native format from then on.

## License

MIT
