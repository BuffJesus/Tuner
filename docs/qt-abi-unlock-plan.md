# Qt ABI Unlock Plan

## Current Situation

The prebuilt Qt 6.7.3 MinGW DLLs from `aqtinstall` were compiled with a slightly older MinGW version than our local MinGW UCRT 15.2. This ABI mismatch causes SIGSEGV whenever Qt's internal code creates/manipulates `QString` objects in certain call paths.

## What's Blocked

| Feature | Why it crashes | What it would enable |
|---------|---------------|---------------------|
| `QLineEdit` | Internal text insertion uses `QString` | Native text input, search boxes, parameter editors |
| `Qt::RichText` labels | HTML parser uses `QString` internally | Styled gauge displays, colored inline values, bold/size mixing |
| `QPainter` custom widgets | Some paint calls go through `QString` for text | Analog dial gauges, bar gauges, histogram traces |
| `QTreeWidget::clear()` | Destroys children whose text is `QString` | Tree rebuild on filter (currently using show/hide) |
| `QColor` in code | Constructor may go through ABI | Programmatic color assignment in signal handlers |

## Current Workarounds

| Blocked feature | Workaround |
|----------------|------------|
| QLineEdit | Custom `SearchBox` widget using `e->key()` → ASCII mapping |
| RichText labels | Plain text + CSS stylesheet for colors/sizing |
| Custom painting | Static heatmaps built at construction time only |
| Tree rebuild | Show/hide existing items instead of clear+rebuild |
| QColor | Stylesheet strings only, no `QColor` objects in handlers |

## Fix: Build Qt from Source

```bash
# Download Qt 6.7.3 source
git clone https://code.qt.io/qt/qt5.git -b v6.7.3 --depth 1
cd qt5
perl init-repository --module-subset=qtbase

# Configure with our exact toolchain
./configure -prefix C:/Qt/6.7.3-custom \
  -platform win32-g++ \
  -release \
  -shared \
  -opensource -confirm-license \
  -skip qtwebengine \
  -nomake examples -nomake tests

# Build (takes ~30-60 minutes)
cmake --build . --parallel 4
cmake --install .
```

Then update `CMakeLists.txt`:
```cmake
-DCMAKE_PREFIX_PATH=C:/Qt/6.7.3-custom
```

## What Unlocks After the Fix

1. **Real analog dial gauges** — QPainter arc + needle + tick marks + zones
2. **Rich gauge cards** — bold values, colored zones, multi-size text
3. **Native QLineEdit** — proper text input with cursor, selection, clipboard
4. **Histogram/trace gauges** — scrolling line charts for channel history
5. **Tree filtering** — proper clear + rebuild for instant search results
6. **QColor in handlers** — zone-colored needle, per-cell foreground in tables

## Priority

Building Qt from source should be done as a dedicated task before the next major UI phase. It's ~1 hour of build time and eliminates all 5 ABI workarounds permanently. Every visual feature after that point becomes dramatically simpler to implement.
