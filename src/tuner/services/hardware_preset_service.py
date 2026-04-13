from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(slots=True, frozen=True)
class IgnitionHardwarePreset:
    key: str
    label: str
    description: str
    running_dwell_ms: float
    cranking_dwell_ms: float
    source_note: str
    source_url: str | None = None


@dataclass(slots=True, frozen=True)
class InjectorHardwarePreset:
    key: str
    label: str
    description: str
    nominal_flow_ccmin: float
    dead_time_ms: float | None
    reference_pressure_psi: float
    source_note: str
    source_url: str | None = None
    flow_samples_ccmin: tuple["InjectorFlowSample", ...] = ()
    voltage_offset_samples_ms: tuple["InjectorVoltageOffsetSample", ...] = ()
    dead_time_pressure_compensation: tuple["InjectorPressureCompensationSample", ...] = ()


@dataclass(slots=True, frozen=True)
class InjectorFlowSample:
    differential_pressure_psi: float
    flow_ccmin: float


@dataclass(slots=True, frozen=True)
class InjectorVoltageOffsetSample:
    battery_voltage: float
    offset_ms: float


@dataclass(slots=True, frozen=True)
class InjectorPressureCompensationSample:
    differential_pressure_psi: float
    multiplier: float


@dataclass(slots=True, frozen=True)
class WidebandHardwarePreset:
    key: str
    label: str
    description: str
    afr_equation: str
    lambda_equation: str
    reference_table_aliases: tuple[str, ...] = ()
    source_note: str = ""
    source_url: str | None = None


@dataclass(slots=True, frozen=True)
class PressureSensorPreset:
    key: str
    label: str
    description: str
    minimum_value: float
    maximum_value: float
    units: str
    source_note: str
    source_url: str | None = None


@dataclass(slots=True, frozen=True)
class TurboHardwarePreset:
    key: str
    label: str
    description: str
    compressor_corrected_flow_lbmin: float | None
    compressor_pressure_ratio: float | None
    compressor_inducer_mm: float | None
    compressor_exducer_mm: float | None
    compressor_ar: float | None
    turbine_inducer_mm: float | None
    turbine_exducer_mm: float | None
    turbine_ar: float | None
    source_note: str
    source_url: str | None = None


