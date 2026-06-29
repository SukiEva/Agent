from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "mvp.yml"


def test_mvp_workflow_runs_redis_backed_smoke() -> None:
    content = WORKFLOW.read_text()

    assert "redis:" in content
    assert "image: redis:7-alpine" in content
    assert "Run Redis-backed backend smoke" in content
    assert "scripts/dev_services.py --runtime-store redis --smoke --exit-after-smoke" in content


def test_mvp_workflow_runs_local_suite_and_memory_smoke() -> None:
    content = WORKFLOW.read_text()

    assert "scripts/verify_all.py" in content
    assert "Run in-memory backend smoke" in content
    assert "scripts/dev_services.py --smoke --exit-after-smoke" in content


if __name__ == "__main__":
    test_mvp_workflow_runs_redis_backed_smoke()
    test_mvp_workflow_runs_local_suite_and_memory_smoke()
    print("ci workflow tests ok")
