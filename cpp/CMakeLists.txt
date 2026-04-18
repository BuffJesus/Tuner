# Future Phase 13 — Native shared core (first slice).
#
# Builds:
#   - tuner_core              static library (C++20, stdlib only)
#   - tuner_core_tests        doctest unit suite for the C++ side
#   - tuner_core (binding)    nanobind Python extension (optional)
#
# Defaults match the agreed Phase 13 scope decisions:
#   - C++20 baseline
#   - CMake build system
#   - stdlib + minimal vendored deps (doctest, nanobind)
#   - subdirectory of the main repo at cpp/
#
# Build instructions live in cpp/README.md.

cmake_minimum_required(VERSION 3.20)
project(tuner_core LANGUAGES CXX VERSION 0.1.0)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

if(MSVC)
    add_compile_options(/W4 /permissive-)
else()
    add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# Static-link the MinGW runtime so the resulting .pyd / .exe has zero
# runtime DLL dependency. Without this, Python on Windows can't load
# the extension because it doesn't honor PATH for DLL search since 3.8
# (the user would have to call os.add_dll_directory() for the MinGW
# bin every time). Static linking makes the artifact self-contained.
if(MINGW)
    add_link_options(
        -static-libgcc
        -static-libstdc++
        -static
        -Wl,-Bstatic,--whole-archive
        -lwinpthread
        -Wl,--no-whole-archive
    )
endif()

option(TUNER_CORE_BUILD_TESTS "Build the doctest unit suite" ON)
option(TUNER_CORE_BUILD_BINDINGS "Build the nanobind Python extension (kept while Python is the oracle)" OFF)
option(TUNER_BUILD_APP "Build the native Qt 6 desktop application" OFF)

function(tuner_find_first_existing out_var)
    foreach(candidate IN LISTS ARGN)
        if(EXISTS "${candidate}")
            set(${out_var} "${candidate}" PARENT_SCOPE)
            return()
        endif()
    endforeach()
    set(${out_var} "" PARENT_SCOPE)
endfunction()

# ---------------------------------------------------------------------------
# Core library
# ---------------------------------------------------------------------------

