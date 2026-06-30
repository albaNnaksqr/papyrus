from __future__ import annotations

import json
from pathlib import Path

from trajectory.export_portfolio import export_portfolio


def _record(paper_id: str, *, score: float, strict: float, confidence: str) -> dict:
    return {
        "paper": {
            "paper_id": paper_id,
            "title": paper_id.replace("_", " ").title(),
        },
        "labels": {
            "outcome": "success",
            "reproduction_level": "Bounded Level 2/3",
            "failure_types": ["synthetic_fixture"] if paper_id != "reflexion_repro" else [],
        },
        "reward": {
            "overall_score": score,
            "strict_overall_score": strict,
            "signal_coverage": strict,
            "confidence": confidence,
        },
        "failure_analysis": {
            "primary_failure_type": "synthetic_fixture"
            if paper_id != "reflexion_repro"
            else None
        },
        "artifacts": {
            "generated_project_path": f"/tmp/{paper_id}",
        },
    }


def test_export_portfolio_marks_mainline_case_and_writes_files(tmp_path: Path) -> None:
    records = [
        _record("swe_bench_repro", score=1.0, strict=1.0, confidence="high"),
        _record("swe_agent_repro", score=1.0, strict=1.0, confidence="high"),
        _record("swe_bench_multimodal_repro", score=1.0, strict=0.85, confidence="high"),
        _record("agentless_repro", score=0.75, strict=0.55, confidence="medium"),
    ]
    json_path = tmp_path / "portfolio_summary.json"
    markdown_path = tmp_path / "portfolio_summary.md"
    case_path = tmp_path / "code_agent_trajectory_data_pipeline.md"

    summary = export_portfolio(
        records,
        json_path=json_path,
        markdown_path=markdown_path,
        case_path=case_path,
    )

    assert json_path.is_file()
    assert markdown_path.is_file()
    assert case_path.is_file()
    assert summary["total_runs"] == 4
    assert summary["mainline_paper_ids"] == [
        "swe_bench_repro",
        "swe_agent_repro",
        "swe_bench_multimodal_repro",
    ]
    assert summary["confidence_counts"] == {"high": 3, "medium": 1}

    markdown = markdown_path.read_text(encoding="utf-8")
    assert "Code Agent Trajectory Data Pipeline" in markdown
    assert "strict_score" in markdown
    assert "benchmark_fidelity" in markdown

    case_markdown = case_path.read_text(encoding="utf-8")
    assert "SWE-bench" in case_markdown
    assert "SWE-agent" in case_markdown
    assert "SWE-bench Multimodal" in case_markdown

    persisted = json.loads(json_path.read_text(encoding="utf-8"))
    assert persisted["mainline_paper_ids"] == summary["mainline_paper_ids"]
