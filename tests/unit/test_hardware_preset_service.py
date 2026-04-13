import pytest

from tuner.services.hardware_preset_service import HardwarePresetService


def test_ignition_presets_include_source_backed_ls_coils() -> None:
    presets = {preset.key: preset for preset in HardwarePresetService().ignition_presets()}

    assert "gm_ls_10457730" in presets
    assert presets["gm_ls_10457730"].running_dwell_ms == 5.0
    assert presets["gm_ls_10457730"].source_url == "https://documents.holley.com/199r10515rev3.pdf"
    assert "gm_d581_12558693" in presets
    assert presets["gm_d581_12558693"].running_dwell_ms == 3.5
    assert "square coil" in presets["gm_d581_12558693"].label.lower()
    assert "msextra" in presets["gm_d581_12558693"].source_url.lower()

    assert "single_coil_distributor" in presets
    assert "inferred" in presets["single_coil_distributor"].source_note.lower()


def test_wideband_presets_include_common_controller_equations() -> None:
    presets = {preset.key: preset for preset in HardwarePresetService().wideband_presets()}

    assert presets["spartan_2"].afr_equation == "AFR = volts * 2.0 + 10.0"
    assert "aem linear" in presets["aem_x_series"].reference_table_aliases
    assert "configurable" in presets["innovate_mtx_l"].source_note.lower()


def test_pressure_sensor_presets_include_map_oil_and_baro_ranges() -> None:
    service = HardwarePresetService()
    map_presets = {preset.key: preset for preset in service.map_sensor_presets()}
    oil_presets = {preset.key: preset for preset in service.oil_pressure_presets()}
    baro_presets = {preset.key: preset for preset in service.baro_sensor_presets()}

    assert map_presets["nxp_mpxh6250a_dropbear"].maximum_value == 250.0
    assert "dropbear" in map_presets["nxp_mpxh6250a_dropbear"].label.lower()
    assert map_presets["bosch_0261230119_3bar"].maximum_value == 300.0
    assert map_presets["bosch_0281006059_tmap"].minimum_value == 50.0
    assert oil_presets["bosch_pt_liquid_0261230340"].maximum_value == 10.0
    assert baro_presets["nxp_mpx4115_kp234_dropbear_baro"].minimum_value == 10.0
    assert baro_presets["nxp_mpx4115_kp234_dropbear_baro"].maximum_value == 121.0
    assert baro_presets["bmw_13628637900_tmap"].minimum_value == 20.0


def test_turbo_presets_include_maxpeedingrods_gt2871() -> None:
    presets = {preset.key: preset for preset in HardwarePresetService().turbo_presets()}

    assert presets["maxpeedingrods_gt2871"].compressor_inducer_mm == 49.2
    assert presets["maxpeedingrods_gt2871"].compressor_exducer_mm == 71.0
    assert presets["maxpeedingrods_gt2871"].turbine_ar == 0.64
    assert presets["maxpeedingrods_gt2871"].compressor_corrected_flow_lbmin == 35.0


def test_source_confidence_labels_distinguish_official_secondary_and_starter() -> None:
    service = HardwarePresetService()

    assert service.source_confidence_label(
        source_note="Holley LS harness instructions list 5.0 ms as the maximum dwell.",
        source_url="https://documents.holley.com/199r10515rev3.pdf",
    ) == "Official"
    assert service.source_confidence_label(
        source_note="NXP lists the MPXH6250A as a 20-250 kPa absolute pressure sensor.",
        source_url="https://www.nxp.com/assets/block-diagram/en/MPXx6250.pdf",
    ) == "Official"
    assert service.source_confidence_label(
        source_note="MS4X lists BMW M52TU OEM injectors at 237 cc/min.",
        source_url="https://www.ms4x.net/index.php?title=Fuel_Injector_Deadtimes",
    ) == "Trusted Secondary"
    assert service.source_confidence_label(
        source_note="MSExtra hardware manual recommends 3.5 ms dwell for GM truck coils.",
        source_url="https://www.msextra.com/doc/general/sparkout-v30.html",
    ) == "Trusted Secondary"
    assert service.source_confidence_label(
        source_note="Conservative inferred starter preset. Review against the coil datasheet.",
        source_url=None,
    ) == "Starter"


def test_injector_presets_include_curated_id_xds_data() -> None:
    presets = {preset.key: preset for preset in HardwarePresetService().injector_presets()}

    assert presets["id1050x_xds"].nominal_flow_ccmin == 1065.0
    assert presets["id1050x_xds"].dead_time_ms == 0.925
    assert presets["id1750x_xds"].dead_time_ms == 0.882
    assert presets["siemens_deka_60"].dead_time_ms == 0.43
    assert presets["siemens_deka_42_6900371"].dead_time_ms == 0.85
    assert presets["gm_ls3_ls7_12576341"].reference_pressure_psi == 43.0
    assert presets["bosch_green_giant_0280155968"].dead_time_ms == 0.704