add_library(tuner_core STATIC
    src/msq_parser.cpp
    src/native_format.cpp
    src/ini_preprocessor.cpp
    src/ini_constants_parser.cpp
    src/ini_defines_parser.cpp
    src/ini_output_channels_parser.cpp
    src/ini_table_editor_parser.cpp
    src/ini_curve_editor_parser.cpp
    src/ini_menu_parser.cpp
    src/ini_gauge_configurations_parser.cpp
    src/ini_front_page_parser.cpp
    src/ini_logger_definition_parser.cpp
    src/ini_controller_commands_parser.cpp
    src/ecu_definition_compiler.cpp
    src/speeduino_framing.cpp
    src/speeduino_protocol.cpp
    src/speeduino_value_codec.cpp
    src/speeduino_param_codec.cpp
    src/speeduino_live_data_decoder.cpp
    src/visibility_expression.cpp
    src/math_expression_evaluator.cpp
    src/flash_target_detection.cpp
    src/required_fuel_calculator.cpp
    src/table_edit.cpp
    src/sample_gate_helpers.cpp
    src/autotune_filter_gate_evaluator.cpp
    src/wue_analyze_helpers.cpp
    src/hardware_setup_validation.cpp
    src/board_detection.cpp
    src/pressure_sensor_calibration.cpp
    src/release_manifest.cpp
    src/tune_value_preview.cpp
    src/staged_change.cpp
    src/tuning_page_diff.cpp
    src/table_view.cpp
    src/evidence_replay_comparison.cpp
    src/gauge_color_zones.cpp
    src/tuning_page_validation.cpp
    src/sync_state.cpp
    src/parameter_catalog.cpp
    src/flash_preflight.cpp
    src/live_data_map_parser.cpp
    src/page_family.cpp
    src/curve_page_classifier.cpp
    src/operation_log.cpp
    src/operation_evidence.cpp
    src/surface_evidence.cpp
    src/scalar_page_editor.cpp
    src/table_replay_context.cpp
    src/table_replay_hit.cpp
    src/replay_sample_gate.cpp
    src/datalog_review.cpp
    src/table_rendering.cpp
    src/ve_proposal_smoothing.cpp
    src/ve_root_cause_diagnostics.cpp
    src/ve_cell_hit_accumulator.cpp
    src/ve_analyze_review.cpp
    src/wue_analyze_snapshot.cpp
    src/wue_analyze_review.cpp
    src/thermistor_calibration.cpp
    src/idle_rpm_generator.cpp
    src/afr_target_generator.cpp
    src/spark_table_generator.cpp
    src/ve_table_generator.cpp
    src/startup_enrichment_generator.cpp
    src/runtime_telemetry.cpp
    src/ini_dialog_parser.cpp
    src/definition_layout.cpp
    src/tuning_page_grouping.cpp
    src/local_tune_edit.cpp
    src/wideband_calibration.cpp
    src/dashboard_layout.cpp
    src/hardware_presets.cpp
    src/firmware_capabilities.cpp
    src/operator_engine_context.cpp
    src/hardware_setup_generator_context.cpp
    src/sensor_setup_checklist.cpp
    src/curve_page_builder.cpp
    src/evidence_replay.cpp
    src/page_evidence_review.cpp
    src/evidence_replay_formatter.cpp
    src/trigger_log_visualization.cpp
    src/trigger_log_analysis.cpp
    src/datalog_profile.cpp
    src/firmware_catalog.cpp
    src/datalog_replay.cpp
    src/ignition_trigger_cross_validation.cpp
    src/ts_dash_file.cpp
    src/wue_analyze_accumulator.cpp
    src/virtual_dyno.cpp
    src/chart_axes.cpp
    src/widget_math.cpp
    src/tune_storage_map.cpp
    src/boost_table_generator.cpp
    src/compressor_map_modeling.cpp
    src/ve_analyze_accumulator.cpp
    src/tuning_page_builder.cpp
    src/datalog_import.cpp
    src/msq_value_formatter.cpp
    src/workspace_state.cpp
    src/native_tune_writer.cpp
    src/project_file.cpp
    src/native_definition_writer.cpp
    src/hardware_setup_summary.cpp
    src/workspace_presenter.cpp
    src/table_surface_3d.cpp
    src/live_trigger_logger.cpp
    src/live_capture_session.cpp
    src/firmware_flash_builder.cpp
    src/legacy_project_file.cpp
    src/xcp_packets.cpp
    src/xcp_simulator.cpp
    src/protocol_simulator.cpp
    src/speeduino_connect_strategy.cpp
    src/ini_setting_groups_parser.cpp
    src/ini_setting_context_help_parser.cpp
    src/ini_constants_extensions_parser.cpp
    src/ini_tools_parser.cpp
    src/ini_reference_tables_parser.cpp
    src/ini_pc_variables_parser.cpp
    src/ini_autotune_sections_parser.cpp
    src/transport_serial.cpp
    src/transport_tcp.cpp
    src/mdns_discovery.cpp
    src/speeduino_controller.cpp
    src/teensy_hex_image.cpp
    src/teensy_hid_flasher.cpp
    src/udp_discovery.cpp
    src/airbear_api.cpp
)
target_include_directories(tuner_core
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
    PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/third_party
)
target_compile_features(tuner_core PUBLIC cxx_std_20)
# Link ws2_32 for winsock2 (TCP transport).
if(WIN32)
    target_link_libraries(tuner_core PRIVATE ws2_32 setupapi hid)
endif()

