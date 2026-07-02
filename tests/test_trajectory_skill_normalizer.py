from __future__ import annotations

import json
from pathlib import Path

from trajectory.normalize_skill_run import normalize_skill_run
from trajectory.reward import compute_reward


ROOT = Path(__file__).resolve().parents[1]
BOYER_MOORE = ROOT / "examples" / "boyer_moore_skill"


def test_normalizes_boyer_moore_skill_run_to_schema_v1() -> None:
    normalized = normalize_skill_run(BOYER_MOORE)

    assert normalized["schema_version"] == "papyrus.trajectory.v1"
    assert normalized["paper"]["title"] == "A Fast String Searching Algorithm"
    assert normalized["paper"]["paper_type"] == "algorithm"
    assert normalized["run"]["runner"] == "skill"
    assert normalized["run"]["agent_host"] == "codex"
    assert normalized["run"]["model"] == "gpt-5.5"
    assert normalized["contracts"]["reproduction_contract"]["reproduction_level"] == "Level 3"
    assert normalized["artifacts"]["reproduction_report"]["path"] == "REPRODUCTION_REPORT.md"
    assert normalized["trajectory"]["turn_count"] == 9
    assert normalized["trajectory"]["tool_calls_by_name"]["exec_command"] == 20
    assert normalized["labels"]["outcome"] == "partial_success"
    assert normalized["labels"]["failure_types"] == [
        "unavailable_original_benchmark_data",
        "nonportable_hardware_metric",
    ]
    assert normalized["failure_analysis"]["primary_failure_type"] == (
        "unavailable_original_benchmark_data"
    )
    assert normalized["reward"]["overall_score"] > 0.8
    assert normalized["reward"]["claim_fidelity"] == 0.75


def test_compute_reward_prefers_honest_approximate_reproduction() -> None:
    evaluation = {
        "status": "approximately_reproduced",
        "fully_reproduced": [{"item": "correctness"}],
        "approximately_reproduced": [{"item": "trend"}],
        "not_reproduced": [],
    }
    summary = {
        "status": "completed",
        "checks": {
            "matches_reference": True,
            "fewer_comparisons_than_naive": True,
        },
    }
    report = (
        "Fully reproduced: exact behavior.\n"
        "Approximately reproduced: trend with substitutes.\n"
        "Not reproduced: exact original machine counts.\n"
    )

    reward = compute_reward(evaluation=evaluation, summary=summary, report_text=report)

    assert reward["task_completion"] == 0.75
    assert reward["code_runs"] == 1.0
    assert reward["smoke_pass"] == 1.0
    assert reward["experiment_completed"] == 1.0
    assert reward["claim_fidelity"] == 0.75
    assert reward["report_honesty"] == 1.0
    assert reward["missing_signals"] == []


def test_compute_reward_exposes_strict_score_and_signal_coverage() -> None:
    evaluation = {
        "fully_reproduced": ["bounded claim"],
        "approximately_reproduced": [],
        "not_reproduced": [],
    }
    summary = {}
    report = (
        "Fully reproduced: bounded claim.\n"
        "Approximately reproduced: none.\n"
        "Not reproduced: full benchmark.\n"
    )

    reward = compute_reward(evaluation=evaluation, summary=summary, report_text=report)

    assert reward["overall_score"] == 1.0
    assert reward["strict_overall_score"] == 0.55
    assert reward["signal_coverage"] == 0.55
    assert reward["confidence"] == "medium"
    assert reward["missing_signals"] == [
        "code_runs",
        "smoke_pass",
        "experiment_completed",
    ]


def test_compute_reward_reads_list_checks_and_status_aliases() -> None:
    evaluation = {
        "overall_status": "fully_reproduced",
        "checks": [
            {"name": "first", "passed": True},
            {"name": "second", "passed": True},
        ],
        "fully_reproduced": ["bounded claim"],
        "approximately_reproduced": [],
        "not_reproduced": [],
    }
    summary = {}
    report = (
        "Fully reproduced: bounded claim.\n"
        "Approximately reproduced: none.\n"
        "Not reproduced: full benchmark.\n"
    )

    reward = compute_reward(evaluation=evaluation, summary=summary, report_text=report)

    assert reward["code_runs"] == 1.0
    assert reward["experiment_completed"] == 1.0
    assert reward["smoke_pass"] == 1.0
    assert reward["strict_overall_score"] == 1.0
    assert reward["confidence"] == "high"


def test_normalizes_partial_success_when_evaluation_has_mixed_target_lists() -> None:
    normalized = normalize_skill_run(ROOT / "output" / "adam_optimizer_repro")

    assert normalized["paper"]["title"].startswith("Adam: A Method for Stochastic Optimization")
    assert normalized["run"]["runner"] == "skill"
    assert normalized["run"]["agent_host"] == "claude"
    assert normalized["labels"]["outcome"] == "partial_success"
    assert normalized["reward"]["claim_fidelity"] == 0.75
    assert "metric_mismatch" in normalized["labels"]["failure_types"]
    assert "hyperparameter_missing" in normalized["labels"]["failure_types"]


def test_normalizes_scaffold_failure_without_claim_credit() -> None:
    normalized = normalize_skill_run(ROOT / "output" / "dropout_repro")

    assert normalized["paper"]["title"].startswith("Dropout:")
    assert normalized["labels"]["outcome"] == "failure"
    assert normalized["reward"]["claim_fidelity"] == 0.0
    assert "hyperparameter_missing" in normalized["labels"]["failure_types"]
    assert "compute_budget_limit" in normalized["labels"]["failure_types"]


