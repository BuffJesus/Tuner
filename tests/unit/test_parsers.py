from pathlib import Path

from tuner.domain.project import ConnectionProfile
from tuner.parsers.ini_parser import IniParser
from tuner.parsers.msq_parser import MsqParser
from tuner.parsers.project_parser import ProjectParser
from tuner.services.project_service import ProjectService


def test_project_parser_reads_basic_fields(tmp_path: Path) -> None:
    project_file = tmp_path / "demo.project"
    project_file.write_text(
        "\n".join(
            [
                "projectName=Demo Project",
                "ecuDefinition=main.ini",
                "tuneFile=tune.msq",
                "dashboards=Main,Aux",
            ]
        ),
        encoding="utf-8",
    )

    project = ProjectParser().parse(project_file)

    assert project.name == "Demo Project"
    assert project.ecu_definition_path == (tmp_path / "main.ini").resolve()
    assert project.tune_file_path == (tmp_path / "tune.msq").resolve()
    assert project.dashboards == ["Main", "Aux"]


def test_project_service_creates_and_saves_reopenable_project(tmp_path: Path) -> None:
    project_dir = tmp_path / "MyCar"
    definition = project_dir / "speeduino.ini"
    tune = project_dir / "base.msq"
    definition.parent.mkdir(parents=True, exist_ok=True)
    definition.write_text("signature=Speeduino", encoding="utf-8")
    tune.write_text("<msq/>", encoding="utf-8")

    project = ProjectService().create_project(
        name="MyCar",
        project_directory=project_dir,
        ecu_definition_path=definition,
        tune_file_path=tune,
        connection_profile=ConnectionProfile(
            name="Default",
            transport="serial",
            protocol="speeduino",
            serial_port="COM7",
            baud_rate=115200,
        ),
        metadata={
            "lambdaDisplay": "AFR",
            "ui.activeTab": "1",
            "ui.workspace.activePageId": "table-editor:ve",
            "ui.workspace.catalogQuery": "ve",
        },
    )

    reopened = ProjectParser().parse(project.project_path)

    assert project.project_path is not None
    assert project.project_path.exists()
    assert reopened.name == "MyCar"
    assert reopened.ecu_definition_path == definition.resolve()
    assert reopened.tune_file_path == tune.resolve()
    assert reopened.metadata["lambdaDisplay"] == "AFR"
    assert reopened.metadata["ui.activeTab"] == "1"
    assert reopened.metadata["ui.workspace.activePageId"] == "table-editor:ve"
    assert reopened.metadata["ui.workspace.catalogQuery"] == "ve"
    assert len(reopened.connection_profiles) == 1
    assert reopened.connection_profiles[0].transport == "serial"
    assert reopened.connection_profiles[0].protocol == "speeduino"
    assert reopened.connection_profiles[0].serial_port == "COM7"


def test_ini_parser_reads_signature_and_channels(tmp_path: Path) -> None:
    ini_file = tmp_path / "ecu.ini"
    ini_file.write_text(
        "\n".join(
            [
                "signature=MS3-Pro",
                "protocol=XCP",
                "outputChannels=rpm,map,afr",
                "constants=reqFuel,warmupEnrich",
                "xcpMap.rpm=0x4,4,u32,rpm",
                "xcpMap.afr=0xA,4,f32,afr",
            ]
        ),
        encoding="utf-8",
    )

    definition = IniParser().parse(ini_file)

    assert definition.name == "MS3-Pro"
    assert definition.transport_hint == "XCP"
    assert definition.output_channels == ["rpm", "map", "afr"]
    assert [item.name for item in definition.scalars] == ["reqFuel", "warmupEnrich"]
    assert [(item.name, item.address, item.size, item.data_type) for item in definition.xcp_mappings] == [
        ("rpm", 0x4, 4, "u32"),
        ("afr", 0xA, 4, "f32"),
    ]


