from __future__ import annotations

def main() -> int:
    try:
        from tuner.ui.main_window import launch_app
    except ModuleNotFoundError as exc:
        missing = exc.name or "unknown dependency"
        print(f"UI bootstrap is unavailable because '{missing}' is not installed.")
        print("Install GUI dependencies from pyproject.toml and retry.")
        return 1

    return launch_app()
