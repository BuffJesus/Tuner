from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

from tuner.domain.tune import TuneFile, TuneValue


MSQ_NS = {"msq": "http://www.msefi.com/:msq"}


class MsqParser:
    def parse(self, path: Path) -> TuneFile:
        root = ET.parse(path).getroot()
        version_info = root.find("msq:versionInfo", MSQ_NS)
        tune = TuneFile(source_path=path)
        if version_info is not None:
            tune.signature = version_info.attrib.get("signature")
            tune.firmware_info = version_info.attrib.get("firmwareInfo")
            tune.file_format = version_info.attrib.get("fileFormat")
            n_pages = version_info.attrib.get("nPages")
            tune.page_count = int(n_pages) if n_pages and n_pages.isdigit() else None

        for node in root.findall(".//msq:constant", MSQ_NS):
            tune.constants.append(self._parse_value_node(node))
        for node in root.findall(".//msq:pcVariable", MSQ_NS):
            tune.pc_variables.append(self._parse_value_node(node))
        return tune

    def _parse_value_node(self, node: ET.Element) -> TuneValue:
        text = (node.text or "").strip()
        rows = self._parse_int(node.attrib.get("rows"))
        cols = self._parse_int(node.attrib.get("cols"))
        value = self._parse_text_value(text, rows=rows, cols=cols)
        return TuneValue(
            name=node.attrib["name"],
            value=value,
            units=node.attrib.get("units"),
            digits=self._parse_int(node.attrib.get("digits")),
            rows=rows,
            cols=cols,
        )

    @staticmethod
    def _parse_int(value: str | None) -> int | None:
        if value is None:
            return None
        try:
            return int(value, 0)
        except ValueError:
            return None

    @staticmethod
    def _parse_text_value(text: str, rows: int | None, cols: int | None) -> str | float | list[float]:
        if rows or cols:
            values: list[float] = []
            for line in text.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                for token in stripped.split():
                    try:
                        values.append(float(token))
                    except ValueError:
                        continue
            return values
        if text.startswith('"') and text.endswith('"'):
            return text.strip('"')
        try:
            return float(text)
        except ValueError:
            return text
