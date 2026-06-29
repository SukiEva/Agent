from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "scripts"))

import verify_mvp  # noqa: E402


def test_verify_mvp_skips_redis_when_optional_and_unreachable() -> None:
    calls: list[list[str]] = []
    exit_code = _run_verify_mvp(["verify_mvp.py"], calls, redis_available=False)

    assert exit_code == 0
    assert _command_suffixes(calls) == [
        ["scripts/verify_all.py"],
        ["scripts/dev_services.py", "--smoke", "--exit-after-smoke"],
    ]


def test_verify_mvp_requires_redis_when_requested() -> None:
    calls: list[list[str]] = []
    exit_code = _run_verify_mvp(["verify_mvp.py", "--redis", "required"], calls, redis_available=False)

    assert exit_code == 1
    assert _command_suffixes(calls) == [
        ["scripts/verify_all.py"],
        ["scripts/dev_services.py", "--smoke", "--exit-after-smoke"],
    ]


def test_verify_mvp_runs_redis_smoke_when_reachable() -> None:
    calls: list[list[str]] = []
    exit_code = _run_verify_mvp(["verify_mvp.py", "--redis", "required"], calls, redis_available=True)

    assert exit_code == 0
    assert _command_suffixes(calls)[-1] == [
        "scripts/dev_services.py",
        "--runtime-store",
        "redis",
        "--redis-url",
        "redis://localhost:6379/0",
        "--smoke",
        "--exit-after-smoke",
    ]


def test_verify_mvp_can_skip_redis_smoke() -> None:
    calls: list[list[str]] = []
    exit_code = _run_verify_mvp(["verify_mvp.py", "--redis", "skip"], calls, redis_available=True)

    assert exit_code == 0
    assert len(calls) == 2


def _run_verify_mvp(argv: list[str], calls: list[list[str]], redis_available: bool) -> int:
    original_argv = sys.argv
    original_run = verify_mvp.run
    original_check_redis = verify_mvp.check_redis
    sys.argv = argv
    verify_mvp.run = calls.append
    verify_mvp.check_redis = lambda _url: redis_available
    try:
        return verify_mvp.main()
    finally:
        sys.argv = original_argv
        verify_mvp.run = original_run
        verify_mvp.check_redis = original_check_redis


def _command_suffixes(calls: list[list[str]]) -> list[list[str]]:
    return [command[1:] for command in calls]


if __name__ == "__main__":
    test_verify_mvp_skips_redis_when_optional_and_unreachable()
    test_verify_mvp_requires_redis_when_requested()
    test_verify_mvp_runs_redis_smoke_when_reachable()
    test_verify_mvp_can_skip_redis_smoke()
    print("verify mvp tests ok")