def test_ini_parser_reads_speeduino_style_constant_metadata(tmp_path: Path) -> None:
    ini_file = tmp_path / "speeduino.ini"
    ini_file.write_text(
        "\n".join(
            [
                "[MegaTune]",
                'queryCommand = "Q"',
                'signature = "speeduino 202501-T41"',
                'versionInfo = "S"',
                "[Constants]",
                "endianness = little",
                "pageSize = 128, 288",
                "page = 1",
                'reqFuel = scalar, U08, 24, "ms", 0.1, 0.0, 0.0, 25.5, 1',
                'veTable = array, U08, 0, [16x16], "%", 1.0, 0.0, 0.0, 255.0, 0',
            ]
        ),
        encoding="utf-8",
    )

    definition = IniParser().parse(ini_file)

    assert definition.query_command == "Q"
    assert definition.endianness == "little"
    assert definition.page_sizes == [128, 288]
    assert definition.scalars[0].name == "reqFuel"
    assert definition.scalars[0].page == 1
    assert definition.scalars[0].offset == 24
    assert definition.tables[0].name == "veTable"


def test_ini_parser_extracts_descriptive_page_titles_from_constant_comments(tmp_path: Path) -> None:
    ini_file = tmp_path / "speeduino.ini"
    ini_file.write_text(
        "\n".join(
            [
                "[Constants]",
                ";--------------------------------------------------",
                ";Start page 6",
                "; Page 6 is all settings associated with O2/AFR",
                ";--------------------------------------------------",
                "page = 6",
                'egoType = bits, U08, 0, [0:1], "Off", "Narrowband", "Wideband"',
                ";Page 13 is the programmable outputs",
                "page = 13",
                'outputPin = scalar, U08, 0, "", 1, 0, 0, 255, 0',
            ]
        ),
        encoding="utf-8",
    )

    definition = IniParser().parse(ini_file)

    assert definition.page_titles[6] == "O2/AFR Settings"
    assert definition.page_titles[13] == "Programmable Outputs"


def test_ini_parser_preserves_expression_backed_table_fields_with_embedded_commas(tmp_path: Path) -> None:
    definition_path = tmp_path / "speeduino_expr.ini"
    definition_path.write_text(
        "\n".join(
            [
                '[MegaTune]',
                'signature = "speeduino 202501-T41-U16P2"',
                '[Constants]',
                'page = 2',
                'algorithm = bits, U08, 37, [0:2], "MAP", "TPS", "IMAP/EMAP"',
                'fuelLoadBins = array, U08, 528, [16], { bitStringValue(algorithmUnits , algorithm) }, {fuelLoadRes}, 0.0, 0.0, {fuelLoadMax}, {fuelDecimalRes}',
            ]
        ),
        encoding="utf-8",
    )

    definition = IniParser().parse(definition_path)
    fuel_load_bins = next(item for item in definition.tables if item.name == "fuelLoadBins")

    assert fuel_load_bins.units == "{ bitStringValue(algorithmUnits , algorithm) }"
    assert fuel_load_bins.scale_expression == "{fuelLoadRes}"
    assert fuel_load_bins.translate == 0.0
    assert fuel_load_bins.max_value is None
    assert fuel_load_bins.digits is None
    assert definition.tables[0].rows == 16
    assert definition.tables[0].columns == 1


def test_ini_parser_resolves_lastoffset_for_following_arrays_and_scalars(tmp_path: Path) -> None:
    definition_path = tmp_path / "speeduino_lastoffset.ini"
    definition_path.write_text(
        "\n".join(
            [
                "[Constants]",
                "page = 5",
                'lambdaTable = array, U08, 0, [16x16], "Lambda", 0.1, 0.0, 0.0, 2.0, 3',
                'afrTable = array, U08, lastOffset, [16x16], "AFR", 0.1, 0.0, 7.0, 25.5, 1',
                'ego_min_lambda = scalar, U08, lastOffset, "Lambda", 0.1, 0.0, 0.0, 2.0, 3',
            ]
        ),
        encoding="utf-8",
    )

    definition = IniParser().parse(definition_path)

    lambda_table = next(item for item in definition.tables if item.name == "lambdaTable")
    afr_table = next(item for item in definition.tables if item.name == "afrTable")
    ego_min_lambda = next(item for item in definition.scalars if item.name == "ego_min_lambda")

    assert lambda_table.offset == 0
    assert afr_table.offset == 256
    assert ego_min_lambda.offset == 512