# Vendor check for nlohmann/json single header — used by native_format.cpp.
if(NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/third_party/nlohmann/json.hpp")
    message(FATAL_ERROR
        "nlohmann/json.hpp not found at cpp/third_party/nlohmann/json.hpp.\n"
        "Vendor the single-header release from "
        "https://github.com/nlohmann/json/releases (file: json.hpp)")
endif()

# ---------------------------------------------------------------------------
# Tests (doctest, single-header — vendored under third_party/doctest/)
# ---------------------------------------------------------------------------

if(TUNER_CORE_BUILD_TESTS)
    enable_testing()
    if(NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/third_party/doctest/doctest.h")
        message(FATAL_ERROR
            "doctest.h not found at cpp/third_party/doctest/doctest.h.\n"
            "Vendor the single-header release from "
            "https://github.com/doctest/doctest/releases (file: doctest.h)")
    endif()
    add_executable(tuner_core_tests
        tests/test_msq_parser.cpp
        tests/test_native_format.cpp
        tests/test_ini_preprocessor.cpp
        tests/test_ini_constants_parser.cpp
        tests/test_ini_defines_parser.cpp
        tests/test_ini_output_channels_parser.cpp
        tests/test_ini_table_editor_parser.cpp
        tests/test_ini_curve_editor_parser.cpp
        tests/test_ini_menu_parser.cpp
        tests/test_ini_gauge_configurations_parser.cpp
        tests/test_ini_front_page_parser.cpp
        tests/test_ini_logger_definition_parser.cpp
        tests/test_ini_controller_commands_parser.cpp
        tests/test_ecu_definition_compiler.cpp
        tests/test_speeduino_framing.cpp
        tests/test_speeduino_protocol.cpp
        tests/test_speeduino_value_codec.cpp
        tests/test_speeduino_param_codec.cpp
        tests/test_speeduino_live_data_decoder.cpp
        tests/test_visibility_expression.cpp
        tests/test_math_expression_evaluator.cpp
        tests/test_flash_target_detection.cpp
        tests/test_required_fuel_calculator.cpp
        tests/test_table_edit.cpp
        tests/test_sample_gate_helpers.cpp
        tests/test_autotune_filter_gate_evaluator.cpp
        tests/test_wue_analyze_helpers.cpp
        tests/test_hardware_setup_validation.cpp
        tests/test_board_detection.cpp
        tests/test_pressure_sensor_calibration.cpp
        tests/test_release_manifest.cpp
        tests/test_tune_value_preview.cpp
        tests/test_staged_change.cpp
        tests/test_tuning_page_diff.cpp
        tests/test_table_view.cpp
        tests/test_evidence_replay_comparison.cpp
        tests/test_gauge_color_zones.cpp
        tests/test_tuning_page_validation.cpp
        tests/test_sync_state.cpp
        tests/test_parameter_catalog.cpp
        tests/test_flash_preflight.cpp
        tests/test_live_data_map_parser.cpp
        tests/test_page_family.cpp
        tests/test_curve_page_classifier.cpp
        tests/test_operation_log.cpp
        tests/test_operation_evidence.cpp
        tests/test_surface_evidence.cpp
        tests/test_scalar_page_editor.cpp
        tests/test_table_replay_context.cpp
        tests/test_table_replay_hit.cpp
        tests/test_replay_sample_gate.cpp
        tests/test_datalog_review.cpp
        tests/test_table_rendering.cpp
        tests/test_ve_proposal_smoothing.cpp
        tests/test_ve_root_cause_diagnostics.cpp
        tests/test_ve_cell_hit_accumulator.cpp
        tests/test_ve_analyze_review.cpp
        tests/test_wue_analyze_snapshot.cpp
        tests/test_wue_analyze_review.cpp
        tests/test_thermistor_calibration.cpp
        tests/test_idle_rpm_generator.cpp
        tests/test_afr_target_generator.cpp
        tests/test_spark_table_generator.cpp
        tests/test_ve_table_generator.cpp
        tests/test_startup_enrichment_generator.cpp
        tests/test_runtime_telemetry.cpp
        tests/test_ini_dialog_parser.cpp
        tests/test_definition_layout.cpp
        tests/test_tuning_page_grouping.cpp
        tests/test_local_tune_edit.cpp
        tests/test_wideband_and_dashboard.cpp
        tests/test_hardware_presets.cpp
        tests/test_firmware_capabilities.cpp
        tests/test_operator_engine_context.cpp
        tests/test_hardware_setup_generator_context.cpp
        tests/test_sensor_setup_checklist.cpp
        tests/test_curve_page_builder.cpp
        tests/test_evidence_replay.cpp
        tests/test_page_evidence_review.cpp
        tests/test_evidence_replay_formatter.cpp
        tests/test_trigger_log_visualization.cpp
        tests/test_trigger_log_analysis.cpp
        tests/test_live_analyze_session.cpp
        tests/test_datalog_profile.cpp
        tests/test_firmware_catalog.cpp
        tests/test_datalog_replay.cpp
        tests/test_ignition_trigger_cross_validation.cpp
        tests/test_mock_ecu_runtime.cpp
        tests/test_ts_dash_file.cpp
        tests/test_wue_analyze_accumulator.cpp
        tests/test_ve_analyze_accumulator.cpp
        tests/test_tuning_page_builder.cpp
        tests/test_datalog_import.cpp
        tests/test_integration_production_ini.cpp
        tests/test_integration_pipeline.cpp
        tests/test_msq_value_formatter.cpp
        tests/test_milestone_1000.cpp
        tests/test_workspace_state.cpp
        tests/test_native_tune_writer.cpp
        tests/test_project_file.cpp
        tests/test_native_definition_writer.cpp
        tests/test_native_format_integration.cpp
        tests/test_hardware_setup_summary.cpp
        tests/test_workspace_presenter.cpp
        tests/test_presenter_integration.cpp
        tests/test_end_to_end.cpp
        tests/test_table_surface_3d.cpp
        tests/test_live_trigger_logger.cpp
        tests/test_live_capture_session.cpp
        tests/test_firmware_flash_builder.cpp
        tests/test_legacy_project_file.cpp
        tests/test_xcp_packets.cpp
        tests/test_xcp_simulator.cpp
        tests/test_protocol_simulator.cpp
        tests/test_speeduino_connect_strategy.cpp
        tests/test_ini_setting_groups_parser.cpp
        tests/test_ini_setting_context_help_parser.cpp
        tests/test_ini_constants_extensions_parser.cpp
        tests/test_ini_tools_parser.cpp
        tests/test_ini_reference_tables_parser.cpp
        tests/test_ini_pc_variables_parser.cpp
        tests/test_ini_autotune_sections_parser.cpp
        tests/test_teensy_hex_image.cpp
        tests/test_mdns_discovery.cpp
        tests/test_udp_discovery.cpp
        tests/test_airbear_api.cpp
        tests/test_compressor_map_modeling.cpp
        tests/test_chart_axes.cpp
        tests/test_widget_math.cpp
        tests/test_tune_storage_map.cpp
    )
    target_include_directories(tuner_core_tests
        PRIVATE
            ${CMAKE_CURRENT_SOURCE_DIR}/third_party/doctest
    )
    target_link_libraries(tuner_core_tests PRIVATE tuner_core)
    add_test(NAME tuner_core_tests COMMAND tuner_core_tests)
endif()

# ---------------------------------------------------------------------------
# Offline tool: compile an INI into a schema-v2 .tunerdef. Run once
# after an INI change to refresh the shipped native fixture so the
# app loads from the native format without falling back to INI.
# ---------------------------------------------------------------------------

add_executable(gen_v2_tunerdef tools/gen_v2_tunerdef.cpp)
target_link_libraries(gen_v2_tunerdef PRIVATE tuner_core)
target_include_directories(gen_v2_tunerdef PRIVATE include)

# ---------------------------------------------------------------------------
# Python bindings (nanobind, optional)
# ---------------------------------------------------------------------------

if(TUNER_CORE_BUILD_BINDINGS)
    find_package(Python 3.10 COMPONENTS Interpreter Development.Module REQUIRED)
    find_package(nanobind CONFIG REQUIRED)
    nanobind_add_module(tuner_core_py NB_STATIC bindings/tuner_core_module.cpp)
    target_link_libraries(tuner_core_py PRIVATE tuner_core)
    set_target_properties(tuner_core_py PROPERTIES OUTPUT_NAME tuner_core)
endif()

# ---------------------------------------------------------------------------
# Native Qt 6 desktop application (Phase 14)
# ---------------------------------------------------------------------------

if(TUNER_BUILD_APP)
    # Qt 6 is found via the standard CONFIG package. The user is
    # expected to provide CMAKE_PREFIX_PATH pointing at the Qt
    # install prefix (e.g. C:/Qt/6.7.3/mingw_64) — see cpp/README.md.
    find_package(Qt6 6.5 REQUIRED COMPONENTS Core Gui Widgets)

    # Qt 6 metaobject compiler / resource compiler / UI compiler are
    # auto-invoked when these are ON. We don't use .ui files in v1
    # (hand-coded widgets per the locked Phase 14 scope decisions),
    # but Q_OBJECT classes still need MOC.
    set(CMAKE_AUTOMOC ON)
    set(CMAKE_AUTORCC ON)
    set(CMAKE_AUTOUIC OFF)

    # Use plain add_executable instead of qt_add_executable, then
    # explicitly NOT link Qt6::EntryPoint. The Qt 6.7 prebuilt
    # `Qt6EntryPoint.a` was compiled against an older MSVC-style
    # runtime that exports `__imp___argc` / `__imp___argv`; UCRT-based
    # MinGW 15.2.0 doesn't export those symbols, so the link fails
    # with "undefined reference to `__imp___argc`". Providing our own
    # main() and skipping the entry-point shim sidesteps the
    # mismatch entirely.
    add_executable(tuner_app
        app/main.cpp
        app/widgets/bar_gauge_widget.cpp
        app/widgets/dial_gauge_widget.cpp
        app/widgets/draggable_card_label.cpp
        app/widgets/histogram_widget.cpp
        app/widgets/led_gauge_widget.cpp
    )
    target_include_directories(tuner_app PRIVATE app)
    target_link_libraries(tuner_app
        PRIVATE
            tuner_core
            Qt6::Core
            Qt6::Gui
            Qt6::Widgets
    )

    if(WIN32)
        set(_user_home "$ENV{USERPROFILE}")
        tuner_find_first_existing(TUNER_TEENSY_TOOLS_SRC
            "${_user_home}/.platformio/packages/tool-teensy"
            "${_user_home}/Desktop/SpeedyLoader-1.7.0/bin/teensy_loader_cli-windows")
        tuner_find_first_existing(TUNER_AVRDUDE_TOOLS_SRC
            "${_user_home}/Desktop/SpeedyLoader-1.7.0/bin/avrdude-windows")
        tuner_find_first_existing(TUNER_DFUUTIL_TOOLS_SRC
            "${_user_home}/Desktop/SpeedyLoader-1.7.0/bin/dfuutil-windows")

        if(TUNER_TEENSY_TOOLS_SRC)
            add_custom_command(TARGET tuner_app POST_BUILD
                COMMAND ${CMAKE_COMMAND} -E make_directory
                    "$<TARGET_FILE_DIR:tuner_app>/bin/teensy_loader_cli-windows"
                COMMAND ${CMAKE_COMMAND} -E copy_directory
                    "${TUNER_TEENSY_TOOLS_SRC}"
                    "$<TARGET_FILE_DIR:tuner_app>/bin/teensy_loader_cli-windows"
                COMMENT "Bundling Teensy flash tools with tuner_app")
        else()
            message(WARNING
                "No local Teensy tools bundle found. tuner_app flashing for Teensy targets "
                "will rely on runtime discovery only.")
        endif()

        if(TUNER_AVRDUDE_TOOLS_SRC)
            add_custom_command(TARGET tuner_app POST_BUILD
                COMMAND ${CMAKE_COMMAND} -E make_directory
                    "$<TARGET_FILE_DIR:tuner_app>/bin/avrdude-windows"
                COMMAND ${CMAKE_COMMAND} -E copy_directory
                    "${TUNER_AVRDUDE_TOOLS_SRC}"
                    "$<TARGET_FILE_DIR:tuner_app>/bin/avrdude-windows"
                COMMENT "Bundling AVRDUDE tools with tuner_app")
        endif()

        if(TUNER_DFUUTIL_TOOLS_SRC)
            add_custom_command(TARGET tuner_app POST_BUILD
                COMMAND ${CMAKE_COMMAND} -E make_directory
                    "$<TARGET_FILE_DIR:tuner_app>/bin/dfuutil-windows"
                COMMAND ${CMAKE_COMMAND} -E copy_directory
                    "${TUNER_DFUUTIL_TOOLS_SRC}"
                    "$<TARGET_FILE_DIR:tuner_app>/bin/dfuutil-windows"
                COMMENT "Bundling DFU-UTIL tools with tuner_app")
        endif()
    endif()
    # Strip the auto-propagated Qt6::EntryPoint dependency that
    # Qt6::Core normally pulls in via its interface link list.
    set_property(TARGET tuner_app PROPERTY qt_no_entrypoint ON)
    if(TARGET Qt6::EntryPoint)
        # Remove Qt6::EntryPoint from the link interface that
        # Qt6::Core would otherwise force on us.
        get_target_property(_qt_core_libs Qt6::Core INTERFACE_LINK_LIBRARIES)
        if(_qt_core_libs)
            list(REMOVE_ITEM _qt_core_libs Qt6::EntryPoint
                                            "$<LINK_ONLY:Qt6::EntryPoint>")
            set_property(TARGET Qt6::Core PROPERTY INTERFACE_LINK_LIBRARIES "${_qt_core_libs}")
        endif()
    endif()

    # NOTE: tuner_app is built as a console-subsystem binary in v1 so
    # the standard `int main(int argc, char* argv[])` entry point in
    # app/main.cpp links cleanly under MinGW UCRT. The trade-off is a
    # console window appearing alongside the main app window when
    # launched from Explorer; this is fine for development and easily
    # fixed later by providing a WinMain shim alongside main(). Not
    # worth the complexity right now — the milestone is "Qt window
    # opens", not "release-quality launcher".
endif()
