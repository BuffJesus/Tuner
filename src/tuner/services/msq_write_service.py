from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

from tuner.domain.tune import TuneValue
from tuner.services.local_tune_edit_service import LocalTuneEditService


MSQ_NS = {"msq": "http://www.msefi.com/:msq"}
_MSQ_NS_URI = "http://www.msefi.com/:msq"


class MsqWriteService:
    def save(
        self,
        source_path: Path,
        destination_path: Path,
        edit_service: LocalTuneEditService,
        *,
        insert_missing: bool = False,
    ) -> None:
        """Write the effective tune values back into a copy of *source_path*.

        ``insert_missing`` (Fragile area #1 fix) — when True, any staged or
        base value whose ``name`` does not exist as a ``<constant>`` node in
        the source XML is *inserted* into the first ``<page>`` element
        instead of being silently dropped. The default ``False`` preserves
        the historical behaviour for callers that need byte-stable round
        trips against an unmodified source MSQ.
        """
        if not source_path.exists():
            raise FileNotFoundError(f"Source MSQ not found: {source_path}")
        tree = ET.parse(source_path)
        root = tree.getroot()
        node_index: dict[str, ET.Element] = {}
        for node in root.findall(".//msq:constant", MSQ_NS):
            name = node.attrib.get("name")
            if name:
                node_index[name] = node
        for node in root.findall(".//msq:pcVariable", MSQ_NS):
            name = node.attrib.get("name")
            if name:
                node_index[name] = node

        # Write all effective values (staged OR base).  Staged values take
        # precedence over base; base values are present even after a burn clears
        # the staged layer.  Writing only staged_values would silently leave the
        # MSQ at its original on-disk state for any parameter that was burned
        # (because burn clears the staged entry).
        for name, node in node_index.items():
            effective = edit_service.get_value(name)
            if effective is None:
                continue
            node.text = self._format_value(effective)

        if insert_missing:
            self._insert_missing_constants(root, node_index, edit_service)

        destination_path.parent.mkdir(parents=True, exist_ok=True)
        tree.write(destination_path, encoding="ISO-8859-1", xml_declaration=True)

    def _insert_missing_constants(
        self,
        root: ET.Element,
        existing: dict[str, ET.Element],
        edit_service: LocalTuneEditService,
    ) -> None:
        """Inject new ``<constant>`` nodes for staged or base values absent
        from the source XML. Targets the first ``<page>`` element so the
        insertion stays inside the document tree the parser already
        understands. Names already in ``existing`` are skipped.
        """
        page_element = root.find(".//msq:page", MSQ_NS)
        if page_element is None:
            return

        # Build the set of effective values to consider. Order: base
        # constants first (so any pre-existing layout intent is honored),
        # then any staged-only names that aren't in the base.
        names: list[str] = []
        seen: set[str] = set()
        base = edit_service.base_tune_file
        if base is not None:
            for item in (*base.constants, *base.pc_variables):
                if item.name and item.name not in seen:
                    names.append(item.name)
                    seen.add(item.name)
        for name in edit_service.staged_values:
            if name and name not in seen:
                names.append(name)
                seen.add(name)

        for name in names:
            if name in existing:
                continue
            tune_value = edit_service.get_value(name)
            if tune_value is None:
                continue
            element = ET.SubElement(
                page_element,
                f"{{{_MSQ_NS_URI}}}constant",
                attrib=self._constant_attribs(tune_value),
            )
            element.text = self._format_value(tune_value)
            existing[name] = element

    @staticmethod
    def _constant_attribs(tune_value: TuneValue) -> dict[str, str]:
        attribs: dict[str, str] = {"name": tune_value.name}
        if tune_value.units:
            attribs["units"] = tune_value.units
        if isinstance(tune_value.value, list):
            attribs["rows"] = str(tune_value.rows or 1)
            attribs["cols"] = str(tune_value.cols or len(tune_value.value))
        if tune_value.digits is not None:
            attribs["digits"] = str(tune_value.digits)
        return attribs

    def _format_value(self, tune_value: TuneValue) -> str:
        value = tune_value.value
        if isinstance(value, list):
            rows = tune_value.rows or len(value)
            cols = tune_value.cols or 1
            lines: list[str] = []
            for row_index in range(rows):
                start = row_index * cols
                end = start + cols
                row = value[start:end]
                if not row:
                    continue
                lines.append("         " + " ".join(_fmt_scalar(v) for v in row) + " ")
            return "\n" + "\n".join(lines) + "\n      "
        if isinstance(value, str):
            return value if value.startswith('"') and value.endswith('"') else value
        return _fmt_scalar(value)


def _fmt_scalar(value: float | int) -> str:
    """Format a scalar value the same way TunerStudio does: integers without decimals."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