def test_ini_parser_reads_table_editor_metadata(tmp_path: Path) -> None:
    ini_file = tmp_path / "speeduino.ini"
    ini_file.write_text(
        "\n".join(
            [
                "[TableEditor]",
                'table = veTable1Tbl, veTable1Map, "VE Table", 2',
                'topicHelp = "http://wiki.speeduino.com/en/configuration/VE_table"',
                "xBins = rpmBins, rpm",
                "yBins = fuelLoadBins, fuelLoad",
                'xyLabels = "RPM", "Fuel Load: "',
                "zBins = veTable",
                "gridHeight = 2.0",
                "gridOrient = 250, 0, 340",
                'upDownLabel = "(RICHER)", "(LEANER)"',
            ]
        ),
        encoding="utf-8",
    )

    definition = IniParser().parse(ini_file)

    assert len(definition.table_editors) == 1
    editor = definition.table_editors[0]
    assert editor.title == "VE Table"
    assert editor.page == 2
    assert editor.x_bins == "rpmBins"
    assert editor.y_bins == "fuelLoadBins"
    assert editor.z_bins == "veTable"
    assert editor.x_label == "RPM"
    assert editor.y_label == "Fuel Load: "
    assert editor.grid_orient == (250.0, 0.0, 340.0)


def test_ini_parser_reads_dialog_menu_help_and_bits_metadata(tmp_path: Path) -> None:
    ini_file = tmp_path / "speeduino.ini"
    ini_file.write_text(
        "\n".join(
            [
                "[Constants]",
                "page = 1",
                'sparkMode = bits, U08, 12, [2:4], "Wasted Spark", "Sequential"',
                'reqFuel = scalar, U08, 24, "ms", 0.1, 0.0, 0.0, 25.5, 1',
                "[ConstantsExtensions]",
                "requiresPowerCycle = sparkMode",
                "[SettingContextHelp]",
                'sparkMode = "Spark output mode help"',
                "[UserDefined]",
                'dialog = sparkSettings, "Spark Settings"',
                'field = "Spark output mode", sparkMode',
                'field = "Required Fuel", reqFuel',
                "[Menu]",
                'menu = "&Spark"',
                'subMenu = sparkSettings, "Spark Settings"',
            ]
        ),
        encoding="utf-8",
    )

    definition = IniParser().parse(ini_file)

    assert definition.scalars[0].name == "sparkMode"
    assert definition.scalars[0].options[0].label == "Wasted Spark"
    assert definition.scalars[0].bit_offset == 2
    assert definition.scalars[0].bit_length == 3
    assert definition.scalars[0].help_text == "Spark output mode help"
    assert definition.scalars[0].requires_power_cycle is True
    assert definition.dialogs[0].dialog_id == "sparkSettings"
    assert definition.dialogs[0].fields[0].parameter_name == "sparkMode"
    assert definition.menus[0].title == "&Spark"
    assert definition.menus[0].items[0].target == "sparkSettings"


def test_ini_parser_reads_output_channels_section_metadata(tmp_path: Path) -> None:
    ini_file = tmp_path / "speeduino.ini"
    ini_file.write_text(
        "\n".join(
            [
                "[OutputChannels]",
                'rpm = scalar, U16, 14, "rpm", 1.0, 0.0',
                'map = scalar, U16, 4, "kPa", 1.0, 0.0',
                'running = bits, U08, 2, [0:0]',
            ]
        ),
        encoding="utf-8",
    )

    definition = IniParser().parse(ini_file)

    assert definition.output_channels == ["rpm", "map", "running"]
    assert [field.name for field in definition.output_channel_definitions] == ["rpm", "map", "running"]
    assert definition.output_channel_definitions[2].bit_offset == 0
    assert definition.output_channel_definitions[2].bit_length == 1


