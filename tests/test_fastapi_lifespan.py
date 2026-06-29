from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_agent_apps_use_lifespan_instead_of_deprecated_on_event() -> None:
    app_files = [
        ROOT / "apps" / "agents" / "master-agent" / "src" / "master_agent" / "main.py",
        ROOT / "apps" / "agents" / "demo-business-agent" / "src" / "demo_business_agent" / "main.py",
        ROOT / "packages" / "agent-core" / "src" / "agent_core" / "business_app.py",
    ]

    for app_file in app_files:
        content = app_file.read_text()
        assert ".on_event(" not in content


def test_lifespan_is_owned_by_agent_apps_or_business_sdk() -> None:
    master_content = (ROOT / "apps" / "agents" / "master-agent" / "src" / "master_agent" / "main.py").read_text()
    demo_content = (
        ROOT / "apps" / "agents" / "demo-business-agent" / "src" / "demo_business_agent" / "main.py"
    ).read_text()
    business_sdk_content = (ROOT / "packages" / "agent-core" / "src" / "agent_core" / "business_app.py").read_text()

    assert "lifespan=" in master_content
    assert "BusinessAgentApp" in demo_content
    assert "lifespan=" in business_sdk_content


if __name__ == "__main__":
    test_agent_apps_use_lifespan_instead_of_deprecated_on_event()
    test_lifespan_is_owned_by_agent_apps_or_business_sdk()
    print("fastapi lifespan tests ok")
