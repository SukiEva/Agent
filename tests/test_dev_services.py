from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from scripts.dev_services import check_redis


def test_check_redis_uses_configured_url() -> None:
    original = sys.modules.get("redis")
    fake_redis = ModuleType("redis")
    calls: list[str] = []

    class FakeClient:
        def ping(self) -> None:
            calls.append("ping")

        def close(self) -> None:
            calls.append("close")

    class FakeRedis:
        @staticmethod
        def from_url(redis_url: str, **_kwargs: object) -> FakeClient:
            calls.append(redis_url)
            return FakeClient()

    fake_redis.Redis = FakeRedis  # type: ignore[attr-defined]
    sys.modules["redis"] = fake_redis
    try:
        assert check_redis("redis://example:6379/2") is True
    finally:
        _restore_module("redis", original)

    assert calls == ["redis://example:6379/2", "ping", "close"]


def test_check_redis_reports_connection_failure() -> None:
    original = sys.modules.get("redis")
    fake_redis = ModuleType("redis")

    class FakeRedis:
        @staticmethod
        def from_url(_redis_url: str, **_kwargs: object) -> object:
            raise RuntimeError("connection refused")

    fake_redis.Redis = FakeRedis  # type: ignore[attr-defined]
    sys.modules["redis"] = fake_redis
    try:
        assert check_redis("redis://localhost:6379/0") is False
    finally:
        _restore_module("redis", original)


def _restore_module(name: str, module: object | None) -> None:
    if module is None:
        sys.modules.pop(name, None)
        return
    sys.modules[name] = module


if __name__ == "__main__":
    test_check_redis_uses_configured_url()
    test_check_redis_reports_connection_failure()
    print("dev services tests ok")