def test_ini_parser_reads_output_channel_array_default_values(tmp_path: Path) -> None:
    """Array-kind output channels with defaultValue lines must populate output_channel_arrays."""
    ini_file = tmp_path / "speeduino.ini"
    ini_file.write_text(
        "\n".join([
            "[OutputChannels]",
            'rpm = scalar, U16, 14, "rpm", 1.0, 0.0',
            "boardHasRTC = array, U08, [4], \" \", 1.0, 0, 0, 255, 0, noMsqSave",
            "boardHasSD  = array, U08, [4], \" \", 1.0, 0, 0, 255, 0, noMsqSave",
            "defaultValue = boardHasRTC, 0 0 1 0",
            "defaultValue = boardHasSD,  0 0 0 1",
            "; defaultValue for rpm is absent — no array stored",
        ]),
        encoding="utf-8",
    )

    from tuner.parsers.ini_parser import IniParser
    definition = IniParser().parse(ini_file)

    assert "boardHasRTC" in definition.output_channel_arrays
    assert definition.output_channel_arrays["boardHasRTC"] == [0.0, 0.0, 1.0, 0.0]
    assert "boardHasSD" in definition.output_channel_arrays
    assert definition.output_channel_arrays["boardHasSD"] == [0.0, 0.0, 0.0, 1.0]
    # Scalar output channels must not create array entries
    assert "rpm" not in definition.output_channel_arrays


def test_msq_parser_reads_speeduino_style_tune_values(tmp_path: Path) -> None:
    msq_file = tmp_path / "base.msq"
    msq_file.write_text(
        "\n".join(
            [
                '<?xml version="1.0" encoding="ISO-8859-1"?>',
                '<msq xmlns="http://www.msefi.com/:msq">',
                '  <versionInfo fileFormat="5.0" firmwareInfo="Speeduino DropBear" nPages="15" signature="speeduino 202501-T41"/>',
                '  <page>',
                '    <pcVariable name="tsCanId">"CAN ID 0"</pcVariable>',
                '    <constant digits="1" name="reqFuel" units="ms">9.1</constant>',
                '    <constant cols="1" digits="0" name="veTable" rows="3" units="%">',
                '      10.0',
                '      20.0',
                '      30.0',
                '    </constant>',
                "  </page>",
                "</msq>",
            ]
        ),
        encoding="utf-8",
    )

    tune = MsqParser().parse(msq_file)

    assert tune.signature == "speeduino 202501-T41"
    assert tune.firmware_info == "Speeduino DropBear"
    assert tune.page_count == 15
    assert tune.pc_variables[0].value == "CAN ID 0"
    assert tune.constants[0].name == "reqFuel"
    assert tune.constants[0].value == 9.1
    assert tune.constants[1].value == [10.0, 20.0, 30.0]


def test_msq_parser_reads_whitespace_separated_table_rows(tmp_path: Path) -> None:
    msq_file = tmp_path / "ford300.msq"
    msq_file.write_text(
        "\n".join(
            [
                '<?xml version="1.0" encoding="ISO-8859-1"?>',
                '<msq xmlns="http://www.msefi.com/:msq">',
                '  <versionInfo fileFormat="5.0" firmwareInfo="Speeduino DropBear" nPages="15" signature="speeduino 202501-T41"/>',
                '  <page>',
                '    <constant cols="2" digits="1" name="veTable" rows="2" units="%">',
                '      10.0 20.0',
                '      30.0 40.0',
                '    </constant>',
                "  </page>",
                "</msq>",
            ]
        ),
        encoding="utf-8",
    )

    tune = MsqParser().parse(msq_file)

    assert tune.constants[0].name == "veTable"
    assert tune.constants[0].value == [10.0, 20.0, 30.0, 40.0]
