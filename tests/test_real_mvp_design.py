from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REAL_MVP = ROOT / "docs" / "architecture" / "real-mvp-design.md"
MVP_SCOPE = ROOT / "docs" / "architecture" / "mvp-scope.md"
MVP_VERIFICATION = ROOT / "docs" / "architecture" / "mvp-verification.md"


def test_real_mvp_design_names_required_missing_agent_runtime_work() -> None:
    content = REAL_MVP.read_text()

    for phrase in (
        "Model-Backed Master Routing",
        "Model-Backed Business Result",
        "PydanticAI Frontend Bridge Tool",
        "Redis-Backed Runtime Smoke",
        "python scripts/verify_mvp.py --redis required",
    ):
        assert phrase in content


def test_real_mvp_design_keeps_mvp_boundaries_explicit() -> None:
    content = REAL_MVP.read_text()

    for phrase in (
        "Agent Gateway remains thin",
        "Business agents do not call other agents",
        "Long-term history",
        "UI output remains component name plus props",
        "Frontend bridge tools are per-agent capabilities",
    ):
        assert phrase in content


def test_existing_mvp_docs_point_to_real_mvp_design() -> None:
    assert "Real MVP Design" in MVP_SCOPE.read_text()
    assert "Real MVP Design" in MVP_VERIFICATION.read_text()


if __name__ == "__main__":
    test_real_mvp_design_names_required_missing_agent_runtime_work()
    test_real_mvp_design_keeps_mvp_boundaries_explicit()
    test_existing_mvp_docs_point_to_real_mvp_design()
    print("real mvp design tests ok")
