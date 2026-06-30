from __future__ import annotations

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