def test_injector_presets_include_expanded_ms4x_catalog_entries() -> None:
    presets = {preset.key: preset for preset in HardwarePresetService().injector_presets()}

    assert presets["bmw_m52tu_oem"].nominal_flow_ccmin == 237.0
    assert presets["bmw_m54b30_oem"].dead_time_ms == 0.384
    assert presets["bosch_0280150945"].nominal_flow_ccmin == 337.0
    assert presets["bosch_0280150945"].voltage_offset_samples_ms[0].offset_ms == 3.33
    assert presets["bosch_0280158227"].dead_time_ms == 0.94
    assert presets["bosch_0280158227"].voltage_offset_samples_ms[-1].offset_ms == 0.85
    assert presets["bosch_0280158123_ev14_660"].nominal_flow_ccmin == 660.0
    assert presets["bosch_0280158123_ev14_660"].flow_samples_ccmin[2].flow_ccmin == 660.0
    assert presets["bosch_0280158124_ev14_410"].dead_time_ms == 0.49
    assert presets["bosch_0280158124_ev14_410"].voltage_offset_samples_ms[-1].offset_ms == 0.338
    assert presets["bosch_0280158040_980"].reference_pressure_psi == 50.76
    assert presets["bosch_0280158040_980"].flow_samples_ccmin[-1].flow_ccmin == 1310.0
    assert presets["siemens_deka_80_fi114991"].nominal_flow_ccmin == 875.0
    assert presets["siemens_deka_80_fi114991"].voltage_offset_samples_ms[0].offset_ms == 2.811
    assert presets["lucas_delphi_42_5_01d030b"].dead_time_ms == 0.58


def test_injector_presets_include_injector_rehab_common_street_and_swap_entries() -> None:
    service = HardwarePresetService()
    presets = {preset.key: preset for preset in service.injector_presets()}

    assert presets["bosch_0280150558"].nominal_flow_ccmin == 440.0
    assert presets["bosch_0280150558"].dead_time_ms == 0.352
    assert presets["bosch_0280158117_ev14_52lb"].nominal_flow_ccmin == 540.0
    assert presets["bosch_0280158117_ev14_52lb"].reference_pressure_psi == 43.5
    assert presets["bosch_0280158117_ev14_52lb"].dead_time_ms == 0.893
    assert service.injector_flow_for_pressure(presets["bosch_0280158117_ev14_52lb"], 50.76) == 580.0
    assert service.injector_dead_time_for_pressure(presets["bosch_0280158117_ev14_52lb"], 39.15) == 0.789
    assert service.injector_dead_time_for_pressure(
        presets["bosch_0280158117_ev14_52lb"], 50.03
    ) == pytest.approx(0.95, abs=0.001)
    assert service.injector_battery_correction_percentages(
        presets["bosch_0280158117_ev14_52lb"],
        [8.0, 10.0, 12.0, 13.0, 14.0, 15.0],
        43.5,
    ) == pytest.approx([276.806, 181.876, 131.939, 114.956, 100.0, 88.593], abs=0.01)
    assert presets["bosch_0280150558"].voltage_offset_samples_ms[4].offset_ms == 0.352
    assert presets["siemens_deka_72_3145"].dead_time_ms == 0.76
    assert presets["siemens_deka_83_3105"].nominal_flow_ccmin == 872.0
    assert presets["denso_23250_42010"].reference_pressure_psi == 32.63


def test_ms4x_injector_presets_with_table_data_compute_voltage_corrections() -> None:
    service = HardwarePresetService()
    presets = {preset.key: preset for preset in service.injector_presets()}

    correction = service.injector_battery_correction_percentages(
        presets["bosch_0280158123_ev14_660"],
        [8.0, 10.0, 12.0, 14.0, 16.0],
        50.76,
    )

    assert correction == pytest.approx([336.492, 216.331, 147.782, 100.0, 81.855], abs=0.01)


# ---------------------------------------------------------------------------
# New MAP sensor presets
# ---------------------------------------------------------------------------

def test_gm_3bar_map_preset_exists() -> None:
    svc = HardwarePresetService()
    keys = [p.key for p in svc.map_sensor_presets()]
    assert "gm_3bar_12592525" in keys


def test_aem_35bar_map_preset_exists() -> None:
    svc = HardwarePresetService()
    keys = [p.key for p in svc.map_sensor_presets()]
    assert "aem_35bar_30_2130_50" in keys


def test_aem_4bar_map_preset_exists() -> None:
    svc = HardwarePresetService()
    keys = [p.key for p in svc.map_sensor_presets()]
    assert "aem_4bar_30_2130_75" in keys


def test_gm_3bar_map_range() -> None:
    svc = HardwarePresetService()
    presets = {p.key: p for p in svc.map_sensor_presets()}
    gm = presets["gm_3bar_12592525"]
    assert gm.maximum_value >= 300.0
    assert gm.units == "kPa"


# ---------------------------------------------------------------------------
# New wideband controller presets
# ---------------------------------------------------------------------------

def test_zeitronix_wideband_preset_exists() -> None:
    svc = HardwarePresetService()
    keys = [p.key for p in svc.wideband_presets()]
    assert "zeitronix_zt2_zt3" in keys


def test_plx_m300_wideband_preset_exists() -> None:
    svc = HardwarePresetService()
    keys = [p.key for p in svc.wideband_presets()]
    assert "plx_m300" in keys


def test_spartan_lambda_wideband_preset_exists() -> None:
    svc = HardwarePresetService()
    keys = [p.key for p in svc.wideband_presets()]
    assert "14point7_spartan_lambda" in keys


# ---------------------------------------------------------------------------
# New ignition coil presets
# ---------------------------------------------------------------------------

def test_toyota_cop_ignition_preset_exists() -> None:
    svc = HardwarePresetService()
    keys = [p.key for p in svc.ignition_presets()]
    assert "toyota_cop_90919_02248" in keys


def test_ford_cop_ignition_preset_exists() -> None:
    svc = HardwarePresetService()
    keys = [p.key for p in svc.ignition_presets()]
    assert "ford_cop_bim_coil" in keys


def test_generic_wasted_spark_ignition_preset_exists() -> None:
    svc = HardwarePresetService()
    keys = [p.key for p in svc.ignition_presets()]
    assert "generic_wasted_spark" in keys
