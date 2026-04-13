from __future__ import annotations

import json
from pathlib import Path

from tuner.domain.generator_context import ForcedInductionTopology, SuperchargerType
from tuner.domain.operator_engine_context import CalibrationIntent, OperatorEngineContext


class OperatorEngineContextService:
    """Session-level store for operator-provided engine facts.

    These are facts the operator knows about the engine that are not held in
    the ECU (e.g. displacement, compression ratio).  The service is mutable
    within a session; nothing is persisted to disk automatically.

    Usage
    -----
    The presenter calls :meth:`get` to embed the context in snapshots that feed
    the required fuel calculator and base tune readiness cards.  UI widgets call
    :meth:`update` when the operator changes a value.
    """

    def __init__(self) -> None:
        self._context = OperatorEngineContext()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self) -> OperatorEngineContext:
        """Return the current operator engine context."""
        return self._context

    # ------------------------------------------------------------------
    # Write (returns new immutable context; does not raise on unknown fields)
    # ------------------------------------------------------------------

    def update(  # noqa: PLR0913
        self,
        *,
        displacement_cc: float | None = ...,  # type: ignore[assignment]
        cylinder_count: int | None = ...,  # type: ignore[assignment]
        compression_ratio: float | None = ...,  # type: ignore[assignment]
        cam_duration_deg: float | None = ...,  # type: ignore[assignment]
        head_flow_class: str | None = ...,  # type: ignore[assignment]
        intake_manifold_style: str | None = ...,  # type: ignore[assignment]
        base_fuel_pressure_psi: float | None = ...,  # type: ignore[assignment]
        injector_pressure_model: str | None = ...,  # type: ignore[assignment]
        secondary_injector_reference_pressure_psi: float | None = ...,  # type: ignore[assignment]
        injector_preset_key: str | None = ...,  # type: ignore[assignment]
        ignition_preset_key: str | None = ...,  # type: ignore[assignment]
        wideband_preset_key: str | None = ...,  # type: ignore[assignment]
        wideband_reference_table_label: str | None = ...,  # type: ignore[assignment]
        turbo_preset_key: str | None = ...,  # type: ignore[assignment]
        injector_characterization: str | None = ...,  # type: ignore[assignment]
        calibration_intent: CalibrationIntent | None = ...,  # type: ignore[assignment]
        # Induction
        forced_induction_topology: ForcedInductionTopology | None = ...,  # type: ignore[assignment]
        supercharger_type: SuperchargerType | None = ...,  # type: ignore[assignment]
        boost_target_kpa: float | None = ...,  # type: ignore[assignment]
        intercooler_present: bool | None = ...,  # type: ignore[assignment]
        # Compressor data
        compressor_corrected_flow_lbmin: float | None = ...,  # type: ignore[assignment]
        compressor_pressure_ratio: float | None = ...,  # type: ignore[assignment]
        compressor_inducer_mm: float | None = ...,  # type: ignore[assignment]
        compressor_exducer_mm: float | None = ...,  # type: ignore[assignment]
        compressor_ar: float | None = ...,  # type: ignore[assignment]
    ) -> OperatorEngineContext:
        """Update one or more fields and return the new context.

        Use the sentinel ``...`` (Ellipsis) to leave a field unchanged — this is
        the default for every parameter so callers only pass what they want to
        change.
        """
        ctx = self._context
        topology_value = (
            ctx.forced_induction_topology
            if forced_induction_topology is ...
            else self._coerce_topology(forced_induction_topology)
        )
        supercharger_value = (
            ctx.supercharger_type
            if supercharger_type is ...
            else self._coerce_supercharger_type(supercharger_type)
        )
        new_displacement = ctx.displacement_cc if displacement_cc is ... else displacement_cc
        new_cylinders = ctx.cylinder_count if cylinder_count is ... else cylinder_count
        new_compression = ctx.compression_ratio if compression_ratio is ... else compression_ratio
        new_cam = ctx.cam_duration_deg if cam_duration_deg is ... else cam_duration_deg
        new_head_flow_class = ctx.head_flow_class if head_flow_class is ... else head_flow_class
        new_manifold_style = ctx.intake_manifold_style if intake_manifold_style is ... else intake_manifold_style
        new_base_pressure = ctx.base_fuel_pressure_psi if base_fuel_pressure_psi is ... else base_fuel_pressure_psi
        new_pressure_model = ctx.injector_pressure_model if injector_pressure_model is ... else injector_pressure_model
        new_secondary_pressure = (
            ctx.secondary_injector_reference_pressure_psi
            if secondary_injector_reference_pressure_psi is ...
            else secondary_injector_reference_pressure_psi
        )
        new_injector_preset = ctx.injector_preset_key if injector_preset_key is ... else injector_preset_key
        new_ignition_preset = ctx.ignition_preset_key if ignition_preset_key is ... else ignition_preset_key
        new_wideband_preset = ctx.wideband_preset_key if wideband_preset_key is ... else wideband_preset_key
        new_wideband_reference = (
            ctx.wideband_reference_table_label
            if wideband_reference_table_label is ...
            else wideband_reference_table_label
        )
        new_turbo_preset = ctx.turbo_preset_key if turbo_preset_key is ... else turbo_preset_key
        new_injector_characterization = (
            ctx.injector_characterization if injector_characterization is ... else injector_characterization
        )
        new_intent = (
            ctx.calibration_intent
            if calibration_intent is ...
            else self._coerce_calibration_intent(calibration_intent)
        )
        new_topology = topology_value or ForcedInductionTopology.NA
        new_sc_type = supercharger_value
        new_boost = ctx.boost_target_kpa if boost_target_kpa is ... else boost_target_kpa
        new_intercooler = ctx.intercooler_present if intercooler_present is ... else bool(intercooler_present)
        new_flow = (
            ctx.compressor_corrected_flow_lbmin
            if compressor_corrected_flow_lbmin is ...
            else compressor_corrected_flow_lbmin
        )
        new_pr = (
            ctx.compressor_pressure_ratio
            if compressor_pressure_ratio is ...
            else compressor_pressure_ratio
        )
        new_inducer = ctx.compressor_inducer_mm if compressor_inducer_mm is ... else compressor_inducer_mm
        new_exducer = ctx.compressor_exducer_mm if compressor_exducer_mm is ... else compressor_exducer_mm
        new_ar = ctx.compressor_ar if compressor_ar is ... else compressor_ar
        self._context = OperatorEngineContext(
            displacement_cc=new_displacement,
            cylinder_count=new_cylinders,
            compression_ratio=new_compression,
            cam_duration_deg=new_cam,
            head_flow_class=new_head_flow_class,
            intake_manifold_style=new_manifold_style,
            base_fuel_pressure_psi=new_base_pressure,
            injector_pressure_model=new_pressure_model,
            secondary_injector_reference_pressure_psi=new_secondary_pressure,
            injector_preset_key=new_injector_preset,
            ignition_preset_key=new_ignition_preset,
            wideband_preset_key=new_wideband_preset,
            wideband_reference_table_label=new_wideband_reference,
            turbo_preset_key=new_turbo_preset,
            injector_characterization=new_injector_characterization,
            calibration_intent=new_intent,
            forced_induction_topology=new_topology,
            supercharger_type=new_sc_type,
            boost_target_kpa=new_boost,
            intercooler_present=new_intercooler,
            compressor_corrected_flow_lbmin=new_flow,
            compressor_pressure_ratio=new_pr,
            compressor_inducer_mm=new_inducer,
            compressor_exducer_mm=new_exducer,
            compressor_ar=new_ar,
        )
        return self._context

    @staticmethod
    def _coerce_calibration_intent(
        value: CalibrationIntent | str | None,
    ) -> CalibrationIntent:
        if value is None:
            return CalibrationIntent.FIRST_START
        if isinstance(value, CalibrationIntent):
            return value
        try:
            return CalibrationIntent(str(value))
        except ValueError:
            return CalibrationIntent.FIRST_START

    @staticmethod
    def _coerce_topology(
        value: ForcedInductionTopology | str | None,
    ) -> ForcedInductionTopology | None:
        if value is None or isinstance(value, ForcedInductionTopology):
            return value
        try:
            return ForcedInductionTopology(str(value))
        except ValueError:
            return ForcedInductionTopology.NA

    @staticmethod
    def _coerce_supercharger_type(
        value: SuperchargerType | str | None,
    ) -> SuperchargerType | None:
        if value is None or isinstance(value, SuperchargerType):
            return value
        try:
            return SuperchargerType(str(value))
        except ValueError:
            return None

    def clear(self) -> None:
        """Reset the context to all-None defaults."""
        self._context = OperatorEngineContext()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: Path) -> None:
        """Serialise the current context to *path* as JSON.

        Only non-None / non-default fields are written so the file stays
        readable and small.  Silently ignores write errors so a missing or
        read-only directory never crashes the application.
        """
        ctx = self._context
        data: dict[str, object] = {}
        if ctx.displacement_cc is not None:
            data["displacement_cc"] = ctx.displacement_cc
        if ctx.cylinder_count is not None:
            data["cylinder_count"] = ctx.cylinder_count
        if ctx.compression_ratio is not None:
            data["compression_ratio"] = ctx.compression_ratio
        if ctx.cam_duration_deg is not None:
            data["cam_duration_deg"] = ctx.cam_duration_deg
        if ctx.head_flow_class:
            data["head_flow_class"] = ctx.head_flow_class
        if ctx.intake_manifold_style:
            data["intake_manifold_style"] = ctx.intake_manifold_style
        if ctx.base_fuel_pressure_psi is not None:
            data["base_fuel_pressure_psi"] = ctx.base_fuel_pressure_psi
        if ctx.injector_pressure_model:
            data["injector_pressure_model"] = ctx.injector_pressure_model
        if ctx.secondary_injector_reference_pressure_psi is not None:
            data["secondary_injector_reference_pressure_psi"] = ctx.secondary_injector_reference_pressure_psi
        if ctx.injector_preset_key:
            data["injector_preset_key"] = ctx.injector_preset_key
        if ctx.ignition_preset_key:
            data["ignition_preset_key"] = ctx.ignition_preset_key
        if ctx.wideband_preset_key:
            data["wideband_preset_key"] = ctx.wideband_preset_key
        if ctx.wideband_reference_table_label:
            data["wideband_reference_table_label"] = ctx.wideband_reference_table_label
        if ctx.turbo_preset_key:
            data["turbo_preset_key"] = ctx.turbo_preset_key
        if ctx.injector_characterization:
            data["injector_characterization"] = ctx.injector_characterization
        _ci = self._coerce_calibration_intent(ctx.calibration_intent)
        if _ci != CalibrationIntent.FIRST_START:
            data["calibration_intent"] = _ci.value
        if ctx.forced_induction_topology != ForcedInductionTopology.NA:
            data["forced_induction_topology"] = ctx.forced_induction_topology.value
        if ctx.supercharger_type is not None:
            data["supercharger_type"] = ctx.supercharger_type.value
        if ctx.boost_target_kpa is not None:
            data["boost_target_kpa"] = ctx.boost_target_kpa
        if ctx.intercooler_present:
            data["intercooler_present"] = True
        if ctx.compressor_corrected_flow_lbmin is not None:
            data["compressor_corrected_flow_lbmin"] = ctx.compressor_corrected_flow_lbmin
        if ctx.compressor_pressure_ratio is not None:
            data["compressor_pressure_ratio"] = ctx.compressor_pressure_ratio
        if ctx.compressor_inducer_mm is not None:
            data["compressor_inducer_mm"] = ctx.compressor_inducer_mm
        if ctx.compressor_exducer_mm is not None:
            data["compressor_exducer_mm"] = ctx.compressor_exducer_mm
        if ctx.compressor_ar is not None:
            data["compressor_ar"] = ctx.compressor_ar
        try:
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:
            pass

    def load_from(self, path: Path) -> None:
        """Load context from a JSON file written by :meth:`save`.

        Missing keys keep their default values.  Unknown keys and parse errors
        are silently ignored — a corrupt sidecar file should not prevent the
        project from opening.
        """
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        intent_map = {item.value: item for item in CalibrationIntent}
        topology_map = {item.value: item for item in ForcedInductionTopology}
        sc_map = {item.value: item for item in SuperchargerType}

        def _float(key: str) -> float | None:
            v = data.get(key)
            return float(v) if v is not None else None

        def _int(key: str) -> int | None:
            v = data.get(key)
            return int(v) if v is not None else None

        self._context = OperatorEngineContext(
            displacement_cc=_float("displacement_cc"),
            cylinder_count=_int("cylinder_count"),
            compression_ratio=_float("compression_ratio"),
            cam_duration_deg=_float("cam_duration_deg"),
            head_flow_class=data.get("head_flow_class"),
            intake_manifold_style=data.get("intake_manifold_style"),
            base_fuel_pressure_psi=_float("base_fuel_pressure_psi"),
            injector_pressure_model=data.get("injector_pressure_model"),
            secondary_injector_reference_pressure_psi=_float("secondary_injector_reference_pressure_psi"),
            injector_preset_key=data.get("injector_preset_key"),
            ignition_preset_key=data.get("ignition_preset_key"),
            wideband_preset_key=data.get("wideband_preset_key"),
            wideband_reference_table_label=data.get("wideband_reference_table_label"),
            turbo_preset_key=data.get("turbo_preset_key"),
            injector_characterization=data.get("injector_characterization"),
            calibration_intent=intent_map.get(data.get("calibration_intent", ""), CalibrationIntent.FIRST_START),
            forced_induction_topology=topology_map.get(data.get("forced_induction_topology", ""), ForcedInductionTopology.NA),
            supercharger_type=sc_map.get(data.get("supercharger_type", ""), None),
            boost_target_kpa=_float("boost_target_kpa"),
            intercooler_present=bool(data.get("intercooler_present", False)),
            compressor_corrected_flow_lbmin=_float("compressor_corrected_flow_lbmin"),
            compressor_pressure_ratio=_float("compressor_pressure_ratio"),
            compressor_inducer_mm=_float("compressor_inducer_mm"),
            compressor_exducer_mm=_float("compressor_exducer_mm"),
            compressor_ar=_float("compressor_ar"),
        )
