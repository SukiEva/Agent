from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "scripts"))

import verify_all  # noqa: E402


def test_verify_all_builds_backend_with_uv_build() -> None:
    calls: list[list[str]] = []
    original_run = verify_all.run

    def fake_run(command: list[str], **_kwargs: object) -> None:
        calls.append(command)

    verify_all.run = fake_run
    try:
        exit_code = verify_all.main()
    finally:
        verify_all.run = original_run

    assert exit_code == 0
    assert [
        "uv",
        "build",
        "--all-packages",
        "--out-dir",
        "/tmp/agent-mvp-build",
        "--no-create-gitignore",
    ] in calls


if __name__ == "__main__":
    test_verify_all_builds_backend_with_uv_build()
    print("verify all tests ok")
