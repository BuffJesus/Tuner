from __future__ import annotations

import json
from pathlib import Path

from tuner.domain.datalog_profile import DatalogChannelEntry, DatalogProfile
from tuner.domain.ecu_definition import ScalarParameterDefinition
from tuner.domain.output_channels import OutputChannelSnapshot, OutputChannelValue

_PRIORITY_CHANNEL_PREFIXES = (
    "rpm", "map", "tps", "afr", "lambda", "coolant", "iat",
    "battery", "advance", "ve", "dwell", "pulsewidth", "pw",
    "ego", "o2", "fuel",
)


class DatalogProfileService:
    """Manage datalog profiles: create defaults, load/save as JSON, validate, filter."""

    # ------------------------------------------------------------------
    # Default profile
    # ------------------------------------------------------------------

    def default_profile(
        self,
        output_channel_defs: list[ScalarParameterDefinition] | None = None,
    ) -> DatalogProfile:
        """Build a default profile.

        If *output_channel_defs* is supplied the profile covers all channels from
        the definition, ordered by priority first.  Without definitions it returns
        an empty profile named "Default".
        """
        if not output_channel_defs:
            return DatalogProfile(name="Default")

        entries = [
            DatalogChannelEntry(
                name=ch.name,
                label=ch.label or ch.name,
                units=ch.units,
                enabled=True,
                format_digits=ch.digits,
            )
            for ch in output_channel_defs
        ]
        entries.sort(key=lambda e: self._priority_rank(e.name))
        return DatalogProfile(name="Default", channels=entries)

    # ------------------------------------------------------------------
    # Load / save (single profile)
    # ------------------------------------------------------------------

    def load(self, path: Path) -> DatalogProfile:
        data = json.loads(path.read_text(encoding="utf-8"))
        return self._deserialize_profile(data, path.stem)

    def save(self, path: Path, profile: DatalogProfile) -> None:
        path.write_text(json.dumps(self._serialize_profile(profile), indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    # Load / save (profile collection — multi-profile sidecar format)
    # ------------------------------------------------------------------

    def load_collection(self, path: Path) -> tuple[list[DatalogProfile], str]:
        """Load a profile collection from *path*.

        Returns ``(profiles, active_name)``.  Falls back to the legacy
        single-profile format when no ``"profiles"`` key is present.
        """
        data = json.loads(path.read_text(encoding="utf-8"))
        if "profiles" in data:
            profiles = [self._deserialize_profile(p) for p in data["profiles"]]
            if not profiles:
                profiles = [DatalogProfile(name="Default")]
            active_name = data.get("active", profiles[0].name)
            return profiles, active_name
        # Old single-profile format — wrap in a list.
        profile = self._deserialize_profile(data, path.stem)
        return [profile], profile.name

    def save_collection(
        self,
        path: Path,
        profiles: list[DatalogProfile],
        active_name: str,
    ) -> None:
        """Write a profile collection to *path*."""
        data: dict = {
            "version": 1,
            "active": active_name,
            "profiles": [self._serialize_profile(p) for p in profiles],
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def unavailable_channels(
        self,
        profile: DatalogProfile,
        available_names: set[str],
    ) -> list[str]:
        """Return names of enabled channels that are not in *available_names*."""
        return [
            ch.name
            for ch in profile.enabled_channels
            if ch.name not in available_names
        ]

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def filter_snapshot(
        self,
        profile: DatalogProfile,
        snapshot: OutputChannelSnapshot,
    ) -> OutputChannelSnapshot:
        """Return a snapshot containing only the enabled channels in *profile*."""
        enabled_names = {ch.name for ch in profile.enabled_channels}
        filtered = [v for v in snapshot.values if v.name in enabled_names]
        return OutputChannelSnapshot(timestamp=snapshot.timestamp, values=filtered)

    def apply_definition_metadata(
        self,
        profile: DatalogProfile,
        output_channel_defs: list[ScalarParameterDefinition],
    ) -> None:
        """Back-fill label/units on existing profile entries from the current definition.

        Does not reorder or add/remove channels.  Safe to call on a loaded profile
        when a new definition is opened.
        """
        by_name = {ch.name: ch for ch in output_channel_defs}
        for entry in profile.channels:
            defn = by_name.get(entry.name)
            if defn is None:
                continue
            if entry.label is None:
                entry.label = defn.label or defn.name
            if entry.units is None:
                entry.units = defn.units
            if entry.format_digits is None:
                entry.format_digits = defn.digits

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _deserialize_profile(data: dict, fallback_name: str = "Default") -> DatalogProfile:
        channels = [
            DatalogChannelEntry(
                name=ch["name"],
                label=ch.get("label"),
                units=ch.get("units"),
                enabled=bool(ch.get("enabled", True)),
                format_digits=ch.get("format_digits"),
            )
            for ch in data.get("channels", [])
        ]
        return DatalogProfile(name=data.get("name", fallback_name), channels=channels)

    @staticmethod
    def _serialize_profile(profile: DatalogProfile) -> dict:
        return {
            "name": profile.name,
            "channels": [
                {k: v for k, v in {
                    "name": ch.name,
                    "label": ch.label,
                    "units": ch.units,
                    "enabled": ch.enabled,
                    "format_digits": ch.format_digits,
                }.items() if v is not None}
                for ch in profile.channels
            ],
        }

    @staticmethod
    def _priority_rank(name: str) -> int:
        lower = name.lower()
        for rank, prefix in enumerate(_PRIORITY_CHANNEL_PREFIXES):
            if lower.startswith(prefix):
                return rank
        return len(_PRIORITY_CHANNEL_PREFIXES)
