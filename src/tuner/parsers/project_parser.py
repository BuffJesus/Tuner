from __future__ import annotations

from pathlib import Path

from tuner.domain.project import ConnectionProfile, Project
from tuner.parsers.common import parse_key_value_file


class ProjectParser:
    def parse(self, path: Path) -> Project:
        metadata = parse_key_value_file(path) if path.exists() else {}
        project = Project(name=metadata.get("projectName", path.stem), project_path=path, metadata=metadata)
        project.ecu_definition_path = self._resolve_optional_path(path, metadata.get("ecuDefinition"))
        project.tune_file_path = self._resolve_optional_path(path, metadata.get("tuneFile"))
        dashboards = metadata.get("dashboards")
        if dashboards:
            project.dashboards = [item.strip() for item in dashboards.split(",") if item.strip()]
        active_settings_raw = metadata.get("activeSettings", "")
        project.active_settings = frozenset(
            s.strip() for s in active_settings_raw.split(",") if s.strip()
        )
        profile = self._parse_default_connection_profile(metadata)
        if profile is not None:
            project.connection_profiles.append(profile)
        return project

    @staticmethod
    def _parse_default_connection_profile(metadata: dict[str, str]) -> ConnectionProfile | None:
        prefix = "connection.default."
        relevant = {key[len(prefix):]: value for key, value in metadata.items() if key.startswith(prefix)}
        if not relevant:
            return None
        port = None
        baud_rate = None
        try:
            if "port" in relevant:
                port = int(relevant["port"])
        except ValueError:
            port = None
        try:
            if "baudRate" in relevant:
                baud_rate = int(relevant["baudRate"])
        except ValueError:
            baud_rate = None
        return ConnectionProfile(
            name=relevant.get("name", "Default"),
            transport=relevant.get("transport", "mock"),
            protocol=relevant.get("protocol"),
            host=relevant.get("host"),
            port=port,
            serial_port=relevant.get("serialPort"),
            baud_rate=baud_rate,
        )

    @staticmethod
    def _resolve_optional_path(project_path: Path, raw_value: str | None) -> Path | None:
        if not raw_value:
            return None
        candidate = Path(raw_value)
        if candidate.is_absolute():
            return candidate
        return (project_path.parent / candidate).resolve()
