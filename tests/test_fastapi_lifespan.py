from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_agent_apps_use_lifespan_instead_of_deprecated_on_event() -> None:
    app_files = [
        ROOT / "apps" / "agents" / "master-agent" / "src" / "master_agent" / "main.py",
        ROOT / "apps" / "agents" / "demo-business-agent" / "src" / "demo_business_agent" / "main.py",
    ]

    for app_file in app_files:
        content = app_file.read_text()
        assert ".on_event(" not in content
        assert "lifespan=" in content


if __name__ == "__main__":
    test_agent_apps_use_lifespan_instead_of_deprecated_on_event()
    print("fastapi lifespan tests ok")
