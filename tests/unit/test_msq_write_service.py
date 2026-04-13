from __future__ import annotations

from pathlib import Path

from tuner.parsers.msq_parser import MsqParser
from tuner.services.local_tune_edit_service import LocalTuneEditService
from tuner.services.msq_write_service import MsqWriteService


_MSQ_TEMPLATE = """\
<?xml version="1.0" encoding="ISO-8859-1"?>
<msq xmlns="http://www.msefi.com/:msq">
  <versionInfo fileFormat="5.0" firmwareInfo="Speeduino DropBear" nPages="15" signature="speeduino 202501-T41"/>
  <page>
    <constant digits="0" name="egoType" units="">0</constant>
    <constant cols="2" digits="1" name="veTable" rows="2" units="%">
      10.0 20.0
      30.0 40.0
    </constant>
  </page>
</msq>"""


def _write_source(tmp_path: Path, content: str = _MSQ_TEMPLATE) -> Path:
    src = tmp_path / "base.msq"
    src.write_text(content, encoding="ISO-8859-1")
    return src


def test_save_writes_staged_values_to_msq(tmp_path: Path) -> None:
    source = tmp_path / "base.msq"
    source.write_text(
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
        encoding="ISO-8859-1",
    )
    parser = MsqParser()
    tune = parser.parse(source)
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune)
    edit_service.stage_list_cell("veTable", 0, "99.5")

    destination = tmp_path / "edited.msq"
    MsqWriteService().save(source, destination, edit_service)
    saved = parser.parse(destination)
    saved_table = next(item for item in saved.constants if item.name == "veTable")

    assert saved_table.value[0] == 99.5


def test_save_writes_base_values_after_staged_cleared(tmp_path: Path) -> None:
    """After burn clears staged_values, save must still write the burned value.

    This is the regression guard for the original bug: MsqWriteService only
    wrote staged_values, so a burn (which clears staging via set_base_value)
    followed by a save would produce a file with the pre-burn value.
    """
    source = _write_source(tmp_path)
    parser = MsqParser()
    tune = parser.parse(source)
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune)

    # Simulate user enabling wideband (egoType=0 → 2)
    edit_service.stage_scalar_value("egoType", "2")
    assert edit_service.is_dirty("egoType")

    # Simulate burn: set_base_value is called, which clears staged entry
    edit_service.set_base_value("egoType", 2.0)
    assert not edit_service.is_dirty("egoType")  # staged cleared
    assert edit_service.get_value("egoType").value == 2.0  # base updated

    # Save should write the base value (2), NOT the stale on-disk value (0)
    destination = tmp_path / "after_burn.msq"
    MsqWriteService().save(source, destination, edit_service)
    saved = parser.parse(destination)
    saved_ego = next(item for item in saved.constants if item.name == "egoType")
    assert saved_ego.value == 2.0


def test_save_writes_integer_scalars_without_decimal(tmp_path: Path) -> None:
    """Integer-like float values should be written as "2" not "2.0"."""
    source = _write_source(tmp_path)
    parser = MsqParser()
    tune = parser.parse(source)
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune)
    edit_service.stage_scalar_value("egoType", "2")
    edit_service.set_base_value("egoType", 2.0)

    destination = tmp_path / "int_format.msq"
    MsqWriteService().save(source, destination, edit_service)
    raw_text = destination.read_text(encoding="ISO-8859-1")
    # "2" not "2.0" in the file
    assert ">2<" in raw_text
    assert ">2.0<" not in raw_text


def test_save_preserves_unchanged_values(tmp_path: Path) -> None:
    """Parameters not changed by the user must keep their original on-disk values."""
    source = _write_source(tmp_path)
    parser = MsqParser()
    tune = parser.parse(source)
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune)
    # Only change egoType; veTable is untouched
    edit_service.stage_scalar_value("egoType", "1")

    destination = tmp_path / "partial.msq"
    MsqWriteService().save(source, destination, edit_service)
    saved = parser.parse(destination)
    saved_table = next(item for item in saved.constants if item.name == "veTable")
    assert saved_table.value == [10.0, 20.0, 30.0, 40.0]
