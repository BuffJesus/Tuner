# tuner_core — native C++ shared core

Future Phase 13 first slice. C++20 implementation of the MSQ parser and
writer, callable from Python via nanobind so the existing Python suite
acts as the correctness oracle.

## Tree

```
cpp/
├── CMakeLists.txt
├── include/tuner_core/
│   ├── msq_parser.hpp                ← Slice 1: MSQ XML reader/writer
│   ├── native_format.hpp             ← Slice 2: Native definition/tune JSON
│   ├── ini_preprocessor.hpp          ← Slice 3: INI #if/#else/#set preprocessor
│   ├── ini_constants_parser.hpp     ← Slice 4: INI [Constants] section parser
│   ├── ini_defines_parser.hpp        ← Slice 5: INI #define collector + expander
│   ├── ini_output_channels_parser.hpp ← Slice 6: INI [OutputChannels] section parser
│   ├── ini_table_editor_parser.hpp   ← Slice 7: INI [TableEditor] section parser
│   ├── ini_curve_editor_parser.hpp   ← Slice 8: INI [CurveEditor] section parser
│   ├── ini_menu_parser.hpp           ← Slice 9: INI [Menu] section parser
│   └── ini_gauge_configurations_parser.hpp ← Slice 10: INI [GaugeConfigurations]
├── src/
│   ├── parse_helpers.hpp             ← shared `strip` / `parse_csv` (private)
│   ├── msq_parser.cpp
│   ├── native_format.cpp
│   ├── ini_preprocessor.cpp
│   ├── ini_constants_parser.cpp
│   ├── ini_defines_parser.cpp
│   ├── ini_output_channels_parser.cpp
│   ├── ini_table_editor_parser.cpp
│   ├── ini_curve_editor_parser.cpp
│   ├── ini_menu_parser.cpp
│   └── ini_gauge_configurations_parser.cpp
├── tests/
│   ├── test_msq_parser.cpp           ← 8 doctest cases
│   ├── test_native_format.cpp        ← 10 doctest cases
│   ├── test_ini_preprocessor.cpp     ← 16 doctest cases
│   ├── test_ini_constants_parser.cpp ← 18 doctest cases
│   ├── test_ini_defines_parser.cpp   ← 12 doctest cases
│   ├── test_ini_output_channels_parser.cpp ← 11 doctest cases
│   ├── test_ini_table_editor_parser.cpp ← 13 doctest cases
│   ├── test_ini_curve_editor_parser.cpp ← 14 doctest cases
│   ├── test_ini_menu_parser.cpp      ← 14 doctest cases
│   └── test_ini_gauge_configurations_parser.cpp ← 12 doctest cases
├── bindings/tuner_core_module.cpp   ← nanobind Python extension
└── third_party/
    ├── doctest/doctest.h        ← vendor here (single header)
    └── nlohmann/json.hpp        ← vendor here (single header)
```

## Scope decisions in force (per docs/tuning-roadmap.md Future Phase 13)

| Decision | Choice |
|---|---|
| End goal | Gradual replacement of the Python implementation |
| First subsystem | MSQ parser/writer |
| Migration cadence | Strict Python-as-oracle; C++ ships only after parity is proven |
| C++ standard | C++20 |
| Compiler matrix | MSVC first; add GCC/Clang to CI later |
| Build system | CMake |
| Dependencies | stdlib + vendored single-header tools (doctest, nanobind) |
| Test framework | doctest |
| Cross-validation | Shared MSQ fixtures + Python parity harness |
| Bindings | nanobind |
| Distribution | cibuildwheel + Python fallback path |

## First-time setup

1. **Vendor doctest** (single header, ~600 KB):

   ```sh
   mkdir -p cpp/third_party/doctest
   curl -L -o cpp/third_party/doctest/doctest.h \
     https://raw.githubusercontent.com/doctest/doctest/master/doctest/doctest.h
   ```

