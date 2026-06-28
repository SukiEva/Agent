from __future__ import annotations

from agent_core.server import hypercorn_bind


def test_hypercorn_bind_uses_server_settings() -> None:
    assert hypercorn_bind({"server": {"host": "127.0.0.1", "port": 8123}}) == ["127.0.0.1:8123"]


def test_hypercorn_bind_defaults() -> None:
    assert hypercorn_bind({}) == ["0.0.0.0:8000"]


if __name__ == "__main__":
    test_hypercorn_bind_uses_server_settings()
    test_hypercorn_bind_defaults()
    print("server tests ok")
