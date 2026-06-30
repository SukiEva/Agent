from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import ValidationError

from agent_core.config import load_service_config, validate_service_config


def test_service_config_is_validated_and_preserves_service_specific_sections() -> None:
    config = validate_service_config(
        {
            "server": {"port": "8011"},
            "runtime": {"store": "redis", "ttl_seconds": 30, "event_maxlen": 100},
            "auth": {"user": {"mode": "header"}, "internal": {"mode": "shared_secret", "secret": "secret"}},
            "logging": {"format": "text"},
            "llm": {"required": True},
            "agent": {"id": "demo_business_agent", "display": {"label": "Demo", "description": "Demo agent."}},
        }
    )

    assert config["server"]["port"] == 8011
    assert config["runtime"]["store"] == "redis"
    assert config["auth"]["user"]["mode"] == "header"
    assert config["logging"]["format"] == "text"
    assert config["llm"]["required"] is True
    assert config["agent"]["id"] == "demo_business_agent"


def test_invalid_service_config_fails_fast() -> None:
    for config in (
        {"server": {"port": 70000}},
        {"runtime": {"store": "database"}},
        {"auth": {"internal": {"mode": "shared-secret"}}},
        {"logging": {"format": "plain"}},
    ):
        try:
            validate_service_config(config)
        except ValidationError:
            pass
        else:
            raise AssertionError(f"config should be invalid: {config}")


def test_load_service_config_merges_defaults_and_validates() -> None:
    with TemporaryDirectory() as temp_dir:
        conf_dir = Path(temp_dir)
        (conf_dir / "default.yaml").write_text(
            "\n".join(
                [
                    "service:",
                    "  name: test-service",
                    "server:",
                    "  port: 8123",
                    "runtime:",
                    "  store: memory",
                ]
            )
        )
        config = load_service_config(conf_dir)

    assert config["service"]["name"] == "test-service"
    assert config["server"]["port"] == 8123
    assert config["redis"]["url"] == "redis://localhost:6379/0"


if __name__ == "__main__":
    test_service_config_is_validated_and_preserves_service_specific_sections()
    test_invalid_service_config_fails_fast()
    test_load_service_config_merges_defaults_and_validates()
    print("config tests ok")
