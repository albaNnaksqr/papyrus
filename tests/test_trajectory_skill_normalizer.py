from __future__ import annotations

import json
from pathlib import Path

from trajectory.normalize_skill_run import normalize_skill_run
from trajectory.reward import compute_reward


ROOT = Path(__file__).resolve().parents[1]
BOYER_MOORE = ROOT / "examples" / "boyer_moore_skill"


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: dict) -> None:
    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _write_rule_extraction_fixture(project_dir: Path) -> None:
    _write_json(
        project_dir / "reproduction_contract.json",
        {
            "paper_title": "Rule Extraction Paper",
            "paper_type": "systems",
            "reproduction_level": "Level 2/3 bounded",
            "reproduction_targets": [{"target": "Extract semantic agent trajectory events"}],
            "metrics": [{"name": "smoke_pass"}],
            "missing_but_required": [],
            "assumptions": [],
        },
    )
    _write_json(project_dir / "paper_structure.json", {"paper_title": "Rule Extraction Paper"})
    _write_json(project_dir / "results" / "reproduction_evaluation.json", {"status": "fully_reproduced"})
    _write_json(project_dir / "results" / "reproduction_summary.json", {"status": "completed", "checks": {"smoke": True}})
    _write_text(
        project_dir / "REPRODUCTION_REPORT.md",
        "Fully reproduced: bounded claim.\nApproximately reproduced: none.\nNot reproduced: full benchmark.\n",
    )
    trace = {
        "source": "codex",
        "model": "gpt-5.5",
        "invoked_at": "2026-06-30T00:00:00Z",
        "ended_at": "2026-06-30T00:05:00Z",
        "args": {"pdf_path": "/tmp/rule-paper.pdf", "run_id": "rule-run"},
        "trace_bounds": {"end_marker": {"status": "complete"}},
        "turns": [
            {
                "role": "assistant",
                "phase": "phase_1",
                "text": "I am extracting the PDF and grounding the target claim.",
                "tool_calls": [
                    {
                        "id": "read_pdf",
                        "name": "exec_command",
                        "input": {"cmd": "pdftotext /tmp/rule-paper.pdf -", "workdir": str(project_dir)},
                        "tool_result": {"metadata": {"exit_code": 0}, "output": "paper text"},
                    }
                ],
                "tool_results": [],
            },
            {
                "role": "assistant",
                "phase": "phase_2",
                "text": "Now I will create the reproduction contract and implementation files.",
                "tool_calls": [
                    {
                        "id": "write_impl",
                        "name": "apply_patch",
                        "input": (
                            "*** Begin Patch\n"
                            "*** Add File: src/model.py\n"
                            "+def run():\n"
                            "+    return False\n"
                            "*** Add File: reproduction_contract.json\n"
                            "+{\"paper_title\": \"Rule Extraction Paper\"}\n"
                            "*** End Patch\n"
                        ),
                        "tool_result": {"metadata": {"exit_code": 0}, "output": "Success. Updated files."},
                    }
                ],
                "tool_results": [],
            },
            {
                "role": "assistant",
                "phase": "phase_3",
                "text": "I am running the smoke test.",
                "tool_calls": [
                    {
                        "id": "smoke_fail",
                        "name": "exec_command",
                        "input": {"cmd": "python -m pytest -q tests", "workdir": str(project_dir)},
                        "tool_result": {
                            "metadata": {"exit_code": 1},
                            "output": "FAILED tests/test_model.py::test_run - AssertionError",
                        },
                    }
                ],
                "tool_results": [],
            },
            {
                "role": "assistant",
                "phase": "phase_3",
                "text": "The smoke test failed because run returns False; I need to adjust the implementation.",
                "tool_calls": [
                    {
                        "id": "repair_impl",
                        "name": "apply_patch",
                        "input": (
                            "*** Begin Patch\n"
                            "*** Update File: src/model.py\n"
                            "@@ \n"
                            "-    return False\n"
                            "+    return True\n"
                            "*** End Patch\n"
                        ),
                        "tool_result": {"metadata": {"exit_code": 0}, "output": "Success. Updated files."},
                    }
                ],
                "tool_results": [],
            },
            {
                "role": "assistant",
                "phase": "phase_3",
                "text": "I am rerunning smoke and evaluator.",
                "tool_calls": [
                    {
                        "id": "smoke_pass",
                        "name": "exec_command",
                        "input": {"cmd": "python -m pytest -q tests", "workdir": str(project_dir)},
                        "tool_result": {"metadata": {"exit_code": 0}, "output": "1 passed"},
                    },
                    {
                        "id": "eval_pass",
                        "name": "exec_command",
                        "input": {"cmd": "python scripts/evaluate_reproduction.py", "workdir": str(project_dir)},
                        "tool_result": {"metadata": {"exit_code": 0}, "output": "fully_reproduced"},
                    },
                ],
                "tool_results": [],
            },
            {
                "role": "assistant",
                "phase": "phase_4",
                "text": "Writing the final reproduction report.",
                "tool_calls": [
                    {
                        "id": "write_report",
                        "name": "apply_patch",
                        "input": (
                            "*** Begin Patch\n"
                            "*** Update File: REPRODUCTION_REPORT.md\n"
                            "+Fully reproduced: bounded claim.\n"
                            "*** End Patch\n"
                        ),
                        "tool_result": {"metadata": {"exit_code": 0}, "output": "Success. Updated files."},
                    }
                ],
                "tool_results": [],
            },
        ],
        "stats": {"tool_calls_by_name": {"exec_command": 4, "apply_patch": 3}},
    }
    _write_text(project_dir / "agent_trace.jsonl", json.dumps(trace, ensure_ascii=False) + "\n")


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


