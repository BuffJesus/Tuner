from __future__ import annotations

from tuner.plugins.api import AppPlugin


class PluginService:
    def __init__(self) -> None:
        self._plugins: dict[str, AppPlugin] = {}

    def register(self, plugin: AppPlugin) -> None:
        self._plugins[plugin.id] = plugin

    def all_plugins(self) -> list[AppPlugin]:
        return list(self._plugins.values())
