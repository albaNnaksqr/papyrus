from __future__ import annotations

import json
from pathlib import Path

from trajectory.normalize_runs import normalize_projects


ROOT = Path(__file__).resolve().parents[1]


def test_normalize_projects_writes_jsonl_and_summary(tmp_path: Path) -> None:
    project = ROOT / "examples" / "boyer_moore_skill"
    jsonl_path = tmp_path / "normalized.jsonl"
    summary_path = tmp_path / "summary.json"

    normalized = normalize_projects([project], jsonl_path=jsonl_path, summary_path=summary_path)

    assert len(normalized) == 1
    assert jsonl_path.is_file()
    assert summary_path.is_file()
    line = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert line["paper"]["title"] == "A Fast String Searching Algorithm"
    assert summary["total_runs"] == 1
    assert summary["outcomes"] == {"partial_success": 1}
    assert summary["failure_types"]["unavailable_original_benchmark_data"] == 1
    assert summary["papers"][0]["strict_score"] == line["reward"]["strict_overall_score"]
    assert summary["papers"][0]["signal_coverage"] == line["reward"]["signal_coverage"]
    assert summary["papers"][0]["confidence"] == line["reward"]["confidence"]
    assert summary["papers"][0]["action_count"] == len(line["trajectory"]["actions"])
    assert summary["papers"][0]["edit_count"] == len(line["trajectory"]["edit_metadata"])
    assert summary["papers"][0]["repair_attempt_count"] == len(line["trajectory"]["repair_attempts"])
    assert summary["papers"][0]["reflection_count"] == len(line["trajectory"]["reflection_events"])
    assert summary["trajectory_signals"]["actions"] == len(line["trajectory"]["actions"])
    assert summary["trajectory_signals"]["edit_metadata"] == len(
        line["trajectory"]["edit_metadata"]
    )
    assert summary["trajectory_signals"]["repair_attempts"] == len(
        line["trajectory"]["repair_attempts"]
    )
    assert summary["trajectory_signals"]["reflection_events"] == len(
        line["trajectory"]["reflection_events"]
    )
