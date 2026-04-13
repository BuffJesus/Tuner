from pathlib import Path

from tuner.services.operator_engine_context_service import OperatorEngineContextService


def test_operator_engine_context_persists_hardware_profile_fields(tmp_path: Path) -> None:
    service = OperatorEngineContextService()
    service.update(
        base_fuel_pressure_psi=58.0,
        injector_preset_key="id1050x_xds",
        ignition_preset_key="gm_ls_19005218",
        wideband_preset_key="aem_x_series",
        wideband_reference_table_label="AEM Linear AEM-30-42xx",
        turbo_preset_key="maxpeedingrods_gt2871",
        head_flow_class="mild_ported",
        intake_manifold_style="itb",
        injector_pressure_model="vacuum_referenced",
        secondary_injector_reference_pressure_psi=58.0,
        injector_characterization="full_characterization",
    )

    path = tmp_path / "engine_context.json"
    service.save(path)

    restored = OperatorEngineContextService()
    restored.load_from(path)
    context = restored.get()

    assert context.base_fuel_pressure_psi == 58.0
    assert context.injector_preset_key == "id1050x_xds"
    assert context.ignition_preset_key == "gm_ls_19005218"
    assert context.wideband_preset_key == "aem_x_series"
    assert context.wideband_reference_table_label == "AEM Linear AEM-30-42xx"
    assert context.turbo_preset_key == "maxpeedingrods_gt2871"
    assert context.head_flow_class == "mild_ported"
    assert context.intake_manifold_style == "itb"
    assert context.injector_pressure_model == "vacuum_referenced"
    assert context.secondary_injector_reference_pressure_psi == 58.0
    assert context.injector_characterization == "full_characterization"
