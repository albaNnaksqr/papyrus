from __future__ import annotations

import json
from pathlib import Path

from trajectory.compare_paired_runs import (
    build_paired_comparison,
    render_markdown_report,
    write_paired_outputs,
)


def _record(
    paper_id: str,
    *,
    title: str,
    outcome: str,
    strict_score: float,
    actions: int,
    edits: int,
    repairs: int,
    reflections: int,
    failure_types: list[str] | None = None,
) -> dict:
    return {
        "paper": {"paper_id": paper_id, "title": title},
        "labels": {"outcome": outcome, "failure_types": failure_types or []},
        "reward": {"strict_overall_score": strict_score, "confidence": "medium"},
        "trajectory": {
            "actions": [{"type": "implement"} for _ in range(actions)],
            "edit_metadata": [{} for _ in range(edits)],
            "repair_attempts": [{} for _ in range(repairs)],
            "reflection_events": [{} for _ in range(reflections)],
        },
        "artifacts": {"result_files": ["results/reproduction_evaluation.json"]},
    }


def test_build_paired_comparison_pairs_records_and_computes_deltas() -> None:
    codex = [
        _record(
            "repobench_repro",
            title="RepoBench",
            outcome="success",
            strict_score=0.85,
            actions=19,
            edits=6,
            repairs=5,
            reflections=4,
        ),
        _record(
            "agentless_repro",
            title="Agentless",
            outcome="partial_success",
            strict_score=0.5,
            actions=9,
            edits=3,
            repairs=1,
            reflections=0,
        ),
    ]
    claude = [
        _record(
            "repobench_claude",
            title="RepoBench",
            outcome="partial_success",
            strict_score=0.675,
            actions=25,
            edits=11,
            repairs=2,
            reflections=1,
            failure_types=["environment_gap"],
        )
    ]

    comparison = build_paired_comparison(
        codex,
        claude,
        left_label="codex",
        right_label="claude",
    )

    assert comparison["total_pairs"] == 1
    assert comparison["unpaired"]["codex"] == ["agentless_repro"]
    assert comparison["unpaired"]["claude"] == []
    pair = comparison["pairs"][0]
    assert pair["paper_key"] == "repobench"
    assert pair["deltas"] == {
        "strict_score": -0.175,
        "actions": 6,
        "edits": 5,
        "repair_attempts": -3,
        "reflection_events": -3,
    }
    assert pair["codex"]["usefulness_tags"] == [
        "artifact_sample",
        "trajectory_sample",
        "repair_sample",
    ]
    assert pair["claude"]["usefulness_tags"] == [
        "artifact_sample",
        "trajectory_sample",
        "repair_sample",
        "gap_sample",
    ]
    assert pair["preferred_for"]["repair_sample"] == "codex"
    assert pair["preferred_for"]["trajectory_sample"] == "claude"


def test_render_markdown_report_includes_pairs_unpaired_and_aggregate() -> None:
    comparison = build_paired_comparison(
        [
            _record(
                "reflexion_repro",
                title="Reflexion",
                outcome="success",
                strict_score=1.0,
                actions=20,
                edits=6,
                repairs=4,
                reflections=3,
            )
        ],
        [
            _record(
                "reflexion_claude",
                title="Reflexion",
                outcome="success",
                strict_score=0.85,
                actions=14,
                edits=2,
                repairs=0,
                reflections=0,
            )
        ],
        left_label="codex",
        right_label="claude",
    )

    markdown = render_markdown_report(comparison)

    assert markdown.startswith("# Paired Trajectory Comparison\n")
    assert "| Reflexion | success / 1.0 | success / 0.85 | -0.15 | -6 | -4 | -3 |" in markdown
    assert "`artifact_sample`" in markdown
    assert "`gap_sample`" in markdown
    assert "## Unpaired Runs" in markdown


def test_write_paired_outputs_reads_jsonl_and_writes_summary_and_report(tmp_path: Path) -> None:
    left_path = tmp_path / "codex.jsonl"
    right_path = tmp_path / "claude.jsonl"
    summary_path = tmp_path / "summary.json"
    report_path = tmp_path / "report.md"
    left_path.write_text(
        json.dumps(
            _record(
                "swe_bench_multimodal_repro",
                title="SWE-bench Multimodal",
                outcome="success",
                strict_score=1.0,
                actions=28,
                edits=7,
                repairs=4,
                reflections=3,
            )
        )
        + "\n",
        encoding="utf-8",
    )
    right_path.write_text(
        json.dumps(
            _record(
                "swe_bench_multimodal_claude",
                title="SWE-bench Multimodal",
                outcome="partial_success",
                strict_score=0.35,
                actions=22,
                edits=14,
                repairs=0,
                reflections=0,
                failure_types=["environment_gap"],
            )
        )
        + "\n",
        encoding="utf-8",
    )

    comparison = write_paired_outputs(
        left_path,
        right_path,
        summary_path=summary_path,
        report_path=report_path,
        left_label="codex",
        right_label="claude",
    )

    assert comparison["total_pairs"] == 1
    assert json.loads(summary_path.read_text(encoding="utf-8"))["pairs"][0]["paper_key"] == (
        "swe_bench_multimodal"
    )
    assert "SWE-bench Multimodal" in report_path.read_text(encoding="utf-8")