class HardwarePresetService:
    """Small curated catalog of safe starter presets for common hardware.

    Presets are intentionally conservative and explicit. They should only cover
    hardware for which we have a defensible source or a clearly-marked inferred
    starter value.
    """

    def ignition_presets(self) -> tuple[IgnitionHardwarePreset, ...]:
        return (
            IgnitionHardwarePreset(
                key="single_coil_distributor",
                label="Single Coil / Distributor",
                description="Conservative starter dwell for a basic inductive single-coil distributor setup.",
                running_dwell_ms=3.5,
                cranking_dwell_ms=4.5,
                source_note="Conservative inferred starter preset. Review against the ignition module or coil datasheet.",
            ),
            IgnitionHardwarePreset(
                key="gm_ls_10457730",
                label="GM LS Coil PN 10457730",
                description="Holley-tested maximum dwell for this GM LS coil family.",
                running_dwell_ms=5.0,
                cranking_dwell_ms=5.0,
                source_note="Holley LS harness instructions list 5.0 ms as the maximum dwell for GM coil PN 10457730.",
                source_url="https://documents.holley.com/199r10515rev3.pdf",
            ),
            IgnitionHardwarePreset(
                key="gm_ls_19005218",
                label="GM LS Coil PN 19005218",
                description="Holley-tested maximum dwell for this GM LS coil family.",
                running_dwell_ms=4.5,
                cranking_dwell_ms=4.5,
                source_note="Holley LS harness instructions list 4.5 ms as the maximum dwell for GM coil PN 19005218.",
                source_url="https://documents.holley.com/199r10515rev3.pdf",
            ),
            IgnitionHardwarePreset(
                key="gm_ls_12573190_family",
                label="GM LS Coil PN 12573190 / 12611424 / 12570616",
                description="Holley-tested maximum dwell for later GM LS coil part numbers in this family.",
                running_dwell_ms=3.5,
                cranking_dwell_ms=3.5,
                source_note="Holley LS harness instructions list 3.5 ms as the maximum dwell for these GM coil part numbers.",
                source_url="https://documents.holley.com/199r10515rev3.pdf",
            ),
            IgnitionHardwarePreset(
                key="gm_d581_12558693",
                label="GM D581 / PN 12558693 Square Coil",
                description="Classic GM truck square coil starter preset for remote-mount LS and swap applications.",
                running_dwell_ms=3.5,
                cranking_dwell_ms=3.5,
                source_note="The MSExtra hardware manual recommends 3.5 ms dwell for GM truck coils, which aligns well with the classic D581 / GM 12558693 square-coil family as a conservative starter value.",
                source_url="https://www.msextra.com/doc/general/sparkout-v30.html",
            ),
            IgnitionHardwarePreset(
                key="toyota_cop_90919_02248",
                label="Toyota COP 90919-02248 (1ZZ / 2ZZ / 1NZ family)",
                description="Common Toyota coil-on-plug used in 1ZZ, 2ZZ, and 1NZ engines, widely reused in swap projects.",
                running_dwell_ms=3.0,
                cranking_dwell_ms=4.0,
                source_note="MSExtra and community resources list 3.0 ms running dwell and 4.0 ms cranking dwell as a conservative starter for the Toyota 90919-02248 COP family.",
                source_url="https://www.msextra.com/doc/general/sparkout-v30.html",
            ),
            IgnitionHardwarePreset(
                key="ford_cop_bim_coil",
                label="Ford COPe / BIM-style COP (DG508 / FD487)",
                description="Common Ford coil-on-plug used in Modular V8 and some inline applications, reused in many swap builds.",
                running_dwell_ms=3.0,
                cranking_dwell_ms=4.0,
                source_note="MSExtra community resources list 3.0 ms running dwell for Ford Modular COP / DG508 / FD487 as a conservative starting point.",
                source_url="https://www.msextra.com/doc/general/sparkout-v30.html",
            ),
            IgnitionHardwarePreset(
                key="generic_wasted_spark",
                label="Generic Wasted-Spark Coil Pack",
                description="Conservative starter preset for a typical wasted-spark coil pack with an internal ignitor.",
                running_dwell_ms=3.5,
                cranking_dwell_ms=4.5,
                source_note="Conservative inferred starter preset for a typical wasted-spark coil pack. Review against the coil module datasheet before extended key-on testing.",
            ),
        )

    @staticmethod
    def source_confidence_label(*, source_note: str, source_url: str | None) -> str:
        note = source_note.lower()
        if "inferred" in note or source_url is None:
            return "Starter"
        domain = urlparse(source_url).netloc.lower()
        if any(
            official in domain
            for official in (
                "injectordynamics.com",
                "chevrolet.com",
                "documents.holley.com",
                "dtec.net.au",
                "nxp.com",
            )
        ):
            return "Official"
        if any(secondary in domain for secondary in ("ms4x.net", "injector-rehab.com", "mpsracing.com", "msextra.com")):
            return "Trusted Secondary"
        return "Sourced"

    def injector_presets(self) -> tuple[InjectorHardwarePreset, ...]:
        return (
            InjectorHardwarePreset(
                key="bmw_m52tu_oem",
                label="BMW M52TU OEM",
                description="Common BMW OEM injector from M52TU engines.",
                nominal_flow_ccmin=237.0,
                dead_time_ms=0.55,
                reference_pressure_psi=50.76,
                source_note="MS4X lists BMW M52TU OEM injectors at 237 cc/min and 0.55 ms offset at 14 V, 3.5 bar.",
                source_url="https://www.ms4x.net/index.php?title=Fuel_Injector_Deadtimes",
            ),
            InjectorHardwarePreset(
                key="bmw_m54b30_oem",
                label="BMW M54B30 OEM",
                description="Common BMW OEM injector from M54B30 engines.",
                nominal_flow_ccmin=254.0,
                dead_time_ms=0.384,
                reference_pressure_psi=50.76,
                source_note="MS4X lists BMW M54B30 OEM injectors at 254 cc/min and 0.384 ms offset at 14 V, 3.5 bar.",
                source_url="https://www.ms4x.net/index.php?title=Fuel_Injector_Deadtimes",
            ),
            InjectorHardwarePreset(
                key="alpina_b3s_pink_top",
                label="Alpina B3S / Bosch 0280156370 Pink Top",
                description="Alpina pink-top Bosch injector used as a mild OEM-plus upgrade.",
                nominal_flow_ccmin=249.0,
                dead_time_ms=0.416,
                reference_pressure_psi=50.76,
                source_note="MS4X lists Bosch 0280156370 / Alpina B3S pink tops at 249 cc/min and 0.416 ms offset at 14 V, 3.5 bar.",
                source_url="https://www.ms4x.net/index.php?title=Fuel_Injector_Deadtimes",
            ),
            InjectorHardwarePreset(
                key="bosch_0280150945",
                label="Bosch 0280150945 Red Top",
                description="Common older Bosch red-top injector used in many Ford and turbo builds.",
                nominal_flow_ccmin=337.0,
                dead_time_ms=0.38,
                reference_pressure_psi=50.76,
                source_note="MS4X lists Bosch 0280150945 at 337 cc/min and 0.38 ms offset at 14 V, 3.5 bar.",
                source_url="https://www.ms4x.net/index.php?title=Fuel_Injector_Deadtimes",
                voltage_offset_samples_ms=(
                    InjectorVoltageOffsetSample(6.0, 3.33),
                    InjectorVoltageOffsetSample(8.0, 1.41),
                    InjectorVoltageOffsetSample(10.0, 0.86),
                    InjectorVoltageOffsetSample(12.0, 0.58),
                    InjectorVoltageOffsetSample(14.0, 0.38),
                    InjectorVoltageOffsetSample(16.0, 0.26),
                ),
            ),
            InjectorHardwarePreset(
                key="bosch_0280158227",
                label="Bosch 0280158227",
                description="Later Bosch EV14-style Ford injector often used in aftermarket conversions.",
                nominal_flow_ccmin=435.0,
                dead_time_ms=0.94,
                reference_pressure_psi=50.76,
                source_note="MS4X lists Bosch 0280158227 at 435 cc/min and 0.94 ms offset at 14 V, 3.5 bar.",
                source_url="https://www.ms4x.net/index.php?title=Fuel_Injector_Deadtimes",
                voltage_offset_samples_ms=(
                    InjectorVoltageOffsetSample(6.0, 4.91),
                    InjectorVoltageOffsetSample(8.0, 2.35),
                    InjectorVoltageOffsetSample(10.0, 1.62),
                    InjectorVoltageOffsetSample(12.0, 1.19),
                    InjectorVoltageOffsetSample(14.0, 0.94),
                    InjectorVoltageOffsetSample(16.0, 0.85),
                ),
            ),
            InjectorHardwarePreset(
                key="bosch_0280150558",
                label='Bosch 0280150558 "42 lb/hr"',
                description="Very common older Bosch EV1 42 lb/hr injector used in many turbo street and swap builds.",
                nominal_flow_ccmin=440.0,
                dead_time_ms=0.352,
                reference_pressure_psi=43.5,
                source_note="Injector-Rehab flow data lists Bosch 0280150558 at 440 cc/min at 3 bar. MS4X notes the same extrapolated voltage-offset table used successfully for Bosch 0280155968 also applies to Bosch 0280150558 at 3.5 bar; the dead time stored here is the 14 V value from that table scaled to the preset's 3 bar reference pressure by square-root pressure ratio.",
                source_url="https://www.ms4x.net/index.php?title=Fuel_Injector_Deadtimes",
                flow_samples_ccmin=(
                    InjectorFlowSample(43.5, 440.0),
                    InjectorFlowSample(50.76, 475.0),
                ),
                voltage_offset_samples_ms=(
                    InjectorVoltageOffsetSample(6.0, 3.552),
                    InjectorVoltageOffsetSample(8.0, 1.472),
                    InjectorVoltageOffsetSample(10.0, 0.896),
                    InjectorVoltageOffsetSample(12.0, 0.608),
                    InjectorVoltageOffsetSample(14.0, 0.352),
                    InjectorVoltageOffsetSample(16.0, 0.224),
                ),
            ),
            InjectorHardwarePreset(
                key="bosch_0280158117_ev14_52lb",
                label='Bosch EV14 52 lb/hr (0280158117)',
                description="Bosch EV14 / GT500-style injector with part-number-specific flow data and Ford/Bosch offset compensation tables.",
                nominal_flow_ccmin=540.0,
                dead_time_ms=0.893,
                reference_pressure_psi=43.5,
                source_note="Flow samples come from the 0280158117 characterization PDF mirrored by Finjector; voltage offset and pressure compensation come from the Ford/Bosch calibration summary mirrored in the LinkECU thread for this exact part number. The single dead-time value is the derived 14 V estimate at 43.5 psi.",
                source_url="https://forums.linkecu.com/topic/7153-bosch-ev14-550cc-settings/",
                flow_samples_ccmin=(
                    InjectorFlowSample(36.26, 480.0),
                    InjectorFlowSample(43.5, 540.0),
                    InjectorFlowSample(50.76, 580.0),
                    InjectorFlowSample(58.02, 620.0),
                    InjectorFlowSample(65.27, 650.0),
                    InjectorFlowSample(72.52, 690.0),
                    InjectorFlowSample(79.78, 740.0),
                    InjectorFlowSample(87.03, 770.0),
                ),
                voltage_offset_samples_ms=(
                    InjectorVoltageOffsetSample(6.0, 5.202),
                    InjectorVoltageOffsetSample(8.0, 2.184),
                    InjectorVoltageOffsetSample(10.0, 1.435),
                    InjectorVoltageOffsetSample(11.0, 1.210),
                    InjectorVoltageOffsetSample(12.0, 1.041),
                    InjectorVoltageOffsetSample(13.0, 0.907),
                    InjectorVoltageOffsetSample(14.0, 0.789),
                    InjectorVoltageOffsetSample(15.0, 0.699),
                ),
                dead_time_pressure_compensation=(
                    InjectorPressureCompensationSample(20.01, 0.7149),
                    InjectorPressureCompensationSample(30.02, 1.0564),
                    InjectorPressureCompensationSample(39.15, 1.0000),
                    InjectorPressureCompensationSample(44.95, 1.1768),
                    InjectorPressureCompensationSample(50.03, 1.2040),
                    InjectorPressureCompensationSample(54.96, 1.2179),
                    InjectorPressureCompensationSample(60.03, 1.1638),
                ),
            ),
            InjectorHardwarePreset(
                key="id1050x_xds",
                label="Injector Dynamics ID1050x / XDS",
                description="Published nominal flow and 14 V offset at 43.5 psi / 3 bar.",
                nominal_flow_ccmin=1065.0,
                dead_time_ms=0.925,
                reference_pressure_psi=43.5,
                source_note="Injector Dynamics dynamic flow data publishes 1065 cc/min nominal flow and 925 us offset at 14 V.",
                source_url="https://www.mpsracing.com/images/products/InjectorDynamics/id1050.pdf",
            ),
            InjectorHardwarePreset(
                key="id1300x_xds",
                label="Injector Dynamics ID1300x / XDS",
                description="Published nominal flow and 14 V offset at 43.5 psi / 3 bar.",
                nominal_flow_ccmin=1335.0,
                dead_time_ms=1.005,
                reference_pressure_psi=43.5,
                source_note="Injector Dynamics product data publishes 1335 cc/min nominal flow and 1005 us offset at 14 V.",
                source_url="https://injectordynamics.com/injectors/id1300-xds/",
            ),
            InjectorHardwarePreset(
                key="id1750x_xds",
                label="Injector Dynamics ID1750x / XDS",
                description="Published nominal flow and 14 V offset at 43.5 psi / 3 bar.",
                nominal_flow_ccmin=1728.0,
                dead_time_ms=0.882,
                reference_pressure_psi=43.5,
                source_note="Injector Dynamics product data publishes 1728 cc/min nominal flow and 882 us offset at 14 V.",
                source_url="https://injectordynamics.com/injectors/id1750x-xds/",
            ),
            InjectorHardwarePreset(
                key="siemens_deka_60",
                label='Siemens Deka IV "60 lb/hr"',
                description="Common high-impedance street/boost injector with published offset data.",
                nominal_flow_ccmin=630.0,
                dead_time_ms=0.43,
                reference_pressure_psi=39.15,
                source_note='MS4X deadtime reference lists Siemens Deka FI114961 / 107961 at 630 cc/min with 0.43 ms offset at 14 V and 39.15 psi.',
                source_url="https://www.ms4x.net/index.php?title=Fuel_Injector_Deadtimes",
                voltage_offset_samples_ms=(
                    InjectorVoltageOffsetSample(6.0, 2.60),
                    InjectorVoltageOffsetSample(8.0, 1.45),
                    InjectorVoltageOffsetSample(10.0, 0.94),
                    InjectorVoltageOffsetSample(12.0, 0.64),
                    InjectorVoltageOffsetSample(14.0, 0.43),
                    InjectorVoltageOffsetSample(16.0, 0.26),
                ),
            ),
            InjectorHardwarePreset(
                key="siemens_deka_42_6900371",
                label='Siemens Deka 6900371 "42 lb/hr"',
                description="Common older EV1-style 42 lb injector used in Volvo and many turbo street builds.",
                nominal_flow_ccmin=475.0,
                dead_time_ms=0.85,
                reference_pressure_psi=50.76,
                source_note='MS4X deadtime reference lists Siemens Deka 6900371 at 475 cc/min and 0.85 ms offset at 14 V, 3.5 bar.',
                source_url="https://www.ms4x.net/index.php?title=Fuel_Injector_Deadtimes",
                flow_samples_ccmin=(
                    InjectorFlowSample(43.5, 440.0),
                    InjectorFlowSample(50.76, 475.0),
                    InjectorFlowSample(72.52, 568.0),
                ),
                voltage_offset_samples_ms=(
                    InjectorVoltageOffsetSample(6.0, 4.44),
                    InjectorVoltageOffsetSample(8.0, 1.88),
                    InjectorVoltageOffsetSample(10.0, 1.15),
                    InjectorVoltageOffsetSample(12.0, 0.94),
                    InjectorVoltageOffsetSample(14.0, 0.85),
                    InjectorVoltageOffsetSample(16.0, 0.77),
                ),
            ),
            InjectorHardwarePreset(
                key="siemens_deka_72_3145",
                label='Siemens Deka 3145 "72 lb/hr"',
                description="Common Siemens Deka high-impedance injector for moderate to high boost street builds.",
                nominal_flow_ccmin=756.0,
                dead_time_ms=0.76,
                reference_pressure_psi=43.5,
                source_note='Injector-Rehab publishes Siemens 3145 at 756 cc/min on the flow-rate page and 0.76 ms lag at 14 V on the lag-time page. Their lag article notes these are broad historical averages, so treat as a strong starter value rather than exact characterization.',
                source_url="https://injector-rehab.com/knowledge-base/fuel-injector-lag-times/",
            ),
            InjectorHardwarePreset(
                key="siemens_deka_83_3105",
                label='Siemens Deka 3105 "83 lb/hr"',
                description="Common Siemens Deka 83 lb high-impedance injector used in many boosted street and race setups.",
                nominal_flow_ccmin=872.0,
                dead_time_ms=0.73,
                reference_pressure_psi=43.5,
                source_note='Injector-Rehab publishes Siemens 3105 at 872 cc/min on the flow-rate page and 0.73 ms lag at 14 V on the lag-time page. Their lag article notes these are broad historical averages, so treat as a strong starter value rather than exact characterization.',
                source_url="https://injector-rehab.com/knowledge-base/fuel-injector-lag-times/",
            ),
            InjectorHardwarePreset(
                key="gm_ls3_ls7_12576341",
                label="GM LS3 / LS7 / L76 / L99 12576341",
                description="Common LS swap EV6 injector from LS3/LS7 family.",
                nominal_flow_ccmin=381.0,
                dead_time_ms=0.38,
                reference_pressure_psi=43.0,
                source_note="Holley injector data sheet lists GM 12576341 at 36.3 lb/hr and 0.38 ms offset at 14.4 V, 43 psi; cc/min shown here is approximate.",
                source_url="https://documents.holley.com/techlibrary_injectorflowdatarev2.pdf",
            ),
            InjectorHardwarePreset(
                key="gm_truck_53_12580426",
                label="GM 5.3L Truck 12580426 / 23526903",
                description="Common return-style LS truck injector family.",
                nominal_flow_ccmin=334.0,
                dead_time_ms=0.30,
                reference_pressure_psi=43.0,
                source_note="Holley injector data sheet lists this injector at 31.8 lb/hr and 0.30 ms offset at 14.4 V, 43 psi; cc/min shown here is approximate.",
                source_url="https://documents.holley.com/techlibrary_injectorflowdatarev2.pdf",
            ),
            InjectorHardwarePreset(
                key="gm_truck_48_53_25320287",
                label="GM 4.8 / 5.3L 25320287 / 25317669",
                description="Small common OEM LS truck injector used in mild swaps and budget builds.",
                nominal_flow_ccmin=198.0,
                dead_time_ms=0.08,
                reference_pressure_psi=43.0,
                source_note="Holley injector data sheet lists this injector at 18.9 lb/hr and 0.08 ms offset at 14.4 V, 43 psi; cc/min shown here is approximate.",
                source_url="https://documents.holley.com/techlibrary_injectorflowdatarev2.pdf",
            ),
            InjectorHardwarePreset(
                key="bosch_green_giant_0280155968",
                label="Bosch Green Giant 0280155968",
                description="Common 42 lb/hr high-impedance upgrade injector used on many turbo street builds.",
                nominal_flow_ccmin=475.0,
                dead_time_ms=0.704,
                reference_pressure_psi=50.76,
                source_note="MS4X cites official Bosch 3.5 bar data for Bosch 0280155968 / Green Giant at 475 cc/min and 0.704 ms offset at 14 V. Their page also notes community disagreement with Bosch's official figures, so treat this as a reviewable starter value.",
                source_url="https://www.ms4x.net/index.php?title=Fuel_Injector_Deadtimes",
                voltage_offset_samples_ms=(
                    InjectorVoltageOffsetSample(6.0, 5.216),
                    InjectorVoltageOffsetSample(8.0, 2.208),
                    InjectorVoltageOffsetSample(10.0, 1.376),
                    InjectorVoltageOffsetSample(12.0, 0.960),
                    InjectorVoltageOffsetSample(14.0, 0.704),
                    InjectorVoltageOffsetSample(16.0, 0.480),
                ),
            ),
            InjectorHardwarePreset(
                key="denso_23250_42010",
                label="Denso 23250-42010 Supra Turbo",
                description="Common Toyota Supra Turbo top-feed injector often reused in older turbo conversions.",
                nominal_flow_ccmin=440.0,
                dead_time_ms=None,
                reference_pressure_psi=32.63,
                source_note="Injector-Rehab flow data lists Denso 23250-42010 at 440 cc/min at 2.25 bar. Latency is left unset because the available Injector-Rehab lag data is not part-number specific for this injector.",
                source_url="https://injector-rehab.com/knowledge-base/flow-rates/",
            ),
            InjectorHardwarePreset(
                key="bosch_0280158123_ev14_660",
                label="Bosch 0280158123 EV14",
                description="Popular EV14 high-flow injector with pressure-specific published deadtimes.",
                nominal_flow_ccmin=660.0,
                dead_time_ms=0.496,
                reference_pressure_psi=50.76,
                source_note="MS4X lists Bosch 0280158123 at 660 cc/min and 0.496 ms offset at 14 V, 3.5 bar.",
                source_url="https://www.ms4x.net/index.php?title=Fuel_Injector_Deadtimes",
                flow_samples_ccmin=(
                    InjectorFlowSample(36.26, 560.0),
                    InjectorFlowSample(43.5, 610.0),
                    InjectorFlowSample(50.76, 660.0),
                    InjectorFlowSample(58.02, 710.0),
                    InjectorFlowSample(65.27, 750.0),
                    InjectorFlowSample(72.52, 820.0),
                    InjectorFlowSample(79.78, 860.0),
                    InjectorFlowSample(87.03, 880.0),
                ),
                voltage_offset_samples_ms=(
                    InjectorVoltageOffsetSample(6.0, 2.307),
                    InjectorVoltageOffsetSample(8.0, 1.669),
                    InjectorVoltageOffsetSample(10.0, 1.073),
                    InjectorVoltageOffsetSample(12.0, 0.733),
                    InjectorVoltageOffsetSample(14.0, 0.496),
                    InjectorVoltageOffsetSample(16.0, 0.406),
                ),
            ),
            InjectorHardwarePreset(
                key="bosch_0280158124_ev14_410",
                label="Bosch 0280158124 EV14",
                description="Popular smaller EV14 injector with pressure-specific published deadtimes.",
                nominal_flow_ccmin=410.0,
                dead_time_ms=0.490,
                reference_pressure_psi=50.76,
                source_note="MS4X lists Bosch 0280158124 at 410 cc/min and 0.490 ms offset at 14 V, 3.5 bar.",
                source_url="https://www.ms4x.net/index.php?title=Fuel_Injector_Deadtimes",
                flow_samples_ccmin=(
                    InjectorFlowSample(36.26, 340.0),
                    InjectorFlowSample(43.5, 380.0),
                    InjectorFlowSample(50.76, 410.0),
                    InjectorFlowSample(58.02, 430.0),
                    InjectorFlowSample(65.27, 460.0),
                    InjectorFlowSample(72.52, 490.0),
                    InjectorFlowSample(79.78, 510.0),
                    InjectorFlowSample(87.03, 540.0),
                ),
                voltage_offset_samples_ms=(
                    InjectorVoltageOffsetSample(6.0, 2.082),
                    InjectorVoltageOffsetSample(8.0, 1.514),
                    InjectorVoltageOffsetSample(10.0, 0.951),
                    InjectorVoltageOffsetSample(12.0, 0.650),
                    InjectorVoltageOffsetSample(14.0, 0.490),
                    InjectorVoltageOffsetSample(16.0, 0.338),
                ),
            ),
            InjectorHardwarePreset(
                key="bosch_0280158040_980",
                label="Bosch 0280158040",
                description="Very large Bosch injector for high-power setups; generally poor choice for pump-gas street idle.",
                nominal_flow_ccmin=950.0,
                dead_time_ms=0.896,
                reference_pressure_psi=50.76,
                source_note="MS4X lists Bosch 0280158040 at 950 cc/min and 0.896 ms offset at 14 V, 3.5 bar, and explicitly warns they are not recommended for pump-gas idle quality.",
                source_url="https://www.ms4x.net/index.php?title=Fuel_Injector_Deadtimes",
                flow_samples_ccmin=(
                    InjectorFlowSample(36.26, 850.0),
                    InjectorFlowSample(43.5, 900.0),
                    InjectorFlowSample(50.76, 950.0),
                    InjectorFlowSample(58.02, 1040.0),
                    InjectorFlowSample(65.27, 1110.0),
                    InjectorFlowSample(72.52, 1150.0),
                    InjectorFlowSample(79.78, 1250.0),
                    InjectorFlowSample(87.03, 1310.0),
                ),
                voltage_offset_samples_ms=(
                    InjectorVoltageOffsetSample(6.0, 2.404),
                    InjectorVoltageOffsetSample(8.0, 2.268),
                    InjectorVoltageOffsetSample(10.0, 1.518),
                    InjectorVoltageOffsetSample(12.0, 1.142),
                    InjectorVoltageOffsetSample(14.0, 0.896),
                    InjectorVoltageOffsetSample(16.0, 0.771),
                ),
            ),
            InjectorHardwarePreset(
                key="siemens_deka_80_fi114991",
                label='Siemens Deka FI114991 "80 lb/hr"',
                description="Common larger Siemens Deka high-impedance injector used in boosted builds.",
                nominal_flow_ccmin=875.0,
                dead_time_ms=0.801,
                reference_pressure_psi=43.5,
                source_note='MS4X lists Siemens Deka FI114991 / 110324 at 875 cc/min and 0.801 ms offset at 14 V, 43.5 psi.',
                source_url="https://www.ms4x.net/index.php?title=Fuel_Injector_Deadtimes",
                voltage_offset_samples_ms=(
                    InjectorVoltageOffsetSample(6.0, 2.811),
                    InjectorVoltageOffsetSample(8.0, 1.777),
                    InjectorVoltageOffsetSample(10.0, 1.288),
                    InjectorVoltageOffsetSample(12.0, 1.017),
                    InjectorVoltageOffsetSample(14.0, 0.801),
                    InjectorVoltageOffsetSample(16.0, 0.639),
                ),
            ),
            InjectorHardwarePreset(
                key="lucas_delphi_42_5_01d030b",
                label='Lucas / Delphi 42.5 lb/hr 01D030B',
                description="Common Lucas/Delphi EV1-style injector used in many turbo street applications.",
                nominal_flow_ccmin=445.0,
                dead_time_ms=0.58,
                reference_pressure_psi=50.76,
                source_note="MS4X lists Lucas/Delphi 01D030B at 445 cc/min and 0.58 ms offset at 14 V, 3.5 bar.",
                source_url="https://www.ms4x.net/index.php?title=Fuel_Injector_Deadtimes",
            ),
        )

    def injector_flow_for_pressure(
        self,
        preset: InjectorHardwarePreset,
        target_pressure_psi: float,
    ) -> float:
        if preset.flow_samples_ccmin:
            return self._interpolate_samples(
                preset.flow_samples_ccmin,
                target_pressure_psi,
                key_fn=lambda item: item.differential_pressure_psi,
                value_fn=lambda item: item.flow_ccmin,
            )
        if preset.reference_pressure_psi <= 0 or target_pressure_psi <= 0:
            return preset.nominal_flow_ccmin
        return preset.nominal_flow_ccmin * ((target_pressure_psi / preset.reference_pressure_psi) ** 0.5)

    def injector_dead_time_for_pressure(
        self,
        preset: InjectorHardwarePreset,
        target_pressure_psi: float,
        *,
        battery_voltage: float = 14.0,
    ) -> float | None:
        base_dead_time = preset.dead_time_ms
        if preset.voltage_offset_samples_ms:
            base_dead_time = self._interpolate_samples(
                preset.voltage_offset_samples_ms,
                battery_voltage,
                key_fn=lambda item: item.battery_voltage,
                value_fn=lambda item: item.offset_ms,
            )
        if base_dead_time is None:
            return None
        if preset.dead_time_pressure_compensation:
            multiplier = self._interpolate_samples(
                preset.dead_time_pressure_compensation,
                target_pressure_psi,
                key_fn=lambda item: item.differential_pressure_psi,
                value_fn=lambda item: item.multiplier,
            )
            return base_dead_time * multiplier
        return base_dead_time

    def injector_battery_correction_percentages(
        self,
        preset: InjectorHardwarePreset,
        battery_voltages: list[float],
        target_pressure_psi: float,
        *,
        reference_voltage: float = 14.0,
    ) -> list[float] | None:
        if not battery_voltages:
            return None
        reference_dead_time = self.injector_dead_time_for_pressure(
            preset,
            target_pressure_psi,
            battery_voltage=reference_voltage,
        )
        if reference_dead_time is None or reference_dead_time <= 0:
            return None
        values: list[float] = []
        for voltage in battery_voltages:
            offset = self.injector_dead_time_for_pressure(
                preset,
                target_pressure_psi,
                battery_voltage=voltage,
            )
            if offset is None:
                return None
            values.append((offset / reference_dead_time) * 100.0)
        return values

    @staticmethod
    def _interpolate_samples(samples, target: float, *, key_fn, value_fn) -> float:
        ordered = sorted(samples, key=key_fn)
        if target <= key_fn(ordered[0]):
            return float(value_fn(ordered[0]))
        if target >= key_fn(ordered[-1]):
            return float(value_fn(ordered[-1]))
        for lower, upper in zip(ordered, ordered[1:]):
            lower_key = float(key_fn(lower))
            upper_key = float(key_fn(upper))
            if lower_key <= target <= upper_key:
                span = upper_key - lower_key
                if span <= 0:
                    return float(value_fn(lower))
                ratio = (target - lower_key) / span
                lower_value = float(value_fn(lower))
                upper_value = float(value_fn(upper))
                return lower_value + ((upper_value - lower_value) * ratio)
        return float(value_fn(ordered[-1]))

    def wideband_presets(self) -> tuple[WidebandHardwarePreset, ...]:
        return (
            WidebandHardwarePreset(
                key="spartan_2",
                label="14point7 Spartan 2",
                description="Popular 0-5V Bosch LSU 4.9 controller with linear analog output.",
                afr_equation="AFR = volts * 2.0 + 10.0",
                lambda_equation="Lambda = volts * 0.136 + 0.68",
                reference_table_aliases=("spartan 2", "14point7 spartan 2"),
                source_note="MS4X documents the Spartan 2 0-5V analog transfer function for AFR and lambda.",
                source_url="https://www.ms4x.net/index.php?title=Aftermarket_Upgrade_Sensor_Data",
            ),
            WidebandHardwarePreset(
                key="aem_x_series",
                label="AEM UEGO X-Series",
                description="Common AEM 30-0300 / 30-0310 wideband controller with 0-5V output.",
                afr_equation="AFR = volts * 2.375 + 7.3125",
                lambda_equation="Lambda = volts * 0.1621 + 0.499",
                reference_table_aliases=(
                    "aem uego x-series",
                    "aem x-series",
                    "aem linear",
                    "aem-30-42xx",
                ),
                source_note="MS4X documents the AEM 30-0300 / 30-0310 X-Series analog transfer function and CAN data.",
                source_url="https://www.ms4x.net/index.php?title=Aftermarket_Upgrade_Sensor_Data",
            ),
            WidebandHardwarePreset(
                key="innovate_mtx_l",
                label="Innovate MTX-L",
                description="Common Innovate wideband controller using the factory-default analog output scale.",
                afr_equation="AFR = volts * 3.01 + 7.35",
                lambda_equation="Lambda = volts * 0.2 + 0.5",
                reference_table_aliases=(
                    "innovate mtx-l",
                    "innovate lc-1 / lc-2 default",
                    "innovate lc-1",
                    "innovate lc-2",
                ),
                source_note="MS4X documents the MTX-L factory-default analog output equations and notes that the output is configurable.",
                source_url="https://www.ms4x.net/index.php?title=Aftermarket_Upgrade_Sensor_Data",
            ),
            WidebandHardwarePreset(
                key="zeitronix_zt2_zt3",
                label="Zeitronix ZT-2 / ZT-3",
                description="Common Zeitronix wideband controllers with their default 0–5V analog output scale.",
                afr_equation="AFR = volts * 2.0 + 10.0",
                lambda_equation="Lambda = volts * 0.1361 + 0.681",
                reference_table_aliases=(
                    "zeitronix zt-2",
                    "zeitronix zt-3",
                    "zeitronix",
                ),
                source_note="Zeitronix ZT-2 / ZT-3 documentation specifies a 0–5V output spanning 10.0–20.0 AFR, giving the linear transfer function shown here. MS4X also lists this scale.",
                source_url="https://www.ms4x.net/index.php?title=Aftermarket_Upgrade_Sensor_Data",
            ),
            WidebandHardwarePreset(
                key="plx_m300",
                label="PLX Devices M300 / SM-AFR",
                description="PLX M300 and SM-AFR wideband controllers using the factory-default 0–5V analog output.",
                afr_equation="AFR = volts * 2.0 + 10.0",
                lambda_equation="Lambda = volts * 0.1361 + 0.681",
                reference_table_aliases=(
                    "plx m300",
                    "plx sm-afr",
                    "plx devices",
                ),
                source_note="PLX M300 / SM-AFR product documentation specifies a 0–5V output spanning 10.0–20.0 AFR, matching the same linear scale as the Zeitronix units.",
                source_url="https://www.ms4x.net/index.php?title=Aftermarket_Upgrade_Sensor_Data",
            ),
            WidebandHardwarePreset(
                key="14point7_spartan_lambda",
                label="14point7 Spartan Lambda (analog out)",
                description="Spartan Lambda controller with the default 0–5V lambda-linear analog output.",
                afr_equation="AFR = volts * 1.471 + 10.3",
                lambda_equation="Lambda = volts * 0.1 + 0.7",
                reference_table_aliases=(
                    "14point7 spartan lambda",
                    "spartan lambda",
                ),
                source_note="14point7 Spartan Lambda documentation specifies a 0–5V output spanning 0.7–1.2 lambda. AFR equation derived from lambda ×14.7 (petrol stoich).",
                source_url="https://www.ms4x.net/index.php?title=Aftermarket_Upgrade_Sensor_Data",
            ),
        )

    def map_sensor_presets(self) -> tuple[PressureSensorPreset, ...]:
        return (
            PressureSensorPreset(
                key="gm_3bar_12592525",
                label="GM 3-bar MAP (12592525 / 16040749)",
                description="Common GM 3-bar absolute pressure sensor widely used in LS swap and turbo builds.",
                minimum_value=10.0,
                maximum_value=304.0,
                units="kPa",
                source_note="GM service data lists the 3-bar MAP sensor (12592525 / 16040749) with a 10–304 kPa absolute pressure range.",
                source_url="https://www.msextra.com/doc/ms3/sensor_calibrations.html",
            ),
            PressureSensorPreset(
                key="aem_35bar_30_2130_50",
                label="AEM 3.5-bar MAP (30-2130-50)",
                description="AEM aftermarket 3.5-bar MAP sensor for moderate-boost applications up to ~36 psi gauge.",
                minimum_value=7.5,
                maximum_value=350.0,
                units="kPa",
                source_note="AEM product documentation for part 30-2130-50 lists a 7.5–350 kPa absolute range.",
                source_url="https://www.msextra.com/doc/ms3/sensor_calibrations.html",
            ),
            PressureSensorPreset(
                key="aem_4bar_30_2130_75",
                label="AEM 4-bar MAP (30-2130-75)",
                description="AEM aftermarket 4-bar MAP sensor for high-boost applications up to ~44 psi gauge.",
                minimum_value=7.5,
                maximum_value=400.0,
                units="kPa",
                source_note="AEM product documentation for part 30-2130-75 lists a 7.5–400 kPa absolute range.",
                source_url="https://www.msextra.com/doc/ms3/sensor_calibrations.html",
            ),
            PressureSensorPreset(
                key="nxp_mpxh6250a_dropbear",
                label="NXP MAP 20-250 kPa (MPXH6250A / DropBear MAP Card)",
                description="DropBear MAP-card sensor using the NXP MPXH6250A absolute pressure sensor.",
                minimum_value=20.0,
                maximum_value=250.0,
                units="kPa",
                source_note="The DropBear MAP-card BOM specifies NXP MPXH6250AC6T1, and the NXP MPXx6250 family sheet lists the MPXH6250A as a 20-250 kPa absolute pressure sensor.",
                source_url="https://www.nxp.com/assets/block-diagram/en/MPXx6250.pdf",
            ),
            PressureSensorPreset(
                key="bosch_0261230119_3bar",
                label="Bosch MAP 20-300 kPa (0261230119)",
                description="Common Bosch 3 bar MAP sensor.",
                minimum_value=20.0,
                maximum_value=300.0,
                units="kPa",
                source_note="MS4X lists Bosch 0261230119 with a 20-300 kPa pressure range.",
                source_url="https://www.ms4x.net/index.php?title=Aftermarket_Upgrade_Sensor_Data",
            ),
            PressureSensorPreset(
                key="bosch_0281002177_tmap",
                label="Bosch TMAP 20-260 kPa (0281002177)",
                description="Common Bosch TMAP sensor used in OEM turbo applications.",
                minimum_value=20.0,
                maximum_value=260.0,
                units="kPa",
                source_note="MS4X lists Bosch 0281002177 with a 20-260 kPa pressure range.",
                source_url="https://www.ms4x.net/index.php?title=Aftermarket_Upgrade_Sensor_Data",
            ),
            PressureSensorPreset(
                key="bosch_0281006059_tmap",
                label="Bosch TMAP 50-400 kPa (0281006059)",
                description="Common Bosch higher-range TMAP sensor for boosted applications.",
                minimum_value=50.0,
                maximum_value=400.0,
                units="kPa",
                source_note="MS4X lists Bosch 0281006059 with a 50-400 kPa pressure range.",
                source_url="https://www.ms4x.net/index.php?title=Aftermarket_Upgrade_Sensor_Data",
            ),
            PressureSensorPreset(
                key="bmw_13628637900_tmap",
                label="BMW TMAP 20-250 kPa (13628637900)",
                description="BMW B58/S58 manifold pressure sensor often reused in speed-density conversions.",
                minimum_value=20.0,
                maximum_value=250.0,
                units="kPa",
                source_note="MS4X lists BMW 13628637900 with a 20-250 kPa pressure range.",
                source_url="https://www.ms4x.net/index.php?title=Aftermarket_Upgrade_Sensor_Data",
            ),
            PressureSensorPreset(
                key="bmw_13628637897_tmap",
                label="BMW TMAP 50-400 kPa (13628637897)",
                description="Higher-range BMW TMAP sensor used on later turbo applications.",
                minimum_value=50.0,
                maximum_value=400.0,
                units="kPa",
                source_note="MS4X lists BMW 13628637897 with a 50-400 kPa pressure range.",
                source_url="https://www.ms4x.net/index.php?title=Aftermarket_Upgrade_Sensor_Data",
            ),
        )

    def oil_pressure_presets(self) -> tuple[PressureSensorPreset, ...]:
        return (
            PressureSensorPreset(
                key="bosch_pt_liquid_0261230340",
                label="Bosch PT Liquid 0-10 bar (0261230340)",
                description="Combined pressure and temperature sensor commonly repurposed for oil pressure logging.",
                minimum_value=0.0,
                maximum_value=10.0,
                units="bar",
                source_note="MS4X lists Bosch 0261230340 pressure output as 0-10 bar over the active sensor range.",
                source_url="https://www.ms4x.net/index.php?title=Aftermarket_Upgrade_Sensor_Data",
            ),
        )

    def baro_sensor_presets(self) -> tuple[PressureSensorPreset, ...]:
        return (
            PressureSensorPreset(
                key="nxp_mpx4115_kp234_dropbear_baro",
                label="NXP Baro 10-121 kPa (MPX4115 / KP234)",
                description="External barometric sensor range used by the DropBear reference tune and Speeduino's standard baro calibration option.",
                minimum_value=10.0,
                maximum_value=121.0,
                units="kPa",
                source_note="The DropBear u16p2 experimental reference tune stores baroMin=10 and baroMax=121, which matches Speeduino's MPX4115/MPXxx6115A/KP234 external-baro calibration option.",
                source_url="https://www.nxp.com/docs/en/data-sheet/MPX4115.pdf",
            ),
            PressureSensorPreset(
                key="bosch_0261230119_3bar",
                label="Bosch MAP 20-300 kPa (0261230119)",
                description="Bosch MAP sensor also usable as an external barometric sensor when wired to a dedicated input.",
                minimum_value=20.0,
                maximum_value=300.0,
                units="kPa",
                source_note="MS4X lists Bosch 0261230119 with a 20-300 kPa pressure range.",
                source_url="https://www.ms4x.net/index.php?title=Aftermarket_Upgrade_Sensor_Data",
            ),
            PressureSensorPreset(
                key="bosch_0281002177_tmap",
                label="Bosch TMAP 20-260 kPa (0281002177)",
                description="Bosch TMAP sensor usable as an external barometric sensor if a dedicated pressure output is wired.",
                minimum_value=20.0,
                maximum_value=260.0,
                units="kPa",
                source_note="MS4X lists Bosch 0281002177 with a 20-260 kPa pressure range.",
                source_url="https://www.ms4x.net/index.php?title=Aftermarket_Upgrade_Sensor_Data",
            ),
            PressureSensorPreset(
                key="bmw_13628637900_tmap",
                label="BMW TMAP 20-250 kPa (13628637900)",
                description="BMW TMAP sensor usable as an external barometric sensor if pressure output is wired separately.",
                minimum_value=20.0,
                maximum_value=250.0,
                units="kPa",
                source_note="MS4X lists BMW 13628637900 with a 20-250 kPa pressure range.",
                source_url="https://www.ms4x.net/index.php?title=Aftermarket_Upgrade_Sensor_Data",
            ),
        )

    def turbo_presets(self) -> tuple[TurboHardwarePreset, ...]:
        return (
            TurboHardwarePreset(
                key="maxpeedingrods_gt2871",
                label="Maxpeedingrods GT2871",
                description="Budget GT2871-style turbocharger preset for twin-identical or single-turbo street builds.",
                compressor_corrected_flow_lbmin=35.0,
                compressor_pressure_ratio=None,
                compressor_inducer_mm=49.2,
                compressor_exducer_mm=71.0,
                compressor_ar=0.60,
                turbine_inducer_mm=53.8,
                turbine_exducer_mm=47.0,
                turbine_ar=0.64,
                source_note="User-provided Maxpeedingrods GT2871 specification. Compressor flow is conservatively inferred from the advertised 350 BHP rating at roughly 10 BHP per lb/min; review against a real compressor map if available.",
            ),
        )
