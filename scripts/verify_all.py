from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(command))
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    subprocess.run(command, cwd=cwd, env=merged_env, check=True)


def main() -> int:
    run(["./.venv/bin/python", "-m", "compileall", "apps", "packages", "scripts", "tests"])
    for test in (
        "tests/test_a2a_cards.py",
        "tests/test_agent_gateway.py",
        "tests/test_agent_core_stores.py",
        "tests/test_auth.py",
        "tests/test_cancel_events.py",
        "tests/test_ci_workflow.py",
        "tests/test_config.py",
        "tests/test_dev_services.py",
        "tests/test_files.py",
        "tests/test_agent_server_auth.py",
        "tests/test_agent_server_files.py",
        "tests/test_llm.py",
        "tests/test_logging.py",
        "tests/test_master_agent_delivery.py",
        "tests/test_master_agent_routing.py",
        "tests/test_redis_stores.py",
        "tests/test_server.py",
        "tests/test_ui_contracts.py",
        "tests/test_verify_mvp.py",
    ):
        run(["./.venv/bin/python", test])

    run(["bun", "src/runtime/events.test.ts"], cwd=ROOT / "web")
    run(["bun", "run", "web:typecheck"])
    run(["bun", "run", "web:build"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