def test_normalizes_status_schema_success_from_bounded_code_agent_run() -> None:
    normalized = normalize_skill_run(ROOT / "output" / "code_agent_deep_runs" / "swe_bench_repro")

    assert normalized["paper"]["title"].startswith("SWE-bench:")
    assert normalized["paper"]["paper_type"] == "systems"
    assert normalized["run"]["agent_host"] == "codex"
    assert normalized["labels"]["outcome"] == "success"
    assert normalized["reward"]["claim_fidelity"] == 1.0
    assert normalized["reward"]["smoke_pass"] == 1.0
    assert normalized["reward"]["overall_score"] == 1.0
    assert "full_benchmark_not_attempted" in normalized["labels"]["failure_types"]
    assert "synthetic_fixture" in normalized["labels"]["failure_types"]


def test_normalizes_multimodal_list_checks_as_observed_smoke_signal() -> None:
    normalized = normalize_skill_run(
        ROOT / "output" / "code_agent_deep_runs" / "swe_bench_multimodal_repro"
    )

    assert normalized["paper"]["title"].startswith("SWE-bench Multimodal")
    assert normalized["reward"]["smoke_pass"] == 1.0
    assert normalized["reward"]["strict_overall_score"] == 1.0
    assert normalized["reward"]["confidence"] == "high"


def test_code_agent_file_edits_include_patch_metadata_for_each_apply_patch() -> None:
    project = ROOT / "output" / "code_agent_deep_runs" / "swe_agent_repro"
    normalized = normalize_skill_run(project)

    apply_patch_calls = [
        call
        for call in normalized["trajectory"]["tool_calls"]
        if call["name"] == "apply_patch"
    ]
    file_edits = normalized["trajectory"]["file_edits"]

    assert {edit["tool_call_id"] for edit in file_edits} == {
        call["id"] for call in apply_patch_calls
    }
    assert file_edits
    for edit in file_edits:
        assert edit["path"]
        assert edit["operation"] in {"create", "update", "delete"}
        assert edit["diff_line_count"] > 0
        assert edit["target_class"] in {
            "implementation",
            "test",
            "evaluator",
            "config",
            "report",
            "other",
        }


def test_swe_agent_tdd_red_green_loop_is_planned_repair_attempt() -> None:
    normalized = normalize_skill_run(
        ROOT / "output" / "code_agent_deep_runs" / "swe_agent_repro"
    )

    planned = [
        attempt
        for attempt in normalized["trajectory"]["repair_attempts"]
        if attempt["kind"] == "planned_tdd_red"
    ]

    assert planned
    assert any(attempt["turn_span"] == [7, 10] for attempt in planned)
    tdd_attempt = next(attempt for attempt in planned if attempt["turn_span"] == [7, 10])
    assert "python -m unittest discover -s tests -v" in tdd_attempt["failing_command"]
    assert "ImportError" in tdd_attempt["failure_summary"]
    assert "src/aci.py" in tdd_attempt["edited_files"]
    assert tdd_attempt["retest_command"] == "python -m unittest discover -s tests -v"
    assert tdd_attempt["repair_success"] is True


def test_collects_codex_token_usage_from_matching_rollout(tmp_path, monkeypatch) -> None:
    session_id = "session-with-token-usage"
    home = tmp_path / "home"
    session_dir = home / ".codex" / "sessions" / "2026" / "07" / "02"
    session_dir.mkdir(parents=True)
    (session_dir / f"rollout-2026-07-02T00-00-00-{session_id}.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {
                                "last_token_usage": {
                                    "input_tokens": 10,
                                    "cached_input_tokens": 4,
                                    "output_tokens": 3,
                                    "reasoning_output_tokens": 1,
                                    "total_tokens": 13,
                                }
                            },
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {
                                "last_token_usage": {
                                    "input_tokens": 7,
                                    "cached_input_tokens": 2,
                                    "output_tokens": 5,
                                    "reasoning_output_tokens": 2,
                                    "total_tokens": 12,
                                }
                            },
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home))
    (tmp_path / "agent_trace.jsonl").write_text(
        json.dumps({"source": "codex", "session_id": session_id, "turns": []}) + "\n",
        encoding="utf-8",
    )

    normalized = normalize_skill_run(tmp_path)

    assert normalized["provenance"]["normalizer_version"] == "skill.v2"
    assert normalized["run"]["token_usage"]["input_tokens"] == 17
    assert normalized["run"]["token_usage"]["cached_input_tokens"] == 6
    assert normalized["run"]["token_usage"]["output_tokens"] == 8
    assert normalized["run"]["token_usage"]["reasoning_output_tokens"] == 3
    assert normalized["run"]["token_usage"]["total_tokens"] == 25
    assert normalized["run"]["token_usage"]["session_id"] == session_id


def test_missing_codex_session_keeps_token_usage_null_and_records_note(
    tmp_path, monkeypatch
) -> None:
    home = tmp_path / "home"
    (home / ".codex" / "sessions").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    (tmp_path / "agent_trace.jsonl").write_text(
        json.dumps(
            {
                "source": "codex",
                "session_id": "missing-session-for-normalizer-test",
                "turns": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    normalized = normalize_skill_run(tmp_path)

    assert normalized["run"]["token_usage"] is None
    assert any(
        "missing-session-for-normalizer-test" in note
        and "Codex session rollout not found" in note
        for note in normalized["provenance"]["notes"]
    )
