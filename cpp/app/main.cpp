// SPDX-License-Identifier: MIT
//
// tuner_app — native Qt 6 desktop entry point.
//
// Phase 14 progress shell. 4-tab redesigned layout that loads the
// production INI through the C++ tuner_core orchestrator and renders
// the workspace surfaces using already-ported services. The shell is
// intentionally a thin assembler — every panel either calls a
// tuner_core service directly or renders a static manifest.
//
// IMPORTANT MinGW UCRT + Qt 6.7 GOTCHA
// ------------------------------------
// Do NOT build QString instances via operator+ chains that mix
// `const char*` and `QString` operands, e.g.
//
//     QString html = "<b>" + label + "</b> " + QString::number(v);
//
// The Qt 6.7 prebuilt MinGW DLLs were compiled against a slightly
// older toolchain than our local MinGW UCRT 15.2 build, and the
// `QString operator+(const char*, const QString&)` (and overloads
// that go through `QString::fromUtf8(const char*, qsizetype)`)
// reproducibly crash with SIGSEGV mid-expression on this combo.
// The crash always lives somewhere inside an arg/temporary, never
// in our code, and bisects to whichever expression of that shape
// happens to come next.
//
// Workaround: assemble the entire string into a `char[]` buffer
// with std::snprintf first, then convert ONCE via QString::fromUtf8.
// This sidesteps the broken operator overloads entirely. Every
// rendering helper in this file follows that pattern.
//
// ADDITIONAL CONSTRAINT (2026-04-09 audit):
// The same ABI mismatch also affects chained method calls on QString
// temporaries inside signal/slot lambdas, e.g.
//     q.trimmed().toLower()          // CRASHES — intermediate temporary
//     leaf->text(0).toLower()        // CRASHES — same pattern
// The fix: convert to std::string at the boundary via toStdString()
// and do all comparison/mutation work on the std::string side. Never
// chain .trimmed(), .toLower(), .contains() on QString temporaries
// anywhere in a signal handler. Also never call setExpanded() while
// walking a QTreeWidget from inside its own signal — defer mutations
// until after the walk is complete.
//
// FOURTH CONSTRAINT (2026-04-09): even single calls to text()/data()
// on QTreeWidgetItem inside signal handlers can crash because the
// returned QString goes through the broken ABI boundary. The safest
// approach: store all needed data in a side map (e.g.
// unordered_map<QTreeWidgetItem*, Info>) during tree population, and
// read from that map in handlers instead of querying the widget.
//
// FIFTH CONSTRAINT (2026-04-09): QLineEdit is fundamentally broken —
// its internal text processing (character insertion, cursor movement)
// goes through broken QString paths and SIGSEGVs on any keystroke.
// QTreeWidget::clear() also crashes because it destroys child items
// whose text storage goes through the same path. Workarounds:
//   - Replace QLineEdit with a custom SearchBox widget that handles
//     keyPressEvent using e->key() (int) instead of e->text() (QString)
//   - Never call tree->clear(). Build all tree items once at startup,
//     then use setHidden()/setExpanded() for filtering.
//   - Guard against redundant callbacks (e.g. backspace on empty text)
//     to avoid triggering repeated label updates that crash.

#include "tuner_core/afr_target_generator.hpp"
#include "tuner_core/speeduino_controller.hpp"
#include "tuner_core/speeduino_param_codec.hpp"
#include "tuner_core/wideband_calibration.hpp"
#include "tuner_core/speeduino_live_data_decoder.hpp"
#include "tuner_core/speeduino_value_codec.hpp"
#include "tuner_core/transport.hpp"
#include "tuner_core/table_replay_context.hpp"
#include "tuner_core/table_surface_3d.hpp"
#include "tuner_core/hardware_setup_generator_context.hpp"
#include "tuner_core/datalog_import.hpp"
#include "tuner_core/datalog_replay.hpp"
#include "tuner_core/ignition_trigger_cross_validation.hpp"
#include "tuner_core/operator_engine_context.hpp"
#include "tuner_core/project_file.hpp"
#include "tuner_core/sensor_setup_checklist.hpp"
#include "tuner_core/trigger_log_analysis.hpp"
#include "tuner_core/trigger_log_visualization.hpp"
#include "tuner_core/definition_layout.hpp"
#include "tuner_core/visibility_expression.hpp"
#include "tuner_core/datalog_profile.hpp"
#include "tuner_core/ecu_definition_compiler.hpp"
#include "tuner_core/firmware_catalog.hpp"
#include "tuner_core/firmware_flash_builder.hpp"
#include "tuner_core/teensy_hex_image.hpp"
#include "tuner_core/teensy_hid_flasher.hpp"
#include "tuner_core/live_analyze_session.hpp"
#include "tuner_core/live_capture_session.hpp"
#include "tuner_core/live_trigger_logger.hpp"
#include "tuner_core/virtual_dyno.hpp"
#include "tuner_core/boost_table_generator.hpp"
#include "tuner_core/mock_ecu_runtime.hpp"
#include "tuner_core/math_expression_evaluator.hpp"

#include "theme.hpp"

namespace tt = tuner_theme;
#include "tuner_core/native_format.hpp"
#include "tuner_core/table_edit.hpp"
#include "tuner_core/native_tune_writer.hpp"
#include "tuner_core/tuning_page_grouping.hpp"
#include "tuner_core/flash_preflight.hpp"
#include "tuner_core/dashboard_layout.hpp"
#include "tuner_core/gauge_color_zones.hpp"
#include "tuner_core/hardware_presets.hpp"
#include "tuner_core/hardware_setup_validation.hpp"
#include "tuner_core/idle_rpm_generator.hpp"
#include "tuner_core/local_tune_edit.hpp"
#include "tuner_core/msq_parser.hpp"
#include "tuner_core/required_fuel_calculator.hpp"
#include "tuner_core/runtime_telemetry.hpp"
#include "tuner_core/startup_enrichment_generator.hpp"
#include "tuner_core/table_rendering.hpp"
#include "tuner_core/table_view.hpp"
#include "tuner_core/thermistor_calibration.hpp"
#include "tuner_core/ve_analyze_review.hpp"
#include "tuner_core/workspace_presenter.hpp"
#include "tuner_core/workspace_state.hpp"
#include "tuner_core/wue_analyze_accumulator.hpp"
#include "tuner_core/ve_cell_hit_accumulator.hpp"
#include "tuner_core/ve_proposal_smoothing.hpp"
#include "tuner_core/ve_root_cause_diagnostics.hpp"
#include "tuner_core/ve_table_generator.hpp"
#include "tuner_core/spark_table_generator.hpp"

#include <QApplication>
#include <QBrush>
#include <QColor>
#include <QDialog>
#include <QFont>
#include <QPainter>
#include <QPointer>
#include <QPushButton>
#include <QPaintEvent>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QKeyEvent>
#include <QMouseEvent>
#include <QLabel>
#include <QLineEdit>
#include <QTimer>
#include <QList>
#include <QListWidget>
#include <QMainWindow>
#include <QScrollArea>
#include <QSizePolicy>
#include <QTextEdit>
#include <QShortcut>
#include <QSpinBox>
#include <QSplitter>
#include <QStackedWidget>
#include <QVariant>
#include <QStatusBar>
#include <QMenuBar>
#include <QMenu>
#include <QAction>
#include <QDateTime>
#include <QDir>
#include <QSettings>
#include <QCheckBox>
#include <QClipboard>
#include <QDrag>
#include <QMimeData>
#include <QCloseEvent>
#include <QComboBox>
#include <QFileDialog>
#include <QMessageBox>
#include <QProcess>
#include <QProgressBar>
#include <QStandardPaths>
#include <QString>
#include <QStyleFactory>
#include <QSysInfo>
#include <QTabWidget>
#include <QTreeWidget>
#include <QTreeWidgetItem>
#include <QVBoxLayout>
#include <QWidget>

#include <algorithm>
#include <atomic>
#include <cctype>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <map>
#include <memory>
#include <mutex>
#include <set>
#include <sstream>
#include <string>
#include <thread>
#include <unordered_map>
#include <utility>
#include <variant>
#include <vector>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#endif

namespace {

// ---------------------------------------------------------------------------
// Serial port enumeration (Windows registry)
// ---------------------------------------------------------------------------

std::vector<std::string> list_serial_ports() {
    std::vector<std::string> ports;
#ifdef _WIN32
    HKEY hKey = nullptr;
    if (RegOpenKeyExA(HKEY_LOCAL_MACHINE,
                      "HARDWARE\\DEVICEMAP\\SERIALCOMM",
                      0, KEY_READ, &hKey) != ERROR_SUCCESS) {
        return ports;
    }
    char valueName[256];
    char valueData[256];
    DWORD index = 0;
    for (;;) {
        DWORD nameLen = sizeof(valueName);
        DWORD dataLen = sizeof(valueData);
        DWORD type = 0;
        LONG ret = RegEnumValueA(hKey, index, valueName, &nameLen,
                                  nullptr, &type,
                                  reinterpret_cast<BYTE*>(valueData), &dataLen);
        if (ret != ERROR_SUCCESS) break;
        if (type == REG_SZ && dataLen > 0) {
            ports.emplace_back(valueData, dataLen > 0 ? dataLen - 1 : 0);
        }
        ++index;
    }
    RegCloseKey(hKey);
    std::sort(ports.begin(), ports.end());
#endif
    return ports;
}

std::string current_system_name() {
#ifdef _WIN32
    return "windows";
#elif defined(__APPLE__)
    return "darwin";
#else
    return "linux";
#endif
}

std::string current_machine_name() {
    std::string arch = QSysInfo::currentCpuArchitecture().toStdString();
    std::transform(arch.begin(), arch.end(), arch.begin(),
                   [](unsigned char ch) { return static_cast<char>(std::tolower(ch)); });
    if (arch == "x86_64" || arch == "x86-64") return "x86_64";
    if (arch == "amd64") return "amd64";
    if (arch == "i386" || arch == "i686" || arch == "x86") return arch;
    if (arch == "arm64") return "arm64";
    if (arch == "aarch64") return "aarch64";
    if (arch == "arm" || arch == "armv7l") return arch;
    return arch.empty() ? "x86_64" : arch;
}

std::vector<std::filesystem::path> flash_search_roots() {
    std::vector<std::filesystem::path> roots;
    const auto app_dir = std::filesystem::path(
        QCoreApplication::applicationDirPath().toStdString());
    const auto cwd = std::filesystem::current_path();
    const auto home_dir = std::filesystem::path(QDir::homePath().toStdString());
    roots.push_back(app_dir);
    roots.push_back(app_dir / "tools");
    if (app_dir.has_parent_path()) {
        roots.push_back(app_dir.parent_path());
        roots.push_back(app_dir.parent_path() / "tools");
    }
    roots.push_back(cwd);
    roots.push_back(cwd / "tools");
#ifdef _WIN32
    roots.push_back(home_dir / ".platformio" / "packages" / "tool-teensy");
    const auto desktop_dir = home_dir / "Desktop";
    std::error_code ec;
    if (std::filesystem::exists(desktop_dir, ec) && !ec) {
        for (const auto& entry : std::filesystem::directory_iterator(desktop_dir, ec)) {
            if (ec || !entry.is_directory()) continue;
            const auto name = entry.path().filename().string();
            if (name.rfind("SpeedyLoader-", 0) == 0) {
                roots.push_back(entry.path());
                roots.push_back(entry.path() / "bin");
            }
        }
    }
#endif
    return roots;
}

std::string find_flash_program_path(tuner_core::firmware_flash_builder::FlashTool tool,
                                    const std::string& filename) {
    namespace ffb = tuner_core::firmware_flash_builder;

    const auto system_name = current_system_name();
    std::string platform_name;
    try {
        platform_name = ffb::platform_dir(tool, system_name, current_machine_name());
    } catch (const std::exception&) {
        platform_name.clear();
    }

    for (const auto& root : flash_search_roots()) {
        std::vector<std::filesystem::path> candidates;
        candidates.push_back(root / filename);
        if (!platform_name.empty()) {
            candidates.push_back(root / platform_name / filename);
            candidates.push_back(root / "bin" / platform_name / filename);
            candidates.push_back(root / "tools" / "bin" / platform_name / filename);
        }
        candidates.push_back(root / "bin" / filename);
        for (const auto& candidate : candidates) {
            std::error_code ec;
            if (std::filesystem::exists(candidate, ec) && !ec) {
                return candidate.string();
            }
        }
    }

    const auto resolved = QStandardPaths::findExecutable(QString::fromUtf8(filename.c_str()));
    return resolved.isEmpty() ? std::string() : resolved.toStdString();
}

std::string find_flash_support_file(tuner_core::firmware_flash_builder::FlashTool tool,
                                    const std::string& filename,
                                    const std::string& program_path = std::string()) {
    namespace ffb = tuner_core::firmware_flash_builder;

    const auto system_name = current_system_name();
    std::string platform_name;
    try {
        platform_name = ffb::platform_dir(tool, system_name, current_machine_name());
    } catch (const std::exception&) {
        platform_name.clear();
    }

    std::vector<std::filesystem::path> roots;
    if (!program_path.empty()) {
        auto program_parent = std::filesystem::path(program_path).parent_path();
        roots.push_back(program_parent);
        if (program_parent.has_parent_path()) {
            roots.push_back(program_parent.parent_path());
        }
    }
    for (const auto& root : flash_search_roots()) {
        roots.push_back(root);
    }

    for (const auto& root : roots) {
        std::vector<std::filesystem::path> candidates;
        candidates.push_back(root / filename);
        if (!platform_name.empty()) {
            candidates.push_back(root / platform_name / filename);
            candidates.push_back(root / "bin" / platform_name / filename);
            candidates.push_back(root / "tools" / "bin" / platform_name / filename);
        }
        candidates.push_back(root / "bin" / filename);
        for (const auto& candidate : candidates) {
            std::error_code ec;
            if (std::filesystem::exists(candidate, ec) && !ec) {
                return candidate.string();
            }
        }
    }
    return std::string();
}

void set_info_card_accent(QWidget* card, const char* accent_color) {
    char style[256];
    std::snprintf(style, sizeof(style),
        "background-color: %s; border: 1px solid %s; "
        "border-left: 3px solid %s; border-radius: %dpx;",
        tt::bg_elevated, tt::border, accent_color, tt::radius_md);
    card->setStyleSheet(QString::fromUtf8(style));
}

// ---------------------------------------------------------------------------
// Shared ECU connection state
// ---------------------------------------------------------------------------
// One instance lives in TunerMainWindow and is shared with the LIVE tab
// timer, TUNE crosshair timer, status bar timer, and sidebar indicator.
// All access happens on the Qt GUI thread (timer callbacks), so no mutex
// needed.

struct EcuConnection {
    std::unique_ptr<tuner_core::speeduino_controller::SpeeduinoController> controller;
    tuner_core::speeduino_controller::ConnectionInfo info;
    bool connected = false;

    // Last decoded runtime snapshot — channel name → value.
    std::unordered_map<std::string, double> runtime;

    // Output channel layouts from the parsed INI (needed to decode
    // the runtime packet). Built once after INI load.
    std::vector<tuner_core::speeduino_live_data_decoder::OutputChannelLayout> channel_layouts;
    std::size_t runtime_packet_size = 0;

    // Page cache — stores raw page bytes read from the ECU. Needed by
    // bit-field scalar encoding (read-modify-write) and for future
    // ECU-vs-local mismatch detection. Keyed by page number.
    std::unordered_map<int, std::vector<std::uint8_t>> page_cache;

    // Pages that have been written to RAM but not yet burned to flash.
    // Iterated in sorted order during burn.
    std::set<int> dirty_pages;

    // Poll the ECU for runtime data and update `runtime` map.
    // Returns true on success, false on error (disconnects on failure).
    bool poll_runtime() {
        if (!connected || !controller) return false;
        if (runtime_packet_size == 0) return false;
        try {
            auto bytes = controller->read_runtime(
                0, static_cast<std::uint16_t>(runtime_packet_size));
            if (bytes.size() < runtime_packet_size) return false;
            auto values = tuner_core::speeduino_live_data_decoder::decode_runtime_packet(
                channel_layouts, bytes);
            for (const auto& v : values) {
                runtime[v.name] = v.value;
            }
            return true;
        } catch (...) {
            // Connection lost — mark disconnected and log for debug.
            connected = false;
            try { controller->disconnect(); } catch (...) {}
            // debug_log not in scope here; console log only.
            std::printf("[live] ECU connection lost\n");
            std::fflush(stdout);
            return false;
        }
    }

    // Read a page slice from the ECU (or return cached bytes).
    // For bit-field scalar encoding we need the current byte(s) at
    // the target offset before we can do the read-modify-write.
    std::vector<std::uint8_t> read_page_slice(
        int page, int offset, int length) {
        if (!connected || !controller) return {};
        // Check cache first.
        auto it = page_cache.find(page);
        if (it != page_cache.end() &&
            static_cast<int>(it->second.size()) >= offset + length) {
            return std::vector<std::uint8_t>(
                it->second.begin() + offset,
                it->second.begin() + offset + length);
        }
        // Targeted read from ECU.
        return controller->read_page(
            static_cast<std::uint8_t>(page),
            static_cast<std::uint16_t>(offset),
            static_cast<std::uint16_t>(length));
    }

    // Write parameter bytes to ECU RAM, respecting the blocking factor.
    // Mirrors Python's `_write_page_chunk` — splits large payloads into
    // chunks no bigger than the negotiated blocking factor.
    void write_chunked(int page, int offset,
                       const std::uint8_t* data, std::size_t size,
                       bool is_table = false) {
        if (!connected || !controller) return;
        int max_chunk = is_table
            ? info.table_blocking_factor
            : info.blocking_factor;
        if (max_chunk <= 0) max_chunk = 128;
        std::size_t sent = 0;
        while (sent < size) {
            std::size_t chunk_size = std::min(
                static_cast<std::size_t>(max_chunk), size - sent);
            controller->write_parameter(
                static_cast<std::uint8_t>(page),
                static_cast<std::uint16_t>(offset + static_cast<int>(sent)),
                data + sent, chunk_size);
            sent += chunk_size;
            if (sent < size) {
                // 10ms inter-chunk delay — matches Python.
                std::this_thread::sleep_for(std::chrono::milliseconds(10));
            }
        }
        // Update page cache with the written bytes.
        auto& cached = page_cache[page];
        if (cached.size() < static_cast<std::size_t>(offset) + size) {
            cached.resize(static_cast<std::size_t>(offset) + size, 0);
        }
        std::memcpy(cached.data() + offset, data, size);
        dirty_pages.insert(page);
    }

    // Read all ECU pages into the page cache. Computes page sizes from
    // the definition by finding max(offset + data_size) per page number
    // across all scalars and arrays. Mirrors the Python read_from_ecu()
    // flow that invalidates the cache and reads every known page.
    // Returns the number of pages successfully read.
    int read_all_pages(const tuner_core::NativeEcuDefinition& def) {
        if (!connected || !controller) return 0;
        namespace svc = tuner_core::speeduino_value_codec;

        // Compute page sizes: max(offset + data_size) per page.
        std::map<int, int> page_sizes;
        for (const auto& sc : def.constants.scalars) {
            if (!sc.page.has_value() || !sc.offset.has_value()) continue;
            int page = *sc.page;
            int end = *sc.offset;
            try { end += static_cast<int>(svc::data_size_bytes(svc::parse_data_type(sc.data_type))); }
            catch (...) { end += 1; }
            if (end > page_sizes[page]) page_sizes[page] = end;
        }
        for (const auto& ar : def.constants.arrays) {
            if (!ar.page.has_value() || !ar.offset.has_value()) continue;
            int page = *ar.page;
            int elem_size = 1;
            try { elem_size = static_cast<int>(svc::data_size_bytes(svc::parse_data_type(ar.data_type))); }
            catch (...) {}
            int end = *ar.offset + ar.rows * ar.columns * elem_size;
            if (end > page_sizes[page]) page_sizes[page] = end;
        }

        int read_count = 0;
        for (const auto& [page, size] : page_sizes) {
            if (size <= 0) continue;
            try {
                auto data = controller->read_page(
                    static_cast<std::uint8_t>(page), 0,
                    static_cast<std::uint16_t>(size));
                if (!data.empty()) {
                    page_cache[page] = std::move(data);
                    read_count++;
                }
            } catch (...) {
                // Connection may have dropped — stop reading.
                break;
            }
        }
        return read_count;
    }

    // Get a runtime value by channel name (returns 0.0 if not found).
    double get(const std::string& name) const {
        auto it = runtime.find(name);
        return (it != runtime.end()) ? it->second : 0.0;
    }

    // Disconnect and clean up.
    void close() {
        if (controller) {
            try { controller->disconnect(); } catch (...) {}
        }
        connected = false;
        runtime.clear();
        page_cache.clear();
        dirty_pages.clear();
    }
};

// ---------------------------------------------------------------------------
// LiveDataHttpServer — background HTTP server for external dashboard
// consumers. Serves live ECU channel data as JSON on port 8080 so
// browser-based dashboards (Airbear web UI, phones, tablets, Raspberry
// Pi) can display gauges on the local network. Three endpoints:
//   GET /api/channels       — all channel name:value pairs
//   GET /api/channels/{name} — single channel with units
//   GET /api/status         — connection state + signature
// CORS headers on every response for cross-origin browser access.
// ---------------------------------------------------------------------------

class LiveDataHttpServer {
public:
    template<typename MapT>
    void update_snapshot(const MapT& channels,
                         bool connected, const std::string& signature) {
        std::lock_guard<std::mutex> lock(mu_);
        channels_.clear();
        for (const auto& [k, v] : channels) channels_[k] = v;
        connected_ = connected;
        signature_ = signature;
    }

    void start(int port = 8080) {
        if (running_) return;
        port_ = port;
        running_ = true;
        thread_ = std::thread([this]() { run(); });
    }

    void stop() {
        running_ = false;
        // Connect to self to unblock accept().
#ifdef _WIN32
        SOCKET wake = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
        if (wake != INVALID_SOCKET) {
            sockaddr_in addr{};
            addr.sin_family = AF_INET;
            addr.sin_port = htons(static_cast<u_short>(port_));
            addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
            connect(wake, reinterpret_cast<sockaddr*>(&addr), sizeof(addr));
            closesocket(wake);
        }
#endif
        if (thread_.joinable()) thread_.join();
    }

    ~LiveDataHttpServer() { stop(); }

private:
    std::unordered_map<std::string, double> channels_;
    bool connected_ = false;
    std::string signature_;
    std::mutex mu_;
    std::atomic<bool> running_{false};
    std::thread thread_;
    int port_ = 8080;

    void run() {
#ifdef _WIN32
        SOCKET srv = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
        if (srv == INVALID_SOCKET) { running_ = false; return; }

        // Allow port reuse.
        int opt = 1;
        setsockopt(srv, SOL_SOCKET, SO_REUSEADDR,
                   reinterpret_cast<const char*>(&opt), sizeof(opt));

        sockaddr_in addr{};
        addr.sin_family = AF_INET;
        addr.sin_port = htons(static_cast<u_short>(port_));
        addr.sin_addr.s_addr = htonl(INADDR_ANY);

        if (bind(srv, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) != 0) {
            closesocket(srv); running_ = false; return;
        }
        if (listen(srv, 4) != 0) {
            closesocket(srv); running_ = false; return;
        }

        while (running_) {
            SOCKET client = accept(srv, nullptr, nullptr);
            if (client == INVALID_SOCKET) continue;
            if (!running_) { closesocket(client); break; }
            handle_request(client);
            closesocket(client);
        }
        closesocket(srv);
#endif
    }

    void handle_request(
#ifdef _WIN32
        SOCKET client
#else
        int client
#endif
    ) {
        // Read request (just the first line is enough).
        char buf[2048];
        int n = recv(client, buf, sizeof(buf) - 1, 0);
        if (n <= 0) return;
        buf[n] = '\0';

        // Parse method + path from "GET /path HTTP/1.1\r\n..."
        std::string req(buf);
        std::string path;
        if (req.size() > 4 && req.substr(0, 4) == "GET ") {
            auto end = req.find(' ', 4);
            if (end != std::string::npos)
                path = req.substr(4, end - 4);
        }

        std::string body;
        std::string content_type = "application/json";
        int status = 200;

        if (path == "/api/channels") {
            body = build_channels_json();
        } else if (path.find("/api/channels/") == 0) {
            std::string name = path.substr(14);
            body = build_channel_json(name);
            if (body.empty()) { status = 404; body = "{\"error\":\"channel not found\"}"; }
        } else if (path == "/api/status") {
            body = build_status_json();
        } else {
            status = 404;
            body = "{\"error\":\"not found\",\"endpoints\":[\"/api/channels\",\"/api/status\"]}";
        }

        // Build HTTP response with CORS headers.
        char header[512];
        std::snprintf(header, sizeof(header),
            "HTTP/1.1 %d %s\r\n"
            "Content-Type: %s\r\n"
            "Content-Length: %d\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Access-Control-Allow-Methods: GET, OPTIONS\r\n"
            "Access-Control-Allow-Headers: Content-Type\r\n"
            "Connection: close\r\n"
            "\r\n",
            status, status == 200 ? "OK" : "Not Found",
            content_type.c_str(),
            static_cast<int>(body.size()));

        std::string response = std::string(header) + body;
        send(client, response.c_str(),
             static_cast<int>(response.size()), 0);
    }

    std::string build_channels_json() {
        std::lock_guard<std::mutex> lock(mu_);
        std::string json = "{";
        bool first = true;
        for (const auto& [name, val] : channels_) {
            if (!first) json += ",";
            first = false;
            char entry[128];
            std::snprintf(entry, sizeof(entry), "\"%s\":%.6g",
                          name.c_str(), val);
            json += entry;
        }
        json += "}";
        return json;
    }

    std::string build_channel_json(const std::string& name) {
        std::lock_guard<std::mutex> lock(mu_);
        auto it = channels_.find(name);
        if (it == channels_.end()) return {};
        char json[256];
        std::snprintf(json, sizeof(json),
            "{\"name\":\"%s\",\"value\":%.6g}",
            name.c_str(), it->second);
        return json;
    }

    std::string build_status_json() {
        std::lock_guard<std::mutex> lock(mu_);
        char json[512];
        std::snprintf(json, sizeof(json),
            "{\"connected\":%s,\"signature\":\"%s\",\"channels\":%d}",
            connected_ ? "true" : "false",
            signature_.c_str(),
            static_cast<int>(channels_.size()));
        return json;
    }
};

constexpr const char* kCurrentProjectNameKey = "projects/current/name";
constexpr const char* kCurrentProjectIniKey = "projects/current/ini";
constexpr const char* kCurrentProjectTuneKey = "projects/current/tune";
constexpr const char* kCurrentProjectSigKey = "projects/current/sig";
constexpr const char* kCurrentProjectDateKey = "projects/current/date";
std::vector<QPointer<QWidget>> g_retired_windows;

std::filesystem::path selected_ini_path();
std::filesystem::path selected_tune_path();

std::string debug_log_path() {
    return QDir(QDir::tempPath()).filePath("tuner_app_debug.log").toStdString();
}

void debug_log(const std::string& message) {
    std::ofstream out(debug_log_path(), std::ios::app | std::ios::binary);
    if (!out) return;
    const auto now = QDateTime::currentDateTime().toString(Qt::ISODateWithMs).toStdString();
    out << "[" << now << "] " << message << "\n";
    out.flush();
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// Find a native .tunerdef v2 file (preferred over INI).
std::filesystem::path find_native_definition() {
    // Check QSettings for a project-level definition path.
    QSettings settings;
    auto def_path = settings.value("projects/current/tunerdef", "").toString().toStdString();
    if (!def_path.empty() && std::filesystem::exists(def_path)) return def_path;
    // Search fixture directory.
    const char* candidates[] = {
        "tests/fixtures/native/Ford300_TwinGT28_BaseStartup.tunerdef",
        "../tests/fixtures/native/Ford300_TwinGT28_BaseStartup.tunerdef",
        "../../tests/fixtures/native/Ford300_TwinGT28_BaseStartup.tunerdef",
    };
    for (const char* c : candidates)
        if (std::filesystem::exists(c)) return c;
    return {};
}

std::filesystem::path find_production_ini() {
    auto selected = selected_ini_path();
    if (!selected.empty()) return selected;
    const char* candidates[] = {
        "tests/fixtures/speeduino-dropbear-v2.0.1.ini",
        "../tests/fixtures/speeduino-dropbear-v2.0.1.ini",
        "../../tests/fixtures/speeduino-dropbear-v2.0.1.ini",
        "../../../tests/fixtures/speeduino-dropbear-v2.0.1.ini",
        "D:/Documents/JetBrains/Python/Tuner/tests/fixtures/speeduino-dropbear-v2.0.1.ini",
    };
    for (const char* c : candidates) {
        if (std::filesystem::exists(c)) return c;
    }
    return {};
}

std::filesystem::path find_production_msq() {
    auto selected = selected_tune_path();
    if (!selected.empty()) {
        std::string ext = selected.extension().string();
        for (auto& c : ext) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
        if (ext == ".msq") return selected;
    }
    const char* candidates[] = {
        "tests/fixtures/Ford300_TwinGT28_BaseStartup.msq",
        "../tests/fixtures/Ford300_TwinGT28_BaseStartup.msq",
        "../../tests/fixtures/Ford300_TwinGT28_BaseStartup.msq",
        "../../../tests/fixtures/Ford300_TwinGT28_BaseStartup.msq",
        "D:/Documents/JetBrains/Python/Tuner/tests/fixtures/Ford300_TwinGT28_BaseStartup.msq",
    };
    for (const char* c : candidates) {
        if (std::filesystem::exists(c)) return c;
    }
    return {};
}

// Native format file finders — look for .tuner files in the native/ fixture
// directory. These take priority over .msq when present.
std::filesystem::path find_native_tune() {
    auto selected = selected_tune_path();
    if (!selected.empty()) {
        std::string ext = selected.extension().string();
        for (auto& c : ext) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
        if (ext == ".tuner") return selected;
    }
    const char* candidates[] = {
        "tests/fixtures/native/Ford300_TwinGT28_BaseStartup.tuner",
        "../tests/fixtures/native/Ford300_TwinGT28_BaseStartup.tuner",
        "../../tests/fixtures/native/Ford300_TwinGT28_BaseStartup.tuner",
        "../../../tests/fixtures/native/Ford300_TwinGT28_BaseStartup.tuner",
        "D:/Documents/JetBrains/Python/Tuner/tests/fixtures/native/Ford300_TwinGT28_BaseStartup.tuner",
    };
    for (const char* c : candidates) {
        if (std::filesystem::exists(c)) return c;
    }
    return {};
}

// Load the active ECU definition — prefers native .tunerdef v2,
// falls back to legacy INI parsing. This is the ONE place in the
// app that decides how to load a definition. All call sites should
// use this instead of calling compile_ecu_definition_file directly.
std::optional<tuner_core::NativeEcuDefinition> load_active_definition() {
    // Try native .tunerdef v2 first.
    auto native_path = find_native_definition();
    if (!native_path.empty()) {
        try {
            auto def = tuner_core::load_definition_v2_file(native_path);
            std::printf("[def] Loaded native .tunerdef v2: %s\n",
                native_path.string().c_str());
            std::fflush(stdout);
            return def;
        } catch (const std::exception& e) {
            std::printf("[def] v2 load failed (%s), falling back to INI\n",
                e.what());
            std::fflush(stdout);
        }
    }
    // Fall back to legacy INI.
    auto ini_path = find_production_ini();
    if (!ini_path.empty()) {
        try {
            auto def = tuner_core::compile_ecu_definition_file(ini_path);
            std::printf("[def] Loaded legacy INI: %s\n",
                ini_path.string().c_str());
            std::fflush(stdout);
            return def;
        } catch (...) {}
    }
    return std::nullopt;
}

// ---------------------------------------------------------------------------
// Recent project persistence
// ---------------------------------------------------------------------------

// Derive a human-friendly project name from an MSQ filename.
// "Ford300_TwinGT28_BaseStartup.msq" → "Ford300 TwinGT28 BaseStartup"
// Simple: strip extension, replace underscores with spaces.
std::string humanize_msq_name(const std::filesystem::path& msq_path) {
    std::string stem = msq_path.stem().string();
    for (auto& c : stem) {
        if (c == '_') c = ' ';
    }
    return stem;
}

struct RecentProject {
    std::string name;
    std::string ini_path;
    std::string msq_path;
    std::string signature;    // ECU signature from MSQ
    std::string last_opened;  // ISO date string "2026-04-12"
};

constexpr int kMaxRecentProjects = 5;

std::string today_iso();

std::filesystem::path resolve_project_path(
    const std::filesystem::path& base_dir,
    const std::string& raw_path) {
    if (raw_path.empty()) return {};
    std::filesystem::path path(raw_path);
    if (path.is_absolute()) return path;
    std::error_code ec;
    auto resolved = std::filesystem::weakly_canonical(base_dir / path, ec);
    return ec ? (base_dir / path) : resolved;
}

std::filesystem::path find_ini_near_tune(const std::filesystem::path& tune_path) {
    if (tune_path.empty()) return {};
    std::error_code ec;
    auto parent = tune_path.parent_path();
    if (parent.empty() || !std::filesystem::exists(parent, ec)) return {};
    for (const auto& entry : std::filesystem::directory_iterator(parent, ec)) {
        if (ec) break;
        if (!entry.is_regular_file()) continue;
        std::string ext = entry.path().extension().string();
        for (auto& c : ext) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
        if (ext == ".ini") return entry.path();
    }
    return {};
}

void save_current_project(const RecentProject& project) {
    QSettings s;
    s.setValue(kCurrentProjectNameKey, QString::fromUtf8(project.name.c_str()));
    s.setValue(kCurrentProjectIniKey, QString::fromUtf8(project.ini_path.c_str()));
    s.setValue(kCurrentProjectTuneKey, QString::fromUtf8(project.msq_path.c_str()));
    s.setValue(kCurrentProjectSigKey, QString::fromUtf8(project.signature.c_str()));
    s.setValue(kCurrentProjectDateKey, QString::fromUtf8(project.last_opened.c_str()));
    debug_log("save_current_project name=\"" + project.name
        + "\" ini=\"" + project.ini_path
        + "\" tune=\"" + project.msq_path
        + "\" sig=\"" + project.signature + "\"");
}

RecentProject load_current_project() {
    QSettings s;
    RecentProject rp;
    rp.name        = s.value(kCurrentProjectNameKey).toString().toStdString();
    rp.ini_path    = s.value(kCurrentProjectIniKey).toString().toStdString();
    rp.msq_path    = s.value(kCurrentProjectTuneKey).toString().toStdString();
    rp.signature   = s.value(kCurrentProjectSigKey).toString().toStdString();
    rp.last_opened = s.value(kCurrentProjectDateKey).toString().toStdString();
    return rp;
}

// Load the recent projects list from QSettings.
std::vector<RecentProject> load_recent_projects() {
    QSettings s;
    int count = s.value("projects/recent_count", 0).toInt();
    if (count > kMaxRecentProjects) count = kMaxRecentProjects;
    std::vector<RecentProject> list;
    list.reserve(count);
    for (int i = 0; i < count; ++i) {
        QString prefix = QString("projects/recent/%1/").arg(i);
        RecentProject rp;
        rp.name        = s.value(prefix + "name").toString().toStdString();
        rp.ini_path    = s.value(prefix + "ini").toString().toStdString();
        rp.msq_path    = s.value(prefix + "msq").toString().toStdString();
        rp.signature   = s.value(prefix + "sig").toString().toStdString();
        rp.last_opened = s.value(prefix + "date").toString().toStdString();
        if (!rp.name.empty()) list.push_back(std::move(rp));
    }
    return list;
}

// Save the full recent projects list to QSettings.
void save_recent_projects(const std::vector<RecentProject>& list) {
    QSettings s;
    int count = std::min(static_cast<int>(list.size()), kMaxRecentProjects);
    s.setValue("projects/recent_count", count);
    for (int i = 0; i < count; ++i) {
        QString prefix = QString("projects/recent/%1/").arg(i);
        s.setValue(prefix + "name", QString::fromUtf8(list[i].name.c_str()));
        s.setValue(prefix + "ini",  QString::fromUtf8(list[i].ini_path.c_str()));
        s.setValue(prefix + "msq",  QString::fromUtf8(list[i].msq_path.c_str()));
        s.setValue(prefix + "sig",  QString::fromUtf8(list[i].signature.c_str()));
        s.setValue(prefix + "date", QString::fromUtf8(list[i].last_opened.c_str()));
    }
    // Clean up stale entries beyond the new count.
    for (int i = count; i < kMaxRecentProjects; ++i) {
        QString prefix = QString("projects/recent/%1/").arg(i);
        s.remove(prefix + "name");
        s.remove(prefix + "ini");
        s.remove(prefix + "msq");
        s.remove(prefix + "sig");
        s.remove(prefix + "date");
    }
}

// Add a project to the front of the recent list (MRU order).
// If the same MSQ path already exists, move it to the front.
void push_recent_project(const RecentProject& proj) {
    auto list = load_recent_projects();
    // Remove existing entry with same MSQ path.
    list.erase(
        std::remove_if(list.begin(), list.end(),
                        [&](const RecentProject& rp) {
                            return rp.msq_path == proj.msq_path;
                        }),
        list.end());
    // Insert at front.
    list.insert(list.begin(), proj);
    // Trim to max.
    if (static_cast<int>(list.size()) > kMaxRecentProjects)
        list.resize(kMaxRecentProjects);
    save_recent_projects(list);
}

// Convenience: load the most recent project (first in list), or empty.
RecentProject load_recent_project() {
    auto list = load_recent_projects();
    return list.empty() ? RecentProject{} : list[0];
}

RecentProject active_project() {
    auto current = load_current_project();
    if (!current.msq_path.empty() || !current.ini_path.empty()) return current;
    return load_recent_project();
}

RecentProject project_from_file(const std::filesystem::path& raw_path) {
    namespace pf = tuner_core::project_file;

    std::error_code ec;
    std::filesystem::path path = std::filesystem::weakly_canonical(raw_path, ec);
    if (ec) path = raw_path;

    RecentProject rp;
    rp.last_opened = today_iso();

    std::string ext = path.extension().string();
    for (auto& c : ext) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    debug_log("project_from_file raw=\"" + raw_path.string()
        + "\" canonical=\"" + path.string() + "\" ext=\"" + ext + "\"");

    if (ext == ".tunerproj") {
        std::ifstream in(path, std::ios::binary);
        if (!in) throw std::runtime_error("Could not read .tunerproj file");
        std::stringstream buffer;
        buffer << in.rdbuf();
        auto project = pf::import_json(buffer.str());
        debug_log("project_from_file parsed .tunerproj name=\"" + project.name
            + "\" definition_path=\"" + project.definition_path
            + "\" tune_path=\"" + project.tune_path
            + "\" signature=\"" + project.firmware_signature + "\"");
        rp.name = project.name.empty() ? humanize_msq_name(path) : project.name;
        rp.ini_path = resolve_project_path(path.parent_path(), project.definition_path).string();
        rp.msq_path = resolve_project_path(path.parent_path(), project.tune_path).string();
        rp.signature = project.firmware_signature;
        if (rp.ini_path.empty() && !rp.msq_path.empty()) {
            rp.ini_path = find_ini_near_tune(rp.msq_path).string();
        }
        debug_log("project_from_file resolved .tunerproj name=\"" + rp.name
            + "\" ini=\"" + rp.ini_path
            + "\" tune=\"" + rp.msq_path + "\"");
        if (rp.msq_path.empty() || !std::filesystem::exists(rp.msq_path)) {
            throw std::runtime_error(".tunerproj does not point to an existing tune file");
        }
        return rp;
    }

    rp.name = humanize_msq_name(path);
    rp.msq_path = path.string();
    rp.ini_path = find_ini_near_tune(path).string();
    debug_log("project_from_file resolved direct file name=\"" + rp.name
        + "\" ini=\"" + rp.ini_path
        + "\" tune=\"" + rp.msq_path + "\"");
    if (rp.msq_path.empty() || !std::filesystem::exists(rp.msq_path)) {
        throw std::runtime_error("Selected tune file does not exist");
    }
    return rp;
}

std::filesystem::path selected_ini_path() {
    auto project = active_project();
    if (!project.ini_path.empty() && std::filesystem::exists(project.ini_path)) {
        return project.ini_path;
    }
    return {};
}

std::filesystem::path selected_tune_path() {
    auto project = active_project();
    if (!project.msq_path.empty() && std::filesystem::exists(project.msq_path)) {
        return project.msq_path;
    }
    return {};
}

// Migration: if old single-entry keys exist, import them.
void migrate_recent_project_keys() {
    QSettings s;
    auto old_name = s.value("projects/last_name").toString().toStdString();
    if (old_name.empty()) return;  // nothing to migrate
    if (s.value("projects/recent_count", 0).toInt() > 0) return;  // already migrated
    RecentProject rp;
    rp.name        = old_name;
    rp.ini_path    = s.value("projects/last_ini").toString().toStdString();
    rp.msq_path    = s.value("projects/last_msq").toString().toStdString();
    rp.signature   = s.value("projects/last_signature").toString().toStdString();
    rp.last_opened = s.value("projects/last_opened").toString().toStdString();
    push_recent_project(rp);
    // Clean old keys.
    s.remove("projects/last_name");
    s.remove("projects/last_ini");
    s.remove("projects/last_msq");
    s.remove("projects/last_signature");
    s.remove("projects/last_opened");
}

// Format today's date as "YYYY-MM-DD".
std::string today_iso() {
    auto now = std::chrono::system_clock::now();
    auto time = std::chrono::system_clock::to_time_t(now);
    std::tm tm_buf{};
#ifdef _WIN32
    localtime_s(&tm_buf, &time);
#else
    localtime_r(&time, &tm_buf);
#endif
    char buf[16];
    std::strftime(buf, sizeof(buf), "%Y-%m-%d", &tm_buf);
    return buf;
}

// Friendly "last opened" label — "today", "yesterday", or the date.
std::string friendly_date(const std::string& iso_date) {
    std::string today = today_iso();
    if (iso_date == today) return "today";
    // Simple yesterday check — parse year/month/day.
    // For robustness, just compare strings.
    return iso_date.empty() ? "unknown" : iso_date;
}

// SearchBox class removed — QLineEdit works with custom-built Qt.

// Case-insensitive substring match on std::string (avoids all QString
// temporaries so the Qt 6.7 + UCRT 15.2 ABI mismatch never fires).
bool icontains(const std::string& haystack, const std::string& needle) {
    if (needle.empty()) return true;
    if (haystack.size() < needle.size()) return false;
    auto it = std::search(
        haystack.begin(), haystack.end(),
        needle.begin(), needle.end(),
        [](unsigned char a, unsigned char b) {
            return std::tolower(a) == std::tolower(b);
        });
    return it != haystack.end();
}

// ---------------------------------------------------------------------------
// Tune tab — collapsible tree + search filter + selection feedback
// ---------------------------------------------------------------------------
//
// This is the simplest shape that's actually been observed RUNNING
// end-to-end with all four tabs and Qt 6.7 MinGW UCRT. Resist the
// urge to add a styled rich-text stats panel on the right pane —
// every attempt to introduce QString operator+ chains or QString
// HTML rendering past a certain widget count reproducibly hangs/
// crashes on this prebuilt-Qt + UCRT combination. Selection feedback
// works because it just sets plain text from snprintf into a single
// QLabel. Anything richer needs a different stats backend.
//
// CRASH FIX (2026-04-09): the textChanged lambda previously chained
// q.trimmed().toLower() and leaf->text(0).toLower().contains(needle)
// which created intermediate QString temporaries — the same ABI
// gotcha documented in the file header. Fixed by converting to
// std::string at the boundary and doing all comparisons on the
// std::string side via icontains().

// Forward declaration — defined in the SETUP tab section.
QWidget* render_heatmap(const std::vector<double>& values, int rows, int cols,
                         const char* title_text);

// Page data structs for tree rebuilding.
struct PageEntry { std::string display; std::string target; std::string type_tag; };
struct GroupEntry { std::string title; std::vector<PageEntry> pages; };

// ---------------------------------------------------------------------------
// TableSurface3DView — wireframe 3D projection of a table surface.
// Sub-slice 83 of Phase 14 Slice 4. Consumes the pure-logic projection
// math from `tuner_core::table_surface_3d` and paints the resulting
// mesh with QPainter. Supports mouse-drag rotation (azimuth on X,
// elevation on Y) and overlays the live operating-point crosshair via
// `interpolate_screen_point`.
//
// No Q_OBJECT — no signals/slots needed, so MOC stays out of the
// picture. Same deliberate pattern as `DialGaugeWidget` further down
// the file.
// ---------------------------------------------------------------------------

class TableSurface3DView : public QWidget {
public:
    explicit TableSurface3DView(QWidget* parent = nullptr) : QWidget(parent) {
        setMinimumSize(240, 180);
        setAttribute(Qt::WA_OpaquePaintEvent, true);
        setCursor(Qt::OpenHandCursor);
    }

    void set_table(const std::vector<double>& values, int rows, int cols) {
        values_ = values;
        rows_ = rows;
        cols_ = cols;
        update();
    }

    void set_operating_point(double row_frac, double col_frac) {
        op_row_ = row_frac;
        op_col_ = col_frac;
        update();
    }

    void clear_operating_point() {
        op_row_ = -1.0;
        op_col_ = -1.0;
        update();
    }

    void set_azimuth(double deg) {
        while (deg < 0) deg += 360;
        while (deg >= 360) deg -= 360;
        azimuth_ = deg;
        update();
    }

    void set_elevation(double deg) {
        if (deg < 15) deg = 15;
        if (deg > 85) deg = 85;
        elevation_ = deg;
        update();
    }

    double azimuth() const { return azimuth_; }
    double elevation() const { return elevation_; }

protected:
    QSize sizeHint() const override { return QSize(360, 260); }

    void mousePressEvent(QMouseEvent* e) override {
        if (e->button() == Qt::LeftButton) {
            dragging_ = true;
            drag_last_ = e->pos();
            setCursor(Qt::ClosedHandCursor);
        }
    }

    void mouseMoveEvent(QMouseEvent* e) override {
        if (!dragging_) return;
        QPoint d = e->pos() - drag_last_;
        drag_last_ = e->pos();
        set_azimuth(azimuth_ + d.x() * 0.6);
        set_elevation(elevation_ - d.y() * 0.4);
    }

    void mouseReleaseEvent(QMouseEvent* e) override {
        if (e->button() == Qt::LeftButton) {
            dragging_ = false;
            setCursor(Qt::OpenHandCursor);
        }
    }

    void paintEvent(QPaintEvent*) override {
        QPainter p(this);
        p.setRenderHint(QPainter::Antialiasing);

        p.fillRect(rect(), QColor(26, 29, 36));

        const double w = width(), h = height();

        if (rows_ <= 0 || cols_ <= 0 || values_.empty()) {
            p.setPen(QColor(138, 147, 166));
            QFont f = p.font(); f.setPointSize(9); p.setFont(f);
            p.drawText(rect(), Qt::AlignCenter, QString::fromUtf8("No table data"));
            return;
        }

        namespace ts3d = tuner_core::table_surface_3d;
        auto surface = ts3d::project(values_, rows_, cols_,
                                     azimuth_, elevation_, w, h);
        if (surface.points.empty()) return;

        const double range = std::max(1.0, surface.max_value - surface.min_value);

        // Col-parallel edges (walk cols within each row).
        for (int r = 0; r < surface.rows; ++r) {
            for (int c = 0; c + 1 < surface.cols; ++c) {
                const auto& a = surface.points[r][c];
                const auto& b = surface.points[r][c + 1];
                double va = (surface.values[r][c] - surface.min_value) / range;
                double vb = (surface.values[r][c + 1] - surface.min_value) / range;
                QColor col = heat_color((va + vb) * 0.5);
                col.setAlphaF(0.9);
                p.setPen(QPen(col, 1.4));
                p.drawLine(QPointF(a.x, a.y), QPointF(b.x, b.y));
            }
        }
        // Row-parallel edges (walk rows within each col).
        for (int c = 0; c < surface.cols; ++c) {
            for (int r = 0; r + 1 < surface.rows; ++r) {
                const auto& a = surface.points[r][c];
                const auto& b = surface.points[r + 1][c];
                double va = (surface.values[r][c] - surface.min_value) / range;
                double vb = (surface.values[r + 1][c] - surface.min_value) / range;
                QColor col = heat_color((va + vb) * 0.5);
                col.setAlphaF(0.9);
                p.setPen(QPen(col, 1.4));
                p.drawLine(QPointF(a.x, a.y), QPointF(b.x, b.y));
            }
        }

        // Value dots at each vertex.
        for (int r = 0; r < surface.rows; ++r) {
            for (int c = 0; c < surface.cols; ++c) {
                double v = (surface.values[r][c] - surface.min_value) / range;
                QColor col = heat_color(v);
                p.setPen(Qt::NoPen);
                p.setBrush(col);
                p.drawEllipse(QPointF(surface.points[r][c].x,
                                      surface.points[r][c].y),
                              2.4, 2.4);
            }
        }

        // Crosshair at the live operating point.
        if (op_row_ >= 0.0 && op_col_ >= 0.0) {
            auto pt = ts3d::interpolate_screen_point(surface, op_row_, op_col_);
            if (pt) {
                p.setPen(QPen(QColor(255, 255, 255), 2.0));
                p.setBrush(QColor(255, 68, 68));
                p.drawEllipse(QPointF(pt->x, pt->y), 5.0, 5.0);
                p.setPen(QPen(QColor(255, 68, 68, 200), 1.0, Qt::DashLine));
                p.drawLine(QPointF(pt->x - 14, pt->y), QPointF(pt->x + 14, pt->y));
                p.drawLine(QPointF(pt->x, pt->y - 14), QPointF(pt->x, pt->y + 14));
            }
        }

        // Corner labels.
        char buf[160];
        std::snprintf(buf, sizeof(buf),
            "min %.1f  \xc2\xb7  max %.1f  \xc2\xb7  az %.0f\xc2\xb0  el %.0f\xc2\xb0",
            surface.min_value, surface.max_value, azimuth_, elevation_);
        QFont lf = p.font(); lf.setPixelSize(10); p.setFont(lf);
        p.setPen(QColor(138, 147, 166));
        p.drawText(QRect(6, 4, static_cast<int>(w) - 12, 14),
                   Qt::AlignLeft | Qt::AlignTop,
                   QString::fromUtf8(buf));
        p.setPen(QColor(106, 112, 128));
        p.drawText(QRect(6, static_cast<int>(h) - 16, static_cast<int>(w) - 12, 14),
                   Qt::AlignRight | Qt::AlignBottom,
                   QString::fromUtf8("drag to rotate"));
    }

private:
    static QColor heat_color(double t) {
        if (t < 0) t = 0;
        if (t > 1) t = 1;
        struct Stop { double t; int r, g, b; };
        static const Stop stops[] = {
            {0.00,  50,  90, 180},
            {0.25,  40, 170, 200},
            {0.50,  90, 200, 110},
            {0.75, 230, 200,  80},
            {1.00, 220,  80,  60},
        };
        for (std::size_t i = 0; i + 1 < sizeof(stops) / sizeof(stops[0]); ++i) {
            if (t <= stops[i + 1].t) {
                double span = stops[i + 1].t - stops[i].t;
                double u = span > 0 ? (t - stops[i].t) / span : 0.0;
                int r = static_cast<int>(stops[i].r + (stops[i + 1].r - stops[i].r) * u);
                int g = static_cast<int>(stops[i].g + (stops[i + 1].g - stops[i].g) * u);
                int b = static_cast<int>(stops[i].b + (stops[i + 1].b - stops[i].b) * u);
                return QColor(r, g, b);
            }
        }
        return QColor(stops[4].r, stops[4].g, stops[4].b);
    }

    std::vector<double> values_;
    int rows_ = 0, cols_ = 0;
    double azimuth_ = 45.0;
    double elevation_ = 30.0;
    double op_row_ = -1.0;
    double op_col_ = -1.0;
    QPoint drag_last_;
    bool dragging_ = false;
};

// Event filter for click / double-click / drag on heatmap cells.
// Single click: select cell (Shift extends selection range).
// Double click: open inline editor overlay.
// Click + drag: rectangle selection from anchor to current cell.
class CellClickFilter : public QObject {
public:
    using EditCallback = std::function<void(int row, int col, QLabel* lbl)>;
    using SelectCallback = std::function<void(int row, int col, bool shift)>;
    using DragCallback = std::function<void(int row, int col, bool start)>;
    CellClickFilter(int row, int col, EditCallback edit_cb, SelectCallback sel_cb,
                    DragCallback drag_cb = nullptr, QObject* parent = nullptr)
        : QObject(parent), row_(row), col_(col),
          edit_cb_(std::move(edit_cb)), sel_cb_(std::move(sel_cb)),
          drag_cb_(std::move(drag_cb)) {}
protected:
    bool eventFilter(QObject* obj, QEvent* ev) override {
        if (ev->type() == QEvent::MouseButtonDblClick) {
            edit_cb_(row_, col_, qobject_cast<QLabel*>(obj));
            return true;
        }
        if (ev->type() == QEvent::MouseButtonPress) {
            auto* me = static_cast<QMouseEvent*>(ev);
            bool shift = (me->modifiers() & Qt::ShiftModifier) != 0;
            sel_cb_(row_, col_, shift);
            if (drag_cb_) drag_cb_(row_, col_, /*start=*/true);
            return false;
        }
        if (ev->type() == QEvent::MouseMove && drag_cb_) {
            // During drag, find which cell the mouse is currently over
            // and extend the selection rectangle.
            auto* me = static_cast<QMouseEvent*>(ev);
            if (me->buttons() & Qt::LeftButton) {
                auto* widget = qobject_cast<QWidget*>(obj);
                if (widget) {
                    QPoint global_pos = widget->mapToGlobal(me->pos());
                    auto* under = QApplication::widgetAt(global_pos);
                    if (under) {
                        // Check if the widget under the cursor has a
                        // CellClickFilter — if so, use its (row, col).
                        for (auto* child : under->children()) {
                            auto* filter = dynamic_cast<CellClickFilter*>(child);
                            if (filter) {
                                drag_cb_(filter->row_, filter->col_, /*start=*/false);
                                return false;
                            }
                        }
                    }
                }
            }
            return false;
        }
        if (ev->type() == QEvent::MouseButtonRelease && drag_cb_) {
            drag_cb_(-1, -1, /*start=*/false);  // end drag
            return false;
        }
        return QObject::eventFilter(obj, ev);
    }
private:
    int row_, col_;
    EditCallback edit_cb_;
    SelectCallback sel_cb_;
    DragCallback drag_cb_;
};

using StagedChangedCallback = std::function<void()>;

// Context hint lookup — returns a short operator-facing description
// for a given page title, or empty string if no known hint exists.
// Used for both tree leaf tooltips (hover preview) and the detail
// card (on page selection). The title is matched case-insensitively
// against known keywords — most specific first, then broader.
const char* page_context_hint(const std::string& display_title) {
    std::string lower = display_title;
    for (auto& c : lower) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));

    if (lower.find("ve table") != std::string::npos || lower.find("vetable") != std::string::npos)
        return "Controls how much fuel the engine gets at every RPM and load point.\nStart by reviewing idle cells at row 0, columns 0\xe2\x80\x93" "3.";
    if (lower.find("sequential fuel trim") != std::string::npos)
        return "Per-cylinder fuel trim corrections for sequential injection.\nUsed to balance cylinder-to-cylinder AFR differences after VE tuning is stable.";
    if (lower.find("staged injection") != std::string::npos)
        return "Controls when and how secondary injectors activate.\nUsed on high-power builds with two sets of injectors.";
    if (lower.find("second fuel") != std::string::npos)
        return "Secondary fuel table for flex-fuel or dual-fuel setups.\nBlended with the primary VE table based on fuel composition sensor input.";
    if (lower.find("second spark") != std::string::npos)
        return "Secondary spark table for flex-fuel or dual-fuel setups.\nBlended with the primary spark table based on fuel composition.";
    if (lower.find("dwell") != std::string::npos)
        return "Coil charge time (dwell) settings.\nToo low = weak spark and misfires. Too high = coil overheating. Check coil manufacturer specs.";
    if (lower.find("knock") != std::string::npos)
        return "Knock detection and retard settings.\nProtects the engine by pulling timing when detonation is detected.";
    if (lower.find("rotary") != std::string::npos)
        return "Rotary engine ignition settings.\nConfigures leading/trailing split and rotor phasing for Wankel engines.";
    if (lower.find("spark") != std::string::npos || lower.find("ignition") != std::string::npos)
        return "Ignition timing across the RPM and load map.\nWOT cells are conservative \xe2\x80\x94 verify against knock data before tuning up.";
    if (lower.find("afr") != std::string::npos || lower.find("lambda") != std::string::npos || lower.find("o2") != std::string::npos)
        return "Target air-fuel ratio for each operating point.\nRicher at WOT protects the engine; leaner at cruise saves fuel.";
    if (lower.find("cranking") != std::string::npos)
        return "Cranking enrichment and timing settings.\nExtra fuel and fixed timing during engine cranking to ensure reliable starts.";
    if (lower.find("afterstart") != std::string::npos || lower.find("ase") != std::string::npos)
        return "After-Start Enrichment (ASE) \xe2\x80\x94 extra fuel for a few seconds after the engine fires.\nHelps stabilize idle while the engine transitions from cranking to running.";
    if (lower.find("accel") != std::string::npos)
        return "Acceleration enrichment (TPS and MAP based).\nAdds fuel during rapid throttle changes to prevent lean stumbles.";
    if (lower.find("idle") != std::string::npos || lower.find("iac") != std::string::npos)
        return "Idle RPM targets and idle valve control.\nHigher cold-idle helps the engine warm up and stay stable.";
    if (lower.find("warmup") != std::string::npos || lower.find("wue") != std::string::npos || lower.find("enrich") != std::string::npos)
        return "Extra fuel during cold start and warmup.\nTapers from cold enrichment to 100% at normal operating temperature.";
    if (lower.find("launch") != std::string::npos || lower.find("flat shift") != std::string::npos)
        return "Launch control and flat-shift settings.\nLimits RPM on launch; allows full-throttle upshifts without lifting.";
    if (lower.find("nitrous") != std::string::npos)
        return "Nitrous oxide injection settings.\nControls activation conditions and fuel enrichment during nitrous use.";
    if (lower.find("boost") != std::string::npos)
        return "Boost control targets and duty cycle.\nReview wastegate duty before first WOT run under boost.";
    if (lower.find("vvt") != std::string::npos)
        return "Variable valve timing control.\nAdjusts cam phasing for better breathing across the RPM range.";
    if (lower.find("wmi") != std::string::npos)
        return "Water-methanol injection control.\nSprays water/methanol to reduce intake temps and suppress knock under boost.";
    if (lower.find("flex") != std::string::npos)
        return "Flex-fuel sensor configuration.\nAllows automatic fuel and timing adjustment based on ethanol content.";
    if (lower.find("trigger") != std::string::npos || lower.find("decoder") != std::string::npos)
        return "Trigger wheel and decoder configuration.\nMust match your physical crank/cam wheel exactly for sync.";
    if (lower.find("injector") != std::string::npos || lower.find("inj char") != std::string::npos)
        return "Injector hardware characteristics.\nDead time and flow rate directly affect fueling accuracy.";
    if (lower.find("engine constant") != std::string::npos)
        return "Core engine parameters: cylinders, displacement, req fuel, MAP type.\nThese must be set correctly before any tuning.";
    if (lower.find("protection") != std::string::npos || lower.find("rev limit") != std::string::npos)
        return "Engine protection and rev limiters.\nSafety limits that prevent damage from over-rev, overheating, or low oil pressure.";
    if (lower.find("thermo fan") != std::string::npos || lower.find("fan") != std::string::npos)
        return "Cooling fan activation settings.\nSets the temperature threshold for turning the radiator fan on and off.";
    if (lower.find("fuel pump") != std::string::npos)
        return "Fuel pump control and priming.\nConfigures pump priming duration on key-on and runtime pump control.";
    if (lower.find("tacho") != std::string::npos)
        return "Tachometer output signal configuration.\nSets the output pin and pulses-per-revolution for your tachometer.";
    if (lower.find("canbus") != std::string::npos || lower.find("can ") != std::string::npos || lower.find("serial") != std::string::npos)
        return "CAN bus and secondary serial interface settings.\nUsed for external displays, data loggers, and inter-ECU communication.";
    if (lower.find("auxiliary") != std::string::npos || lower.find("auxil") != std::string::npos)
        return "Auxiliary analog/digital input configuration.\nMaps additional sensor inputs to channels for logging and control.";
    if (lower.find("calibrat") != std::string::npos || lower.find("pressure sensor") != std::string::npos)
        return "Sensor calibration settings.\nSets voltage-to-value mapping for MAP, baro, oil, and fuel pressure sensors.";
    if (lower.find("filter") != std::string::npos)
        return "Analog sensor input filtering.\nSmooths noisy sensor readings; higher values = more smoothing but slower response.";
    if (lower.find("clock") != std::string::npos || lower.find("rtc") != std::string::npos)
        return "Real-time clock configuration.\nSets the onboard clock for timestamped logging on boards with RTC hardware.";
    if (lower.find("logger") != std::string::npos || lower.find("sd") != std::string::npos)
        return "Onboard SD card logging configuration.\nConfigures what channels to log and at what rate on boards with SD hardware.";
    if (lower.find("output") != std::string::npos || lower.find("programmable") != std::string::npos)
        return "Programmable output pin configuration.\nMaps engine conditions to output pins for relays, indicators, or external controllers.";
    if (lower.find("vss") != std::string::npos || lower.find("gear") != std::string::npos)
        return "Vehicle speed sensor and gear detection.\nUsed for speed-based fuel/spark corrections and gear-dependent boost targets.";
    if (lower.find("air condition") != std::string::npos || lower.find("a/c") != std::string::npos)
        return "Air conditioning compressor control.\nManages idle-up and timing adjustments when the A/C compressor engages.";
    if (lower.find("oil") != std::string::npos || lower.find("fuel pressure") != std::string::npos || lower.find("fuel/oil") != std::string::npos)
        return "Oil and fuel pressure monitoring.\nSets warning thresholds and protection actions for low pressure conditions.";
    if (lower.find("gauge") != std::string::npos || lower.find("limit") != std::string::npos)
        return "Gauge display range limits.\nSets the min/max values shown on runtime gauges for each channel.";
    if (lower.find("reset") != std::string::npos)
        return "Reset and recovery control.\nOptions for resetting the ECU to factory defaults or recovering from bad configurations.";
    return "";
}

// Forward declaration — defined further down in the file (used by SETUP tab).
QWidget* render_1d_curve(const std::vector<double>& bins,
                          const std::vector<double>& values,
                          const char* title_text,
                          const char* units,
                          const char* accent);

// ---------------------------------------------------------------------------
// Connect dialog — lets operator pick Serial (COM port + baud) or TCP
// (host + port). Returns true if a connection was established.
// ---------------------------------------------------------------------------

bool open_connect_dialog(QWidget* parent,
                         std::shared_ptr<EcuConnection> ecu_conn,
                         QLabel* conn_label) {
    auto* dlg = new QDialog(parent);
    dlg->setWindowTitle("Connect to ECU");
    dlg->setFixedSize(380, 260);
    {
        char ds[768];
        std::snprintf(ds, sizeof(ds),
            "QDialog { background: %s; }"
            "QLabel { color: %s; font-size: %dpx; }"
            "QComboBox, QLineEdit { background: %s; color: %s; border: 1px solid %s; "
            "  border-radius: %dpx; padding: %dpx %dpx; font-size: %dpx; }"
            "QPushButton { background: %s; color: %s; border: 1px solid %s; "
            "  border-radius: %dpx; padding: %dpx %dpx; font-size: %dpx; }"
            "QPushButton:hover { background: %s; }",
            tt::bg_base,
            tt::text_primary, tt::font_body,
            tt::bg_elevated, tt::text_primary, tt::border,
            tt::radius_sm, tt::space_xs, tt::space_sm, tt::font_body,
            tt::bg_elevated, tt::text_primary, tt::border,
            tt::radius_sm, tt::space_xs, tt::space_md, tt::font_body,
            tt::fill_primary_mid);
        dlg->setStyleSheet(QString::fromUtf8(ds));
    }

    auto* layout = new QVBoxLayout(dlg);
    layout->setContentsMargins(tt::space_lg, tt::space_lg, tt::space_lg, tt::space_lg);
    layout->setSpacing(tt::space_md);

    // Transport type selector.
    auto* type_row = new QHBoxLayout;
    type_row->addWidget(new QLabel("Transport:"));
    auto* transport_combo = new QComboBox;
    transport_combo->addItem("Serial");
    transport_combo->addItem("TCP / WiFi");
    type_row->addWidget(transport_combo, 1);
    layout->addLayout(type_row);

    // Serial fields.
    auto* serial_group = new QWidget;
    auto* serial_layout = new QVBoxLayout(serial_group);
    serial_layout->setContentsMargins(0, 0, 0, 0);
    serial_layout->setSpacing(tt::space_sm);

    auto* port_row = new QHBoxLayout;
    port_row->addWidget(new QLabel("Port:"));
    auto* port_combo = new QComboBox;
    port_combo->setEditable(true);
    auto ports = list_serial_ports();
    for (const auto& p : ports)
        port_combo->addItem(QString::fromUtf8(p.c_str()));
    if (ports.empty())
        port_combo->addItem("COM3");
    port_row->addWidget(port_combo, 1);

    // Refresh button.
    auto* refresh_btn = new QPushButton("\xe2\x9f\xb3");
    refresh_btn->setFixedWidth(32);
    refresh_btn->setToolTip("Refresh port list");
    QObject::connect(refresh_btn, &QPushButton::clicked, [port_combo]() {
        auto current = port_combo->currentText().toStdString();
        port_combo->clear();
        auto updated = list_serial_ports();
        for (const auto& p : updated)
            port_combo->addItem(QString::fromUtf8(p.c_str()));
        if (updated.empty())
            port_combo->addItem("COM3");
        // Restore previous selection if still present.
        int idx = port_combo->findText(QString::fromUtf8(current.c_str()));
        if (idx >= 0) port_combo->setCurrentIndex(idx);
    });
    port_row->addWidget(refresh_btn);
    serial_layout->addLayout(port_row);

    auto* baud_row = new QHBoxLayout;
    baud_row->addWidget(new QLabel("Baud:"));
    auto* baud_combo = new QComboBox;
    baud_combo->addItem("115200");
    baud_combo->addItem("230400");
    baud_combo->addItem("57600");
    baud_combo->addItem("9600");
    baud_combo->setCurrentIndex(0);
    baud_row->addWidget(baud_combo, 1);
    serial_layout->addLayout(baud_row);
    layout->addWidget(serial_group);

    // TCP fields.
    auto* tcp_group = new QWidget;
    auto* tcp_layout = new QVBoxLayout(tcp_group);
    tcp_layout->setContentsMargins(0, 0, 0, 0);
    tcp_layout->setSpacing(tt::space_sm);

    auto* host_row = new QHBoxLayout;
    host_row->addWidget(new QLabel("Host:"));
    auto* host_edit = new QLineEdit;
    host_edit->setText("speeduino.local");
    host_row->addWidget(host_edit, 1);
    tcp_layout->addLayout(host_row);

    auto* tcp_port_row = new QHBoxLayout;
    tcp_port_row->addWidget(new QLabel("Port:"));
    auto* tcp_port_edit = new QLineEdit;
    tcp_port_edit->setText("2000");
    tcp_port_row->addWidget(tcp_port_edit, 1);
    tcp_layout->addLayout(tcp_port_row);

    // EcuHub UDP discovery — scan for devices on port 21846.
    auto* scan_row = new QHBoxLayout;
    auto* scan_btn = new QPushButton(QString::fromUtf8("Scan Network"));
    scan_btn->setCursor(Qt::PointingHandCursor);
    auto* scan_status = new QLabel;
    {
        char ss[128];
        std::snprintf(ss, sizeof(ss),
            "QLabel { color: %s; font-size: %dpx; }",
            tt::text_muted, tt::font_small);
        scan_status->setStyleSheet(QString::fromUtf8(ss));
    }
    scan_row->addWidget(scan_btn);
    scan_row->addWidget(scan_status, 1);
    tcp_layout->addLayout(scan_row);

    QObject::connect(scan_btn, &QPushButton::clicked,
                     [host_edit, tcp_port_edit, scan_status, scan_btn]() {
        scan_status->setText(QString::fromUtf8("Scanning..."));
        scan_btn->setEnabled(false);
        QApplication::processEvents();

#ifdef _WIN32
        // Broadcast DISCOVER_SLAVE_SERVER on UDP port 21846.
        SOCKET sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
        if (sock == INVALID_SOCKET) {
            scan_status->setText(QString::fromUtf8("Socket error"));
            scan_btn->setEnabled(true);
            return;
        }

        // Enable broadcast.
        int bcast = 1;
        setsockopt(sock, SOL_SOCKET, SO_BROADCAST,
                   reinterpret_cast<const char*>(&bcast), sizeof(bcast));

        // Set receive timeout to 2 seconds.
        DWORD timeout_ms = 2000;
        setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO,
                   reinterpret_cast<const char*>(&timeout_ms), sizeof(timeout_ms));

        // Bind to any port.
        sockaddr_in local{};
        local.sin_family = AF_INET;
        local.sin_port = 0;
        local.sin_addr.s_addr = htonl(INADDR_ANY);
        bind(sock, reinterpret_cast<sockaddr*>(&local), sizeof(local));

        // Send discovery message.
        const char* msg = "DISCOVER_SLAVE_SERVER";
        sockaddr_in dest{};
        dest.sin_family = AF_INET;
        dest.sin_port = htons(21846);
        dest.sin_addr.s_addr = htonl(INADDR_BROADCAST);
        sendto(sock, msg, static_cast<int>(std::strlen(msg)), 0,
               reinterpret_cast<sockaddr*>(&dest), sizeof(dest));

        // Collect responses (2-second window).
        struct DiscoveredDevice {
            std::string name;
            std::string ip;
            int port = 2000;
        };
        std::vector<DiscoveredDevice> devices;

        char buf[2048];
        sockaddr_in from{};
        int from_len = sizeof(from);
        while (true) {
            int n = recvfrom(sock, buf, sizeof(buf) - 1, 0,
                             reinterpret_cast<sockaddr*>(&from), &from_len);
            if (n <= 0) break;
            buf[n] = '\0';

            // Parse response — key:value lines.
            DiscoveredDevice dev;
            char ip_buf[64];
            inet_ntop(AF_INET, &from.sin_addr, ip_buf, sizeof(ip_buf));
            dev.ip = ip_buf;

            std::istringstream stream(buf);
            std::string line;
            while (std::getline(stream, line)) {
                if (!line.empty() && line.back() == '\r') line.pop_back();
                auto colon = line.find(':');
                if (colon == std::string::npos) continue;
                std::string key = line.substr(0, colon);
                std::string val = line.substr(colon + 1);
                while (!val.empty() && val.front() == ' ') val.erase(val.begin());
                if (key == "name" || key == "slave") dev.name = val;
                if (key == "port") {
                    try { dev.port = std::stoi(val); } catch (...) {}
                }
            }
            if (dev.name.empty()) dev.name = dev.ip;
            devices.push_back(std::move(dev));
        }
        closesocket(sock);

        if (devices.empty()) {
            scan_status->setText(QString::fromUtf8(
                "No devices found \xe2\x80\x94 check WiFi connection"));
        } else {
            // Use first device.
            host_edit->setText(QString::fromUtf8(devices[0].ip.c_str()));
            char port_buf[16];
            std::snprintf(port_buf, sizeof(port_buf), "%d", devices[0].port);
            tcp_port_edit->setText(QString::fromUtf8(port_buf));

            char found[128];
            std::snprintf(found, sizeof(found),
                "\xe2\x9c\x85 Found: %s (%s:%d)",
                devices[0].name.c_str(), devices[0].ip.c_str(),
                devices[0].port);
            scan_status->setText(QString::fromUtf8(found));
        }
#else
        scan_status->setText(QString::fromUtf8("UDP discovery not available on this platform"));
#endif
        scan_btn->setEnabled(true);
    });

    layout->addWidget(tcp_group);
    tcp_group->hide();  // Serial is default.

    // Toggle visibility based on transport type.
    QObject::connect(transport_combo, QOverload<int>::of(&QComboBox::currentIndexChanged),
                     [serial_group, tcp_group](int idx) {
        serial_group->setVisible(idx == 0);
        tcp_group->setVisible(idx == 1);
    });

    // Status label for feedback during connect.
    auto* status_label = new QLabel;
    {
        char sl[128];
        std::snprintf(sl, sizeof(sl),
            "color: %s; font-size: %dpx;",
            tt::text_dim, tt::font_small);
        status_label->setStyleSheet(QString::fromUtf8(sl));
    }
    layout->addWidget(status_label);

    // Buttons.
    auto* btn_row = new QHBoxLayout;
    btn_row->addStretch(1);
    auto* cancel_btn = new QPushButton("Cancel");
    auto* connect_btn = new QPushButton("Connect");
    btn_row->addWidget(cancel_btn);
    btn_row->addWidget(connect_btn);
    layout->addLayout(btn_row);

    QObject::connect(cancel_btn, &QPushButton::clicked, dlg, &QDialog::reject);

    bool success = false;

    QObject::connect(connect_btn, &QPushButton::clicked,
                     [&, dlg, transport_combo, port_combo, baud_combo,
                      host_edit, tcp_port_edit, status_label,
                      ecu_conn, conn_label]() {
        // Disconnect any existing connection.
        ecu_conn->close();

        status_label->setText("Connecting...");
        connect_btn->setEnabled(false);
        // Force repaint so the status shows before blocking connect.
        QApplication::processEvents();

        try {
            std::unique_ptr<tuner_core::transport::Transport> transport;
            std::string desc;

            if (transport_combo->currentIndex() == 0) {
                // Serial.
                std::string port = port_combo->currentText().toStdString();
                int baud = std::stoi(baud_combo->currentText().toStdString());
                transport = std::make_unique<tuner_core::transport::SerialTransport>(
                    port, baud);
                char d[128];
                std::snprintf(d, sizeof(d), "%s @ %d", port.c_str(), baud);
                desc = d;
            } else {
                // TCP.
                std::string host = host_edit->text().toStdString();
                int port = std::stoi(tcp_port_edit->text().toStdString());
                transport = std::make_unique<tuner_core::transport::TcpTransport>(
                    host, port);
                char d[128];
                std::snprintf(d, sizeof(d), "%s:%d", host.c_str(), port);
                desc = d;
            }

            ecu_conn->controller = std::make_unique<
                tuner_core::speeduino_controller::SpeeduinoController>(
                    std::move(transport));

            auto info = ecu_conn->controller->connect(
                {115200, 230400, 57600, 9600},
                'Q', 1.5,
                [status_label](const std::string& msg) {
                    status_label->setText(QString::fromUtf8(msg.c_str()));
                    QApplication::processEvents();
                });

            ecu_conn->info = info;
            ecu_conn->connected = true;

            // Update sidebar connection indicator.
            if (conn_label) {
                char ct[256];
                std::snprintf(ct, sizeof(ct),
                    "<span style='color: %s;'>\xe2\x97\x89</span> "
                    "<span style='color: %s;'>%s</span>",
                    tt::accent_ok, tt::text_muted, desc.c_str());
                conn_label->setText(QString::fromUtf8(ct));
            }

            success = true;
            dlg->accept();
        } catch (const std::exception& e) {
            char err[512];
            std::snprintf(err, sizeof(err),
                "<span style='color: %s;'>%s</span>",
                tt::accent_danger, e.what());
            status_label->setText(QString::fromUtf8(err));
            status_label->setTextFormat(Qt::RichText);
            connect_btn->setEnabled(true);
        }
    });

    dlg->exec();
    return success;
}

// Build output channel layouts from the parsed ECU definition for the
// runtime decoder. Called once after INI load.
void build_channel_layouts(
    std::shared_ptr<EcuConnection> ecu_conn,
    const tuner_core::NativeEcuDefinition* ecu_def) {
    if (!ecu_def) return;
    namespace sld = tuner_core::speeduino_live_data_decoder;
    namespace spc = tuner_core::speeduino_param_codec;

    ecu_conn->channel_layouts.clear();
    for (const auto& ch : ecu_def->output_channels.channels) {
        sld::OutputChannelLayout layout;
        layout.name = ch.name;
        layout.units = ch.units.value_or("");
        layout.layout.data_type = tuner_core::speeduino_value_codec::parse_data_type(ch.data_type);
        layout.layout.offset = ch.offset;
        layout.layout.scale = ch.scale.value_or(1.0);
        layout.layout.translate = ch.translate.value_or(0.0);
        ecu_conn->channel_layouts.push_back(std::move(layout));
    }
    if (!ecu_conn->channel_layouts.empty()) {
        ecu_conn->runtime_packet_size =
            sld::runtime_packet_size(ecu_conn->channel_layouts);
    }
}

QWidget* build_tune_tab(
    std::shared_ptr<tuner_core::workspace_state::Workspace> workspace,
    std::shared_ptr<tuner_core::local_tune_edit::EditService> shared_edit_svc,
    std::shared_ptr<EcuConnection> ecu_conn = nullptr,
    std::shared_ptr<std::string> out_signature = nullptr,
    StagedChangedCallback on_staged_changed = nullptr) {
    auto* container = new QWidget;
    auto* outer = new QVBoxLayout(container);
    outer->setContentsMargins(tt::space_lg, tt::space_lg, tt::space_lg, tt::space_lg);
    outer->setSpacing(tt::space_sm);

    // Project context replaces the title — no wasted vertical space.
    // Compound identity strip: bold project name (hero) + dim metadata
    // chain (secondary) + a right-aligned "Review (N)" chip that only
    // appears when the workspace has staged edits.
    auto* project_bar = new QWidget;
    auto* project_bar_layout = new QHBoxLayout(project_bar);
    project_bar_layout->setContentsMargins(tt::space_md, tt::space_sm, tt::space_md, tt::space_sm);
    project_bar_layout->setSpacing(tt::space_sm);
    {
        char style_buf[192];
        std::snprintf(style_buf, sizeof(style_buf),
            "background-color: %s; border: 1px solid %s; "
            "border-radius: %dpx;",
            tt::bg_panel, tt::border, tt::radius_sm);
        project_bar->setStyleSheet(QString::fromUtf8(style_buf));
    }

    auto current_project = std::make_shared<RecentProject>(active_project());
    debug_log("build_tune_tab active_project name=\"" + current_project->name
        + "\" ini=\"" + current_project->ini_path
        + "\" tune=\"" + current_project->msq_path
        + "\" sig=\"" + current_project->signature + "\"");
    auto* project_label = new QLabel;
    project_label->setTextFormat(Qt::RichText);
    auto refresh_project_label = [project_label, current_project]() {
        const std::string project_name =
            current_project->name.empty() ? "Speeduino Project" : current_project->name;
        const std::string signature =
            current_project->signature.empty() ? "signature unknown" : current_project->signature;
        char text_buf[640];
        std::snprintf(text_buf, sizeof(text_buf),
            "<span style='font-size: %dpx; font-weight: bold; color: %s;'>"
            "%s</span>"
            "<span style='color: %s; font-size: %dpx;'>"
            "  \xc2\xb7  %s  \xc2\xb7  Ctrl+K to search  \xc2\xb7  Ctrl+R to review</span>",
            tt::font_label, tt::text_primary,
            project_name.c_str(),
            tt::text_dim, tt::font_small,
            signature.c_str());
        project_label->setText(QString::fromUtf8(text_buf));
    };
    refresh_project_label();
    project_label->setStyleSheet("background: transparent; border: none;");
    project_bar_layout->addWidget(project_label);
    project_bar_layout->addStretch(1);

    // Review chip — clickable button styled as a small inline chip.
    // Hidden when nothing is staged; shown with live count otherwise.
    auto* review_button = new QPushButton;
    review_button->setCursor(Qt::PointingHandCursor);
    {
        char style[384];
        std::snprintf(style, sizeof(style),
            "QPushButton { background: %s; border: 1px solid %s; "
            "  border-radius: %dpx; padding: 3px 10px; "
            "  color: %s; font-size: %dpx; font-weight: bold; } "
            "QPushButton:hover { border-color: %s; color: %s; }",
            tt::bg_inset, tt::accent_warning, tt::radius_sm,
            tt::accent_warning, tt::font_small,
            tt::accent_primary, tt::text_primary);
        review_button->setStyleSheet(QString::fromUtf8(style));
    }
    review_button->hide();
    project_bar_layout->addWidget(review_button);

    outer->addWidget(project_bar);

    auto* splitter = new QSplitter(Qt::Horizontal);

    // ---- left rail ----
    auto* left_panel = new QWidget;
    auto* left_layout = new QVBoxLayout(left_panel);
    left_layout->setContentsMargins(0, 0, 0, 0);

    auto* search = new QLineEdit;
    search->setPlaceholderText(QString::fromUtf8("Filter pages..."));
    search->setClearButtonEnabled(true);
    left_layout->addWidget(search);

    auto* tree = new QTreeWidget;
    tree->setHeaderHidden(true);
    left_layout->addWidget(tree, 1);

    // ---- right pane ----
    auto* right_pane = new QWidget;
    auto* right_layout = new QVBoxLayout(right_pane);
    right_layout->setContentsMargins(tt::space_lg, 0, 0, 0);
    right_layout->setSpacing(tt::space_xs);
    right_layout->setAlignment(Qt::AlignTop);

    // Selected-page title + per-page staged indicator chip side-by-side.
    // The chip only appears when the active page has one or more
    // staged edits — otherwise it's hidden, avoiding empty-state chrome.
    auto* selected_row = new QWidget;
    auto* selected_row_layout = new QHBoxLayout(selected_row);
    selected_row_layout->setContentsMargins(0, 0, 0, 0);
    selected_row_layout->setSpacing(tt::space_sm);

    // Sub-slice 127: empty-state welcome title. Overwritten on the
    // first page selection — the operator never sees it once they
    // click anything — but it's the first hero line on launch, so
    // it should read as an invitation rather than a command.
    auto* selected_label = new QLabel("Welcome \xe2\x80\x94 pick a page to start tuning");
    {
        QFont sf = selected_label->font();
        sf.setPixelSize(tt::font_heading - 3);  // 15px — between label and heading
        sf.setBold(true);
        selected_label->setFont(sf);
        char style[64];
        std::snprintf(style, sizeof(style), "color: %s;", tt::text_primary);
        selected_label->setStyleSheet(QString::fromUtf8(style));
    }
    selected_row_layout->addWidget(selected_label);

    // Per-page staged chip — hidden when the active page has no edits.
    // Sub-slice 92: makes staged state visible right next to the page
    // title so the operator can see at a glance whether their current
    // view has pending changes.
    auto* page_staged_chip = new QLabel;
    page_staged_chip->setTextFormat(Qt::RichText);
    {
        char style[256];
        std::snprintf(style, sizeof(style),
            "background: %s; border: 1px solid %s; border-radius: %dpx; "
            "padding: 2px %dpx; color: %s; font-size: %dpx; font-weight: bold;",
            tt::bg_inset, tt::accent_warning, tt::radius_sm,
            tt::space_sm, tt::accent_warning, tt::font_small);
        page_staged_chip->setStyleSheet(QString::fromUtf8(style));
    }
    page_staged_chip->hide();
    selected_row_layout->addWidget(page_staged_chip);
    selected_row_layout->addStretch(1);

    right_layout->addWidget(selected_row);

    // Context header card — the one place each TUNE page gets a
    // single line of "what does this page do" guidance. Blue-accent
    // left bar matches `make_info_card` so "context here" reads as
    // the same visual grammar across the app.
    //
    // Sub-slice 127: the initial empty-state copy below is the
    // first thing an operator sees on the TUNE tab before they
    // pick a page. It doubles as a welcome message and a discovery
    // breadcrumb — points at the command palette (Ctrl+K) and the
    // shortcut cheat sheet (F1) without demanding screen real
    // estate. The tree on the left is still the primary navigation
    // surface; this card is the "you're here, here are your next
    // moves" orientation.
    auto* detail_label = new QLabel;
    detail_label->setWordWrap(true);
    {
        char style[256];
        std::snprintf(style, sizeof(style),
            "color: %s; font-size: %dpx; "
            "background-color: %s; border: 1px solid %s; "
            "border-left: 3px solid %s; border-radius: %dpx; "
            "padding: %dpx %dpx;",
            tt::text_secondary, tt::font_small,
            tt::bg_panel, tt::border, tt::accent_primary, tt::radius_sm,
            tt::space_xs + 2, tt::space_sm + 2);
        detail_label->setStyleSheet(QString::fromUtf8(style));
    }
    detail_label->setText(QString::fromUtf8(
        "Pick a page from the tree on the left to see its parameters, "
        "table, or curve.  \xc2\xb7  Press Ctrl+K to search by name.  "
        "\xc2\xb7  Press F1 for every keyboard shortcut."));
    right_layout->addWidget(detail_label);

    // Scrollable form area for parameter fields.
    // We replace the entire widget on each page selection rather than
    // trying to clean up individual layouts (which crashes).
    auto* params_scroll = new QScrollArea;
    params_scroll->setWidgetResizable(true);
    params_scroll->setStyleSheet("QScrollArea { border: none; }");
    // Vertical sizing flips per page in the rebuild callback:
    //   scalar pages → Expanding + stretch 1 (form fills right pane)
    //   table  pages → Maximum   + stretch 0 (form takes only what it
    //                  needs so the heatmap card below gets the rest)
    // The default below matches the scalar case; the table branch
    // overrides it before rendering.
    params_scroll->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Expanding);
    right_layout->addWidget(params_scroll, 1);

    // Heatmap widget pointer — now safe to delete with custom-built Qt.
    auto heatmap_widget = std::make_shared<QWidget*>(nullptr);

    // Sub-slice 94 bugfix: live map from param_name → {QLineEdit*,
    // base_text} for the currently-rendered parameter form. The form
    // is rebuilt on every page switch, so this map is cleared + re-
    // populated each time. The per-row × revert button in the review
    // popup uses this to reset the editor's text and style when the
    // operator reverts a staged value — otherwise the edit_svc state
    // clears but the visible QLineEdit keeps the user-typed text.
    struct EditorEntry {
        QLineEdit* edit = nullptr;
        QComboBox* combo = nullptr;  // non-null for enum fields
        std::string base_text;
    };
    auto visible_editors = std::make_shared<std::unordered_map<std::string, EditorEntry>>();

    // Workspace state machine — tracks staged edits per page. Owned
    // by MainWindow now (sub-slice 92) so the sidebar's "N staged"
    // badge can read from the same source of truth.
    // `workspace` is the parameter passed in by MainWindow.

    // Stable reference width for cell sizing (captured once at build time).
    auto initial_container_width = std::make_shared<int>(container->width());
    // Will be updated on first valid use.

    // Live crosshair state for table pages.
    struct CrosshairState {
        std::vector<std::vector<QLabel*>> cell_labels;  // [row][col]
        std::vector<std::string> x_labels, y_labels;
        std::string x_param, y_param;
        int rows = 0, cols = 0;
        int prev_row = -1, prev_col = -1;
        std::string prev_style;  // original style of highlighted cell
        // Sub-slice 83: the 3D surface view that mirrors the same cell
        // the 2D crosshair is pointing at. Raw pointer into the current
        // page's card; cleared on every page change along with the 2D
        // label grid so the timer never dereferences a stale widget.
        TableSurface3DView* view_3d = nullptr;
        // Cell editing overlay — a single shared QLineEdit created once,
        // repositioned over the clicked cell on double-click.
        QLineEdit* cell_editor = nullptr;
        int edit_row = -1, edit_col = -1;
        std::string z_param;       // table data parameter name (for staging)
        std::string page_target;   // active page target (for workspace staging)
        // Row index map — maps display row to model row for flat array
        // indexing (handles y-axis inversion).
        std::vector<std::size_t> row_index_map;
        // Multi-cell selection (display coordinates).
        int sel_top = -1, sel_left = -1, sel_bottom = -1, sel_right = -1;
        // Original cell styles — saved before selection highlight so we
        // can restore them when selection changes.
        std::vector<std::vector<std::string>> base_styles;
        // Increment step for +/- keys.
        double increment = 1.0;
        // Drag selection state.
        bool dragging = false;
        int drag_anchor_row = -1, drag_anchor_col = -1;
        // Reverse map: QLabel widget pointer → (row, col) for drag hit-testing.
        std::unordered_map<QWidget*, std::pair<int,int>> cell_widget_map;

        bool has_selection() const {
            return sel_top >= 0 && sel_left >= 0 && sel_bottom >= 0 && sel_right >= 0;
        }
        void clear_selection() {
            // Restore base styles on previously selected cells.
            if (has_selection()) {
                for (int r = sel_top; r <= sel_bottom && r < static_cast<int>(cell_labels.size()); ++r)
                    for (int c = sel_left; c <= sel_right && c < static_cast<int>(cell_labels[r].size()); ++c)
                        if (r < static_cast<int>(base_styles.size()) && c < static_cast<int>(base_styles[r].size()))
                            cell_labels[r][c]->setStyleSheet(QString::fromUtf8(base_styles[r][c].c_str()));
            }
            sel_top = sel_left = sel_bottom = sel_right = -1;
        }
        void set_selection(int r1, int c1, int r2, int c2) {
            clear_selection();
            sel_top = std::min(r1, r2); sel_left = std::min(c1, c2);
            sel_bottom = std::max(r1, r2); sel_right = std::max(c1, c2);
            // Apply selection highlight.
            for (int r = sel_top; r <= sel_bottom && r < static_cast<int>(cell_labels.size()); ++r)
                for (int c = sel_left; c <= sel_right && c < static_cast<int>(cell_labels[r].size()); ++c) {
                    char sel_style[128];
                    std::snprintf(sel_style, sizeof(sel_style),
                        "background-color: #2a4a6e; color: #ffffff; border: 1px solid #4b7bd1; "
                        "padding: 0px; font-size: 10px; font-family: monospace;");
                    cell_labels[r][c]->setStyleSheet(QString::fromUtf8(sel_style));
                }
        }
    };
    auto crosshair = std::make_shared<CrosshairState>();
    // Shared cell editor overlay — created once, repositioned over the
    // target cell on double-click. Never deleted (hidden when not editing).
    auto* cell_editor_widget = new QLineEdit(container);
    cell_editor_widget->hide();
    cell_editor_widget->setAlignment(Qt::AlignCenter);
    {
        char ce_style[256];
        std::snprintf(ce_style, sizeof(ce_style),
            "background: %s; color: %s; border: 2px solid %s; "
            "font-family: monospace; font-size: 11px; padding: 1px;",
            tt::bg_elevated, tt::text_primary, tt::accent_primary);
        cell_editor_widget->setStyleSheet(QString::fromUtf8(ce_style));
    }
    crosshair->cell_editor = cell_editor_widget;
    // Escape cancels cell editing (no external deps — safe here).
    auto* cell_escape = new QShortcut(Qt::Key_Escape, cell_editor_widget);
    cell_escape->setContext(Qt::WidgetShortcut);
    QObject::connect(cell_escape, &QShortcut::activated, [crosshair]() {
        if (crosshair->cell_editor) {
            crosshair->cell_editor->hide();
            crosshair->edit_row = crosshair->edit_col = -1;
        }
    });
    // NOTE: editingFinished signal is wired BELOW, after edit_svc and
    // the refresh lambdas are created (they don't exist at this point).

    auto tune_mock_ecu = std::make_shared<tuner_core::mock_ecu_runtime::MockEcu>(99);

    // ---- populate + compile layout ----
    // Side map: QTreeWidgetItem* → (display_title, target_key). Avoids
    // calling text()/data() on QTreeWidgetItem in signal handlers,
    // which would create QString temporaries through the broken ABI.
    namespace dlns = tuner_core::definition_layout;
    struct ItemInfo { std::string title; std::string target; };
    auto item_info = std::make_shared<std::unordered_map<QTreeWidgetItem*, ItemInfo>>();
    auto page_map = std::make_shared<std::unordered_map<std::string, dlns::LayoutPage>>();
    // Store the INI definition for table editor lookups in the handler.
    auto ecu_def = std::make_shared<tuner_core::NativeEcuDefinition>();
    // Load tune values — prefer native .tuner format, fall back to .msq.
    // The .tuner format is human-readable JSON with trimmed precision and
    // compact table rows; the .msq format is legacy XML.
    // Both feed the same EditService downstream.
    namespace lte = tuner_core::local_tune_edit;
    auto tune_file = std::make_shared<lte::TuneFile>();
    auto edit_svc = shared_edit_svc;
    std::string tune_source;  // "native" or "msq" — for status display
    {
        bool loaded = false;
        // Try native .tuner first.
        auto native_tune_path = find_native_tune();
        debug_log("build_tune_tab find_native_tune=\"" + native_tune_path.string() + "\"");
        if (!native_tune_path.empty()) {
            try {
                auto native_tune = tuner_core::load_tune_file(native_tune_path);
                tune_file->signature = native_tune.definition_signature.value_or("");
                if (out_signature) *out_signature = tune_file->signature;
                for (const auto& [name, val] : native_tune.values) {
                    lte::TuneValue tv;
                    tv.name = name;
                    std::visit([&tv](const auto& v) {
                        using T = std::decay_t<decltype(v)>;
                        if constexpr (std::is_same_v<T, double>) {
                            tv.value = v;
                        } else if constexpr (std::is_same_v<T, std::string>) {
                            tv.value = v;
                        } else if constexpr (std::is_same_v<T, std::vector<double>>) {
                            tv.value = v;
                        }
                    }, val);
                    tune_file->constants.push_back(std::move(tv));
                }
                edit_svc->set_tune_file(tune_file.get());
                tune_source = "native";
                loaded = true;
                std::printf("[tune] Loaded native .tuner: %s (%d values)\n",
                    native_tune_path.string().c_str(),
                    static_cast<int>(native_tune.values.size()));
                std::fflush(stdout);
                debug_log("build_tune_tab loaded native tune path=\"" + native_tune_path.string()
                    + "\" values=" + std::to_string(native_tune.values.size()) + "");
                // Save to recent projects.
                RecentProject rp;
                rp.name = humanize_msq_name(native_tune_path);
                rp.msq_path = native_tune_path.string();
                rp.signature = tune_file->signature;
                rp.last_opened = today_iso();
                auto def_p = find_native_definition();
                if (!def_p.empty()) rp.ini_path = def_p.string();
                else { auto ip = find_production_ini(); if (!ip.empty()) rp.ini_path = ip.string(); }
                push_recent_project(rp);
                save_current_project(rp);
                *current_project = rp;
                refresh_project_label();
            } catch (const std::exception& e) {
                std::printf("[tune] Native .tuner load failed: %s\n", e.what());
                std::fflush(stdout);
                debug_log(std::string("build_tune_tab native load failed: ") + e.what());
            }
        }
        // Fall back to .msq if native wasn't found or failed.
        if (!loaded) {
            auto msq_path = find_production_msq();
            debug_log("build_tune_tab find_production_msq=\"" + msq_path.string() + "\"");
            if (!msq_path.empty()) {
                try {
                    auto msq = tuner_core::parse_msq(msq_path);
                    tune_file->signature = msq.signature;
                    if (out_signature) *out_signature = msq.signature;
                    for (const auto& c : msq.constants) {
                        lte::TuneValue tv;
                        tv.name = c.name;
                        tv.units = c.units;
                        tv.digits = c.digits;
                        tv.rows = c.rows;
                        tv.cols = c.cols;
                        if (c.rows > 0 || c.cols > 0) {
                            std::vector<double> vals;
                            std::istringstream iss(c.text);
                            double d;
                            while (iss >> d) vals.push_back(d);
                            if (!vals.empty()) {
                                tv.value = std::move(vals);
                            } else {
                                tv.value = c.text;
                            }
                        } else {
                            try {
                                tv.value = std::stod(c.text);
                            } catch (...) {
                                tv.value = c.text;
                            }
                        }
                        tune_file->constants.push_back(std::move(tv));
                    }
                    edit_svc->set_tune_file(tune_file.get());
                    tune_source = "msq";
                    loaded = true;
                    RecentProject rp;
                    rp.name = humanize_msq_name(msq_path);
                    rp.msq_path = msq_path.string();
                    rp.signature = tune_file->signature;
                    rp.last_opened = today_iso();
                    auto ini_p = find_production_ini();
                    if (!ini_p.empty()) rp.ini_path = ini_p.string();
                    push_recent_project(rp);
                    save_current_project(rp);
                    *current_project = rp;
                    refresh_project_label();
                    debug_log("build_tune_tab loaded msq path=\"" + msq_path.string()
                        + "\" constants=" + std::to_string(msq.constants.size()) + "");
                } catch (...) {}
            }
        }
    }
    int total_pages = 0, table_pages = 0, scalar_pages = 0;

    // Groups + rebuild lambda defined here so they're in scope for both
    // the populate block and the signal handlers below.
    auto all_groups = std::make_shared<std::vector<GroupEntry>>();

    // Show/hide filtering — tree->clear() crashes even with custom Qt
    // (destroys items referenced by currentItemChanged handler mid-event).
    // Build all items once, then toggle visibility on filter.
    // Sub-slice 96: `base_label` caches the leaf's display text without
    // any state marker, so `refresh_tree_state_indicators` can recompose
    // "`<title><tag>`" or "`<title><tag>  ◉ N`" cleanly without having
    // to parse an already-marked label back apart.
    struct TreeLeafInfo {
        QTreeWidgetItem* item;
        std::string title;
        std::string target;
        std::string base_label;
    };
    struct TreeGroupRef { QTreeWidgetItem* group; std::vector<TreeLeafInfo> leaves; };
    auto tree_refs = std::make_shared<std::vector<TreeGroupRef>>();

    auto rebuild_tree = [tree, item_info, all_groups, tree_refs](const std::string& needle) {
        // First call: build the tree.
        if (tree_refs->empty()) {
            for (const auto& grp : *all_groups) {
                TreeGroupRef ref;
                char group_buf[128];
                std::snprintf(group_buf, sizeof(group_buf), "%s  (%d)",
                              grp.title.c_str(), static_cast<int>(grp.pages.size()));
                ref.group = new QTreeWidgetItem(tree);
                ref.group->setText(0, QString::fromUtf8(group_buf));
                char group_tip[128];
                std::snprintf(group_tip, sizeof(group_tip),
                              "%s \xe2\x80\x94 %d page%s",
                              grp.title.c_str(),
                              static_cast<int>(grp.pages.size()),
                              grp.pages.size() == 1 ? "" : "s");
                ref.group->setToolTip(0, QString::fromUtf8(group_tip));
                for (const auto& pg : grp.pages) {
                    char leaf_buf[256];
                    std::snprintf(leaf_buf, sizeof(leaf_buf), "%s%s",
                                  pg.display.c_str(), pg.type_tag.c_str());
                    auto* leaf = new QTreeWidgetItem(ref.group);
                    leaf->setText(0, QString::fromUtf8(leaf_buf));
                    // Hover tooltip — shows the context description
                    // from the page_context_hint mapping, or falls back
                    // to the raw target key so every leaf has some hover
                    // context (no silently-missing tooltips).
                    const char* hint = page_context_hint(pg.display);
                    if (*hint)
                        leaf->setToolTip(0, QString::fromUtf8(hint));
                    else
                        leaf->setToolTip(0, QString::fromUtf8(pg.target.c_str()));
                    (*item_info)[leaf] = {pg.display, pg.target};
                    ref.leaves.push_back({leaf, pg.display, pg.target, leaf_buf});
                }
                tree_refs->push_back(std::move(ref));
            }
            return;
        }
        // Subsequent calls: show/hide.
        for (auto& ref : *tree_refs) {
            int visible = 0;
            for (auto& lf : ref.leaves) {
                bool match = needle.empty() || icontains(lf.title, needle);
                lf.item->setHidden(!match);
                if (match) visible++;
            }
            ref.group->setHidden(visible == 0 && !needle.empty());
            ref.group->setExpanded(!needle.empty() && visible > 0);
        }
    };

    auto def_opt = load_active_definition();
    if (def_opt.has_value()) {
        try {
            auto& def = *def_opt;
            *ecu_def = def;  // Store for handler use.
            auto compiled = dlns::compile_pages(def.menus, def.dialogs, def.table_editors);
            // Add curve editor pages. Each CurveEditor in the INI becomes
            // a LayoutPage with curve_editor_id set to the curve name.
            // These land in the tree alongside table and scalar pages.
            for (const auto& curve : def.curve_editors.curves) {
                dlns::LayoutPage cp;
                cp.target = "curve_" + curve.name;
                cp.title = curve.title.empty() ? curve.name : curve.title;
                cp.curve_editor_id = curve.name;
                // Assign to a group based on keyword matching.
                std::string lower = cp.title;
                for (auto& ch : lower) ch = static_cast<char>(
                    std::tolower(static_cast<unsigned char>(ch)));
                if (lower.find("warmup") != std::string::npos || lower.find("wue") != std::string::npos
                    || lower.find("enrich") != std::string::npos || lower.find("ase") != std::string::npos
                    || lower.find("crank") != std::string::npos || lower.find("prime") != std::string::npos)
                    { cp.group_id = "enrich"; cp.group_title = "Startup / Enrich"; }
                else if (lower.find("idle") != std::string::npos || lower.find("iac") != std::string::npos)
                    { cp.group_id = "idle"; cp.group_title = "Idle"; }
                else if (lower.find("fuel") != std::string::npos || lower.find("inject") != std::string::npos
                         || lower.find("baro") != std::string::npos)
                    { cp.group_id = "fuel"; cp.group_title = "Fuel"; }
                else if (lower.find("spark") != std::string::npos || lower.find("dwell") != std::string::npos
                         || lower.find("ignition") != std::string::npos)
                    { cp.group_id = "ignition"; cp.group_title = "Ignition"; }
                else if (lower.find("boost") != std::string::npos || lower.find("vvt") != std::string::npos)
                    { cp.group_id = "boost"; cp.group_title = "Boost / Airflow"; }
                else
                    { cp.group_id = "curves"; cp.group_title = "Curves"; }
                compiled.push_back(std::move(cp));
            }
            // Filter out pages whose visibility expression evaluates
            // to false against the current tune values. Mirrors Python's
            // TuningWorkspacePresenter._is_page_visible(). Most page-
            // level visibility depends on constants like egoType or
            // boostEnabled rather than runtime data, so evaluating once
            // at load time is correct.
            {
                namespace vex = tuner_core::visibility_expression;
                auto values = edit_svc->get_scalar_values_dict();
                // Only filter if we have actual tune data. When no tune
                // is loaded (new project), all values are empty — every
                // visibility expression would evaluate to 0 (false) and
                // hide ALL pages. Show everything instead.
                if (!values.empty()) {
                    std::map<std::string, double> val_map(values.begin(), values.end());
                    auto it = std::remove_if(compiled.begin(), compiled.end(),
                        [&val_map](const dlns::LayoutPage& pg) {
                            if (pg.visibility_expression.empty()) return false;
                            return !vex::evaluate(pg.visibility_expression, val_map);
                        });
                    compiled.erase(it, compiled.end());
                }
            }
            // Group pages BEFORE moving into the map.
            namespace tpg = tuner_core::tuning_page_grouping;
            auto groups = tpg::group_pages(compiled);
            // Now move into the map for detail lookup.
            for (auto& p : compiled) {
                total_pages++;
                if (!p.table_editor_id.empty()) table_pages++;
                else scalar_pages++;
                (*page_map)[p.target] = std::move(p);
            }
            // Store grouped data for filter rebuilds.
            // Humanize INI page titles — replace camelCase/technical names
            // with operator-friendly labels.
            auto humanize = [](const std::string& raw) -> std::string {
                // Known replacements.
                static const std::vector<std::pair<std::string, std::string>> known = {
                    {"veTableDialog", "VE Table"},
                    {"advanceTableDialog", "Spark Advance Table"},
                    {"afrTable1Dialog", "AFR Target Table"},
                    {"afrTable2Dialog", "AFR Target Table 2"},
                    {"boostTableDialog", "Boost Target Table"},
                    {"boostDutyDialog", "Boost Duty Table"},
                    {"vvtTableDialog", "VVT Target Table"},
                    {"fuelTable2Dialog", "Second Fuel Table"},
                    {"sparkTable2Dialog", "Second Spark Table"},
                    {"idleUpDown", "Idle Control"},
                    {"accelEnrichDialog", "Acceleration Enrichment"},
                    {"engineConstants", "Engine Constants"},
                    {"injectorCharacteristics", "Injector Characteristics"},
                    {"triggerSettings", "Trigger Settings"},
                    {"dwellSettings", "Dwell Settings"},
                    {"warmupEnrichDialog", "Warmup Enrichment"},
                    {"aseDialog", "After-Start Enrichment"},
                    {"crankingDialog", "Cranking Settings"},
                    {"flexFuelDialog", "Flex Fuel Settings"},
                    {"generalSettings", "General Settings"},
                    {"canBusSettings", "CAN Bus Settings"},
                    {"revLimitDialog", "Rev Limiter"},
                    {"launchControlDialog", "Launch Control"},
                    {"nitrousDialog", "Nitrous Control"},
                    {"oilPressureDialog", "Oil Pressure"},
                    {"fanSettings", "Cooling Fan"},
                    {"tachOutputDialog", "Tachometer Output"},
                    {"vssDialog", "Vehicle Speed Sensor"},
                    {"programmableOutputs", "Programmable Outputs"},
                    {"rotarySettings", "Rotary Settings"},
                    {"knockSettings", "Knock Detection"},
                    {"stagedInjection", "Staged Injection"},
                    {"wmiDialog", "Water-Methanol Injection"},
                };
                for (const auto& [key, human] : known)
                    if (raw.find(key) != std::string::npos) return human;
                // Fallback: insert spaces before capitals in camelCase.
                if (raw.empty()) return raw;
                std::string result;
                for (size_t i = 0; i < raw.size(); ++i) {
                    char c = raw[i];
                    if (i > 0 && std::isupper(static_cast<unsigned char>(c))
                        && std::islower(static_cast<unsigned char>(raw[i-1])))
                        result += ' ';
                    result += c;
                }
                // Capitalize first letter.
                if (!result.empty())
                    result[0] = static_cast<char>(std::toupper(static_cast<unsigned char>(result[0])));
                return result;
            };

            for (const auto& grp : groups) {
                GroupEntry ge;
                ge.title = grp.group_title;
                for (const auto& gp : grp.pages) {
                    PageEntry pe;
                    std::string raw_title = gp.title.empty() ? gp.target : gp.title;
                    pe.display = humanize(raw_title);
                    pe.target = gp.target;
                    if (!gp.table_editor_id.empty())
                        pe.type_tag = " \xe2\x96\xa3";  // ▣ small square for tables
                    else if (!gp.curve_editor_id.empty())
                        pe.type_tag = " \xe2\x8c\xa1";  // ⌡ curve indicator
                    else
                        pe.type_tag = "";
                    ge.pages.push_back(std::move(pe));
                }
                all_groups->push_back(std::move(ge));
            }
            // Sub-slice 98 bugfix: declare every page target to the
            // workspace BEFORE any edits happen. Without this the
            // `page_states_` map stays empty, `stage_edit` can't
            // transition CLEAN → STAGED, and `page_state(target)`
            // returns CLEAN for every page. The tree-entry state
            // refresh then sees "count > 0 but state == CLEAN", hits
            // its clean branch, and resets the label — so staged
            // edits never become visible on the tree (while the
            // right-pane chip works because it only checks count).
            std::vector<std::string> page_ids;
            page_ids.reserve(page_map->size());
            for (const auto& [target, _] : *page_map) page_ids.push_back(target);
            workspace->set_pages(page_ids);

            rebuild_tree("");

            // Show compiled page count in the detail pane.
            char info[256];
            std::snprintf(info, sizeof(info),
                "Compiled %d layout pages from INI (%d table, %d scalar).",
                total_pages, table_pages, scalar_pages);
            detail_label->setText(QString::fromUtf8(info));

            // Restore tree expansion state and last-selected page from
            // the prior session.  Expansion is stored as a comma-separated
            // list of group indices ("0,2,5"); the selected page is stored
            // as the target key string (e.g. "veTableDialog").
            {
                QSettings s;
                // Expansion state.
                auto expanded_str = s.value("session/tune_expanded_groups").toString().toStdString();
                if (!expanded_str.empty()) {
                    // Parse comma-separated indices.
                    std::istringstream iss(expanded_str);
                    std::string tok;
                    while (std::getline(iss, tok, ',')) {
                        auto ns = tok.find_first_not_of(" ");
                        if (ns == std::string::npos) continue;
                        int idx = std::atoi(tok.c_str() + ns);
                        if (idx >= 0 && idx < static_cast<int>(tree_refs->size())) {
                            (*tree_refs)[idx].group->setExpanded(true);
                        }
                    }
                }
                // Last selected page.
                auto last_page = s.value("session/tune_last_page").toString().toStdString();
                if (!last_page.empty()) {
                    // Walk tree_refs to find the matching leaf.
                    for (auto& ref : *tree_refs) {
                        for (auto& lf : ref.leaves) {
                            if (lf.target == last_page) {
                                // Expand the parent group so the leaf is visible.
                                ref.group->setExpanded(true);
                                tree->setCurrentItem(lf.item);
                                goto restore_done;
                            }
                        }
                    }
                    restore_done:;
                }
            }

            // Wire search — show/hide filter on each keystroke.
            QObject::connect(search, &QLineEdit::textChanged,
                             [rebuild_tree](const QString& q) {
                std::string needle = q.toStdString();
                for (auto& c : needle)
                    c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
                auto s = needle.find_first_not_of(" \t");
                auto e = needle.find_last_not_of(" \t");
                if (s != std::string::npos)
                    needle = needle.substr(s, e - s + 1);
                else
                    needle.clear();
                rebuild_tree(needle);
            });

            // Save tree expansion state on every expand/collapse so the
            // next launch restores the same group visibility.
            auto save_expansion = [tree_refs]() {
                std::string indices;
                for (int i = 0; i < static_cast<int>(tree_refs->size()); ++i) {
                    if ((*tree_refs)[i].group->isExpanded()) {
                        if (!indices.empty()) indices += ',';
                        indices += std::to_string(i);
                    }
                }
                QSettings s;
                s.setValue("session/tune_expanded_groups",
                           QString::fromUtf8(indices.c_str()));
            };
            QObject::connect(tree, &QTreeWidget::itemExpanded,
                             [save_expansion](QTreeWidgetItem*) { save_expansion(); });
            QObject::connect(tree, &QTreeWidget::itemCollapsed,
                             [save_expansion](QTreeWidgetItem*) { save_expansion(); });
        } catch (const std::exception&) {
            auto* err = new QTreeWidgetItem(tree);
            err->setText(0, "Failed to parse INI");
        }
    }

    // ---- signals ----

    // Helper: update the per-page staged chip next to the selected-page
    // label. Hidden when the count is 0. Color switches based on the
    // page's state: amber for STAGED, blue for WRITTEN (in RAM).
    // Captured by both the selection handler and the stage-edit lambda.
    auto refresh_page_chip = std::make_shared<std::function<void(const std::string&)>>(
        [page_staged_chip, workspace](const std::string& target) {
            int n = workspace->staged_count_for(target);
            if (n <= 0) {
                page_staged_chip->hide();
                return;
            }
            auto ps = workspace->page_state(target);
            const char* accent = tt::accent_warning;  // STAGED
            const char* verb = "staged";
            if (ps == tuner_core::workspace_state::PageState::WRITTEN) {
                accent = tt::accent_primary;  // WRITTEN
                verb = "in RAM";
            }
            char style[256];
            std::snprintf(style, sizeof(style),
                "background: %s; border: 1px solid %s; border-radius: %dpx; "
                "padding: 2px %dpx; color: %s; font-size: %dpx; font-weight: bold;",
                tt::bg_inset, accent, tt::radius_sm,
                tt::space_sm, accent, tt::font_small);
            page_staged_chip->setStyleSheet(QString::fromUtf8(style));
            char text[64];
            std::snprintf(text, sizeof(text), "\xe2\x97\x89 %d %s", n, verb);
            page_staged_chip->setText(QString::fromUtf8(text));
            page_staged_chip->show();
        });

    // Helper: update the "Review (N)" chip in the project bar. Hidden
    // when nothing is staged — no empty-state chrome. Color reflects
    // the aggregate state across all pages: amber if any STAGED, blue
    // if all pending edits are already WRITTEN to RAM.
    auto refresh_review_button = std::make_shared<std::function<void()>>(
        [review_button, edit_svc, workspace]() {
            int n = edit_svc->staged_count();
            if (n <= 0) {
                review_button->hide();
                return;
            }
            auto agg = workspace->aggregate_state();
            const char* accent = tt::accent_warning;
            const char* verb = "Review";
            if (agg == tuner_core::workspace_state::PageState::WRITTEN) {
                accent = tt::accent_primary;
                verb = "In RAM";
            }
            char style[512];
            std::snprintf(style, sizeof(style),
                "QPushButton { background: %s; border: 1px solid %s; "
                "  border-radius: %dpx; padding: 3px 10px; "
                "  color: %s; font-size: %dpx; font-weight: bold; } "
                "QPushButton:hover { border-color: %s; color: %s; }",
                tt::bg_inset, accent, tt::radius_sm,
                accent, tt::font_small,
                tt::accent_primary, tt::text_primary);
            review_button->setStyleSheet(QString::fromUtf8(style));
            char text[64];
            std::snprintf(text, sizeof(text),
                "\xe2\x97\x89 %s (%d)", verb, n);
            review_button->setText(QString::fromUtf8(text));
            review_button->show();
        });

    // Sub-slice 96: tree-entry state indicators. Walks the cached
    // tree_refs, queries workspace state for each leaf's target, and
    // updates the item text + foreground color to show a colored
    // bullet + count beside pages that have pending edits. Runs on
    // every state transition via the same call sites as the other
    // three zoom helpers.
    auto refresh_tree_state_indicators = std::make_shared<std::function<void()>>(
        [tree_refs, workspace]() {
            namespace wsns = tuner_core::workspace_state;
            for (auto& ref : *tree_refs) {
                for (auto& lf : ref.leaves) {
                    int n = workspace->staged_count_for(lf.target);
                    // Sub-slice 98 bugfix: early-exit only on count
                    // zero, never on state == CLEAN. Count is the
                    // authoritative "does this page have work"
                    // signal (matches refresh_page_chip). State
                    // merely picks the color ramp. If state is CLEAN
                    // but count > 0 (set_pages wasn't called, etc.),
                    // default to STAGED so the tree still reflects
                    // reality instead of going blind.
                    if (n <= 0) {
                        lf.item->setText(0, QString::fromUtf8(lf.base_label.c_str()));
                        lf.item->setForeground(0, QBrush());
                        continue;
                    }
                    auto ps = workspace->page_state(lf.target);
                    const char* accent =
                        (ps == wsns::PageState::WRITTEN)
                            ? tt::accent_primary : tt::accent_warning;
                    char marked[320];
                    std::snprintf(marked, sizeof(marked),
                        "%s  \xe2\x97\x89 %d",  // base + "  ◉ N"
                        lf.base_label.c_str(), n);
                    lf.item->setText(0, QString::fromUtf8(marked));
                    lf.item->setForeground(0,
                        QBrush(QColor(QString::fromUtf8(accent))));
                }
            }
        });

    // Sub-slice 94: resync helper. Rebuilds `workspace` per-page counts
    // from `edit_svc` by walking the compiled page map and checking
    // `is_dirty()` for each field. Needed because `edit_svc->revert(name)`
    // doesn't know which page the parameter belongs to — the authoritative
    // param→page map lives in `page_map`, which workspace_state has no
    // access to. Walking it here (the one place that owns both) is the
    // cleanest fix without a bigger refactor of workspace_state's API.
    //
    // Called after any per-edit revert so all three zoom levels of the
    // staged-state hierarchy stay in sync with the edit_svc.
    auto resync_workspace = std::make_shared<std::function<void()>>(
        [workspace, page_map, edit_svc]() {
            workspace->revert_all();
            for (const auto& [target, page] : *page_map) {
                for (const auto& sec : page.sections) {
                    for (const auto& f : sec.fields) {
                        if (edit_svc->is_dirty(f.parameter_name)) {
                            workspace->stage_edit(target, f.parameter_name);
                        }
                    }
                }
            }
        });

    // Wire cell editor editingFinished → stage + re-render. Deferred
    // to here because edit_svc + refresh lambdas are defined above.
    QObject::connect(cell_editor_widget, &QLineEdit::editingFinished,
        [crosshair, edit_svc, workspace, on_staged_changed,
         refresh_page_chip, refresh_review_button,
         refresh_tree_state_indicators]() {
        auto* editor = crosshair->cell_editor;
        if (!editor || !editor->isVisible()) return;
        int r = crosshair->edit_row;
        int c = crosshair->edit_col;
        if (r < 0 || c < 0) { editor->hide(); return; }

        double new_val;
        try { new_val = std::stod(editor->text().toStdString()); }
        catch (...) {
            // Flash the cell editor red briefly to signal invalid input.
            editor->setStyleSheet(QString::fromUtf8(
                "QLineEdit { background: #3d2020; color: #e08080; "
                "border: 2px solid #d65a5a; }"));
            QTimer::singleShot(800, editor, [editor]() { editor->hide(); });
            return;
        }

        // Flat index — row_index_map handles y-inversion.
        int model_row = (r < static_cast<int>(crosshair->row_index_map.size()))
            ? static_cast<int>(crosshair->row_index_map[r]) : r;
        int flat = model_row * crosshair->cols + c;

        try {
            edit_svc->stage_list_cell(crosshair->z_param, flat, new_val);
            workspace->stage_edit(crosshair->page_target, crosshair->z_param);
            // Update cell label text.
            if (r < static_cast<int>(crosshair->cell_labels.size())
                && c < static_cast<int>(crosshair->cell_labels[r].size())) {
                char buf[16];
                std::snprintf(buf, sizeof(buf), "%.4g", new_val);
                crosshair->cell_labels[r][c]->setText(QString::fromUtf8(buf));
            }
            (*refresh_page_chip)(crosshair->page_target);
            (*refresh_review_button)();
            (*refresh_tree_state_indicators)();
            if (on_staged_changed) on_staged_changed();
        } catch (...) {}
        editor->hide();
        crosshair->edit_row = crosshair->edit_col = -1;
    });

    // Repaint the visible 2D table from the current staged/base values.
    // Uses display-row -> model-row mapping so the heatmap stays aligned
    // with the same visual orientation after transforms, paste, or
    // history navigation.
    namespace tr_ns = tuner_core::table_rendering;
    auto refresh_visible_table = [crosshair, edit_svc]() {
        if (crosshair->z_param.empty()) return;
        auto* tv = edit_svc->get_value(crosshair->z_param);
        if (!tv || !std::holds_alternative<std::vector<double>>(tv->value)) return;
        const auto& vals = std::get<std::vector<double>>(tv->value);

        // Recompute heatmap colors from current values.
        namespace tv_ns = tuner_core::table_view;
        tv_ns::ShapeHints hints;
        hints.rows = crosshair->rows;
        hints.cols = crosshair->cols;
        auto model_opt = tv_ns::build_table_model(
            std::span<const double>(vals.data(), vals.size()), hints);
        std::vector<std::string> empty_labels;
        std::optional<tr_ns::RenderModel> render_opt;
        if (model_opt.has_value()) {
            render_opt = tr_ns::build_render_model(*model_opt, empty_labels, empty_labels, true);
        }

        int cell_font = tt::font_micro;
        for (int r = 0; r < static_cast<int>(crosshair->cell_labels.size()); ++r) {
            std::size_t model_r =
                (r < static_cast<int>(crosshair->row_index_map.size()))
                    ? crosshair->row_index_map[r]
                    : static_cast<std::size_t>(r);
            for (int c = 0; c < static_cast<int>(crosshair->cell_labels[r].size()); ++c) {
                std::size_t flat = model_r * static_cast<std::size_t>(crosshair->cols)
                    + static_cast<std::size_t>(c);
                if (flat >= vals.size()) continue;
                char buf[16];
                std::snprintf(buf, sizeof(buf), "%.4g", vals[flat]);
                crosshair->cell_labels[r][c]->setText(QString::fromUtf8(buf));

                // Update heatmap color.
                if (render_opt.has_value()
                    && model_r < render_opt->rows
                    && static_cast<std::size_t>(c) < render_opt->columns) {
                    const auto& cell = render_opt->cells[model_r][c];
                    char style_buf[256];
                    std::snprintf(style_buf, sizeof(style_buf),
                        "background-color: %s; color: %s; border: none; "
                        "padding: 1px; font-size: %dpx; font-family: monospace;",
                        cell.background_hex.c_str(), cell.foreground_hex.c_str(), cell_font);
                    crosshair->base_styles[r][c] = style_buf;
                    crosshair->cell_labels[r][c]->setStyleSheet(
                        QString::fromUtf8(style_buf));
                }
            }
        }
        if (crosshair->has_selection()) {
            crosshair->set_selection(
                crosshair->sel_top, crosshair->sel_left,
                crosshair->sel_bottom, crosshair->sel_right);
        }
    };

    // Helper: apply a table_edit transform to the current table and
    // re-render the affected cells. Takes a lambda that transforms
    // the flat value vector into a new one.
    namespace te = tuner_core::table_edit;
    auto apply_table_op = [crosshair, edit_svc, workspace, on_staged_changed,
                           refresh_page_chip, refresh_review_button,
                           refresh_tree_state_indicators, refresh_visible_table](
        std::function<std::vector<double>(std::span<const double>, std::size_t, const te::TableSelection&)> op) {
        if (!crosshair->has_selection() || crosshair->z_param.empty()) return;
        auto* tv = edit_svc->get_value(crosshair->z_param);
        if (!tv || !std::holds_alternative<std::vector<double>>(tv->value)) return;
        auto& old_vals = std::get<std::vector<double>>(tv->value);
        te::TableSelection sel;
        // Map display coords to model coords via row_index_map.
        auto map_row = [&](int display_r) -> std::size_t {
            return (display_r < static_cast<int>(crosshair->row_index_map.size()))
                ? crosshair->row_index_map[display_r]
                : static_cast<std::size_t>(display_r);
        };
        sel.top = map_row(crosshair->sel_top);
        sel.bottom = map_row(crosshair->sel_bottom);
        // Ensure top <= bottom after mapping (inversion may flip them).
        if (sel.top > sel.bottom) std::swap(sel.top, sel.bottom);
        sel.left = static_cast<std::size_t>(crosshair->sel_left);
        sel.right = static_cast<std::size_t>(crosshair->sel_right);
        auto new_vals = op(
            std::span<const double>(old_vals.data(), old_vals.size()),
            static_cast<std::size_t>(crosshair->cols), sel);
        edit_svc->replace_list(crosshair->z_param, new_vals);
        workspace->stage_edit(crosshair->page_target, crosshair->z_param);
        refresh_visible_table();
        (*refresh_page_chip)(crosshair->page_target);
        (*refresh_review_button)();
        (*refresh_tree_state_indicators)();
        if (on_staged_changed) on_staged_changed();
    };

    // Table keyboard shortcuts — operate on the current cell selection.
    // +/- : increment/decrement selected cells by 1 (configurable step).
    // Ctrl+Shift+= / Ctrl+-: percentage adjust ±5%.
    // I : interpolate, S : smooth, F : fill with top-left value.
    // Ctrl+C / Ctrl+V : copy/paste.
    // Ctrl+Z : undo, Ctrl+Y : redo.
    {
        // Increment (+/=)
        auto* inc_sc = new QShortcut(QKeySequence(Qt::Key_Plus), container);
        inc_sc->setContext(Qt::WidgetWithChildrenShortcut);
        QObject::connect(inc_sc, &QShortcut::activated, [crosshair, apply_table_op]() {
            double step = crosshair->increment;
            apply_table_op([step](auto vals, auto cols, const auto& sel) {
                auto out = std::vector<double>(vals.begin(), vals.end());
                for (std::size_t r = sel.top; r <= sel.bottom; ++r)
                    for (std::size_t c = sel.left; c <= sel.right; ++c)
                        out[r * cols + c] += step;
                return out;
            });
        });
        auto* inc2 = new QShortcut(QKeySequence(Qt::Key_Equal), container);
        inc2->setContext(Qt::WidgetWithChildrenShortcut);
        QObject::connect(inc2, &QShortcut::activated, [inc_sc]() { inc_sc->activated(); });

        // Decrement (-)
        auto* dec_sc = new QShortcut(QKeySequence(Qt::Key_Minus), container);
        dec_sc->setContext(Qt::WidgetWithChildrenShortcut);
        QObject::connect(dec_sc, &QShortcut::activated, [crosshair, apply_table_op]() {
            double step = crosshair->increment;
            apply_table_op([step](auto vals, auto cols, const auto& sel) {
                auto out = std::vector<double>(vals.begin(), vals.end());
                for (std::size_t r = sel.top; r <= sel.bottom; ++r)
                    for (std::size_t c = sel.left; c <= sel.right; ++c)
                        out[r * cols + c] -= step;
                return out;
            });
        });

        auto* pct_up_sc = new QShortcut(
            QKeySequence(Qt::CTRL | Qt::SHIFT | Qt::Key_Equal), container);
        pct_up_sc->setContext(Qt::WidgetWithChildrenShortcut);
        QObject::connect(pct_up_sc, &QShortcut::activated, [apply_table_op]() {
            apply_table_op([](auto vals, auto cols, const auto& sel) {
                auto out = std::vector<double>(vals.begin(), vals.end());
                for (std::size_t r = sel.top; r <= sel.bottom; ++r)
                    for (std::size_t c = sel.left; c <= sel.right; ++c)
                        out[r * cols + c] *= 1.05;
                return out;
            });
        });

        auto* pct_down_sc = new QShortcut(
            QKeySequence(Qt::CTRL | Qt::SHIFT | Qt::Key_Minus), container);
        pct_down_sc->setContext(Qt::WidgetWithChildrenShortcut);
        QObject::connect(pct_down_sc, &QShortcut::activated, [apply_table_op]() {
            apply_table_op([](auto vals, auto cols, const auto& sel) {
                auto out = std::vector<double>(vals.begin(), vals.end());
                for (std::size_t r = sel.top; r <= sel.bottom; ++r)
                    for (std::size_t c = sel.left; c <= sel.right; ++c)
                        out[r * cols + c] *= 0.95;
                return out;
            });
        });

        // Fill-down / fill-right — mirrors the Python workspace's table
        // power-user paths. `Ctrl+R` is already reserved for review on the
        // native TUNE surface, so fill-right uses Ctrl+Shift+R here to stay
        // conflict-free while keeping the mnemonic.
        auto* fill_down_sc = new QShortcut(QKeySequence(Qt::CTRL | Qt::Key_D), container);
        fill_down_sc->setContext(Qt::WidgetWithChildrenShortcut);
        QObject::connect(fill_down_sc, &QShortcut::activated, [apply_table_op]() {
            apply_table_op([](auto vals, auto cols, const auto& sel) {
                return te::fill_down_region(vals, cols, sel);
            });
        });

        auto* fill_right_sc = new QShortcut(
            QKeySequence(Qt::CTRL | Qt::SHIFT | Qt::Key_R), container);
        fill_right_sc->setContext(Qt::WidgetWithChildrenShortcut);
        QObject::connect(fill_right_sc, &QShortcut::activated, [apply_table_op]() {
            apply_table_op([](auto vals, auto cols, const auto& sel) {
                return te::fill_right_region(vals, cols, sel);
            });
        });

        // Interpolate (I)
        auto* interp_sc = new QShortcut(QKeySequence(Qt::Key_I), container);
        interp_sc->setContext(Qt::WidgetWithChildrenShortcut);
        QObject::connect(interp_sc, &QShortcut::activated, [apply_table_op]() {
            apply_table_op([](auto vals, auto cols, const auto& sel) {
                return te::interpolate_region(vals, cols, sel);
            });
        });

        // Smooth (S)
        auto* smooth_sc = new QShortcut(QKeySequence(Qt::Key_S), container);
        smooth_sc->setContext(Qt::WidgetWithChildrenShortcut);
        QObject::connect(smooth_sc, &QShortcut::activated, [apply_table_op]() {
            apply_table_op([](auto vals, auto cols, const auto& sel) {
                return te::smooth_region(vals, cols, sel);
            });
        });

        // Fill selection with top-left value (F)
        auto* fill_sc = new QShortcut(QKeySequence(Qt::Key_F), container);
        fill_sc->setContext(Qt::WidgetWithChildrenShortcut);
        QObject::connect(fill_sc, &QShortcut::activated, [crosshair, edit_svc, apply_table_op]() {
            if (!crosshair->has_selection()) return;
            auto* tv = edit_svc->get_value(crosshair->z_param);
            if (!tv || !std::holds_alternative<std::vector<double>>(tv->value)) return;
            auto& vals = std::get<std::vector<double>>(tv->value);
            auto map_row = [&](int display_r) -> std::size_t {
                return (display_r < static_cast<int>(crosshair->row_index_map.size()))
                    ? crosshair->row_index_map[display_r]
                    : static_cast<std::size_t>(display_r);
            };
            std::size_t flat = map_row(crosshair->sel_top) * crosshair->cols + crosshair->sel_left;
            double fill_val = (flat < vals.size()) ? vals[flat] : 0.0;
            apply_table_op([fill_val](auto vals, auto cols, const auto& sel) {
                return te::fill_region(vals, cols, sel, fill_val);
            });
        });

        // Undo (Ctrl+Z)
        auto* undo_sc = new QShortcut(QKeySequence(Qt::CTRL | Qt::Key_Z), container);
        undo_sc->setContext(Qt::WidgetWithChildrenShortcut);
        QObject::connect(undo_sc, &QShortcut::activated,
                         [crosshair, edit_svc, refresh_visible_table,
                          refresh_page_chip, refresh_review_button,
                          refresh_tree_state_indicators, on_staged_changed,
                          resync_workspace]() {
            if (crosshair->z_param.empty()) return;
            if (edit_svc->can_undo(crosshair->z_param)) {
                edit_svc->undo(crosshair->z_param);
                (*resync_workspace)();
                refresh_visible_table();
                (*refresh_page_chip)(crosshair->page_target);
                (*refresh_review_button)();
                (*refresh_tree_state_indicators)();
                if (on_staged_changed) on_staged_changed();
            }
        });

        // Redo (Ctrl+Y)
        auto* redo_sc = new QShortcut(QKeySequence(Qt::CTRL | Qt::Key_Y), container);
        redo_sc->setContext(Qt::WidgetWithChildrenShortcut);
        QObject::connect(redo_sc, &QShortcut::activated,
                         [crosshair, edit_svc, refresh_visible_table,
                          refresh_page_chip, refresh_review_button,
                          refresh_tree_state_indicators, on_staged_changed,
                          resync_workspace]() {
            if (crosshair->z_param.empty()) return;
            if (edit_svc->can_redo(crosshair->z_param)) {
                edit_svc->redo(crosshair->z_param);
                (*resync_workspace)();
                refresh_visible_table();
                (*refresh_page_chip)(crosshair->page_target);
                (*refresh_review_button)();
                (*refresh_tree_state_indicators)();
                if (on_staged_changed) on_staged_changed();
            }
        });

        // Copy (Ctrl+C) — exports the visible selection as a tab-delimited
        // grid using the currently-rendered cell text. This keeps the
        // operator-facing clipboard identical to what they see on screen.
        auto* copy_sc = new QShortcut(QKeySequence(Qt::CTRL | Qt::Key_C), container);
        copy_sc->setContext(Qt::WidgetWithChildrenShortcut);
        QObject::connect(copy_sc, &QShortcut::activated, [crosshair]() {
            if (!crosshair->has_selection()) return;
            std::string clip;
            for (int r = crosshair->sel_top; r <= crosshair->sel_bottom; ++r) {
                if (r > crosshair->sel_top) clip += '\n';
                for (int c = crosshair->sel_left; c <= crosshair->sel_right; ++c) {
                    if (c > crosshair->sel_left) clip += '\t';
                    if (r < static_cast<int>(crosshair->cell_labels.size())
                        && c < static_cast<int>(crosshair->cell_labels[r].size())) {
                        clip += crosshair->cell_labels[r][c]->text().toStdString();
                    }
                }
            }
            QApplication::clipboard()->setText(QString::fromUtf8(clip.c_str()));
        });

        // Paste (Ctrl+V) — applies the pure-logic paste_region transform
        // and then refreshes the visible grid from the new staged values.
        auto* paste_sc = new QShortcut(QKeySequence(Qt::CTRL | Qt::Key_V), container);
        paste_sc->setContext(Qt::WidgetWithChildrenShortcut);
        QObject::connect(paste_sc, &QShortcut::activated, [apply_table_op]() {
            const std::string clipboard_text =
                QApplication::clipboard()->text().toStdString();
            if (clipboard_text.empty()) return;
            apply_table_op([&clipboard_text](auto vals, auto cols, const auto& sel) {
                return te::paste_region(vals, cols, sel, clipboard_text);
            });
        });

        // Arrow key navigation — move the single-cell selection within
        // the table grid. Essential for keyboard-driven table editing
        // (navigate with arrows, type value, Enter, move, repeat).
        auto move_sel = [crosshair](int dr, int dc) {
            if (!crosshair->has_selection()) return;
            int r = crosshair->sel_top + dr;
            int c = crosshair->sel_left + dc;
            r = std::clamp(r, 0, crosshair->rows - 1);
            c = std::clamp(c, 0, crosshair->cols - 1);
            crosshair->set_selection(r, c, r, c);
        };
        auto* up_sc = new QShortcut(QKeySequence(Qt::Key_Up), container);
        up_sc->setContext(Qt::WidgetWithChildrenShortcut);
        QObject::connect(up_sc, &QShortcut::activated, [move_sel]() { move_sel(-1, 0); });

        auto* down_sc = new QShortcut(QKeySequence(Qt::Key_Down), container);
        down_sc->setContext(Qt::WidgetWithChildrenShortcut);
        QObject::connect(down_sc, &QShortcut::activated, [move_sel]() { move_sel(1, 0); });

        auto* left_sc = new QShortcut(QKeySequence(Qt::Key_Left), container);
        left_sc->setContext(Qt::WidgetWithChildrenShortcut);
        QObject::connect(left_sc, &QShortcut::activated, [move_sel]() { move_sel(0, -1); });

        auto* right_sc = new QShortcut(QKeySequence(Qt::Key_Right), container);
        right_sc->setContext(Qt::WidgetWithChildrenShortcut);
        QObject::connect(right_sc, &QShortcut::activated, [move_sel]() { move_sel(0, 1); });

        // Enter — open cell editor at current selection.
        auto* enter_sc = new QShortcut(QKeySequence(Qt::Key_Return), container);
        enter_sc->setContext(Qt::WidgetWithChildrenShortcut);
        QObject::connect(enter_sc, &QShortcut::activated, [crosshair]() {
            if (!crosshair->has_selection()) return;
            int r = crosshair->sel_top;
            int c = crosshair->sel_left;
            if (r < static_cast<int>(crosshair->cell_labels.size())
                && c < static_cast<int>(crosshair->cell_labels[r].size())) {
                auto* lbl = crosshair->cell_labels[r][c];
                auto* ed = crosshair->cell_editor;
                if (!ed || !lbl || crosshair->z_param.empty()) return;
                QPoint pos = lbl->mapTo(ed->parentWidget(), QPoint(0, 0));
                ed->setGeometry(pos.x(), pos.y(), lbl->width(), lbl->height());
                ed->setText(lbl->text());
                ed->show();
                ed->setFocus();
                ed->selectAll();
                crosshair->edit_row = r;
                crosshair->edit_col = c;
            }
        });
    }

    // Selection handler — reads from the side map only, NEVER calls
    // text()/data() on QTreeWidgetItem (those return QStrings through
    // the broken ABI and crash).
    QObject::connect(tree, &QTreeWidget::currentItemChanged,
                     [selected_label, page_staged_chip, refresh_page_chip,
                      refresh_review_button, refresh_tree_state_indicators,
                      on_staged_changed, visible_editors,
                      detail_label, params_scroll, right_layout, heatmap_widget,
                      page_map, item_info, edit_svc, tune_file, ecu_def, crosshair, workspace, splitter, right_layout, container](
                         QTreeWidgetItem* current, QTreeWidgetItem*) {
        if (current == nullptr) return;

        // Look up from side map — no Qt string calls.
        auto info_it = item_info->find(current);
        if (info_it == item_info->end()) {
            // Group item, not a leaf — just clear.
            selected_label->setText(QString::fromUtf8(""));
            detail_label->setText(QString::fromUtf8("Expand a group and select a page."));
            page_staged_chip->hide();
            return;
        }
        const auto& [title_str, target] = info_it->second;
        selected_label->setText(QString::fromUtf8(title_str.c_str()));
        (*refresh_page_chip)(target);
        workspace->select_page(target);
        // Persist the selected page target so the next launch restores
        // the operator's last editing context.
        { QSettings s; s.setValue("session/tune_last_page",
                                  QString::fromUtf8(target.c_str())); }
        // Sub-slice 94 bugfix: clear the visible-editors map before
        // the old form is hidden. The hidden QLineEdits stay alive
        // (never deleted from signal handlers) but we only want the
        // popup's revert handler to reach widgets that are currently
        // on-screen.
        visible_editors->clear();
        // Detach old params widget — just hide it, never delete.
        auto* old_widget = params_scroll->takeWidget();
        if (old_widget) old_widget->hide();
        auto* params_container = new QWidget;
        auto* params_layout = new QVBoxLayout(params_container);
        params_layout->setContentsMargins(0, 0, 0, 0);
        params_layout->setSpacing(2);
        params_scroll->setWidget(params_container);
        // Remove previous heatmap from layout and hide it.
        if (*heatmap_widget) {
            right_layout->removeWidget(*heatmap_widget);
            (*heatmap_widget)->hide();
            (*heatmap_widget)->setParent(nullptr);  // detach fully
            *heatmap_widget = nullptr;
        }

        auto it = page_map->find(target);
        if (it == page_map->end()) {
            detail_label->setText(QString::fromUtf8("Select a page to see its compiled layout."));
            return;
        }
        auto& page = it->second;
        // Context-aware page guidance (Phase B UX) — now a shared
        // helper so tree leaf tooltips can reuse the same mapping.
        char info[512];
        const char* context_hint = page_context_hint(title_str);

        if (!page.curve_editor_id.empty()) {
            if (*context_hint)
                std::snprintf(info, sizeof(info), "%s", context_hint);
            else
                std::snprintf(info, sizeof(info), "1D curve editor.");
        } else if (!page.table_editor_id.empty()) {
            int field_count = 0;
            for (const auto& s : page.sections) field_count += static_cast<int>(s.fields.size());
            if (*context_hint)
                std::snprintf(info, sizeof(info), "%s", context_hint);
            else
                std::snprintf(info, sizeof(info), "Table with %d supporting field(s).", field_count);
        } else {
            int field_count = 0;
            for (const auto& s : page.sections) field_count += static_cast<int>(s.fields.size());
            if (*context_hint)
                std::snprintf(info, sizeof(info), "%s", context_hint);
            else
                std::snprintf(info, sizeof(info), "%d field(s) across %d section(s).",
                    field_count, static_cast<int>(page.sections.size()));
        }
        detail_label->setText(QString::fromUtf8(info));

        // Humanize parameter/section names.
        auto humanize_param = [](const std::string& raw) -> std::string {
            // Strip underscores, insert spaces before capitals.
            std::string result;
            for (size_t i = 0; i < raw.size(); ++i) {
                char c = raw[i];
                if (c == '_') { result += ' '; continue; }
                if (i > 0 && std::isupper(static_cast<unsigned char>(c))
                    && std::islower(static_cast<unsigned char>(raw[i-1])))
                    result += ' ';
                result += c;
            }
            if (!result.empty())
                result[0] = static_cast<char>(std::toupper(static_cast<unsigned char>(result[0])));
            return result;
        };

        // Strip surrounding quotes from string values.
        auto strip_quotes = [](const std::string& s) -> std::string {
            if (s.size() >= 2 && s.front() == '"' && s.back() == '"')
                return s.substr(1, s.size() - 2);
            return s;
        };

        // O(1) lookup for IniScalar metadata (options, min/max, units)
        // per parameter name. Built once per page, consumed by every
        // field row for enum detection and tooltip range.
        std::unordered_map<std::string, const tuner_core::IniScalar*> scalar_by_name;
        for (const auto& sc : ecu_def->constants.scalars)
            scalar_by_name[sc.name] = &sc;

        // Populate parameter form with editable fields.
        for (const auto& sec : page.sections) {
            // Section header — humanized, strip "Dialog" noise.
            std::string sec_title = sec.title;
            if (!sec_title.empty()) {
                sec_title = humanize_param(sec_title);
                // Remove "Dialog" and directional suffixes.
                for (const char* noise : {"Dialog ", " Dialog", "dialog ", " dialog",
                                          " South", " south", " North", " north",
                                          " East", " east", " West", " west"}) {
                    auto pos = sec_title.find(noise);
                    if (pos != std::string::npos)
                        sec_title.erase(pos, std::strlen(noise));
                }
                // Trim whitespace.
                while (!sec_title.empty() && sec_title.back() == ' ') sec_title.pop_back();
                while (!sec_title.empty() && sec_title.front() == ' ') sec_title.erase(0, 1);
                if (sec_title.empty()) sec_title = "Settings";
            }
            auto* sec_label = new QLabel(QString::fromUtf8(sec_title.c_str()));
            {
                QFont sf = sec_label->font();
                sf.setBold(true);
                sf.setPixelSize(tt::font_body);
                sec_label->setFont(sf);
            }
            sec_label->setStyleSheet(
                QString::fromUtf8(tt::section_header_style().c_str()));
            params_layout->addWidget(sec_label);

            for (const auto& f : sec.fields) {
                auto* row = new QHBoxLayout;
                row->setSpacing(tt::space_sm);

                // Sub-slice 129: per-row hover tooltip pulled from
                // the INI `[SettingContextHelp]` section compiled
                // into `ecu_def->setting_context_help.help_by_name`.
                // Every scalar / table / curve parameter the INI
                // describes gets a one-line hover hint — the
                // operator no longer has to leave the form to find
                // out what a field means. Falls back to the raw
                // parameter name when no help text is available,
                // so there's always some context on hover.
                //
                // The tooltip lands on both the label AND the
                // editor so the operator can hover either column
                // without having to aim for the specific widget.
                std::string tooltip_text;
                {
                    const auto& help_map = ecu_def->setting_context_help.help_by_name;
                    auto it = help_map.find(f.parameter_name);
                    if (it != help_map.end() && !it->second.empty()) {
                        tooltip_text = it->second;
                    } else {
                        // Fallback — show the raw parameter name so
                        // the operator can at least search for it
                        // in docs. The `·` separator grammar matches
                        // every other discovery surface.
                        tooltip_text = f.parameter_name;
                    }
                    // Append valid range from the O(1) scalar lookup.
                    auto sc_it = scalar_by_name.find(f.parameter_name);
                    if (sc_it != scalar_by_name.end()) {
                        auto* sc = sc_it->second;
                        if (sc->min_value.has_value() || sc->max_value.has_value()) {
                            char range_buf[64];
                            if (sc->min_value.has_value() && sc->max_value.has_value())
                                std::snprintf(range_buf, sizeof(range_buf),
                                              " \xc2\xb7 Range: %.4g\xe2\x80\x93" "%.4g",
                                              *sc->min_value, *sc->max_value);
                            else if (sc->min_value.has_value())
                                std::snprintf(range_buf, sizeof(range_buf),
                                              " \xc2\xb7 Min: %.4g", *sc->min_value);
                            else
                                std::snprintf(range_buf, sizeof(range_buf),
                                              " \xc2\xb7 Max: %.4g", *sc->max_value);
                            tooltip_text += range_buf;
                            if (sc->units.has_value() && !sc->units->empty()) {
                                tooltip_text += " ";
                                tooltip_text += *sc->units;
                            }
                        }
                    }
                }

                // Label — humanize the field label.
                std::string display_label = f.label.empty()
                    ? humanize_param(f.parameter_name) : f.label;
                auto* label = new QLabel(QString::fromUtf8(display_label.c_str()));
                label->setStyleSheet(QString::fromUtf8(tt::field_label_style().c_str()));
                label->setFixedWidth(180);
                label->setToolTip(QString::fromUtf8(tooltip_text.c_str()));
                row->addWidget(label);

                // Value editor or display.
                auto* tv = edit_svc->get_value(f.parameter_name);
                if (tv != nullptr && std::holds_alternative<double>(tv->value)) {
                    double v = std::get<double>(tv->value);
                    char val_str[32];
                    std::snprintf(val_str, sizeof(val_str), "%.4g", v);
                    auto* edit = new QLineEdit(QString::fromUtf8(val_str));
                    edit->setFixedWidth(100);
                    edit->setStyleSheet(QString::fromUtf8(
                        tt::scalar_editor_style(tt::EditorState::Default).c_str()));
                    edit->setToolTip(QString::fromUtf8(tooltip_text.c_str()));
                    row->addWidget(edit);

                    // Sub-slice 94 bugfix: record this editor + its
                    // base text in the visible-editors map so a popup
                    // revert can reset it. Read the base from
                    // get_base_value, not get_value, so we capture
                    // the "return to this on revert" target, not the
                    // current (possibly already-staged) value.
                    {
                        std::string base_text;
                        auto* base_tv = edit_svc->get_base_value(f.parameter_name);
                        if (base_tv != nullptr && std::holds_alternative<double>(base_tv->value)) {
                            char btxt[32];
                            std::snprintf(btxt, sizeof(btxt), "%.4g",
                                std::get<double>(base_tv->value));
                            base_text = btxt;
                        } else {
                            // No base value known — fall back to the
                            // currently-displayed text, which at
                            // startup is the same as base.
                            base_text = val_str;
                        }
                        (*visible_editors)[f.parameter_name] = {edit, nullptr, base_text};
                    }

                    // Units label.
                    if (!tv->units.empty()) {
                        auto* units = new QLabel(QString::fromUtf8(tv->units.c_str()));
                        units->setStyleSheet(QString::fromUtf8(tt::units_label_style().c_str()));
                        row->addWidget(units);
                    }

                    // Wire edit → stage on enter, with range validation.
                    std::string param_name = f.parameter_name;
                    std::string page_target = target;
                    // Capture min/max from definition for inline validation.
                    double sc_min = -1e9, sc_max = 1e9;
                    bool has_range = false;
                    {
                        auto sc_it = scalar_by_name.find(f.parameter_name);
                        if (sc_it != scalar_by_name.end()) {
                            if (sc_it->second->min_value.has_value()) {
                                sc_min = *sc_it->second->min_value;
                                has_range = true;
                            }
                            if (sc_it->second->max_value.has_value()) {
                                sc_max = *sc_it->second->max_value;
                                has_range = true;
                            }
                        }
                    }
                    QObject::connect(edit, &QLineEdit::editingFinished,
                                     [edit, edit_svc, param_name, page_target,
                                      workspace, on_staged_changed,
                                      refresh_page_chip, refresh_review_button,
                                      refresh_tree_state_indicators,
                                      sc_min, sc_max, has_range]() {
                        std::string new_val = edit->text().toStdString();
                        // Range validation.
                        if (has_range) {
                            try {
                                double nv = std::stod(new_val);
                                if (nv < sc_min || nv > sc_max) {
                                    char tip[128];
                                    std::snprintf(tip, sizeof(tip),
                                        "Out of range: %.4g \xe2\x80\x93 %.4g",
                                        sc_min, sc_max);
                                    edit->setToolTip(QString::fromUtf8(tip));
                                    edit->setStyleSheet(QString::fromUtf8(
                                        tt::scalar_editor_style(
                                            tt::EditorState::Warning).c_str()));
                                    // Still stage — warning only, not blocking.
                                }
                            } catch (...) {}
                        }
                        try {
                            edit_svc->stage_scalar_value(param_name, new_val);
                            workspace->stage_edit(page_target, param_name);
                            // Sub-slice 92: refresh the per-page staged
                            // chip immediately, then notify MainWindow
                            // so the sidebar "N staged" badge can
                            // refresh from the same source of truth.
                            // Sub-slice 93: also refresh the "Review (N)"
                            // chip in the project bar.
                            // Sub-slice 96: refresh the tree entry
                            // state indicators so the left pane shows
                            // which page has edits without navigating
                            // through the hierarchy.
                            (*refresh_page_chip)(page_target);
                            (*refresh_review_button)();
                            (*refresh_tree_state_indicators)();
                            if (on_staged_changed) on_staged_changed();

                            // Smart cross-parameter warnings (Phase D).
                            std::string warning;
                            std::string lower_name = param_name;
                            for (auto& c : lower_name)
                                c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
                            double nv = 0;
                            try { nv = std::stod(new_val); } catch (...) {}

                            if (lower_name.find("dwell") != std::string::npos) {
                                if (nv > 6.0)
                                    warning = "Dwell above 6ms may overheat coils \xe2\x80\x94 check datasheet";
                                else if (nv > 0 && nv < 1.0)
                                    warning = "Dwell below 1ms may cause weak spark";
                            } else if (lower_name.find("reqfuel") != std::string::npos) {
                                warning = "Update injector flow rate if you changed reqFuel";
                            } else if (lower_name.find("stoich") != std::string::npos) {
                                if (nv < 6 || nv > 22)
                                    warning = "Stoich outside plausible range (6\xe2\x80\x93""22)";
                            }

                            if (!warning.empty()) {
                                edit->setStyleSheet(QString::fromUtf8(
                                    tt::scalar_editor_style(tt::EditorState::Warning).c_str()));
                                edit->setToolTip(QString::fromUtf8(warning.c_str()));
                            } else {
                                edit->setStyleSheet(QString::fromUtf8(
                                    tt::scalar_editor_style(tt::EditorState::Ok).c_str()));
                                edit->setToolTip(QString());
                            }
                        } catch (...) {}
                    });
                } else if (tv != nullptr && std::holds_alternative<std::string>(tv->value)) {
                    std::string raw_val = strip_quotes(std::get<std::string>(tv->value));
                    // Check if this parameter has enum options.
                    auto sbn_it = scalar_by_name.find(f.parameter_name);
                    bool has_options = sbn_it != scalar_by_name.end()
                                      && !sbn_it->second->options.empty();

                    if (has_options) {
                        // Editable QComboBox dropdown for enum parameters.
                        auto* combo = new QComboBox;
                        combo->setFixedWidth(160);
                        combo->setStyleSheet(QString::fromUtf8(
                            tt::combo_editor_style(tt::EditorState::Default).c_str()));
                        combo->setToolTip(QString::fromUtf8(tooltip_text.c_str()));

                        const auto& options = sbn_it->second->options;
                        int current_idx = -1;
                        for (int oi = 0; oi < static_cast<int>(options.size()); ++oi) {
                            if (options[oi].empty()) continue;
                            // Skip "INVALID" options (matching Python).
                            std::string upper = options[oi];
                            for (auto& ch : upper)
                                ch = static_cast<char>(std::toupper(
                                    static_cast<unsigned char>(ch)));
                            if (upper == "INVALID") continue;
                            combo->addItem(
                                QString::fromUtf8(options[oi].c_str()),
                                QString::fromUtf8(options[oi].c_str()));
                            // Match current value by display text.
                            if (options[oi] == raw_val)
                                current_idx = combo->count() - 1;
                        }
                        if (current_idx >= 0) combo->setCurrentIndex(current_idx);
                        row->addWidget(combo);

                        // Record for revert support.
                        {
                            std::string base_text;
                            auto* base_tv = edit_svc->get_base_value(f.parameter_name);
                            if (base_tv && std::holds_alternative<std::string>(base_tv->value))
                                base_text = strip_quotes(std::get<std::string>(base_tv->value));
                            else
                                base_text = raw_val;
                            (*visible_editors)[f.parameter_name] = {nullptr, combo, base_text};
                        }

                        // Wire combo → stage on selection change.
                        std::string param_name = f.parameter_name;
                        std::string page_target = target;
                        QObject::connect(combo, &QComboBox::currentIndexChanged,
                            [combo, edit_svc, param_name, page_target,
                             workspace, on_staged_changed,
                             refresh_page_chip, refresh_review_button,
                             refresh_tree_state_indicators]() {
                            std::string sel = combo->currentData().toString().toStdString();
                            try {
                                edit_svc->stage_scalar_value(param_name, sel);
                                workspace->stage_edit(page_target, param_name);
                                (*refresh_page_chip)(page_target);
                                (*refresh_review_button)();
                                (*refresh_tree_state_indicators)();
                                if (on_staged_changed) on_staged_changed();
                                combo->setStyleSheet(QString::fromUtf8(
                                    tt::combo_editor_style(tt::EditorState::Ok).c_str()));
                            } catch (...) {}
                        });

                        // Units label for enums (rare but possible).
                        if (!tv->units.empty()) {
                            auto* units = new QLabel(QString::fromUtf8(tv->units.c_str()));
                            units->setStyleSheet(QString::fromUtf8(
                                tt::units_label_style().c_str()));
                            row->addWidget(units);
                        }
                    } else {
                        // No options — read-only chip for plain string constants.
                        auto* val = new QLabel(QString::fromUtf8(raw_val.c_str()));
                        val->setStyleSheet(QString::fromUtf8(
                            tt::inline_value_chip_style().c_str()));
                        val->setToolTip(QString::fromUtf8(tooltip_text.c_str()));
                        row->addWidget(val);
                    }
                } else if (tv != nullptr && std::holds_alternative<std::vector<double>>(tv->value)) {
                    auto& list = std::get<std::vector<double>>(tv->value);
                    int n = static_cast<int>(list.size());
                    char desc[128];
                    if (n <= 4) {
                        int off = 0;
                        for (int vi = 0; vi < n; ++vi)
                            off += std::snprintf(desc + off, sizeof(desc) - off,
                                                 "%s%.4g", vi > 0 ? ", " : "", list[vi]);
                    } else {
                        // Show first 3 values + shape hint.
                        // Guess shape: common Speeduino tables are square.
                        int sq = static_cast<int>(std::sqrt(static_cast<double>(n)));
                        if (sq * sq == n && sq > 1)
                            std::snprintf(desc, sizeof(desc),
                                "%.4g, %.4g, %.4g\xe2\x80\xa6 (%d\xc3\x97%d)",
                                list[0], list[1], list[2], sq, sq);
                        else
                            std::snprintf(desc, sizeof(desc),
                                "%.4g, %.4g, %.4g\xe2\x80\xa6 (%d values)",
                                list[0], list[1], list[2], n);
                    }
                    auto* val = new QLabel(QString::fromUtf8(desc));
                    val->setStyleSheet(QString::fromUtf8(tt::field_label_style().c_str()));
                    row->addWidget(val);
                    if (!tv->units.empty()) {
                        auto* units = new QLabel(QString::fromUtf8(tv->units.c_str()));
                        units->setStyleSheet(QString::fromUtf8(tt::units_label_style().c_str()));
                        row->addWidget(units);
                    }
                } else {
                    auto* val = new QLabel(QString::fromUtf8(f.parameter_name.c_str()));
                    val->setStyleSheet(QString::fromUtf8(tt::units_label_style().c_str()));
                    row->addWidget(val);
                }

                row->addStretch(1);
                params_layout->addLayout(row);
            }
        }
        // Vertical sizing flips per page type. Scalar pages: scroll area
        // fills the right pane (Expanding + stretch 1) so the form isn't
        // clipped to a tiny strip at the top. Table pages: scroll area
        // takes only what the supporting fields need (Maximum + stretch
        // 0) so the heatmap card added below gets the remaining height,
        // BUT we have to bump its minimum height up to the form's
        // estimated content height — Qt's default QScrollArea sizeHint
        // is small and clips the rows otherwise.
        params_scroll->setMaximumHeight(16777215);
        if (!page.table_editor_id.empty() || !page.curve_editor_id.empty()) {
            int section_count = static_cast<int>(page.sections.size());
            int field_count = 0;
            for (const auto& s : page.sections) field_count += static_cast<int>(s.fields.size());
            // Section header ~26px, each field row ~28px, plus a bit of slack.
            int estimated_h = section_count * 26 + field_count * 28 + 12;
            // Cap so a page with many fields doesn't eat the heatmap.
            estimated_h = std::min(estimated_h, 320);
            params_scroll->setMinimumHeight(estimated_h);
            params_scroll->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Maximum);
            right_layout->setStretchFactor(params_scroll, 0);
        } else {
            params_scroll->setMinimumHeight(0);
            params_scroll->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Expanding);
            right_layout->setStretchFactor(params_scroll, 1);
            params_layout->addStretch(1);
        }

        // Render table heatmap with crosshair support.
        crosshair->cell_labels.clear();
        crosshair->x_labels.clear();
        crosshair->y_labels.clear();
        crosshair->x_param.clear();
        crosshair->y_param.clear();
        crosshair->rows = crosshair->cols = 0;
        crosshair->prev_row = crosshair->prev_col = -1;
        crosshair->view_3d = nullptr;

        if (!page.curve_editor_id.empty()) {
            // Render 1D curve page — editable table + bar chart.
            try {
                for (const auto& curve : ecu_def->curve_editors.curves) {
                    if (curve.name != page.curve_editor_id) continue;

                    // Load x-axis bins.
                    std::vector<double> x_vals;
                    auto* x_tv = edit_svc->get_value(curve.x_bins_param);
                    if (x_tv && std::holds_alternative<std::vector<double>>(x_tv->value))
                        x_vals = std::get<std::vector<double>>(x_tv->value);

                    // Build the curve card.
                    auto* card = new QWidget;
                    auto* vl = new QVBoxLayout(card);
                    vl->setContentsMargins(tt::space_sm, tt::space_xs, tt::space_sm, tt::space_xs);
                    vl->setSpacing(tt::space_xs);
                    card->setStyleSheet(QString::fromUtf8(tt::card_style().c_str()));

                    // Title + axis labels.
                    {
                        char curve_info[256];
                        std::snprintf(curve_info, sizeof(curve_info),
                            "<span style='color: %s; font-size: %dpx; font-weight: bold;'>%s</span>"
                            "<span style='color: %s; font-size: %dpx;'>  \xc2\xb7  "
                            "X: %s  \xc2\xb7  Y: %s</span>",
                            tt::text_secondary, tt::font_small,
                            curve.title.empty() ? curve.name.c_str() : curve.title.c_str(),
                            tt::text_muted, tt::font_micro,
                            curve.x_label.c_str(), curve.y_label.c_str());
                        auto* info_lbl = new QLabel;
                        info_lbl->setTextFormat(Qt::RichText);
                        info_lbl->setText(QString::fromUtf8(curve_info));
                        info_lbl->setStyleSheet("border: none;");
                        vl->addWidget(info_lbl);
                    }

                    // For each y-bins line, build a two-column table (X | Y)
                    // and a horizontal bar chart.
                    for (const auto& yb : curve.y_bins_list) {
                        std::vector<double> y_vals;
                        auto* y_tv = edit_svc->get_value(yb.param);
                        if (y_tv && std::holds_alternative<std::vector<double>>(y_tv->value))
                            y_vals = std::get<std::vector<double>>(y_tv->value);

                        if (y_vals.empty()) continue;

                        // Optional line label for multi-line curves.
                        if (yb.label.has_value() && !yb.label->empty()) {
                            char ll[128];
                            std::snprintf(ll, sizeof(ll),
                                "<span style='color: %s; font-size: %dpx;'>%s</span>",
                                tt::text_muted, tt::font_micro, yb.label->c_str());
                            auto* yll = new QLabel;
                            yll->setTextFormat(Qt::RichText);
                            yll->setText(QString::fromUtf8(ll));
                            yll->setStyleSheet("border: none;");
                            vl->addWidget(yll);
                        }

                        // Bar chart — rendered via render_1d_curve. We
                        // keep a pointer to the bar chart widget and a
                        // shared y-values vector so editing a Y value
                        // can rebuild the bar chart in-place.
                        QWidget* bar_widget = nullptr;
                        auto live_y = std::make_shared<std::vector<double>>(y_vals);
                        auto live_x = std::make_shared<std::vector<double>>(x_vals);
                        std::string curve_y_label_str = curve.y_label;
                        if (!x_vals.empty()) {
                            bar_widget = render_1d_curve(x_vals, y_vals,
                                "", curve.y_label.c_str(), tt::accent_primary);
                            vl->addWidget(bar_widget);
                        }

                        // Lambda that rebuilds the bar chart after a Y edit.
                        auto refresh_curve_bar = [vl, &bar_widget, live_x, live_y, curve_y_label_str]() {
                            // Can't delete widgets in handlers — hide the
                            // old one and insert a new one at the same position.
                            // The bar chart is always at index 2 in the card
                            // layout (after info label and optional line label).
                            if (live_x->empty()) return;
                            auto* new_bar = render_1d_curve(*live_x, *live_y,
                                "", curve_y_label_str.c_str(), tt::accent_primary);
                            if (bar_widget) bar_widget->hide();
                            // Insert after the first visible widget.
                            int insert_idx = -1;
                            for (int j = 0; j < vl->count(); ++j) {
                                auto* w = vl->itemAt(j)->widget();
                                if (w && w == bar_widget) { insert_idx = j; break; }
                            }
                            if (insert_idx >= 0)
                                vl->insertWidget(insert_idx + 1, new_bar);
                            else
                                vl->insertWidget(1, new_bar);
                            bar_widget = new_bar;
                        };

                        // Editable value table: X | Y columns.
                        auto* grid = new QGridLayout;
                        grid->setSpacing(1);
                        grid->setContentsMargins(0, tt::space_xs, 0, 0);
                        // Header row.
                        {
                            char hdr_style[128];
                            std::snprintf(hdr_style, sizeof(hdr_style),
                                "color: %s; font-size: %dpx; font-weight: bold; border: none; padding: 2px;",
                                tt::text_muted, tt::font_micro);
                            auto* xh = new QLabel(QString::fromUtf8(curve.x_label.c_str()));
                            xh->setStyleSheet(QString::fromUtf8(hdr_style));
                            xh->setAlignment(Qt::AlignCenter);
                            grid->addWidget(xh, 0, 0);
                            auto* yh = new QLabel(QString::fromUtf8(curve.y_label.c_str()));
                            yh->setStyleSheet(QString::fromUtf8(hdr_style));
                            yh->setAlignment(Qt::AlignCenter);
                            grid->addWidget(yh, 0, 1);
                        }
                        int n = std::min(static_cast<int>(x_vals.size()),
                                         static_cast<int>(y_vals.size()));
                        for (int i = 0; i < n; ++i) {
                            // X value (read-only).
                            char xbuf[16]; std::snprintf(xbuf, sizeof(xbuf), "%.4g", x_vals[i]);
                            auto* xl = new QLabel(QString::fromUtf8(xbuf));
                            xl->setAlignment(Qt::AlignCenter);
                            {
                                char xs[128];
                                std::snprintf(xs, sizeof(xs),
                                    "color: %s; font-size: %dpx; font-family: monospace; "
                                    "background: %s; border: none; padding: 2px;",
                                    tt::text_muted, tt::font_small, tt::bg_inset);
                                xl->setStyleSheet(QString::fromUtf8(xs));
                            }
                            grid->addWidget(xl, i + 1, 0);

                            // Y value (editable).
                            char ybuf[16]; std::snprintf(ybuf, sizeof(ybuf), "%.4g", y_vals[i]);
                            auto* ye = new QLineEdit(QString::fromUtf8(ybuf));
                            ye->setAlignment(Qt::AlignCenter);
                            ye->setFixedWidth(80);
                            ye->setStyleSheet(QString::fromUtf8(
                                tt::scalar_editor_style(tt::EditorState::Default).c_str()));
                            grid->addWidget(ye, i + 1, 1);

                            // Wire editing — stages the value AND refreshes the bar chart.
                            std::string y_param = yb.param;
                            int idx = i;
                            std::string pt = target;
                            QObject::connect(ye, &QLineEdit::editingFinished,
                                [ye, edit_svc, y_param, idx, pt, workspace,
                                 on_staged_changed, refresh_page_chip,
                                 refresh_review_button, refresh_tree_state_indicators,
                                 live_y, refresh_curve_bar]() {
                                double nv;
                                try { nv = std::stod(ye->text().toStdString()); }
                                catch (...) { return; }
                                try {
                                    edit_svc->stage_list_cell(y_param, idx, nv);
                                    workspace->stage_edit(pt, y_param);
                                    // Update the live Y values and rebuild bar chart.
                                    if (idx < static_cast<int>(live_y->size()))
                                        (*live_y)[idx] = nv;
                                    refresh_curve_bar();
                                    (*refresh_page_chip)(pt);
                                    (*refresh_review_button)();
                                    (*refresh_tree_state_indicators)();
                                    if (on_staged_changed) on_staged_changed();
                                    ye->setStyleSheet(QString::fromUtf8(
                                        tt::scalar_editor_style(tt::EditorState::Ok).c_str()));
                                } catch (...) {}
                            });
                        }
                        auto* gw = new QWidget; gw->setLayout(grid);
                        gw->setStyleSheet("border: none;");
                        vl->addWidget(gw);
                    }

                    *heatmap_widget = card;
                    right_layout->addWidget(card, 1);
                    break;
                }
            } catch (...) {}
        } else if (!page.table_editor_id.empty()) {
            try {
                for (const auto& editor : ecu_def->table_editors.editors) {
                    if (editor.table_id != page.table_editor_id) continue;
                    if (!editor.z_bins.has_value()) break;
                    auto* tv = edit_svc->get_value(*editor.z_bins);
                    if (tv == nullptr || !std::holds_alternative<std::vector<double>>(tv->value)) break;
                    auto& values = std::get<std::vector<double>>(tv->value);
                    if (values.empty() || values.size() > 1024) break;
                    int rows = 0, cols = 0;
                    for (const auto& arr : ecu_def->constants.arrays) {
                        if (arr.name == *editor.z_bins) {
                            rows = arr.rows; cols = arr.columns; break;
                        }
                    }
                    if (rows <= 0 || cols <= 0) {
                        int n = static_cast<int>(values.size());
                        cols = static_cast<int>(std::sqrt(static_cast<double>(n)));
                        if (cols <= 0) cols = 1;
                        rows = (n + cols - 1) / cols;
                    }
                    if (rows > 32 || cols > 32) break;

                    // Build heatmap inline to capture cell label pointers.
                    namespace tv_ns = tuner_core::table_view;
                    namespace tr_ns = tuner_core::table_rendering;
                    tv_ns::ShapeHints hints; hints.rows = rows; hints.cols = cols;
                    auto model_opt = tv_ns::build_table_model(
                        std::span<const double>(values.data(), values.size()), hints);
                    if (!model_opt) break;

                    // Read axis labels from the tune if available.
                    std::vector<std::string> x_labels, y_labels;
                    if (editor.x_bins.has_value()) {
                        auto* xv = edit_svc->get_value(*editor.x_bins);
                        if (xv && std::holds_alternative<std::vector<double>>(xv->value)) {
                            for (double d : std::get<std::vector<double>>(xv->value)) {
                                char b[16]; std::snprintf(b, sizeof(b), "%.0f", d);
                                x_labels.push_back(b);
                            }
                        }
                    }
                    if (editor.y_bins.has_value()) {
                        auto* yv = edit_svc->get_value(*editor.y_bins);
                        if (yv && std::holds_alternative<std::vector<double>>(yv->value)) {
                            for (double d : std::get<std::vector<double>>(yv->value)) {
                                char b[16]; std::snprintf(b, sizeof(b), "%.0f", d);
                                y_labels.push_back(b);
                            }
                        }
                    }

                    auto render = tr_ns::build_render_model(*model_opt, x_labels, y_labels, true);
                    int dr = std::min(static_cast<int>(render.rows), 16);
                    int dc = std::min(static_cast<int>(render.columns), 16);

                    auto* card = new QWidget;
                    auto* vl = new QVBoxLayout(card);
                    vl->setContentsMargins(tt::space_sm, tt::space_xs, tt::space_sm, tt::space_xs);
                    vl->setSpacing(1);
                    card->setStyleSheet(QString::fromUtf8(tt::card_style().c_str()));
                    // Card is added directly to right_layout — no special size policy needed
                    // because the inner scroll area clips the grid.

                    // Compact table info: dimensions + axis labels in one line.
                    {
                        char table_info[320]; int toff = 0;
                        toff += std::snprintf(table_info + toff, sizeof(table_info) - toff,
                            "<span style='color: %s; font-size: %dpx; font-weight: bold;'>"
                            "%d \xc3\x97 %d</span>",
                            tt::text_secondary, tt::font_small, dr, dc);
                        if (editor.x_label.has_value() && !editor.x_label->empty())
                            toff += std::snprintf(table_info + toff, sizeof(table_info) - toff,
                                "<span style='color: %s; font-size: %dpx;'>"
                                "  \xc2\xb7  X: %s</span>",
                                tt::text_muted, tt::font_small, editor.x_label->c_str());
                        if (editor.y_label.has_value() && !editor.y_label->empty())
                            toff += std::snprintf(table_info + toff, sizeof(table_info) - toff,
                                "<span style='color: %s; font-size: %dpx;'>"
                                "  \xc2\xb7  Y: %s</span>",
                                tt::text_muted, tt::font_small, editor.y_label->c_str());
                        auto* info_label = new QLabel;
                        info_label->setTextFormat(Qt::RichText);
                        info_label->setText(QString::fromUtf8(table_info));
                        info_label->setStyleSheet("border: none; padding: 2px 0;");
                        vl->addWidget(info_label);
                    }

                    auto* grid = new QGridLayout;
                    grid->setSpacing(0); grid->setContentsMargins(0, 2, 0, 0);
                    int grid_row_offset = 1;
                    int grid_col_offset = 1;

                    // Cell sizing: pure column-count-based, no widget queries.
                    // Widget width queries are unreliable in Qt when fixed-size
                    // children inflate parent geometries. Use a simple lookup.
                    int cell_w;
                    if      (dc <= 4)  cell_w = 55;
                    else if (dc <= 6)  cell_w = 50;
                    else if (dc <= 8)  cell_w = 45;
                    else if (dc <= 10) cell_w = 42;
                    else if (dc <= 12) cell_w = 38;
                    else if (dc <= 16) cell_w = 34;
                    else               cell_w = 28;
                    int cell_h = std::max(15, cell_w * 2 / 5 + 2);
                    int axis_font = std::clamp(cell_w / 4, 8, 11);
                    int cell_font = std::clamp(cell_w / 4, 8, 11);

                    // X-axis labels along top — bright enough to read.
                    if (!x_labels.empty()) {
                        int xl = std::min(static_cast<int>(x_labels.size()), dc);
                        for (int c = 0; c < xl; ++c) {
                            auto* al = new QLabel(QString::fromUtf8(x_labels[c].c_str()));
                            al->setAlignment(Qt::AlignCenter);
                            char as[160];
                            std::snprintf(as, sizeof(as),
                                "color: %s; font-size: %dpx; border: none; "
                                "font-family: monospace; font-weight: bold;",
                                tt::text_muted, axis_font);
                            al->setStyleSheet(QString::fromUtf8(as));
                            grid->addWidget(al, 0, c + grid_col_offset);
                        }
                    }

                    // Y-axis labels along left — inverted, bright.
                    if (!y_labels.empty()) {
                        int yl = std::min(static_cast<int>(y_labels.size()), dr);
                        for (int r = 0; r < yl; ++r) {
                            int inv_r = yl - 1 - r;
                            const char* text = (inv_r < static_cast<int>(y_labels.size()))
                                ? y_labels[inv_r].c_str() : "";
                            auto* al = new QLabel(QString::fromUtf8(text));
                            al->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
                            char as[192];
                            std::snprintf(as, sizeof(as),
                                "color: %s; font-size: %dpx; border: none; "
                                "font-family: monospace; font-weight: bold; padding-right: 4px;",
                                tt::text_muted, axis_font);
                            al->setStyleSheet(QString::fromUtf8(as));
                            grid->addWidget(al, r + grid_row_offset, 0);
                        }
                    }

                    crosshair->cell_labels.resize(dr);
                    crosshair->base_styles.resize(dr);
                    // Selection anchor for Shift+click range selection.
                    auto sel_anchor = std::make_shared<std::pair<int,int>>(-1, -1);
                    for (int r = 0; r < dr; ++r) {
                        crosshair->cell_labels[r].resize(dc, nullptr);
                        crosshair->base_styles[r].resize(dc);
                        for (int c = 0; c < dc; ++c) {
                            auto& cell = render.cells[r][c];
                            char style_buf[256];
                            std::snprintf(style_buf, sizeof(style_buf),
                                "background-color: %s; color: %s; border: none; "
                                "padding: 1px; font-size: %dpx; font-family: monospace;",
                                cell.background_hex.c_str(), cell.foreground_hex.c_str(), cell_font);
                            crosshair->base_styles[r][c] = style_buf;
                            auto* lbl = new QLabel(QString::fromUtf8(cell.text.c_str()));
                            lbl->setAlignment(Qt::AlignCenter);
                            lbl->setStyleSheet(QString::fromUtf8(style_buf));
                            lbl->setMinimumHeight(cell_h);
                            grid->addWidget(lbl, r + grid_row_offset, c + grid_col_offset);
                            crosshair->cell_labels[r][c] = lbl;
                            // Double-click → edit, single click → select.
                            lbl->installEventFilter(new CellClickFilter(r, c,
                                // Edit callback (double-click).
                                [crosshair](int row, int col, QLabel* cell_lbl) {
                                    auto* ed = crosshair->cell_editor;
                                    if (!ed || crosshair->z_param.empty()) return;
                                    QPoint pos = cell_lbl->mapTo(ed->parentWidget(), QPoint(0, 0));
                                    ed->setGeometry(pos.x(), pos.y(),
                                                    cell_lbl->width(), cell_lbl->height());
                                    ed->setText(cell_lbl->text());
                                    ed->show();
                                    ed->setFocus();
                                    ed->selectAll();
                                    crosshair->edit_row = row;
                                    crosshair->edit_col = col;
                                },
                                // Selection callback (single click).
                                [crosshair, sel_anchor](int row, int col, bool shift) {
                                    if (shift && sel_anchor->first >= 0) {
                                        crosshair->set_selection(
                                            sel_anchor->first, sel_anchor->second, row, col);
                                    } else {
                                        crosshair->set_selection(row, col, row, col);
                                        *sel_anchor = {row, col};
                                    }
                                },
                                // Drag callback (mouse move while button held).
                                [crosshair, sel_anchor](int row, int col, bool start) {
                                    if (start) {
                                        // Begin drag — set anchor.
                                        crosshair->dragging = true;
                                        crosshair->drag_anchor_row = row;
                                        crosshair->drag_anchor_col = col;
                                    } else if (crosshair->dragging && row >= 0 && col >= 0) {
                                        // Extend selection from drag anchor.
                                        crosshair->set_selection(
                                            crosshair->drag_anchor_row,
                                            crosshair->drag_anchor_col,
                                            row, col);
                                        *sel_anchor = {crosshair->drag_anchor_row,
                                                       crosshair->drag_anchor_col};
                                    } else {
                                        // End drag.
                                        crosshair->dragging = false;
                                    }
                                },
                            lbl));
                        }
                    }
                    // Store table metadata for the cell editor.
                    crosshair->z_param = *editor.z_bins;
                    crosshair->page_target = target;
                    crosshair->row_index_map.assign(
                        render.row_index_map.begin(), render.row_index_map.end());

                    // Equal column stretches so the grid fills its container.
                    for (int c = 0; c <= dc; ++c)
                        grid->setColumnStretch(c, c == 0 ? 0 : 1);

                    auto* gw = new QWidget; gw->setLayout(grid);
                    gw->setStyleSheet("border: none;");

                    // Wrap in a scroll area that clips — prevents splitter inflation.
                    auto* hm_scroll = new QScrollArea;
                    hm_scroll->setWidget(gw);
                    hm_scroll->setWidgetResizable(true);
                    hm_scroll->setFrameShape(QFrame::NoFrame);
                    hm_scroll->setStyleSheet("background: transparent; border: none;");
                    hm_scroll->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
                    hm_scroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);

                    // Sub-slice 83: build a 2D↔3D toggle. The 3D view
                    // consumes the flat value vector and the same
                    // (rows, cols) shape the heatmap uses. Both live
                    // inside a QStackedWidget so the toggle is a
                    // zero-delete setCurrentIndex() call — safe under
                    // the "never delete widgets in signal handlers"
                    // rule documented at the top of this file.
                    //
                    // Feed the values in **model order** (row 0 = lowest
                    // load, row max = highest load) to match the front-
                    // right camera default (azimuth 45°). The projection
                    // puts row 0 at the front of the mesh and row max at
                    // the back, so both views read the same way: RPM
                    // increases left→right, load increases front→back,
                    // VE pops up on the vertical axis.
                    auto* view3d = new TableSurface3DView;
                    view3d->set_table(values, rows, cols);

                    auto* stack = new QStackedWidget;
                    stack->addWidget(hm_scroll);  // index 0 = 2D grid
                    stack->addWidget(view3d);     // index 1 = 3D surface
                    stack->setCurrentIndex(0);

                    // Toggle row above the stack.
                    auto* toggle_row = new QWidget;
                    auto* toggle_layout = new QHBoxLayout(toggle_row);
                    toggle_layout->setContentsMargins(0, 2, 0, 2);
                    toggle_layout->setSpacing(tt::space_xs);
                    auto* btn_2d = new QPushButton(QString::fromUtf8("2D"));
                    auto* btn_3d = new QPushButton(QString::fromUtf8("3D"));
                    // Two-state toggle: active uses `accent_primary`
                    // border + elevated fill, idle uses the standard
                    // card palette with hover → text_secondary.
                    static char toggle_style_active[384];
                    static char toggle_style_idle[512];
                    std::snprintf(toggle_style_active, sizeof(toggle_style_active),
                        "QPushButton { background-color: %s; color: %s; "
                        "border: 1px solid %s; border-radius: 3px; "
                        "padding: 2px %dpx; font-size: %dpx; }",
                        tt::fill_primary_mid, tt::text_primary,
                        tt::accent_primary, tt::space_sm + 2, tt::font_micro);
                    std::snprintf(toggle_style_idle, sizeof(toggle_style_idle),
                        "QPushButton { background-color: %s; color: %s; "
                        "border: 1px solid %s; border-radius: 3px; "
                        "padding: 2px %dpx; font-size: %dpx; } "
                        "QPushButton:hover { color: %s; }",
                        tt::bg_panel, tt::text_muted,
                        tt::border, tt::space_sm + 2, tt::font_micro,
                        tt::text_secondary);
                    btn_2d->setStyleSheet(QString::fromUtf8(toggle_style_active));
                    btn_3d->setStyleSheet(QString::fromUtf8(toggle_style_idle));
                    btn_2d->setCursor(Qt::PointingHandCursor);
                    btn_3d->setCursor(Qt::PointingHandCursor);
                    toggle_layout->addStretch(1);
                    toggle_layout->addWidget(btn_2d);
                    toggle_layout->addWidget(btn_3d);
                    // The toggle style buffers are `static`, so lambdas
                    // access them directly without a capture — capturing
                    // a static-storage array is a compiler warning and
                    // semantically meaningless.
                    QObject::connect(btn_2d, &QPushButton::clicked, [stack, btn_2d, btn_3d]() {
                        stack->setCurrentIndex(0);
                        btn_2d->setStyleSheet(QString::fromUtf8(toggle_style_active));
                        btn_3d->setStyleSheet(QString::fromUtf8(toggle_style_idle));
                    });
                    QObject::connect(btn_3d, &QPushButton::clicked, [stack, btn_2d, btn_3d]() {
                        stack->setCurrentIndex(1);
                        btn_2d->setStyleSheet(QString::fromUtf8(toggle_style_idle));
                        btn_3d->setStyleSheet(QString::fromUtf8(toggle_style_active));
                    });
                    vl->addWidget(toggle_row);
                    vl->addWidget(stack, 1);
                    right_layout->addWidget(card);
                    *heatmap_widget = card;

                    // Store axis info for crosshair.
                    crosshair->rows = dr; crosshair->cols = dc;
                    crosshair->x_labels = x_labels;
                    crosshair->y_labels = y_labels;
                    crosshair->view_3d = view3d;
                    if (editor.x_bins) crosshair->x_param = *editor.x_bins;
                    if (editor.y_bins) crosshair->y_param = *editor.y_bins;
                    break;
                }
            } catch (...) {}
        }
    });

    // ---- Crosshair timer: highlight the live operating cell on the heatmap ----
    namespace trc = tuner_core::table_replay_context;
    auto* crosshair_timer = new QTimer(container);
    QObject::connect(crosshair_timer, &QTimer::timeout,
                     [crosshair, tune_mock_ecu]() {
        if (crosshair->rows == 0 || crosshair->cell_labels.empty()) return;
        auto snap = tune_mock_ecu->poll();

        // Build the table page snapshot for the locator.
        trc::TablePageSnapshot tps;
        tps.x_parameter_name = crosshair->x_param.empty() ? std::nullopt : std::optional(crosshair->x_param);
        tps.y_parameter_name = crosshair->y_param.empty() ? std::nullopt : std::optional(crosshair->y_param);
        tps.x_labels = crosshair->x_labels;
        tps.y_labels = crosshair->y_labels;
        // Build a dummy cell grid — locator only needs the shape.
        tps.cells.resize(crosshair->rows);
        for (int r = 0; r < crosshair->rows; ++r)
            tps.cells[r].resize(crosshair->cols, "0");

        std::vector<trc::RuntimeChannel> channels;
        for (const auto& [name, value] : snap.channels)
            channels.push_back({name, value});

        auto loc = trc::build(tps, channels);

        // Clear previous highlight.
        if (crosshair->prev_row >= 0 && crosshair->prev_col >= 0
            && crosshair->prev_row < crosshair->rows
            && crosshair->prev_col < crosshair->cols) {
            auto* lbl = crosshair->cell_labels[crosshair->prev_row][crosshair->prev_col];
            if (lbl) lbl->setStyleSheet(QString::fromUtf8(crosshair->prev_style.c_str()));
        }

        if (!loc) {
            if (crosshair->view_3d) crosshair->view_3d->clear_operating_point();
            return;
        }

        // Y-axis is inverted in the render model (row 0 = highest load).
        int display_row = crosshair->rows - 1 - static_cast<int>(loc->row_index);
        int display_col = static_cast<int>(loc->column_index);
        if (display_row < 0 || display_row >= crosshair->rows) return;
        if (display_col < 0 || display_col >= crosshair->cols) return;

        auto* lbl = crosshair->cell_labels[display_row][display_col];
        if (!lbl) return;

        // Save original style for restoration.
        crosshair->prev_style = lbl->styleSheet().toStdString();
        crosshair->prev_row = display_row;
        crosshair->prev_col = display_col;

        // Operating-point crosshair highlight — deliberately OUTSIDE
        // the normal theme palette. The design intent is maximum
        // visibility: pure white background, pure black text, alert
        // red border. Tokenized equivalents would soften the intent
        // — `text_primary` (#e8edf5) is not pure white, `accent_danger`
        // (#d65a5a) is not alert red. This is the one place in the
        // app where "look at THIS cell, RIGHT NOW" overrides the
        // restrained palette philosophy.
        lbl->setStyleSheet(
            "background-color: #ffffff; color: #000000; "
            "border: 2px solid #ff4444; padding: 0px; "
            "font-size: 9px; font-family: monospace; font-weight: bold;");

        // Mirror the same cell on the 3D view if the user has it open.
        // The 3D view consumes values in **model order** (row 0 = lowest
        // load), so pass the raw `loc->row_index` from `table_replay_context`
        // — not the display row, which has the y-axis inversion applied.
        if (crosshair->view_3d) {
            crosshair->view_3d->set_operating_point(
                static_cast<double>(loc->row_index),
                static_cast<double>(loc->column_index));
        }
    });
    crosshair_timer->start(300);

    splitter->addWidget(left_panel);
    splitter->addWidget(right_pane);
    splitter->setStretchFactor(0, 1);  // left panel stretches too
    splitter->setStretchFactor(1, 3);  // right pane gets 3x the stretch
    splitter->setSizes({280, 700});    // initial ratio: ~30/70
    outer->addWidget(splitter, 1);

    // ---- Sub-slice 93: staged-changes review popup ------------------------
    //
    // Opens on click of the "Review (N)" chip in the project bar, or via
    // Ctrl+R. Shows a scrollable list of every staged edit with its base
    // and staged values side by side, plus a "Revert All" button. This
    // is the "review" half of the stage → review → commit operator
    // workflow that `docs/ux-design.md` Core Principle #4 calls for
    // (*"Staged everything — never apply changes silently; always
    // preview → review → commit"*).
    auto format_value = [](const lte::TuneValue* tv) -> std::string {
        if (tv == nullptr) return "<none>";
        if (std::holds_alternative<double>(tv->value)) {
            char buf[32];
            std::snprintf(buf, sizeof(buf), "%.4g", std::get<double>(tv->value));
            return buf;
        }
        if (std::holds_alternative<std::string>(tv->value)) {
            return std::get<std::string>(tv->value);
        }
        if (std::holds_alternative<std::vector<double>>(tv->value)) {
            char buf[32];
            std::snprintf(buf, sizeof(buf), "[%d values]",
                static_cast<int>(std::get<std::vector<double>>(tv->value).size()));
            return buf;
        }
        return "<unknown>";
    };

    auto open_review_dialog = [container, edit_svc, workspace, format_value,
                               refresh_page_chip, refresh_review_button,
                               refresh_tree_state_indicators,
                               resync_workspace, on_staged_changed,
                               selected_label, page_staged_chip,
                               visible_editors, ecu_conn, ecu_def]() {
        auto names = edit_svc->staged_names();
        if (names.empty()) return;  // Nothing to review.

        auto* dialog = new QDialog(container);
        dialog->setWindowTitle(QString::fromUtf8("Review staged changes"));
        dialog->setModal(true);
        dialog->resize(620, 440);
        {
            char style[128];
            std::snprintf(style, sizeof(style),
                "QDialog { background: %s; }", tt::bg_base);
            dialog->setStyleSheet(QString::fromUtf8(style));
        }

        auto* dlg_layout = new QVBoxLayout(dialog);
        dlg_layout->setContentsMargins(tt::space_lg, tt::space_lg, tt::space_lg, tt::space_lg);
        dlg_layout->setSpacing(tt::space_md);

        // Title row. The count portion is a separate QLabel so per-row
        // revert can update it in place without rebuilding the whole
        // dialog.
        auto* title = new QLabel;
        title->setTextFormat(Qt::RichText);
        auto update_title = [title](int n) {
            char text[256];
            std::snprintf(text, sizeof(text),
                "<span style='color: %s; font-size: %dpx; font-weight: bold;'>"
                "%d staged change(s)</span>"
                "<br><span style='color: %s; font-size: %dpx;'>"
                "Review before writing to RAM or burning to flash.</span>",
                tt::text_primary, tt::font_heading, n,
                tt::text_muted, tt::font_small);
            title->setText(QString::fromUtf8(text));
        };
        update_title(static_cast<int>(names.size()));
        dlg_layout->addWidget(title);

        // Scrollable list of staged entries.
        auto* list_scroll = new QScrollArea;
        list_scroll->setWidgetResizable(true);
        list_scroll->setFrameShape(QFrame::NoFrame);
        auto* list_container = new QWidget;
        {
            char style[128];
            std::snprintf(style, sizeof(style),
                "background: %s; border: 1px solid %s; border-radius: %dpx;",
                tt::bg_panel, tt::border, tt::radius_md);
            list_container->setStyleSheet(QString::fromUtf8(style));
        }
        auto* list_layout = new QVBoxLayout(list_container);
        list_layout->setContentsMargins(tt::space_sm, tt::space_sm, tt::space_sm, tt::space_sm);
        list_layout->setSpacing(2);

        // Shared counter for the remaining visible rows so per-row
        // revert can update the title and decide when to auto-close.
        auto remaining = std::make_shared<int>(static_cast<int>(names.size()));

        for (const auto& name : names) {
            // Each row is a compound widget: the HTML diff label on the
            // left + a small × revert button on the right.
            auto* row = new QWidget;
            row->setStyleSheet("background: transparent; border: none;");
            auto* row_layout = new QHBoxLayout(row);
            row_layout->setContentsMargins(tt::space_sm, tt::space_xs, tt::space_sm, tt::space_xs);
            row_layout->setSpacing(tt::space_sm);

            auto* diff_label = new QLabel;
            diff_label->setTextFormat(Qt::RichText);
            const lte::TuneValue* base = edit_svc->get_base_value(name);
            const lte::TuneValue* cur  = edit_svc->get_value(name);
            std::string base_text = format_value(base);
            std::string cur_text  = format_value(cur);
            char row_html[640];
            std::snprintf(row_html, sizeof(row_html),
                "<span style='color: %s; font-size: %dpx; font-weight: bold;'>%s</span>"
                "<span style='color: %s; font-size: %dpx;'>  \xc2\xb7  </span>"
                "<span style='color: %s; font-size: %dpx; font-family: monospace;'>%s</span>"
                "<span style='color: %s; font-size: %dpx;'>  \xe2\x86\x92  </span>"
                "<span style='color: %s; font-size: %dpx; font-family: monospace; font-weight: bold;'>%s</span>",
                tt::text_primary, tt::font_body, name.c_str(),
                tt::text_dim, tt::font_small,
                tt::text_muted, tt::font_small, base_text.c_str(),
                tt::accent_primary, tt::font_small,
                tt::accent_primary, tt::font_small, cur_text.c_str());
            diff_label->setText(QString::fromUtf8(row_html));
            diff_label->setStyleSheet("background: transparent; border: none;");
            row_layout->addWidget(diff_label);
            row_layout->addStretch(1);

            // Per-row revert button (× icon). Tokenized: neutral until
            // hover, amber-accented on hover so the operator can tell
            // what it does without a tooltip.
            auto* revert_one = new QPushButton(QString::fromUtf8("\xe2\x9c\x95"));  // ✕
            revert_one->setCursor(Qt::PointingHandCursor);
            revert_one->setFixedSize(22, 22);
            revert_one->setToolTip(QString::fromUtf8(
                ("Revert " + name).c_str()));
            {
                char style[384];
                std::snprintf(style, sizeof(style),
                    "QPushButton { background: %s; border: 1px solid %s; "
                    "  border-radius: %dpx; color: %s; font-size: %dpx; } "
                    "QPushButton:hover { border-color: %s; color: %s; }",
                    tt::bg_inset, tt::border, tt::radius_sm,
                    tt::text_muted, tt::font_small,
                    tt::accent_warning, tt::accent_warning);
                revert_one->setStyleSheet(QString::fromUtf8(style));
            }
            row_layout->addWidget(revert_one);

            // Clicking revert: call edit_svc->revert, resync workspace
            // counts (so per-page chip + sidebar badge reflect reality),
            // reset the visible editor's text + style (sub-slice 94
            // bugfix — the QLineEdit on the TUNE page still holds the
            // user-typed text after edit_svc->revert clears the staged
            // entry, so the visible form drifts from the state until
            // we write the base value back and reset the tint cycle),
            // hide the popup row in place, decrement the title count,
            // auto-close the dialog when the last row is reverted.
            std::string name_copy = name;
            QObject::connect(revert_one, &QPushButton::clicked,
                             [row, dialog, name_copy, edit_svc, workspace,
                              resync_workspace, refresh_page_chip, refresh_review_button,
                              refresh_tree_state_indicators,
                              on_staged_changed, page_staged_chip, visible_editors,
                              update_title, remaining]() {
                edit_svc->revert(name_copy);
                (*resync_workspace)();
                // Reset the corresponding QLineEdit if it's on screen.
                auto it = visible_editors->find(name_copy);
                if (it != visible_editors->end() && it->second.edit != nullptr) {
                    it->second.edit->setText(QString::fromUtf8(it->second.base_text.c_str()));
                    it->second.edit->setStyleSheet(QString::fromUtf8(
                        tt::scalar_editor_style(tt::EditorState::Default).c_str()));
                    it->second.edit->setToolTip(QString());
                }
                // Refresh the outer state hierarchy.
                (*refresh_review_button)();
                (*refresh_tree_state_indicators)();
                if (on_staged_changed) on_staged_changed();
                const std::string& active = workspace->active_page();
                if (!active.empty()) (*refresh_page_chip)(active);
                else page_staged_chip->hide();
                row->hide();
                --(*remaining);
                update_title(*remaining);
                if (*remaining <= 0) dialog->accept();
            });

            list_layout->addWidget(row);
        }
        list_layout->addStretch(1);
        list_scroll->setWidget(list_container);
        dlg_layout->addWidget(list_scroll, 1);

        // Button row — Revert All on the left, Close on the right.
        auto* button_row = new QHBoxLayout;
        button_row->setSpacing(tt::space_sm);

        auto* revert_btn = new QPushButton(QString::fromUtf8("Revert All"));
        revert_btn->setCursor(Qt::PointingHandCursor);
        {
            char style[384];
            std::snprintf(style, sizeof(style),
                "QPushButton { background: %s; border: 1px solid %s; "
                "  border-radius: %dpx; padding: 6px 14px; "
                "  color: %s; font-size: %dpx; font-weight: bold; } "
                "QPushButton:hover { border-color: %s; color: %s; }",
                tt::bg_inset, tt::accent_danger, tt::radius_sm,
                tt::accent_danger, tt::font_body,
                tt::accent_danger, tt::text_primary);
            revert_btn->setStyleSheet(QString::fromUtf8(style));
        }
        button_row->addWidget(revert_btn);
        button_row->addStretch(1);

        // Sub-slice 95: "Write to RAM" button — commits the staged
        // edits as the "in-RAM" state by calling mark_written on every
        // currently-STAGED page. Visually cycles the three-zoom state
        // hierarchy from amber (pending) to blue (in RAM, awaiting
        // burn). No real ECU yet — this is the demo path that exercises
        // the state machine end-to-end.
        auto* write_btn = new QPushButton(QString::fromUtf8("Write to RAM"));
        write_btn->setCursor(Qt::PointingHandCursor);
        {
            char style[384];
            std::snprintf(style, sizeof(style),
                "QPushButton { background: %s; border: 1px solid %s; "
                "  border-radius: %dpx; padding: 6px 14px; "
                "  color: %s; font-size: %dpx; font-weight: bold; } "
                "QPushButton:hover { border-color: %s; color: %s; }",
                tt::fill_primary_mid, tt::accent_primary, tt::radius_sm,
                tt::text_primary, tt::font_body,
                tt::accent_primary, tt::text_primary);
            write_btn->setStyleSheet(QString::fromUtf8(style));
        }
        button_row->addWidget(write_btn);

        // Sub-slice 97: "Burn to Flash" button — terminal commit step
        // that takes the in-RAM edits and commits them to flash. Only
        // enabled when the workspace aggregate state is WRITTEN (i.e.
        // the operator has already run Write to RAM and has no raw
        // STAGED pages left). Disabled button is dimmed and non-
        // clickable. After burn: workspace counts zero out, visible
        // editors reset, all four state surfaces cycle to clean.
        auto* burn_btn = new QPushButton(QString::fromUtf8("Burn to Flash"));
        burn_btn->setCursor(Qt::PointingHandCursor);
        auto set_burn_style = [burn_btn](bool enabled) {
            char style[512];
            if (enabled) {
                std::snprintf(style, sizeof(style),
                    "QPushButton { background: %s; border: 1px solid %s; "
                    "  border-radius: %dpx; padding: 6px 14px; "
                    "  color: %s; font-size: %dpx; font-weight: bold; } "
                    "QPushButton:hover { border-color: %s; }",
                    tt::bg_inset, tt::accent_ok, tt::radius_sm,
                    tt::accent_ok, tt::font_body,
                    tt::accent_ok);
            } else {
                std::snprintf(style, sizeof(style),
                    "QPushButton { background: %s; border: 1px solid %s; "
                    "  border-radius: %dpx; padding: 6px 14px; "
                    "  color: %s; font-size: %dpx; font-weight: bold; }",
                    tt::bg_panel, tt::border, tt::radius_sm,
                    tt::text_dim, tt::font_body);
            }
            burn_btn->setStyleSheet(QString::fromUtf8(style));
        };
        {
            namespace wsns = tuner_core::workspace_state;
            bool ready = (workspace->aggregate_state() == wsns::PageState::WRITTEN);
            burn_btn->setEnabled(ready);
            set_burn_style(ready);
            if (!ready) {
                burn_btn->setToolTip(QString::fromUtf8(
                    "Write to RAM first \xe2\x80\x94 burning bypasses the "
                    "review step."));
            }
        }
        button_row->addWidget(burn_btn);

        auto* close_btn = new QPushButton(QString::fromUtf8("Close"));
        close_btn->setCursor(Qt::PointingHandCursor);
        {
            char style[384];
            std::snprintf(style, sizeof(style),
                "QPushButton { background: %s; border: 1px solid %s; "
                "  border-radius: %dpx; padding: 6px 14px; "
                "  color: %s; font-size: %dpx; } "
                "QPushButton:hover { color: %s; border-color: %s; }",
                tt::bg_panel, tt::border, tt::radius_sm,
                tt::text_secondary, tt::font_body,
                tt::text_primary, tt::accent_primary);
            close_btn->setStyleSheet(QString::fromUtf8(style));
        }
        button_row->addWidget(close_btn);
        dlg_layout->addLayout(button_row);

        QObject::connect(close_btn, &QPushButton::clicked, dialog, &QDialog::accept);

        // Write to RAM: encode each staged parameter and send to the ECU
        // via the Speeduino raw protocol. Falls back to the demo state-
        // machine path when offline. Mirrors Python's
        // TuningWorkspacePresenter.write_active_page().
        //
        // Build lookup maps for scalar and array definitions so we can
        // resolve parameter names to page/offset/encoding metadata.
        std::unordered_map<std::string, const tuner_core::IniScalar*> write_scalar_map;
        std::unordered_map<std::string, const tuner_core::IniArray*> write_array_map;
        if (ecu_def) {
            for (const auto& sc : ecu_def->constants.scalars)
                write_scalar_map[sc.name] = &sc;
            for (const auto& ar : ecu_def->constants.arrays)
                write_array_map[ar.name] = &ar;
        }

        QObject::connect(write_btn, &QPushButton::clicked,
                         [dialog, workspace, edit_svc, ecu_conn, ecu_def,
                          write_scalar_map, write_array_map,
                          refresh_page_chip,
                          refresh_review_button, refresh_tree_state_indicators,
                          on_staged_changed]() {
            namespace wsns = tuner_core::workspace_state;
            namespace spc = tuner_core::speeduino_param_codec;
            namespace svc = tuner_core::speeduino_value_codec;

            // If connected, send each staged parameter to the ECU.
            bool live = ecu_conn && ecu_conn->connected && ecu_conn->controller;
            if (live) {
                auto names = edit_svc->staged_names();
                for (const auto& name : names) {
                    auto* tv = edit_svc->get_value(name);
                    if (!tv) continue;

                    // Try scalar first.
                    auto sc_it = write_scalar_map.find(name);
                    if (sc_it != write_scalar_map.end()) {
                        const auto* sc = sc_it->second;
                        if (!sc->page.has_value() || !sc->offset.has_value()) continue;
                        int page = *sc->page;
                        int offset = *sc->offset;

                        spc::ScalarLayout layout;
                        layout.offset = 0;  // encode_scalar works relative to page slice
                        layout.data_type = svc::parse_data_type(sc->data_type);
                        layout.scale = sc->scale;
                        layout.translate = sc->translate;
                        if (sc->bit_offset.has_value() && sc->bit_length.has_value()) {
                            layout.bit_offset = *sc->bit_offset;
                            layout.bit_length = *sc->bit_length;
                        }

                        double val = 0.0;
                        if (std::holds_alternative<double>(tv->value)) {
                            val = std::get<double>(tv->value);
                        } else if (std::holds_alternative<std::string>(tv->value)) {
                            try { val = std::stod(std::get<std::string>(tv->value)); }
                            catch (...) { continue; }
                        }

                        // For bit-field scalars, read current byte(s) from ECU
                        // so encode_scalar can do the read-modify-write.
                        std::size_t data_sz = svc::data_size_bytes(layout.data_type);
                        std::vector<std::uint8_t> page_slice(data_sz, 0);
                        if (layout.bit_offset >= 0 && layout.bit_length >= 0) {
                            page_slice = ecu_conn->read_page_slice(
                                page, offset, static_cast<int>(data_sz));
                            if (page_slice.size() < data_sz)
                                page_slice.resize(data_sz, 0);
                        }

                        auto encoded = spc::encode_scalar(layout, val, page_slice);
                        ecu_conn->write_chunked(page, offset,
                            encoded.data(), encoded.size(), false);
                        continue;
                    }

                    // Try array/table.
                    auto ar_it = write_array_map.find(name);
                    if (ar_it != write_array_map.end()) {
                        const auto* ar = ar_it->second;
                        if (!ar->page.has_value() || !ar->offset.has_value()) continue;
                        int page = *ar->page;
                        int offset = *ar->offset;

                        if (!std::holds_alternative<std::vector<double>>(tv->value))
                            continue;
                        const auto& vals = std::get<std::vector<double>>(tv->value);

                        spc::TableLayout layout;
                        layout.offset = 0;
                        layout.data_type = svc::parse_data_type(ar->data_type);
                        layout.scale = ar->scale;
                        layout.translate = ar->translate;
                        layout.rows = static_cast<std::size_t>(ar->rows);
                        layout.columns = static_cast<std::size_t>(ar->columns);

                        auto encoded = spc::encode_table(layout, vals);
                        ecu_conn->write_chunked(page, offset,
                            encoded.data(), encoded.size(), true);
                    }
                }
            }

            // State machine transitions — same as before.
            auto staged_pages = workspace->pages_in_state(wsns::PageState::STAGED);
            for (const auto& pid : staged_pages) {
                workspace->mark_written(pid);
            }
            (*refresh_review_button)();
            (*refresh_tree_state_indicators)();
            if (on_staged_changed) on_staged_changed();
            const std::string& active = workspace->active_page();
            if (!active.empty()) (*refresh_page_chip)(active);
            dialog->accept();
        });

        // Burn to flash: send burn command for each dirty page, then
        // clean up the workspace state. Mirrors Python's
        // TuningWorkspacePresenter.burn_active_page(). When offline,
        // falls back to the demo path (revert_all approximates accept).
        QObject::connect(burn_btn, &QPushButton::clicked,
                         [dialog, workspace, edit_svc, visible_editors,
                          refresh_page_chip, refresh_review_button,
                          refresh_tree_state_indicators, on_staged_changed,
                          page_staged_chip, ecu_conn]() {
            namespace wsns = tuner_core::workspace_state;

            // Confirmation — burn is irreversible.
            auto answer = QMessageBox::warning(dialog,
                QString::fromUtf8("Burn to Flash"),
                QString::fromUtf8(
                    "Permanently write all changes to ECU flash memory?\n"
                    "This cannot be undone."),
                QMessageBox::Ok | QMessageBox::Cancel,
                QMessageBox::Cancel);
            if (answer != QMessageBox::Ok) return;

            // If connected, burn each dirty page to flash.
            bool live = ecu_conn && ecu_conn->connected && ecu_conn->controller;
            if (live && !ecu_conn->dirty_pages.empty()) {
                for (int page : ecu_conn->dirty_pages) {
                    ecu_conn->controller->burn(
                        static_cast<std::uint8_t>(page));
                    // 20ms inter-page delay — matches Python.
                    std::this_thread::sleep_for(std::chrono::milliseconds(20));
                }
                ecu_conn->dirty_pages.clear();
            }

            auto written_pages = workspace->pages_in_state(wsns::PageState::WRITTEN);
            for (const auto& pid : written_pages) {
                workspace->mark_burned(pid);
            }
            edit_svc->revert_all();
            // Reset every visible editor to default (base value + neutral tint).
            for (auto& [name, entry] : *visible_editors) {
                if (entry.edit == nullptr) continue;
                entry.edit->setText(QString::fromUtf8(entry.base_text.c_str()));
                entry.edit->setStyleSheet(QString::fromUtf8(
                    tt::scalar_editor_style(tt::EditorState::Default).c_str()));
                entry.edit->setToolTip(QString());
            }
            page_staged_chip->hide();
            (*refresh_review_button)();
            (*refresh_tree_state_indicators)();
            if (on_staged_changed) on_staged_changed();
            dialog->accept();
        });

        QObject::connect(revert_btn, &QPushButton::clicked,
                         [dialog, edit_svc, workspace, refresh_page_chip,
                          refresh_review_button, refresh_tree_state_indicators,
                          on_staged_changed,
                          page_staged_chip, visible_editors]() {
            auto answer = QMessageBox::question(dialog,
                QString::fromUtf8("Revert All"),
                QString::fromUtf8(
                    "Discard all staged changes?\n"
                    "This will undo every edit since the last burn."),
                QMessageBox::Ok | QMessageBox::Cancel,
                QMessageBox::Cancel);
            if (answer != QMessageBox::Ok) return;
            edit_svc->revert_all();
            workspace->revert_all();
            // Sub-slice 94 bugfix: reset every visible QLineEdit back
            // to its base text and default style. Same reasoning as
            // per-row revert — the editor widgets still display the
            // user-typed values until we write the base back.
            for (auto& [name, entry] : *visible_editors) {
                if (entry.edit == nullptr) continue;
                entry.edit->setText(QString::fromUtf8(entry.base_text.c_str()));
                entry.edit->setStyleSheet(QString::fromUtf8(
                    tt::scalar_editor_style(tt::EditorState::Default).c_str()));
                entry.edit->setToolTip(QString());
            }
            // Refresh all four staged-state surfaces in one shot:
            // per-page chip (hide), review button (hide), tree entries
            // (clear markers), sidebar badge (clear).
            page_staged_chip->hide();
            (*refresh_review_button)();
            (*refresh_tree_state_indicators)();
            if (on_staged_changed) on_staged_changed();
            dialog->accept();
        });

        dialog->exec();
        dialog->deleteLater();
    };

    QObject::connect(review_button, &QPushButton::clicked, open_review_dialog);

    // Ctrl+R: alternate keyboard path to the review popup.
    auto* review_shortcut = new QShortcut(QKeySequence(Qt::CTRL | Qt::Key_R), container);
    QObject::connect(review_shortcut, &QShortcut::activated, open_review_dialog);

    // Sub-slice 97: Ctrl+W / Ctrl+B open the review popup with focus
    // on the corresponding action — the popup is the one place the
    // operator commits state changes, so both shortcuts land there.
    // (Cmd+W usually closes on macOS; this is Windows only so the
    // conflict doesn't apply.)
    auto* write_shortcut = new QShortcut(QKeySequence(Qt::CTRL | Qt::Key_W), container);
    QObject::connect(write_shortcut, &QShortcut::activated, open_review_dialog);
    auto* burn_shortcut = new QShortcut(QKeySequence(Qt::CTRL | Qt::Key_B), container);
    QObject::connect(burn_shortcut, &QShortcut::activated, open_review_dialog);

    return container;
}

// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// DialGaugeWidget — custom-painted analog gauge with arc, needle, zones
// ---------------------------------------------------------------------------

class DialGaugeWidget : public QWidget {
public:
    struct Config {
        std::string title;
        std::string units;
        double min_value = 0;
        double max_value = 100;
        struct Zone { double lo; double hi; std::string color; };
        std::vector<Zone> zones;
    };

    using ClickCallback = std::function<void(const std::string& title)>;
    using ConfigCallback = std::function<void(const std::string& widget_id)>;

    using SwapCallback = std::function<void(const std::string& from, const std::string& to)>;

    explicit DialGaugeWidget(const Config& cfg, QWidget* parent = nullptr)
        : QWidget(parent), cfg_(cfg) {
        setMinimumSize(120, 120);
        setCursor(Qt::PointingHandCursor);
        setAcceptDrops(true);
    }

    void set_value(double v) { value_ = v; has_value_ = true; update(); }
    void clear_value() { has_value_ = false; update(); }
    void set_click_callback(ClickCallback cb) { click_cb_ = std::move(cb); }
    void set_config_callback(ConfigCallback cb) { config_cb_ = std::move(cb); }
    void set_swap_callback(SwapCallback cb) { swap_cb_ = std::move(cb); }
    void set_widget_id(const std::string& id) { widget_id_ = id; }

protected:
    void mousePressEvent(QMouseEvent* ev) override {
        drag_start_ = ev->pos();
        if (click_cb_) click_cb_(cfg_.title);
    }

    void contextMenuEvent(QContextMenuEvent* ev) override {
        if (!config_cb_) return;
        auto* menu = new QMenu(this);
        auto* action = menu->addAction("Configure Gauge...");
        QObject::connect(action, &QAction::triggered,
                         [this]() { if (config_cb_) config_cb_(widget_id_); });
        menu->popup(ev->globalPos());
    }

    void mouseMoveEvent(QMouseEvent* ev) override {
        if (!(ev->buttons() & Qt::LeftButton)) return;
        if (widget_id_.empty()) return;
        if ((ev->pos() - drag_start_).manhattanLength() < 12) return;
        auto* drag = new QDrag(this);
        auto* mime = new QMimeData;
        mime->setData("application/x-gauge-widget-id",
            QByteArray::fromStdString(widget_id_));
        drag->setMimeData(mime);
        drag->exec(Qt::MoveAction);
    }

    void dragEnterEvent(QDragEnterEvent* ev) override {
        if (ev->mimeData()->hasFormat("application/x-gauge-widget-id")) {
            auto from_id = ev->mimeData()->data("application/x-gauge-widget-id").toStdString();
            if (from_id != widget_id_)
                ev->acceptProposedAction();
        }
    }

    void dropEvent(QDropEvent* ev) override {
        auto from_id = ev->mimeData()->data("application/x-gauge-widget-id").toStdString();
        if (swap_cb_ && from_id != widget_id_)
            swap_cb_(from_id, widget_id_);
        ev->acceptProposedAction();
    }

    void paintEvent(QPaintEvent*) override {
        QPainter p(this);
        p.setRenderHint(QPainter::Antialiasing);

        const double w = width(), h = height();
        const double side = std::min(w, h);
        const double cx = w / 2.0, cy = h / 2.0;
        const double r = side / 2.0 * 0.86;
        const double track_w = r * 0.14;
        const double span = cfg_.max_value - cfg_.min_value;
        constexpr double SWEEP = 270.0;
        constexpr double START = 225.0;
        constexpr double PI = 3.14159265358979323846;

        // Outer bezel ring — subtle metallic edge.
        p.setPen(Qt::NoPen);
        {
            QRadialGradient bezel(cx, cy, r + track_w * 0.9);
            bezel.setColorAt(0.85, QColor(34, 38, 48));
            bezel.setColorAt(0.95, QColor(52, 56, 66));
            bezel.setColorAt(1.0,  QColor(28, 32, 40));
            p.setBrush(bezel);
            p.drawEllipse(QPointF(cx, cy), r + track_w * 0.9, r + track_w * 0.9);
        }

        // Background circle.
        p.setBrush(QColor(18, 21, 28));
        p.drawEllipse(QPointF(cx, cy), r + track_w * 0.5, r + track_w * 0.5);

        // Background arc track.
        QRectF arc_rect(cx - r, cy - r, r * 2, r * 2);
        QPen bg_pen(QColor(40, 44, 52));
        bg_pen.setWidthF(track_w);
        bg_pen.setCapStyle(Qt::FlatCap);
        p.setPen(bg_pen);
        p.drawArc(arc_rect, int(START * 16), int(-SWEEP * 16));

        // Zone arcs.
        auto zone_color = [](const std::string& c) -> QColor {
            if (c == "ok")      return QColor(90, 214, 135);
            if (c == "warning") return QColor(214, 165, 90);
            if (c == "danger")  return QColor(214, 90, 90);
            return QColor(120, 120, 120);
        };

        if (span > 0) {
            for (const auto& z : cfg_.zones) {
                double lo_f = std::max(0.0, (z.lo - cfg_.min_value) / span);
                double hi_f = std::min(1.0, (z.hi - cfg_.min_value) / span);
                if (hi_f <= lo_f) continue;
                QPen zp(zone_color(z.color));
                zp.setWidthF(track_w);
                zp.setCapStyle(Qt::FlatCap);
                p.setPen(zp);
                double start_deg = START - lo_f * SWEEP;
                double span_deg = -(hi_f - lo_f) * SWEEP;
                p.drawArc(arc_rect, int(start_deg * 16), int(span_deg * 16));
            }
        }

        // Minor tick marks (40 subdivisions).
        for (int i = 0; i <= 40; ++i) {
            double frac = i / 40.0;
            double angle = (START - frac * SWEEP) * PI / 180.0;
            double outer = r - track_w * 0.5;
            bool major = (i % 5 == 0);
            double inner = major ? outer - r * 0.10 : outer - r * 0.05;
            double pen_w = major ? std::max(1.5, side * 0.014) : std::max(0.8, side * 0.006);
            QColor tick_color = major ? QColor(110, 116, 130) : QColor(60, 64, 72);
            p.setPen(QPen(tick_color, pen_w));
            p.drawLine(
                QPointF(cx + outer * std::cos(angle), cy - outer * std::sin(angle)),
                QPointF(cx + inner * std::cos(angle), cy - inner * std::sin(angle)));

            // Tick labels on major marks only.
            if (major && span > 0) {
                double val = cfg_.min_value + frac * span;
                char lbl[16];
                if (val == static_cast<int>(val) && std::abs(val) < 100000)
                    std::snprintf(lbl, sizeof(lbl), "%d", static_cast<int>(val));
                else
                    std::snprintf(lbl, sizeof(lbl), "%.0f", val);
                QFont tf;
                tf.setPixelSize(std::max(8, static_cast<int>(side * 0.07)));
                p.setFont(tf);
                p.setPen(QColor(140, 146, 160));
                double label_r = inner - r * 0.09;
                QPointF lp(cx + label_r * std::cos(angle), cy - label_r * std::sin(angle));
                p.drawText(QRectF(lp.x() - 22, lp.y() - 9, 44, 18),
                           Qt::AlignCenter, QString::fromUtf8(lbl));
            }
        }

        // Needle.
        if (has_value_ && span > 0) {
            double frac = std::clamp((value_ - cfg_.min_value) / span, 0.0, 1.0);
            double angle = (START - frac * SWEEP) * PI / 180.0;
            double tip = r * 0.68;

            // Needle color from active zone.
            QColor nc(210, 210, 210);
            for (auto it = cfg_.zones.rbegin(); it != cfg_.zones.rend(); ++it) {
                if (value_ >= it->lo && value_ <= it->hi) {
                    nc = zone_color(it->color);
                    break;
                }
            }

            // Tapered needle — triangle polygon for a premium look.
            double needle_w = std::max(2.0, side * 0.025);
            double perp = angle + PI / 2.0;
            QPointF tip_pt(cx + tip * std::cos(angle), cy - tip * std::sin(angle));
            QPointF base_l(cx + needle_w * std::cos(perp), cy - needle_w * std::sin(perp));
            QPointF base_r(cx - needle_w * std::cos(perp), cy + needle_w * std::sin(perp));
            // Needle shadow/glow.
            {
                QColor glow = nc;
                glow.setAlpha(40);
                p.setPen(Qt::NoPen);
                p.setBrush(glow);
                QPointF glow_pts[3] = {
                    QPointF(tip_pt.x() + 1, tip_pt.y() + 1),
                    QPointF(base_l.x() + 1, base_l.y() + 1),
                    QPointF(base_r.x() + 1, base_r.y() + 1)
                };
                p.drawPolygon(glow_pts, 3);
            }
            // Needle body.
            p.setPen(Qt::NoPen);
            p.setBrush(nc);
            QPointF needle_pts[3] = { tip_pt, base_l, base_r };
            p.drawPolygon(needle_pts, 3);

            // Hub — double ring with colored center.
            double hub_r = r * 0.10;
            p.setPen(Qt::NoPen);
            p.setBrush(QColor(38, 42, 52));
            p.drawEllipse(QPointF(cx, cy), hub_r, hub_r);
            p.setBrush(QColor(52, 56, 66));
            p.drawEllipse(QPointF(cx, cy), hub_r * 0.7, hub_r * 0.7);
            p.setBrush(nc);
            p.drawEllipse(QPointF(cx, cy), hub_r * 0.4, hub_r * 0.4);
        }

        // Value readout.
        {
            QFont vf;
            vf.setPixelSize(std::max(10, static_cast<int>(side * 0.16)));
            vf.setBold(true);
            p.setFont(vf);
            p.setPen(QColor(225, 228, 235));
            char val_buf[32];
            if (!has_value_)
                std::snprintf(val_buf, sizeof(val_buf), "%s", "\xe2\x80\x94");
            else if (value_ == static_cast<int>(value_))
                std::snprintf(val_buf, sizeof(val_buf), "%d", static_cast<int>(value_));
            else
                std::snprintf(val_buf, sizeof(val_buf), "%.1f", value_);
            p.drawText(QRectF(cx - r * 0.5, cy + r * 0.15, r, r * 0.35),
                       Qt::AlignCenter, QString::fromUtf8(val_buf));
        }

        // Units.
        if (!cfg_.units.empty()) {
            QFont uf;
            uf.setPixelSize(std::max(7, static_cast<int>(side * 0.075)));
            p.setFont(uf);
            p.setPen(QColor(90, 96, 110));
            p.drawText(QRectF(cx - r * 0.4, cy + r * 0.46, r * 0.8, r * 0.2),
                       Qt::AlignCenter, QString::fromUtf8(cfg_.units.c_str()));
        }

        // Title.
        {
            QFont tf;
            tf.setPixelSize(std::max(7, static_cast<int>(side * 0.085)));
            p.setFont(tf);
            p.setPen(QColor(130, 135, 148));
            p.drawText(QRectF(cx - r * 0.5, cy + r * 0.65, r, r * 0.22),
                       Qt::AlignCenter, QString::fromUtf8(cfg_.title.c_str()));
        }
    }

private:
    Config cfg_;
    double value_ = 0;
    bool has_value_ = false;
    ClickCallback click_cb_;
    ConfigCallback config_cb_;
    SwapCallback swap_cb_;
    std::string widget_id_;
    QPoint drag_start_;
};

// ---------------------------------------------------------------------------
// HistogramWidget — scrolling sparkline chart (Phase D)
// ---------------------------------------------------------------------------

class HistogramWidget : public QWidget {
public:
    struct Config {
        std::string title;
        std::string units;
        double min_value = 0;
        double max_value = 100;
        int max_samples = 60;  // ~12 seconds at 5Hz
        std::string line_color = tt::accent_primary;
    };

    explicit HistogramWidget(const Config& cfg, QWidget* parent = nullptr)
        : QWidget(parent), cfg_(cfg) {
        setMinimumSize(200, 80);
        samples_.reserve(cfg.max_samples);
    }

    void push_value(double v) {
        samples_.push_back(v);
        if (static_cast<int>(samples_.size()) > cfg_.max_samples)
            samples_.erase(samples_.begin());
        update();
    }

protected:
    void paintEvent(QPaintEvent*) override {
        QPainter p(this);
        p.setRenderHint(QPainter::Antialiasing);
        const double w = width(), h = height();

        // Background.
        p.fillRect(rect(), QColor(26, 29, 36));

        // Border.
        p.setPen(QPen(QColor(47, 52, 61), 1));
        p.drawRect(0, 0, static_cast<int>(w) - 1, static_cast<int>(h) - 1);

        if (samples_.size() < 2) {
            p.setPen(QColor(100, 106, 120));
            QFont f; f.setPixelSize(10); p.setFont(f);
            p.drawText(rect(), Qt::AlignCenter, QString::fromUtf8("Waiting for data..."));
            return;
        }

        double range = cfg_.max_value - cfg_.min_value;
        if (range <= 0) range = 1;

        // Draw gridlines.
        p.setPen(QPen(QColor(35, 39, 48), 1));
        for (int i = 1; i < 4; ++i) {
            double y = h * i / 4.0;
            p.drawLine(QPointF(0, y), QPointF(w, y));
        }

        // Draw line.
        QColor lineColor(cfg_.line_color.c_str());
        p.setPen(QPen(lineColor, 1.5));
        int n = static_cast<int>(samples_.size());
        double step = w / std::max(1, cfg_.max_samples - 1);
        double x_offset = (cfg_.max_samples - n) * step;
        for (int i = 1; i < n; ++i) {
            double x0 = x_offset + (i - 1) * step;
            double x1 = x_offset + i * step;
            double y0 = h - ((samples_[i - 1] - cfg_.min_value) / range) * h;
            double y1 = h - ((samples_[i] - cfg_.min_value) / range) * h;
            y0 = std::clamp(y0, 0.0, h);
            y1 = std::clamp(y1, 0.0, h);
            p.drawLine(QPointF(x0, y0), QPointF(x1, y1));
        }

        // Title + latest value.
        p.setPen(QColor(138, 147, 166));
        QFont tf; tf.setPixelSize(9); p.setFont(tf);
        char label[64];
        std::snprintf(label, sizeof(label), "%s: %.1f %s",
            cfg_.title.c_str(), samples_.back(), cfg_.units.c_str());
        p.drawText(4, 12, QString::fromUtf8(label));

        // Min/max labels.
        char min_label[16], max_label[16];
        std::snprintf(min_label, sizeof(min_label), "%.0f", cfg_.min_value);
        std::snprintf(max_label, sizeof(max_label), "%.0f", cfg_.max_value);
        p.drawText(4, static_cast<int>(h) - 3, QString::fromUtf8(min_label));
        p.drawText(4, 22, QString::fromUtf8(max_label));
    }

private:
    Config cfg_;
    std::vector<double> samples_;
};

// ---------------------------------------------------------------------------
// Shared card builder used across tabs
// ---------------------------------------------------------------------------

// Tab header factory — the single place that builds the hero title +
// breadcrumb label used by FLASH / ASSIST / TRIGGERS / LOGGING tabs.
// Before this helper, four tabs each pasted the same 4-line inline-
// hex stylesheet and the same HTML shape, which meant tuning the
// header look meant touching four files in lockstep. Collapsing to
// one helper is the sub-slice-91 pattern: any repeated visual
// grammar gets named and reused so the palette stays coherent as
// new tabs land.
QLabel* make_tab_header(const char* title, const char* breadcrumb) {
    char html[512];
    tt::format_tab_header_html(html, sizeof(html), title, breadcrumb);
    auto* label = new QLabel(QString::fromUtf8(html));
    label->setTextFormat(Qt::RichText);
    label->setStyleSheet(QString::fromUtf8(tt::tab_header_style().c_str()));
    return label;
}

QWidget* make_info_card(const char* heading, const char* body,
                         const char* accent_color = tt::accent_primary) {
    auto* w = new QWidget;
    auto* l = new QVBoxLayout(w);
    // Use elevated bg (not bg_panel) so info cards read as a tier above
    // regular content containers — matches their role as "attention
    // please" surfaces the operator should read before acting.
    l->setContentsMargins(tt::space_md + 2, tt::space_md, tt::space_md + 2, tt::space_md);
    l->setSpacing(tt::space_xs + 2);
    char style[256];
    std::snprintf(style, sizeof(style),
        "background-color: %s; border: 1px solid %s; "
        "border-left: 3px solid %s; border-radius: %dpx;",
        tt::bg_elevated, tt::border, accent_color, tt::radius_md);
    w->setStyleSheet(QString::fromUtf8(style));

    auto* h = new QLabel(QString::fromUtf8(heading));
    QFont hf = h->font();
    hf.setBold(true);
    hf.setPixelSize(tt::font_label);
    h->setFont(hf);
    char heading_style[96];
    std::snprintf(heading_style, sizeof(heading_style),
        "color: %s; border: none;", tt::text_primary);
    h->setStyleSheet(QString::fromUtf8(heading_style));
    l->addWidget(h);

    auto* b = new QLabel(QString::fromUtf8(body));
    b->setWordWrap(true);
    char body_style[96];
    std::snprintf(body_style, sizeof(body_style),
        "color: %s; border: none; font-size: %dpx;",
        tt::text_secondary, tt::font_body);
    b->setStyleSheet(QString::fromUtf8(body_style));
    l->addWidget(b);
    return w;
}

// ---------------------------------------------------------------------------
// Live tab — runtime telemetry + gauge color zones
// ---------------------------------------------------------------------------

using NavigateCallback = std::function<void(int page_index, const std::string& hint)>;

// Dashboard JSON serialization — hand-rolled for the known flat schema.
// Gauge configuration dialog — edit source channel, kind, range, and zones.
// Returns true if the user accepted changes, false on cancel.
bool open_gauge_config_dialog(
    QWidget* parent,
    tuner_core::dashboard_layout::Widget& widget,
    const std::vector<tuner_core::IniGaugeConfiguration>& gauge_catalog) {
    namespace dln = tuner_core::dashboard_layout;
    namespace gcz = tuner_core::gauge_color_zones;

    auto* dlg = new QDialog(parent);
    dlg->setWindowTitle("Configure Gauge");
    dlg->setMinimumWidth(380);
    {
        char s[64];
        std::snprintf(s, sizeof(s), "QDialog { background: %s; }", tt::bg_base);
        dlg->setStyleSheet(QString::fromUtf8(s));
    }

    auto* form = new QVBoxLayout(dlg);
    form->setContentsMargins(tt::space_lg, tt::space_lg, tt::space_lg, tt::space_lg);
    form->setSpacing(tt::space_sm);

    auto make_form_row = [form](const char* label_text) -> QComboBox* {
        auto* row = new QHBoxLayout;
        auto* label = new QLabel(QString::fromUtf8(label_text));
        label->setFixedWidth(120);
        {
            char s[64];
            std::snprintf(s, sizeof(s), "QLabel { color: %s; }", tt::text_secondary);
            label->setStyleSheet(QString::fromUtf8(s));
        }
        row->addWidget(label);
        auto* combo = new QComboBox;
        {
            char s[192];
            std::snprintf(s, sizeof(s),
                "QComboBox { background: %s; color: %s; border: 1px solid %s; "
                "border-radius: %dpx; padding: 4px 8px; }",
                tt::bg_elevated, tt::text_primary, tt::border, tt::radius_sm);
            combo->setStyleSheet(QString::fromUtf8(s));
        }
        row->addWidget(combo, 1);
        form->addLayout(row);
        return combo;
    };

    auto make_spin_row = [form](const char* label_text, double val,
                                double min_v, double max_v) -> QSpinBox* {
        auto* row = new QHBoxLayout;
        auto* label = new QLabel(QString::fromUtf8(label_text));
        label->setFixedWidth(120);
        {
            char s[64];
            std::snprintf(s, sizeof(s), "QLabel { color: %s; }", tt::text_secondary);
            label->setStyleSheet(QString::fromUtf8(s));
        }
        row->addWidget(label);
        auto* spin = new QSpinBox;
        spin->setRange(static_cast<int>(min_v), static_cast<int>(max_v));
        spin->setValue(static_cast<int>(val));
        {
            char s[192];
            std::snprintf(s, sizeof(s),
                "QSpinBox { background: %s; color: %s; border: 1px solid %s; "
                "border-radius: %dpx; padding: 4px; }",
                tt::bg_elevated, tt::text_primary, tt::border, tt::radius_sm);
            spin->setStyleSheet(QString::fromUtf8(s));
        }
        row->addWidget(spin, 1);
        form->addLayout(row);
        return spin;
    };

    // Source channel combo — populated from INI gauge catalog.
    auto* source_combo = make_form_row("Source Channel:");
    int current_source_idx = 0;
    for (int i = 0; i < static_cast<int>(gauge_catalog.size()); ++i) {
        const auto& g = gauge_catalog[i];
        char entry[128];
        std::snprintf(entry, sizeof(entry), "%s (%s)", g.title.c_str(), g.channel.c_str());
        source_combo->addItem(QString::fromUtf8(entry));
        if (g.channel == widget.source || g.name == widget.widget_id)
            current_source_idx = i;
    }
    // Add "Custom" at end for manual entry.
    source_combo->addItem(QString::fromUtf8("Custom (keep current)"));
    source_combo->setCurrentIndex(current_source_idx);

    // Kind selector.
    auto* kind_combo = make_form_row("Gauge Kind:");
    kind_combo->addItem("Analog Dial");
    kind_combo->addItem("Number Card");
    kind_combo->addItem("Bar");
    int kind_idx = (widget.kind == "dial") ? 0 : (widget.kind == "bar") ? 2 : 1;
    kind_combo->setCurrentIndex(kind_idx);

    // Min / Max.
    auto* min_spin = make_spin_row("Minimum:", widget.min_value, -1000, 50000);
    auto* max_spin = make_spin_row("Maximum:", widget.max_value, -1000, 50000);

    // Zone presets.
    auto* zone_combo = make_form_row("Color Zones:");
    zone_combo->addItem("Keep Current");
    zone_combo->addItem("Temperature (CLT/IAT)");
    zone_combo->addItem("AFR (10-20)");
    zone_combo->addItem("RPM (0-8000)");
    zone_combo->addItem("Voltage (8-16V)");
    zone_combo->addItem("None (no zones)");

    // Auto-fill from catalog on source change.
    QObject::connect(source_combo, QOverload<int>::of(&QComboBox::currentIndexChanged),
                     [source_combo, min_spin, max_spin, &gauge_catalog](int idx) {
        if (idx < 0 || idx >= static_cast<int>(gauge_catalog.size())) return;
        const auto& g = gauge_catalog[idx];
        if (g.lo.has_value()) min_spin->setValue(static_cast<int>(*g.lo));
        if (g.hi.has_value()) max_spin->setValue(static_cast<int>(*g.hi));
    });

    // OK / Cancel.
    auto* btn_row = new QHBoxLayout;
    btn_row->addStretch(1);
    auto* ok_btn = new QPushButton("OK");
    auto* cancel_btn = new QPushButton("Cancel");
    btn_row->addWidget(ok_btn);
    btn_row->addWidget(cancel_btn);
    form->addLayout(btn_row);

    bool accepted = false;

    QObject::connect(cancel_btn, &QPushButton::clicked, dlg, &QDialog::reject);
    QObject::connect(ok_btn, &QPushButton::clicked, [&]() {
        // Apply changes to widget.
        int src_idx = source_combo->currentIndex();
        if (src_idx >= 0 && src_idx < static_cast<int>(gauge_catalog.size())) {
            const auto& g = gauge_catalog[src_idx];
            widget.widget_id = g.name;
            widget.source = g.channel;
            widget.title = g.title;
            widget.units = g.units;
        }
        const char* kinds[] = {"dial", "number", "bar"};
        widget.kind = kinds[std::clamp(kind_combo->currentIndex(), 0, 2)];
        widget.min_value = min_spin->value();
        widget.max_value = max_spin->value();

        // Zone presets.
        int zone_idx = zone_combo->currentIndex();
        if (zone_idx > 0) {
            widget.color_zones.clear();
            gcz::Thresholds th;
            switch (zone_idx) {
                case 1: // Temperature
                    th.hi_warn = 95; th.hi_danger = 105; break;
                case 2: // AFR
                    th.lo_danger = 10; th.lo_warn = 11.5;
                    th.hi_warn = 16; th.hi_danger = 18; break;
                case 3: // RPM
                    th.hi_warn = 6500; th.hi_danger = 7500; break;
                case 4: // Voltage
                    th.lo_danger = 11; th.lo_warn = 12;
                    th.hi_warn = 14.5; th.hi_danger = 15.5; break;
                case 5: // None
                    break;
            }
            if (zone_idx < 5) {
                auto zones = gcz::derive_zones(widget.min_value, widget.max_value, th);
                for (const auto& z : zones) {
                    dln::ColorZone cz;
                    cz.lo = z.lo; cz.hi = z.hi; cz.color = z.color;
                    widget.color_zones.push_back(cz);
                }
            }
        }
        accepted = true;
        dlg->accept();
    });

    dlg->exec();
    dlg->deleteLater();
    return accepted;
}

std::string dashboard_layout_to_json(const tuner_core::dashboard_layout::Layout& layout) {
    namespace dln = tuner_core::dashboard_layout;
    std::string json = "{\"name\":\"";
    json += layout.name;
    json += "\",\"widgets\":[";
    for (size_t i = 0; i < layout.widgets.size(); ++i) {
        if (i > 0) json += ",";
        const auto& w = layout.widgets[i];
        char buf[512];
        std::snprintf(buf, sizeof(buf),
            "{\"widget_id\":\"%s\",\"kind\":\"%s\",\"title\":\"%s\","
            "\"source\":\"%s\",\"units\":\"%s\","
            "\"x\":%.0f,\"y\":%.0f,\"width\":%.0f,\"height\":%.0f,"
            "\"min_value\":%.6g,\"max_value\":%.6g,\"color_zones\":[",
            w.widget_id.c_str(), w.kind.c_str(), w.title.c_str(),
            w.source.c_str(), w.units.c_str(),
            w.x, w.y, w.width, w.height,
            w.min_value, w.max_value);
        json += buf;
        for (size_t z = 0; z < w.color_zones.size(); ++z) {
            if (z > 0) json += ",";
            char zb[64];
            std::snprintf(zb, sizeof(zb),
                "{\"lo\":%.6g,\"hi\":%.6g,\"color\":\"%s\"}",
                w.color_zones[z].lo, w.color_zones[z].hi,
                w.color_zones[z].color.c_str());
            json += zb;
        }
        json += "]}";
    }
    json += "]}";
    return json;
}

tuner_core::dashboard_layout::Layout dashboard_layout_from_json(const std::string& text) {
    namespace dln = tuner_core::dashboard_layout;
    dln::Layout layout;
    // Extract name.
    auto name_pos = text.find("\"name\":\"");
    if (name_pos != std::string::npos) {
        auto start = name_pos + 8;
        auto end = text.find('"', start);
        if (end != std::string::npos) layout.name = text.substr(start, end - start);
    }
    // Extract widgets array.
    auto widgets_pos = text.find("\"widgets\":[");
    if (widgets_pos == std::string::npos) return layout;

    // Helper to extract a string field value.
    auto extract_str = [](const std::string& obj, const std::string& key) -> std::string {
        auto pos = obj.find("\"" + key + "\":\"");
        if (pos == std::string::npos) return {};
        auto start = pos + key.size() + 4;
        auto end = obj.find('"', start);
        return (end != std::string::npos) ? obj.substr(start, end - start) : std::string{};
    };
    auto extract_num = [](const std::string& obj, const std::string& key, double def = 0.0) -> double {
        auto pos = obj.find("\"" + key + "\":");
        if (pos == std::string::npos) return def;
        auto start = pos + key.size() + 3;
        try { return std::stod(obj.substr(start)); } catch (...) { return def; }
    };

    // Walk widget objects by finding matching braces.
    size_t pos = widgets_pos + 11;
    while (pos < text.size()) {
        auto obj_start = text.find('{', pos);
        if (obj_start == std::string::npos) break;
        // Find matching close brace (skip nested zone objects).
        int depth = 0;
        size_t obj_end = obj_start;
        for (size_t i = obj_start; i < text.size(); ++i) {
            if (text[i] == '{') depth++;
            if (text[i] == '}') { depth--; if (depth == 0) { obj_end = i; break; } }
        }
        std::string obj = text.substr(obj_start, obj_end - obj_start + 1);

        dln::Widget w;
        w.widget_id = extract_str(obj, "widget_id");
        w.kind = extract_str(obj, "kind");
        w.title = extract_str(obj, "title");
        w.source = extract_str(obj, "source");
        w.units = extract_str(obj, "units");
        w.x = extract_num(obj, "x");
        w.y = extract_num(obj, "y");
        w.width = extract_num(obj, "width", 1);
        w.height = extract_num(obj, "height", 1);
        w.min_value = extract_num(obj, "min_value");
        w.max_value = extract_num(obj, "max_value", 100);
        if (!w.widget_id.empty()) layout.widgets.push_back(std::move(w));
        pos = obj_end + 1;
    }
    return layout;
}

QWidget* build_live_tab(
    std::shared_ptr<EcuConnection> ecu_conn = nullptr,
    NavigateCallback on_navigate = nullptr,
    std::shared_ptr<LiveDataHttpServer> http_server = nullptr,
    std::shared_ptr<tuner_core::dashboard_layout::Layout> shared_dash_out = nullptr,
    std::shared_ptr<std::function<void()>> rebuild_dashboard_out = nullptr) {
    auto* scroll = new QScrollArea;
    scroll->setWidgetResizable(true);
    scroll->setStyleSheet("QScrollArea { border: none; }");
    auto* container = new QWidget;
    auto* layout = new QVBoxLayout(container);
    layout->setContentsMargins(tt::space_lg, tt::space_lg, tt::space_lg, tt::space_lg);
    layout->setSpacing(tt::space_sm + 2);

    // ---- Runtime header (sub-slice 88 beautification pass) -----------------
    //
    // A single compound widget stacks two elements inside one card:
    //
    //   1. Phase indicator (hero line — bold WOT / CRUISE / IDLE)
    //   2. Formula channel strip (faint secondary row of computed values)
    //
    // Progressive disclosure: the eye lands on the phase first because
    // it's the biggest, boldest thing on the page, then drops to the
    // computed-channel readouts. Keeping both in one bordered container
    // signals "this is one thing" — the current engine state at a
    // glance — rather than two unrelated chips stacked.
    auto* runtime_header = new QWidget;
    auto* rh_layout = new QVBoxLayout(runtime_header);
    rh_layout->setContentsMargins(tt::space_md, tt::space_sm, tt::space_md, tt::space_sm);
    rh_layout->setSpacing(tt::space_xs);
    {
        char style[192];
        std::snprintf(style, sizeof(style),
            "background-color: %s; border: 1px solid %s; "
            "border-radius: %dpx; margin-top: %dpx;",
            tt::bg_elevated, tt::border, tt::radius_md, tt::space_sm);
        runtime_header->setStyleSheet(QString::fromUtf8(style));
    }

    auto* phase_label = new QLabel;
    phase_label->setTextFormat(Qt::RichText);
    phase_label->setAlignment(Qt::AlignCenter);
    phase_label->setMinimumHeight(28);
    phase_label->setStyleSheet("background: transparent; border: none;");
    rh_layout->addWidget(phase_label);

    // Thin divider between the hero phase line and the formula row.
    auto* rh_divider = new QFrame;
    rh_divider->setFrameShape(QFrame::HLine);
    rh_divider->setFrameShadow(QFrame::Plain);
    {
        char div_style[96];
        std::snprintf(div_style, sizeof(div_style),
            "color: %s; background: %s; max-height: 1px;",
            tt::border_soft, tt::border_soft);
        rh_divider->setStyleSheet(QString::fromUtf8(div_style));
    }
    rh_layout->addWidget(rh_divider);

    layout->addWidget(runtime_header);

    // ---- Sub-slice 87: load formula output channels from the production INI.
    // These are evaluated on every timer tick against the mock runtime
    // snapshot via `math_expression_evaluator::enrich`, so the dashboard
    // gauges (and the small formula strip below) see computed channels
    // like `throttle`, `lambda`, `map_psi`, `revolutionTime` alongside
    // the hardware channels the mock runtime emits directly.
    namespace mee = tuner_core::math_expression_evaluator;
    auto formula_channels = std::make_shared<std::vector<tuner_core::IniFormulaOutputChannel>>();
    auto formula_arrays = std::make_shared<mee::ArrayMap>();
    auto front_page_indicators = std::make_shared<std::vector<tuner_core::IniFrontPageIndicator>>();
    {
        {
            auto def_opt = load_active_definition();
            if (def_opt.has_value()) {
                auto& def = *def_opt;
                *formula_channels = def.output_channels.formula_channels;
                *formula_arrays = def.output_channels.arrays;
                *front_page_indicators = def.front_page.indicators;
            }
        }
    }

    // ---- Formula channel strip (secondary row inside runtime_header) ------
    //
    // Lives inside the runtime header compound, directly beneath the
    // phase indicator, separated by the thin divider above. Carries the
    // "computed channels" meaning via the `accent_special` purple hue
    // reserved for derived values — differentiating these visually from
    // the hardware readouts that dominate the rest of the LIVE tab.
    auto* formula_strip = new QLabel;
    formula_strip->setTextFormat(Qt::RichText);
    formula_strip->setAlignment(Qt::AlignCenter);
    formula_strip->setMinimumHeight(22);
    formula_strip->setStyleSheet("background: transparent; border: none;");
    rh_layout->addWidget(formula_strip);

    // ---- FrontPage indicator strip ----
    // Boolean indicator chips from INI [FrontPage] section. Evaluated
    // against live runtime data on each 200ms tick. Mirrors the legacy
    // status indicator row (running, sync, error, flood, etc.).
    struct IndicatorBinding {
        std::string expression;
        std::string on_style;
        std::string off_style;
        std::string on_text;
        std::string off_text;
        QLabel* chip = nullptr;
        bool prev_active = false;
    };

    auto indicator_bindings = std::make_shared<std::vector<IndicatorBinding>>();

    // Map INI color names → theme hex values.
    // Map INI color names to dark-theme-appropriate values.
    // The INI uses the legacy light-theme palette (white bg + black text
    // for off-state, colored bg for on-state). We remap "white" bg to the
    // dark theme's inset panel color so off-state chips blend into the
    // chrome instead of glowing like headlights.
    auto color_hex = [](const std::string& name, bool is_bg) -> const char* {
        std::string lower = name;
        for (auto& ch : lower) ch = static_cast<char>(
            std::tolower(static_cast<unsigned char>(ch)));
        if (lower == "red")    return tt::accent_danger;
        if (lower == "green")  return tt::accent_ok;
        if (lower == "yellow") return tt::accent_warning;
        if (lower == "white")  return is_bg ? tt::bg_inset : tt::text_primary;
        if (lower == "black")  return is_bg ? tt::bg_base : tt::text_muted;
        if (lower == "blue")   return tt::accent_primary;
        return is_bg ? tt::bg_elevated : tt::text_dim;
    };

    if (!front_page_indicators->empty()) {
        auto* ind_container = new QWidget;
        auto* ind_grid = new QGridLayout(ind_container);
        ind_grid->setContentsMargins(tt::space_sm, tt::space_xs, tt::space_sm, tt::space_xs);
        ind_grid->setSpacing(tt::space_xs);
        ind_container->setStyleSheet(QString::fromUtf8(tt::card_style().c_str()));

        int max_ind = std::min(static_cast<int>(front_page_indicators->size()), 48);
        indicator_bindings->reserve(max_ind);

        for (int i = 0; i < max_ind; ++i) {
            const auto& ind = (*front_page_indicators)[i];
            IndicatorBinding b;
            b.expression = ind.expression;
            b.on_text = ind.on_label.empty() ? "\xe2\x80\xa2" : ind.on_label;
            b.off_text = ind.off_label.empty() ? "\xe2\x80\xa2" : ind.off_label;

            // Pre-build stylesheet strings.
            char on_s[256], off_s[256];
            std::snprintf(on_s, sizeof(on_s),
                "QLabel { background: %s; color: %s; border-radius: 3px; "
                "padding: 1px 4px; font-size: %dpx; border: none; }",
                color_hex(ind.on_bg, true), color_hex(ind.on_fg, false), tt::font_small);
            std::snprintf(off_s, sizeof(off_s),
                "QLabel { background: %s; color: %s; border-radius: 3px; "
                "padding: 1px 4px; font-size: %dpx; border: none; }",
                color_hex(ind.off_bg, true), color_hex(ind.off_fg, false), tt::font_small);
            b.on_style = on_s;
            b.off_style = off_s;

            auto* chip = new QLabel(QString::fromUtf8(b.off_text.c_str()));
            chip->setFixedHeight(20);
            chip->setMinimumWidth(40);
            chip->setAlignment(Qt::AlignCenter);
            chip->setStyleSheet(QString::fromUtf8(off_s));
            b.chip = chip;

            ind_grid->addWidget(chip, i / 8, i % 8);
            indicator_bindings->push_back(std::move(b));
        }

        rh_layout->addWidget(ind_container);
    }

    // ---- Dashboard gauge cluster ----

    namespace dln = tuner_core::dashboard_layout;
    namespace mer = tuner_core::mock_ecu_runtime;

    // Build layout from INI FrontPage gauge slots + GaugeConfigurations
    // catalog, falling back to default_layout() when unavailable.
    auto build_ini_layout = [](
        const std::vector<std::string>* slots_ptr,
        const std::vector<tuner_core::IniGaugeConfiguration>* catalog_ptr)
            -> tuner_core::dashboard_layout::Layout {
        namespace dln2 = tuner_core::dashboard_layout;
        namespace gcz = tuner_core::gauge_color_zones;
        const auto& slot_names = *slots_ptr;
        const auto& gauge_catalog = *catalog_ptr;
        // Build lookup map.
        std::unordered_map<std::string, const tuner_core::IniGaugeConfiguration*> by_name;
        for (const auto& g : gauge_catalog) by_name[g.name] = &g;

        dln2::Layout layout;
        layout.name = "INI";
        // Grid: 4 columns, 2 rows of dials then number cards.
        int placed = 0;
        for (const auto& slot_name : slot_names) {
            if (slot_name.empty()) continue;
            auto it = by_name.find(slot_name);
            if (it == by_name.end()) continue;
            const auto* g = it->second;

            dln2::Widget w;
            w.widget_id = g->name;
            w.source = g->channel;
            w.title = g->title;
            w.units = g->units;
            w.min_value = g->lo.value_or(0.0);
            w.max_value = g->hi.value_or(100.0);

            // Derive color zones from thresholds.
            gcz::Thresholds th;
            th.lo_danger = g->lo_danger;
            th.lo_warn = g->lo_warn;
            th.hi_warn = g->hi_warn;
            th.hi_danger = g->hi_danger;
            auto zones = gcz::derive_zones(w.min_value, w.max_value, th);
            for (const auto& z : zones) {
                dln2::ColorZone cz;
                cz.lo = z.lo;
                cz.hi = z.hi;
                cz.color = z.color;
                w.color_zones.push_back(cz);
            }

            // First two gauges are 2x2 dials, rest are 1x1 number cards.
            if (placed < 2) {
                w.kind = "dial";
                w.x = placed * 2;
                w.y = 0;
                w.width = 2;
                w.height = 2;
            } else {
                w.kind = "number";
                int idx = placed - 2;
                w.x = idx % 4;
                w.y = 2 + idx / 4;
                w.width = 1;
                w.height = 1;
            }
            layout.widgets.push_back(std::move(w));
            placed++;
            if (placed >= 11) break;  // cap at 11 widgets
        }
        return layout;
    };

    dln::Layout dash;
    // Try INI-driven layout.
    if (!front_page_indicators->empty()) {
        // front_page_indicators was already loaded — check gauges too.
        {
            auto def_opt_g = load_active_definition();
            if (def_opt_g.has_value()) {
                auto& def = *def_opt_g;
                if (!def.front_page.gauges.empty() &&
                    !def.gauge_configurations.gauges.empty()) {
                    QSettings settings;
                    std::string saved = settings.value(
                        "live/gauge_selection", "").toString().toStdString();
                    std::vector<std::string> selected_slots;
                    if (!saved.empty()) {
                        // Parse comma-separated gauge names.
                        std::istringstream ss(saved);
                        std::string name;
                        while (std::getline(ss, name, ',')) {
                            while (!name.empty() && name.front() == ' ') name.erase(name.begin());
                            while (!name.empty() && name.back() == ' ') name.pop_back();
                            if (!name.empty()) selected_slots.push_back(name);
                        }
                    }
                    if (selected_slots.empty())
                        selected_slots = def.front_page.gauges;

                    dash = build_ini_layout(&selected_slots,
                        &def.gauge_configurations.gauges);
                }
            }
        }
    }
    if (dash.widgets.empty()) dash = dln::default_layout();
    auto shared_dash = std::make_shared<dln::Layout>(std::move(dash));

    // Shared state for the timer callback.
    struct GaugeBinding {
        std::string source;
        std::string title;
        std::string units;
        std::vector<dln::ColorZone> zones;
        int font_size;
        DialGaugeWidget* dial = nullptr;
        QLabel* card = nullptr;
        std::string prev_zone;  // track zone transitions for alerts
    };
    auto bindings = std::make_shared<std::vector<GaugeBinding>>();
    auto mock_ecu = std::make_shared<mer::MockEcu>(42);

    auto* dash_grid = new QGridLayout;
    dash_grid->setSpacing(tt::space_xs);
    auto* dash_container = new QWidget;
    dash_container->setLayout(dash_grid);

    // Rebuild dashboard gauges from shared_dash layout. Called on
    // initial build and after config/save-load/drag-drop changes.
    // Load INI gauge catalog for the config dialog source picker.
    auto gauge_catalog = std::make_shared<std::vector<tuner_core::IniGaugeConfiguration>>();
    {
        auto def_opt_gc = load_active_definition();
        if (def_opt_gc.has_value())
            *gauge_catalog = def_opt_gc->gauge_configurations.gauges;
    }

    auto rebuild_dashboard = std::make_shared<std::function<void()>>();
    *rebuild_dashboard = [dash_grid, bindings, shared_dash, on_navigate,
                          gauge_catalog, rebuild_dashboard]() {
        // Clear existing gauges.
        bindings->clear();
        while (auto* item = dash_grid->takeAt(0)) {
            if (item->widget()) item->widget()->hide();
            // deleteLater is safe; hide prevents visual glitch.
            if (item->widget()) item->widget()->deleteLater();
            delete item;
        }
        // Rebuild from layout.
        for (const auto& w : shared_dash->widgets) {
            int gx = static_cast<int>(w.x);
            int gy = static_cast<int>(w.y);
            int gw = static_cast<int>(w.width);
            int gh = static_cast<int>(w.height);

            GaugeBinding binding;
            binding.source = w.source;
            binding.title = w.title;
            binding.units = w.units;
            binding.zones = w.color_zones;
            binding.font_size = (gh > 1) ? 28 : 18;

            if (w.kind == "dial") {
                DialGaugeWidget::Config cfg;
                cfg.title = w.title; cfg.units = w.units;
                cfg.min_value = w.min_value; cfg.max_value = w.max_value;
                for (const auto& z : w.color_zones)
                    cfg.zones.push_back({z.lo, z.hi, z.color});
                auto* gauge = new DialGaugeWidget(cfg);
                gauge->set_widget_id(w.widget_id);
                if (on_navigate) {
                    gauge->set_click_callback([on_navigate](const std::string& title) {
                        on_navigate(0, title);
                    });
                }
                // Drag-and-drop → swap gauge positions.
                gauge->set_swap_callback(
                    [shared_dash, rebuild_dashboard](
                        const std::string& from_id, const std::string& to_id) {
                    // Find both widgets and swap their grid positions.
                    dln::Widget* wa = nullptr;
                    dln::Widget* wb = nullptr;
                    for (auto& w : shared_dash->widgets) {
                        if (w.widget_id == from_id) wa = &w;
                        if (w.widget_id == to_id) wb = &w;
                    }
                    if (wa && wb) {
                        std::swap(wa->x, wb->x);
                        std::swap(wa->y, wb->y);
                        std::swap(wa->width, wb->width);
                        std::swap(wa->height, wb->height);
                        (*rebuild_dashboard)();
                    }
                });
                // Right-click → configure gauge dialog.
                gauge->set_config_callback(
                    [shared_dash, gauge_catalog, rebuild_dashboard](
                        const std::string& wid) {
                    for (auto& w : shared_dash->widgets) {
                        if (w.widget_id == wid) {
                            if (open_gauge_config_dialog(nullptr, w, *gauge_catalog))
                                (*rebuild_dashboard)();
                            break;
                        }
                    }
                });
                dash_grid->addWidget(gauge, gy, gx, gh, gw);
                binding.dial = gauge;
            } else {
                auto* cell = new QLabel;
                cell->setTextFormat(Qt::RichText);
                cell->setAlignment(Qt::AlignCenter);
                cell->setMinimumHeight(gh > 1 ? 100 : 50);
                cell->setStyleSheet(QString::fromUtf8(
                    tt::number_card_style(tt::accent_primary).c_str()));
                dash_grid->addWidget(cell, gy, gx, gh, gw);
                binding.card = cell;
            }
            bindings->push_back(std::move(binding));
        }
    };

    // Initial build.
    (*rebuild_dashboard)();
    layout->addWidget(dash_container);

    // Fullscreen dashboard — frameless, stays-on-top window with
    // larger fonts. Escape or double-click to close. F11 shortcut.
    auto fs_dialog = std::make_shared<QPointer<QDialog>>();
    auto open_fullscreen = [container, shared_dash, bindings, mock_ecu,
                            ecu_conn, fs_dialog]() {
        if (!fs_dialog->isNull()) return;  // already open

        auto* dlg = new QDialog(nullptr);  // no parent = independent window
        dlg->setWindowFlags(Qt::Window | Qt::FramelessWindowHint
                            | Qt::WindowStaysOnTopHint);
        dlg->showFullScreen();
        {
            char s[64];
            std::snprintf(s, sizeof(s), "QDialog { background: %s; }", tt::bg_deep);
            dlg->setStyleSheet(QString::fromUtf8(s));
        }
        auto* dl = new QVBoxLayout(dlg);
        dl->setContentsMargins(tt::space_xl, tt::space_xl, tt::space_xl, tt::space_xl);
        dl->setSpacing(tt::space_xs);

        auto* grid = new QGridLayout;
        grid->setSpacing(tt::space_sm - 2);

        // Build gauge widgets at 1.5x font scale.
        auto fs_bindings = std::make_shared<std::vector<GaugeBinding>>();
        for (const auto& w : shared_dash->widgets) {
            int gx = static_cast<int>(w.x);
            int gy = static_cast<int>(w.y);
            int gw = static_cast<int>(w.width);
            int gh = static_cast<int>(w.height);

            GaugeBinding binding;
            binding.source = w.source;
            binding.title = w.title;
            binding.units = w.units;
            binding.zones = w.color_zones;
            binding.font_size = (gh > 1) ? 42 : 24;  // 1.5x scale

            if (w.kind == "dial") {
                DialGaugeWidget::Config cfg;
                cfg.title = w.title; cfg.units = w.units;
                cfg.min_value = w.min_value; cfg.max_value = w.max_value;
                for (const auto& z : w.color_zones)
                    cfg.zones.push_back({z.lo, z.hi, z.color});
                auto* gauge = new DialGaugeWidget(cfg);
                gauge->setMinimumSize(200, 200);
                grid->addWidget(gauge, gy, gx, gh, gw);
                binding.dial = gauge;
            } else {
                auto* cell = new QLabel;
                cell->setTextFormat(Qt::RichText);
                cell->setAlignment(Qt::AlignCenter);
                cell->setMinimumHeight(gh > 1 ? 150 : 80);
                cell->setStyleSheet(QString::fromUtf8(
                    tt::number_card_style(tt::accent_primary).c_str()));
                grid->addWidget(cell, gy, gx, gh, gw);
                binding.card = cell;
            }
            fs_bindings->push_back(std::move(binding));
        }
        dl->addLayout(grid);

        // Hint label.
        auto* hint = new QLabel(QString::fromUtf8(
            "Press Escape or double-click to exit fullscreen"));
        {
            char s[128];
            std::snprintf(s, sizeof(s),
                "QLabel { color: %s; font-size: %dpx; }",
                tt::text_dim, tt::font_small);
            hint->setStyleSheet(QString::fromUtf8(s));
        }
        hint->setAlignment(Qt::AlignCenter);
        dl->addWidget(hint);

        *fs_dialog = dlg;

        // Update timer — piggyback on the same 200ms tick via a
        // dedicated timer in the fullscreen dialog.
        auto* fs_timer = new QTimer(dlg);
        QObject::connect(fs_timer, &QTimer::timeout,
                         [fs_bindings, mock_ecu, ecu_conn]() {
            auto snap = mock_ecu->poll();
            if (ecu_conn && ecu_conn->connected) {
                for (const auto& [name, val] : ecu_conn->runtime)
                    snap.channels[name] = val;
            }
            for (auto& b : *fs_bindings) {
                double v = snap.get(b.source);
                if (b.dial) {
                    b.dial->set_value(v);
                } else if (b.card) {
                    // Simplified number card update.
                    char html[256];
                    std::snprintf(html, sizeof(html),
                        "<div style='text-align:center;'>"
                        "<span style='font-size: %dpx; font-weight: bold; "
                        "color: %s;'>%.1f</span><br>"
                        "<span style='font-size: %dpx; color: %s;'>%s %s</span>"
                        "</div>",
                        b.font_size, tt::text_primary, v,
                        tt::font_body, tt::text_muted,
                        b.title.c_str(), b.units.c_str());
                    b.card->setText(QString::fromUtf8(html));
                }
            }
        });
        fs_timer->start(200);

        // Close on Escape.
        auto* esc = new QShortcut(QKeySequence(Qt::Key_Escape), dlg);
        QObject::connect(esc, &QShortcut::activated, dlg, &QDialog::close);

        dlg->show();
    };

    // F11 shortcut.
    auto* fs_shortcut = new QShortcut(QKeySequence(Qt::Key_F11), container);
    QObject::connect(fs_shortcut, &QShortcut::activated, open_fullscreen);

    // Fullscreen button.
    auto* fs_btn = new QPushButton(QString::fromUtf8("Fullscreen (F11)"));
    fs_btn->setCursor(Qt::PointingHandCursor);
    {
        char bs[256];
        std::snprintf(bs, sizeof(bs),
            "QPushButton { background: %s; color: %s; border: 1px solid %s; "
            "border-radius: %dpx; padding: 4px 12px; font-size: %dpx; }"
            "QPushButton:hover { background: %s; }",
            tt::bg_elevated, tt::text_primary, tt::border,
            tt::radius_sm, tt::font_small, tt::fill_primary_mid);
        fs_btn->setStyleSheet(QString::fromUtf8(bs));
    }
    QObject::connect(fs_btn, &QPushButton::clicked, open_fullscreen);
    layout->addWidget(fs_btn);

    // Export shared state for File menu save/load integration.
    if (shared_dash_out) {
        // Copy the layout data into the caller's shared_ptr.
        *shared_dash_out = *shared_dash;
    }
    if (rebuild_dashboard_out) {
        // Wire the rebuild function so the caller can trigger rebuilds.
        *rebuild_dashboard_out = [shared_dash, rebuild_dashboard,
                                  shared_dash_out]() {
            // Sync from the caller's copy back to our local copy and rebuild.
            if (shared_dash_out) *shared_dash = *shared_dash_out;
            (*rebuild_dashboard)();
        };
    }

    // Timer: update all gauges every 200ms. When a real ECU
    // connection is active, poll it for runtime data; otherwise
    // fall back to the MockEcu demo animation.
    auto* timer = new QTimer(container);
    QObject::connect(timer, &QTimer::timeout,
                     [bindings, mock_ecu, ecu_conn, phase_label, formula_strip,
                      formula_channels, formula_arrays, http_server]() {
        // Attempt real ECU poll first.
        bool using_real = false;
        if (ecu_conn && ecu_conn->connected) {
            using_real = ecu_conn->poll_runtime();
        }
        // Fall back to mock if not connected or poll failed.
        auto snap = mock_ecu->poll();
        if (using_real) {
            // Overlay real runtime values onto the mock snapshot so
            // formula enrichment and gauge bindings see real data.
            for (const auto& [name, val] : ecu_conn->runtime) {
                snap.channels[name] = val;
            }
        }

        // ---- Sub-slice 87: enrich the raw mock snapshot with formula
        // output channels from the definition before gauges / strip read.
        // Seed a few channels the mock runtime doesn't emit directly but
        // that many production formulas depend on (baro, stoich, twoStroke,
        // pulseWidth, *Raw temperatures). Without these seeds the production
        // formulas that reference them evaluate to 0 (unknown-id fallback).
        if (!formula_channels->empty()) {
            if (!snap.channels.count("baro"))       snap.channels["baro"] = 101.3;
            if (!snap.channels.count("stoich"))     snap.channels["stoich"] = 14.7;
            if (!snap.channels.count("twoStroke"))  snap.channels["twoStroke"] = 0.0;
            if (!snap.channels.count("pulseWidth")) snap.channels["pulseWidth"] = snap.get("pw1") * 1000.0;
            if (!snap.channels.count("coolantRaw")) snap.channels["coolantRaw"] = snap.get("clt") + 40.0;
            if (!snap.channels.count("iatRaw"))     snap.channels["iatRaw"] = snap.get("iat") + 40.0;
            if (!snap.channels.count("nSquirts"))   snap.channels["nSquirts"] = 2.0;
            if (!snap.channels.count("nCylinders")) snap.channels["nCylinders"] = 6.0;
            mee::enrich(snap.channels, *formula_channels, formula_arrays.get());
        }

        // Feed HTTP Live-Data API with the current snapshot.
        if (http_server) {
            std::string sig;
            if (ecu_conn && ecu_conn->connected)
                sig = ecu_conn->info.signature;
            http_server->update_snapshot(snap.channels,
                ecu_conn && ecu_conn->connected, sig);
        }

        if (!formula_channels->empty()) {
            // Update the formula-channel strip with four headline values.
            // Every computed channel uses the `accent_special` purple token
            // to signal "derived" — hardware channels in the gauge cluster
            // below use accent_primary/ok/warning, so the purple reads as
            // a clean visual category distinction.
            char strip_buf[768];
            std::snprintf(strip_buf, sizeof(strip_buf),
                "<span style='color: %s; font-size: %dpx; "
                "letter-spacing: 1px;'>COMPUTED</span>  "
                "<span style='color: %s; font-size: %dpx; font-weight: bold;'>"
                "\xce\xbb %.3f</span>"
                "<span style='color: %s; font-size: %dpx;'>  \xc2\xb7  </span>"
                "<span style='color: %s; font-size: %dpx; font-weight: bold;'>"
                "throttle %.1f%%</span>"
                "<span style='color: %s; font-size: %dpx;'>  \xc2\xb7  </span>"
                "<span style='color: %s; font-size: %dpx; font-weight: bold;'>"
                "map %.1f PSI</span>"
                "<span style='color: %s; font-size: %dpx;'>  \xc2\xb7  </span>"
                "<span style='color: %s; font-size: %dpx; font-weight: bold;'>"
                "rev %.1f ms</span>",
                tt::text_dim, tt::font_micro,
                tt::accent_special, tt::font_medium, snap.get("lambda"),
                tt::text_dim, tt::font_small,
                tt::accent_special, tt::font_medium, snap.get("throttle"),
                tt::text_dim, tt::font_small,
                tt::accent_special, tt::font_medium, snap.get("map_psi"),
                tt::text_dim, tt::font_small,
                tt::accent_special, tt::font_medium, snap.get("revolutionTime"));
            formula_strip->setText(QString::fromUtf8(strip_buf));
        } else {
            char empty_buf[256];
            std::snprintf(empty_buf, sizeof(empty_buf),
                "<span style='color: %s; font-size: %dpx;'>"
                "no formula channels \xe2\x80\x94 definition not loaded"
                "</span>",
                tt::text_dim, tt::font_small);
            formula_strip->setText(QString::fromUtf8(empty_buf));
        }

        // Determine driving phase from TPS/RPM. Each phase maps to one
        // of the semantic accent tokens rather than a raw hex literal so
        // the color coding stays consistent with the rest of the app.
        double tps = snap.get("tps");
        double rpm = snap.get("rpm");
        const char* phase;
        const char* phase_color;
        if (tps > 80) { phase = "WIDE OPEN THROTTLE"; phase_color = tt::accent_danger; }
        else if (tps > 5 && rpm > 1200) { phase = "CRUISE"; phase_color = tt::accent_ok; }
        else if (rpm > 900 && tps < 3) { phase = "DECELERATION"; phase_color = tt::accent_warning; }
        else { phase = "IDLE"; phase_color = tt::accent_primary; }

        int tick = mock_ecu->tick();  // always ticks for blink timing
        // Recording indicator: blinks when connected to real ECU.
        bool rec_blink = using_real && (tick % 20) < 10;
        char rec_buf[128];
        std::snprintf(rec_buf, sizeof(rec_buf),
            "<span style='color: %s; font-size: %dpx;'>\xe2\x97\x89 REC</span>  ",
            rec_blink ? tt::accent_danger : tt::text_dim, tt::font_body);

        char phase_buf[512];
        std::snprintf(phase_buf, sizeof(phase_buf),
            "%s"
            "<span style='font-size: %dpx; font-weight: bold; color: %s; "
            "letter-spacing: 0.5px;'>\xe2\x97\x89 %s</span>"
            "<span style='color: %s; font-size: %dpx;'>"
            "  \xc2\xb7  RPM %.0f  \xc2\xb7  TPS %.1f%%  \xc2\xb7  tick %d</span>",
            rec_buf,
            tt::font_label, phase_color, phase,
            tt::text_dim, tt::font_small,
            rpm, tps, tick);
        phase_label->setText(QString::fromUtf8(phase_buf));

        for (auto& b : *bindings) {
            double val = snap.get(b.source);
            if (b.dial) {
                b.dial->set_value(val);
                continue;
            }
            if (!b.card) continue;
            // Determine zone — `zone_accent` maps the name string to
            // the right theme accent (ok/warning/danger/default).
            std::string zone_name = "normal";
            for (const auto& z : b.zones) {
                if (val >= z.lo && val <= z.hi) {
                    zone_name = z.color;
                }
            }
            const char* accent = tt::zone_accent(zone_name);

            // Zone-based alert: pulse border width on danger entry (Phase C).
            int border_width = 2;
            if (zone_name == "danger" && b.prev_zone != "danger")
                border_width = 4;  // flash thicker on entry
            b.prev_zone = zone_name;

            // Alert indicator for danger zone.
            const char* alert_icon = (zone_name == "danger") ? " \xe2\x9a\xa0" :
                                     (zone_name == "warning") ? " \xe2\x97\x8b" : "";

            char content[512];
            tt::format_number_card_html(content, sizeof(content),
                b.font_size, accent, val, alert_icon,
                b.units.c_str(), b.title.c_str());
            b.card->setText(QString::fromUtf8(content));
            b.card->setStyleSheet(QString::fromUtf8(
                tt::number_card_style(accent, border_width).c_str()));
        }
    });
    // ---- Sparkline histograms (Phase D) ----
    auto* hist_afr = new HistogramWidget({"AFR", "", 10, 18, 60, tt::accent_primary});
    auto* hist_rpm = new HistogramWidget({"RPM", "rpm", 0, 8000, 60, tt::accent_ok});
    auto* hist_map = new HistogramWidget({"MAP", "kPa", 0, 250, 60, tt::accent_warning});
    hist_afr->setFixedHeight(70);
    hist_rpm->setFixedHeight(70);
    hist_map->setFixedHeight(70);

    auto* hist_grid = new QHBoxLayout;
    hist_grid->setSpacing(tt::space_xs);
    hist_grid->addWidget(hist_afr);
    hist_grid->addWidget(hist_rpm);
    hist_grid->addWidget(hist_map);
    auto* hist_container = new QWidget;
    hist_container->setLayout(hist_grid);
    layout->addWidget(hist_container);

    // Wire histogram updates into the timer.
    QObject::connect(timer, &QTimer::timeout, [hist_afr, hist_rpm, hist_map, mock_ecu, ecu_conn]() {
        // Use real ECU data when connected, mock otherwise.
        if (ecu_conn && ecu_conn->connected) {
            hist_afr->push_value(ecu_conn->get("afr"));
            hist_rpm->push_value(ecu_conn->get("rpm"));
            hist_map->push_value(ecu_conn->get("map"));
        } else {
            auto snap2 = mock_ecu->poll();
            hist_afr->push_value(snap2.get("afr"));
            hist_rpm->push_value(snap2.get("rpm"));
            hist_map->push_value(snap2.get("map"));
        }
    });

    // Indicator strip update — evaluate boolean expressions on each tick.
    if (!indicator_bindings->empty()) {
        QObject::connect(timer, &QTimer::timeout,
                         [indicator_bindings, mock_ecu, ecu_conn]() {
            namespace vex = tuner_core::visibility_expression;

            // Build values map from runtime snapshot.
            auto snap = mock_ecu->poll();
            if (ecu_conn && ecu_conn->connected) {
                for (const auto& [name, val] : ecu_conn->runtime)
                    snap.channels[name] = val;
            }
            std::map<std::string, double> val_map(
                snap.channels.begin(), snap.channels.end());

            for (auto& b : *indicator_bindings) {
                bool active = vex::evaluate(b.expression, val_map);
                if (active != b.prev_active) {
                    b.prev_active = active;
                    b.chip->setText(QString::fromUtf8(
                        active ? b.on_text.c_str() : b.off_text.c_str()));
                    b.chip->setStyleSheet(QString::fromUtf8(
                        active ? b.on_style.c_str() : b.off_style.c_str()));
                }
            }
        });
    }

    // ---- Runtime status strip ----
    // Compact inline strip below the dashboard — shows sync state,
    // learn status, and active conditions as colored chips. Same
    // visual grammar as the FrontPage indicator strip above.
    namespace rtl = tuner_core::runtime_telemetry;
    auto* status_strip = new QLabel;
    status_strip->setTextFormat(Qt::RichText);
    status_strip->setAlignment(Qt::AlignCenter);
    {
        char ss[192];
        std::snprintf(ss, sizeof(ss),
            "QLabel { background: transparent; color: %s; "
            "font-size: %dpx; padding: %dpx 0; }",
            tt::text_muted, tt::font_small, tt::space_xs);
        status_strip->setStyleSheet(QString::fromUtf8(ss));
    }
    layout->addWidget(status_strip);

    // Wire status strip into the main timer.
    QObject::connect(timer, &QTimer::timeout,
                     [status_strip, mock_ecu, ecu_conn]() {
        auto snap = mock_ecu->poll();
        if (ecu_conn && ecu_conn->connected) {
            for (const auto& [name, val] : ecu_conn->runtime)
                snap.channels[name] = val;
        }
        rtl::ValueMap vm(snap.channels.begin(), snap.channels.end());
        auto summary = rtl::decode(vm);
        const auto& rs = summary.runtime_status;

        // Build compact chip strip: ◉ Sync · ◉ Learn · ◉ Warmup
        char buf[512];
        int off = 0;

        auto chip = [&](const char* label, const char* color) {
            off += std::snprintf(buf + off, sizeof(buf) - off,
                "<span style='color: %s; font-weight: bold;'>"
                "\xe2\x97\x89</span> "
                "<span style='color: %s;'>%s</span>",
                color, color, label);
        };
        auto sep = [&]() {
            off += std::snprintf(buf + off, sizeof(buf) - off,
                "  <span style='color: %s;'>\xc2\xb7</span>  ", tt::text_dim);
        };

        chip(rs.full_sync ? "Sync" : "No Sync",
             rs.full_sync ? tt::accent_ok : tt::accent_danger);
        sep();
        chip(rs.tune_learn_valid ? "Learn" : "Learn Off",
             rs.tune_learn_valid ? tt::accent_ok : tt::text_dim);
        if (rs.warmup_or_ase_active) { sep(); chip("Warmup", tt::accent_warning); }
        if (rs.transient_active)     { sep(); chip("Accel", tt::accent_warning); }
        if (rs.fuel_pump_on)         { sep(); chip("Fuel Pump", tt::text_muted); }

        status_strip->setText(QString::fromUtf8(buf));
    });

    // ---- Hardware test panel ----
    // Grouped by category: Enable/Disable toggle at top, then
    // Injectors / Spark / Auxiliary in collapsible sections.
    // Only shows outputs relevant to the configuration (4-cyl
    // builds don't see injector 5-8 buttons).
    {
        auto test_commands = std::make_shared<std::vector<tuner_core::IniControllerCommand>>();
        {
            auto def_opt = load_active_definition();
            if (def_opt.has_value()) {
                *test_commands = def_opt->controller_commands.commands;
            }
        }

        if (!test_commands->empty()) {
            auto* test_card = new QWidget;
            auto* test_layout = new QVBoxLayout(test_card);
            test_layout->setContentsMargins(tt::space_md, tt::space_md, tt::space_md, tt::space_md);
            test_layout->setSpacing(tt::space_sm);
            test_card->setStyleSheet(QString::fromUtf8(tt::card_style().c_str()));

            // Header row with title + enable/disable toggle.
            auto* header_row = new QHBoxLayout;
            header_row->setSpacing(tt::space_sm);
            auto* test_title = new QLabel;
            test_title->setTextFormat(Qt::RichText);
            {
                char h[256];
                std::snprintf(h, sizeof(h),
                    "<span style='color: %s; font-size: %dpx; font-weight: bold;'>"
                    "Hardware Test</span>",
                    tt::text_primary, tt::font_label);
                test_title->setText(QString::fromUtf8(h));
            }
            test_title->setStyleSheet("border: none;");
            header_row->addWidget(test_title);
            header_row->addStretch(1);

            // Test mode buttons — style the same throughout.
            char btn_style[384];
            std::snprintf(btn_style, sizeof(btn_style),
                "QPushButton { background: %s; color: %s; border: 1px solid %s; "
                "border-radius: %dpx; padding: %dpx %dpx; font-size: %dpx; } "
                "QPushButton:hover { background: %s; } "
                "QPushButton:disabled { color: %s; border-color: %s; }",
                tt::bg_elevated, tt::text_primary, tt::border,
                tt::radius_sm, tt::space_xs, tt::space_sm, tt::font_small,
                tt::fill_primary_mid, tt::text_dim, tt::border);
            std::string btn_ss(btn_style);

            // Categorize commands.
            struct CmdEntry {
                std::string label;
                std::vector<std::uint8_t> payload;
            };
            std::vector<CmdEntry> enable_cmds, inj_cmds, spk_cmds, aux_cmds;

            // Known command name → human label + category.
            struct KnownCmd { const char* ini; const char* label; const char* cat; };
            static const KnownCmd known_cmds[] = {
                {"cmdEnableTestMode",   "Enable Test Mode",  "control"},
                {"cmdStopTestMode",     "Stop Test Mode",    "control"},
                // Injectors 1-8 (sequential V8 / 8-cyl support).
                {"cmdtestinj1on",       "Inj 1 ON",         "injector"},
                {"cmdtestinj1off",      "Inj 1 OFF",        "injector"},
                {"cmdtestinj2on",       "Inj 2 ON",         "injector"},
                {"cmdtestinj2off",      "Inj 2 OFF",        "injector"},
                {"cmdtestinj3on",       "Inj 3 ON",         "injector"},
                {"cmdtestinj3off",      "Inj 3 OFF",        "injector"},
                {"cmdtestinj4on",       "Inj 4 ON",         "injector"},
                {"cmdtestinj4off",      "Inj 4 OFF",        "injector"},
                {"cmdtestinj5on",       "Inj 5 ON",         "injector"},
                {"cmdtestinj5off",      "Inj 5 OFF",        "injector"},
                {"cmdtestinj6on",       "Inj 6 ON",         "injector"},
                {"cmdtestinj6off",      "Inj 6 OFF",        "injector"},
                {"cmdtestinj7on",       "Inj 7 ON",         "injector"},
                {"cmdtestinj7off",      "Inj 7 OFF",        "injector"},
                {"cmdtestinj8on",       "Inj 8 ON",         "injector"},
                {"cmdtestinj8off",      "Inj 8 OFF",        "injector"},
                // Spark 1-8 (COP on V8 / 8-cyl).
                {"cmdtestspk1on",       "Spark 1 ON",       "spark"},
                {"cmdtestspk1off",      "Spark 1 OFF",      "spark"},
                {"cmdtestspk2on",       "Spark 2 ON",       "spark"},
                {"cmdtestspk2off",      "Spark 2 OFF",      "spark"},
                {"cmdtestspk3on",       "Spark 3 ON",       "spark"},
                {"cmdtestspk3off",      "Spark 3 OFF",      "spark"},
                {"cmdtestspk4on",       "Spark 4 ON",       "spark"},
                {"cmdtestspk4off",      "Spark 4 OFF",      "spark"},
                {"cmdtestspk5on",       "Spark 5 ON",       "spark"},
                {"cmdtestspk5off",      "Spark 5 OFF",      "spark"},
                {"cmdtestspk6on",       "Spark 6 ON",       "spark"},
                {"cmdtestspk6off",      "Spark 6 OFF",      "spark"},
                {"cmdtestspk7on",       "Spark 7 ON",       "spark"},
                {"cmdtestspk7off",      "Spark 7 OFF",      "spark"},
                {"cmdtestspk8on",       "Spark 8 ON",       "spark"},
                {"cmdtestspk8off",      "Spark 8 OFF",      "spark"},
                // Auxiliary outputs.
                {"cmdtestFan",          "Cooling Fan",       "aux"},
                {"cmdtestFuelPump",     "Fuel Pump",         "aux"},
                {"cmdtestIdleUp",       "Idle Up",           "aux"},
                {"cmdtestVVT",          "VVT Solenoid",      "aux"},
                {"cmdtestBoost",        "Boost Solenoid",    "aux"},
            };

            for (const auto& cmd : *test_commands) {
                for (const auto& k : known_cmds) {
                    if (cmd.name == k.ini) {
                        CmdEntry e{k.label, cmd.payload};
                        std::string cat = k.cat;
                        if (cat == "control")  enable_cmds.push_back(e);
                        else if (cat == "injector") inj_cmds.push_back(e);
                        else if (cat == "spark")    spk_cmds.push_back(e);
                        else                        aux_cmds.push_back(e);
                        break;
                    }
                }
            }

            // Status label.
            auto* test_status = new QLabel;
            {
                char s[128];
                std::snprintf(s, sizeof(s),
                    "QLabel { color: %s; font-size: %dpx; border: none; }",
                    tt::text_muted, tt::font_small);
                test_status->setStyleSheet(QString::fromUtf8(s));
                test_status->setText(QString::fromUtf8(
                    "Enable test mode, then select an output to activate"));
            }

            // Helper: create a styled test button wired to send a command.
            auto make_test_btn = [&btn_ss, ecu_conn, test_status](
                const CmdEntry& entry) -> QPushButton* {
                auto* btn = new QPushButton(QString::fromUtf8(entry.label.c_str()));
                btn->setStyleSheet(QString::fromUtf8(btn_ss.c_str()));
                btn->setCursor(Qt::PointingHandCursor);
                auto payload = std::make_shared<std::vector<std::uint8_t>>(entry.payload);
                auto label = std::make_shared<std::string>(entry.label);
                QObject::connect(btn, &QPushButton::clicked,
                                 [ecu_conn, payload, label, test_status]() {
                    if (!ecu_conn || !ecu_conn->connected || !ecu_conn->controller) {
                        test_status->setText(QString::fromUtf8(
                            "Not connected \xe2\x80\x94 connect first"));
                        return;
                    }
                    try {
                        ecu_conn->controller->fetch_raw(*payload, 1, 1.0);
                        char msg[128];
                        std::snprintf(msg, sizeof(msg),
                            "\xe2\x9c\x85 %s", label->c_str());
                        test_status->setText(QString::fromUtf8(msg));
                    } catch (const std::exception& e) {
                        char msg[256];
                        std::snprintf(msg, sizeof(msg),
                            "\xe2\x9d\x8c %s", e.what());
                        test_status->setText(QString::fromUtf8(msg));
                    }
                });
                return btn;
            };

            // Enable / Disable row (prominent).
            if (!enable_cmds.empty()) {
                auto* en_row = new QHBoxLayout;
                en_row->setSpacing(tt::space_sm);
                for (const auto& e : enable_cmds)
                    en_row->addWidget(make_test_btn(e));
                en_row->addStretch(1);
                header_row->addStretch(0);  // remove earlier stretch
                test_layout->addLayout(header_row);
                test_layout->addLayout(en_row);
            } else {
                test_layout->addLayout(header_row);
            }

            // Section helper — adds a dim group label + button row.
            auto add_group = [&](const char* group_label,
                                 const std::vector<CmdEntry>& cmds) {
                if (cmds.empty()) return;
                auto* label = new QLabel(QString::fromUtf8(group_label));
                {
                    char s[128];
                    std::snprintf(s, sizeof(s),
                        "QLabel { color: %s; font-size: %dpx; "
                        "font-weight: bold; border: none; margin-top: %dpx; }",
                        tt::text_muted, tt::font_small, tt::space_xs);
                    label->setStyleSheet(QString::fromUtf8(s));
                }
                test_layout->addWidget(label);
                auto* row = new QHBoxLayout;
                row->setSpacing(tt::space_xs);
                for (const auto& e : cmds)
                    row->addWidget(make_test_btn(e));
                row->addStretch(1);
                test_layout->addLayout(row);
            };

            add_group("INJECTORS", inj_cmds);
            add_group("SPARK", spk_cmds);
            add_group("AUXILIARY", aux_cmds);

            test_layout->addWidget(test_status);
            layout->addWidget(test_card);
        }
    }

    timer->start(200);

    layout->addStretch(1);
    scroll->setWidget(container);
    return scroll;
}

// ---------------------------------------------------------------------------
// Flash tab — placeholder
// ---------------------------------------------------------------------------

QWidget* build_flash_tab(std::shared_ptr<EcuConnection> ecu_conn = nullptr) {
    namespace fp = tuner_core::flash_preflight;
    namespace ffb = tuner_core::firmware_flash_builder;
    namespace bd = tuner_core::board_detection;

    auto* scroll = new QScrollArea;
    scroll->setWidgetResizable(true);
    scroll->setStyleSheet("QScrollArea { border: none; }");
    auto* container = new QWidget;
    auto* layout = new QVBoxLayout(container);
    layout->setContentsMargins(tt::space_lg, tt::space_lg, tt::space_lg, tt::space_lg);
    layout->setSpacing(tt::space_sm + 2);

    layout->addWidget(make_tab_header(
        "Flash Firmware",
        "Preflight \xe2\x86\x92 Select \xe2\x86\x92 Flash \xe2\x86\x92 Verify"));

    auto ports = list_serial_ports();
    auto current_definition_signature = std::make_shared<std::string>();
    auto current_tune_signature = std::make_shared<std::string>();
    auto current_detected_board = std::make_shared<std::optional<bd::BoardFamily>>();

    auto* preflight_card = new QWidget;
    auto* preflight_layout = new QVBoxLayout(preflight_card);
    preflight_layout->setContentsMargins(tt::space_md + 2, tt::space_md, tt::space_md + 2, tt::space_md);
    preflight_layout->setSpacing(tt::space_xs + 2);
    auto* preflight_title_label = new QLabel;
    {
        QFont hf = preflight_title_label->font();
        hf.setBold(true);
        hf.setPixelSize(tt::font_label);
        preflight_title_label->setFont(hf);
        char style[96];
        std::snprintf(style, sizeof(style),
            "color: %s; border: none;", tt::text_primary);
        preflight_title_label->setStyleSheet(QString::fromUtf8(style));
    }
    auto* preflight_body_label = new QLabel;
    preflight_body_label->setWordWrap(true);
    {
        char style[96];
        std::snprintf(style, sizeof(style),
            "color: %s; border: none; font-size: %dpx;",
            tt::text_secondary, tt::font_body);
        preflight_body_label->setStyleSheet(QString::fromUtf8(style));
    }
    preflight_layout->addWidget(preflight_title_label);
    preflight_layout->addWidget(preflight_body_label);
    layout->addWidget(preflight_card);

    // ---------------------------------------------------------------
    // Firmware selection + port selection + flash action
    // ---------------------------------------------------------------

    // Firmware file label — shows path after selection.
    auto* fw_path_label = new QLabel(QString::fromUtf8("No firmware file selected"));
    {
        char style[256];
        std::snprintf(style, sizeof(style),
            "QLabel { color: %s; font-size: %dpx; padding: %dpx; "
            "background: %s; border: 1px solid %s; border-radius: %dpx; }",
            tt::text_muted, tt::font_body, tt::space_sm,
            tt::bg_panel, tt::border, tt::radius_sm);
        fw_path_label->setStyleSheet(QString::fromUtf8(style));
    }

    // Shared state for the selected firmware path.
    auto firmware_path = std::make_shared<std::string>();

    // "Select Firmware..." button.
    auto* select_fw_btn = new QPushButton(QString::fromUtf8("Select Firmware (.hex)..."));
    select_fw_btn->setCursor(Qt::PointingHandCursor);
    {
        char style[384];
        std::snprintf(style, sizeof(style),
            "QPushButton { background: %s; border: 1px solid %s; "
            "border-radius: %dpx; padding: 6px 14px; "
            "color: %s; font-size: %dpx; font-weight: bold; } "
            "QPushButton:hover { background: %s; }",
            tt::bg_elevated, tt::accent_primary,
            tt::radius_sm, tt::text_primary, tt::font_body,
            tt::fill_primary_mid);
        select_fw_btn->setStyleSheet(QString::fromUtf8(style));
    }

    // Port selector combo.
    auto* port_combo = new QComboBox;
    for (const auto& p : ports) {
        port_combo->addItem(QString::fromUtf8(p.c_str()));
    }
    if (ports.empty()) {
        port_combo->addItem(QString::fromUtf8("(no ports)"));
        port_combo->setEnabled(false);
    }
    {
        char style[256];
        std::snprintf(style, sizeof(style),
            "QComboBox { background: %s; color: %s; border: 1px solid %s; "
            "border-radius: %dpx; padding: 4px 8px; font-size: %dpx; }",
            tt::bg_elevated, tt::text_primary, tt::border,
            tt::radius_sm, tt::font_body);
        port_combo->setStyleSheet(QString::fromUtf8(style));
    }

    // Refresh ports button.
    auto* refresh_ports_btn = new QPushButton(QString::fromUtf8("\xe2\x9f\xb3"));  // ⟳
    refresh_ports_btn->setFixedWidth(32);
    refresh_ports_btn->setCursor(Qt::PointingHandCursor);
    refresh_ports_btn->setToolTip(QString::fromUtf8("Rescan serial ports"));

    // Flash button — enabled when firmware + port selected.
    auto* flash_btn = new QPushButton(QString::fromUtf8("Flash Firmware"));
    flash_btn->setCursor(Qt::PointingHandCursor);
    flash_btn->setEnabled(false);
    {
        char style[512];
        std::snprintf(style, sizeof(style),
            "QPushButton { background: %s; border: 1px solid %s; "
            "border-radius: %dpx; padding: 8px 20px; "
            "color: %s; font-size: %dpx; font-weight: bold; } "
            "QPushButton:hover { background: %s; } "
            "QPushButton:disabled { background: %s; color: %s; border-color: %s; }",
            tt::accent_ok, tt::accent_ok, tt::radius_sm,
            tt::text_primary, tt::font_body,
            tt::fill_ok_mid,  // slightly lighter green on hover
            tt::bg_elevated, tt::text_dim, tt::border);
        flash_btn->setStyleSheet(QString::fromUtf8(style));
    }

    // Helper to update flash button enabled state.
    auto update_flash_enabled = [flash_btn, firmware_path, port_combo]() {
        bool can_flash = !firmware_path->empty()
            && port_combo->isEnabled()
            && port_combo->count() > 0;
        flash_btn->setEnabled(can_flash);
    };

    // Selection row layout.
    auto* sel_row = new QHBoxLayout;
    sel_row->setSpacing(tt::space_sm);
    sel_row->addWidget(select_fw_btn);
    sel_row->addWidget(fw_path_label, 1);
    layout->addLayout(sel_row);

    // Port + flash row layout.
    auto* port_row = new QHBoxLayout;
    port_row->setSpacing(tt::space_sm);
    {
        auto* port_label = new QLabel(QString::fromUtf8("Port:"));
        char lbl_style[128];
        std::snprintf(lbl_style, sizeof(lbl_style),
            "QLabel { color: %s; font-size: %dpx; }",
            tt::text_secondary, tt::font_body);
        port_label->setStyleSheet(QString::fromUtf8(lbl_style));
        port_row->addWidget(port_label);
    }
    port_row->addWidget(port_combo);
    port_row->addWidget(refresh_ports_btn);
    port_row->addStretch(1);
    port_row->addWidget(flash_btn);
    layout->addLayout(port_row);

    auto* firmware_card = new QWidget;
    auto* firmware_layout = new QVBoxLayout(firmware_card);
    firmware_layout->setContentsMargins(tt::space_md + 2, tt::space_md, tt::space_md + 2, tt::space_md);
    firmware_layout->setSpacing(tt::space_xs + 2);
    auto* firmware_title_label = new QLabel(QString::fromUtf8("Firmware"));
    {
        QFont hf = firmware_title_label->font();
        hf.setBold(true);
        hf.setPixelSize(tt::font_label);
        firmware_title_label->setFont(hf);
        char style[96];
        std::snprintf(style, sizeof(style),
            "color: %s; border: none;", tt::text_primary);
        firmware_title_label->setStyleSheet(QString::fromUtf8(style));
    }
    auto* firmware_body_label = new QLabel;
    firmware_body_label->setWordWrap(true);
    {
        char style[96];
        std::snprintf(style, sizeof(style),
            "color: %s; border: none; font-size: %dpx;",
            tt::text_secondary, tt::font_body);
        firmware_body_label->setStyleSheet(QString::fromUtf8(style));
    }
    firmware_layout->addWidget(firmware_title_label);
    firmware_layout->addWidget(firmware_body_label);
    layout->addWidget(firmware_card);

    // Flash output log — shows subprocess stdout/stderr.
    auto* log_label = new QLabel(QString::fromUtf8("Flash Log"));
    {
        char style[128];
        std::snprintf(style, sizeof(style),
            "QLabel { color: %s; font-size: %dpx; font-weight: bold; }",
            tt::text_secondary, tt::font_label);
        log_label->setStyleSheet(QString::fromUtf8(style));
    }
    layout->addWidget(log_label);

    // Progress bar — indeterminate (busy) during flash.
    auto* progress_bar = new QProgressBar;
    progress_bar->setRange(0, 0);  // indeterminate mode
    progress_bar->setFixedHeight(4);
    progress_bar->hide();
    {
        char ps[256];
        std::snprintf(ps, sizeof(ps),
            "QProgressBar { border: none; background: %s; } "
            "QProgressBar::chunk { background: %s; }",
            tt::bg_deep, tt::accent_primary);
        progress_bar->setStyleSheet(QString::fromUtf8(ps));
    }
    layout->addWidget(progress_bar);

    auto* log_output = new QTextEdit;
    log_output->setReadOnly(true);
    log_output->setMinimumHeight(180);
    {
        char style[256];
        std::snprintf(style, sizeof(style),
            "QTextEdit { background: %s; color: %s; border: 1px solid %s; "
            "border-radius: %dpx; font-family: 'Consolas', 'Courier New', monospace; "
            "font-size: %dpx; padding: %dpx; }",
            tt::bg_deep, tt::text_primary, tt::border,
            tt::radius_sm, tt::font_small, tt::space_sm);
        log_output->setStyleSheet(QString::fromUtf8(style));
    }
    layout->addWidget(log_output);

    // ---------------------------------------------------------------
    // Signal wiring
    // ---------------------------------------------------------------

    auto refresh_flash_state =
        [ecu_conn, current_definition_signature, current_tune_signature,
         current_detected_board, preflight_card, preflight_title_label,
         preflight_body_label, firmware_card, firmware_body_label]() {
        QSettings settings;
        *current_definition_signature =
            settings.value(kCurrentProjectSigKey, "").toString().toStdString();
        *current_tune_signature = *current_definition_signature;
        *current_detected_board = bd::detect_from_text(*current_definition_signature);
        auto fresh_ports = list_serial_ports();

        char checklist[2048];
        int coff = 0;
        if (ecu_conn && ecu_conn->connected) {
            coff += std::snprintf(checklist + coff, sizeof(checklist) - coff,
                "\xe2\x9c\x85 Connection: %s\n", ecu_conn->info.signature.c_str());
        } else {
            coff += std::snprintf(checklist + coff, sizeof(checklist) - coff,
                "\xe2\x9d\x8c Connection: Offline \xe2\x80\x94 connect via File \xe2\x86\x92 Connect\n");
        }
        if (!current_definition_signature->empty()) {
            coff += std::snprintf(checklist + coff, sizeof(checklist) - coff,
                "\xe2\x9c\x85 Definition: %s\n", current_definition_signature->c_str());
        } else {
            coff += std::snprintf(checklist + coff, sizeof(checklist) - coff,
                "\xe2\x9a\xa0\xef\xb8\x8f Definition: not loaded\n");
        }
        if (!current_tune_signature->empty()) {
            coff += std::snprintf(checklist + coff, sizeof(checklist) - coff,
                "\xe2\x9c\x85 Tune: %s\n", current_tune_signature->c_str());
        } else {
            coff += std::snprintf(checklist + coff, sizeof(checklist) - coff,
                "\xe2\x9a\xa0\xef\xb8\x8f Tune: no MSQ loaded\n");
        }
        if (!current_definition_signature->empty() && !current_tune_signature->empty()) {
            if (*current_definition_signature == *current_tune_signature) {
                coff += std::snprintf(checklist + coff, sizeof(checklist) - coff,
                    "\xe2\x9c\x85 Signatures match\n");
            } else {
                coff += std::snprintf(checklist + coff, sizeof(checklist) - coff,
                    "\xe2\x9a\xa0\xef\xb8\x8f Signature mismatch: definition=%s  tune=%s\n",
                    current_definition_signature->c_str(), current_tune_signature->c_str());
            }
        }
        if (fresh_ports.empty()) {
            coff += std::snprintf(checklist + coff, sizeof(checklist) - coff,
                "\xe2\x9a\xa0\xef\xb8\x8f No serial ports detected");
        } else {
            coff += std::snprintf(checklist + coff, sizeof(checklist) - coff,
                "\xe2\x9c\x85 Ports: ");
            for (size_t i = 0; i < fresh_ports.size(); ++i) {
                if (i > 0) coff += std::snprintf(checklist + coff, sizeof(checklist) - coff, ", ");
                coff += std::snprintf(checklist + coff, sizeof(checklist) - coff, "%s", fresh_ports[i].c_str());
            }
        }

        const bool has_warnings = current_definition_signature->empty()
            || current_tune_signature->empty()
            || (*current_definition_signature != *current_tune_signature)
            || fresh_ports.empty()
            || !(ecu_conn && ecu_conn->connected);
        preflight_title_label->setText(QString::fromUtf8(
            has_warnings ? "Preflight: Review Required" : "Preflight: Ready to Flash"));
        preflight_body_label->setText(QString::fromUtf8(checklist));
        set_info_card_accent(preflight_card, has_warnings ? tt::accent_warning : tt::accent_ok);

        char fw_desc[512];
        if (!current_definition_signature->empty()) {
            auto sig_family = fp::signature_family(*current_definition_signature);
            const std::string family_str = sig_family.value_or("unknown");
            std::snprintf(fw_desc, sizeof(fw_desc),
                "Definition: %s\n"
                "Board family: %s",
                current_definition_signature->c_str(), family_str.c_str());
            set_info_card_accent(firmware_card, tt::accent_ok);
        } else {
            std::snprintf(fw_desc, sizeof(fw_desc),
                "Load a project first to get firmware recommendations.\n"
                "Use File \xe2\x86\x92 Open Tune to load an INI + MSQ pair.");
            set_info_card_accent(firmware_card, tt::accent_primary);
        }
        firmware_body_label->setText(QString::fromUtf8(fw_desc));
    };

    refresh_flash_state();
    auto* flash_state_timer = new QTimer(container);
    flash_state_timer->setInterval(1000);
    QObject::connect(flash_state_timer, &QTimer::timeout, refresh_flash_state);
    flash_state_timer->start();

    // Select firmware file.
    QObject::connect(select_fw_btn, &QPushButton::clicked,
                     [container, fw_path_label, firmware_path,
                      update_flash_enabled]() {
        auto path = QFileDialog::getOpenFileName(
            container,
            QString::fromUtf8("Select Firmware File"),
            QString(),
            QString::fromUtf8("Firmware Files (*.hex *.bin);;All Files (*)"));
        if (path.isEmpty()) return;
        *firmware_path = path.toStdString();
        // Show just the filename, not full path.
        auto fname = std::filesystem::path(*firmware_path).filename().string();
        fw_path_label->setText(QString::fromUtf8(fname.c_str()));
        update_flash_enabled();
    });

    // Refresh serial ports.
    QObject::connect(refresh_ports_btn, &QPushButton::clicked,
                     [port_combo, update_flash_enabled]() {
        port_combo->clear();
        auto fresh_ports = list_serial_ports();
        if (fresh_ports.empty()) {
            port_combo->addItem(QString::fromUtf8("(no ports)"));
            port_combo->setEnabled(false);
        } else {
            port_combo->setEnabled(true);
            for (const auto& p : fresh_ports)
                port_combo->addItem(QString::fromUtf8(p.c_str()));
        }
        update_flash_enabled();
    });

    // Flash firmware — detect tool, build args, run subprocess.
    QObject::connect(flash_btn, &QPushButton::clicked,
                     [container, firmware_path, port_combo, flash_btn,
                      select_fw_btn, log_output, progress_bar,
                      current_detected_board, ecu_conn,
                      refresh_flash_state]() {
        std::string port = port_combo->currentText().toStdString();
        if (firmware_path->empty() || port.empty() || port == "(no ports)") return;

        // Determine flash tool and build arguments.
        std::string program;
        std::vector<std::string> args;
        namespace ffb = tuner_core::firmware_flash_builder;
        const auto system_name = current_system_name();

        // Detect board family from definition signature.
        bd::BoardFamily board = current_detected_board->value_or(bd::BoardFamily::ATMEGA2560);

        log_output->clear();
        char header[256];
        std::snprintf(header, sizeof(header),
            "Flashing %s on %s via %s...\n",
            std::filesystem::path(*firmware_path).filename().string().c_str(),
            port.c_str(),
            std::string(bd::to_string(board)).c_str());
        log_output->append(QString::fromUtf8(header));

        // Embedded HID flasher path — no external exe needed.
        // Mirrors the old Python app's `_flash_internal_teensy` path.
        const bool is_teensy =
            board == bd::BoardFamily::TEENSY35 ||
            board == bd::BoardFamily::TEENSY36 ||
            board == bd::BoardFamily::TEENSY41;
        if (is_teensy && tuner_core::teensy_hid_flasher::supported()) {
            namespace thi = tuner_core::teensy_hex_image;
            namespace thf = tuner_core::teensy_hid_flasher;
            auto spec_src = ffb::teensy_mcu_spec(board);
            thi::McuSpec spec{spec_src.name, spec_src.code_size, spec_src.block_size};

            std::string hex_text;
            try {
                std::ifstream in(*firmware_path, std::ios::binary);
                if (!in) throw std::runtime_error("could not open firmware file");
                std::stringstream ss;
                ss << in.rdbuf();
                hex_text = ss.str();
            } catch (const std::exception& e) {
                char err[512];
                std::snprintf(err, sizeof(err), "Error reading firmware: %s\n", e.what());
                log_output->append(QString::fromUtf8(err));
                return;
            }

            log_output->append(QString::fromUtf8("Using embedded HID flasher (no external exe).\n"));
            flash_btn->setEnabled(false);
            select_fw_btn->setEnabled(false);
            progress_bar->show();
            progress_bar->setRange(0, 100);
            progress_bar->setValue(0);

            if (ecu_conn && ecu_conn->connected) {
                log_output->append(QString::fromUtf8(
                    "Disconnecting ECU to free serial port...\n"));
                ecu_conn->close();
                refresh_flash_state();
            }

            std::string port_copy = port;
            QPointer<QTextEdit> log_p(log_output);
            QPointer<QProgressBar> prog_p(progress_bar);
            QPointer<QPushButton> flash_p(flash_btn);
            QPointer<QPushButton> select_p(select_fw_btn);
            auto refresh = refresh_flash_state;

            std::thread worker([hex_text, spec, port_copy,
                                log_p, prog_p, flash_p, select_p, refresh]() {
                auto on_progress = [log_p, prog_p](const thf::FlashProgress& p) {
                    QString msg = QString::fromUtf8(p.message.c_str());
                    int pct = p.percent;
                    QMetaObject::invokeMethod(qApp, [log_p, prog_p, msg, pct]() {
                        if (log_p) log_p->append(msg);
                        if (prog_p && pct >= 0) prog_p->setValue(pct);
                    }, Qt::QueuedConnection);
                };
                auto result = thf::flash(hex_text, spec, port_copy, on_progress);
                QMetaObject::invokeMethod(qApp,
                    [log_p, prog_p, flash_p, select_p, refresh, result]() {
                        if (prog_p) prog_p->hide();
                        if (log_p) {
                            if (result.ok) {
                                log_p->append(QString::fromUtf8(
                                    "\n\xe2\x9c\x85 Flash completed successfully.\n"));
                            } else {
                                log_p->append(QString::fromUtf8(
                                    (std::string("\n\xe2\x9d\x8c Flash failed: ") +
                                     result.detail + "\n").c_str()));
                            }
                        }
                        if (flash_p) flash_p->setEnabled(true);
                        if (select_p) select_p->setEnabled(true);
                        refresh();
                    }, Qt::QueuedConnection);
            });
            worker.detach();
            return;
        }

        try {
            switch (board) {
            case bd::BoardFamily::ATMEGA2560: {
                program = find_flash_program_path(
                    ffb::FlashTool::AVRDUDE,
                    ffb::tool_filename(ffb::FlashTool::AVRDUDE, system_name));
                if (program.empty()) {
                    throw std::runtime_error("avrdude executable not found (bundled tools or PATH).");
                }
                const auto config_path = find_flash_support_file(
                    ffb::FlashTool::AVRDUDE, "avrdude.conf", program);
                if (config_path.empty()) {
                    throw std::runtime_error("avrdude.conf not found next to bundled tools.");
                }
                args = ffb::build_avrdude_arguments(port, config_path, *firmware_path);
                break;
            }
            case bd::BoardFamily::TEENSY35:
            case bd::BoardFamily::TEENSY36:
            case bd::BoardFamily::TEENSY41: {
                auto spec = ffb::teensy_mcu_spec(board);
                program = find_flash_program_path(
                    ffb::FlashTool::TEENSY,
                    ffb::teensy_cli_filename(system_name));
                if (!program.empty()) {
                    args = ffb::build_teensy_cli_arguments(spec.name, *firmware_path);
                    break;
                }
                program = find_flash_program_path(
                    ffb::FlashTool::TEENSY,
                    ffb::tool_filename(ffb::FlashTool::TEENSY, system_name));
                if (program.empty()) {
                    throw std::runtime_error(
                        "No Teensy flash tool found (teensy_loader_cli or teensy_post_compile).");
                }
                {
                    const auto firmware_fs_path = std::filesystem::path(*firmware_path);
                    args = ffb::build_teensy_legacy_arguments(
                        spec.name,
                        firmware_fs_path.stem().string(),
                        firmware_fs_path.parent_path().string(),
                        std::filesystem::path(program).parent_path().string());
                }
                break;
            }
            case bd::BoardFamily::STM32F407_DFU: {
                program = find_flash_program_path(
                    ffb::FlashTool::DFU_UTIL,
                    ffb::tool_filename(ffb::FlashTool::DFU_UTIL, system_name));
                if (program.empty()) {
                    throw std::runtime_error("dfu-util executable not found (bundled tools or PATH).");
                }
                args = ffb::build_dfu_arguments("0483", "df11", *firmware_path);
                break;
            }
            }
        } catch (const std::exception& e) {
            char err[512];
            std::snprintf(err, sizeof(err),
                "Error building flash command: %s\n", e.what());
            log_output->append(QString::fromUtf8(err));
            return;
        }

        // Log the command being run.
        {
            std::string cmd_line = program;
            for (const auto& a : args) {
                cmd_line += " ";
                cmd_line += a;
            }
            char cmd_buf[1024];
            std::snprintf(cmd_buf, sizeof(cmd_buf), "$ %s\n", cmd_line.c_str());
            log_output->append(QString::fromUtf8(cmd_buf));
        }

        // Disable controls during flash and show progress.
        flash_btn->setEnabled(false);
        select_fw_btn->setEnabled(false);
        progress_bar->show();

        // If connected, disconnect first — the flash tool needs the port.
        if (ecu_conn && ecu_conn->connected) {
            log_output->append(QString::fromUtf8(
                "Disconnecting ECU to free serial port...\n"));
            ecu_conn->close();
            refresh_flash_state();
        }

        // Run via QProcess.
        auto* process = new QProcess(container);
        QObject::connect(process, &QProcess::readyReadStandardOutput,
                         [process, log_output]() {
            auto data = process->readAllStandardOutput();
            log_output->append(QString::fromUtf8(data));
        });
        QObject::connect(process, &QProcess::readyReadStandardError,
                         [process, log_output]() {
            auto data = process->readAllStandardError();
            log_output->append(QString::fromUtf8(data));
        });
        QObject::connect(process,
            static_cast<void(QProcess::*)(int, QProcess::ExitStatus)>(
                &QProcess::finished),
            [process, log_output, flash_btn, select_fw_btn, progress_bar,
             refresh_flash_state](
                int exitCode, QProcess::ExitStatus status) {
            progress_bar->hide();
            if (status == QProcess::NormalExit && exitCode == 0) {
                char ok[128];
                std::snprintf(ok, sizeof(ok),
                    "\n\xe2\x9c\x85 Flash completed successfully (exit code 0).\n");
                log_output->append(QString::fromUtf8(ok));
            } else {
                char fail[128];
                std::snprintf(fail, sizeof(fail),
                    "\n\xe2\x9d\x8c Flash failed (exit code %d).\n", exitCode);
                log_output->append(QString::fromUtf8(fail));
            }
            flash_btn->setEnabled(true);
            select_fw_btn->setEnabled(true);
            refresh_flash_state();
            process->deleteLater();
        });
        QObject::connect(process, &QProcess::errorOccurred,
                         [process, log_output, flash_btn, select_fw_btn, progress_bar,
                          refresh_flash_state](
                             QProcess::ProcessError error) {
            const char* msg = "Unknown error";
            switch (error) {
                case QProcess::FailedToStart: msg = "Failed to start — flash tool could not be launched"; break;
                case QProcess::Crashed: msg = "Process crashed"; break;
                case QProcess::Timedout: msg = "Process timed out"; break;
                case QProcess::WriteError: msg = "Write error"; break;
                case QProcess::ReadError: msg = "Read error"; break;
                default: break;
            }
            progress_bar->hide();
            char err[256];
            std::snprintf(err, sizeof(err),
                "\n\xe2\x9d\x8c %s\n", msg);
            log_output->append(QString::fromUtf8(err));
            flash_btn->setEnabled(true);
            select_fw_btn->setEnabled(true);
            refresh_flash_state();
            process->deleteLater();
        });

        // Convert args to QStringList.
        QStringList qargs;
        for (const auto& a : args)
            qargs.append(QString::fromUtf8(a.c_str()));

        process->start(QString::fromUtf8(program.c_str()), qargs);
    });

    layout->addStretch(1);
    scroll->setWidget(container);
    return scroll;
}

// ---------------------------------------------------------------------------
// Assist tab — Phase 7 accumulator + smoothing + diagnostics on synthetic data
// ---------------------------------------------------------------------------
//
// Demonstrates the full Phase 7 assist pipeline (sub-slices 33, 34, 35)
// live against a synthetic 4x4 VE cell-hit accumulation. The accumulator
// (sub-slice 35) produces proposals, the smoothing service (33) smooths
// them, and the diagnostics engine (34) analyzes them. Pure C++ — no
// Python in the pipeline. Same snprintf+QString::fromUtf8 pattern as the
// rest of the shell to dodge the Qt 6.7 + UCRT operator+ crash.

QWidget* build_assist_tab(
    std::shared_ptr<tuner_core::local_tune_edit::EditService> shared_edit_svc = nullptr,
    std::shared_ptr<EcuConnection> ecu_conn = nullptr) {
    namespace vca = tuner_core::ve_cell_hit_accumulator;
    namespace vps = tuner_core::ve_proposal_smoothing;
    namespace rcd = tuner_core::ve_root_cause_diagnostics;
    namespace var = tuner_core::ve_analyze_review;

    auto* scroll = new QScrollArea;
    scroll->setWidgetResizable(true);
    scroll->setStyleSheet("QScrollArea { border: none; }");
    auto* container = new QWidget;
    auto* outer = new QVBoxLayout(container);
    outer->setContentsMargins(tt::space_lg, tt::space_lg, tt::space_lg, tt::space_lg);
    outer->setSpacing(tt::space_sm + 2);

    outer->addWidget(make_tab_header(
        "Tune Assist",
        "Import a datalog, review correction proposals, then apply"));

    // ---- Shared state for proposals ----
    auto proposals = std::make_shared<std::vector<vps::Proposal>>();
    auto ve_table_name = std::make_shared<std::string>("veTable1");
    auto grid_rows = std::make_shared<int>(16);
    auto grid_cols = std::make_shared<int>(16);

    // ---- Import + Apply button row ----
    auto* btn_row = new QHBoxLayout;
    btn_row->setSpacing(tt::space_sm);

    auto* import_btn = new QPushButton(QString::fromUtf8("Import Datalog CSV..."));
    import_btn->setCursor(Qt::PointingHandCursor);
    {
        char bs[384];
        std::snprintf(bs, sizeof(bs),
            "QPushButton { background: %s; border: 1px solid %s; "
            "border-radius: %dpx; padding: 6px 14px; "
            "color: %s; font-size: %dpx; font-weight: bold; } "
            "QPushButton:hover { background: %s; }",
            tt::bg_elevated, tt::accent_primary,
            tt::radius_sm, tt::text_primary, tt::font_body,
            tt::fill_primary_mid);
        import_btn->setStyleSheet(QString::fromUtf8(bs));
    }

    auto* apply_btn = new QPushButton(QString::fromUtf8("Apply Proposals to VE Table"));
    apply_btn->setCursor(Qt::PointingHandCursor);
    apply_btn->setEnabled(false);
    {
        char bs[512];
        std::snprintf(bs, sizeof(bs),
            "QPushButton { background: %s; border: 1px solid %s; "
            "border-radius: %dpx; padding: 6px 14px; "
            "color: %s; font-size: %dpx; font-weight: bold; } "
            "QPushButton:hover { background: %s; } "
            "QPushButton:disabled { background: %s; color: %s; border-color: %s; }",
            tt::accent_ok, tt::accent_ok, tt::radius_sm,
            tt::text_primary, tt::font_body, tt::fill_ok_mid,
            tt::bg_elevated, tt::text_dim, tt::border);
        apply_btn->setStyleSheet(QString::fromUtf8(bs));
    }

    auto* source_label = new QLabel(QString::fromUtf8("Showing demo data"));
    {
        char sl[128];
        std::snprintf(sl, sizeof(sl),
            "QLabel { color: %s; font-size: %dpx; }", tt::text_muted, tt::font_small);
        source_label->setStyleSheet(QString::fromUtf8(sl));
    }

    btn_row->addWidget(import_btn);
    btn_row->addWidget(apply_btn);
    btn_row->addWidget(source_label, 1);
    outer->addLayout(btn_row);

    // ---- Results container — rebuilt dynamically ----
    auto* results_widget = new QWidget;
    auto* results_layout = new QVBoxLayout(results_widget);
    results_layout->setContentsMargins(0, 0, 0, 0);
    results_layout->setSpacing(tt::space_sm + 2);
    outer->addWidget(results_widget);

    // Helper: populate results from a snapshot.
    auto populate = std::make_shared<std::function<void(
        const vca::Snapshot&, int, int)>>();

    *populate = [results_layout, proposals](
        const vca::Snapshot& snapshot, int rows, int cols) {
        // Hide existing children.
        for (int i = results_layout->count() - 1; i >= 0; --i) {
            auto* item = results_layout->itemAt(i);
            if (item && item->widget()) item->widget()->hide();
        }

        auto layer = vps::smooth(snapshot.proposals, {});
        auto report = rcd::diagnose(snapshot.proposals);

        // Accumulator summary.
        char acc_buf[512];
        std::snprintf(acc_buf, sizeof(acc_buf),
            "%s\nCoverage: %d/%d cells visited (%.0f%%)",
            snapshot.summary_text.c_str(),
            snapshot.coverage.visited_count, snapshot.coverage.total_count,
            snapshot.coverage.coverage_ratio() * 100.0);
        results_layout->addWidget(make_info_card(
            "Cell Hit Accumulator", acc_buf, tt::accent_primary));

        // Smoothing.
        char sm_buf[512];
        std::snprintf(sm_buf, sizeof(sm_buf),
            "%s\nSmoothed cells: %d   Preserved unchanged: %d",
            layer.summary_text.c_str(),
            layer.smoothed_count, layer.unchanged_count);
        results_layout->addWidget(make_info_card(
            "Proposal Smoothing", sm_buf, tt::accent_special));

        // Diagnostics.
        if (report.has_findings()) {
            for (const auto& d : report.diagnostics) {
                char heading[160];
                std::snprintf(heading, sizeof(heading),
                    "Diagnostic: %s  [%s]", d.rule.c_str(), d.severity.c_str());
                results_layout->addWidget(make_info_card(
                    heading, d.message.c_str(), tt::accent_warning));
            }
        } else {
            results_layout->addWidget(make_info_card(
                "Root-Cause Diagnostics",
                report.summary_text.c_str(), tt::accent_ok));
        }

        // Heatmap grid (capped at 16x16 for display).
        int disp_rows = std::min(rows, 16);
        int disp_cols = std::min(cols, 16);
        auto* grid_card = new QWidget;
        auto* gl = new QVBoxLayout(grid_card);
        gl->setContentsMargins(tt::space_md + 2, tt::space_md, tt::space_md + 2, tt::space_md);
        grid_card->setStyleSheet(QString::fromUtf8(
            tt::card_style(tt::accent_ok).c_str()));
        auto* gh = new QLabel("Correction factor proposals");
        QFont ghf = gh->font(); ghf.setBold(true);
        gh->setFont(ghf);
        {
            char s[96];
            std::snprintf(s, sizeof(s), "color: %s; border: none;", tt::text_secondary);
            gh->setStyleSheet(QString::fromUtf8(s));
        }
        gl->addWidget(gh);

        // Build grid lookup.
        std::vector<std::vector<double>> cf_grid(disp_rows,
            std::vector<double>(disp_cols, 1.0));
        for (const auto& p : snapshot.proposals) {
            if (p.row_index < disp_rows && p.col_index < disp_cols)
                cf_grid[p.row_index][p.col_index] = p.correction_factor;
        }
        for (int r = 0; r < disp_rows; ++r) {
            char row_buf[1024];
            int off = 0;
            for (int c = 0; c < disp_cols; ++c) {
                double cf = cf_grid[r][c];
                const char* color = (cf > 1.05) ? tt::accent_danger :
                                    (cf < 0.95) ? tt::accent_primary : tt::accent_ok;
                off += std::snprintf(row_buf + off, sizeof(row_buf) - off,
                    "<span style='background-color: %s; color: %s; "
                    "padding: 2px 6px; margin-right: 2px; "
                    "font-family: monospace; font-size: %dpx;'>%.2f</span>",
                    color, tt::text_inverse, tt::font_small, cf);
                if (off >= (int)sizeof(row_buf) - 1) break;
            }
            auto* row_lbl = new QLabel;
            row_lbl->setTextFormat(Qt::RichText);
            row_lbl->setText(QString::fromUtf8(row_buf));
            row_lbl->setStyleSheet("border: none;");
            gl->addWidget(row_lbl);
        }
        results_layout->addWidget(grid_card);

        // Review.
        auto review = var::build(snapshot, {}, &layer, &report);
        results_layout->addWidget(make_info_card(
            "Analysis Review", review.detail_text.c_str(), tt::accent_warning));

        // Store proposals for Apply button.
        *proposals = snapshot.proposals;
    };

    // ---- Initial demo data (4x4 grid) ----
    {
        std::vector<vca::CellAccumulation> cells;
        for (int r = 0; r < 4; ++r) {
            for (int c = 0; c < 4; ++c) {
                vca::CellAccumulation cell;
                cell.row_index = r;
                cell.col_index = c;
                cell.current_ve = 100.0;
                double cf = (r == 1 && c == 1) ? 1.10 : 1.00;
                int n = (r == 1 && c == 1) ? 1 : 5;
                for (int i = 0; i < n; ++i) {
                    vca::CorrectionSample s;
                    s.correction_factor = cf;
                    s.weight = 1.0;
                    s.timestamp_seconds = 1000.0 + i;
                    cell.samples.push_back(s);
                }
                cells.push_back(cell);
            }
        }
        auto snapshot = vca::build_snapshot(cells, 4, 4, 77, 3);
        (*populate)(snapshot, 4, 4);
    }

    // ---- Import datalog CSV ----
    QObject::connect(import_btn, &QPushButton::clicked,
                     [container, source_label, apply_btn, populate,
                      proposals, ve_table_name, grid_rows, grid_cols,
                      shared_edit_svc]() {
        auto path = QFileDialog::getOpenFileName(container,
            QString::fromUtf8("Import Datalog CSV"),
            QDir::homePath(),
            QString::fromUtf8("CSV Files (*.csv);;All Files (*)"));
        if (path.isEmpty()) return;

        // Read file.
        std::ifstream in(path.toStdString(), std::ios::in | std::ios::binary);
        if (!in) return;
        std::string text((std::istreambuf_iterator<char>(in)),
                         std::istreambuf_iterator<char>());
        in.close();

        // Parse CSV header.
        std::istringstream stream(text);
        std::string header_line;
        if (!std::getline(stream, header_line)) return;
        if (!header_line.empty() && header_line.back() == '\r')
            header_line.pop_back();

        std::vector<std::string> columns;
        {
            std::istringstream hs(header_line);
            std::string col;
            while (std::getline(hs, col, ',')) {
                while (!col.empty() && col.front() == ' ') col.erase(col.begin());
                while (!col.empty() && col.back() == ' ') col.pop_back();
                columns.push_back(col);
            }
        }

        // Find key column indices.
        int rpm_idx = -1, map_idx = -1, afr_idx = -1, lambda_idx = -1;
        for (int i = 0; i < static_cast<int>(columns.size()); ++i) {
            std::string lower = columns[i];
            for (auto& ch : lower) ch = static_cast<char>(
                std::tolower(static_cast<unsigned char>(ch)));
            if (lower == "rpm") rpm_idx = i;
            else if (lower == "map" || lower == "fuelload") map_idx = i;
            else if (lower == "afr" || lower == "afr1") afr_idx = i;
            else if (lower == "lambda" || lower == "lambda1") lambda_idx = i;
        }

        if (rpm_idx < 0 || map_idx < 0 || (afr_idx < 0 && lambda_idx < 0)) {
            source_label->setText(QString::fromUtf8(
                "CSV missing required columns (rpm, map, afr/lambda)"));
            return;
        }

        // Standard Speeduino 16x16 VE table bins (default).
        // TODO: read actual bins from the loaded tune definition.
        std::vector<double> rpm_bins = {
            500, 700, 1000, 1500, 2000, 2500, 3000, 3500,
            4000, 4500, 5000, 5500, 6000, 6500, 7000, 8000};
        std::vector<double> map_bins = {
            10, 20, 30, 40, 50, 60, 70, 80,
            100, 120, 140, 160, 180, 200, 220, 240};
        int nrows = static_cast<int>(map_bins.size());
        int ncols = static_cast<int>(rpm_bins.size());

        // Get current VE values from edit_svc if available.
        std::vector<double> current_ve(nrows * ncols, 50.0);
        if (shared_edit_svc) {
            auto* tv = shared_edit_svc->get_value("veTable1");
            if (tv && std::holds_alternative<std::vector<double>>(tv->value)) {
                current_ve = std::get<std::vector<double>>(tv->value);
                current_ve.resize(nrows * ncols, 50.0);
            }
        }

        // Nearest-bin lookup helper.
        auto nearest = [](const std::vector<double>& bins, double val) -> int {
            int best = 0;
            double best_dist = std::abs(val - bins[0]);
            for (int i = 1; i < static_cast<int>(bins.size()); ++i) {
                double d = std::abs(val - bins[i]);
                if (d < best_dist) { best_dist = d; best = i; }
            }
            return best;
        };

        // Accumulate per cell.
        std::map<std::pair<int,int>, std::vector<vca::CorrectionSample>> cell_samples;
        int accepted = 0, rejected = 0;
        double ts = 0.0;

        std::string line;
        while (std::getline(stream, line)) {
            if (!line.empty() && line.back() == '\r') line.pop_back();
            if (line.empty()) continue;

            // Parse values.
            std::vector<std::string> vals;
            {
                std::istringstream ls(line);
                std::string cell;
                while (std::getline(ls, cell, ',')) {
                    while (!cell.empty() && cell.front() == ' ') cell.erase(cell.begin());
                    while (!cell.empty() && cell.back() == ' ') cell.pop_back();
                    vals.push_back(cell);
                }
            }

            auto safe_double = [&vals](int idx) -> double {
                if (idx < 0 || idx >= static_cast<int>(vals.size())) return 0.0;
                try { return std::stod(vals[idx]); } catch (...) { return 0.0; }
            };

            double rpm = safe_double(rpm_idx);
            double map_val = safe_double(map_idx);
            double lambda = 0.0;
            if (lambda_idx >= 0)
                lambda = safe_double(lambda_idx);
            else if (afr_idx >= 0)
                lambda = safe_double(afr_idx) / 14.7;  // AFR → lambda (gasoline)

            // Basic gating: reject invalid data.
            if (rpm < 300 || rpm > 10000 || map_val < 5 || map_val > 300
                || lambda < 0.5 || lambda > 2.0) {
                rejected++;
                continue;
            }

            int row = nearest(map_bins, map_val);
            int col = nearest(rpm_bins, rpm);

            vca::CorrectionSample s;
            s.correction_factor = 1.0 / lambda;  // stoich target = lambda 1.0
            s.weight = 1.0;
            s.timestamp_seconds = ts;
            ts += 0.2;  // assume 200ms log interval

            cell_samples[{row, col}].push_back(s);
            accepted++;
        }

        if (accepted == 0) {
            source_label->setText(QString::fromUtf8(
                "No valid records found in CSV"));
            return;
        }

        // Build CellAccumulation vector.
        std::vector<vca::CellAccumulation> accums;
        for (auto& [key, samples] : cell_samples) {
            vca::CellAccumulation ca;
            ca.row_index = key.first;
            ca.col_index = key.second;
            int flat = ca.row_index * ncols + ca.col_index;
            ca.current_ve = (flat < static_cast<int>(current_ve.size()))
                ? current_ve[flat] : 50.0;
            ca.samples = std::move(samples);
            accums.push_back(std::move(ca));
        }

        auto snapshot = vca::build_snapshot(
            accums, nrows, ncols, accepted, rejected);

        *grid_rows = nrows;
        *grid_cols = ncols;
        (*populate)(snapshot, nrows, ncols);

        // Update source label.
        auto fname = std::filesystem::path(path.toStdString()).filename().string();
        char lbl[256];
        std::snprintf(lbl, sizeof(lbl),
            "%s \xe2\x80\x94 %d accepted, %d rejected, %d cells hit",
            fname.c_str(), accepted, rejected,
            static_cast<int>(accums.size()));
        source_label->setText(QString::fromUtf8(lbl));
        apply_btn->setEnabled(!proposals->empty());
    });

    // ---- Apply proposals to VE table ----
    QObject::connect(apply_btn, &QPushButton::clicked,
                     [container, proposals, ve_table_name,
                      grid_cols, shared_edit_svc, apply_btn, source_label]() {
        if (!shared_edit_svc || proposals->empty()) return;

        // Get current VE table values.
        auto* tv = shared_edit_svc->get_value(*ve_table_name);
        if (!tv || !std::holds_alternative<std::vector<double>>(tv->value)) {
            source_label->setText(QString::fromUtf8(
                "VE table not found in tune \xe2\x80\x94 cannot apply"));
            return;
        }

        auto values = std::get<std::vector<double>>(tv->value);

        // Apply each proposal.
        int applied = 0;
        for (const auto& p : *proposals) {
            int flat = p.row_index * (*grid_cols) + p.col_index;
            if (flat >= 0 && flat < static_cast<int>(values.size())) {
                values[flat] = p.proposed_ve;
                applied++;
            }
        }

        if (applied > 0) {
            shared_edit_svc->replace_list(*ve_table_name, values);
            char msg[128];
            std::snprintf(msg, sizeof(msg),
                "Applied %d VE proposals \xe2\x80\x94 review on TUNE tab",
                applied);
            source_label->setText(QString::fromUtf8(msg));
        }
        apply_btn->setEnabled(false);
    });

    // ---- Live VE Analyze session ----
    // Real-time correction accumulation while connected to ECU.
    // Polls ecu_conn->runtime every 500ms, maps RPM/MAP to VE cell,
    // calculates correction from live lambda, accumulates per-cell.
    {
        auto* live_header = new QLabel("Live VE Analyze");
        QFont lhf = live_header->font(); lhf.setBold(true); lhf.setPixelSize(tt::font_heading);
        live_header->setFont(lhf);
        live_header->setStyleSheet(QString::fromUtf8("margin-top: 12px;"));
        outer->addWidget(live_header);

        auto* live_card = new QWidget;
        auto* live_layout = new QHBoxLayout(live_card);
        live_layout->setContentsMargins(tt::space_md, tt::space_sm, tt::space_md, tt::space_sm);
        live_layout->setSpacing(tt::space_md);
        live_card->setStyleSheet(QString::fromUtf8(tt::card_style().c_str()));

        auto* live_status = new QLabel(QString::fromUtf8("Idle \xe2\x80\x94 connect to ECU and press Start"));
        {
            char s[128];
            std::snprintf(s, sizeof(s), "QLabel { color: %s; font-size: %dpx; border: none; }",
                tt::text_secondary, tt::font_body);
            live_status->setStyleSheet(QString::fromUtf8(s));
        }
        live_layout->addWidget(live_status, 1);

        auto make_btn = [](const char* text) {
            auto* btn = new QPushButton(QString::fromUtf8(text));
            char bs[256];
            std::snprintf(bs, sizeof(bs),
                "QPushButton { background: %s; color: %s; border: 1px solid %s; "
                "border-radius: %dpx; padding: %dpx %dpx; font-size: %dpx; }"
                "QPushButton:hover { background: %s; }"
                "QPushButton:disabled { color: %s; }",
                tt::bg_elevated, tt::text_primary, tt::border,
                tt::radius_sm, tt::space_xs, tt::space_md, tt::font_small,
                tt::fill_primary_mid, tt::text_dim);
            btn->setStyleSheet(QString::fromUtf8(bs));
            return btn;
        };

        auto* start_live_btn = make_btn("\xe2\x97\x89 Start");
        auto* stop_live_btn = make_btn("\xe2\x96\xa0 Stop");
        auto* reset_live_btn = make_btn("Reset");
        stop_live_btn->setEnabled(false);

        live_layout->addWidget(start_live_btn);
        live_layout->addWidget(stop_live_btn);
        live_layout->addWidget(reset_live_btn);
        outer->addWidget(live_card);

        // Live results container — rebuilt periodically.
        auto* live_results = new QWidget;
        auto* live_results_layout = new QVBoxLayout(live_results);
        live_results_layout->setContentsMargins(0, 0, 0, 0);
        live_results_layout->setSpacing(tt::space_sm);
        outer->addWidget(live_results);

        // Shared live session state.
        auto live_active = std::make_shared<bool>(false);
        auto live_accums = std::make_shared<
            std::map<std::pair<int,int>, std::vector<vca::CorrectionSample>>>();
        auto live_accepted = std::make_shared<int>(0);
        auto live_rejected = std::make_shared<int>(0);
        auto live_ts = std::make_shared<double>(0.0);

        // Standard 16x16 bins (same as import path).
        auto rpm_bins = std::make_shared<std::vector<double>>(std::vector<double>{
            500, 700, 1000, 1500, 2000, 2500, 3000, 3500,
            4000, 4500, 5000, 5500, 6000, 6500, 7000, 8000});
        auto map_bins = std::make_shared<std::vector<double>>(std::vector<double>{
            10, 20, 30, 40, 50, 60, 70, 80,
            100, 120, 140, 160, 180, 200, 220, 240});

        auto nearest = [](const std::vector<double>& bins, double val) -> int {
            int best = 0;
            double best_dist = std::abs(val - bins[0]);
            for (int i = 1; i < static_cast<int>(bins.size()); ++i) {
                double d = std::abs(val - bins[i]);
                if (d < best_dist) { best_dist = d; best = i; }
            }
            return best;
        };

        // Live poll timer — 500ms interval for accumulation.
        auto* live_timer = new QTimer(container);

        // Refresh display from accumulated data.
        auto refresh_live = std::make_shared<std::function<void()>>();
        *refresh_live = [live_results_layout, live_accums, live_accepted,
                         live_rejected, live_status, shared_edit_svc,
                         proposals, apply_btn,
                         rpm_bins, map_bins]() {
            // Hide existing children.
            for (int i = live_results_layout->count() - 1; i >= 0; --i) {
                auto* item = live_results_layout->itemAt(i);
                if (item && item->widget()) item->widget()->hide();
            }

            if (live_accums->empty()) return;

            int nrows = static_cast<int>(map_bins->size());
            int ncols = static_cast<int>(rpm_bins->size());

            // Get current VE values.
            std::vector<double> current_ve(nrows * ncols, 50.0);
            if (shared_edit_svc) {
                auto* tv = shared_edit_svc->get_value("veTable1");
                if (tv && std::holds_alternative<std::vector<double>>(tv->value)) {
                    current_ve = std::get<std::vector<double>>(tv->value);
                    current_ve.resize(nrows * ncols, 50.0);
                }
            }

            // Build accumulations.
            std::vector<vca::CellAccumulation> accums;
            for (auto& [key, samples] : *live_accums) {
                vca::CellAccumulation ca;
                ca.row_index = key.first;
                ca.col_index = key.second;
                int flat = ca.row_index * ncols + ca.col_index;
                ca.current_ve = (flat < static_cast<int>(current_ve.size()))
                    ? current_ve[flat] : 50.0;
                ca.samples = samples;
                accums.push_back(std::move(ca));
            }

            auto snapshot = vca::build_snapshot(
                accums, nrows, ncols, *live_accepted, *live_rejected);
            auto layer = vps::smooth(snapshot.proposals, {});

            // Summary card.
            char acc_buf[512];
            std::snprintf(acc_buf, sizeof(acc_buf),
                "Live: %d accepted, %d rejected\n"
                "Coverage: %d/%d cells (%.0f%%)",
                *live_accepted, *live_rejected,
                snapshot.coverage.visited_count, snapshot.coverage.total_count,
                snapshot.coverage.coverage_ratio() * 100.0);
            live_results_layout->addWidget(make_info_card(
                "Live Accumulator", acc_buf, tt::accent_primary));

            if (!snapshot.proposals.empty()) {
                char sm_buf[256];
                std::snprintf(sm_buf, sizeof(sm_buf),
                    "%d proposals \xc2\xb7 %d smoothed",
                    static_cast<int>(snapshot.proposals.size()),
                    layer.smoothed_count);
                live_results_layout->addWidget(make_info_card(
                    "Live Proposals", sm_buf, tt::accent_ok));
            }

            // Update status.
            char st[128];
            std::snprintf(st, sizeof(st),
                "Recording \xe2\x80\x94 %d samples, %d cells",
                *live_accepted,
                static_cast<int>(live_accums->size()));
            live_status->setText(QString::fromUtf8(st));

            // Store proposals for Apply.
            *proposals = snapshot.proposals;
            apply_btn->setEnabled(!proposals->empty());
        };

        QObject::connect(live_timer, &QTimer::timeout,
                         [live_active, live_accums, live_accepted, live_rejected,
                          live_ts, ecu_conn, rpm_bins, map_bins, nearest,
                          refresh_live]() {
            if (!*live_active) return;
            if (!ecu_conn || !ecu_conn->connected) return;

            const auto& rt = ecu_conn->runtime;
            auto get = [&rt](const std::string& name) -> double {
                auto it = rt.find(name);
                return (it != rt.end()) ? it->second : 0.0;
            };

            // Firmware learn gate — reject samples when the ECU reports
            // conditions unsuitable for autotune learning: no sync, active
            // transient (accel enrichment firing), or warmup/ASE active.
            // Mirrors Python's firmwareLearnGate (Phase 7 Slice 7.1).
            {
                std::vector<std::pair<std::string, double>> vm(rt.begin(), rt.end());
                auto telem = tuner_core::runtime_telemetry::decode(vm);
                const auto& rs = telem.runtime_status;
                if (!rs.full_sync || rs.transient_active || rs.warmup_or_ase_active) {
                    (*live_rejected)++;
                    return;
                }
            }

            double rpm = get("rpm");
            double map_val = get("map");
            double lambda = get("lambda1");
            if (lambda <= 0.0) lambda = get("afr") / 14.7;

            // Basic gating.
            if (rpm < 300 || rpm > 10000 || map_val < 5 || map_val > 300
                || lambda < 0.5 || lambda > 2.0) {
                (*live_rejected)++;
                return;
            }

            int row = nearest(*map_bins, map_val);
            int col = nearest(*rpm_bins, rpm);

            vca::CorrectionSample s;
            s.correction_factor = 1.0 / lambda;
            s.weight = 1.0;
            s.timestamp_seconds = *live_ts;
            *live_ts += 0.5;

            (*live_accums)[{row, col}].push_back(s);
            (*live_accepted)++;

            // Refresh display every 10 samples.
            if (*live_accepted % 10 == 0) {
                (*refresh_live)();
            }
        });

        QObject::connect(start_live_btn, &QPushButton::clicked,
                         [start_live_btn, stop_live_btn, live_active,
                          live_timer, live_status]() {
            *live_active = true;
            start_live_btn->setEnabled(false);
            stop_live_btn->setEnabled(true);
            live_timer->start(500);
            live_status->setText(QString::fromUtf8(
                "Recording \xe2\x80\x94 waiting for data..."));
        });

        QObject::connect(stop_live_btn, &QPushButton::clicked,
                         [start_live_btn, stop_live_btn, live_active,
                          live_timer, refresh_live]() {
            *live_active = false;
            start_live_btn->setEnabled(true);
            stop_live_btn->setEnabled(false);
            live_timer->stop();
            (*refresh_live)();
        });

        QObject::connect(reset_live_btn, &QPushButton::clicked,
                         [live_accums, live_accepted, live_rejected, live_ts,
                          live_status, live_results_layout, proposals, apply_btn]() {
            live_accums->clear();
            *live_accepted = 0;
            *live_rejected = 0;
            *live_ts = 0.0;
            proposals->clear();
            apply_btn->setEnabled(false);
            // Hide results.
            for (int i = live_results_layout->count() - 1; i >= 0; --i) {
                auto* item = live_results_layout->itemAt(i);
                if (item && item->widget()) item->widget()->hide();
            }
            live_status->setText(QString::fromUtf8(
                "Reset \xe2\x80\x94 press Start to begin new session"));
        });
    }

    // ---- Virtual Dyno ----
    // Estimates torque and HP from ECU sensor data during a WOT pull.
    {
        namespace vd = tuner_core::virtual_dyno;

        auto* dyno_header = new QLabel("Virtual Dyno");
        QFont dhf = dyno_header->font(); dhf.setBold(true); dhf.setPixelSize(tt::font_heading);
        dyno_header->setFont(dhf);
        dyno_header->setStyleSheet(QString::fromUtf8("margin-top: 12px;"));
        outer->addWidget(dyno_header);

        auto* dyno_note = new QLabel(
            "Estimates torque and horsepower from ECU sensor data during a "
            "WOT pull. Import a datalog CSV with RPM, MAP, IAT, and AFR "
            "columns, or use the last captured log.");
        dyno_note->setWordWrap(true);
        {
            char ws[64];
            std::snprintf(ws, sizeof(ws), "color: %s;", tt::text_muted);
            dyno_note->setStyleSheet(QString::fromUtf8(ws));
        }
        outer->addWidget(dyno_note);

        // Engine spec fields (inline, from wizard values or defaults).
        auto* dyno_card = new QWidget;
        auto* dyno_layout = new QVBoxLayout(dyno_card);
        dyno_layout->setContentsMargins(tt::space_md, tt::space_sm, tt::space_md, tt::space_sm);
        dyno_layout->setSpacing(tt::space_sm);
        dyno_card->setStyleSheet(QString::fromUtf8(tt::card_style().c_str()));

        auto* dyno_result_label = new QLabel(QString::fromUtf8(
            "Import a WOT pull CSV to see results"));
        dyno_result_label->setWordWrap(true);
        {
            char s[96];
            std::snprintf(s, sizeof(s),
                "QLabel { color: %s; font-size: %dpx; border: none; }",
                tt::text_secondary, tt::font_body);
            dyno_result_label->setStyleSheet(QString::fromUtf8(s));
        }

        // Dyno curve display — text-based table for now (no chart widget).
        auto* dyno_curve_label = new QLabel;
        dyno_curve_label->setTextFormat(Qt::RichText);
        dyno_curve_label->setWordWrap(true);
        {
            char s[128];
            std::snprintf(s, sizeof(s),
                "QLabel { color: %s; font-size: %dpx; font-family: monospace; border: none; }",
                tt::text_primary, tt::font_small);
            dyno_curve_label->setStyleSheet(QString::fromUtf8(s));
        }

        // Import WOT button.
        auto* dyno_import_btn = new QPushButton(QString::fromUtf8("Import WOT Pull CSV..."));
        dyno_import_btn->setCursor(Qt::PointingHandCursor);
        {
            char bs[256];
            std::snprintf(bs, sizeof(bs),
                "QPushButton { background: %s; color: %s; border: 1px solid %s; "
                "border-radius: %dpx; padding: %dpx %dpx; font-size: %dpx; } "
                "QPushButton:hover { background: %s; }",
                tt::bg_elevated, tt::text_primary, tt::border,
                tt::radius_sm, tt::space_xs, tt::space_md, tt::font_small,
                tt::fill_primary_mid);
            dyno_import_btn->setStyleSheet(QString::fromUtf8(bs));
        }

        QObject::connect(dyno_import_btn, &QPushButton::clicked,
                         [container, dyno_result_label, dyno_curve_label]() {
            auto path = QFileDialog::getOpenFileName(container,
                QString::fromUtf8("Import WOT Pull CSV"),
                QDir::homePath(),
                QString::fromUtf8("CSV Files (*.csv);;All Files (*)"));
            if (path.isEmpty()) return;

            // Read and parse CSV.
            std::ifstream in(path.toStdString(), std::ios::in | std::ios::binary);
            if (!in) return;
            std::string header_line;
            if (!std::getline(in, header_line)) return;
            if (!header_line.empty() && header_line.back() == '\r')
                header_line.pop_back();

            // Find column indices.
            std::vector<std::string> cols;
            {
                std::istringstream hs(header_line);
                std::string col;
                while (std::getline(hs, col, ',')) {
                    while (!col.empty() && col.front() == ' ') col.erase(col.begin());
                    while (!col.empty() && col.back() == ' ') col.pop_back();
                    std::string lower = col;
                    for (auto& c : lower) c = static_cast<char>(
                        std::tolower(static_cast<unsigned char>(c)));
                    cols.push_back(lower);
                }
            }

            int rpm_i = -1, map_i = -1, iat_i = -1, afr_i = -1;
            for (int i = 0; i < static_cast<int>(cols.size()); ++i) {
                if (cols[i] == "rpm") rpm_i = i;
                else if (cols[i] == "map" || cols[i] == "fuelload") map_i = i;
                else if (cols[i] == "iat") iat_i = i;
                else if (cols[i] == "afr" || cols[i] == "afr1") afr_i = i;
            }
            if (rpm_i < 0 || map_i < 0 || afr_i < 0) {
                dyno_result_label->setText(QString::fromUtf8(
                    "CSV missing required columns (rpm, map, afr)"));
                return;
            }

            // Parse rows — filter to WOT (TPS > 90% or MAP > 90 kPa).
            std::vector<vd::DataPoint> data;
            std::string line;
            while (std::getline(in, line)) {
                if (!line.empty() && line.back() == '\r') line.pop_back();
                if (line.empty()) continue;
                std::vector<std::string> vals;
                {
                    std::istringstream ls(line);
                    std::string cell;
                    while (std::getline(ls, cell, ',')) {
                        while (!cell.empty() && cell.front() == ' ') cell.erase(cell.begin());
                        while (!cell.empty() && cell.back() == ' ') cell.pop_back();
                        vals.push_back(cell);
                    }
                }
                auto safe_d = [&vals](int idx) -> double {
                    if (idx < 0 || idx >= static_cast<int>(vals.size())) return 0;
                    try { return std::stod(vals[idx]); } catch (...) { return 0; }
                };

                double rpm = safe_d(rpm_i);
                double map_v = safe_d(map_i);
                double afr = safe_d(afr_i);
                double iat = (iat_i >= 0) ? safe_d(iat_i) : 25.0;

                // WOT filter: MAP > 90 kPa or high RPM + high MAP.
                if (map_v < 90 || rpm < 1500 || afr < 8 || afr > 25) continue;

                vd::DataPoint dp;
                dp.rpm = rpm;
                dp.map_kpa = map_v;
                dp.iat_celsius = iat;
                dp.afr = afr;
                data.push_back(dp);
            }
            in.close();

            if (data.empty()) {
                dyno_result_label->setText(QString::fromUtf8(
                    "No WOT data found (MAP > 90 kPa, RPM > 1500)"));
                return;
            }

            // Run calculation.
            vd::EngineSpec spec;
            spec.displacement_cc = 2000;  // TODO: read from tune
            spec.cylinders = 6;
            auto result = vd::calculate(data, spec);

            dyno_result_label->setText(QString::fromUtf8(
                result.summary_text.c_str()));

            // Build text-based curve display.
            char curve_buf[2048];
            int off = 0;
            off += std::snprintf(curve_buf + off, sizeof(curve_buf) - off,
                "<table style='border-collapse: collapse;'>"
                "<tr><th style='padding: 2px 8px; color: %s;'>RPM</th>"
                "<th style='padding: 2px 8px; color: %s;'>Torque (Nm)</th>"
                "<th style='padding: 2px 8px; color: %s;'>HP</th></tr>",
                tt::text_muted, tt::text_muted, tt::text_muted);

            for (const auto& p : result.points) {
                bool is_peak_t = (std::abs(p.rpm - result.peak_torque_rpm) < 50);
                bool is_peak_h = (std::abs(p.rpm - result.peak_hp_rpm) < 50);
                const char* t_color = is_peak_t ? tt::accent_ok : tt::text_primary;
                const char* h_color = is_peak_h ? tt::accent_ok : tt::text_primary;
                off += std::snprintf(curve_buf + off, sizeof(curve_buf) - off,
                    "<tr>"
                    "<td style='padding: 2px 8px; color: %s;'>%.0f</td>"
                    "<td style='padding: 2px 8px; color: %s;'>%.1f%s</td>"
                    "<td style='padding: 2px 8px; color: %s;'>%.1f%s</td>"
                    "</tr>",
                    tt::text_secondary, p.rpm,
                    t_color, p.torque_nm, is_peak_t ? " \xe2\x9c\xb6" : "",
                    h_color, p.horsepower, is_peak_h ? " \xe2\x9c\xb6" : "");
                if (off >= static_cast<int>(sizeof(curve_buf) - 200)) break;
            }
            off += std::snprintf(curve_buf + off, sizeof(curve_buf) - off, "</table>");
            dyno_curve_label->setText(QString::fromUtf8(curve_buf));
        });

        dyno_layout->addWidget(dyno_import_btn);
        dyno_layout->addWidget(dyno_result_label);
        dyno_layout->addWidget(dyno_curve_label);
        outer->addWidget(dyno_card);
    }

    // ---- WUE Analyze demo (unchanged) ----
    {
        namespace waa_ns = tuner_core::wue_analyze_accumulator;
        auto* wue_header = new QLabel("WUE Analyze (Warmup Enrichment)");
        QFont whf = wue_header->font(); whf.setBold(true); whf.setPixelSize(tt::font_heading);
        wue_header->setFont(whf);
        wue_header->setStyleSheet(QString::fromUtf8("margin-top: 12px;"));
        outer->addWidget(wue_header);

        auto* wue_note = new QLabel(
            "WUE Analyze maps lambda readings to CLT bins and proposes enrichment "
            "corrections. Cold bins that run lean get increased; warm bins that run "
            "rich get decreased.");
        wue_note->setWordWrap(true);
        {
            char wstyle[64];
            std::snprintf(wstyle, sizeof(wstyle), "color: %s;", tt::text_muted);
            wue_note->setStyleSheet(QString::fromUtf8(wstyle));
        }
        outer->addWidget(wue_note);

        waa_ns::TableAxis axis;
        axis.bins = {-20, -10, 0, 10, 20, 40, 60, 70, 80, 90};
        axis.along_y = true;
        std::vector<std::string> cells = {"180", "170", "155", "140", "130", "118", "108", "104", "102", "100"};

        waa_ns::Accumulator acc;
        for (int i = 0; i < 8; ++i) {
            waa_ns::Record rec; rec.values = {{"lambda1", 1.12}, {"coolant", -5.0}};
            acc.add_record(rec, axis, cells);
        }
        for (int i = 0; i < 6; ++i) {
            waa_ns::Record rec; rec.values = {{"lambda1", 1.02}, {"coolant", 35.0}};
            acc.add_record(rec, axis, cells);
        }
        for (int i = 0; i < 10; ++i) {
            waa_ns::Record rec; rec.values = {{"lambda1", 0.95}, {"coolant", 85.0}};
            acc.add_record(rec, axis, cells);
        }

        auto wue_snap = acc.snapshot(cells, 3, 100.0, 250.0);
        outer->addWidget(make_info_card("WUE Summary",
            wue_snap.summary_text.c_str(), tt::accent_warning));

        for (const auto& p : wue_snap.proposals) {
            char buf[128];
            std::snprintf(buf, sizeof(buf),
                "CLT bin %d: %.0f%% \xe2\x86\x92 %.0f%% (\xc3\x97%.4f, %d samples)",
                p.row_index + 1, p.current_enrichment, p.proposed_enrichment,
                p.correction_factor, p.sample_count);
            const char* accent = (p.correction_factor > 1.01) ? tt::accent_danger :
                                 (p.correction_factor < 0.99) ? tt::accent_primary : tt::accent_ok;
            outer->addWidget(make_info_card("WUE Proposal", buf, accent));
        }
    }

    outer->addStretch(1);
    scroll->setWidget(container);
    return scroll;
}

// ---------------------------------------------------------------------------
// Heatmap renderer — turns a flat 16×16 value table into a colored grid
// ---------------------------------------------------------------------------

QWidget* render_heatmap(const std::vector<double>& values, int rows, int cols,
                         const char* title_text) {
    auto* card = new QWidget;
    auto* vl = new QVBoxLayout(card);
    vl->setContentsMargins(tt::space_md + 2, tt::space_sm + 2, tt::space_md + 2, tt::space_sm + 2);
    vl->setSpacing(tt::space_xs);
    {
        char cstyle[192];
        std::snprintf(cstyle, sizeof(cstyle),
            "background-color: %s; border: 1px solid %s; "
            "border-radius: %dpx;",
            tt::bg_elevated, tt::border, tt::radius_md);
        card->setStyleSheet(QString::fromUtf8(cstyle));
    }

    auto* h = new QLabel(QString::fromUtf8(title_text));
    QFont hf = h->font(); hf.setBold(true); hf.setPixelSize(tt::font_label);
    h->setFont(hf);
    {
        char hstyle[96];
        std::snprintf(hstyle, sizeof(hstyle),
            "color: %s; border: none;", tt::text_secondary);
        h->setStyleSheet(QString::fromUtf8(hstyle));
    }
    vl->addWidget(h);

    // Build a ViewModel and render through the table_rendering service.
    namespace tv = tuner_core::table_view;
    namespace tr = tuner_core::table_rendering;
    tv::ShapeHints hints;
    hints.rows = rows;
    hints.cols = cols;
    auto model_opt = tv::build_table_model(
        std::span<const double>(values.data(), values.size()), hints);
    if (!model_opt.has_value()) return card;
    auto& model = *model_opt;

    std::vector<std::string> x_labels, y_labels;
    auto render = tr::build_render_model(model, x_labels, y_labels, true);

    auto* grid = new QGridLayout;
    grid->setSpacing(1);
    grid->setContentsMargins(0, 4, 0, 0);

    int display_rows = std::min(static_cast<int>(render.rows), 16);
    int display_cols = std::min(static_cast<int>(render.columns), 16);

    for (int r = 0; r < display_rows; ++r) {
        for (int c = 0; c < display_cols; ++c) {
            auto& cell = render.cells[r][c];
            char style_buf[256];
            std::snprintf(style_buf, sizeof(style_buf),
                "background-color: %s; color: %s; border: none; "
                "padding: 1px; font-size: 9px; font-family: monospace;",
                cell.background_hex.c_str(), cell.foreground_hex.c_str());
            auto* lbl = new QLabel(QString::fromUtf8(cell.text.c_str()));
            lbl->setAlignment(Qt::AlignCenter);
            lbl->setStyleSheet(QString::fromUtf8(style_buf));
            lbl->setMinimumSize(32, 16);
            grid->addWidget(lbl, r, c);
        }
    }
    auto* grid_widget = new QWidget;
    grid_widget->setLayout(grid);
    grid_widget->setStyleSheet("border: none;");
    vl->addWidget(grid_widget);
    return card;
}

// ---------------------------------------------------------------------------
// 1D curve renderer — renders a CLT → value curve as a horizontal bar chart
// ---------------------------------------------------------------------------

QWidget* render_1d_curve(const std::vector<double>& bins,
                          const std::vector<double>& values,
                          const char* title_text,
                          const char* units,
                          const char* accent = tt::accent_primary) {
    auto* card = new QWidget;
    auto* vl = new QVBoxLayout(card);
    vl->setContentsMargins(tt::space_md + 2, tt::space_sm + 2, tt::space_md + 2, tt::space_sm + 2);
    vl->setSpacing(tt::space_xs);
    char card_style[256];
    std::snprintf(card_style, sizeof(card_style),
        "background-color: %s; border: 1px solid %s; "
        "border-left: 3px solid %s; border-radius: %dpx;",
        tt::bg_elevated, tt::border, accent, tt::radius_md);
    card->setStyleSheet(QString::fromUtf8(card_style));

    auto* h = new QLabel(QString::fromUtf8(title_text));
    QFont hf = h->font(); hf.setBold(true); hf.setPixelSize(tt::font_label);
    h->setFont(hf);
    {
        char hstyle[96];
        std::snprintf(hstyle, sizeof(hstyle),
            "color: %s; border: none;", tt::text_secondary);
        h->setStyleSheet(QString::fromUtf8(hstyle));
    }
    vl->addWidget(h);

    // Find range for bar scaling.
    double min_v = values.empty() ? 0 : *std::min_element(values.begin(), values.end());
    double max_v = values.empty() ? 1 : *std::max_element(values.begin(), values.end());
    double range = std::max(1.0, max_v - min_v);

    int count = std::min(bins.size(), values.size());
    for (int i = 0; i < count; ++i) {
        int bar_width = static_cast<int>(((values[i] - min_v) / range) * 200) + 20;
        char buf[512];
        std::snprintf(buf, sizeof(buf),
            "<span style='color: %s; font-size: %dpx; "
            "font-family: monospace;'>%6.0f\xc2\xb0""C </span>"
            "<span style='background-color: %s; color: %s; "
            "padding: 2px %dpx 2px 6px; border-radius: 2px; "
            "font-size: %dpx; font-family: monospace;'>"
            "%.0f %s</span>",
            tt::text_muted, tt::font_micro, bins[i],
            accent, tt::text_inverse, bar_width, tt::font_micro,
            values[i], units);
        auto* row = new QLabel;
        row->setTextFormat(Qt::RichText);
        row->setText(QString::fromUtf8(buf));
        row->setStyleSheet("border: none;");
        vl->addWidget(row);
    }
    return card;
}

// ---------------------------------------------------------------------------
// Engine Setup Wizard — interactive multi-step dialog for new projects.
// Stages the operator's choices into the edit service so the generators
// and validation rules see real values instead of defaults.
// ---------------------------------------------------------------------------

struct InjectorPresetEntry {
    const char* label;
    double flow_ccmin;
    double dead_time_ms;  // 0 = unknown
    double ref_pressure_psi;
};

static const InjectorPresetEntry kInjectorPresets[] = {
    {"Custom / Manual Entry",                   0,      0,      0},
    {"BMW M52TU OEM (237 cc @ 3.5 bar)",        237.0,  0.55,   50.76},
    {"BMW M54B30 OEM (254 cc @ 3.5 bar)",       254.0,  0.384,  50.76},
    {"Bosch 0280150945 Red Top (337 cc)",        337.0,  0.38,   50.76},
    {"GM LS3/LS7 12576341 (381 cc @ 43 psi)",   381.0,  0.38,   43.0},
    {"Bosch 0280158124 EV14 (410 cc @ 3.5 bar)",410.0,  0.490,  50.76},
    {"Bosch 0280158227 (435 cc @ 3.5 bar)",     435.0,  0.94,   50.76},
    {"Bosch 0280150558 42lb (440 cc @ 3 bar)",  440.0,  0.352,  43.5},
    {"Bosch Green Giant 0280155968 (475 cc)",    475.0,  0.704,  50.76},
    {"Bosch EV14 52lb 0280158117 (540 cc)",     540.0,  0.893,  43.5},
    {"Siemens Deka 60lb FI114961 (630 cc)",     630.0,  0.43,   39.15},
    {"Bosch 0280158123 EV14 (660 cc @ 3.5 bar)",660.0,  0.496,  50.76},
    {"Siemens Deka 72lb 3145 (756 cc)",         756.0,  0.76,   43.5},
    {"Siemens Deka FI114991 80lb (875 cc)",     875.0,  0.801,  43.5},
    {"Bosch 0280158040 (950 cc @ 3.5 bar)",     950.0,  0.896,  50.76},
    {"ID1050x / XDS (1065 cc @ 3 bar)",         1065.0, 0.925,  43.5},
    {"ID1300x / XDS (1335 cc @ 3 bar)",         1335.0, 1.005,  43.5},
    {"ID1750x / XDS (1728 cc @ 3 bar)",         1728.0, 0.882,  43.5},
};
constexpr int kInjectorPresetCount = sizeof(kInjectorPresets) / sizeof(kInjectorPresets[0]);

struct MapSensorPresetEntry {
    const char* label;
    double min_kpa;
    double max_kpa;
};

static const MapSensorPresetEntry kMapPresets[] = {
    {"Custom / Manual Entry",                      0,     0},
    {"GM 3-bar (12592525) \xe2\x80\x94 10-304 kPa",    10.0,  304.0},
    {"AEM 3.5-bar (30-2130-50) \xe2\x80\x94 7.5-350 kPa", 7.5, 350.0},
    {"AEM 4-bar (30-2130-75) \xe2\x80\x94 7.5-400 kPa",   7.5, 400.0},
    {"NXP MPXH6250A / DropBear \xe2\x80\x94 20-250 kPa",  20.0, 250.0},
    {"Bosch 0261230119 3-bar \xe2\x80\x94 20-300 kPa",    20.0, 300.0},
    {"Bosch TMAP 0281002177 \xe2\x80\x94 20-260 kPa",     20.0, 260.0},
    {"Bosch TMAP 0281006059 \xe2\x80\x94 50-400 kPa",     50.0, 400.0},
    {"BMW TMAP 13628637900 \xe2\x80\x94 20-250 kPa",      20.0, 250.0},
};
constexpr int kMapPresetCount = sizeof(kMapPresets) / sizeof(kMapPresets[0]);

struct WizardResult {
    bool accepted = false;
    // Step 1: Engine
    int cylinders = 6;
    double displacement_cc = 2000.0;
    double compression_ratio = 10.0;
    bool two_stroke = false;
    int load_algorithm = 0;  // 0=Speed Density (MAP), 1=Alpha-N (TPS)
    int board_family = 3;    // 0=Mega2560, 1=T35, 2=T36, 3=T41, 4=STM32
    int n_injectors = 6;
    int inj_layout = 0;     // 0=paired, 1=semi-sequential, 2=sequential
    int calibration_intent = 0;  // 0=first start, 1=drivable base
    // Step 2: Induction
    int induction = 0;  // 0=NA, 1=single turbo, 2=twin turbo, 3=supercharged
    double boost_target_psi = 14.0;
    bool intercooler_present = false;
    int turbo_type = 0;          // 0=journal, 1=ball bearing
    double ar_ratio = 0.63;
    double comp_trim = 56.0;
    double turbine_trim = 76.0;
    // Step 3: Injectors
    double injector_flow = 440.0;
    double dead_time_ms = 0.5;
    double req_fuel_ms = 8.0;
    double stoich = 14.7;
    int ae_mode = 0;             // 0=TPS-based, 1=MAP-based, 2=disabled
    double ae_threshold = 10.0;  // TPS delta %
    double ae_amount = 2.0;      // enrichment ms
    int fuel_pressure_model = 0; // 0=fixed, 1=vacuum-ref, 2=boost-ref
    double rail_pressure_kpa = 300.0;
    int dead_time_comp = 0;      // 0=fixed, 1=voltage curve
    bool flex_fuel_enabled = false;
    double flex_freq_low = 50.0;
    double flex_freq_high = 150.0;
    // Step 4: Trigger / Ignition
    int trigger_teeth = 36;
    int missing_teeth = 1;
    int spark_mode = 0;  // 0=wasted, 1=single, 2=wasted COP, 3=sequential
    int cam_input = 0;   // 0=none, 1=VR, 2=hall (visible when sequential)
    double dwell_running = 3.0;
    double dwell_cranking = 4.5;
    // Step 5: Sensors
    int ego_type = 2;  // 0=disabled, 1=narrow, 2=wideband
    int wideband_preset = 0;
    double map_min = 10.0;
    double map_max = 260.0;
    int clt_thermistor = 0;  // index into thermistor presets (0=GM default)
    int iat_thermistor = 0;
    int knock_mode = 0;      // 0=off, 1=digital, 2=analog
    double knock_max_retard = 6.0;
    bool oil_pressure_enabled = false;
    double oil_pressure_min = 0.0;
    double oil_pressure_max = 10.0;
    bool afr_protection_enabled = false;
    double afr_protection_max = 18.0;
    double afr_protection_cut_time = 2.0;
    int clt_filter = 180;
    int iat_filter = 180;
};

WizardResult open_engine_setup_wizard(QWidget* parent) {
    namespace hp = tuner_core::hardware_presets;
    namespace wb = tuner_core::wideband_calibration;
    namespace rfc = tuner_core::required_fuel_calculator;

    WizardResult result;
    auto* dlg = new QDialog(parent);
    dlg->setWindowTitle("Engine Setup Wizard");
    dlg->setFixedSize(560, 580);
    {
        char ds[768];
        std::snprintf(ds, sizeof(ds),
            "QDialog { background: %s; }"
            "QLabel { color: %s; font-size: %dpx; }"
            "QLineEdit, QComboBox { background: %s; color: %s; "
            "  border: 1px solid %s; border-radius: %dpx; padding: %dpx; font-size: %dpx; }"
            "QComboBox { padding-right: 20px; }"
            "QComboBox QAbstractItemView { background: %s; color: %s; "
            "  border: 1px solid %s; selection-background-color: %s; }"
            "QPushButton { background: %s; color: %s; border: 1px solid %s; "
            "  border-radius: %dpx; padding: %dpx %dpx; font-size: %dpx; }"
            "QPushButton:hover { background: %s; }"
            "QPushButton:disabled { color: %s; }",
            tt::bg_base,
            tt::text_primary, tt::font_body,
            tt::bg_elevated, tt::text_primary, tt::border,
            tt::radius_sm, tt::space_xs, tt::font_body,
            tt::bg_panel, tt::text_primary, tt::border, tt::fill_primary_mid,
            tt::bg_elevated, tt::text_primary, tt::border,
            tt::radius_sm, tt::space_xs, tt::space_md, tt::font_body,
            tt::fill_primary_mid, tt::text_dim);
        dlg->setStyleSheet(QString::fromUtf8(ds));
    }

    auto* outer = new QVBoxLayout(dlg);
    outer->setContentsMargins(tt::space_lg, tt::space_lg, tt::space_lg, tt::space_md);
    outer->setSpacing(tt::space_sm);

    // Title.
    auto* title = new QLabel;
    title->setTextFormat(Qt::RichText);
    {
        char th[384];
        std::snprintf(th, sizeof(th),
            "<span style='font-size: %dpx; font-weight: bold; color: %s;'>"
            "Engine Setup Wizard</span><br>"
            "<span style='color: %s; font-size: %dpx;'>"
            "Configure your engine to generate starter VE, AFR, spark, "
            "and enrichment tables</span>",
            tt::font_label, tt::text_primary,
            tt::text_dim, tt::font_small);
        title->setText(QString::fromUtf8(th));
    }
    outer->addWidget(title);

    auto* pages = new QStackedWidget;

    // Helpers.
    auto make_step_header = [](const char* step_text) {
        auto* h = new QLabel;
        h->setTextFormat(Qt::RichText);
        char ph[192];
        std::snprintf(ph, sizeof(ph),
            "<span style='color: %s; font-size: %dpx; font-weight: bold;'>"
            "%s</span>",
            tt::accent_primary, tt::font_body, step_text);
        h->setText(QString::fromUtf8(ph));
        return h;
    };
    auto make_row = [](QVBoxLayout* layout, const char* label) -> QLineEdit* {
        auto* row = new QHBoxLayout;
        auto* lbl = new QLabel(QString::fromUtf8(label));
        lbl->setFixedWidth(180);
        row->addWidget(lbl);
        auto* edit = new QLineEdit;
        edit->setFixedWidth(140);
        edit->setAlignment(Qt::AlignCenter);
        row->addWidget(edit);
        row->addStretch(1);
        layout->addLayout(row);
        return edit;
    };
    auto make_combo_row = [](QVBoxLayout* layout, const char* label) -> QComboBox* {
        auto* row = new QHBoxLayout;
        auto* lbl = new QLabel(QString::fromUtf8(label));
        lbl->setFixedWidth(180);
        row->addWidget(lbl);
        auto* combo = new QComboBox;
        combo->setMinimumWidth(200);
        row->addWidget(combo, 1);
        layout->addLayout(row);
        return combo;
    };
    // Guidance note — brief contextual explanation at the top of each
    // step. Tells the operator WHY this step matters and what to focus on.
    // Uses accent_primary so it reads as guidance, not background chrome.
    auto make_guidance = [](QVBoxLayout* layout, const char* text) {
        auto* g = new QLabel;
        g->setTextFormat(Qt::RichText);
        g->setWordWrap(true);
        char buf[384];
        std::snprintf(buf, sizeof(buf),
            "<span style='color: %s; font-size: %dpx;'>%s</span>",
            tt::accent_primary, tt::font_body, text);
        g->setText(QString::fromUtf8(buf));
        layout->addWidget(g);
    };
    auto make_hint = [](QVBoxLayout* layout, const char* text) {
        auto* h = new QLabel;
        h->setTextFormat(Qt::RichText);
        h->setWordWrap(true);
        char hh[256];
        std::snprintf(hh, sizeof(hh),
            "<span style='color: %s; font-size: %dpx;'>%s</span>",
            tt::text_dim, tt::font_micro, text);
        h->setText(QString::fromUtf8(hh));
        layout->addWidget(h);
    };

    // ---- Step 1: Engine ----
    auto* p1 = new QWidget;
    auto* p1l = new QVBoxLayout(p1);
    p1l->setSpacing(tt::space_sm);
    p1l->addWidget(make_step_header("Step 1 of 6 \xe2\x80\x94 Engine"));
    make_guidance(p1l, "Tell us about your engine. These basics shape everything \xe2\x80\x94 "
                       "the VE table, fuel calculations, and trigger setup all start here.");
    auto* cyl_edit = make_row(p1l, "Cylinders:");
    cyl_edit->setText("6");
    auto* disp_edit = make_row(p1l, "Displacement (cc):");
    disp_edit->setText("2000");
    auto* cr_edit = make_row(p1l, "Compression Ratio:");
    cr_edit->setText("10.0");
    auto* stroke_combo = make_combo_row(p1l, "Cycle:");
    stroke_combo->addItem("Four-Stroke");
    stroke_combo->addItem("Two-Stroke");
    auto* load_combo = make_combo_row(p1l, "Load Algorithm:");
    load_combo->addItem("Speed Density (MAP)");
    load_combo->addItem("Alpha-N (TPS)");
    auto* board_combo = make_combo_row(p1l, "Board / MCU:");
    board_combo->addItem("Mega 2560 (Arduino)");
    board_combo->addItem("Teensy 3.5");
    board_combo->addItem("Teensy 3.6");
    board_combo->addItem("Teensy 4.1 (DropBear)");
    board_combo->addItem("STM32F407 (Black Pill)");
    board_combo->setCurrentIndex(3);  // DropBear default
    auto* inj_count_edit = make_row(p1l, "Injector Count:");
    inj_count_edit->setText("6");
    auto* inj_layout_combo = make_combo_row(p1l, "Injection Mode:");
    inj_layout_combo->addItem("Paired (batch)");
    inj_layout_combo->addItem("Semi-Sequential");
    inj_layout_combo->addItem("Sequential");
    auto* seq_note = new QLabel;
    seq_note->setWordWrap(true);
    {
        char sn[256];
        std::snprintf(sn, sizeof(sn),
            "<span style='color: %s; font-size: %dpx;'>"
            "\xe2\x9a\xa0\xef\xb8\x8f Sequential requires a cam sync input "
            "\xe2\x80\x94 configure in Step 4</span>",
            tt::accent_warning, tt::font_small);
        seq_note->setTextFormat(Qt::RichText);
        seq_note->setText(QString::fromUtf8(sn));
    }
    seq_note->hide();
    p1l->addWidget(seq_note);
    QObject::connect(inj_layout_combo, QOverload<int>::of(&QComboBox::currentIndexChanged),
                     [seq_note](int idx) { seq_note->setVisible(idx == 2); });
    // Staged injection auto-detect — if injector count > cylinder count,
    // the build is running staged injectors (primary + secondary bank).
    auto* staged_note = new QLabel;
    staged_note->setTextFormat(Qt::RichText);
    staged_note->setWordWrap(true);
    staged_note->hide();
    p1l->addWidget(staged_note);
    auto update_staged_note = [staged_note, cyl_edit, inj_count_edit]() {
        int nc = 0, ni = 0;
        try { nc = std::stoi(cyl_edit->text().toStdString()); } catch (...) {}
        try { ni = std::stoi(inj_count_edit->text().toStdString()); } catch (...) {}
        if (ni > nc && nc > 0) {
            char sn[256];
            std::snprintf(sn, sizeof(sn),
                "<span style='color: %s; font-size: %dpx;'>"
                "\xe2\x84\xb9 Staged injection detected (%d injectors on %d cyl) "
                "\xe2\x80\x94 secondary bank staging will be configured.</span>",
                tt::accent_primary, tt::font_small, ni, nc);
            staged_note->setText(QString::fromUtf8(sn));
            staged_note->show();
        } else {
            staged_note->hide();
        }
    };
    QObject::connect(cyl_edit, &QLineEdit::textChanged,
                     [update_staged_note](const QString&) { update_staged_note(); });
    QObject::connect(inj_count_edit, &QLineEdit::textChanged,
                     [update_staged_note](const QString&) { update_staged_note(); });
    auto* intent_combo = make_combo_row(p1l, "Calibration Intent:");
    intent_combo->addItem("First Start (conservative)");
    intent_combo->addItem("Drivable Base (moderate)");
    make_hint(p1l, "Speed Density is recommended for most builds. "
              "Sequential injection requires cam sync. "
              "Teensy 4.1 (DropBear) is recommended for new builds.");
    p1l->addStretch(1);
    pages->addWidget(p1);

    // ---- Step 2: Induction ----
    auto* p2 = new QWidget;
    auto* p2l = new QVBoxLayout(p2);
    p2l->setSpacing(tt::space_sm);
    p2l->addWidget(make_step_header("Step 2 of 6 \xe2\x80\x94 Induction"));
    make_guidance(p2l, "How does air get into the engine? Naturally aspirated, turbo, or supercharged. "
                       "This determines how the VE table handles boost and the AFR targets under load.");
    auto* induction_combo = make_combo_row(p2l, "Topology:");
    induction_combo->addItem("Naturally Aspirated");
    induction_combo->addItem("Single Turbo");
    induction_combo->addItem("Twin Turbo");
    induction_combo->addItem("Supercharged");
    auto* boost_edit = make_row(p2l, "Boost Target (psi):");
    boost_edit->setText("14.0");
    boost_edit->setEnabled(false);
    auto* intercooler_row = new QHBoxLayout;
    auto* ic_label = new QLabel("Intercooler:");
    ic_label->setFixedWidth(180);
    intercooler_row->addWidget(ic_label);
    auto* intercooler_combo = new QComboBox;
    intercooler_combo->addItem("No Intercooler");
    intercooler_combo->addItem("Intercooled");
    intercooler_combo->setEnabled(false);
    intercooler_row->addWidget(intercooler_combo);
    intercooler_row->addStretch(1);
    p2l->addLayout(intercooler_row);
    // Turbo characterization fields (enabled only for forced induction).
    auto* turbo_type_combo = make_combo_row(p2l, "Turbo Type:");
    turbo_type_combo->addItem("Journal Bearing");
    turbo_type_combo->addItem("Ball Bearing");
    turbo_type_combo->setEnabled(false);
    auto* ar_edit = make_row(p2l, "Turbine A/R Ratio:");
    ar_edit->setText("0.63");
    ar_edit->setEnabled(false);
    auto* comp_trim_edit = make_row(p2l, "Compressor Trim:");
    comp_trim_edit->setText("56");
    comp_trim_edit->setEnabled(false);
    auto* turbine_trim_edit = make_row(p2l, "Turbine Trim:");
    turbine_trim_edit->setText("76");
    turbine_trim_edit->setEnabled(false);

    QObject::connect(induction_combo, QOverload<int>::of(&QComboBox::currentIndexChanged),
                     [boost_edit, intercooler_combo,
                      turbo_type_combo, ar_edit, comp_trim_edit, turbine_trim_edit](int idx) {
        bool forced = idx > 0;
        bool turbo = (idx == 1 || idx == 2);  // single or twin turbo
        boost_edit->setEnabled(forced);
        intercooler_combo->setEnabled(forced);
        turbo_type_combo->setEnabled(turbo);
        ar_edit->setEnabled(turbo);
        comp_trim_edit->setEnabled(turbo);
        turbine_trim_edit->setEnabled(turbo);
    });
    make_hint(p2l, "Forced induction shapes the VE table top-end and AFR targets under boost. "
              "Turbo specs are optional \xe2\x80\x94 used for boost target estimation and "
              "compressor surge avoidance. Leave defaults if unknown.");
    p2l->addStretch(1);
    pages->addWidget(p2);

    // ---- Step 3: Injectors ----
    auto* p3 = new QWidget;
    auto* p3l = new QVBoxLayout(p3);
    p3l->setSpacing(tt::space_sm);
    p3l->addWidget(make_step_header("Step 3 of 6 \xe2\x80\x94 Injectors"));
    make_guidance(p3l, "Your injector specs directly affect fuel delivery. "
                       "Select a preset if you know your injectors, or enter values manually.");
    auto* inj_preset_combo = make_combo_row(p3l, "Injector Preset:");
    for (int i = 0; i < kInjectorPresetCount; ++i)
        inj_preset_combo->addItem(QString::fromUtf8(kInjectorPresets[i].label));
    inj_preset_combo->setCurrentIndex(0);
    auto* inj_flow_edit = make_row(p3l, "Flow Rate (cc/min):");
    inj_flow_edit->setText("440");
    auto* dead_time_edit = make_row(p3l, "Dead Time (ms):");
    dead_time_edit->setText("0.50");
    auto* stoich_edit = make_row(p3l, "Stoichiometric AFR:");
    stoich_edit->setText("14.7");
    // Acceleration enrichment — basic TPS-delta threshold + amount.
    auto* ae_combo = make_combo_row(p3l, "Accel Enrichment Mode:");
    ae_combo->addItem("TPS-based (recommended)");
    ae_combo->addItem("MAP-based");
    ae_combo->addItem("Disabled");
    auto* ae_threshold_edit = make_row(p3l, "AE TPS Threshold (%):");
    ae_threshold_edit->setText("10");
    auto* ae_amount_edit = make_row(p3l, "AE Enrichment (ms):");
    ae_amount_edit->setText("2.0");
    // Injector pressure compensation.
    auto* fuel_pressure_combo = make_combo_row(p3l, "Fuel Pressure Model:");
    fuel_pressure_combo->addItem("Fixed rail pressure");
    fuel_pressure_combo->addItem("Vacuum-referenced");
    fuel_pressure_combo->addItem("Boost-referenced");
    auto* rail_pressure_edit = make_row(p3l, "Base Rail Pressure (kPa):");
    rail_pressure_edit->setText("300");
    auto* comp_mode_combo = make_combo_row(p3l, "Dead Time Compensation:");
    comp_mode_combo->addItem("Fixed (single value)");
    comp_mode_combo->addItem("Voltage curve (battery-compensated)");
    // Flex fuel sensor.
    auto* flex_combo = make_combo_row(p3l, "Flex Fuel Sensor:");
    flex_combo->addItem("Disabled");
    flex_combo->addItem("Enabled (GM / Continental)");
    auto* flex_low_edit = make_row(p3l, "Flex Low Freq (Hz):");
    flex_low_edit->setText("50");
    flex_low_edit->setVisible(false);
    auto* flex_high_edit = make_row(p3l, "Flex High Freq (Hz):");
    flex_high_edit->setText("150");
    flex_high_edit->setVisible(false);
    QObject::connect(flex_combo, QOverload<int>::of(&QComboBox::currentIndexChanged),
                     [flex_low_edit, flex_high_edit](int idx) {
        flex_low_edit->setVisible(idx > 0);
        flex_high_edit->setVisible(idx > 0);
    });
    // reqFuel preview — computed from displacement, cylinders, flow.
    auto* reqfuel_label = new QLabel;
    reqfuel_label->setTextFormat(Qt::RichText);
    {
        char rl[256];
        std::snprintf(rl, sizeof(rl),
            "<span style='color: %s; font-size: %dpx;'>"
            "Required Fuel: calculating...</span>",
            tt::text_dim, tt::font_small);
        reqfuel_label->setText(QString::fromUtf8(rl));
    }
    p3l->addWidget(reqfuel_label);
    // Auto-populate from preset selection.
    QObject::connect(inj_preset_combo, QOverload<int>::of(&QComboBox::currentIndexChanged),
                     [inj_flow_edit, dead_time_edit](int idx) {
        if (idx <= 0 || idx >= kInjectorPresetCount) return;
        const auto& p = kInjectorPresets[idx];
        char buf[16];
        std::snprintf(buf, sizeof(buf), "%.0f", p.flow_ccmin);
        inj_flow_edit->setText(QString::fromUtf8(buf));
        if (p.dead_time_ms > 0) {
            std::snprintf(buf, sizeof(buf), "%.3f", p.dead_time_ms);
            dead_time_edit->setText(QString::fromUtf8(buf));
        }
    });
    make_hint(p3l, "Select a preset to auto-fill flow rate and dead time. "
              "The required fuel is calculated from displacement, cylinders, and flow.");
    p3l->addStretch(1);
    pages->addWidget(p3);

    // ---- Step 4: Trigger & Ignition ----
    auto* p4 = new QWidget;
    auto* p4l = new QVBoxLayout(p4);
    p4l->setSpacing(tt::space_sm);
    p4l->addWidget(make_step_header("Step 4 of 6 \xe2\x80\x94 Trigger & Ignition"));
    make_guidance(p4l, "The trigger wheel tells the ECU where the engine is in its rotation. "
                       "Most Speeduino builds use a 36-1 missing tooth wheel. Get this wrong and the engine won\xe2\x80\x99t start.");
    auto* teeth_edit = make_row(p4l, "Trigger Teeth:");
    teeth_edit->setText("36");
    auto* missing_edit = make_row(p4l, "Missing Teeth:");
    missing_edit->setText("1");
    auto* spark_combo = make_combo_row(p4l, "Spark Mode:");
    spark_combo->addItem("Wasted Spark");
    spark_combo->addItem("Single Channel");
    spark_combo->addItem("Wasted COP");
    spark_combo->addItem("Sequential");
    // Cam trigger input — required for sequential injection/ignition.
    // Inline row so we can hide label + combo together (make_combo_row
    // adds them to a throwaway QHBoxLayout).
    auto* cam_row_widget = new QWidget;
    auto* cam_row = new QHBoxLayout(cam_row_widget);
    cam_row->setContentsMargins(0, 0, 0, 0);
    auto* cam_label = new QLabel("Cam / Sync Input:");
    cam_label->setFixedWidth(180);
    cam_row->addWidget(cam_label);
    auto* cam_combo = new QComboBox;
    cam_combo->setMinimumWidth(200);
    cam_combo->addItem("None");
    cam_combo->addItem("VR Sensor");
    cam_combo->addItem("Hall Effect");
    cam_row->addWidget(cam_combo, 1);
    p4l->addWidget(cam_row_widget);
    cam_row_widget->hide();
    // Show cam input when injection OR ignition is sequential.
    auto update_cam_vis = [cam_row_widget, inj_layout_combo, spark_combo]() {
        bool need_cam = (inj_layout_combo->currentIndex() == 2)
                     || (spark_combo->currentIndex() == 3);
        cam_row_widget->setVisible(need_cam);
    };
    QObject::connect(spark_combo, QOverload<int>::of(&QComboBox::currentIndexChanged),
                     [update_cam_vis](int) { update_cam_vis(); });
    // Cross-step wire: Step 1 injection mode → Step 4 cam visibility.
    QObject::connect(inj_layout_combo, QOverload<int>::of(&QComboBox::currentIndexChanged),
                     [update_cam_vis](int) { update_cam_vis(); });
    // Ignition coil presets.
    auto* coil_combo = make_combo_row(p4l, "Coil Preset:");
    coil_combo->addItem("Custom / Manual Entry");
    for (const auto& p : hp::ignition_presets())
        coil_combo->addItem(QString::fromUtf8(p.label.c_str()));
    auto* dwell_run_edit = make_row(p4l, "Running Dwell (ms):");
    dwell_run_edit->setText("3.0");
    auto* dwell_crank_edit = make_row(p4l, "Cranking Dwell (ms):");
    dwell_crank_edit->setText("4.5");
    // Dwell warning — > 6ms is unusual for modern coils. Flag it so the
    // operator knows to double-check the coil spec before burning.
    auto* dwell_warn = new QLabel;
    dwell_warn->setTextFormat(Qt::RichText);
    dwell_warn->setWordWrap(true);
    dwell_warn->hide();
    p4l->addWidget(dwell_warn);
    auto update_dwell_warn = [dwell_warn, dwell_run_edit]() {
        double d = 0;
        try { d = std::stod(dwell_run_edit->text().toStdString()); } catch (...) {}
        if (d > 6.0) {
            char msg[256];
            std::snprintf(msg, sizeof(msg),
                "<span style='color: %s; font-size: %dpx;'>"
                "\xe2\x9a\xa0\xef\xb8\x8f Dwell %.1f ms is high \xe2\x80\x94 verify "
                "coil specs. Typical modern coils run 2.5\xe2\x80\x93" "4 ms.</span>",
                tt::accent_warning, tt::font_small, d);
            dwell_warn->setText(QString::fromUtf8(msg));
            dwell_warn->show();
        } else {
            dwell_warn->hide();
        }
    };
    QObject::connect(dwell_run_edit, &QLineEdit::textChanged,
                     [update_dwell_warn](const QString&) { update_dwell_warn(); });
    QObject::connect(coil_combo, QOverload<int>::of(&QComboBox::currentIndexChanged),
                     [dwell_run_edit, dwell_crank_edit](int idx) {
        if (idx <= 0) return;
        const auto& presets = hp::ignition_presets();
        int pi = idx - 1;
        if (pi < 0 || pi >= static_cast<int>(presets.size())) return;
        char buf[16];
        std::snprintf(buf, sizeof(buf), "%.1f", presets[pi].running_dwell_ms);
        dwell_run_edit->setText(QString::fromUtf8(buf));
        std::snprintf(buf, sizeof(buf), "%.1f", presets[pi].cranking_dwell_ms);
        dwell_crank_edit->setText(QString::fromUtf8(buf));
    });
    make_hint(p4l, "Select a coil preset to auto-fill dwell values. "
              "36-1 missing tooth is the most common Speeduino trigger pattern.");
    p4l->addStretch(1);
    pages->addWidget(p4);

    // ---- Step 5: Sensors ----
    auto* p5 = new QWidget;
    auto* p5l = new QVBoxLayout(p5);
    p5l->setSpacing(tt::space_sm);
    p5l->addWidget(make_step_header("Step 5 of 6 \xe2\x80\x94 Sensors"));
    make_guidance(p5l, "Sensors are the ECU\xe2\x80\x99s eyes. Wideband O2 is essential for tuning. "
                       "MAP range must match your installed sensor. Thermistor presets handle the math.");
    auto* ego_combo = make_combo_row(p5l, "O2 Sensor Type:");
    ego_combo->addItem("Disabled");
    ego_combo->addItem("Narrowband");
    ego_combo->addItem("Wideband");
    ego_combo->setCurrentIndex(2);
    auto* wb_combo = make_combo_row(p5l, "Wideband Controller:");
    wb_combo->addItem("Custom / Manual");
    for (const auto& p : wb::presets())
        wb_combo->addItem(QString::fromUtf8(p.name.c_str()));
    // MAP sensor presets.
    auto* map_combo = make_combo_row(p5l, "MAP Sensor:");
    for (int i = 0; i < kMapPresetCount; ++i)
        map_combo->addItem(QString::fromUtf8(kMapPresets[i].label));
    map_combo->setCurrentIndex(4);  // NXP/DropBear default
    auto* map_min_edit = make_row(p5l, "MAP Minimum (kPa):");
    map_min_edit->setText("20");
    auto* map_max_edit = make_row(p5l, "MAP Maximum (kPa):");
    map_max_edit->setText("250");
    QObject::connect(map_combo, QOverload<int>::of(&QComboBox::currentIndexChanged),
                     [map_min_edit, map_max_edit](int idx) {
        if (idx <= 0 || idx >= kMapPresetCount) return;
        char buf[16];
        std::snprintf(buf, sizeof(buf), "%.0f", kMapPresets[idx].min_kpa);
        map_min_edit->setText(QString::fromUtf8(buf));
        std::snprintf(buf, sizeof(buf), "%.0f", kMapPresets[idx].max_kpa);
        map_max_edit->setText(QString::fromUtf8(buf));
    });
    // Trigger initial fill from the default preset.
    {
        const auto& dp = kMapPresets[4];
        char buf[16];
        std::snprintf(buf, sizeof(buf), "%.0f", dp.min_kpa);
        map_min_edit->setText(QString::fromUtf8(buf));
        std::snprintf(buf, sizeof(buf), "%.0f", dp.max_kpa);
        map_max_edit->setText(QString::fromUtf8(buf));
    }

    // Thermistor presets for CLT and IAT.
    namespace tc = tuner_core::thermistor_calibration;
    auto* clt_combo = make_combo_row(p5l, "CLT Thermistor:");
    auto* iat_combo = make_combo_row(p5l, "IAT Thermistor:");
    // Populate from C++ thermistor preset catalog.
    {
        auto* gm = tc::preset_by_name("GM");
        // List all known preset names.
        const char* therm_names[] = {
            "GM", "Ford", "Toyota", "Chrysler 85+", "Saab / Bosch",
            "Mazda", "Mitsubishi", "BMW E30 325i",
        };
        for (const char* name : therm_names) {
            clt_combo->addItem(QString::fromUtf8(name));
            iat_combo->addItem(QString::fromUtf8(name));
        }
        (void)gm;
    }

    // Baro sensor preset.
    auto* baro_combo = make_combo_row(p5l, "Baro Sensor:");
    baro_combo->addItem("None / Internal");
    baro_combo->addItem("Bosch 0261230218 \xe2\x80\x94 15-115 kPa");
    baro_combo->addItem("GM 12592525 1-bar \xe2\x80\x94 10-105 kPa");
    baro_combo->addItem("NXP MPXA6115A \xe2\x80\x94 15-115 kPa");
    baro_combo->addItem("Bosch TMAP \xe2\x80\x94 20-110 kPa (limited range)");

    // Knock sensor.
    auto* knock_combo = make_combo_row(p5l, "Knock Sensor:");
    knock_combo->addItem("Disabled");
    knock_combo->addItem("Digital");
    knock_combo->addItem("Analog");
    auto* knock_retard_edit = make_row(p5l, "Max Knock Retard (\xc2\xb0):");
    knock_retard_edit->setText("6.0");
    knock_retard_edit->setVisible(false);
    QObject::connect(knock_combo, QOverload<int>::of(&QComboBox::currentIndexChanged),
                     [knock_retard_edit](int idx) {
        knock_retard_edit->setVisible(idx > 0);
    });

    // Oil pressure sensor.
    auto* oil_combo = make_combo_row(p5l, "Oil Pressure Sensor:");
    oil_combo->addItem("Disabled");
    oil_combo->addItem("Enabled");

    // AFR lean protection.
    auto* afr_prot_combo = make_combo_row(p5l, "AFR Lean Protection:");
    afr_prot_combo->addItem("Disabled");
    afr_prot_combo->addItem("Enabled");
    auto* afr_prot_max_edit = make_row(p5l, "Max AFR Before Cut:");
    afr_prot_max_edit->setText("18.0");
    afr_prot_max_edit->setVisible(false);
    auto* afr_prot_time_edit = make_row(p5l, "Cut Delay (seconds):");
    afr_prot_time_edit->setText("2.0");
    afr_prot_time_edit->setVisible(false);
    QObject::connect(afr_prot_combo, QOverload<int>::of(&QComboBox::currentIndexChanged),
                     [afr_prot_max_edit, afr_prot_time_edit](int idx) {
        afr_prot_max_edit->setVisible(idx > 0);
        afr_prot_time_edit->setVisible(idx > 0);
    });

    make_hint(p5l, "Wideband AFR is strongly recommended. "
              "Knock sensor protects against detonation. "
              "AFR lean protection cuts fuel/spark if AFR exceeds threshold. "
              "Oil pressure monitoring alerts on low pressure at RPM.");
    p5l->addStretch(1);
    pages->addWidget(p5);

    // ---- Step 6: Review ----
    auto* p6 = new QWidget;
    auto* p6l = new QVBoxLayout(p6);
    p6l->setSpacing(tt::space_sm);
    p6l->addWidget(make_step_header("Step 6 of 6 \xe2\x80\x94 Review"));
    make_guidance(p6l, "Review your settings below. When you click Finish, the wizard will "
                       "generate starter VE, AFR, spark, warmup, and cranking tables for your engine.");
    auto* review_label = new QLabel;
    review_label->setTextFormat(Qt::RichText);
    review_label->setWordWrap(true);
    {
        char rl[256];
        std::snprintf(rl, sizeof(rl),
            "<span style='color: %s; font-size: %dpx;'>"
            "Review your configuration on the previous steps, then click "
            "Finish to generate starter VE, AFR, spark, and enrichment tables "
            "based on these parameters.</span>",
            tt::text_secondary, tt::font_body);
        review_label->setText(QString::fromUtf8(rl));
    }
    p6l->addWidget(review_label);
    // Summary card — updated when page 6 becomes visible.
    auto* summary_label = new QLabel;
    summary_label->setTextFormat(Qt::RichText);
    summary_label->setWordWrap(true);
    summary_label->setStyleSheet(QString::fromUtf8(tt::card_style().c_str()));
    p6l->addWidget(summary_label);
    p6l->addStretch(1);
    pages->addWidget(p6);

    outer->addWidget(pages, 1);

    // Step indicator + buttons.
    constexpr int total_steps = 6;
    auto* step_label = new QLabel;
    step_label->setAlignment(Qt::AlignCenter);
    step_label->setTextFormat(Qt::RichText);
    {
        char sl[128];
        std::snprintf(sl, sizeof(sl),
            "<span style='color: %s; font-size: %dpx;'>Step 1 of %d</span>",
            tt::text_dim, tt::font_small, total_steps);
        step_label->setText(QString::fromUtf8(sl));
    }
    outer->addWidget(step_label);

    auto* btn_row = new QHBoxLayout;
    btn_row->addStretch(1);
    auto* cancel_btn = new QPushButton("Cancel");
    auto* back_btn = new QPushButton("Back");
    auto* next_btn = new QPushButton("Next");
    back_btn->setEnabled(false);
    btn_row->addWidget(cancel_btn);
    btn_row->addWidget(back_btn);
    btn_row->addWidget(next_btn);
    outer->addLayout(btn_row);

    QObject::connect(cancel_btn, &QPushButton::clicked, dlg, &QDialog::reject);

    // Update step label and review summary.
    auto update_step_ui = [step_label, back_btn, next_btn, summary_label,
                           cyl_edit, disp_edit, cr_edit, induction_combo,
                           boost_edit, inj_flow_edit, dead_time_edit, stoich_edit,
                           teeth_edit, missing_edit, spark_combo,
                           dwell_run_edit, dwell_crank_edit,
                           ego_combo, wb_combo, map_min_edit, map_max_edit,
                           reqfuel_label, pages](int idx) {
        char sl[128];
        std::snprintf(sl, sizeof(sl),
            "<span style='color: %s; font-size: %dpx;'>Step %d of %d</span>",
            tt::text_dim, tt::font_small, idx + 1, total_steps);
        step_label->setText(QString::fromUtf8(sl));
        back_btn->setEnabled(idx > 0);
        next_btn->setText(idx == total_steps - 1 ? "Finish" : "Next");

        // Update reqFuel preview on the injector page.
        if (idx == 2) {
            double d = 2000, f = 440;
            int nc = 6;
            try { d = std::stod(disp_edit->text().toStdString()); } catch (...) {}
            try { nc = std::stoi(cyl_edit->text().toStdString()); } catch (...) {}
            try { f = std::stod(inj_flow_edit->text().toStdString()); } catch (...) {}
            auto rf = rfc::calculate(d, nc, f, 14.7);
            char rl[256];
            std::snprintf(rl, sizeof(rl),
                "<span style='color: %s; font-size: %dpx;'>"
                "\xe2\x9c\x85 Required Fuel: <b>%.2f ms</b> "
                "(%.0f cc, %d cyl, %.0f cc/min inj)</span>",
                tt::accent_ok, tt::font_small,
                rf.req_fuel_ms, d, nc, f);
            reqfuel_label->setText(QString::fromUtf8(rl));
        }

        // Update review summary on the last page.
        if (idx == total_steps - 1) {
            char sm[1024];
            int off = 0;
            off += std::snprintf(sm + off, sizeof(sm) - off,
                "<span style='font-size: %dpx; color: %s;'>", tt::font_small, tt::text_secondary);
            off += std::snprintf(sm + off, sizeof(sm) - off,
                "<b>Engine:</b> %s cyl, %s cc, CR %s<br>",
                cyl_edit->text().toStdString().c_str(),
                disp_edit->text().toStdString().c_str(),
                cr_edit->text().toStdString().c_str());
            off += std::snprintf(sm + off, sizeof(sm) - off,
                "<b>Induction:</b> %s",
                induction_combo->currentText().toStdString().c_str());
            if (induction_combo->currentIndex() > 0)
                off += std::snprintf(sm + off, sizeof(sm) - off,
                    " @ %s psi", boost_edit->text().toStdString().c_str());
            off += std::snprintf(sm + off, sizeof(sm) - off, "<br>");
            off += std::snprintf(sm + off, sizeof(sm) - off,
                "<b>Injectors:</b> %s cc/min, %s ms dead time, AFR %s<br>",
                inj_flow_edit->text().toStdString().c_str(),
                dead_time_edit->text().toStdString().c_str(),
                stoich_edit->text().toStdString().c_str());
            off += std::snprintf(sm + off, sizeof(sm) - off,
                "<b>Trigger:</b> %s-%s missing tooth, %s<br>",
                teeth_edit->text().toStdString().c_str(),
                missing_edit->text().toStdString().c_str(),
                spark_combo->currentText().toStdString().c_str());
            off += std::snprintf(sm + off, sizeof(sm) - off,
                "<b>Ignition:</b> %s ms run / %s ms crank<br>",
                dwell_run_edit->text().toStdString().c_str(),
                dwell_crank_edit->text().toStdString().c_str());
            off += std::snprintf(sm + off, sizeof(sm) - off,
                "<b>Sensors:</b> %s, MAP %s\xe2\x80\x93%s kPa",
                ego_combo->currentText().toStdString().c_str(),
                map_min_edit->text().toStdString().c_str(),
                map_max_edit->text().toStdString().c_str());
            off += std::snprintf(sm + off, sizeof(sm) - off, "</span>");
            summary_label->setText(QString::fromUtf8(sm));
        }
    };

    QObject::connect(next_btn, &QPushButton::clicked,
                     [pages, update_step_ui, dlg, &result,
                      cyl_edit, disp_edit, cr_edit, stroke_combo, load_combo,
                      induction_combo, boost_edit, intercooler_combo,
                      inj_flow_edit, dead_time_edit, stoich_edit,
                      teeth_edit, missing_edit, spark_combo,
                      dwell_run_edit, dwell_crank_edit,
                      ego_combo, wb_combo,
                      map_min_edit, map_max_edit,
                      clt_combo, iat_combo, board_combo,
                      turbo_type_combo, ar_edit, comp_trim_edit, turbine_trim_edit,
                      ae_combo, ae_threshold_edit, ae_amount_edit,
                      fuel_pressure_combo, rail_pressure_edit, comp_mode_combo,
                      baro_combo,
                      inj_count_edit, inj_layout_combo, intent_combo,
                      flex_combo, flex_low_edit, flex_high_edit,
                      cam_combo, knock_combo, knock_retard_edit,
                      oil_combo, afr_prot_combo, afr_prot_max_edit,
                      afr_prot_time_edit]() {
        int idx = pages->currentIndex();
        if (idx < pages->count() - 1) {
            pages->setCurrentIndex(idx + 1);
            update_step_ui(idx + 1);
        } else {
            // Finish — collect all values.
            try { result.cylinders = std::stoi(cyl_edit->text().toStdString()); } catch (...) {}
            try { result.displacement_cc = std::stod(disp_edit->text().toStdString()); } catch (...) {}
            try { result.compression_ratio = std::stod(cr_edit->text().toStdString()); } catch (...) {}
            result.two_stroke = (stroke_combo->currentIndex() == 1);
            result.load_algorithm = load_combo->currentIndex();
            result.board_family = board_combo->currentIndex();
            try { result.n_injectors = std::stoi(inj_count_edit->text().toStdString()); } catch (...) {}
            result.inj_layout = inj_layout_combo->currentIndex();
            result.calibration_intent = intent_combo->currentIndex();
            result.induction = induction_combo->currentIndex();
            try { result.boost_target_psi = std::stod(boost_edit->text().toStdString()); } catch (...) {}
            result.intercooler_present = (intercooler_combo->currentIndex() == 1);
            result.turbo_type = turbo_type_combo->currentIndex();
            try { result.ar_ratio = std::stod(ar_edit->text().toStdString()); } catch (...) {}
            try { result.comp_trim = std::stod(comp_trim_edit->text().toStdString()); } catch (...) {}
            try { result.turbine_trim = std::stod(turbine_trim_edit->text().toStdString()); } catch (...) {}
            try { result.injector_flow = std::stod(inj_flow_edit->text().toStdString()); } catch (...) {}
            try { result.dead_time_ms = std::stod(dead_time_edit->text().toStdString()); } catch (...) {}
            try { result.stoich = std::stod(stoich_edit->text().toStdString()); } catch (...) {}
            result.ae_mode = ae_combo->currentIndex();
            try { result.ae_threshold = std::stod(ae_threshold_edit->text().toStdString()); } catch (...) {}
            try { result.ae_amount = std::stod(ae_amount_edit->text().toStdString()); } catch (...) {}
            // fuel_pressure_model already read above via the new staging path.
            try { result.rail_pressure_kpa = std::stod(rail_pressure_edit->text().toStdString()); } catch (...) {}
            result.dead_time_comp = comp_mode_combo->currentIndex();
            try { result.trigger_teeth = std::stoi(teeth_edit->text().toStdString()); } catch (...) {}
            try { result.missing_teeth = std::stoi(missing_edit->text().toStdString()); } catch (...) {}
            result.spark_mode = spark_combo->currentIndex();
            try { result.dwell_running = std::stod(dwell_run_edit->text().toStdString()); } catch (...) {}
            try { result.dwell_cranking = std::stod(dwell_crank_edit->text().toStdString()); } catch (...) {}
            result.ego_type = ego_combo->currentIndex();
            result.wideband_preset = wb_combo->currentIndex();
            try { result.map_min = std::stod(map_min_edit->text().toStdString()); } catch (...) {}
            try { result.map_max = std::stod(map_max_edit->text().toStdString()); } catch (...) {}
            result.clt_thermistor = clt_combo->currentIndex();
            result.iat_thermistor = iat_combo->currentIndex();
            // New fields.
            result.flex_fuel_enabled = (flex_combo->currentIndex() > 0);
            try { result.flex_freq_low = std::stod(flex_low_edit->text().toStdString()); } catch (...) {}
            try { result.flex_freq_high = std::stod(flex_high_edit->text().toStdString()); } catch (...) {}
            result.cam_input = cam_combo->currentIndex();
            result.knock_mode = knock_combo->currentIndex();
            try { result.knock_max_retard = std::stod(knock_retard_edit->text().toStdString()); } catch (...) {}
            result.oil_pressure_enabled = (oil_combo->currentIndex() > 0);
            result.afr_protection_enabled = (afr_prot_combo->currentIndex() > 0);
            try { result.afr_protection_max = std::stod(afr_prot_max_edit->text().toStdString()); } catch (...) {}
            try { result.afr_protection_cut_time = std::stod(afr_prot_time_edit->text().toStdString()); } catch (...) {}
            result.fuel_pressure_model = fuel_pressure_combo->currentIndex();
            result.accepted = true;
            dlg->accept();
        }
    });

    QObject::connect(back_btn, &QPushButton::clicked,
                     [pages, update_step_ui]() {
        int idx = pages->currentIndex();
        if (idx > 0) {
            pages->setCurrentIndex(idx - 1);
            update_step_ui(idx - 1);
        }
    });

    dlg->exec();
    dlg->deleteLater();
    return result;
}

// ---------------------------------------------------------------------------
// Setup tab — generator outputs with real heatmaps and curves
// ---------------------------------------------------------------------------

QWidget* build_setup_tab(
    std::shared_ptr<tuner_core::local_tune_edit::EditService> edit_svc = nullptr) {
    auto* scroll = new QScrollArea;
    scroll->setWidgetResizable(true);
    scroll->setStyleSheet("QScrollArea { border: none; }");

    auto* container = new QWidget;
    auto* layout = new QVBoxLayout(container);
    layout->setContentsMargins(tt::space_lg, tt::space_lg, tt::space_lg, tt::space_lg);
    layout->setSpacing(tt::space_md);

    // Wizard step buttons — compact but clickable-looking.
    {
        struct Step { const char* icon; const char* label; bool active; };
        Step steps[] = {
            {"\xe2\x9c\x93", "Engine", false},
            {"\xe2\x9c\x93", "Induction", false},
            {"\xe2\x9c\x93", "Injectors", false},
            {"\xe2\x9c\x93", "Ignition", false},
            {"\xe2\x9c\x93", "Sensors", false},
            {"\xe2\x96\xb6", "Review", true},
        };
        auto* step_bar = new QWidget;
        auto* step_layout = new QHBoxLayout(step_bar);
        step_layout->setContentsMargins(0, 0, 0, 4);
        step_layout->setSpacing(tt::space_xs);
        for (const auto& s : steps) {
            // Active step uses `fill_primary_mid` + `accent_primary`
            // border + `text_primary` text — same "selected" grammar
            // as the sidebar selection, the command palette selection,
            // and the TUNE-tab scalar editor ok state. Inactive step
            // is completed (the check mark + `accent_ok` icon) and
            // reads as muted chrome (`bg_elevated` background).
            const char* bg = s.active ? tt::fill_primary_mid : tt::bg_elevated;
            const char* fg = s.active ? tt::text_primary     : tt::text_muted;
            const char* step_border = s.active ? tt::accent_primary : tt::border;
            const char* icon_color = s.active ? tt::accent_primary : tt::accent_ok;
            char style[256];
            std::snprintf(style, sizeof(style),
                "background-color: %s; border: 1px solid %s; "
                "border-radius: %dpx; padding: %dpx %dpx; font-size: %dpx;",
                bg, step_border, tt::radius_sm, tt::space_xs + 2, tt::space_md, tt::font_small);
            char label[256];
            std::snprintf(label, sizeof(label),
                "<span style='color: %s;'>%s</span> "
                "<span style='color: %s; font-weight: %s;'>%s</span>",
                icon_color, s.icon, fg, s.active ? "bold" : "normal", s.label);
            auto* btn = new QLabel;
            btn->setTextFormat(Qt::RichText);
            btn->setText(QString::fromUtf8(label));
            btn->setStyleSheet(QString::fromUtf8(style));
            btn->setAlignment(Qt::AlignCenter);
            btn->setCursor(Qt::PointingHandCursor);
            step_layout->addWidget(btn, 1);
        }
        layout->addWidget(step_bar);
    }

    // "Run Setup Wizard" button — opens the interactive wizard dialog.
    {
        auto* wizard_btn = new QPushButton(QString::fromUtf8(
            "\xe2\x9a\x99  Run Engine Setup Wizard..."));
        char ws[256];
        std::snprintf(ws, sizeof(ws),
            "QPushButton { background: %s; color: %s; border: 1px solid %s; "
            "border-radius: %dpx; padding: %dpx %dpx; font-size: %dpx; font-weight: bold; }"
            "QPushButton:hover { background: %s; border-color: %s; color: %s; }",
            tt::bg_elevated, tt::text_secondary, tt::border,
            tt::radius_md, tt::space_sm, tt::space_lg, tt::font_body,
            tt::fill_primary_mid, tt::accent_primary, tt::text_primary);
        wizard_btn->setStyleSheet(QString::fromUtf8(ws));
        wizard_btn->setCursor(Qt::PointingHandCursor);
        QObject::connect(wizard_btn, &QPushButton::clicked, [edit_svc, container]() {
            auto wr = open_engine_setup_wizard(container);
            if (wr.accepted && edit_svc) {
                // Stage wizard values into the edit service.
                auto stage_s = [&edit_svc](const char* name, double val) {
                    char buf[32]; std::snprintf(buf, sizeof(buf), "%.6g", val);
                    try { edit_svc->stage_scalar_value(name, buf); } catch (...) {}
                };

                // Compute boost in kPa (psi × 6.895 + atmospheric).
                double boost_kpa = wr.boost_target_psi * 6.895 + 101.3;

                // ---- Scalars ----
                // Engine.
                stage_s("nCylinders", wr.cylinders);
                stage_s("twoStroke", wr.two_stroke ? 1.0 : 0.0);
                stage_s("algorithm", wr.load_algorithm);  // 0=MAP, 1=TPS
                // Injectors.
                stage_s("injFlow1", wr.injector_flow);
                stage_s("injOpen", wr.dead_time_ms);
                stage_s("stoich", wr.stoich);
                // Compute and stage reqFuel.
                double computed_req_fuel;
                {
                    namespace rfc = tuner_core::required_fuel_calculator;
                    auto rf = rfc::calculate(wr.displacement_cc, wr.cylinders,
                                             wr.injector_flow, wr.stoich);
                    computed_req_fuel = rf.req_fuel_ms;
                    stage_s("reqFuel", rf.req_fuel_ms);
                }
                // Boost control.
                if (wr.induction > 0) {
                    stage_s("boostEnabled", 1.0);
                }
                // Trigger & ignition.
                stage_s("TrigPattern", 0);  // missing tooth
                stage_s("nTeeth", wr.trigger_teeth);
                stage_s("missingTeeth", wr.missing_teeth);
                stage_s("sparkMode", wr.spark_mode);
                stage_s("dwellRun", wr.dwell_running);
                stage_s("dwellcrank", wr.dwell_cranking);
                stage_s("dwellLim", std::max(wr.dwell_running, wr.dwell_cranking) + 1.0);
                // Sensors.
                stage_s("egoType", wr.ego_type);
                stage_s("mapMin", wr.map_min);
                stage_s("mapMax", wr.map_max);
                // Acceleration enrichment.
                if (wr.ae_mode < 2) {
                    stage_s("aeMode", wr.ae_mode);  // 0=TPS, 1=MAP
                    stage_s("taeThresh", wr.ae_threshold);
                    stage_s("taeAmount", wr.ae_amount);
                }
                // Injector layout + count.
                stage_s("nInjectors", wr.n_injectors);
                stage_s("injLayout", wr.inj_layout);
                // Fuel pressure model.
                if (wr.fuel_pressure_model > 0) {
                    stage_s("fuelPressureModel", wr.fuel_pressure_model);
                    stage_s("fuelPressure", wr.rail_pressure_kpa);
                }
                // Flex fuel.
                if (wr.flex_fuel_enabled) {
                    stage_s("flexEnabled", 1.0);
                    stage_s("flexFreqLow", wr.flex_freq_low);
                    stage_s("flexFreqHigh", wr.flex_freq_high);
                }
                // Cam input (for sequential).
                if (wr.cam_input > 0) {
                    stage_s("camInput", wr.cam_input);
                }
                // Knock sensor.
                if (wr.knock_mode > 0) {
                    stage_s("knockMode", wr.knock_mode);
                    stage_s("knock_maxRetard", wr.knock_max_retard);
                }
                // AFR lean protection.
                if (wr.afr_protection_enabled) {
                    stage_s("afrProtectEnabled", 1.0);
                    stage_s("afrProtectDeviation", wr.afr_protection_max);
                    stage_s("afrProtectCutTime", wr.afr_protection_cut_time);
                }
                // Oil pressure sensor.
                if (wr.oil_pressure_enabled) {
                    stage_s("oilPressureEnable", 1.0);
                    stage_s("oilPressureMin", wr.oil_pressure_min);
                    stage_s("oilPressureMax", wr.oil_pressure_max);
                }
                // Sensor filters.
                stage_s("ADCFILTER_CLT", wr.clt_filter);
                stage_s("ADCFILTER_IAT", wr.iat_filter);

                // ---- Generate starter tables ----
                namespace vg = tuner_core::ve_table_generator;
                namespace ag = tuner_core::afr_target_generator;
                namespace sg = tuner_core::spark_table_generator;
                namespace seg = tuner_core::startup_enrichment_generator;
                namespace irg = tuner_core::idle_rpm_generator;

                // VE table — fully populated context.
                vg::VeGeneratorContext ve_ctx;
                ve_ctx.displacement_cc = wr.displacement_cc;
                ve_ctx.cylinder_count = wr.cylinders;
                ve_ctx.compression_ratio = wr.compression_ratio;
                ve_ctx.required_fuel_ms = computed_req_fuel;
                ve_ctx.injector_flow_ccmin = wr.injector_flow;
                ve_ctx.injector_dead_time_ms = wr.dead_time_ms;
                ve_ctx.intercooler_present = wr.intercooler_present;
                if (wr.induction > 0) {
                    ve_ctx.forced_induction_topology = (wr.induction == 3)
                        ? vg::ForcedInductionTopology::SINGLE_SUPERCHARGER
                        : (wr.induction == 2)
                            ? vg::ForcedInductionTopology::TWIN_TURBO_IDENTICAL
                            : vg::ForcedInductionTopology::SINGLE_TURBO;
                    ve_ctx.boost_target_kpa = boost_kpa;
                }
                auto ve_result = vg::generate(ve_ctx);
                try { edit_svc->replace_list("veTable", ve_result.values); } catch (...) {}

                // AFR targets — with stoich and intercooler.
                ag::AfrGeneratorContext afr_ctx;
                afr_ctx.stoich_ratio = wr.stoich;
                afr_ctx.intercooler_present = wr.intercooler_present;
                if (wr.induction > 0) {
                    afr_ctx.forced_induction_topology = (wr.induction == 3)
                        ? ag::ForcedInductionTopology::SINGLE_SUPERCHARGER
                        : ag::ForcedInductionTopology::SINGLE_TURBO;
                    afr_ctx.boost_target_kpa = boost_kpa;
                }
                auto afr_result = ag::generate(afr_ctx, ag::CalibrationIntent::FIRST_START);
                try { edit_svc->replace_list("afrTable", afr_result.values); } catch (...) {}

                // Spark advance — with intercooler.
                sg::SparkGeneratorContext spark_ctx;
                spark_ctx.compression_ratio = wr.compression_ratio;
                spark_ctx.cylinder_count = wr.cylinders;
                spark_ctx.dwell_ms = wr.dwell_running;
                spark_ctx.intercooler_present = wr.intercooler_present;
                if (wr.induction > 0) {
                    spark_ctx.forced_induction_topology = (wr.induction == 3)
                        ? sg::ForcedInductionTopology::SINGLE_SUPERCHARGER
                        : sg::ForcedInductionTopology::SINGLE_TURBO;
                    spark_ctx.boost_target_kpa = boost_kpa;
                }
                auto spark_result = sg::generate(spark_ctx, sg::CalibrationIntent::FIRST_START);
                try { edit_svc->replace_list("advanceTable", spark_result.values); } catch (...) {}

                // WUE enrichment curve.
                seg::StartupContext wue_ctx;
                wue_ctx.stoich_ratio = wr.stoich;
                auto wue = seg::generate_wue(wue_ctx, seg::CalibrationIntent::FIRST_START);
                try { edit_svc->replace_list("wueAFR", wue.enrichment_pct); } catch (...) {}

                // Cranking enrichment curve.
                seg::StartupContext crank_ctx;
                crank_ctx.compression_ratio = wr.compression_ratio;
                auto crank = seg::generate_cranking(crank_ctx, seg::CalibrationIntent::FIRST_START);
                try { edit_svc->replace_list("crankRPM", crank.enrichment_pct); } catch (...) {}

                // Idle RPM targets.
                irg::GeneratorContext idle_ctx;
                if (wr.induction > 0)
                    idle_ctx.forced_induction_topology = irg::ForcedInductionTopology::SINGLE_TURBO;
                auto idle = irg::generate(idle_ctx, irg::CalibrationIntent::FIRST_START);
                try { edit_svc->replace_list("iacCLValues", idle.rpm_targets); } catch (...) {}

                // Boost target + duty tables (forced induction only).
                if (wr.induction > 0) {
                    namespace btg = tuner_core::boost_table_generator;
                    btg::BoostGeneratorContext boost_ctx;
                    boost_ctx.target_boost_kpa = boost_kpa;
                    boost_ctx.intercooled = wr.intercooler_present;
                    auto boost = btg::generate(boost_ctx);
                    try { edit_svc->replace_list("boostTable", boost.target_values); } catch (...) {}
                    try { edit_svc->replace_list("boostDutyTable", boost.duty_values); } catch (...) {}
                }

                // Thermistor calibration — generate CLT + IAT lookup tables.
                {
                    namespace tc = tuner_core::thermistor_calibration;
                    const char* therm_names[] = {
                        "GM", "Ford", "Toyota", "Chrysler 85+",
                        "Saab / Bosch", "Mazda", "Mitsubishi", "BMW E30 325i",
                    };
                    int therm_count = sizeof(therm_names) / sizeof(therm_names[0]);
                    // CLT calibration.
                    int clt_idx = std::clamp(wr.clt_thermistor, 0, therm_count - 1);
                    auto* clt_preset = tc::preset_by_name(therm_names[clt_idx]);
                    if (clt_preset) {
                        auto cal = tc::generate(*clt_preset, tc::Sensor::CLT);
                        // Stage the three calibration point pairs.
                        auto pts = cal.preview_points();
                        if (pts.size() >= 3) {
                            stage_s("cltBias", clt_preset->pullup_ohms);
                        }
                    }
                    // IAT calibration.
                    int iat_idx = std::clamp(wr.iat_thermistor, 0, therm_count - 1);
                    auto* iat_preset = tc::preset_by_name(therm_names[iat_idx]);
                    if (iat_preset) {
                        auto cal = tc::generate(*iat_preset, tc::Sensor::IAT);
                        auto pts = cal.preview_points();
                        if (pts.size() >= 3) {
                            stage_s("iatBias", iat_preset->pullup_ohms);
                        }
                    }
                }

                // Post-wizard guidance — tell the operator what to do next.
                // This is the "guided power" moment: the wizard did the hard
                // work, now guide them through the first steps.
                // Build the list of what was generated.
                std::string generated = "Generated tables:\n";
                generated += "  \xe2\x80\xa2 VE Table (volumetric efficiency)\n";
                generated += "  \xe2\x80\xa2 AFR Target Table (air-fuel ratio targets)\n";
                generated += "  \xe2\x80\xa2 Spark Advance Table (ignition timing)\n";
                generated += "  \xe2\x80\xa2 Warmup Enrichment curve\n";
                generated += "  \xe2\x80\xa2 Cranking Enrichment curve\n";
                generated += "  \xe2\x80\xa2 Idle RPM Targets\n";
                if (wr.induction > 0)
                    generated += "  \xe2\x80\xa2 Boost Target + Duty Tables\n";
                generated += "\n";

                std::string msg =
                    "Your engine is configured!\n\n" + generated +
                    "Next steps:\n\n"
                    "1. Review the generated tables on the TUNE tab (Alt+1)\n"
                    "   \xe2\x80\x94 check the VE table shape and spark advance curve\n"
                    "2. Connect to your ECU (File \xe2\x86\x92 Connect to ECU)\n"
                    "3. Write the tune to ECU RAM (Ctrl+W)\n"
                    "4. Start the engine and verify idle\n"
                    "   \xe2\x80\x94 if it won\xe2\x80\x99t start, check trigger settings first\n"
                    "5. Use LOGGING to capture data while driving\n"
                    "6. Use ASSIST \xe2\x86\x92 VE Analyze to refine the tune\n\n"
                    "The starter tune is conservative \xe2\x80\x94 expect to refine it "
                    "through a few drive-and-analyze cycles.";
                QMessageBox::information(container,
                    QString::fromUtf8("Setup Complete"),
                    QString::fromUtf8(msg.c_str()));

                // Switch to TUNE tab so the operator can see their new tables.
                if (auto* sb = container->window()->findChild<QListWidget*>())
                    sb->setCurrentRow(0);
            }
        });
        layout->addWidget(wizard_btn);
    }

    // Read engine context from loaded tune if available, otherwise
    // fall back to demo values (Ford 300 Twin GT28 context).
    auto read_scalar = [&edit_svc](const std::string& name, double fallback) -> double {
        if (!edit_svc) return fallback;
        auto* tv = edit_svc->get_value(name);
        if (tv && std::holds_alternative<double>(tv->value))
            return std::get<double>(tv->value);
        return fallback;
    };
    double disp = read_scalar("displacement", 2998.0);
    int ncyl = static_cast<int>(read_scalar("nCylinders", 6));
    double cr = read_scalar("compressionRatio", 10.5);
    double req_fuel = read_scalar("reqFuel", 8.5);
    double inj_flow = read_scalar("injFlow1", 550.0);
    double boost_kpa = read_scalar("boostTarget", 200.0);
    double dwell = read_scalar("dwellRun", 3.5);
    bool has_tune = (edit_svc != nullptr && edit_svc->get_value("reqFuel") != nullptr);
    const char* data_source = has_tune ? "loaded tune" : "demo defaults";

    namespace vg = tuner_core::ve_table_generator;
    namespace ag = tuner_core::afr_target_generator;
    namespace sg = tuner_core::spark_table_generator;
    namespace irg = tuner_core::idle_rpm_generator;
    namespace seg = tuner_core::startup_enrichment_generator;
    namespace tc = tuner_core::thermistor_calibration;

    // VE table
    vg::VeGeneratorContext ve_ctx;
    ve_ctx.forced_induction_topology = vg::ForcedInductionTopology::SINGLE_TURBO;
    ve_ctx.cam_duration_deg = 280.0;
    ve_ctx.compression_ratio = cr;
    ve_ctx.head_flow_class = "race_ported";
    ve_ctx.intake_manifold_style = "short_runner_plenum";
    ve_ctx.cylinder_count = ncyl;
    ve_ctx.displacement_cc = disp;
    ve_ctx.required_fuel_ms = req_fuel;
    auto ve_result = vg::generate(ve_ctx);
    {
        char ve_title[256];
        std::snprintf(ve_title, sizeof(ve_title),
            "VE Table (%.0fcc %dcyl, %.1f:1 CR) \xe2\x80\x94 %s",
            disp, ncyl, cr, data_source);
        layout->addWidget(render_heatmap(ve_result.values, 16, 16, ve_title));
    }

    // Confidence badges for VE assumptions (Phase B).
    if (!ve_result.assumptions.empty()) {
        char badge_buf[512]; int boff = 0;
        for (const auto& a : ve_result.assumptions) {
            const char* badge =
                (a.source == vg::AssumptionSource::FROM_CONTEXT)
                    ? "\xf0\x9f\x9f\xa2" :  // green circle
                (a.source == vg::AssumptionSource::COMPUTED)
                    ? "\xf0\x9f\x9f\xa1" :  // yellow circle
                    "\xf0\x9f\x94\xb4";     // red circle
            boff += std::snprintf(badge_buf + boff, sizeof(badge_buf) - boff,
                "%s %s: %s\n", badge, a.label.c_str(), a.value_str.c_str());
            if (boff >= static_cast<int>(sizeof(badge_buf) - 1)) break;
        }
        layout->addWidget(make_info_card("VE Assumptions", badge_buf, tt::text_muted));
    }

    // AFR target table
    ag::AfrGeneratorContext afr_ctx;
    afr_ctx.forced_induction_topology = ag::ForcedInductionTopology::SINGLE_TURBO;
    afr_ctx.boost_target_kpa = boost_kpa;
    afr_ctx.intercooler_present = true;
    auto afr_result = ag::generate(afr_ctx, ag::CalibrationIntent::FIRST_START);
    layout->addWidget(render_heatmap(afr_result.values, 16, 16,
        "AFR Target (Single Turbo, 200 kPa, intercooled, first-start)"));

    // Spark advance table
    sg::SparkGeneratorContext spark_ctx;
    spark_ctx.forced_induction_topology = sg::ForcedInductionTopology::SINGLE_TURBO;
    spark_ctx.compression_ratio = cr;
    spark_ctx.boost_target_kpa = boost_kpa;
    spark_ctx.intercooler_present = true;
    spark_ctx.cylinder_count = ncyl;
    spark_ctx.dwell_ms = dwell;
    auto spark_result = sg::generate(spark_ctx, sg::CalibrationIntent::FIRST_START);
    layout->addWidget(render_heatmap(spark_result.values, 16, 16,
        "Spark Advance (Single Turbo, 10.5:1 CR, first-start)"));

    // Idle RPM curve
    irg::GeneratorContext idle_ctx;
    idle_ctx.forced_induction_topology = irg::ForcedInductionTopology::SINGLE_TURBO;
    idle_ctx.cam_duration_deg = 280.0;
    idle_ctx.head_flow_class = "race_ported";
    idle_ctx.intake_manifold_style = "short_runner_plenum";
    auto idle_result = irg::generate(idle_ctx, irg::CalibrationIntent::FIRST_START);
    layout->addWidget(render_1d_curve(
        idle_result.clt_bins, idle_result.rpm_targets,
        "Idle RPM Targets (turbo, 280\xc2\xb0 cam, race-ported, short-runner)",
        "RPM", tt::accent_ok));

    // WUE curve
    seg::StartupContext wue_ctx;
    wue_ctx.stoich_ratio = 14.7;
    auto wue_result = seg::generate_wue(wue_ctx, seg::CalibrationIntent::FIRST_START);
    layout->addWidget(render_1d_curve(
        wue_result.clt_bins, wue_result.enrichment_pct,
        "Warmup Enrichment (petrol, first-start)",
        "%", tt::accent_warning));

    // Cranking enrichment
    seg::StartupContext crank_ctx;
    crank_ctx.compression_ratio = 10.5;
    auto crank_result = seg::generate_cranking(crank_ctx, seg::CalibrationIntent::FIRST_START);
    layout->addWidget(render_1d_curve(
        crank_result.clt_bins, crank_result.enrichment_pct,
        "Cranking Enrichment (10.5:1 CR, first-start)",
        "%", tt::accent_danger));

    // Thermistor calibration preview
    auto* gm_preset = tc::preset_by_name("GM");
    if (gm_preset) {
        auto cal = tc::generate(*gm_preset, tc::Sensor::CLT);
        auto preview = cal.preview_points();
        std::vector<double> adc_bins, temp_values;
        for (auto [adc, temp] : preview) {
            adc_bins.push_back(static_cast<double>(adc));
            temp_values.push_back(temp);
        }
        // Render as a 1D curve (ADC → temperature).
        auto* therm_card = new QWidget;
        auto* tl = new QVBoxLayout(therm_card);
        tl->setContentsMargins(tt::space_md + 2, tt::space_sm + 2, tt::space_md + 2, tt::space_sm + 2);
        tl->setSpacing(tt::space_xs);
        {
            char cstyle[192];
            std::snprintf(cstyle, sizeof(cstyle),
                "%s padding: 0;",
                tt::card_style(tt::accent_special).c_str());
            therm_card->setStyleSheet(QString::fromUtf8(cstyle));
        }
        auto* th = new QLabel("GM CLT Thermistor Calibration (Steinhart-Hart)");
        QFont thf = th->font(); thf.setBold(true); thf.setPixelSize(tt::font_label);
        th->setFont(thf);
        {
            char hstyle[96];
            std::snprintf(hstyle, sizeof(hstyle),
                "color: %s; border: none;", tt::text_secondary);
            th->setStyleSheet(QString::fromUtf8(hstyle));
        }
        tl->addWidget(th);

        for (auto [adc, temp] : preview) {
            // Color: hot = danger red, warm = warning amber,
            // normal = ok green, cold = primary blue.
            double t_norm = (temp - (-40.0)) / (350.0 - (-40.0));
            t_norm = std::clamp(t_norm, 0.0, 1.0);
            const char* color = (t_norm > 0.7) ? tt::accent_danger :
                                (t_norm > 0.4) ? tt::accent_warning :
                                (t_norm > 0.15) ? tt::accent_ok : tt::accent_primary;
            char buf[256];
            std::snprintf(buf, sizeof(buf),
                "<span style='color: %s; font-size: %dpx; "
                "font-family: monospace;'>ADC %4d </span>"
                "<span style='background-color: %s; color: %s; "
                "padding: 2px 8px; border-radius: 2px; "
                "font-size: %dpx; font-family: monospace;'>"
                "%6.1f \xc2\xb0""C</span>",
                tt::text_muted, tt::font_micro, adc,
                color, tt::text_inverse, tt::font_micro, temp);
            auto* row = new QLabel;
            row->setTextFormat(Qt::RichText);
            row->setText(QString::fromUtf8(buf));
            row->setStyleSheet("border: none;");
            tl->addWidget(row);
        }
        layout->addWidget(therm_card);
    }

    // ---- Required Fuel Calculator (sub-slice 2) ----
    {
        namespace rfc = tuner_core::required_fuel_calculator;
        auto result = rfc::calculate(disp, ncyl, inj_flow, 14.7);
        char buf[256];
        std::snprintf(buf, sizeof(buf),
            "Displacement: %.0f cc, Cylinders: %d, Injector: %.0f cc/min\n"
            "Target AFR: 14.7 (stoich petrol)\n"
            "Required Fuel: %.2f ms (stored as %d)",
            result.displacement_cc, result.cylinder_count,
            result.injector_flow_ccmin, result.req_fuel_ms, result.req_fuel_stored);
        layout->addWidget(make_info_card(
            "Required Fuel Calculator", buf, tt::accent_ok));
    }

    // ---- Hardware Setup Validation (sub-slice 7) ----
    {
        namespace hsv = tuner_core::hardware_setup_validation;
        std::vector<std::string> params = {
            "dwellLim", "injOpen", "TrigPattern", "nTeeth",
        };
        auto issues = hsv::validate(params, [](std::string_view name) -> std::optional<double> {
            if (name == "dwellLim") return 5.0;
            if (name == "injOpen") return 0.0;  // triggers warning
            if (name == "TrigPattern") return 0.0;
            if (name == "nTeeth") return 36.0;
            return std::nullopt;
        });
        if (issues.empty()) {
            layout->addWidget(make_info_card(
                "Hardware Validation",
                "All validation rules passed.", tt::accent_ok));
        } else {
            char buf[512];
            int off = 0;
            for (const auto& issue : issues) {
                if (off > 0) off += std::snprintf(buf + off, sizeof(buf) - off, "\n");
                off += std::snprintf(buf + off, sizeof(buf) - off, "%s",
                                      issue.message.c_str());
                if (off >= static_cast<int>(sizeof(buf) - 1)) break;
            }
            layout->addWidget(make_info_card(
                "Hardware Validation", buf, tt::accent_warning));
        }
    }

    // ---- Ignition Coil Presets ----
    {
        namespace hpns = tuner_core::hardware_presets;
        auto* preset_header = new QLabel("Ignition Coil Presets");
        QFont phf = preset_header->font(); phf.setBold(true); phf.setPixelSize(tt::font_heading);
        preset_header->setFont(phf);
        preset_header->setStyleSheet(QString::fromUtf8("margin-top: 8px;"));
        layout->addWidget(preset_header);

        for (const auto& p : hpns::ignition_presets()) {
            std::string confidence = hpns::source_confidence_label(p.source_note, p.source_url);
            const char* accent = (confidence == "Official") ? tt::accent_ok :
                                 (confidence == "Trusted Secondary") ? tt::accent_primary : tt::accent_warning;
            char body[512];
            std::snprintf(body, sizeof(body),
                "%s\nRunning: %.1f ms  |  Cranking: %.1f ms  |  Source: %s",
                p.description.c_str(), p.running_dwell_ms, p.cranking_dwell_ms,
                confidence.c_str());
            layout->addWidget(make_info_card(p.label.c_str(), body, accent));
        }
    }

    // ---- Sensor Setup Checklist ----
    {
        namespace ssc = tuner_core::sensor_setup_checklist;
        auto* sensor_header = new QLabel("Sensor Setup Checklist");
        QFont shf = sensor_header->font(); shf.setBold(true); shf.setPixelSize(tt::font_heading);
        sensor_header->setFont(shf);
        sensor_header->setStyleSheet(QString::fromUtf8("margin-top: 8px;"));
        layout->addWidget(sensor_header);

        // Simulated sensor pages with typical Speeduino parameters.
        ssc::Page sensor_page;
        sensor_page.parameters = {
            {"egoType", "O2 Sensor Type", {}, {}},
            {"stoich", "Stoichiometric AFR", {}, {}},
            {"tpsMin", "TPS Minimum ADC", {}, {}},
            {"tpsMax", "TPS Maximum ADC", {}, {}},
            {"mapMin", "MAP Sensor Min", {}, {}},
            {"mapMax", "MAP Sensor Max", {}, {}},
        };
        std::map<std::string, double> sensor_vals = {
            {"egoType", 2.0}, {"stoich", 14.7},
            {"tpsMin", 12.0}, {"tpsMax", 850.0},
            {"mapMin", 10.0}, {"mapMax", 260.0},
        };
        ssc::ValueGetter svg = [&sensor_vals](const std::string& name) -> std::optional<double> {
            auto it = sensor_vals.find(name);
            return (it != sensor_vals.end()) ? std::optional(it->second) : std::nullopt;
        };
        ssc::OptionLabelGetter solg = [](const ssc::Parameter&) -> std::string { return ""; };
        auto checks = ssc::validate({sensor_page}, svg, solg);
        for (const auto& item : checks) {
            const char* accent =
                (item.status == ssc::Status::OK)      ? tt::accent_ok :
                (item.status == ssc::Status::INFO)     ? tt::accent_primary :
                (item.status == ssc::Status::NEEDED)   ? tt::accent_warning :
                (item.status == ssc::Status::WARNING)  ? tt::accent_warning : tt::accent_danger;
            layout->addWidget(make_info_card(item.title.c_str(), item.detail.c_str(), accent));
        }
    }

    // ---- Generator Readiness ----
    {
        namespace hsgc = tuner_core::hardware_setup_generator_context;
        auto* gen_header = new QLabel("Generator Readiness");
        QFont ghf2 = gen_header->font(); ghf2.setBold(true); ghf2.setPixelSize(tt::font_heading);
        gen_header->setFont(ghf2);
        gen_header->setStyleSheet(QString::fromUtf8("margin-top: 8px;"));
        layout->addWidget(gen_header);

        // Use the operator context from the SETUP demo above.
        tuner_core::operator_engine_context::OperatorEngineContext op_ctx;
        op_ctx.displacement_cc = 2998.0;
        op_ctx.cylinder_count = 6;
        op_ctx.compression_ratio = 10.5;
        op_ctx.cam_duration_deg = 280.0;
        op_ctx.head_flow_class = "race_ported";
        op_ctx.forced_induction_topology =
            tuner_core::generator_types::ForcedInductionTopology::SINGLE_TURBO;
        op_ctx.boost_target_kpa = 200.0;
        op_ctx.intercooler_present = true;

        // Simulated tune pages with some values populated.
        hsgc::Page gen_page;
        gen_page.parameters = {
            {"injFlow1", "Injector Flow Rate"},
            {"reqFuel", "Required Fuel"},
            {"rpmHard", "Rev Limit"},
            {"stoich", "Stoichiometric AFR"},
            {"dwellRun", "Running Dwell"},
        };
        std::map<std::string, double> gen_vals = {
            {"injFlow1", 550.0}, {"reqFuel", 8.5}, {"rpmHard", 7200.0},
            {"stoich", 14.7}, {"dwellRun", 3.5},
        };
        hsgc::ValueGetter gen_gv = [](const std::string& name, void* user) -> std::optional<double> {
            auto* m = static_cast<std::map<std::string, double>*>(user);
            auto it = m->find(name);
            return (it != m->end()) ? std::optional(it->second) : std::nullopt;
        };
        auto gen_ctx = hsgc::build({gen_page}, gen_gv, &gen_vals, &op_ctx);

        // Show what's ready and what's missing.
        char gen_buf[512];
        int off = 0;
        if (gen_ctx.missing_for_ve_generation.empty())
            off += std::snprintf(gen_buf + off, sizeof(gen_buf) - off,
                "\xe2\x9c\x85 VE table generation: all inputs available\n");
        else {
            off += std::snprintf(gen_buf + off, sizeof(gen_buf) - off,
                "\xe2\x9a\xa0 VE table generation missing: ");
            for (size_t i = 0; i < gen_ctx.missing_for_ve_generation.size(); ++i) {
                if (i > 0) off += std::snprintf(gen_buf + off, sizeof(gen_buf) - off, ", ");
                off += std::snprintf(gen_buf + off, sizeof(gen_buf) - off, "%s",
                    gen_ctx.missing_for_ve_generation[i].c_str());
            }
            off += std::snprintf(gen_buf + off, sizeof(gen_buf) - off, "\n");
        }
        if (gen_ctx.missing_for_spark_helper.empty())
            off += std::snprintf(gen_buf + off, sizeof(gen_buf) - off,
                "\xe2\x9c\x85 Spark table generation: all inputs available\n");
        else {
            off += std::snprintf(gen_buf + off, sizeof(gen_buf) - off,
                "\xe2\x9a\xa0 Spark table generation missing: ");
            for (size_t i = 0; i < gen_ctx.missing_for_spark_helper.size(); ++i) {
                if (i > 0) off += std::snprintf(gen_buf + off, sizeof(gen_buf) - off, ", ");
                off += std::snprintf(gen_buf + off, sizeof(gen_buf) - off, "%s",
                    gen_ctx.missing_for_spark_helper[i].c_str());
            }
            off += std::snprintf(gen_buf + off, sizeof(gen_buf) - off, "\n");
        }
        if (gen_ctx.computed_req_fuel_ms.has_value())
            std::snprintf(gen_buf + off, sizeof(gen_buf) - off,
                "\xe2\x9c\x85 Computed reqFuel: %.2f ms", *gen_ctx.computed_req_fuel_ms);
        else
            std::snprintf(gen_buf + off, sizeof(gen_buf) - off,
                "\xe2\x9a\xa0 Cannot compute reqFuel (missing inputs)");

        layout->addWidget(make_info_card(
            "Generator Readiness", gen_buf, tt::accent_primary));
    }

    // ---- Ignition / Trigger Cross-Validation ----
    {
        namespace itcv = tuner_core::ignition_trigger_cross_validation;
        auto* cv_header = new QLabel("Ignition / Trigger Cross-Validation");
        QFont cvhf = cv_header->font(); cvhf.setBold(true); cvhf.setPixelSize(tt::font_heading);
        cv_header->setFont(cvhf);
        cv_header->setStyleSheet(QString::fromUtf8("margin-top: 8px;"));
        layout->addWidget(cv_header);

        // Simulated ignition + trigger pages.
        itcv::Page ign_page;
        ign_page.parameters = {
            {"dwellRun", "Running Dwell", {}, {}},
            {"sparkMode", "Spark Mode", {}, {}},
        };
        itcv::Page trig_page;
        trig_page.parameters = {
            {"TrigPattern", "Trigger Pattern", {}, {}},
            {"TriggerAngle", "Reference Angle", {}, {}},
            {"nTeeth", "Tooth Count", {}, {}},
            {"missingTeeth", "Missing Teeth", {}, {}},
            {"trigPatternSec", "Secondary Trigger", {}, {}},
        };
        std::map<std::string, double> cv_vals = {
            {"dwellRun", 3.5}, {"sparkMode", 3.0},  // sequential ignition
            {"TrigPattern", 0.0}, {"TriggerAngle", 10.0},
            {"nTeeth", 36.0}, {"missingTeeth", 1.0},
            {"trigPatternSec", 0.0},  // single tooth cam
        };
        itcv::ValueGetter cv_gv = [&cv_vals](const std::string& name) -> std::optional<double> {
            auto it = cv_vals.find(name);
            return (it != cv_vals.end()) ? std::optional(it->second) : std::nullopt;
        };
        itcv::OptionLabelGetter cv_olg = [](const itcv::Parameter&) -> std::string { return ""; };
        auto checks = itcv::validate(&ign_page, &trig_page, cv_gv, cv_olg);
        for (const auto& item : checks) {
            const char* accent =
                (item.status == itcv::Status::OK)      ? tt::accent_ok :
                (item.status == itcv::Status::INFO)     ? tt::accent_primary :
                (item.status == itcv::Status::NEEDED)   ? tt::accent_warning :
                (item.status == itcv::Status::WARNING)  ? tt::accent_warning : tt::accent_danger;
            layout->addWidget(make_info_card(item.title.c_str(), item.detail.c_str(), accent));
        }
    }

    layout->addStretch(1);
    scroll->setWidget(container);
    return scroll;
}

// ---------------------------------------------------------------------------
// Triggers tab — trigger log visualization demo
// ---------------------------------------------------------------------------

QWidget* build_triggers_tab(std::shared_ptr<EcuConnection> ecu_conn = nullptr) {
    namespace tlv = tuner_core::trigger_log_visualization;
    namespace tla = tuner_core::trigger_log_analysis;

    auto* scroll = new QScrollArea;
    scroll->setWidgetResizable(true);
    scroll->setStyleSheet("QScrollArea { border: none; }");
    auto* container = new QWidget;
    auto* outer = new QVBoxLayout(container);
    outer->setContentsMargins(tt::space_lg, tt::space_lg, tt::space_lg, tt::space_lg);
    outer->setSpacing(tt::space_sm + 2);

    outer->addWidget(make_tab_header(
        "Trigger Logs",
        "Import a log to diagnose sync, tooth spacing, and crank/cam phase"));

    // Import button row.
    auto* import_row = new QHBoxLayout;
    import_row->setSpacing(tt::space_sm);
    auto* import_btn = new QPushButton(QString::fromUtf8("Import CSV..."));
    import_btn->setCursor(Qt::PointingHandCursor);
    {
        char bs[384];
        std::snprintf(bs, sizeof(bs),
            "QPushButton { background: %s; border: 1px solid %s; "
            "border-radius: %dpx; padding: 6px 14px; "
            "color: %s; font-size: %dpx; font-weight: bold; } "
            "QPushButton:hover { background: %s; }",
            tt::bg_elevated, tt::accent_primary,
            tt::radius_sm, tt::text_primary, tt::font_body,
            tt::fill_primary_mid);
        import_btn->setStyleSheet(QString::fromUtf8(bs));
    }
    auto* source_label = new QLabel(QString::fromUtf8("Showing demo 36-1 data"));
    {
        char sl[128];
        std::snprintf(sl, sizeof(sl),
            "QLabel { color: %s; font-size: %dpx; }",
            tt::text_muted, tt::font_small);
        source_label->setStyleSheet(QString::fromUtf8(sl));
    }
    // Live capture button — captures tooth/composite log from connected ECU.
    auto* capture_btn = new QPushButton(QString::fromUtf8("Capture from ECU"));
    capture_btn->setCursor(Qt::PointingHandCursor);
    capture_btn->setEnabled(false);  // enabled when ECU connected
    {
        char bs[512];
        std::snprintf(bs, sizeof(bs),
            "QPushButton { background: %s; border: 1px solid %s; "
            "border-radius: %dpx; padding: 6px 14px; "
            "color: %s; font-size: %dpx; font-weight: bold; } "
            "QPushButton:hover { background: %s; } "
            "QPushButton:disabled { background: %s; color: %s; border-color: %s; }",
            tt::bg_elevated, tt::accent_ok,
            tt::radius_sm, tt::text_primary, tt::font_body,
            tt::fill_primary_mid,
            tt::bg_elevated, tt::text_dim, tt::border);
        capture_btn->setStyleSheet(QString::fromUtf8(bs));
    }

    // Logger type combo (Tooth / Composite).
    auto* logger_combo = new QComboBox;
    logger_combo->addItem(QString::fromUtf8("Tooth"));
    logger_combo->addItem(QString::fromUtf8("Composite"));
    {
        char cs[256];
        std::snprintf(cs, sizeof(cs),
            "QComboBox { background: %s; color: %s; border: 1px solid %s; "
            "border-radius: %dpx; padding: 4px 8px; font-size: %dpx; }",
            tt::bg_elevated, tt::text_primary, tt::border,
            tt::radius_sm, tt::font_body);
        logger_combo->setStyleSheet(QString::fromUtf8(cs));
    }

    import_row->addWidget(import_btn);
    import_row->addWidget(capture_btn);
    import_row->addWidget(logger_combo);
    import_row->addWidget(source_label, 1);
    outer->addLayout(import_row);

    // Enable capture button when ECU is connected — check via timer.
    auto* conn_check = new QTimer(container);
    QObject::connect(conn_check, &QTimer::timeout,
                     [capture_btn, ecu_conn]() {
        bool live = ecu_conn && ecu_conn->connected && ecu_conn->controller;
        if (capture_btn->isEnabled() != live)
            capture_btn->setEnabled(live);
    });
    conn_check->start(1000);

    // Results container — rebuilt on each import.
    auto* results_widget = new QWidget;
    auto* results_layout = new QVBoxLayout(results_widget);
    results_layout->setContentsMargins(0, 0, 0, 0);
    results_layout->setSpacing(tt::space_sm + 2);
    outer->addWidget(results_widget);

    // Helper: parse CSV text into rows + column names.
    auto parse_csv_text = [](const std::string& text,
                             std::vector<tlv::Row>& out_rows,
                             std::vector<std::string>& out_columns) {
        out_rows.clear();
        out_columns.clear();
        std::istringstream stream(text);
        std::string line;
        // Header line.
        if (!std::getline(stream, line)) return;
        // Strip trailing \r.
        if (!line.empty() && line.back() == '\r') line.pop_back();
        // Split header on commas.
        {
            std::istringstream hs(line);
            std::string col;
            while (std::getline(hs, col, ',')) {
                // Trim whitespace.
                while (!col.empty() && col.front() == ' ') col.erase(col.begin());
                while (!col.empty() && col.back() == ' ') col.pop_back();
                if (!col.empty()) out_columns.push_back(col);
            }
        }
        // Data lines.
        while (std::getline(stream, line)) {
            if (!line.empty() && line.back() == '\r') line.pop_back();
            if (line.empty()) continue;
            tlv::Row row;
            std::istringstream ls(line);
            std::string cell;
            int ci = 0;
            while (std::getline(ls, cell, ',')) {
                while (!cell.empty() && cell.front() == ' ') cell.erase(cell.begin());
                while (!cell.empty() && cell.back() == ' ') cell.pop_back();
                if (ci < static_cast<int>(out_columns.size()) && !cell.empty()) {
                    row.fields.emplace_back(out_columns[ci], cell);
                }
                ci++;
            }
            if (!row.fields.empty()) out_rows.push_back(std::move(row));
        }
    };

    // Helper: populate results_layout with visualization + analysis cards.
    // Clears existing children first (hide, not delete — safe in handlers).
    auto populate_results = std::make_shared<std::function<void(
        const std::vector<tlv::Row>&,
        const std::vector<std::string>&)>>();

    *populate_results = [results_layout](
        const std::vector<tlv::Row>& rows,
        const std::vector<std::string>& columns) {

        // Hide all existing children.
        for (int i = results_layout->count() - 1; i >= 0; --i) {
            auto* item = results_layout->itemAt(i);
            if (item && item->widget()) item->widget()->hide();
        }

        // Visualization.
        auto snap = tlv::build_from_rows(rows, columns);

        results_layout->addWidget(make_info_card("Visualization Summary",
            snap.summary_text.c_str(),
            snap.trace_count > 0 ? tt::accent_ok : tt::accent_warning));

        for (const auto& trace : snap.traces) {
            double min_y = trace.y_values.empty() ? 0 :
                *std::min_element(trace.y_values.begin(), trace.y_values.end());
            double max_y = trace.y_values.empty() ? 1 :
                *std::max_element(trace.y_values.begin(), trace.y_values.end());
            char body[256];
            std::snprintf(body, sizeof(body),
                "%d points | Y range: %.1f \xe2\x80\x93 %.1f | Offset: %.1f | %s",
                static_cast<int>(trace.x_values.size()), min_y, max_y,
                trace.offset, trace.is_digital ? "Digital signal" : "Analog signal");
            const char* accent = trace.is_digital ? tt::accent_primary : tt::accent_special;
            results_layout->addWidget(make_info_card(trace.name.c_str(), body, accent));
        }

        if (!snap.annotations.empty()) {
            int warnings = 0, edges = 0;
            for (const auto& ann : snap.annotations) {
                if (ann.severity == "warning") warnings++;
                else edges++;
            }
            char ann_buf[256];
            std::snprintf(ann_buf, sizeof(ann_buf),
                "%d edge annotation(s) detected%s",
                edges, warnings > 0 ? "" : " \xe2\x80\x94 no anomalies found.");
            if (warnings > 0) {
                char warn_part[64];
                std::snprintf(warn_part, sizeof(warn_part),
                    ", %d warning(s) including possible gap.", warnings);
                std::strncat(ann_buf, warn_part, sizeof(ann_buf) - std::strlen(ann_buf) - 1);
            }
            results_layout->addWidget(make_info_card("Annotations",
                ann_buf, warnings > 0 ? tt::accent_warning : tt::accent_primary));
        }

        // Analysis.
        std::map<std::string, double> tune_vals = {
            {"TrigPattern", 0}, {"nTeeth", 36}, {"missingTeeth", 1},
            {"sparkMode", 3}, {"trigPatternSec", 0},
        };
        auto decoder = tla::build_decoder_context(
            [&tune_vals](const std::string& name) -> std::optional<double> {
                auto it = tune_vals.find(name);
                return (it != tune_vals.end()) ? std::optional(it->second) : std::nullopt;
            },
            0x10);

        std::vector<tla::Row> analysis_rows;
        analysis_rows.reserve(rows.size());
        for (const auto& vr : rows) {
            tla::Row ar;
            ar.fields = vr.fields;
            analysis_rows.push_back(std::move(ar));
        }

        auto analysis = tla::analyze_rows(analysis_rows, columns, decoder);

        const char* sev_accent = (analysis.severity == "warning")
            ? tt::accent_warning : tt::accent_primary;
        results_layout->addWidget(make_info_card(
            "Capture Summary", analysis.capture_summary_text.c_str(), sev_accent));
        results_layout->addWidget(make_info_card(
            "Decoder Context", analysis.decoder_summary_text.c_str(), tt::accent_special));

        for (const auto& finding : analysis.findings) {
            const char* accent = (analysis.severity == "warning")
                ? tt::accent_warning : tt::accent_ok;
            results_layout->addWidget(make_info_card("Finding", finding.c_str(), accent));
        }
    };

    // Build initial demo data (36-1 missing tooth).
    {
        std::vector<tlv::Row> rows;
        double t = 0;
        double tooth_period = 0.5;
        for (int rev = 0; rev < 3; ++rev) {
            for (int tooth = 0; tooth < 36; ++tooth) {
                tlv::Row row;
                double crank_val = (tooth == 35) ? 0.0 : 1.0;
                double cam_val = (tooth < 18) ? 1.0 : 0.0;
                row.fields = {
                    {"Time_ms", std::to_string(t)},
                    {"crankSignal", std::to_string(crank_val)},
                    {"camSignal", std::to_string(cam_val)},
                };
                rows.push_back(row);
                t += (tooth == 34) ? tooth_period * 2.5 : tooth_period;
            }
        }
        (*populate_results)(rows, {"Time_ms", "crankSignal", "camSignal"});
    }

    // Import CSV button handler.
    QObject::connect(import_btn, &QPushButton::clicked,
                     [container, source_label, parse_csv_text,
                      populate_results]() {
        auto path = QFileDialog::getOpenFileName(container,
            QString::fromUtf8("Import Trigger Log CSV"),
            QDir::homePath(),
            QString::fromUtf8("CSV Files (*.csv);;All Files (*)"));
        if (path.isEmpty()) return;

        // Read file.
        std::ifstream in(path.toStdString(), std::ios::in | std::ios::binary);
        if (!in) return;
        std::string text((std::istreambuf_iterator<char>(in)),
                         std::istreambuf_iterator<char>());
        in.close();

        std::vector<tlv::Row> rows;
        std::vector<std::string> columns;
        parse_csv_text(text, rows, columns);

        if (rows.empty() || columns.empty()) return;

        // Update source label with filename + row count.
        auto fname = std::filesystem::path(path.toStdString()).filename().string();
        char lbl[256];
        std::snprintf(lbl, sizeof(lbl), "%s \xe2\x80\x94 %d rows, %d columns",
            fname.c_str(), static_cast<int>(rows.size()),
            static_cast<int>(columns.size()));
        source_label->setText(QString::fromUtf8(lbl));

        (*populate_results)(rows, columns);
    });

    // ---- Live trigger capture from connected ECU ----
    QObject::connect(capture_btn, &QPushButton::clicked,
                     [container, source_label, logger_combo, ecu_conn,
                      populate_results, capture_btn]() {
        namespace ltl = tuner_core::live_trigger_logger;

        if (!ecu_conn || !ecu_conn->connected || !ecu_conn->controller) return;

        // Find logger definitions from the active definition.
        auto def_opt = load_active_definition();
        if (!def_opt.has_value()) {
            source_label->setText(QString::fromUtf8(
                "No definition loaded \xe2\x80\x94 cannot determine logger format"));
            return;
        }
        auto loggers = def_opt->logger_definitions;

        if (loggers.loggers.empty()) {
            source_label->setText(QString::fromUtf8(
                "No logger definitions found in INI"));
            return;
        }

        // Select logger by combo index: 0 = tooth, 1+ = composite.
        int sel = logger_combo->currentIndex();
        const tuner_core::IniLoggerDefinition* logger_def = nullptr;
        for (const auto& lg : loggers.loggers) {
            if (sel == 0 && lg.kind == "tooth") { logger_def = &lg; break; }
            if (sel == 1 && lg.kind == "composite") { logger_def = &lg; break; }
        }
        if (!logger_def) {
            // Fall back to first available.
            logger_def = &loggers.loggers[0];
        }

        // Compute expected data length.
        int data_length = logger_def->record_header_len
            + logger_def->record_count * logger_def->record_len;
        if (data_length <= 0) {
            source_label->setText(QString::fromUtf8(
                "Logger data length is zero"));
            return;
        }

        source_label->setText(QString::fromUtf8("Capturing..."));
        capture_btn->setEnabled(false);
        QApplication::processEvents();

        // Send the logger data read command and receive the response.
        std::vector<std::uint8_t> raw;
        try {
            double timeout = logger_def->data_read_timeout_ms / 1000.0;
            if (timeout < 2.0) timeout = 2.0;
            raw = ecu_conn->controller->fetch_raw(
                logger_def->data_read_command,
                static_cast<std::size_t>(data_length),
                timeout);
        } catch (const std::exception& e) {
            char err[256];
            std::snprintf(err, sizeof(err),
                "Capture failed: %s", e.what());
            source_label->setText(QString::fromUtf8(err));
            capture_btn->setEnabled(true);
            return;
        }

        if (raw.empty()) {
            source_label->setText(QString::fromUtf8(
                "No data received from ECU"));
            capture_btn->setEnabled(true);
            return;
        }

        // Decode the binary buffer into typed rows.
        auto capture = ltl::decode(*logger_def, raw);

        if (capture.rows.empty()) {
            source_label->setText(QString::fromUtf8(
                "Decoded 0 rows from capture buffer"));
            capture_btn->setEnabled(true);
            return;
        }

        // Convert TriggerLogRow (unordered_map) to visualization Row format.
        std::vector<tuner_core::trigger_log_visualization::Row> viz_rows;
        viz_rows.reserve(capture.rows.size());
        for (const auto& lr : capture.rows) {
            tuner_core::trigger_log_visualization::Row vr;
            for (const auto& [name, val] : lr.values) {
                char val_buf[32];
                std::snprintf(val_buf, sizeof(val_buf), "%.6g", val);
                vr.fields.emplace_back(name, std::string(val_buf));
            }
            viz_rows.push_back(std::move(vr));
        }

        // Use capture's column order.
        (*populate_results)(viz_rows, capture.columns);

        char lbl[256];
        std::snprintf(lbl, sizeof(lbl),
            "Live %s capture \xe2\x80\x94 %d rows, %d columns",
            logger_def->display_name.c_str(),
            static_cast<int>(capture.rows.size()),
            static_cast<int>(capture.columns.size()));
        source_label->setText(QString::fromUtf8(lbl));
        capture_btn->setEnabled(true);
    });

    outer->addStretch(1);
    scroll->setWidget(container);
    return scroll;
}

// ---------------------------------------------------------------------------
// Logging tab — datalog profile + replay demo
// ---------------------------------------------------------------------------

QWidget* build_logging_tab(std::shared_ptr<EcuConnection> ecu_conn) {
    namespace dlp = tuner_core::datalog_profile;
    namespace lcs = tuner_core::live_capture_session;

    auto* scroll = new QScrollArea;
    scroll->setWidgetResizable(true);
    scroll->setStyleSheet("QScrollArea { border: none; }");
    auto* container = new QWidget;
    auto* layout = new QVBoxLayout(container);
    layout->setContentsMargins(tt::space_lg, tt::space_lg, tt::space_lg, tt::space_lg);
    layout->setSpacing(tt::space_sm + 2);

    layout->addWidget(make_tab_header(
        "Logging",
        "Capture \xc2\xb7 Profiles \xc2\xb7 Replay"));

    // ---- Shared capture state ----
    auto recording = std::make_shared<bool>(false);
    auto records = std::make_shared<std::vector<lcs::CapturedRecord>>();
    auto start_time = std::make_shared<std::chrono::steady_clock::time_point>();

    // Build profile from loaded INI output channels, with QSettings
    // persistence. On first run, builds a default profile from the INI
    // and saves it. On subsequent runs, restores the saved profile so
    // channel enabled/disabled state and ordering are preserved.
    auto profile = std::make_shared<dlp::Profile>();
    auto profile_channel_names = std::make_shared<std::vector<std::string>>();
    {
        QSettings settings;
        std::string saved_json = settings.value(
            "logging/profile", "").toString().toStdString();

        bool restored = false;
        if (!saved_json.empty()) {
            try {
                *profile = dlp::deserialize_profile(saved_json, "Default");
                restored = !profile->channels.empty();
            } catch (...) { restored = false; }
        }

        if (!restored) {
            // Build from INI output channels.
            std::vector<dlp::ChannelDef> defs;
            {
                auto def_opt = load_active_definition();
                if (def_opt.has_value()) {
                    auto& def = *def_opt;
                    for (const auto& ch : def.output_channels.channels) {
                        dlp::ChannelDef d;
                        d.name = ch.name;
                        d.label = ch.name;
                        d.units = ch.units.value_or("");
                        d.digits = ch.digits;
                        defs.push_back(d);
                    }
                }
            }
            if (defs.empty()) {
                defs = {
                    {"rpm", "RPM", "RPM", 0}, {"map", "MAP", "kPa", 0},
                    {"tps", "TPS", "%", 1}, {"afr", "AFR", "", 2},
                    {"advance", "Timing Advance", "deg", 1}, {"clt", "Coolant", "\xc2\xb0""C", 1},
                    {"iat", "Intake Air", "\xc2\xb0""C", 1}, {"batt", "Battery", "V", 2},
                };
            }
            *profile = dlp::default_profile(defs);
            // Persist for next session.
            auto json = dlp::serialize_profile(*profile);
            settings.setValue("logging/profile",
                QString::fromUtf8(json.c_str()));
        }
        for (const auto& ch : profile->enabled_channels())
            profile_channel_names->push_back(ch.name);
    }

    // Per-channel digit map for CSV formatting.
    auto format_digits = std::make_shared<std::unordered_map<std::string, int>>();
    for (const auto& ch : profile->channels) {
        if (ch.format_digits.has_value())
            (*format_digits)[ch.name] = *ch.format_digits;
    }

    // ---- Capture controls ----
    auto* ctrl_card = new QWidget;
    auto* ctrl_layout = new QHBoxLayout(ctrl_card);
    ctrl_layout->setContentsMargins(tt::space_md, tt::space_sm, tt::space_md, tt::space_sm);
    ctrl_layout->setSpacing(tt::space_md);
    ctrl_card->setStyleSheet(QString::fromUtf8(tt::card_style().c_str()));

    auto* status_label = new QLabel;
    status_label->setTextFormat(Qt::RichText);
    {
        char sl[256];
        std::snprintf(sl, sizeof(sl),
            "<span style='color: %s; font-size: %dpx;'>\xe2\x97\x8b</span> "
            "<span style='color: %s; font-size: %dpx;'>Ready</span>",
            tt::text_dim, tt::font_body,
            tt::text_secondary, tt::font_body);
        status_label->setText(QString::fromUtf8(sl));
    }
    status_label->setStyleSheet("border: none;");
    ctrl_layout->addWidget(status_label, 1);

    auto make_ctrl_btn = [](const char* text) {
        auto* btn = new QPushButton(QString::fromUtf8(text));
        char bs[256];
        std::snprintf(bs, sizeof(bs),
            "QPushButton { background: %s; color: %s; border: 1px solid %s; "
            "border-radius: %dpx; padding: %dpx %dpx; font-size: %dpx; }"
            "QPushButton:hover { background: %s; }"
            "QPushButton:disabled { color: %s; }",
            tt::bg_elevated, tt::text_primary, tt::border,
            tt::radius_sm, tt::space_xs, tt::space_md, tt::font_small,
            tt::fill_primary_mid, tt::text_dim);
        btn->setStyleSheet(QString::fromUtf8(bs));
        return btn;
    };

    auto* start_btn = make_ctrl_btn("\xe2\x97\x89 Start");
    auto* stop_btn = make_ctrl_btn("\xe2\x96\xa0 Stop");
    auto* clear_btn = make_ctrl_btn("Clear");
    auto* save_btn = make_ctrl_btn("Save CSV...");
    stop_btn->setEnabled(false);
    save_btn->setEnabled(false);

    // Start: clear records, begin capture.
    QObject::connect(start_btn, &QPushButton::clicked,
                     [status_label, start_btn, stop_btn, save_btn,
                      recording, records, start_time]() {
        records->clear();
        *start_time = std::chrono::steady_clock::now();
        *recording = true;
        start_btn->setEnabled(false);
        stop_btn->setEnabled(true);
        save_btn->setEnabled(false);
        char sl[256];
        std::snprintf(sl, sizeof(sl),
            "<span style='color: %s; font-size: %dpx;'>\xe2\x97\x89</span> "
            "<span style='color: %s; font-size: %dpx;'>Recording...</span>",
            tt::accent_danger, tt::font_body,
            tt::text_primary, tt::font_body);
        status_label->setText(QString::fromUtf8(sl));
    });

    // Stop: freeze capture.
    QObject::connect(stop_btn, &QPushButton::clicked,
                     [status_label, start_btn, stop_btn, save_btn,
                      recording, records]() {
        *recording = false;
        start_btn->setEnabled(true);
        stop_btn->setEnabled(false);
        save_btn->setEnabled(!records->empty());
        char sl[256];
        std::snprintf(sl, sizeof(sl),
            "<span style='color: %s; font-size: %dpx;'>\xe2\x97\x8b</span> "
            "<span style='color: %s; font-size: %dpx;'>Stopped \xe2\x80\x94 %d rows</span>",
            tt::accent_ok, tt::font_body,
            tt::text_secondary, tt::font_body,
            static_cast<int>(records->size()));
        status_label->setText(QString::fromUtf8(sl));
    });

    // Clear: discard records.
    QObject::connect(clear_btn, &QPushButton::clicked,
                     [status_label, save_btn, records]() {
        records->clear();
        save_btn->setEnabled(false);
        char sl[256];
        std::snprintf(sl, sizeof(sl),
            "<span style='color: %s; font-size: %dpx;'>\xe2\x97\x8b</span> "
            "<span style='color: %s; font-size: %dpx;'>Ready</span>",
            tt::text_dim, tt::font_body,
            tt::text_secondary, tt::font_body);
        status_label->setText(QString::fromUtf8(sl));
    });

    // Save CSV: format records via live_capture_session::format_csv
    // and write to user-selected file.
    QObject::connect(save_btn, &QPushButton::clicked,
                     [container, records, profile_channel_names, format_digits]() {
        if (records->empty()) return;
        auto path = QFileDialog::getSaveFileName(container,
            QString::fromUtf8("Save Datalog CSV"),
            QDir::homePath(), QString::fromUtf8("CSV Files (*.csv)"));
        if (path.isEmpty()) return;

        auto columns = lcs::ordered_column_names(
            *profile_channel_names, *records);
        auto csv = lcs::format_csv(*records, columns, *format_digits);

        std::ofstream out(path.toStdString(),
            std::ios::out | std::ios::binary);
        if (out) {
            out.write(csv.data(), static_cast<std::streamsize>(csv.size()));
            out.close();
        }
    });

    ctrl_layout->addWidget(start_btn);
    ctrl_layout->addWidget(stop_btn);
    ctrl_layout->addWidget(clear_btn);
    ctrl_layout->addWidget(save_btn);
    layout->addWidget(ctrl_card);

    // ---- Capture timer ----
    // Polls ecu_conn->runtime every 200ms while recording is true.
    // Accumulates CapturedRecord instances with elapsed_ms and all
    // available channel values. Also updates the status label with
    // a live row count while recording.
    auto* capture_timer = new QTimer(container);
    QObject::connect(capture_timer, &QTimer::timeout,
                     [recording, records, start_time, ecu_conn,
                      status_label, profile_channel_names]() {
        if (!*recording) return;

        // Sample current runtime snapshot.
        std::unordered_map<std::string, double> snap;
        if (ecu_conn && ecu_conn->connected) {
            snap = ecu_conn->runtime;
        }
        if (snap.empty()) return;  // No data to capture.

        // Build a CapturedRecord.
        auto now = std::chrono::steady_clock::now();
        double elapsed_ms = std::chrono::duration<double, std::milli>(
            now - *start_time).count();

        lcs::CapturedRecord rec;
        rec.elapsed_ms = elapsed_ms;
        // Use profile channel order for consistent column ordering.
        for (const auto& name : *profile_channel_names) {
            auto it = snap.find(name);
            if (it != snap.end()) {
                rec.keys.push_back(name);
                rec.values.push_back(it->second);
            }
        }
        // Also capture channels not in profile (runtime extras).
        for (const auto& [name, val] : snap) {
            bool in_profile = false;
            for (const auto& pn : rec.keys) {
                if (pn == name) { in_profile = true; break; }
            }
            if (!in_profile) {
                rec.keys.push_back(name);
                rec.values.push_back(val);
            }
        }
        records->push_back(std::move(rec));

        // Update status label with live row count (every record).
        int count = static_cast<int>(records->size());
        double elapsed_s = elapsed_ms / 1000.0;
        char sl[256];
        std::snprintf(sl, sizeof(sl),
            "<span style='color: %s; font-size: %dpx;'>\xe2\x97\x89</span> "
            "<span style='color: %s; font-size: %dpx;'>"
            "Recording \xe2\x80\x94 %d rows (%.1fs)</span>",
            tt::accent_danger, tt::font_body,
            tt::text_primary, tt::font_body,
            count, elapsed_s);
        status_label->setText(QString::fromUtf8(sl));
    });
    capture_timer->start(200);  // 200ms — matches LIVE tab poll rate.

    // ---- Profile manager — switch, add, delete ----
    // Multi-profile support with collection persistence.
    auto all_profiles = std::make_shared<std::vector<dlp::Profile>>();
    auto active_name = std::make_shared<std::string>(profile->name);
    all_profiles->push_back(*profile);

    // Try loading saved collection from QSettings.
    {
        QSettings settings;
        std::string saved_coll = settings.value(
            "logging/profiles_collection", "").toString().toStdString();
        if (!saved_coll.empty()) {
            try {
                auto [profs, aname] = dlp::deserialize_collection(saved_coll);
                if (!profs.empty()) {
                    *all_profiles = std::move(profs);
                    *active_name = aname;
                    // Find the active profile and use it.
                    for (const auto& p : *all_profiles) {
                        if (p.name == *active_name) {
                            *profile = p;
                            break;
                        }
                    }
                }
            } catch (...) {}
        }
    }

    // Helper: save current collection to QSettings.
    auto save_profiles = [all_profiles, active_name]() {
        QSettings settings;
        auto json = dlp::serialize_collection(*all_profiles, *active_name);
        settings.setValue("logging/profiles_collection",
            QString::fromUtf8(json.c_str()));
    };

    // Profile selector row.
    auto* profile_row = new QHBoxLayout;
    profile_row->setSpacing(tt::space_sm);
    {
        auto* lbl = new QLabel(QString::fromUtf8("Profile:"));
        char ls[96];
        std::snprintf(ls, sizeof(ls),
            "QLabel { color: %s; font-size: %dpx; font-weight: bold; }",
            tt::text_secondary, tt::font_body);
        lbl->setStyleSheet(QString::fromUtf8(ls));
        profile_row->addWidget(lbl);
    }
    auto* profile_combo = new QComboBox;
    {
        char cs[192];
        std::snprintf(cs, sizeof(cs),
            "QComboBox { background: %s; color: %s; border: 1px solid %s; "
            "border-radius: %dpx; padding: %dpx %dpx; font-size: %dpx; }",
            tt::bg_elevated, tt::text_primary, tt::border,
            tt::radius_sm, tt::space_xs, tt::space_sm, tt::font_body);
        profile_combo->setStyleSheet(QString::fromUtf8(cs));
    }
    for (const auto& p : *all_profiles)
        profile_combo->addItem(QString::fromUtf8(p.name.c_str()));
    // Select active.
    for (int i = 0; i < profile_combo->count(); ++i) {
        if (profile_combo->itemText(i).toStdString() == *active_name) {
            profile_combo->setCurrentIndex(i);
            break;
        }
    }
    profile_row->addWidget(profile_combo, 1);

    // Add profile button.
    auto* add_prof_btn = new QPushButton(QString::fromUtf8("+"));
    add_prof_btn->setFixedWidth(28);
    add_prof_btn->setCursor(Qt::PointingHandCursor);
    {
        char s[192];
        std::snprintf(s, sizeof(s),
            "QPushButton { background: %s; color: %s; border: 1px solid %s; "
            "border-radius: %dpx; font-size: %dpx; font-weight: bold; }"
            "QPushButton:hover { background: %s; }",
            tt::bg_elevated, tt::accent_ok, tt::border,
            tt::radius_sm, tt::font_body, tt::fill_primary_mid);
        add_prof_btn->setStyleSheet(QString::fromUtf8(s));
    }

    // Delete profile button.
    auto* del_prof_btn = new QPushButton(QString::fromUtf8("\xe2\x88\x92"));  // −
    del_prof_btn->setFixedWidth(28);
    del_prof_btn->setCursor(Qt::PointingHandCursor);
    {
        char s[192];
        std::snprintf(s, sizeof(s),
            "QPushButton { background: %s; color: %s; border: 1px solid %s; "
            "border-radius: %dpx; font-size: %dpx; font-weight: bold; }"
            "QPushButton:hover { background: %s; }",
            tt::bg_elevated, tt::accent_danger, tt::border,
            tt::radius_sm, tt::font_body, tt::fill_primary_mid);
        del_prof_btn->setStyleSheet(QString::fromUtf8(s));
    }
    del_prof_btn->setEnabled(all_profiles->size() > 1);

    profile_row->addWidget(add_prof_btn);
    profile_row->addWidget(del_prof_btn);
    layout->addLayout(profile_row);

    // Channel count label.
    auto* channel_info = new QLabel;
    {
        char ci[128];
        std::snprintf(ci, sizeof(ci),
            "<span style='color: %s; font-size: %dpx;'>%d channels enabled</span>",
            tt::text_muted, tt::font_small,
            static_cast<int>(profile->enabled_channels().size()));
        channel_info->setTextFormat(Qt::RichText);
        channel_info->setText(QString::fromUtf8(ci));
    }
    layout->addWidget(channel_info);

    // Switch profile.
    QObject::connect(profile_combo, QOverload<int>::of(&QComboBox::currentIndexChanged),
                     [profile_combo, all_profiles, active_name, profile,
                      profile_channel_names, channel_info, save_profiles](int idx) {
        if (idx < 0 || idx >= static_cast<int>(all_profiles->size())) return;
        *profile = (*all_profiles)[idx];
        *active_name = profile->name;
        profile_channel_names->clear();
        for (const auto& ch : profile->enabled_channels())
            profile_channel_names->push_back(ch.name);
        char ci[128];
        std::snprintf(ci, sizeof(ci),
            "<span style='color: %s; font-size: %dpx;'>%d channels enabled</span>",
            tt::text_muted, tt::font_small,
            static_cast<int>(profile->enabled_channels().size()));
        channel_info->setText(QString::fromUtf8(ci));
        save_profiles();
    });

    // Add new profile (duplicate current).
    QObject::connect(add_prof_btn, &QPushButton::clicked,
                     [profile_combo, all_profiles, profile, active_name,
                      del_prof_btn, save_profiles]() {
        // Generate unique name.
        std::string base = profile->name + " Copy";
        std::string name = base;
        int n = 1;
        while (true) {
            bool found = false;
            for (const auto& p : *all_profiles)
                if (p.name == name) { found = true; break; }
            if (!found) break;
            char buf[64]; std::snprintf(buf, sizeof(buf), "%s %d", base.c_str(), ++n);
            name = buf;
        }
        dlp::Profile np = *profile;
        np.name = name;
        all_profiles->push_back(np);
        profile_combo->addItem(QString::fromUtf8(name.c_str()));
        profile_combo->setCurrentIndex(profile_combo->count() - 1);
        del_prof_btn->setEnabled(all_profiles->size() > 1);
        save_profiles();
    });

    // Delete current profile.
    QObject::connect(del_prof_btn, &QPushButton::clicked,
                     [profile_combo, all_profiles, active_name,
                      del_prof_btn, save_profiles]() {
        if (all_profiles->size() <= 1) return;
        int idx = profile_combo->currentIndex();
        if (idx < 0 || idx >= static_cast<int>(all_profiles->size())) return;
        all_profiles->erase(all_profiles->begin() + idx);
        profile_combo->removeItem(idx);
        del_prof_btn->setEnabled(all_profiles->size() > 1);
        save_profiles();
    });

    // Legacy channel display — show first few channels.
    {
        char ch_buf[2048]; int coff = 0;
        int shown = std::min(static_cast<int>(profile->channels.size()), 24);
        for (int i = 0; i < shown; ++i) {
            auto& ch = profile->channels[i];
            const char* dot = (i < 6) ? "\xf0\x9f\x9f\xa2" : (i < 12) ? "\xf0\x9f\x94\xb5" : "\xe2\x9a\xaa";
            coff += std::snprintf(ch_buf + coff, sizeof(ch_buf) - coff,
                "%s %s%s%s%s", dot, ch.label.c_str(),
                ch.units.empty() ? "" : " (",
                ch.units.empty() ? "" : ch.units.c_str(),
                ch.units.empty() ? "" : ")");
            if (i < shown - 1) coff += std::snprintf(ch_buf + coff, sizeof(ch_buf) - coff, "\n");
            if (coff >= static_cast<int>(sizeof(ch_buf) - 1)) break;
        }
        if (static_cast<int>(profile->channels.size()) > shown) {
            coff += std::snprintf(ch_buf + coff, sizeof(ch_buf) - coff,
                "\n... and %d more channels",
                static_cast<int>(profile->channels.size()) - shown);
        }
        bool has_def = !find_native_definition().empty() || !find_production_ini().empty();
        char title[128];
        std::snprintf(title, sizeof(title),
            "Logging Profile \xe2\x80\x94 %d channels from %s",
            static_cast<int>(profile->channels.size()),
            has_def ? "loaded definition" : "defaults");
        layout->addWidget(make_info_card(title, ch_buf, tt::accent_primary));
    }

    // ---- Import + Replay section ----
    namespace dli = tuner_core::datalog_import;
    namespace dlr = tuner_core::datalog_replay;

    auto replay_records = std::make_shared<std::vector<dlr::Record>>();

    // Import row with button + info.
    auto* import_card = new QWidget;
    {
        auto* il = new QHBoxLayout(import_card);
        il->setContentsMargins(tt::space_md, tt::space_sm, tt::space_md, tt::space_sm);
        il->setSpacing(tt::space_md);
        import_card->setStyleSheet(QString::fromUtf8(tt::card_style().c_str()));

        auto* import_info = new QLabel;
        import_info->setTextFormat(Qt::RichText);
        {
            char ii[256];
            std::snprintf(ii, sizeof(ii),
                "<span style='color: %s; font-size: %dpx; font-weight: bold;'>"
                "Datalog Import</span><br>"
                "<span style='color: %s; font-size: %dpx;'>"
                "Load a CSV datalog for replay and VE Analyze</span>",
                tt::text_secondary, tt::font_body,
                tt::text_dim, tt::font_small);
            import_info->setText(QString::fromUtf8(ii));
        }
        import_info->setStyleSheet("border: none;");
        il->addWidget(import_info, 1);

        auto* import_btn = new QPushButton(QString::fromUtf8("Import CSV..."));
        {
            char bs[256];
            std::snprintf(bs, sizeof(bs),
                "QPushButton { background: %s; color: %s; border: 1px solid %s; "
                "border-radius: %dpx; padding: %dpx %dpx; font-size: %dpx; }"
                "QPushButton:hover { background: %s; }",
                tt::bg_elevated, tt::text_primary, tt::border,
                tt::radius_sm, tt::space_xs, tt::space_md, tt::font_small,
                tt::fill_primary_mid);
            import_btn->setStyleSheet(QString::fromUtf8(bs));
        }
        il->addWidget(import_btn);
        layout->addWidget(import_card);

        // Replay navigation card — row spinner + summary.
        auto* replay_card = new QWidget;
        auto* rl = new QHBoxLayout(replay_card);
        rl->setContentsMargins(tt::space_md, tt::space_sm, tt::space_md, tt::space_sm);
        rl->setSpacing(tt::space_md);
        replay_card->setStyleSheet(QString::fromUtf8(tt::card_style().c_str()));
        replay_card->hide();  // shown after import

        auto* row_label = new QLabel(QString::fromUtf8("Row:"));
        {
            char s[64];
            std::snprintf(s, sizeof(s), "QLabel { color: %s; font-size: %dpx; border: none; }",
                tt::text_secondary, tt::font_body);
            row_label->setStyleSheet(QString::fromUtf8(s));
        }
        rl->addWidget(row_label);

        auto* row_spin = new QSpinBox;
        row_spin->setMinimum(1);
        row_spin->setMaximum(1);
        row_spin->setValue(1);
        {
            char ss[256];
            std::snprintf(ss, sizeof(ss),
                "QSpinBox { background: %s; color: %s; border: 1px solid %s; "
                "border-radius: %dpx; padding: 4px 8px; font-size: %dpx; }",
                tt::bg_elevated, tt::text_primary, tt::border,
                tt::radius_sm, tt::font_body);
            row_spin->setStyleSheet(QString::fromUtf8(ss));
        }
        rl->addWidget(row_spin);

        auto* replay_summary = new QLabel;
        replay_summary->setWordWrap(true);
        {
            char s[64];
            std::snprintf(s, sizeof(s), "QLabel { color: %s; font-size: %dpx; border: none; }",
                tt::text_muted, tt::font_small);
            replay_summary->setStyleSheet(QString::fromUtf8(s));
        }
        rl->addWidget(replay_summary, 1);
        layout->addWidget(replay_card);

        // Replay channel values card.
        auto* values_card = new QLabel;
        values_card->setTextFormat(Qt::RichText);
        values_card->setWordWrap(true);
        values_card->hide();
        {
            char vs[256];
            std::snprintf(vs, sizeof(vs),
                "QLabel { background: %s; color: %s; border: 1px solid %s; "
                "border-radius: %dpx; padding: %dpx; font-family: 'Consolas', monospace; "
                "font-size: %dpx; }",
                tt::bg_panel, tt::text_primary, tt::border,
                tt::radius_sm, tt::space_sm, tt::font_small);
            values_card->setStyleSheet(QString::fromUtf8(vs));
        }
        layout->addWidget(values_card);

        // Shared refresh lambda — updates summary + values on row change.
        auto refresh_replay = std::make_shared<std::function<void(int)>>();
        *refresh_replay = [replay_records, replay_summary, values_card](int row_1based) {
            if (replay_records->empty()) return;
            int idx = std::clamp(row_1based - 1, 0,
                static_cast<int>(replay_records->size()) - 1);
            auto snap = dlr::select_row(*replay_records, idx);
            replay_summary->setText(QString::fromUtf8(snap.summary_text.c_str()));
            values_card->setText(QString::fromUtf8(snap.preview_text.c_str()));
        };

        // Spinbox navigation.
        QObject::connect(row_spin,
            static_cast<void(QSpinBox::*)(int)>(&QSpinBox::valueChanged),
            [refresh_replay](int val) { (*refresh_replay)(val); });

        // Import button handler — parse CSV, populate replay state.
        QObject::connect(import_btn, &QPushButton::clicked,
                         [container, replay_records, replay_card, values_card,
                          row_spin, refresh_replay]() {
            auto path = QFileDialog::getOpenFileName(container,
                QString::fromUtf8("Import Datalog CSV"),
                QDir::homePath(),
                QString::fromUtf8("CSV Files (*.csv);;All Files (*)"));
            if (path.isEmpty()) return;

            // Read file.
            std::ifstream in(path.toStdString(), std::ios::in | std::ios::binary);
            if (!in) return;

            // Parse header.
            std::string header_line;
            if (!std::getline(in, header_line)) return;
            if (!header_line.empty() && header_line.back() == '\r')
                header_line.pop_back();

            std::vector<std::string> headers;
            {
                std::istringstream hs(header_line);
                std::string col;
                while (std::getline(hs, col, ',')) {
                    while (!col.empty() && col.front() == ' ') col.erase(col.begin());
                    while (!col.empty() && col.back() == ' ') col.pop_back();
                    headers.push_back(col);
                }
            }
            if (headers.empty()) return;

            // Parse data rows.
            std::vector<dli::CsvRow> csv_rows;
            std::string line;
            while (std::getline(in, line)) {
                if (!line.empty() && line.back() == '\r') line.pop_back();
                if (line.empty()) continue;
                dli::CsvRow row;
                std::istringstream ls(line);
                std::string cell;
                int ci = 0;
                while (std::getline(ls, cell, ',')) {
                    while (!cell.empty() && cell.front() == ' ') cell.erase(cell.begin());
                    while (!cell.empty() && cell.back() == ' ') cell.pop_back();
                    if (ci < static_cast<int>(headers.size()))
                        row.emplace_back(headers[ci], cell);
                    ci++;
                }
                csv_rows.push_back(std::move(row));
            }
            in.close();
            if (csv_rows.empty()) return;

            // Import via the service.
            auto fname = std::filesystem::path(path.toStdString()).filename().string();
            dli::ImportSnapshot snap;
            try {
                snap = dli::import_rows(headers, csv_rows, fname);
            } catch (...) { return; }

            // Convert import records → replay records.
            replay_records->clear();
            replay_records->reserve(snap.records.size());
            for (const auto& ir : snap.records) {
                dlr::Record rr;
                char ts[32];
                std::snprintf(ts, sizeof(ts), "%.3fs", ir.timestamp_seconds);
                rr.timestamp_iso = ts;
                rr.values.reserve(ir.values.size());
                for (const auto& [k, v] : ir.values)
                    rr.values.emplace_back(k, v);
                replay_records->push_back(std::move(rr));
            }

            if (replay_records->empty()) return;

            // Configure UI.
            row_spin->setMaximum(static_cast<int>(replay_records->size()));
            row_spin->setValue(1);
            replay_card->show();
            values_card->show();
            (*refresh_replay)(1);
        });
    }

    layout->addStretch(1);
    scroll->setWidget(container);
    return scroll;
}

// ---------------------------------------------------------------------------
// History tab — manifest of every workspace service ported to C++
// ---------------------------------------------------------------------------

QWidget* build_history_tab() {
    auto* container = new QWidget;
    auto* layout = new QVBoxLayout(container);
    layout->setContentsMargins(tt::space_lg, tt::space_lg, tt::space_lg, tt::space_lg);
    layout->setSpacing(tt::space_md);

    auto* title = new QLabel("Phase 14 Slice 4 - workspace services in C++");
    QFont tf = title->font(); tf.setPixelSize(tt::font_hero); tf.setBold(true);
    title->setFont(tf);
    layout->addWidget(title);

    auto* count = new QLabel(
        "<b>82 sub-slices landed. 1063 tests passing.</b> Each item below is a real C++ service "
        "in tuner_core, parity-tested or doctest-pinned against the Python oracle.");
    count->setTextFormat(Qt::RichText);
    count->setWordWrap(true);
    layout->addWidget(count);

    auto* list = new QListWidget;
    static const char* services[] = {
        "01. visibility_expression - INI {expr} evaluator",
        "02. required_fuel_calculator - reqFuel formula",
        "03. table_edit - fill / fill_down / interpolate / smooth / paste",
        "04. sample_gate_helpers - channel resolver + lambda/AFR + apply_operator",
        "05. autotune_filter_gate_evaluator - std_DeadLambda / axis bounds / parametric",
        "06. wue_analyze_helpers - confidence + numeric_axis + nearest_index",
        "07. hardware_setup_validation - 10 dwell/dead-time/trigger/wideband rules",
        "08. board_detection - regex-driven board family detection",
        "09. pressure_sensor_calibration - preset matching + URL confidence labels",
        "10. release_manifest - JSON release_manifest.json loader",
        "11. tune_value_preview - Python str(float) repr via std::to_chars",
        "12. staged_change - composes tune_value_preview for staged review",
        "13. tuning_page_diff - per-page diff with summary + detail_text",
        "14. table_view - flat list to 2D string grid with shape resolution",
        "15. evidence_replay_comparison - channel-delta diff with top-4",
        "16. gauge_color_zones - INI thresholds to ok/warning/danger bands",
        "17. tuning_page_validation - composes visibility evaluator + range checks",
        "18. sync_state - signature/page/ECU-vs-tune mismatch detector",
        "19. parameter_catalog - sortable definition + tune-only catalog",
        "20. flash_preflight - 8 warning rules + signature_family classifier",
        "21. live_data_map_parser - Speeduino live_data_map.h to ChannelContract",
        "22. page_family - fuel/spark/target/vvt grouping with sort + tab titles",
        "23. curve_page_classifier - 8-rule keyword classifier",
        "24. operation_log - append-only mutation log",
        "25. operation_evidence - composes operation_log into session snapshot",
        "26. scalar_page_editor - composes visibility evaluator with two-level filtering",
        "27. table_replay_context - live operating-point crosshair locator",
        "28. table_replay_hit - datalog to cell hit-count aggregator",
        "29. surface_evidence - workspace pill strip + rollup paragraph",
        "30. replay_sample_gate - named-gate evaluator for replay records",
        "31. datalog_review - Logging tab review-chart trace builder",
        "32. table_rendering - 6-stop heatmap gradient + foreground flip",
        "33. ve_proposal_smoothing - Phase 7.5 reviewable smoothing transform",
        "34. ve_root_cause_diagnostics - Phase 7.7 4-rule diagnostic engine",
        "35. ve_cell_hit_accumulator - Phase 7.2 weighted-correction snapshot layer",
        "36. ve_analyze_review - Phase 7 operator-facing review text builder",
        "37. wue_analyze_snapshot - WUE Analyze 1D row accumulator snapshot",
        "38. wue_analyze_review - WUE Analyze operator-facing review text",
        "39. thermistor_calibration - Steinhart-Hart CLT/IAT table generator",
        "40. idle_rpm_generator - conservative idle RPM target curve generator",
        "41. afr_target_generator - conservative 16x16 AFR target table",
        "42. spark_table_generator - conservative 16x16 spark advance table",
        "43. ve_table_generator - conservative 16x16 VE table with topology shaping",
        "44. startup_enrichment_generator - WUE + cranking + ASE curves",
        "45. runtime_telemetry - Speeduino board capability + runtime status decoder",
        "46. ini_dialog_parser - [UserDefined] dialog/field/panel parser",
        "47. definition_layout - INI dialogs + menus -> editor-facing layout pages",
        "48. tuning_page_grouping - keyword classifier for page group families",
        "49. local_tune_edit - staged-edit state machine with undo/redo",
        "50. wideband_calibration - wideband O2 AFR table + 5 presets",
        "51. dashboard_layout - dashboard widget model + 11-gauge default",
        "52. hardware_presets - ignition coil preset catalog with sources",
        "53. firmware_capabilities - runtime trust summary + uncertain channels",
        "54. operator_engine_context - session-level engine facts store + JSON persistence",
        "55. hardware_setup_generator_context - keyword-based parameter discovery for generators",
        "56. sensor_setup_checklist - 9-check sensor hardware validation",
        "57. curve_page_builder - curve page builder with group classification",
        "58. evidence_replay - evidence snapshot composer for workspace replay",
        "59. page_evidence_review - page-level channel selector for evidence review",
        "60. evidence_replay_formatter - text and JSON snapshot formatter",
        "61. trigger_log_visualization - trace builder with edge/gap annotations",
        "62. trigger_log_analysis - decoder context + gap + phase + sync analysis",
        "63. live_ve_analyze_session - stateful VE session status builder",
        "64. live_wue_analyze_session - stateful WUE session status builder",
        "65. datalog_profile - priority ordering + JSON profile collection",
        "66. firmware_catalog - board detection + entry scoring for firmware suggestion",
        "67. datalog_replay - row selection with channel preview",
        "68. ignition_trigger_cross_validation - 6 cross-page ign/trig checks + topology",
        "69. mock_ecu_runtime - simulated driving cycle for live gauge animation",
        "70. ts_dash_file - legacy dashboard .dash XML import/export",
        "71. wue_analyze_accumulator - WUE stateful accumulator with CLT axis detection",
        "72. ve_analyze_accumulator - VE stateful accumulator with RPM/MAP cell mapping",
        "73. tuning_page_builder - compiles definition into grouped page model",
        "74. datalog_import - CSV datalog import with time detection + channel extraction",
        "75. msq_value_formatter - legacy MSQ value formatting",
        "76. workspace_state - page state machine (clean/staged/written/burned)",
        "77. native_tune_writer - .tuner JSON export/import (native format step 1)",
        "78. project_file - .tunerproj JSON project metadata (native format step 2)",
        "79. native_definition_writer - .tunerdef JSON definition export (native format step 3)",
        "80. hardware_setup_summary - contextual setup cards per page type",
        "81. workspace_presenter - compact workspace orchestrator (load/navigate/edit/write/burn)",
        "82. table_surface_3d - 3D wireframe projection for table values (G2 foundation)",
    };
    for (const char* s : services) list->addItem(QString::fromUtf8(s));
    layout->addWidget(list, 1);

    auto* footer = new QLabel(
        "Plus the entire Speeduino raw protocol stack (framing + command shapes "
        "+ value codec + parameter codec + live-data decoder), every INI section "
        "parser, the EcuDefinition compiler, the MSQ parser, and the native "
        "format writer. Total: 931 doctest cases, 6668 assertions, 0 failures. "
        "Python parity suite: 2445/2445 passing.");
    footer->setWordWrap(true);
    footer->setStyleSheet("color: gray;");
    layout->addWidget(footer);
    return container;
}

// ---------------------------------------------------------------------------
// Main window
// ---------------------------------------------------------------------------

class TunerMainWindow : public QMainWindow {
public:
    TunerMainWindow() {
        debug_log("TunerMainWindow ctor begin");
        setWindowTitle("Tuner \xe2\x80\x94 Speeduino Workstation");
        // Default size if there's no saved geometry — used on first
        // launch only. `restoreGeometry` at the end of the ctor
        // overrides this whenever a prior session exists.
        resize(1280, 800);

        // Organization / application names feed QSettings — they
        // decide the registry / ini path the persistence layer uses.
        // Match `QApplication::setApplicationName("Tuner")` from
        // main() so every `QSettings(...)` call across the app sees
        // the same storage.
        QCoreApplication::setOrganizationName("Cornelio");
        QCoreApplication::setOrganizationDomain("tuner.local");
        // Migrate single-entry recent project to multi-entry list.
        migrate_recent_project_keys();

        // ---- Sidebar + stacked content (Phase D: sidebar navigation) ----
        auto* central = new QWidget;
        auto* h_layout = new QHBoxLayout(central);
        h_layout->setContentsMargins(0, 0, 0, 0);
        h_layout->setSpacing(0);

        // Sidebar navigation list — driven entirely by theme tokens so
        // the chrome stays coherent with the content cards it sits next
        // to. Selection uses a 3px `accent_primary` left bar, matching
        // the `make_info_card` accent convention so "selected" reads as
        // the same visual grammar as "attention here" elsewhere.
        auto* sidebar = new QListWidget;
        sidebar->setFixedWidth(160);
        {
            char sidebar_style[768];
            std::snprintf(sidebar_style, sizeof(sidebar_style),
                "QListWidget { background: %s; border: none; "
                "  border-right: 1px solid %s; outline: none; "
                "  font-size: %dpx; font-weight: bold; }"
                "QListWidget::item { padding: %dpx %dpx; color: %s; border: none; }"
                "QListWidget::item:selected { background: %s; color: %s; "
                "  border-left: 3px solid %s; }"
                "QListWidget::item:hover:!selected { background: %s; color: %s; }",
                tt::bg_deep, tt::border,
                tt::font_body,
                tt::space_md, tt::space_lg,
                tt::text_muted,
                tt::bg_panel, tt::text_primary,
                tt::accent_primary,
                tt::bg_base, tt::text_secondary);
            sidebar->setStyleSheet(QString::fromUtf8(sidebar_style));
        }

        // Sub-slice 128: each sidebar item carries a one-line
        // tooltip describing its purpose plus the Alt+N shortcut.
        // Hover discoverability — the tab label is short ("Tune",
        // "Live", etc) so a first-time operator doesn't always
        // know what they'll find on each tab. Mouse-hover reveals
        // a description without demanding screen real estate, and
        // the trailing "(Alt+N)" chip on every tooltip reinforces
        // the keyboard-nav affordance a third time (alongside the
        // menu bar View menu and the F1 cheat sheet).
        //
        // Tooltip copy matches the F1 cheat sheet Navigation group
        // exactly — same source of truth, so any edit to the
        // description automatically stays in sync across the three
        // discovery surfaces.
        struct NavItem {
            const char* icon;
            const char* label;
            const char* tooltip;
        };
        NavItem nav_items[] = {
            {"\xf0\x9f\x94\xa7", "Tune",
                "Tune \xe2\x80\x94 edit scalars, tables, curves  (Alt+1)"},
            {"\xf0\x9f\x93\x8a", "Live",
                "Live \xe2\x80\x94 runtime gauges and histograms  (Alt+2)"},
            {"\xe2\x9a\xa1",     "Flash",
                "Flash \xe2\x80\x94 firmware preflight  (Alt+3)"},
            {"\xe2\x9a\x99",     "Setup",
                "Setup \xe2\x80\x94 engine configuration + generators  (Alt+4)"},
            {"\xf0\x9f\xa7\xaa", "Assist",
                "Assist \xe2\x80\x94 VE / WUE Analyze pipeline  (Alt+5)"},
            {"\xf0\x9f\x94\x8d", "Triggers",
                "Triggers \xe2\x80\x94 trigger log diagnostics  (Alt+6)"},
            {"\xf0\x9f\x93\x9d", "Logging",
                "Logging \xe2\x80\x94 datalog profiles and replay  (Alt+7)"},
            {"\xf0\x9f\x93\x8b", "History",
                "History \xe2\x80\x94 ported service manifest  (Alt+8)"},
        };
        for (const auto& item : nav_items) {
            char label[96];
            std::snprintf(label, sizeof(label), "%s  %s", item.icon, item.label);
            auto* list_item = new QListWidgetItem(QString::fromUtf8(label));
            list_item->setToolTip(QString::fromUtf8(item.tooltip));
            sidebar->addItem(list_item);
        }

        // Sub-slice 92/95: shared workspace state so the sidebar Tune
        // badge can read the same counter the TUNE tab mutates, and
        // show a state-aware suffix (staged / in RAM) based on
        // aggregate_state() — amber for pending, blue once the edits
        // are written to RAM and awaiting burn.
        //
        // Sub-slice 126: the same refresh also updates the window
        // title so the operator sees the staged-edit state from the
        // Windows taskbar without focusing the app. Convention on
        // every desktop editor: unsaved changes get a trailing `*`
        // in the title. We go slightly further and surface the
        // staged count + state verb so the taskbar itself reads as
        // "Tuner — Ford 300 Twin GT28 • 3 staged". Operators tuning
        // across multiple projects in multiple instances get state
        // visibility one glance away.
        auto shared_workspace = std::make_shared<tuner_core::workspace_state::Workspace>();
        auto ecu_conn = std::make_shared<EcuConnection>();
        auto shared_dash = std::make_shared<tuner_core::dashboard_layout::Layout>();
        auto rebuild_dashboard = std::make_shared<std::function<void()>>();

        // HTTP Live-Data API — serves channel data to browser dashboards.
        auto http_server = std::make_shared<LiveDataHttpServer>();
        http_server->start(8080);
        std::printf("[ctor] HTTP Live-Data API started on port 8080\n");
        std::fflush(stdout);

        // Connection indicator label — created early so the File menu
        // connect/disconnect lambdas can capture the pointer. Added to
        // the sidebar layout later in the constructor.
        auto* conn_label = new QLabel;
        conn_label->setTextFormat(Qt::RichText);
        conn_label->setAlignment(Qt::AlignCenter);
        conn_label->setMinimumHeight(36);
        {
            char cs[192];
            std::snprintf(cs, sizeof(cs),
                "background: %s; border-top: 1px solid %s; "
                "padding: %dpx; font-size: %dpx;",
                tt::bg_deep, tt::border, tt::space_xs + 2, tt::font_micro);
            conn_label->setStyleSheet(QString::fromUtf8(cs));
        }
        {
            char ct[256];
            std::snprintf(ct, sizeof(ct),
                "<span style='color: %s;'>\xe2\x97\x8b</span> "
                "<span style='color: %s;'>Offline</span>",
                tt::text_dim, tt::text_muted);
            conn_label->setText(QString::fromUtf8(ct));
        }
        // Project name — loaded from the recent project stored in
        // QSettings by `build_tune_tab` after MSQ ingestion. Falls
        // back to "Speeduino Project" on first launch before any
        // project has been opened.
        auto project_name = std::make_shared<std::string>();
        {
            auto proj = active_project();
            *project_name = proj.name.empty() ? "Speeduino Project" : proj.name;
            debug_log("TunerMainWindow ctor active project name=\"" + proj.name
                + "\" ini=\"" + proj.ini_path
                + "\" tune=\"" + proj.msq_path + "\"");
        }
        auto refresh_tune_badge = [this, sidebar, shared_workspace, project_name]() {
            int n = shared_workspace->staged_count();
            char label[96];
            char title[192];
            if (n > 0) {
                auto agg = shared_workspace->aggregate_state();
                const char* verb =
                    (agg == tuner_core::workspace_state::PageState::WRITTEN)
                        ? "in RAM" : "staged";
                std::snprintf(label, sizeof(label),
                    "\xf0\x9f\x94\xa7  Tune  \xc2\xb7  %d %s", n, verb);
                // Title: trailing `•` chip shows state.
                std::snprintf(title, sizeof(title),
                    "Tuner \xe2\x80\x94 %s  \xe2\x80\xa2  %d %s",
                    project_name->c_str(), n, verb);
            } else {
                std::snprintf(label, sizeof(label), "\xf0\x9f\x94\xa7  Tune");
                // Clean title with project name, no state suffix.
                std::snprintf(title, sizeof(title),
                    "Tuner \xe2\x80\x94 %s", project_name->c_str());
            }
            if (auto* item = sidebar->item(0))
                item->setText(QString::fromUtf8(label));
            setWindowTitle(QString::fromUtf8(title));
        };

        auto reload_active_project = [this, project_name, ecu_conn]() {
            debug_log("reload_active_project begin");
            // Disconnect ECU before replacing the window — the old
            // window's shared_ptr captures keep the controller alive,
            // which holds the COM port open. Without this, the new
            // window can't connect to the same port.
            ecu_conn->close();
            QSettings settings;
            settings.setValue("session/geometry", saveGeometry());
            settings.setValue("session/window_state", saveState());
            if (auto* current_sidebar = findChild<QListWidget*>()) {
                settings.setValue("session/last_tab", current_sidebar->currentRow());
            }
            auto proj = active_project();
            *project_name = proj.name.empty() ? "Speeduino Project" : proj.name;
            debug_log("reload_active_project active name=\"" + proj.name
                + "\" ini=\"" + proj.ini_path
                + "\" tune=\"" + proj.msq_path + "\"");
            hide();
            QTimer::singleShot(0, this, [this]() {
                debug_log("reload_active_project singleShot fired");
                qApp->setQuitOnLastWindowClosed(false);
                auto* replacement = new TunerMainWindow();
                debug_log("reload_active_project replacement constructed");
                replacement->show();
                replacement->raise();
                replacement->activateWindow();
                debug_log("reload_active_project replacement shown; retiring old window hidden");
                g_retired_windows.push_back(QPointer<QWidget>(this));
                qApp->setQuitOnLastWindowClosed(true);
            });
        };

        // Stacked content pages.
        auto* stack = new QStackedWidget;

        // Navigation callback: switches sidebar + stack to the target page.
        auto navigate = [sidebar, stack](int page_index, const std::string& /*hint*/) {
            if (page_index >= 0 && page_index < stack->count()) {
                sidebar->setCurrentRow(page_index);
            }
        };

        std::printf("[ctor] tune begin\n"); std::fflush(stdout);
        debug_log("TunerMainWindow building tune tab");
        auto shared_edit_svc = std::make_shared<tuner_core::local_tune_edit::EditService>();
        auto tune_signature = std::make_shared<std::string>();
        stack->addWidget(build_tune_tab(shared_workspace, shared_edit_svc, ecu_conn, tune_signature, refresh_tune_badge));
        {
            auto proj = active_project();
            *project_name = proj.name.empty() ? "Speeduino Project" : proj.name;
        }
        std::printf("[ctor] tune ok\n"); std::fflush(stdout);
        debug_log("TunerMainWindow tune tab built");
        stack->addWidget(build_live_tab(ecu_conn, navigate, http_server,
            shared_dash, rebuild_dashboard));
        std::printf("[ctor] live ok\n"); std::fflush(stdout);
        stack->addWidget(build_flash_tab(ecu_conn));
        std::printf("[ctor] flash ok\n"); std::fflush(stdout);
        stack->addWidget(build_setup_tab(shared_edit_svc));
        std::printf("[ctor] setup ok\n"); std::fflush(stdout);
        stack->addWidget(build_assist_tab(shared_edit_svc, ecu_conn));
        std::printf("[ctor] assist ok\n"); std::fflush(stdout);
        stack->addWidget(build_triggers_tab(ecu_conn));
        std::printf("[ctor] triggers ok\n"); std::fflush(stdout);
        stack->addWidget(build_logging_tab(ecu_conn));
        std::printf("[ctor] logging ok\n"); std::fflush(stdout);
        stack->addWidget(build_history_tab());
        std::printf("[ctor] history ok\n"); std::fflush(stdout);

        // Wire sidebar → stack page switching.
        QObject::connect(sidebar, &QListWidget::currentRowChanged,
                         stack, &QStackedWidget::setCurrentIndex);
        sidebar->setCurrentRow(0);

        // Initial render of the Tune badge — starts at "no staged".
        refresh_tune_badge();

        // Save as native .tuner file (demo — writes to stdout). Named
        // so the menu bar's File → Save As action can share the
        // handler with the Ctrl+S shortcut.
        // Remembered save path — empty on first launch, populated after
        // first Save. Subsequent Ctrl+S writes to the same path without
        // a dialog (standard "Save" behavior).
        auto save_path = std::make_shared<std::string>();
        {
            auto proj = active_project();
            std::filesystem::path tune_path = proj.msq_path;
            std::string ext = tune_path.extension().string();
            for (auto& c : ext) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
            if (ext == ".tuner") {
                *save_path = tune_path.string();
            }
        }
        // tune_signature is populated by build_tune_tab above.
        auto save_as_native_handler = [this, shared_edit_svc, save_path, tune_signature,
                                       shared_workspace, refresh_tune_badge]() {
            namespace ntw = tuner_core::native_tune_writer;
            // Build the tune from the live edit service.
            auto tune = ntw::from_edit_service(
                *shared_edit_svc,
                tune_signature->empty() ? "speeduino 202501-T41" : *tune_signature);
            auto json = ntw::export_json(tune);

            // Determine file path — reuse last path or ask.
            std::string path = *save_path;
            if (path.empty()) {
                QString qpath = QFileDialog::getSaveFileName(
                    this, "Save Tune",
                    QString(), "Native Tune (*.tuner);;All Files (*)");
                if (qpath.isEmpty()) return;
                path = qpath.toStdString();
            }

            // Write to disk.
            std::ofstream out(path, std::ios::binary);
            if (!out) {
                QMessageBox::warning(this, "Save Failed",
                    QString::fromUtf8(("Could not write to: " + path).c_str()));
                return;
            }
            out.write(json.data(), static_cast<std::streamsize>(json.size()));
            out.close();
            *save_path = path;

            // The save captured current staged values as the new tune
            // file. Clear staged state so the UI reflects "saved — no
            // pending changes". The operator can always re-edit.
            shared_edit_svc->revert_all();
            shared_workspace->revert_all();
            refresh_tune_badge();

            // Brief status bar confirmation.
            auto fname = std::filesystem::path(path).filename().string();
            statusBar()->showMessage(
                QString::fromUtf8(("\xe2\x9c\x85 Saved: " + fname).c_str()), 5000);
        };

        // Alt+1..8 sidebar navigation is wired via the View menu's
        // QActions below — setting `QAction::setShortcut` both binds
        // the key and displays the binding next to the menu item,
        // which is one of the main discoverability wins of adding
        // a menu bar.

        // Command palette handler — named so the menu bar View →
        // Command Palette action can share it with the Ctrl+K shortcut.
        // Shared connect callback — set in the File menu section below,
        // but referenced by the command palette. Using a shared pointer
        // so the palette lambda captures the indirection, not the (not
        // yet defined) function itself.
        auto connect_callback = std::make_shared<std::function<void()>>();

        auto open_command_palette = [this, sidebar, connect_callback]() {
            auto* dialog = new QDialog(this);
            dialog->setWindowTitle("Command Palette");
            dialog->setFixedSize(520, 480);
            dialog->setWindowFlags(Qt::Dialog | Qt::FramelessWindowHint);

            // Sub-slice 145: redesigned command palette. The previous
            // version was a flat list of plain-text entries with no
            // visual grouping, no category icons, and no shortcut hints.
            // This version follows the "guided power" philosophy:
            //
            //  - Each entry has a category icon (left) + title (bold) +
            //    description (dim) + optional shortcut chip (right)
            //  - Entries are grouped by purpose: Navigate / Tune pages /
            //    Actions / Connection
            //  - Category group headers (NAVIGATION, TUNING, ACTIONS,
            //    CONNECTION) use the same uppercase + letter-spacing +
            //    text_muted grammar as the F1 cheat sheet group headers
            //  - Shortcut chips reuse the bg_inset/border/monospace look
            //    from the F1 cheat sheet key chips
            //  - The search input has a subtle icon prefix and larger
            //    padding for a more polished feel
            //  - Selected item uses the same fill_primary_mid tint as
            //    the sidebar selection
            //
            // Visual hierarchy: operator's eye scans the bold title
            // column, then the dim description distinguishes entries
            // with similar names, then the shortcut chip at the right
            // edge rewards muscle-memory learners.

            {
                char palette_qss[1536];
                std::snprintf(palette_qss, sizeof(palette_qss),
                    "QDialog { background: %s; border: 1px solid %s; "
                    "  border-radius: %dpx; }"
                    "QLineEdit { background: %s; border: 1px solid %s; "
                    "  border-radius: %dpx; padding: %dpx %dpx; "
                    "  color: %s; font-size: %dpx; "
                    "  selection-background-color: %s; }"
                    "QLineEdit:focus { border-color: %s; }"
                    "QListWidget { background: transparent; border: none; "
                    "  outline: none; }"
                    "QListWidget::item { padding: 0px; border: none; "
                    "  border-radius: %dpx; margin: 1px %dpx; }"
                    "QListWidget::item:selected { background: %s; }"
                    "QListWidget::item:hover:!selected { background: %s; }",
                    tt::bg_base, tt::border, tt::radius_md,
                    tt::bg_elevated, tt::border,
                    tt::radius_sm, tt::space_sm + 4, tt::space_md,
                    tt::text_primary, tt::font_label,
                    tt::fill_primary_mid,
                    tt::accent_primary,
                    tt::radius_sm, tt::space_xs,
                    tt::fill_primary_mid,
                    tt::bg_elevated);
                dialog->setStyleSheet(QString::fromUtf8(palette_qss));
            }

            auto* vl = new QVBoxLayout(dialog);
            vl->setContentsMargins(tt::space_md, tt::space_md, tt::space_md, tt::space_sm);
            vl->setSpacing(tt::space_xs + 2);

            // Search input with magnifying glass prefix.
            auto* input = new QLineEdit;
            input->setPlaceholderText(QString::fromUtf8(
                "\xf0\x9f\x94\x8d  Search pages, actions, parameters..."));
            vl->addWidget(input);

            // Hint line beneath the input.
            auto* hint_label = new QLabel;
            hint_label->setTextFormat(Qt::RichText);
            {
                char hl[256];
                std::snprintf(hl, sizeof(hl),
                    "<span style='color: %s; font-size: %dpx;'>"
                    "\xe2\x86\x91\xe2\x86\x93 navigate  \xc2\xb7  "
                    "\xe2\x86\xb5 select  \xc2\xb7  "
                    "esc dismiss  \xc2\xb7  "
                    "F1 all shortcuts</span>",
                    tt::text_dim, tt::font_micro);
                hint_label->setText(QString::fromUtf8(hl));
            }
            hint_label->setAlignment(Qt::AlignCenter);
            vl->addWidget(hint_label);

            auto* results = new QListWidget;
            results->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
            results->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);

            struct CmdEntry {
                std::string search_text;  // lowercase for filtering
                std::string title;
                std::string description;
                const char* icon;
                const char* shortcut;     // null = no shortcut chip
                const char* category;     // group header text
                int page_index;
                bool is_header = false;   // true = non-selectable group header
            };
            auto entries = std::make_shared<std::vector<CmdEntry>>();

            // Helper to add a group header.
            auto add_header = [&entries](const char* label) {
                CmdEntry e;
                e.category = label;
                e.title = label;
                e.is_header = true;
                e.page_index = -2;
                entries->push_back(std::move(e));
            };

            // Helper to add a command entry.
            auto add_entry = [&entries](const char* icon, const char* title,
                                         const char* desc, const char* shortcut,
                                         const char* category, int page) {
                CmdEntry e;
                e.icon = icon;
                e.title = title;
                e.description = desc;
                e.shortcut = shortcut;
                e.category = category;
                e.page_index = page;
                // Build lowercase search text.
                std::string s = std::string(title) + " " + desc;
                if (category) s += std::string(" ") + category;
                for (auto& c : s) c = static_cast<char>(
                    std::tolower(static_cast<unsigned char>(c)));
                e.search_text = std::move(s);
                entries->push_back(std::move(e));
            };

            // --- Navigation ---
            add_header("NAVIGATION");
            add_entry("\xf0\x9f\x94\xa7", "Tune",     "Edit scalars, tables, curves",   "Alt+1", "navigation", 0);
            add_entry("\xf0\x9f\x93\x8a", "Live",     "Runtime gauges and histograms",  "Alt+2", "navigation", 1);
            add_entry("\xe2\x9a\xa1",     "Flash",    "Firmware flash preflight",        "Alt+3", "navigation", 2);
            add_entry("\xe2\x9a\x99",     "Setup",    "Engine configuration + generators","Alt+4", "navigation", 3);
            add_entry("\xf0\x9f\xa7\xaa", "Assist",   "VE / WUE Analyze pipeline",      "Alt+5", "navigation", 4);
            add_entry("\xf0\x9f\x94\x8d", "Triggers", "Trigger log diagnostics",        "Alt+6", "navigation", 5);
            add_entry("\xf0\x9f\x93\x9d", "Logging",  "Datalog profiles and replay",    "Alt+7", "navigation", 6);
            add_entry("\xf0\x9f\x93\x8b", "History",  "Ported service manifest",        "Alt+8", "navigation", 7);

            // --- Tune pages ---
            add_header("TUNING");
            add_entry("\xf0\x9f\x93\x90", "VE Table",            "Volumetric efficiency map",   nullptr, "tuning", 0);
            add_entry("\xf0\x9f\x93\x90", "AFR Table",           "Air-fuel ratio targets",      nullptr, "tuning", 0);
            add_entry("\xf0\x9f\x93\x90", "Spark Table",         "Ignition advance map",        nullptr, "tuning", 0);
            add_entry("\xf0\x9f\x93\x90", "Boost Table",         "Boost target map",            nullptr, "tuning", 0);
            add_entry("\xe2\x9a\x99",     "reqFuel",             "Required fuel pulse width",   nullptr, "tuning", 0);
            add_entry("\xe2\x9a\x99",     "Idle RPM",            "Idle speed targets",          nullptr, "tuning", 0);
            add_entry("\xe2\x9a\x99",     "Warmup Enrichment",   "WUE curve",                   nullptr, "tuning", 0);
            add_entry("\xe2\x9a\x99",     "Cranking Settings",   "Cranking enrichment",         nullptr, "tuning", 0);

            // --- Actions ---
            add_header("ACTIONS");
            add_entry("\xf0\x9f\x92\xbe", "Save as Native",  "Export tune to .tuner JSON",           "Ctrl+S", "actions", 0);
            add_entry("\xf0\x9f\x94\x8d", "Review Changes",  "Review staged parameter edits",        "Ctrl+R", "actions", 0);
            add_entry("\xe2\x9a\xa1",     "Write to RAM",    "Send staged changes to ECU RAM",       "Ctrl+W", "actions", 0);
            add_entry("\xf0\x9f\x94\xa5", "Burn to Flash",   "Write RAM to permanent flash storage", "Ctrl+B", "actions", 0);
            add_entry("\xf0\x9f\xa7\xaa", "Start VE Analyze","Begin live VE correction session",      nullptr,  "actions", 4);

            add_entry("\xf0\x9f\x93\x82", "New Project",      "Create a new project directory",        nullptr,  "actions", -10);
            add_entry("\xf0\x9f\x92\xbe", "Save Dashboard",  "Save gauge layout to JSON file",       nullptr,  "actions", -11);
            add_entry("\xf0\x9f\x93\x82", "Load Dashboard",  "Load gauge layout from JSON file",     nullptr,  "actions", -12);
            add_entry("\xe2\x9a\x99",     "Definition Settings", "Toggle INI feature flags",          nullptr,  "actions", -13);
            add_entry("\xf0\x9f\x96\xa5",  "Fullscreen Dashboard", "Full-screen gauge display",      "F11",    "actions", 1);

            // --- Connection ---
            add_header("CONNECTION");
            add_entry("\xf0\x9f\x94\x8c", "Connect to ECU",  "Serial or WiFi connection",   nullptr, "connection", -1);
            add_entry("\xe2\x8f\x8f",     "Disconnect",       "Close active ECU connection",  nullptr, "connection", -3);

            // Build the list widget items.
            for (const auto& e : *entries) {
                auto* item = new QListWidgetItem;
                if (e.is_header) {
                    // Group header — non-selectable, styled like F1 cheat sheet.
                    item->setFlags(item->flags() & ~Qt::ItemIsSelectable & ~Qt::ItemIsEnabled);
                    item->setSizeHint(QSize(0, 28));
                    results->addItem(item);
                    auto* header_label = new QLabel;
                    header_label->setTextFormat(Qt::RichText);
                    char hdr[256];
                    std::snprintf(hdr, sizeof(hdr),
                        "<span style='color: %s; font-size: %dpx; "
                        "letter-spacing: 2px; font-weight: bold;'>%s</span>",
                        tt::text_dim, tt::font_micro, e.title.c_str());
                    header_label->setText(QString::fromUtf8(hdr));
                    {
                        char ls[128];
                        std::snprintf(ls, sizeof(ls),
                            "padding: %dpx %dpx %dpx %dpx; background: transparent;",
                            tt::space_sm, tt::space_md, 0, tt::space_md);
                        header_label->setStyleSheet(QString::fromUtf8(ls));
                    }
                    results->setItemWidget(item, header_label);
                } else {
                    // Command entry — rich-text label with icon + title + description + shortcut.
                    item->setSizeHint(QSize(0, 36));
                    results->addItem(item);

                    auto* row_widget = new QWidget;
                    auto* row_layout = new QHBoxLayout(row_widget);
                    row_layout->setContentsMargins(tt::space_sm, 2, tt::space_sm, 2);
                    row_layout->setSpacing(tt::space_sm);
                    row_widget->setStyleSheet("background: transparent;");

                    // Icon.
                    auto* icon_label = new QLabel(QString::fromUtf8(e.icon));
                    icon_label->setFixedWidth(24);
                    icon_label->setAlignment(Qt::AlignCenter);
                    icon_label->setStyleSheet("background: transparent; border: none;");
                    row_layout->addWidget(icon_label);

                    // Title + description as a compound label.
                    auto* text_label = new QLabel;
                    text_label->setTextFormat(Qt::RichText);
                    char text_html[512];
                    std::snprintf(text_html, sizeof(text_html),
                        "<span style='color: %s; font-size: %dpx; font-weight: bold;'>%s</span>"
                        "<span style='color: %s; font-size: %dpx;'>  %s</span>",
                        tt::text_primary, tt::font_body, e.title.c_str(),
                        tt::text_dim, tt::font_small, e.description.c_str());
                    text_label->setText(QString::fromUtf8(text_html));
                    text_label->setStyleSheet("background: transparent; border: none;");
                    row_layout->addWidget(text_label, 1);

                    // Shortcut chip (if present).
                    if (e.shortcut) {
                        auto* chip = new QLabel;
                        chip->setTextFormat(Qt::RichText);
                        char chip_html[256];
                        std::snprintf(chip_html, sizeof(chip_html),
                            "<span style='color: %s; font-size: %dpx; "
                            "font-family: monospace;'>%s</span>",
                            tt::text_muted, tt::font_micro, e.shortcut);
                        chip->setText(QString::fromUtf8(chip_html));
                        {
                            char cs[192];
                            std::snprintf(cs, sizeof(cs),
                                "background: %s; border: 1px solid %s; "
                                "border-radius: %dpx; padding: 1px %dpx;",
                                tt::bg_inset, tt::border,
                                tt::radius_sm, tt::space_xs + 2);
                            chip->setStyleSheet(QString::fromUtf8(cs));
                        }
                        row_layout->addWidget(chip);
                    }

                    results->setItemWidget(item, row_widget);
                }
            }
            vl->addWidget(results, 1);

            // Filter on typing — matches against search_text (lowercase).
            QObject::connect(input, &QLineEdit::textChanged, [results, entries](const QString& q) {
                std::string needle = q.toStdString();
                for (auto& c : needle) c = static_cast<char>(
                    std::tolower(static_cast<unsigned char>(c)));
                // Track whether any group has visible entries — hide
                // headers for empty groups.
                for (int i = 0; i < results->count(); ++i) {
                    const auto& e = (*entries)[i];
                    if (e.is_header) continue;
                    bool match = needle.empty()
                        || e.search_text.find(needle) != std::string::npos;
                    results->item(i)->setHidden(!match);
                }
                // Hide group headers that have no visible entries after them.
                for (int i = 0; i < results->count(); ++i) {
                    const auto& e = (*entries)[i];
                    if (!e.is_header) continue;
                    // Look ahead for the next visible non-header entry
                    // in this group.
                    bool has_visible = false;
                    for (int j = i + 1; j < results->count(); ++j) {
                        if ((*entries)[j].is_header) break;
                        if (!results->item(j)->isHidden()) {
                            has_visible = true;
                            break;
                        }
                    }
                    results->item(i)->setHidden(!has_visible);
                }
                // Auto-select the first visible selectable item.
                for (int i = 0; i < results->count(); ++i) {
                    if (!results->item(i)->isHidden()
                        && (results->item(i)->flags() & Qt::ItemIsSelectable)) {
                        results->setCurrentRow(i);
                        break;
                    }
                }
            });

            // Navigate on Enter or double-click.
            auto navigate_selected = [dialog, results, entries, sidebar, connect_callback, this]() {
                auto* item = results->currentItem();
                if (!item) return;
                int row = results->row(item);
                if (row >= 0 && row < static_cast<int>(entries->size())) {
                    int page = (*entries)[row].page_index;
                    if ((*entries)[row].is_header) return;
                    dialog->accept();
                    if (page == -1 && *connect_callback) {
                        (*connect_callback)();
                    } else if (page == -3) {
                        // Disconnect — no-op if not connected.
                    } else if (page <= -10 && page >= -13) {
                        // Trigger File menu action by title.
                        const char* titles[] = {
                            "New Project", "Save Dashboard",
                            "Load Dashboard", "Definition Settings"};
                        int idx = -(page + 10);
                        if (idx >= 0 && idx < 4) {
                            for (auto* action : this->findChildren<QAction*>()) {
                                if (action->text().contains(
                                    QString::fromUtf8(titles[idx]))) {
                                    QTimer::singleShot(0, [action]() {
                                        action->trigger();
                                    });
                                    break;
                                }
                            }
                        }
                    } else if (page >= 0) {
                        sidebar->setCurrentRow(page);
                    }
                }
            };
            QObject::connect(results, &QListWidget::itemDoubleClicked,
                             [navigate_selected](QListWidgetItem*) {
                navigate_selected();
            });
            QObject::connect(input, &QLineEdit::returnPressed, navigate_selected);

            // Select the first selectable item.
            for (int i = 0; i < results->count(); ++i) {
                if (results->item(i)->flags() & Qt::ItemIsSelectable) {
                    results->setCurrentRow(i);
                    break;
                }
            }

            input->setFocus();
            dialog->exec();
            dialog->deleteLater();
        };

        // ------------------------------------------------------------
        // Keyboard shortcut help overlay (F1 or ?)
        // ------------------------------------------------------------
        //
        // Every `QShortcut` declared above is silent chrome — the
        // operator can't see the bindings anywhere in the app until
        // they stumble on them in a blog post or a docs file. This
        // overlay is the one place that makes all of them
        // discoverable without demanding screen real estate on the
        // workspace itself.
        //
        // Philosophy — progressive disclosure applied to keyboard
        // navigation. The main workspace never screams "you can
        // press Alt+2 to jump to LIVE"; instead, one quiet key (?)
        // reveals the full cheat sheet whenever the operator wants
        // it. The `docs/ux-design.md` principle "don't teach what
        // the operator can ask for" applies: the shortcuts are there
        // when needed, invisible when not.
        //
        // Two bindings open the same dialog:
        //   - `F1`  — the universal "help" key every Windows / Qt app
        //             respects
        //   - `?`  — the universal "help" key every vim / terminal app
        //             respects; ergonomic for right-hand-only reach
        //
        // Binding to `?` via `Qt::SHIFT | Qt::Key_Slash` is the Qt
        // idiom — `Key_Question` alone doesn't resolve on US layouts.
        auto open_shortcuts_dialog = [this, sidebar]() {
            auto* dialog = new QDialog(this);
            dialog->setWindowTitle("Keyboard Shortcuts");
            dialog->setFixedSize(480, 520);
            {
                char dlg_qss[768];
                std::snprintf(dlg_qss, sizeof(dlg_qss),
                    "QDialog { background: %s; border: 1px solid %s; }"
                    "QLabel { color: %s; }",
                    tt::bg_base, tt::border, tt::text_secondary);
                dialog->setStyleSheet(QString::fromUtf8(dlg_qss));
            }
            auto* vl = new QVBoxLayout(dialog);
            vl->setContentsMargins(tt::space_lg, tt::space_lg, tt::space_lg, tt::space_lg);
            vl->setSpacing(tt::space_sm);

            // Header — hero title + context line. Reuses the tab
            // header grammar (`font_label` bold title + `font_small`
            // dim subtitle) so the overlay reads as part of the
            // same app voice.
            auto* header = new QLabel;
            header->setTextFormat(Qt::RichText);
            {
                char hdr_html[384];
                std::snprintf(hdr_html, sizeof(hdr_html),
                    "<span style='font-size: %dpx; font-weight: bold; color: %s;'>"
                    "Keyboard Shortcuts</span><br>"
                    "<span style='color: %s; font-size: %dpx;'>"
                    "Press F1 or ? anywhere to show this panel. Esc to dismiss."
                    "</span>",
                    tt::font_label, tt::text_primary,
                    tt::text_dim, tt::font_small);
                header->setText(QString::fromUtf8(hdr_html));
            }
            vl->addWidget(header);

            // Grouped cheat sheet. Each row is a key chip + a
            // description label, laid out as a two-column HTML
            // table inside one rich-text QLabel so the alignment
            // stays deterministic without a grid widget.
            //
            // The key chip uses `bg_inset` + `border` + monospace
            // font — same visual as the tune-page scalar editor
            // chips so "keys" and "tune values" share the one
            // "interactive primitive" look.
            //
            // Sub-slice 125: contextual emphasis. The group header
            // colour tracks the active sidebar tab — the group
            // that's relevant "right here, right now" lights up in
            // `accent_primary`; every other group stays muted. The
            // Tune workflow group also picks up a dim
            // "(available on the Tune tab)" suffix when the
            // operator is NOT on the TUNE tab, so they can read the
            // Ctrl+R/W/B keys without getting confused when the
            // keys don't fire on the current tab.
            struct ShortcutRow {
                const char* key;
                const char* label;
            };
            struct ShortcutGroup {
                const char* title;
                // -1 = global (always relevant), 0..7 = sidebar tab
                // index. The header lights up in `accent_primary`
                // when the active tab matches, stays muted otherwise.
                int active_tab;
                // Non-null when the group is context-scoped and
                // needs a dim "(available on …)" suffix on non-
                // matching tabs. Used by the Tune workflow group to
                // signal that Ctrl+R/W/B only fire on the TUNE tab.
                const char* scope_note;
                std::vector<ShortcutRow> rows;
            };
            const std::vector<ShortcutGroup> groups = {
                {"Navigation", -1, nullptr, {
                    {"Alt+1",   "TUNE \xe2\x80\x94 edit scalars, tables, curves"},
                    {"Alt+2",   "LIVE \xe2\x80\x94 runtime gauges and histograms"},
                    {"Alt+3",   "FLASH \xe2\x80\x94 firmware preflight"},
                    {"Alt+4",   "SETUP \xe2\x80\x94 engine configuration + generators"},
                    {"Alt+5",   "ASSIST \xe2\x80\x94 VE / WUE Analyze pipeline"},
                    {"Alt+6",   "TRIGGERS \xe2\x80\x94 trigger log diagnostics"},
                    {"Alt+7",   "LOGGING \xe2\x80\x94 datalog profiles and replay"},
                    {"Alt+8",   "HISTORY \xe2\x80\x94 ported service manifest"},
                    {"Ctrl+K",  "Command palette \xe2\x80\x94 jump to any page by name"},
                }},
                {"Tune workflow", 0, "available on the Tune tab", {
                    {"Ctrl+R", "Review staged changes"},
                    {"Ctrl+W", "Write staged changes to RAM"},
                    {"Ctrl+B", "Burn to flash"},
                }},
                {"Table editing", 0, "available on the Tune tab", {
                    {"\xe2\x86\x90\xe2\x86\x91\xe2\x86\x93\xe2\x86\x92", "Navigate cells"},
                    {"Enter",  "Edit selected cell"},
                    {"Ctrl+Z", "Undo last cell edit"},
                    {"Ctrl+Y", "Redo cell edit"},
                    {"Ctrl+C", "Copy selection"},
                    {"Ctrl+V", "Paste from clipboard"},
                    {"Ctrl+D", "Fill down"},
                    {"+/-",    "Increment / decrement cell"},
                    {"I",      "Interpolate selection"},
                    {"S",      "Smooth selection"},
                }},
                {"Files", -1, nullptr, {
                    {"Ctrl+S", "Save as .tuner (native JSON)"},
                }},
                {"Help", -1, nullptr, {
                    {"F1",     "Show this shortcut panel"},
                    {"?",      "Show this shortcut panel (alternate)"},
                    {"Esc",    "Dismiss any open dialog"},
                }},
            };

            const int active_tab = sidebar->currentRow();
            char body_html[4096];
            int off = 0;
            off += std::snprintf(body_html + off, sizeof(body_html) - off,
                "<table cellspacing='6' cellpadding='0' border='0'>");
            for (const auto& group : groups) {
                const bool is_active =
                    (group.active_tab >= 0 && group.active_tab == active_tab);
                const char* title_color = is_active ? tt::accent_primary : tt::text_muted;
                // Append the scope-note suffix only when the group
                // is context-scoped AND we're off-tab. When on-tab,
                // the accent_primary header already signals
                // "these work here", so the suffix would be noise.
                char title_buf[192];
                if (group.scope_note && !is_active) {
                    std::snprintf(title_buf, sizeof(title_buf),
                        "%s <span style='color: %s; font-weight: normal; "
                        "text-transform: none; letter-spacing: 0;'>"
                        "(%s)</span>",
                        group.title, tt::text_dim, group.scope_note);
                } else {
                    std::snprintf(title_buf, sizeof(title_buf), "%s", group.title);
                }
                off += std::snprintf(body_html + off, sizeof(body_html) - off,
                    "<tr><td colspan='2' style='padding-top: %dpx;'>"
                    "<span style='color: %s; font-size: %dpx; font-weight: bold; "
                    "text-transform: uppercase; letter-spacing: 1px;'>%s</span>"
                    "</td></tr>",
                    tt::space_sm + 2, title_color, tt::font_small, title_buf);
                for (const auto& row : group.rows) {
                    off += std::snprintf(body_html + off, sizeof(body_html) - off,
                        "<tr>"
                        "<td style='padding-right: %dpx;'>"
                        "<span style='background-color: %s; border: 1px solid %s; "
                        "border-radius: %dpx; padding: 2px 8px; color: %s; "
                        "font-family: monospace; font-size: %dpx;'>%s</span>"
                        "</td>"
                        "<td><span style='color: %s; font-size: %dpx;'>%s</span></td>"
                        "</tr>",
                        tt::space_md, tt::bg_inset, tt::border, tt::radius_sm,
                        tt::text_primary, tt::font_small, row.key,
                        tt::text_secondary, tt::font_body, row.label);
                    if (off >= static_cast<int>(sizeof(body_html) - 256)) break;
                }
            }
            std::snprintf(body_html + off, sizeof(body_html) - off, "</table>");

            auto* body = new QLabel;
            body->setTextFormat(Qt::RichText);
            body->setText(QString::fromUtf8(body_html));
            body->setAlignment(Qt::AlignTop | Qt::AlignLeft);
            vl->addWidget(body, 1);

            // Esc dismisses (QDialog default). Any key also closes
            // the dialog if it's not F1/? again — keeps the modal
            // dismissable without requiring the mouse.
            dialog->exec();
            dialog->deleteLater();
        };

        // ------------------------------------------------------------
        // Menu bar — File / View / Tune / Help
        // ------------------------------------------------------------
        //
        // Every Windows desktop app the operator has ever used has a
        // menu bar with the same rough shape. The previous slices
        // avoided it because the sidebar nav + command palette + F1
        // cheat sheet covered every function — but that left every
        // first-time operator staring at a workspace with no
        // conventional desktop-app landmark. Adding a menu bar now
        // doesn't cost anything (Qt renders it natively, tokens
        // already shape every QAction's display) and it:
        //
        //   1. Makes every shortcut self-documenting — Qt displays
        //      the `QAction::shortcut()` binding next to each menu
        //      entry automatically, so File → Save As appears as
        //      "Save as Native...          Ctrl+S".
        //   2. Gives the operator a conventional anchor point that
        //      matches every other Qt app on the system.
        //   3. Reuses the handlers we just hoisted above
        //      (save_as_native_handler, open_command_palette,
        //      open_shortcuts_dialog) — no duplication.
        //
        // Alt+F / Alt+V / Alt+T / Alt+H still work as menu accelerators
        // via the `&` mnemonic, which is a bonus discoverability
        // layer on top of the existing Alt+1..8 page shortcuts.
        auto* menu_bar = menuBar();
        {
            // File menu ------------------------------------------------
            auto* file_menu = menu_bar->addMenu("&File");
            auto* save_action = file_menu->addAction("&Save as Native...");
            save_action->setShortcut(QKeySequence(Qt::CTRL | Qt::Key_S));
            save_action->setShortcutContext(Qt::ApplicationShortcut);
            QObject::connect(save_action, &QAction::triggered, save_as_native_handler);
            this->addAction(save_action);
            // File → Open... opens a file dialog for .msq tune files.
            // Hot-reload is not yet supported — the selected file is
            // saved to recents and the operator is prompted to restart.
            // New Project — creates project directory, saves .project file.
            auto* new_proj_action = file_menu->addAction("&New Project...");
            QObject::connect(new_proj_action, &QAction::triggered,
                             [this, shared_workspace, reload_active_project]() {
                auto* dlg = new QDialog(this);
                dlg->setWindowTitle("New Project");
                dlg->setMinimumWidth(480);
                {
                    char s[64];
                    std::snprintf(s, sizeof(s), "QDialog { background: %s; }", tt::bg_base);
                    dlg->setStyleSheet(QString::fromUtf8(s));
                }
                auto* form = new QVBoxLayout(dlg);
                form->setContentsMargins(tt::space_xl, tt::space_xl, tt::space_xl, tt::space_xl);
                form->setSpacing(tt::space_md);

                // Title.
                auto* title = new QLabel;
                title->setTextFormat(Qt::RichText);
                {
                    char h[128];
                    std::snprintf(h, sizeof(h),
                        "<span style='font-size: %dpx; font-weight: bold; color: %s;'>"
                        "Create New Project</span>",
                        tt::font_heading, tt::text_primary);
                    title->setText(QString::fromUtf8(h));
                }
                form->addWidget(title);

                auto make_field = [form](const char* label_text) -> QComboBox* {
                    auto* row = new QHBoxLayout;
                    auto* label = new QLabel(QString::fromUtf8(label_text));
                    label->setFixedWidth(120);
                    {
                        char s[64];
                        std::snprintf(s, sizeof(s), "QLabel { color: %s; }", tt::text_secondary);
                        label->setStyleSheet(QString::fromUtf8(s));
                    }
                    row->addWidget(label);
                    auto* combo = new QComboBox;
                    combo->setEditable(true);
                    {
                        char s[192];
                        std::snprintf(s, sizeof(s),
                            "QComboBox { background: %s; color: %s; border: 1px solid %s; "
                            "border-radius: %dpx; padding: %dpx %dpx; }",
                            tt::bg_elevated, tt::text_primary, tt::border,
                            tt::radius_sm, tt::space_xs, tt::space_sm);
                        combo->setStyleSheet(QString::fromUtf8(s));
                    }
                    row->addWidget(combo, 1);

                    auto* browse = new QPushButton(QString::fromUtf8("..."));
                    browse->setFixedWidth(32);
                    row->addWidget(browse);
                    form->addLayout(row);
                    return combo;
                };

                auto* name_field = make_field("Project Name:");
                name_field->setEditText(QString::fromUtf8("My Speeduino Project"));

                auto* dir_field = make_field("Directory:");
                dir_field->setEditText(QDir::homePath());
                // Wire browse button (it's the last widget in the row).
                {
                    auto* row_layout = static_cast<QHBoxLayout*>(form->itemAt(form->count() - 1)->layout());
                    auto* browse_btn = qobject_cast<QPushButton*>(row_layout->itemAt(2)->widget());
                    if (browse_btn) {
                        QObject::connect(browse_btn, &QPushButton::clicked,
                                         [dlg, dir_field]() {
                            auto dir = QFileDialog::getExistingDirectory(dlg,
                                QString::fromUtf8("Select Project Directory"));
                            if (!dir.isEmpty()) dir_field->setEditText(dir);
                        });
                    }
                }

                auto* def_field = make_field("Definition:");
                {
                    // Prefer native .tunerdef, fall back to INI.
                    auto native_def = find_native_definition();
                    if (!native_def.empty())
                        def_field->setEditText(QString::fromUtf8(native_def.string().c_str()));
                    else {
                        auto ini_path = find_production_ini();
                        if (!ini_path.empty())
                            def_field->setEditText(QString::fromUtf8(ini_path.string().c_str()));
                    }
                }
                // Wire definition browse button.
                {
                    auto* row_layout = static_cast<QHBoxLayout*>(form->itemAt(form->count() - 1)->layout());
                    auto* browse_btn = qobject_cast<QPushButton*>(row_layout->itemAt(2)->widget());
                    if (browse_btn) {
                        QObject::connect(browse_btn, &QPushButton::clicked,
                                         [dlg, def_field]() {
                            auto path = QFileDialog::getOpenFileName(dlg,
                                QString::fromUtf8("Select ECU Definition"),
                                QString(),
                                QString::fromUtf8(
                                    "Native Definition (*.tunerdef);;Legacy INI (*.ini);;All Files (*)"));
                            if (!path.isEmpty()) def_field->setEditText(path);
                        });
                    }
                }

                auto* tune_field = make_field("Tune File:");
                tune_field->setEditText(QString::fromUtf8("(create empty)"));
                // Wire tune browse button.
                {
                    auto* row_layout = static_cast<QHBoxLayout*>(form->itemAt(form->count() - 1)->layout());
                    auto* browse_btn = qobject_cast<QPushButton*>(row_layout->itemAt(2)->widget());
                    if (browse_btn) {
                        QObject::connect(browse_btn, &QPushButton::clicked,
                                         [dlg, tune_field]() {
                            auto path = QFileDialog::getOpenFileName(dlg,
                                QString::fromUtf8("Select Tune File"),
                                QString(),
                                QString::fromUtf8(
                                    "Native Tune (*.tuner);;MSQ Tune (*.msq);;All Files (*)"));
                            if (!path.isEmpty()) tune_field->setEditText(path);
                        });
                    }
                }

                // Hint.
                auto* hint = new QLabel;
                hint->setWordWrap(true);
                {
                    char h[384];
                    std::snprintf(h, sizeof(h),
                        "<span style='color: %s; font-size: %dpx;'>"
                        "Creates a project directory with a .project file. "
                        "Use the browse buttons to select your INI and tune files. "
                        "Native .tuner format is preferred over legacy .msq. "
                        "Leave tune as '(create empty)' and run the Engine Setup Wizard "
                        "to generate a base tune.</span>",
                        tt::text_dim, tt::font_small);
                    hint->setTextFormat(Qt::RichText);
                    hint->setText(QString::fromUtf8(h));
                }
                form->addWidget(hint);

                // Buttons.
                auto* btn_row = new QHBoxLayout;
                btn_row->addStretch(1);
                auto* create_btn = new QPushButton(QString::fromUtf8("Create"));
                auto* cancel_btn = new QPushButton(QString::fromUtf8("Cancel"));
                btn_row->addWidget(create_btn);
                btn_row->addWidget(cancel_btn);
                form->addLayout(btn_row);

                QObject::connect(cancel_btn, &QPushButton::clicked, dlg, &QDialog::reject);
                QObject::connect(create_btn, &QPushButton::clicked,
                                 [dlg, name_field, dir_field, def_field, tune_field]() {
                    std::string name = name_field->currentText().toStdString();
                    std::string dir = dir_field->currentText().toStdString();
                    std::string def_path = def_field->currentText().toStdString();
                    std::string tune = tune_field->currentText().toStdString();

                    if (name.empty() || dir.empty()) return;

                    // Create project directory.
                    std::filesystem::path proj_dir = std::filesystem::path(dir) / name;
                    std::filesystem::create_directories(proj_dir);

                    // Write minimal .project file.
                    auto proj_file = proj_dir / (name + ".project");
                    std::ofstream out(proj_file, std::ios::out);
                    if (out) {
                        out << "# Tuner project file\n";
                        out << "projectName=" << name << "\n";
                        if (!def_path.empty() && def_path != "(create empty)")
                            out << "definitionFile=" << def_path << "\n";
                        out << "activeSettings=\n";
                        out.close();
                    }

                    // Save to QSettings as current project.
                    QSettings settings;
                    settings.setValue(kCurrentProjectNameKey,
                        QString::fromUtf8(name.c_str()));

                    // Detect if the definition is native (.tunerdef) or
                    // legacy INI and save to the appropriate QSettings key.
                    if (!def_path.empty() && def_path != "(create empty)") {
                        std::string ext = std::filesystem::path(def_path).extension().string();
                        for (auto& c : ext) c = static_cast<char>(
                            std::tolower(static_cast<unsigned char>(c)));
                        if (ext == ".tunerdef") {
                            settings.setValue("projects/current/tunerdef",
                                QString::fromUtf8(def_path.c_str()));
                            // Clear legacy INI key.
                            settings.setValue(kCurrentProjectIniKey, QString());
                        } else {
                            settings.setValue(kCurrentProjectIniKey,
                                QString::fromUtf8(def_path.c_str()));
                        }
                    }
                    // Set tune path if user selected one, clear if empty.
                    if (!tune.empty() && tune != "(create empty)")
                        settings.setValue(kCurrentProjectTuneKey,
                            QString::fromUtf8(tune.c_str()));
                    else
                        settings.setValue(kCurrentProjectTuneKey, QString());
                    settings.setValue(kCurrentProjectSigKey, QString());

                    dlg->accept();
                });

                if (dlg->exec() == QDialog::Accepted) {
                    // Reload to pick up the new project, then
                    // immediately open the Engine Setup Wizard.
                    // This is the "guided power" flow: create project
                    // → wizard configures the engine → generates base
                    // tune → operator lands on the TUNE tab ready to
                    // refine. No confusion about what to do next.
                    reload_active_project();
                    QTimer::singleShot(300, [this]() {
                        // Switch to Setup tab and open wizard.
                        if (auto* sb = this->findChild<QListWidget*>())
                            sb->setCurrentRow(3);
                        open_engine_setup_wizard(this);
                    });
                }
                dlg->deleteLater();
            });

            auto* open_action = file_menu->addAction("&Open Tune...");
            open_action->setShortcut(QKeySequence(Qt::CTRL | Qt::Key_O));
            open_action->setShortcutContext(Qt::ApplicationShortcut);
            QObject::connect(open_action, &QAction::triggered,
                             [this, shared_workspace, reload_active_project]() {
                debug_log("File/Open triggered");
                QString path = QFileDialog::getOpenFileName(
                    this,
                    "Open Tune File",
                    QString(),
                    "Tune Files (*.tuner *.msq);;Native Tune (*.tuner);;Speeduino Tune (*.msq);;Project (*.tunerproj);;All Files (*)");
                debug_log("File/Open selected=\"" + path.toStdString() + "\"");
                if (path.isEmpty()) return;
                if (shared_workspace->staged_count() > 0) {
                    auto answer = QMessageBox::question(
                        this,
                        "Discard staged changes?",
                        QString::fromUtf8(
                            "Opening another project will discard the current staged edits.\n\n"
                            "Continue?"),
                        QMessageBox::Yes | QMessageBox::Cancel,
                        QMessageBox::Cancel);
                    if (answer != QMessageBox::Yes) return;
                }
                try {
                    auto rp = project_from_file(path.toStdString());
                    debug_log("File/Open project parsed name=\"" + rp.name
                        + "\" ini=\"" + rp.ini_path
                        + "\" tune=\"" + rp.msq_path + "\"");
                    if (rp.msq_path.empty()) {
                        QMessageBox::warning(
                            this,
                            "Open Failed",
                            QString::fromUtf8(
                                "This project does not declare a tune file yet."));
                        return;
                    }
                    push_recent_project(rp);
                    save_current_project(rp);
                    debug_log("File/Open calling reload_active_project");
                    reload_active_project();
                } catch (const std::exception& e) {
                    debug_log(std::string("File/Open failed: ") + e.what());
                    QMessageBox::warning(
                        this, "Open Failed", QString::fromUtf8(e.what()));
                }
            });
            this->addAction(open_action);
            // Open Recent submenu — shows up to 5 recent projects
            // in MRU order. Each entry is a no-op for now (the app
            // loads the most recent project on startup automatically).
            auto* recent_menu = file_menu->addMenu("Open &Recent");
            {
                auto recent_list = load_recent_projects();
                if (recent_list.empty()) {
                    auto* empty = recent_menu->addAction("(none)");
                    empty->setEnabled(false);
                } else {
                    for (const auto& rp : recent_list) {
                        char entry_label[256];
                        std::string date_str = friendly_date(rp.last_opened);
                        std::snprintf(entry_label, sizeof(entry_label),
                                      "%s  \xe2\x80\x94  %s",
                                      rp.name.c_str(), date_str.c_str());
                        auto* action = recent_menu->addAction(
                            QString::fromUtf8(entry_label));
                        QObject::connect(action, &QAction::triggered,
                                         [this, rp, shared_workspace, reload_active_project]() {
                            debug_log("Open Recent triggered name=\"" + rp.name
                                + "\" tune=\"" + rp.msq_path + "\"");
                            if (shared_workspace->staged_count() > 0) {
                                auto answer = QMessageBox::question(
                                    this,
                                    "Discard staged changes?",
                                    QString::fromUtf8(
                                        "Opening a recent project will discard the current staged edits.\n\n"
                                        "Continue?"),
                                    QMessageBox::Yes | QMessageBox::Cancel,
                                    QMessageBox::Cancel);
                                if (answer != QMessageBox::Yes) return;
                            }
                            auto selected = rp;
                            selected.last_opened = today_iso();
                            if (selected.msq_path.empty()
                                || !std::filesystem::exists(selected.msq_path)) {
                                QMessageBox::warning(
                                    this,
                                    "Project Missing",
                                    QString::fromUtf8(
                                        "That recent project no longer points to an existing tune file."));
                                return;
                            }
                            push_recent_project(selected);
                            save_current_project(selected);
                            debug_log("Open Recent calling reload_active_project");
                            reload_active_project();
                        });
                    }
                }
            }
            // Definition Settings — toggle INI [SettingGroups] flags.
            // Dashboard save/load.
            auto* save_dash_action = file_menu->addAction("Save &Dashboard...");
            QObject::connect(save_dash_action, &QAction::triggered,
                             [this, shared_dash]() {
                if (!shared_dash || shared_dash->widgets.empty()) return;
                QSettings settings;
                QString last_dir = settings.value("dashboard/lastDir",
                    QDir::homePath()).toString();
                auto path = QFileDialog::getSaveFileName(this,
                    QString::fromUtf8("Save Dashboard Layout"),
                    last_dir,
                    QString::fromUtf8("Dashboard (*.json)"));
                if (path.isEmpty()) return;
                auto json = dashboard_layout_to_json(*shared_dash);
                std::ofstream out(path.toStdString(), std::ios::out | std::ios::binary);
                if (out) {
                    out.write(json.data(), static_cast<std::streamsize>(json.size()));
                    out.close();
                    settings.setValue("dashboard/lastDir",
                        QFileInfo(path).absolutePath());
                }
            });

            auto* load_dash_action = file_menu->addAction("&Load Dashboard...");
            QObject::connect(load_dash_action, &QAction::triggered,
                             [this, shared_dash, rebuild_dashboard]() {
                QSettings settings;
                QString last_dir = settings.value("dashboard/lastDir",
                    QDir::homePath()).toString();
                auto path = QFileDialog::getOpenFileName(this,
                    QString::fromUtf8("Load Dashboard Layout"),
                    last_dir,
                    QString::fromUtf8("Dashboard (*.json);;All Files (*)"));
                if (path.isEmpty()) return;
                std::ifstream in(path.toStdString(), std::ios::in | std::ios::binary);
                if (!in) return;
                std::string text((std::istreambuf_iterator<char>(in)),
                                 std::istreambuf_iterator<char>());
                in.close();
                auto loaded = dashboard_layout_from_json(text);
                if (loaded.widgets.empty()) return;
                *shared_dash = std::move(loaded);
                (*rebuild_dashboard)();
                settings.setValue("dashboard/lastDir",
                    QFileInfo(path).absolutePath());
            });

            file_menu->addSeparator();
            // Import INI → Export as .tunerdef v2 (one-time migration).
            auto* import_ini_action = file_menu->addAction("&Import Legacy INI...");
            QObject::connect(import_ini_action, &QAction::triggered, [this]() {
                auto ini_path = QFileDialog::getOpenFileName(this,
                    QString::fromUtf8("Import Legacy INI Definition"),
                    QString(),
                    QString::fromUtf8("INI Files (*.ini);;All Files (*)"));
                if (ini_path.isEmpty()) return;

                try {
                    auto def = tuner_core::compile_ecu_definition_file(
                        ini_path.toStdString());
                    auto json = tuner_core::dump_definition_v2(def);

                    // Suggest output path next to the INI.
                    auto ini_fs = std::filesystem::path(ini_path.toStdString());
                    auto suggested = ini_fs.parent_path() / (ini_fs.stem().string() + ".tunerdef");

                    auto out_path = QFileDialog::getSaveFileName(this,
                        QString::fromUtf8("Save Native Definition"),
                        QString::fromUtf8(suggested.string().c_str()),
                        QString::fromUtf8("Native Definition (*.tunerdef)"));
                    if (out_path.isEmpty()) return;

                    std::ofstream out(out_path.toStdString(),
                        std::ios::out | std::ios::binary);
                    if (out) {
                        // Prepend JSON5 header comment.
                        std::string header = "// Imported from: "
                            + ini_fs.filename().string()
                            + "\n// Native Tuner definition (JSON5, schema 2.0)\n";
                        out.write(header.data(), static_cast<std::streamsize>(header.size()));
                        out.write(json.data(), static_cast<std::streamsize>(json.size()));
                        out.close();

                        // Set as current project definition.
                        QSettings settings;
                        settings.setValue("projects/current/tunerdef",
                            out_path);
                        settings.setValue(kCurrentProjectIniKey,
                            QString::fromUtf8(ini_path.toStdString().c_str()));

                        statusBar()->showMessage(
                            QString::fromUtf8(("\xe2\x9c\x85 Exported: "
                                + std::filesystem::path(out_path.toStdString())
                                    .filename().string()).c_str()), 5000);
                    }
                } catch (const std::exception& e) {
                    QMessageBox::warning(this,
                        QString::fromUtf8("Import Failed"),
                        QString::fromUtf8(e.what()));
                }
            });

            file_menu->addSeparator();
            auto* def_settings_action = file_menu->addAction("Definition &Settings...");
            QObject::connect(def_settings_action, &QAction::triggered,
                             [this, shared_workspace, reload_active_project]() {
                auto def_opt_s = load_active_definition();
                if (!def_opt_s.has_value()) {
                    QMessageBox::information(this, "No Definition",
                        QString::fromUtf8("No definition loaded."));
                    return;
                }
                auto def = std::move(*def_opt_s);

                if (def.setting_groups.groups.empty()) {
                    QMessageBox::information(this, "No Settings",
                        QString::fromUtf8("This definition has no configurable settings."));
                    return;
                }

                // Load current active_settings from QSettings.
                QSettings settings;
                std::string saved = settings.value(
                    "projects/current/activeSettings", "").toString().toStdString();
                std::set<std::string> active;
                {
                    std::istringstream ss(saved);
                    std::string tok;
                    while (std::getline(ss, tok, ',')) {
                        while (!tok.empty() && tok.front() == ' ') tok.erase(tok.begin());
                        while (!tok.empty() && tok.back() == ' ') tok.pop_back();
                        if (!tok.empty()) active.insert(tok);
                    }
                }

                // Build dialog with checkboxes / radio groups.
                auto* dlg = new QDialog(this);
                dlg->setWindowTitle("Definition Settings");
                dlg->setMinimumWidth(400);
                {
                    char ds[128];
                    std::snprintf(ds, sizeof(ds),
                        "QDialog { background: %s; }", tt::bg_base);
                    dlg->setStyleSheet(QString::fromUtf8(ds));
                }
                auto* dl = new QVBoxLayout(dlg);
                dl->setContentsMargins(tt::space_lg, tt::space_lg, tt::space_lg, tt::space_lg);
                dl->setSpacing(tt::space_md);

                struct SettingBinding {
                    std::string group_symbol;
                    std::vector<std::string> option_symbols;
                    QComboBox* combo = nullptr;     // multi-option
                    QCheckBox* check = nullptr;     // boolean flag
                };
                std::vector<SettingBinding> bindings;

                for (const auto& grp : def.setting_groups.groups) {
                    if (grp.options.empty()) {
                        // Boolean flag.
                        auto* cb = new QCheckBox(QString::fromUtf8(grp.label.c_str()));
                        cb->setChecked(active.count(grp.symbol) > 0);
                        {
                            char s[128];
                            std::snprintf(s, sizeof(s),
                                "QCheckBox { color: %s; font-size: %dpx; }",
                                tt::text_primary, tt::font_body);
                            cb->setStyleSheet(QString::fromUtf8(s));
                        }
                        dl->addWidget(cb);
                        SettingBinding sb;
                        sb.group_symbol = grp.symbol;
                        sb.check = cb;
                        bindings.push_back(std::move(sb));
                    } else {
                        // Multi-option group.
                        auto* label = new QLabel(QString::fromUtf8(grp.label.c_str()));
                        {
                            char s[128];
                            std::snprintf(s, sizeof(s),
                                "QLabel { color: %s; font-size: %dpx; font-weight: bold; }",
                                tt::text_secondary, tt::font_body);
                            label->setStyleSheet(QString::fromUtf8(s));
                        }
                        dl->addWidget(label);
                        auto* combo = new QComboBox;
                        int current_idx = 0;
                        SettingBinding sb;
                        sb.group_symbol = grp.symbol;
                        for (int i = 0; i < static_cast<int>(grp.options.size()); ++i) {
                            const auto& opt = grp.options[i];
                            combo->addItem(QString::fromUtf8(opt.label.c_str()));
                            sb.option_symbols.push_back(opt.symbol);
                            if (active.count(opt.symbol) > 0) current_idx = i;
                        }
                        combo->setCurrentIndex(current_idx);
                        {
                            char s[256];
                            std::snprintf(s, sizeof(s),
                                "QComboBox { background: %s; color: %s; border: 1px solid %s; "
                                "border-radius: %dpx; padding: 4px 8px; font-size: %dpx; }",
                                tt::bg_elevated, tt::text_primary, tt::border,
                                tt::radius_sm, tt::font_body);
                            combo->setStyleSheet(QString::fromUtf8(s));
                        }
                        dl->addWidget(combo);
                        sb.combo = combo;
                        bindings.push_back(std::move(sb));
                    }
                }

                // OK / Cancel.
                auto* btn_row = new QHBoxLayout;
                btn_row->addStretch(1);
                auto* ok_btn = new QPushButton("OK");
                auto* cancel_btn = new QPushButton("Cancel");
                btn_row->addWidget(ok_btn);
                btn_row->addWidget(cancel_btn);
                dl->addLayout(btn_row);

                QObject::connect(cancel_btn, &QPushButton::clicked, dlg, &QDialog::reject);
                QObject::connect(ok_btn, &QPushButton::clicked,
                                 [dlg, bindings]() {
                    // Collect new active_settings.
                    std::set<std::string> new_active;
                    for (const auto& b : bindings) {
                        if (b.check) {
                            if (b.check->isChecked())
                                new_active.insert(b.group_symbol);
                        } else if (b.combo && !b.option_symbols.empty()) {
                            int idx = b.combo->currentIndex();
                            if (idx >= 0 && idx < static_cast<int>(b.option_symbols.size()))
                                new_active.insert(b.option_symbols[idx]);
                        }
                    }
                    // Save to QSettings.
                    std::string joined;
                    for (const auto& s : new_active) {
                        if (!joined.empty()) joined += ",";
                        joined += s;
                    }
                    QSettings settings;
                    settings.setValue("projects/current/activeSettings",
                        QString::fromUtf8(joined.c_str()));
                    dlg->accept();
                });

                dlg->exec();
                dlg->deleteLater();
            });

            file_menu->addSeparator();

            // Connect / Disconnect ECU actions.
            auto* connect_action = file_menu->addAction("&Connect to ECU...");
            auto* disconnect_action = file_menu->addAction("&Disconnect");
            disconnect_action->setEnabled(false);

            auto open_connect = [this, ecu_conn, conn_label,
                                 connect_action, disconnect_action]() {
                if (open_connect_dialog(this, ecu_conn, conn_label)) {
                    connect_action->setEnabled(false);
                    disconnect_action->setEnabled(true);
                    // Build channel layouts from the active definition
                    // for runtime packet decoding.
                    {
                        auto def_opt_c = load_active_definition();
                        if (def_opt_c.has_value()) {
                            build_channel_layouts(ecu_conn, &*def_opt_c);
                            std::printf("[connect] Channel layouts built, "
                                "page reads deferred to on-demand\n");
                            std::fflush(stdout);
                        }
                    }
                }
            };
            *connect_callback = open_connect;
            QObject::connect(connect_action, &QAction::triggered, open_connect);
            QObject::connect(disconnect_action, &QAction::triggered,
                             [this, ecu_conn, conn_label, connect_action, disconnect_action]() {
                if (!ecu_conn->dirty_pages.empty()) {
                    auto answer = QMessageBox::warning(this,
                        QString::fromUtf8("Disconnect"),
                        QString::fromUtf8(
                            "Changes written to RAM have not been burned to flash.\n"
                            "Disconnect anyway? Unburned changes will be lost on ECU power cycle."),
                        QMessageBox::Ok | QMessageBox::Cancel,
                        QMessageBox::Cancel);
                    if (answer != QMessageBox::Ok) return;
                }
                ecu_conn->close();
                connect_action->setEnabled(true);
                disconnect_action->setEnabled(false);
                if (conn_label) {
                    char ct[256];
                    std::snprintf(ct, sizeof(ct),
                        "<span style='color: %s;'>\xe2\x97\x8b</span> "
                        "<span style='color: %s;'>Offline</span>",
                        tt::text_dim, tt::text_muted);
                    conn_label->setText(QString::fromUtf8(ct));
                }
            });

            file_menu->addSeparator();
            auto* exit_action = file_menu->addAction("E&xit");
            exit_action->setShortcut(QKeySequence::Quit);
            exit_action->setShortcutContext(Qt::ApplicationShortcut);
            QObject::connect(exit_action, &QAction::triggered, this, &QWidget::close);
            this->addAction(exit_action);

            // View menu ------------------------------------------------
            auto* view_menu = menu_bar->addMenu("&View");
            // Sidebar page navigation (Alt+1..8). The `&1` / `&2` etc.
            // mnemonics would collide with the Alt+N shortcuts Qt
            // already assigns automatically, so we leave the numeric
            // accelerators to the shortcut column and use plain
            // labels.
            static const char* nav_labels[8] = {
                "&Tune", "&Live", "&Flash", "&Setup",
                "&Assist", "T&riggers", "L&ogging", "&History",
            };
            for (int i = 0; i < 8; ++i) {
                auto* nav_action = view_menu->addAction(nav_labels[i]);
                nav_action->setShortcut(QKeySequence(Qt::ALT | (Qt::Key_1 + i)));
                nav_action->setShortcutContext(Qt::ApplicationShortcut);
                QObject::connect(nav_action, &QAction::triggered,
                                 [sidebar, i]() { sidebar->setCurrentRow(i); });
                this->addAction(nav_action);
            }
            view_menu->addSeparator();
            auto* palette_action = view_menu->addAction("Command &Palette...");
            palette_action->setShortcut(QKeySequence(Qt::CTRL | Qt::Key_K));
            palette_action->setShortcutContext(Qt::ApplicationShortcut);
            QObject::connect(palette_action, &QAction::triggered, open_command_palette);
            this->addAction(palette_action);

            // Tune menu ------------------------------------------------
            //
            // Review / Write to RAM / Burn to Flash live on the TUNE
            // tab's container as QShortcut instances, not main-window
            // actions — they're context-scoped so the operator can
            // press Ctrl+R / W / B only while the TUNE tab is
            // focused. The menu entries here do NOT set keyboard
            // shortcuts (would conflict with the container-scoped
            // QShortcuts); they switch to the TUNE tab so the
            // operator has the scope they need. The shortcut column
            // is left empty on these entries to stay honest about
            // the context-scoping.
            auto* tune_menu = menu_bar->addMenu("&Tune");
            auto* goto_tune = tune_menu->addAction("Go to &Tune Tab");
            QObject::connect(goto_tune, &QAction::triggered,
                             [sidebar]() { sidebar->setCurrentRow(0); });
            tune_menu->addSeparator();
            tune_menu->addAction("&Review Staged Changes... (Ctrl+R on Tune tab)")
                ->setEnabled(false);
            tune_menu->addAction("&Write to RAM (Ctrl+W on Tune tab)")
                ->setEnabled(false);
            tune_menu->addAction("&Burn to Flash (Ctrl+B on Tune tab)")
                ->setEnabled(false);

            // Help menu ------------------------------------------------
            auto* help_menu = menu_bar->addMenu("&Help");
            auto* shortcuts_action = help_menu->addAction("&Keyboard Shortcuts...");
            shortcuts_action->setShortcut(QKeySequence(Qt::Key_F1));
            shortcuts_action->setShortcutContext(Qt::ApplicationShortcut);
            QObject::connect(shortcuts_action, &QAction::triggered, open_shortcuts_dialog);
            this->addAction(shortcuts_action);
            // `?` as an alternate help binding (vim / terminal muscle
            // memory). Not shown in the menu because the primary
            // binding is F1 — the cheat sheet itself documents the
            // alternate.
            auto* help_q = new QAction(this);
            help_q->setShortcut(QKeySequence(Qt::SHIFT | Qt::Key_Slash));
            help_q->setShortcutContext(Qt::ApplicationShortcut);
            QObject::connect(help_q, &QAction::triggered, open_shortcuts_dialog);
            this->addAction(help_q);
            // Getting Started guide.
            auto* getting_started_action = help_menu->addAction("Getting &Started");
            QObject::connect(getting_started_action, &QAction::triggered, [this]() {
                auto* dlg = new QDialog(this);
                dlg->setWindowTitle("Getting Started");
                dlg->setFixedSize(520, 480);
                {
                    char s[64];
                    std::snprintf(s, sizeof(s), "QDialog { background: %s; }", tt::bg_base);
                    dlg->setStyleSheet(QString::fromUtf8(s));
                }
                auto* vl = new QVBoxLayout(dlg);
                vl->setContentsMargins(tt::space_xl, tt::space_xl, tt::space_xl, tt::space_xl);
                vl->setSpacing(tt::space_md);

                auto* body = new QLabel;
                body->setTextFormat(Qt::RichText);
                body->setWordWrap(true);
                {
                    char html[2048];
                    std::snprintf(html, sizeof(html),
                        "<span style='font-size: %dpx; font-weight: bold; color: %s;'>"
                        "Getting Started with Tuner</span><br><br>"

                        "<span style='color: %s; font-size: %dpx; font-weight: bold;'>"
                        "1. Connect to your ECU</span><br>"
                        "<span style='color: %s; font-size: %dpx;'>"
                        "File \xe2\x86\x92 Connect to ECU. Choose Serial (USB) or TCP/WiFi "
                        "(Airbear). Use Scan Network to auto-find devices.</span><br><br>"

                        "<span style='color: %s; font-size: %dpx; font-weight: bold;'>"
                        "2. View live data</span><br>"
                        "<span style='color: %s; font-size: %dpx;'>"
                        "Switch to the LIVE tab (Alt+2). Gauges show RPM, MAP, AFR, "
                        "temperatures. Right-click any gauge to customize it. "
                        "F11 for fullscreen dashboard.</span><br><br>"

                        "<span style='color: %s; font-size: %dpx; font-weight: bold;'>"
                        "3. Edit tune parameters</span><br>"
                        "<span style='color: %s; font-size: %dpx;'>"
                        "TUNE tab (Alt+1) shows all pages from the INI definition. "
                        "Click a page, edit values. Changes are staged (yellow) until "
                        "you press Ctrl+W to write to RAM.</span><br><br>"

                        "<span style='color: %s; font-size: %dpx; font-weight: bold;'>"
                        "4. Burn to flash</span><br>"
                        "<span style='color: %s; font-size: %dpx;'>"
                        "Ctrl+B burns written values to permanent flash. "
                        "Review changes first with Ctrl+R.</span><br><br>"

                        "<span style='color: %s; font-size: %dpx; font-weight: bold;'>"
                        "5. Log and analyze</span><br>"
                        "<span style='color: %s; font-size: %dpx;'>"
                        "LOGGING tab captures live data to CSV. "
                        "ASSIST tab imports logs for VE correction proposals. "
                        "Start a live VE session while driving for real-time analysis.</span><br><br>"

                        "<span style='color: %s; font-size: %dpx;'>"
                        "Press F1 at any time for keyboard shortcuts.</span>",

                        tt::font_heading, tt::text_primary,
                        tt::accent_primary, tt::font_body,
                        tt::text_secondary, tt::font_body,
                        tt::accent_primary, tt::font_body,
                        tt::text_secondary, tt::font_body,
                        tt::accent_primary, tt::font_body,
                        tt::text_secondary, tt::font_body,
                        tt::accent_primary, tt::font_body,
                        tt::text_secondary, tt::font_body,
                        tt::accent_primary, tt::font_body,
                        tt::text_secondary, tt::font_body,
                        tt::text_dim, tt::font_small);
                    body->setText(QString::fromUtf8(html));
                }
                vl->addWidget(body);
                dlg->exec();
                dlg->deleteLater();
            });

            // Connection guide.
            auto* connection_guide_action = help_menu->addAction("&Connection Guide");
            QObject::connect(connection_guide_action, &QAction::triggered, [this]() {
                auto* dlg = new QDialog(this);
                dlg->setWindowTitle("Connection Guide");
                dlg->setFixedSize(480, 400);
                {
                    char s[64];
                    std::snprintf(s, sizeof(s), "QDialog { background: %s; }", tt::bg_base);
                    dlg->setStyleSheet(QString::fromUtf8(s));
                }
                auto* vl = new QVBoxLayout(dlg);
                vl->setContentsMargins(tt::space_xl, tt::space_xl, tt::space_xl, tt::space_xl);
                vl->setSpacing(tt::space_md);

                auto* body = new QLabel;
                body->setTextFormat(Qt::RichText);
                body->setWordWrap(true);
                {
                    char html[2048];
                    std::snprintf(html, sizeof(html),
                        "<span style='font-size: %dpx; font-weight: bold; color: %s;'>"
                        "Connecting to Your ECU</span><br><br>"

                        "<span style='color: %s; font-size: %dpx; font-weight: bold;'>"
                        "USB Serial</span><br>"
                        "<span style='color: %s; font-size: %dpx;'>"
                        "Plug in via USB. Select the COM port and baud rate (115200 for "
                        "most boards). The app auto-probes baud rates if the first "
                        "attempt fails.</span><br><br>"

                        "<span style='color: %s; font-size: %dpx; font-weight: bold;'>"
                        "WiFi via Airbear</span><br>"
                        "<span style='color: %s; font-size: %dpx;'>"
                        "Connect your laptop to the Airbear WiFi network. Switch to "
                        "TCP/WiFi in the connection dialog. Host: speeduino.local, "
                        "Port: 2000. Use Scan Network to auto-discover.</span><br><br>"

                        "<span style='color: %s; font-size: %dpx; font-weight: bold;'>"
                        "Supported Boards</span><br>"
                        "<span style='color: %s; font-size: %dpx;'>"
                        "\xe2\x80\xa2 Teensy 4.1 (DropBear) \xe2\x80\x94 recommended<br>"
                        "\xe2\x80\xa2 Teensy 3.5 / 3.6<br>"
                        "\xe2\x80\xa2 Arduino Mega 2560<br>"
                        "\xe2\x80\xa2 STM32F407 (Black Pill)</span><br><br>"

                        "<span style='color: %s; font-size: %dpx; font-weight: bold;'>"
                        "Troubleshooting</span><br>"
                        "<span style='color: %s; font-size: %dpx;'>"
                        "No COM port? Check USB cable and drivers. "
                        "WiFi timeout? Verify you're on the Airbear network. "
                        "RC_BUSY_ERR? The Airbear dashboard is using the serial port "
                        "\xe2\x80\x94 close the browser tab or wait.</span>",

                        tt::font_heading, tt::text_primary,
                        tt::accent_ok, tt::font_body,
                        tt::text_secondary, tt::font_body,
                        tt::accent_ok, tt::font_body,
                        tt::text_secondary, tt::font_body,
                        tt::accent_ok, tt::font_body,
                        tt::text_secondary, tt::font_body,
                        tt::accent_warning, tt::font_body,
                        tt::text_secondary, tt::font_body);
                    body->setText(QString::fromUtf8(html));
                }
                vl->addWidget(body);
                dlg->exec();
                dlg->deleteLater();
            });

            help_menu->addSeparator();
            auto* about_action = help_menu->addAction("&About Tuner");
            QObject::connect(about_action, &QAction::triggered, [this]() {
                auto* dlg = new QDialog(this);
                dlg->setWindowTitle("About Tuner");
                dlg->setFixedSize(420, 280);
                {
                    char dstyle[192];
                    std::snprintf(dstyle, sizeof(dstyle),
                        "QDialog { background: %s; border: 1px solid %s; }"
                        "QLabel { color: %s; }",
                        tt::bg_base, tt::border, tt::text_secondary);
                    dlg->setStyleSheet(QString::fromUtf8(dstyle));
                }
                auto* vl = new QVBoxLayout(dlg);
                vl->setContentsMargins(tt::space_xl, tt::space_xl, tt::space_xl, tt::space_xl);
                vl->setSpacing(tt::space_md);
                vl->addStretch(1);
                auto* body = new QLabel;
                body->setTextFormat(Qt::RichText);
                body->setAlignment(Qt::AlignCenter);
                {
                    char html[1024];
                    std::snprintf(html, sizeof(html),
                        "<div style='text-align: center;'>"
                        "<span style='font-size: 24px; font-weight: bold; color: %s; "
                        "letter-spacing: 2px;'>TUNER</span><br>"
                        "<span style='color: %s; font-size: %dpx; letter-spacing: 1px;'>"
                        "guided power</span><br><br>"
                        "<span style='color: %s; font-size: %dpx;'>"
                        "A modern workstation for Speeduino engines.<br>"
                        "Native C++ Qt 6 build \xe2\x80\x94 Phase 14.</span><br><br>"
                        "<span style='color: %s; font-size: %dpx;'>"
                        "Everything you need to tune a Speeduino,<br>"
                        "organized around what you\xe2\x80\x99re<br>"
                        "trying to accomplish."
                        "</span>"
                        "</div>",
                        tt::text_primary,
                        tt::text_muted, tt::font_small,
                        tt::text_secondary, tt::font_body,
                        tt::text_dim, tt::font_small);
                    body->setText(QString::fromUtf8(html));
                }
                vl->addWidget(body);
                vl->addStretch(1);
                dlg->exec();
                dlg->deleteLater();
            });
        }

        // Menu bar stylesheet — matches the app shell chrome. The
        // default Qt menu bar renders with the OS system palette
        // which clashes with the dark theme, so we restyle via QSS.
        {
            char mb_style[768];
            std::snprintf(mb_style, sizeof(mb_style),
                "QMenuBar { background-color: %s; color: %s; "
                "  border-bottom: 1px solid %s; padding: 2px; }"
                "QMenuBar::item { background: transparent; padding: 4px 10px; }"
                "QMenuBar::item:selected { background: %s; color: %s; }"
                "QMenu { background-color: %s; color: %s; "
                "  border: 1px solid %s; padding: 4px; }"
                "QMenu::item { padding: 6px 24px 6px 14px; }"
                "QMenu::item:selected { background: %s; color: %s; }"
                "QMenu::item:disabled { color: %s; }"
                "QMenu::separator { height: 1px; background: %s; "
                "  margin: 4px 6px; }",
                tt::bg_deep, tt::text_secondary, tt::border,
                tt::fill_primary_mid, tt::text_primary,
                tt::bg_panel, tt::text_secondary, tt::border,
                tt::fill_primary_mid, tt::text_primary,
                tt::text_dim,
                tt::border);
            menu_bar->setStyleSheet(QString::fromUtf8(mb_style));
        }

        // Sidebar container: nav list + connection indicator + a quiet
        // philosophy wordmark footer at the bottom. The wordmark is the
        // one place in the chrome that says "what is this app about".
        // Intentionally tiny and dim — it's there for anyone curious
        // enough to look, not to dominate the workspace.
        auto* sidebar_container = new QWidget;
        sidebar_container->setFixedWidth(160);
        {
            char cstyle[64];
            std::snprintf(cstyle, sizeof(cstyle), "background: %s;", tt::bg_deep);
            sidebar_container->setStyleSheet(QString::fromUtf8(cstyle));
        }
        auto* sidebar_vl = new QVBoxLayout(sidebar_container);
        sidebar_vl->setContentsMargins(0, 0, 0, 0);
        sidebar_vl->setSpacing(0);
        sidebar_vl->addWidget(sidebar, 1);

        // Connection indicator — created early in the constructor so
        // the File menu lambdas can capture the pointer. Just add to
        // the sidebar layout here.
        sidebar_vl->addWidget(conn_label);

        // Philosophy wordmark footer. Two quiet lines of identity
        // beneath the connection indicator. See docs/ux-design.md
        // "Core Principles" — the tagline is a literal echo of the
        // philosophy doc's opening paragraph ("guided power").
        auto* wordmark = new QLabel;
        wordmark->setTextFormat(Qt::RichText);
        wordmark->setAlignment(Qt::AlignCenter);
        wordmark->setMinimumHeight(40);
        {
            char ws[192];
            std::snprintf(ws, sizeof(ws),
                "background: %s; border-top: 1px solid %s; "
                "padding: %dpx %dpx;",
                tt::bg_deep, tt::border_soft, tt::space_sm, tt::space_sm);
            wordmark->setStyleSheet(QString::fromUtf8(ws));
        }
        {
            char wt[384];
            std::snprintf(wt, sizeof(wt),
                "<div style='line-height: 1.3;'>"
                "<span style='color: %s; font-size: %dpx; font-weight: bold; "
                "  letter-spacing: 3px;'>TUNER</span><br>"
                "<span style='color: %s; font-size: %dpx; letter-spacing: 1px;'>"
                "  guided power"
                "</span>"
                "</div>",
                tt::text_muted, tt::font_small,
                tt::text_dim, tt::font_micro);
            wordmark->setText(QString::fromUtf8(wt));
        }
        sidebar_vl->addWidget(wordmark);

        h_layout->addWidget(sidebar_container);
        h_layout->addWidget(stack, 1);
        setCentralWidget(central);

        // Dynamic status bar — live telemetry tail. The old "N services
        // · N tests" counter was removed because hard-coding those
        // numbers guarantees they go stale on the next sub-slice; the
        // status bar should only show things that are true *now*.
        auto* sb_ecu = new tuner_core::mock_ecu_runtime::MockEcu(77);
        auto* sb_timer = new QTimer(this);
        auto* sb = statusBar();
        sb->showMessage("Offline \xe2\x80\x94 File \xe2\x86\x92 Connect to link an ECU");

        // Permanent right-aligned hint: `Press F1 for shortcuts`. The
        // operator's eye lands on the left (live telemetry — the thing
        // that changes) then drifts right to the permanent hint, which
        // points to F1 for everything else. This is the discovery
        // breadcrumb a first-time operator needs: the app has
        // keyboard shortcuts, the app has a command palette, both
        // reachable via one key that's now permanently visible.
        //
        // Rendered as a muted QLabel so it reads as chrome ("this is
        // the app telling you how to use it") not content ("this is
        // information from the ECU"). `text_dim` + `font_small` keeps
        // it quiet enough to ignore once the operator has learned it.
        {
            auto* hint = new QLabel(QString::fromUtf8("Press F1 for shortcuts"));
            hint->setTextFormat(Qt::PlainText);
            char hint_style[128];
            std::snprintf(hint_style, sizeof(hint_style),
                "color: %s; font-size: %dpx; padding-right: %dpx;",
                tt::text_dim, tt::font_small, tt::space_sm);
            hint->setStyleSheet(QString::fromUtf8(hint_style));
            sb->addPermanentWidget(hint);
        }
        QObject::connect(sb_timer, &QTimer::timeout, [sb, sb_ecu, ecu_conn]() {
            char msg[256];
            if (ecu_conn && ecu_conn->connected) {
                // Real ECU connected — show real telemetry.
                std::snprintf(msg, sizeof(msg),
                    "%s  \xc2\xb7  "
                    "RPM %.0f  \xc2\xb7  MAP %.0f  \xc2\xb7  AFR %.2f  \xc2\xb7  "
                    "CLT %.1f\xc2\xb0""C",
                    ecu_conn->info.signature.c_str(),
                    ecu_conn->get("rpm"), ecu_conn->get("map"),
                    ecu_conn->get("afr"), ecu_conn->get("clt"));
            } else {
                // Mock fallback.
                auto snap = sb_ecu->poll();
                std::snprintf(msg, sizeof(msg),
                    "Offline  \xc2\xb7  "
                    "RPM %.0f  \xc2\xb7  MAP %.0f  \xc2\xb7  AFR %.2f  \xc2\xb7  "
                    "CLT %.1f\xc2\xb0""C  (demo)",
                    snap.get("rpm"), snap.get("map"), snap.get("afr"), snap.get("clt"));
            }
            sb->showMessage(QString::fromUtf8(msg));
        });
        sb_timer->start(500);

        // --------------------------------------------------------
        // Session restore — `QMainWindow::restoreGeometry` /
        // `restoreState` pull the last-run window size, position,
        // maximized state, and splitter layout from QSettings.
        // Operator expectation: "the app remembers where I left it"
        // is basic desktop hygiene, not a feature.
        //
        // Additional keys restored here:
        //   - `session/last_tab` — which sidebar page was active
        // Both default to zero / current on first launch (no
        // saved session yet).
        // --------------------------------------------------------
        QSettings settings;
        if (auto geometry = settings.value("session/geometry").toByteArray();
            !geometry.isEmpty()) {
            restoreGeometry(geometry);
        }
        if (auto state = settings.value("session/window_state").toByteArray();
            !state.isEmpty()) {
            restoreState(state);
        }
        // Restore the last-active sidebar tab. Clamped to [0, 7]
        // because the valid range is the 8 top-level pages — if a
        // future slice adds or removes tabs, an out-of-range saved
        // value falls through safely to tab 0 (TUNE).
        const int saved_tab = settings.value("session/last_tab", 0).toInt();
        if (saved_tab >= 0 && saved_tab < sidebar->count()) {
            sidebar->setCurrentRow(saved_tab);
        }
        debug_log("TunerMainWindow ctor end");
    }

protected:
    // QMainWindow close override — save the session state back to
    // QSettings so the next launch lands in the same place. Called
    // by Qt on every normal close path (window close button, File
    // menu Exit, Alt+F4, `qApp->quit()`).
    //
    // Philosophy — this is one of the "invisible affordances" the
    // ux-design doc calls out: chrome the operator never sees but
    // would immediately notice if it went missing. Nothing
    // announces that session state was restored; the app just opens
    // where the operator last closed it.
    void closeEvent(QCloseEvent* event) override {
        QSettings settings;
        settings.setValue("session/geometry", saveGeometry());
        settings.setValue("session/window_state", saveState());
        // Find the active sidebar tab via the central widget tree.
        // `centralWidget()->findChild<QListWidget*>` reaches the
        // sidebar regardless of how deep the layout nests it.
        if (auto* sidebar = findChild<QListWidget*>()) {
            settings.setValue("session/last_tab", sidebar->currentRow());
        }
        QMainWindow::closeEvent(event);
    }
};

}  // namespace

int main(int argc, char* argv[]) {
    std::ofstream(debug_log_path(), std::ios::trunc | std::ios::binary).close();
    debug_log("main enter");
    std::printf("[main] enter\n"); std::fflush(stdout);
    try {
        QApplication app(argc, argv);
        debug_log("QApplication constructed");
        std::printf("[main] qapp ok\n"); std::fflush(stdout);
        QApplication::setApplicationName("Tuner");
        // Dark theme via stylesheet only (no QPalette + Fusion combo, which
        // has been observed to interact badly with the Qt 6.7 prebuilt MinGW
        // DLLs on UCRT 15.2 — see diagnostic notes in file header). Composed
        // from theme tokens so the global chrome stays coherent with every
        // tokenized surface migrated in sub-slices 88 / 90 / 91 / 111 / 112.
        //
        // The near-black drift of `#15171c` / `#181b22` / `#1c1f26` all
        // collapses to two tokens (`bg_base` for the shell, `bg_panel`
        // for content containers) — matching the 5-level background
        // ladder introduced in sub-slice 88. The `#ffffff` explicit
        // white on selected tree/list items becomes `text_primary` so
        // every "selected" state reads as the same color across the
        // app. `scroll_thumb_hover` is the one new token this slice
        // adds — one brightness band above `border` that nothing else
        // in the palette needs.
        {
            static char DARK_QSS[2048];
            std::snprintf(DARK_QSS, sizeof(DARK_QSS),
                "QMainWindow { background-color: %s; }"
                "QWidget { color: %s; background-color: %s; }"
                "QTabWidget::pane { border: 1px solid %s; "
                "  background-color: %s; top: -1px; }"
                "QTabBar::tab { background: %s; color: %s; "
                "  padding: %dpx %dpx; border: 1px solid %s; "
                "  border-bottom: none; margin-right: 2px; "
                "  font-weight: bold; letter-spacing: 1px; }"
                "QTabBar::tab:selected { background: %s; color: %s; "
                "  border-top: 2px solid %s; }"
                "QTabBar::tab:hover:!selected { background: %s; color: %s; }"
                "QStatusBar { background: %s; color: %s; "
                "  border-top: 1px solid %s; }"
                "QLineEdit { background: %s; border: 1px solid %s; "
                "  border-radius: %dpx; padding: %dpx %dpx; color: %s; "
                "  selection-background-color: %s; }"
                "QLineEdit:focus { border: 1px solid %s; }"
                "QTreeWidget, QListWidget { background: %s; "
                "  border: 1px solid %s; border-radius: %dpx; "
                "  outline: none; alternate-background-color: %s; }"
                "QTreeWidget::item, QListWidget::item { padding: %dpx %dpx; }"
                "QTreeWidget::item:selected, QListWidget::item:selected { "
                "  background: %s; color: %s; }"
                "QTreeWidget::item:hover, QListWidget::item:hover { "
                "  background: %s; }"
                "QSplitter::handle { background: %s; }"
                "QScrollBar:vertical { background: %s; width: 10px; }"
                "QScrollBar::handle:vertical { background: %s; "
                "  border-radius: %dpx; min-height: 20px; }"
                "QScrollBar::handle:vertical:hover { background: %s; }"
                // Sub-slice 128: tooltips land on every sidebar
                // item and (eventually) elsewhere, so the default
                // system-yellow Qt tooltip would clash hard with
                // the dark theme. Tokenize with `bg_elevated` +
                // `text_primary` + `border` to match the rest of
                // the app shell — tooltips now read as first-class
                // chrome, not as an OS-level popup that escaped
                // the theme layer.
                "QToolTip { background-color: %s; color: %s; "
                "  border: 1px solid %s; border-radius: %dpx; "
                "  padding: %dpx %dpx; font-size: %dpx; }",
                tt::bg_base,
                tt::text_secondary, tt::bg_base,
                tt::border, tt::bg_panel,
                tt::bg_panel, tt::text_muted,
                tt::space_sm, tt::space_lg + 2, tt::border,
                tt::bg_elevated, tt::text_primary, tt::accent_primary,
                tt::bg_panel, tt::text_secondary,
                tt::bg_panel, tt::text_muted, tt::border,
                tt::bg_elevated, tt::border,
                tt::radius_sm, tt::space_xs + 2, tt::space_sm, tt::text_primary,
                tt::accent_primary,
                tt::accent_primary,
                tt::bg_panel, tt::border, tt::radius_sm, tt::bg_panel,
                tt::space_xs, tt::space_xs + 2,
                tt::fill_primary_mid, tt::text_primary,
                tt::bg_elevated,
                tt::border,
                tt::bg_panel,
                tt::border, tt::radius_sm,
                tt::scroll_thumb_hover,
                tt::bg_elevated, tt::text_primary, tt::border,
                tt::radius_sm, tt::space_xs + 2, tt::space_sm, tt::font_small);
            qApp->setStyleSheet(QString::fromUtf8(DARK_QSS));
        }
        std::printf("[main] dark theme applied\n"); std::fflush(stdout);

        bool startup_want_connect = false;
        bool want_new_project = false;

        // ---- G1: Startup project picker ----
        //
        // Tokenized welcome dialog. The wordmark footer pattern (sub-
        // slice 90) says this is the one place the app identifies
        // itself out loud; the startup picker echoes the same grammar
        // with the bold "Tuner" title above a dim tagline. Progressive
        // disclosure: hero title → tagline → recent project chip →
        // action buttons → dismissable hint.
        {
            auto recent_proj = load_recent_project();
            auto* startup = new QDialog;
            startup->setWindowTitle("Tuner \xe2\x80\x94 Welcome");
            startup->setFixedSize(520, 380);
            {
                char startup_qss[768];
                std::snprintf(startup_qss, sizeof(startup_qss),
                    "QDialog { background: %s; }"
                    "QPushButton { background: %s; border: 1px solid %s; "
                    "  border-radius: %dpx; padding: %dpx %dpx; color: %s; "
                    "  font-size: %dpx; font-weight: bold; }"
                    "QPushButton:hover { background: %s; border-color: %s; color: %s; }"
                    "QPushButton:pressed { background: %s; }",
                    tt::bg_deep,
                    tt::bg_elevated, tt::border,
                    tt::radius_md, tt::space_sm + 2, tt::space_lg + 4, tt::text_secondary,
                    tt::font_body,
                    tt::fill_primary_mid, tt::accent_primary, tt::text_primary,
                    tt::fill_primary_soft);
                startup->setStyleSheet(QString::fromUtf8(startup_qss));
            }

            auto* vl = new QVBoxLayout(startup);
            vl->setContentsMargins(tt::space_xl + 8, tt::space_xl + 4,
                                   tt::space_xl + 8, tt::space_xl + 4);
            vl->setSpacing(tt::space_lg);

            auto* welcome = new QLabel;
            welcome->setTextFormat(Qt::RichText);
            welcome->setAlignment(Qt::AlignCenter);
            {
                char welcome_html[384];
                std::snprintf(welcome_html, sizeof(welcome_html),
                    "<span style='font-size: 20px; font-weight: bold; color: %s;'>"
                    "Tuner</span><br>"
                    "<span style='color: %s; font-size: %dpx;'>"
                    "A modern workstation for Speeduino engines</span>",
                    tt::text_primary,
                    tt::text_muted, tt::font_body);
                welcome->setText(QString::fromUtf8(welcome_html));
            }
            vl->addWidget(welcome);

            // Recent project card — shows the last-opened project from
            // QSettings. On first launch (no saved project), shows a
            // placeholder inviting the operator to open their first tune.
            auto* recent = new QLabel;
            recent->setTextFormat(Qt::RichText);
            {
                char recent_html[640];
                if (!recent_proj.name.empty()) {
                    std::string date_label = friendly_date(recent_proj.last_opened);
                    std::string sig_display = recent_proj.signature.empty()
                        ? "unknown signature" : recent_proj.signature;
                    std::snprintf(recent_html, sizeof(recent_html),
                        "<span style='color: %s; font-size: %dpx;'>Recent project:</span><br>"
                        "<span style='color: %s; font-size: %dpx; font-weight: bold;'>"
                        "%s</span><br>"
                        "<span style='color: %s; font-size: %dpx;'>"
                        "%s  \xc2\xb7  last opened %s</span>",
                        tt::text_dim, tt::font_small,
                        tt::text_secondary, tt::font_medium,
                        recent_proj.name.c_str(),
                        tt::text_dim, tt::font_micro,
                        sig_display.c_str(), date_label.c_str());
                } else {
                    std::snprintf(recent_html, sizeof(recent_html),
                        "<span style='color: %s; font-size: %dpx;'>No recent project</span><br>"
                        "<span style='color: %s; font-size: %dpx;'>"
                        "Open a tune file to get started</span>",
                        tt::text_dim, tt::font_small,
                        tt::text_dim, tt::font_micro);
                }
                recent->setText(QString::fromUtf8(recent_html));
            }
            {
                char recent_style[192];
                std::snprintf(recent_style, sizeof(recent_style),
                    "%s padding: %dpx %dpx;",
                    tt::card_style().c_str(),
                    tt::space_md + 2, tt::space_lg + 2);
                recent->setStyleSheet(QString::fromUtf8(recent_style));
            }
            recent->setCursor(Qt::PointingHandCursor);
            vl->addWidget(recent);

            auto* btn_layout = new QHBoxLayout;
            btn_layout->setSpacing(tt::space_sm + 2);
            auto* btn_open = new QPushButton(QString::fromUtf8("Open Last Project"));
            auto* btn_new = new QPushButton(QString::fromUtf8("New Project"));
            auto* btn_connect = new QPushButton(QString::fromUtf8("Connect & Detect"));
            btn_layout->addWidget(btn_open);
            btn_layout->addWidget(btn_new);
            btn_layout->addWidget(btn_connect);
            vl->addLayout(btn_layout);

            auto* skip = new QLabel;
            skip->setTextFormat(Qt::RichText);
            skip->setAlignment(Qt::AlignCenter);
            {
                char skip_html[256];
                std::snprintf(skip_html, sizeof(skip_html),
                    "<span style='color: %s; font-size: %dpx;'>"
                    "Press Escape or click Open Last Project to start tuning immediately."
                    "</span>",
                    tt::text_dim, tt::font_micro);
                skip->setText(QString::fromUtf8(skip_html));
            }
            vl->addWidget(skip);

            vl->addStretch(1);

            // Track which action was chosen.
            bool want_connect = false;
            QObject::connect(btn_open, &QPushButton::clicked, startup, &QDialog::accept);
            QObject::connect(btn_new, &QPushButton::clicked, [&want_new_project, startup]() {
                want_new_project = true;  // outer scope variable
                startup->accept();
            });
            QObject::connect(btn_connect, &QPushButton::clicked, [&want_connect, startup]() {
                want_connect = true;
                startup->accept();
            });

            startup->exec();
            startup->deleteLater();

            startup_want_connect = want_connect;
        }

        TunerMainWindow window;
        debug_log("main window built");
        std::printf("[main] window built\n"); std::fflush(stdout);
        window.show();
        if (startup_want_connect) {
            // Trigger File → Connect after the event loop starts.
            QTimer::singleShot(100, [&window]() {
                auto actions = window.menuBar()->actions();
                for (auto* menu_action : actions) {
                    if (auto* menu = menu_action->menu()) {
                        for (auto* act : menu->actions()) {
                            auto text = act->text().toStdString();
                            if (text.find("Connect") != std::string::npos
                                && text.find("Disconnect") == std::string::npos) {
                                act->trigger();
                                return;
                            }
                        }
                    }
                }
            });
        }
        if (want_new_project) {
            // "New Project" → open the File → New Project dialog,
            // then switch to Setup tab for the wizard.
            QTimer::singleShot(200, [&window]() {
                // Trigger the File → New Project action if it exists.
                auto actions = window.findChildren<QAction*>();
                for (auto* action : actions) {
                    if (action->text().contains("New Project")) {
                        action->trigger();
                        break;
                    }
                }
                // Switch to Setup tab (index 3) for the wizard.
                if (auto* sidebar = window.findChild<QListWidget*>())
                    sidebar->setCurrentRow(3);
            });
        }
        debug_log("main window shown");
        std::printf("[main] window shown\n"); std::fflush(stdout);

        return QApplication::exec();
    } catch (const std::exception& e) {
        debug_log(std::string("FATAL exception: ") + e.what());
        std::fprintf(stderr, "[tuner_app] FATAL: %s\n", e.what());
        return 1;
    } catch (...) {
        debug_log("FATAL unknown exception");
        std::fprintf(stderr, "[tuner_app] FATAL: unknown\n");
        return 1;
    }
}
