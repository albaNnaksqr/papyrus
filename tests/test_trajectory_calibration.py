from __future__ import annotations

import json
from pathlib import Path

from trajectory.evaluate_calibration import (
    evaluate_calibration,
    render_calibration_report,
    write_calibration_outputs,
)


def _record(
    paper_id: str,
    *,
    outcome: str = "success",
    strict_score: float = 1.0,
    actions: int = 12,
    edits: int = 3,
    repairs: int = 0,
    reflections: int = 0,
    failure_types: list[str] | None = None,
) -> dict:
    return {
        "paper": {"paper_id": paper_id, "title": paper_id.replace("_", " ").title()},
        "labels": {"outcome": outcome, "failure_types": failure_types or []},
        "reward": {"strict_overall_score": strict_score},
        "trajectory": {
            "actions": [{"type": "implement"} for _ in range(actions)],
            "edit_metadata": [{} for _ in range(edits)],
            "repair_attempts": [{} for _ in range(repairs)],
            "reflection_events": [{} for _ in range(reflections)],
        },
        "artifacts": {"result_files": ["results/reproduction_evaluation.json"]},
    }


def test_evaluate_calibration_computes_precision_and_tag_metrics() -> None:
    records = [
        _record(
            "repair_rich_repro",
            repairs=3,
            reflections=3,
            failure_types=["synthetic_fixture"],
        )
    ]
    labels = {
        "schema_version": "papyrus.calibration.v1",
        "records": {
            "repair_rich_repro": {
                "repair_attempts": [
                    {"index": 0, "label": "true_positive", "note": "real red-green repair"},
                    {"index": 1, "label": "partial", "note": "duplicate failure shares repair"},
                    {"index": 2, "label": "false_positive", "note": "report update only"},
                ],
                "reflection_events": [
                    {"index": 0, "label": "root_cause", "note": "names exact import issue"},
                    {"index": 1, "label": "plan_adjustment", "note": "states next fix"},
                    {"index": 2, "label": "procedural", "note": "only says rerun tests"},
                ],
                "usefulness_tags": {
                    "gold": [
                        "artifact_sample",
                        "trajectory_sample",
                        "repair_sample",
                        "gap_sample",
                    ]
                },
            }
        },
    }

    summary = evaluate_calibration(records, labels)

    assert summary["coverage"] == {
        "records": {"total": 1, "labeled": 1},
        "repair_attempts": {"extracted": 3, "labeled": 3},
        "reflection_events": {"extracted": 3, "labeled": 3},
        "usefulness_tags": {"runs_with_gold": 1},
    }
    assert summary["repair_attempts"]["strict_precision"] == 0.3333
    assert summary["repair_attempts"]["lenient_precision"] == 0.6667
    assert summary["reflection_events"]["strict_precision"] == 0.3333
    assert summary["reflection_events"]["lenient_precision"] == 0.6667
    assert summary["usefulness_tags"]["precision"] == 1.0
    assert summary["usefulness_tags"]["recall"] == 1.0
    assert summary["error_cases"]["repair_attempts"][0]["label"] == "false_positive"
    assert summary["error_cases"]["reflection_events"][0]["label"] == "procedural"


def test_evaluate_calibration_reports_missing_tag_recall() -> None:
    records = [
        _record(
            "resource_limited_claude",
            strict_score=0.675,
            repairs=1,
            reflections=0,
            failure_types=[],
        )
    ]
    labels = {
        "schema_version": "papyrus.calibration.v1",
        "records": {
            "resource_limited_claude": {
                "repair_attempts": [{"index": 0, "label": "partial"}],
                "reflection_events": [],
                "usefulness_tags": {
                    "gold": [
                        "artifact_sample",
                        "trajectory_sample",
                        "repair_sample",
                        "gap_sample",
                    ]
                },
            }
        },
    }

    summary = evaluate_calibration(records, labels)

    assert summary["usefulness_tags"]["precision"] == 1.0
    assert summary["usefulness_tags"]["recall"] == 0.75
    assert summary["error_cases"]["usefulness_tags"] == [
        {
            "paper_id": "resource_limited_claude",
            "false_positive_tags": [],
            "missing_tags": ["gap_sample"],
        }
    ]


def test_render_calibration_report_summarizes_metrics() -> None:
    summary = {
        "coverage": {
            "records": {"total": 1, "labeled": 1},
            "repair_attempts": {"extracted": 2, "labeled": 2},
            "reflection_events": {"extracted": 1, "labeled": 1},
            "usefulness_tags": {"runs_with_gold": 1},
        },
        "repair_attempts": {"strict_precision": 0.5, "lenient_precision": 1.0},
        "reflection_events": {"strict_precision": 1.0, "lenient_precision": 1.0},
        "usefulness_tags": {"precision": 1.0, "recall": 0.75},
        "error_cases": {"repair_attempts": [], "reflection_events": [], "usefulness_tags": []},
    }

    report = render_calibration_report(summary)

    assert report.startswith("# Trajectory Calibration Report\n")
    assert "| repair_attempts | 2 | 2 | 0.5 | 1.0 |" in report
    assert "| usefulness_tags | 1 runs | 1 runs | 1.0 | 0.75 |" in report


def test_write_calibration_outputs_reads_jsonl_and_writes_summary_and_report(tmp_path: Path) -> None:
    records_path = tmp_path / "records.jsonl"
    labels_path = tmp_path / "labels.json"
    summary_path = tmp_path / "summary.json"
    report_path = tmp_path / "report.md"
    records_path.write_text(
        json.dumps(_record("one_repro", repairs=1, reflections=1)) + "\n",
        encoding="utf-8",
    )
    labels_path.write_text(
        json.dumps(
            {
                "schema_version": "papyrus.calibration.v1",
                "records": {
                    "one_repro": {
                        "repair_attempts": [{"index": 0, "label": "true_positive"}],
                        "reflection_events": [{"index": 0, "label": "root_cause"}],
                        "usefulness_tags": {
                            "gold": ["artifact_sample", "trajectory_sample", "repair_sample"]
                        },
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    summary = write_calibration_outputs(
        [records_path],
        labels_path,
        summary_path=summary_path,
        report_path=report_path,
    )

    assert summary["repair_attempts"]["strict_precision"] == 1.0
    assert json.loads(summary_path.read_text(encoding="utf-8"))["coverage"]["records"]["labeled"] == 1
    assert "one_repro" not in report_path.read_text(encoding="utf-8")