2. **Vendor nlohmann/json** (single header, ~900 KB):

   ```sh
   mkdir -p cpp/third_party/nlohmann
   curl -L -o cpp/third_party/nlohmann/json.hpp \
     https://github.com/nlohmann/json/releases/latest/download/json.hpp
   ```

3. **Install nanobind** (only required for the Python binding build):

   ```sh
   pip install "nanobind>=2.0.0"
   ```

## Build & test (C++ side only)

On Windows with MinGW (the validated path):

```sh
cmake -S cpp -B build/cpp -G "MinGW Makefiles" \
  -DTUNER_CORE_BUILD_TESTS=ON \
  -DCMAKE_BUILD_TYPE=Release
cmake --build build/cpp --config Release
build/cpp/tuner_core_tests.exe
```

`ctest` may fail on Windows with `STATUS_DLL_INIT_FAILED` due to a
working-directory quirk; running the test exe directly works. The
binary is statically linked against the MinGW runtime so no PATH
manipulation is needed.

Expected output: `tuner_core_tests` runs the doctest suite and reports
**584 cases, 1794 assertions, 0 failures** as of Phase 14 Slice 4
sub-slice 34 (`VeRootCauseDiagnosticsService`). Each new sub-slice bumps
both numbers; check `docs/tuning-roadmap.md` for the latest figure
when this README falls behind.

## Build the Python binding

```sh
cmake -S cpp -B build/cpp -G "MinGW Makefiles" \
  -DTUNER_CORE_BUILD_TESTS=ON \
  -DTUNER_CORE_BUILD_BINDINGS=ON \
  -DCMAKE_BUILD_TYPE=Release \
  -Dnanobind_DIR=$(python -m nanobind --cmake_dir)
cmake --build build/cpp --config Release
```

The resulting extension lands in `build/cpp/` as `tuner_core.<plat>.pyd`
on Windows or `tuner_core.<plat>.so` on Linux/macOS. The Python parity
tests (`tests/unit/test_cpp_msq_parser_parity.py`,
`tests/unit/test_cpp_native_format_parity.py`, and
`tests/unit/test_cpp_ini_preprocessor_parity.py`) discover it via a
`sys.path` insertion when the build directory exists; if it can't be
imported they skip rather than fail, so a developer install without a
compiler still works.

**Important: MinGW runtime is statically linked.** `cpp/CMakeLists.txt`
adds `-static-libgcc -static-libstdc++ -static -lwinpthread` for MinGW
builds so the resulting `.pyd` has zero runtime DLL dependency. Without
this, Python on Windows can't load the extension because it doesn't
honor PATH for DLL search since 3.8 (the user would have to call
`os.add_dll_directory()` for the MinGW bin every import). Static
linking makes the artifact self-contained.

Verify the build worked:

```sh
python -m pytest tests/unit/test_cpp_msq_parser_parity.py \
                 tests/unit/test_cpp_native_format_parity.py \
                 tests/unit/test_cpp_ini_preprocessor_parity.py
```

Expected: **112 passed** (9 MSQ + 10 NativeFormat + 16 INI preprocessor +
12 INI constants + 12 INI defines + 9 INI output channels +
11 INI table editor + 12 INI curve editor + 14 INI menu +
7 INI gauge configurations — the last includes byte-identical parity
against the production INI for every gauge's channel/title/units/
thresholds/category), zero skipped.

## Why no third-party XML library?

The MSQ format is a small, well-behaved subset of XML (no DTD, no
namespaces beyond the root xmlns, no entities beyond the standard
five). Pulling in pugixml or expat would dwarf the slice. The
hand-rolled scanner in `src/msq_parser.cpp` is ~150 lines and matches
the Python `MsqParser` / `MsqWriteService.save()` (default
insert_missing=False) behaviour byte-for-byte on the existing fixture
suite.

Future slices that need richer XML handling (e.g. an INI parser port)
will revisit this decision.
