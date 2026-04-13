from __future__ import annotations

from tuner.plugins.api import AppContext, AppPlugin


class PluginManager:
    def __init__(self, app_context: AppContext) -> None:
        self.app_context = app_context
        self._plugins: dict[str, AppPlugin] = {}

    def register(self, plugin: AppPlugin) -> None:
        plugin.initialize(self.app_context)
        self._plugins[plugin.id] = plugin

    def shutdown(self) -> None:
        for plugin in self._plugins.values():
            plugin.shutdown()