def test_rule_based_extraction_derives_actions_edits_repairs_and_reflections(tmp_path: Path) -> None:
    project_dir = tmp_path / "rule_extraction_repro"
    _write_rule_extraction_fixture(project_dir)

    normalized = normalize_skill_run(project_dir)
    trajectory = normalized["trajectory"]

    assert [action["type"] for action in trajectory["actions"]] == [
        "paper_inspect",
        "contract_write",
        "implement",
        "run_smoke",
        "repair",
        "run_smoke",
        "evaluate",
        "report",
    ]
    assert trajectory["edit_metadata"][0]["files"] == [
        "src/model.py",
        "reproduction_contract.json",
    ]
    assert trajectory["edit_metadata"][0]["roles"] == ["contract", "implementation"]
    assert trajectory["edit_metadata"][1]["operation"] == "update"
    assert trajectory["edit_metadata"][1]["roles"] == ["implementation"]
    assert trajectory["repair_attempts"] == [
        {
            "failure_turn": 2,
            "failure_type": "pytest_failure",
            "failure_command": "python -m pytest -q tests",
            "repair_edit_turns": [3],
            "verification_turn": 4,
            "verification_command": "python -m pytest -q tests",
            "resolved": True,
        }
    ]
    assert trajectory["reflection_events"] == [
        {
            "turn_index": 3,
            "linked_failure_turn": 2,
            "linked_edit_turn": 3,
            "text": "The smoke test failed because run returns False; I need to adjust the implementation.",
        }
    ]


