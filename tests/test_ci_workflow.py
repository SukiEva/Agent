from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "mvp.yml"


def test_mvp_workflow_is_valid_yaml() -> None:
    workflow = _load_workflow()

    assert workflow["name"] == "MVP Verification"
    assert "push" in _event_names(workflow)
    assert "pull_request" in _event_names(workflow)
    assert "verify" in workflow["jobs"]


def test_mvp_workflow_runs_redis_backed_smoke() -> None:
    workflow = _load_workflow()
    verify_job = workflow["jobs"]["verify"]
    redis = verify_job["services"]["redis"]
    step_names = _step_names(verify_job)
    run_commands = _run_commands(verify_job)

    assert redis["image"] == "redis:7-alpine"
    assert "6379:6379" in redis["ports"]
    assert "Run Redis-backed backend smoke" in step_names
    assert any("scripts/dev_services.py --runtime-store redis --smoke --exit-after-smoke" in command for command in run_commands)


def test_mvp_workflow_runs_local_suite_and_memory_smoke() -> None:
    verify_job = _load_workflow()["jobs"]["verify"]
    step_names = _step_names(verify_job)
    run_commands = _run_commands(verify_job)

    assert "Run local verification suite" in step_names
    assert "Run in-memory backend smoke" in step_names
    assert any("scripts/verify_all.py" in command for command in run_commands)
    assert any("scripts/dev_services.py --smoke --exit-after-smoke" in command for command in run_commands)


def _load_workflow() -> dict[str, object]:
    return yaml.safe_load(WORKFLOW.read_text())


def _event_names(workflow: dict[str, object]) -> set[str]:
    events = workflow.get("on") or workflow.get(True)
    if isinstance(events, dict):
        return {str(name) for name in events}
    if isinstance(events, list):
        return {str(name) for name in events}
    return {str(events)}


def _step_names(job: dict[str, object]) -> set[str]:
    return {str(step.get("name")) for step in job["steps"] if isinstance(step, dict)}


def _run_commands(job: dict[str, object]) -> list[str]:
    return [str(step["run"]) for step in job["steps"] if isinstance(step, dict) and "run" in step]


if __name__ == "__main__":
    test_mvp_workflow_is_valid_yaml()
    test_mvp_workflow_runs_redis_backed_smoke()
    test_mvp_workflow_runs_local_suite_and_memory_smoke()
    print("ci workflow tests ok")
