from __future__ import annotations

from tuner.domain.dashboard import DashboardLayout


class DashboardService:
    def load_layout(self, name: str) -> DashboardLayout:
        return DashboardLayout(name=name)