def test_claude_trace_shape_derives_actions_edits_and_repairs(tmp_path: Path) -> None:
    project_dir = tmp_path / "claude_repro"
    _write_json(
        project_dir / "reproduction_contract.json",
        {
            "paper_title": "Claude Shape Paper",
            "paper_type": "systems",
            "reproduction_level": "Level 2",
            "reproduction_targets": [{"target": "Handle Claude trace"}],
            "metrics": [],
            "missing_but_required": [],
            "assumptions": [],
        },
    )
    _write_json(project_dir / "paper_structure.json", {"paper_title": "Claude Shape Paper"})
    _write_json(
        project_dir / "results" / "reproduction_evaluation.json",
        {"fully_reproduced": [{"target": "Handle Claude trace"}], "approximately_reproduced": [], "not_reproduced": []},
    )
    _write_json(project_dir / "results" / "reproduction_summary.json", {"status": "completed"})
    _write_text(project_dir / "REPRODUCTION_REPORT.md", "Fully reproduced: bounded claim.\n")
    trace = {
        "source": "claude",
        "model": "claude-sonnet-test",
        "args": {"run_id": "claude-shape-run", "pdf_path": "/tmp/claude-shape.pdf"},
        "trace_bounds": {"end_marker": {"status": "complete"}},
        "turns": [
            {
                "role": "assistant",
                "text": "",
                "tool_calls": [
                    {
                        "id": "read_pdf",
                        "name": "Read",
                        "input": {"file_path": "/tmp/claude-shape.pdf", "pages": "1-2"},
                    }
                ],
                "tool_results": [],
            },
            {
                "role": "tool_result",
                "tool_calls": [],
                "tool_results": [
                    {
                        "tool_use_id": "read_pdf",
                        "content": "PDF pages extracted",
                        "is_error": False,
                    }
                ],
            },
            {
                "role": "assistant",
                "text": "Writing contract and first implementation.",
                "tool_calls": [
                    {
                        "id": "write_contract",
                        "name": "Write",
                        "input": {
                            "file_path": str(project_dir / "reproduction_contract.json"),
                            "content": "{\"paper_title\": \"Claude Shape Paper\"}\n",
                        },
                    },
                    {
                        "id": "write_impl",
                        "name": "Write",
                        "input": {
                            "file_path": str(project_dir / "src" / "model.py"),
                            "content": "def run():\n    return False\n",
                        },
                    },
                ],
                "tool_results": [],
            },
            {
                "role": "tool_result",
                "tool_calls": [],
                "tool_results": [
                    {
                        "tool_use_id": "write_contract",
                        "content": "The file has been updated successfully.",
                        "is_error": False,
                    },
                    {
                        "tool_use_id": "write_impl",
                        "content": "The file has been updated successfully.",
                        "is_error": False,
                    },
                ],
            },
            {
                "role": "assistant",
                "text": "Running smoke.",
                "tool_calls": [
                    {
                        "id": "smoke_fail",
                        "name": "Bash",
                        "input": {"command": "python scripts/run_smoke.py", "description": "Run smoke"},
                    }
                ],
                "tool_results": [],
            },
            {
                "role": "tool_result",
                "tool_calls": [],
                "tool_results": [
                    {
                        "tool_use_id": "smoke_fail",
                        "content": "Traceback: AssertionError",
                        "is_error": True,
                    }
                ],
            },
            {
                "role": "assistant",
                "text": "The smoke failed because run returns False; I need to fix the implementation.",
                "tool_calls": [
                    {
                        "id": "repair_impl",
                        "name": "Edit",
                        "input": {
                            "file_path": str(project_dir / "src" / "model.py"),
                            "old_string": "    return False",
                            "new_string": "    return True",
                        },
                    }
                ],
                "tool_results": [],
            },
            {
                "role": "tool_result",
                "tool_calls": [],
                "tool_results": [
                    {
                        "tool_use_id": "repair_impl",
                        "content": "The file has been updated successfully.",
                        "is_error": False,
                    }
                ],
            },
            {
                "role": "assistant",
                "text": "Rerun smoke and evaluator.",
                "tool_calls": [
                    {
                        "id": "smoke_pass",
                        "name": "Bash",
                        "input": {"command": "python scripts/run_smoke.py"},
                    },
                    {
                        "id": "eval_pass",
                        "name": "Bash",
                        "input": {"command": "python scripts/evaluate_reproduction.py"},
                    },
                ],
                "tool_results": [],
            },
            {
                "role": "tool_result",
                "tool_calls": [],
                "tool_results": [
                    {"tool_use_id": "smoke_pass", "content": "SMOKE PASS", "is_error": False},
                    {"tool_use_id": "eval_pass", "content": "fully_reproduced", "is_error": False},
                ],
            },
        ],
    }
    _write_text(project_dir / "agent_trace.jsonl", json.dumps(trace, ensure_ascii=False) + "\n")

    trajectory = normalize_skill_run(project_dir)["trajectory"]

    assert [action["type"] for action in trajectory["actions"]] == [
        "paper_inspect",
        "contract_write",
        "implement",
        "run_smoke",
        "repair",
        "run_smoke",
        "evaluate",
    ]
    assert trajectory["edit_metadata"][0]["files"] == ["reproduction_contract.json"]
    assert trajectory["edit_metadata"][1]["files"] == ["src/model.py"]
    assert trajectory["repair_attempts"][0]["failure_turn"] == 4
    assert trajectory["repair_attempts"][0]["repair_edit_turns"] == [6]
    assert trajectory["repair_attempts"][0]["verification_turn"] == 8
    assert trajectory["repair_attempts"][0]["resolved"] is True


