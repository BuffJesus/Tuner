from __future__ import annotations

import os
from pathlib import Path

from tuner.domain.project import ConnectionProfile, Project
from tuner.parsers.project_parser import ProjectParser


class ProjectService:
    def __init__(self, parser: ProjectParser | None = None) -> None:
        self.parser = parser or ProjectParser()

    def open_project(self, path: Path) -> Project:
        return self.parser.parse(path)

    def save_project(self, project: Project, path: Path | None = None) -> Path:
        target = (path or project.project_path)
        if target is None:
            raise ValueError("Project path is required to save a project.")
        target.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"projectName={project.name}"]
        if project.ecu_definition_path is not None:
            lines.append(f"ecuDefinition={self._relative_path(target, project.ecu_definition_path)}")
        if project.tune_file_path is not None:
            lines.append(f"tuneFile={self._relative_path(target, project.tune_file_path)}")
        if project.dashboards:
            lines.append(f"dashboards={','.join(project.dashboards)}")
        if project.active_settings:
            lines.append(f"activeSettings={','.join(sorted(project.active_settings))}")
        if project.connection_profiles:
            profile = project.connection_profiles[0]
            lines.append(f"connection.default.name={profile.name}")
            lines.append(f"connection.default.transport={profile.transport}")
            if profile.protocol:
                lines.append(f"connection.default.protocol={profile.protocol}")
            if profile.host:
                lines.append(f"connection.default.host={profile.host}")
            if profile.port is not None:
                lines.append(f"connection.default.port={profile.port}")
            if profile.serial_port:
                lines.append(f"connection.default.serialPort={profile.serial_port}")
            if profile.baud_rate is not None:
                lines.append(f"connection.default.baudRate={profile.baud_rate}")
        for key, value in sorted(project.metadata.items()):
            if key in {"projectName", "ecuDefinition", "tuneFile", "dashboards", "activeSettings"} or key.startswith("connection.default."):
                continue
            lines.append(f"{key}={value}")
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        project.project_path = target
        return target

    def create_project(
        self,
        name: str,
        project_directory: Path,
        ecu_definition_path: Path | None = None,
        tune_file_path: Path | None = None,
        connection_profile: ConnectionProfile | None = None,
        metadata: dict[str, str] | None = None,
    ) -> Project:
        safe_name = self._sanitize_name(name) or "project"
        project_directory.mkdir(parents=True, exist_ok=True)
        project_path = project_directory / f"{safe_name}.project"
        project = Project(
            name=name.strip() or safe_name,
            project_path=project_path,
            ecu_definition_path=ecu_definition_path.resolve() if ecu_definition_path else None,
            tune_file_path=tune_file_path.resolve() if tune_file_path else None,
            connection_profiles=[connection_profile] if connection_profile is not None else [],
            metadata=dict(metadata or {}),
        )
        self.save_project(project, project_path)
        return project

    @staticmethod
    def _sanitize_name(name: str) -> str:
        return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in name.strip()).strip("_")

    @staticmethod
    def _relative_path(project_path: Path, target_path: Path) -> str:
        try:
            return os.path.relpath(target_path.resolve(), start=project_path.parent.resolve())
        except ValueError:
            return str(target_path.resolve())