def test_rule_based_extraction_ignores_exploration_failures_and_normalizes_paths(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "exploration_repro"
    _write_json(
        project_dir / "reproduction_contract.json",
        {
            "paper_title": "Exploration Paper",
            "paper_type": "systems",
            "reproduction_level": "Level 2",
            "reproduction_targets": [],
            "metrics": [],
            "missing_but_required": [],
            "assumptions": [],
        },
    )
    _write_json(project_dir / "paper_structure.json", {"paper_title": "Exploration Paper"})
    _write_json(project_dir / "results" / "reproduction_evaluation.json", {"status": "fully_reproduced"})
    _write_json(project_dir / "results" / "reproduction_summary.json", {"status": "completed"})
    _write_text(project_dir / "REPRODUCTION_REPORT.md", "Fully reproduced: bounded claim.\n")
    trace = {
        "source": "codex",
        "model": "gpt-5.5",
        "args": {"run_id": "exploration-run"},
        "trace_bounds": {"end_marker": {"status": "complete"}},
        "turns": [
            {
                "role": "assistant",
                "text": "Searching for the claim mention.",
                "tool_calls": [
                    {
                        "id": "search_no_match",
                        "name": "exec_command",
                        "input": {"cmd": 'rg -n "missing claim" /tmp/paper.txt'},
                        "tool_result": {"metadata": {"exit_code": 1}, "output": ""},
                    }
                ],
            },
            {
                "role": "assistant",
                "text": "Writing the first implementation.",
                "tool_calls": [
                    {
                        "id": "write_initial",
                        "name": "apply_patch",
                        "input": (
                            "*** Begin Patch\n"
                            f"*** Add File: {project_dir}/reproduction_contract.json\n"
                            "+{\"paper_title\": \"Exploration Paper\"}\n"
                            f"*** Add File: {project_dir}/src/model.py\n"
                            "+def run():\n"
                            "+    return True\n"
                            "*** End Patch\n"
                        ),
                        "tool_result": {"metadata": {"exit_code": 0}, "output": "Success. Updated files."},
                    }
                ],
            },
            {
                "role": "assistant",
                "text": "Running the smoke test.",
                "tool_calls": [
                    {
                        "id": "smoke_pass",
                        "name": "exec_command",
                        "input": {"cmd": "python -m pytest -q tests"},
                        "tool_result": {"metadata": {"exit_code": 0}, "output": "1 passed"},
                    }
                ],
            },
        ],
    }
    _write_text(project_dir / "agent_trace.jsonl", json.dumps(trace, ensure_ascii=False) + "\n")

    trajectory = normalize_skill_run(project_dir)["trajectory"]

    assert trajectory["repair_attempts"] == []
    assert trajectory["edit_metadata"][0]["files"] == [
        "reproduction_contract.json",
        "src/model.py",
    ]
    assert [action["type"] for action in trajectory["actions"]] == [
        "contract_write",
        "implement",
        "run_smoke",
    ]


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
