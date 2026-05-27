import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_load_paper_markdown_excludes_critique_report(tmp_path):
    """_load_paper_markdown_content must not pick up critique_report.md as the paper."""
    from workflows.agent_orchestration_engine import _load_paper_markdown_content

    (tmp_path / "paper.md").write_text("Real paper content")
    (tmp_path / "critique_report.md").write_text("Critique content")

    path, content = _load_paper_markdown_content(str(tmp_path), logging.getLogger())
    assert "critique_report" not in path
    assert content == "Real paper content"


def test_load_paper_markdown_excludes_implement_summary(tmp_path):
    """implement_code_summary.md is also excluded."""
    from workflows.agent_orchestration_engine import _load_paper_markdown_content

    (tmp_path / "paper.md").write_text("Real paper content")
    (tmp_path / "implement_code_summary.md").write_text("Summary content")

    path, content = _load_paper_markdown_content(str(tmp_path), logging.getLogger())
    assert "implement_code_summary" not in path
    assert content == "Real paper content"


def test_validation_error_downgrades_completed_pipeline_status():
    from workflows.agent_orchestration_engine import _status_after_validation

    assert _status_after_validation("completed", {"status": "error"}) == "error"
    assert _status_after_validation("completed", {"status": "partial"}) == "error"


def test_successful_validation_keeps_completed_pipeline_status():
    from workflows.agent_orchestration_engine import _status_after_validation

    assert _status_after_validation("completed", {"status": "success"}) == "completed"
    assert _status_after_validation("incomplete", {"status": "success"}) == "incomplete"


def test_explicit_critique_flag_does_not_read_global_env(monkeypatch):
    from workflows.agent_orchestration_engine import _critique_enabled

    monkeypatch.setenv("PAPER2CODE_NO_CRITIQUE", "1")

    assert _critique_enabled(False) is True
    assert _critique_enabled(True) is False
    assert _critique_enabled(None) is False


def test_quality_error_downgrades_completed_pipeline_status():
    from workflows.agent_orchestration_engine import _status_after_quality_gate

    assert _status_after_quality_gate("completed", {"status": "error"}) == "error"
    assert _status_after_quality_gate("completed_with_warnings", {"status": "error"}) == "error"
    assert _status_after_quality_gate("incomplete", {"status": "error"}) == "incomplete"


def test_pipeline_success_requires_implementation_quality_validation_and_smoke():
    from workflows.agent_orchestration_engine import _final_pipeline_status

    assert _final_pipeline_status(
        implementation={"status": "success", "inner_status": "completed"},
        quality={"status": "success"},
        validation={"status": "success"},
        smoke={"status": "success"},
    ) == "completed"
    assert _final_pipeline_status(
        implementation={"status": "success", "inner_status": "completed"},
        quality={"status": "error"},
        validation={"status": "success"},
        smoke={"status": "success"},
    ) == "error"
    assert _final_pipeline_status(
        implementation={"status": "incomplete", "inner_status": "max_iterations"},
        quality={"status": "success"},
        validation={"status": "success"},
        smoke={"status": "success"},
    ) == "incomplete"
    assert _final_pipeline_status(
        implementation={"status": "success", "inner_status": "completed"},
        quality={"status": "success"},
        validation={"status": "success"},
        smoke={"status": "error"},
    ) == "error"


def test_contract_error_is_merged_into_quality_result():
    from workflows.agent_orchestration_engine import _quality_with_contract_result

    quality = _quality_with_contract_result(
        {"status": "success", "failures": []},
        {
            "status": "error",
            "failures": ["missing entrypoint: src/main.py"],
        },
    )

    assert quality["status"] == "error"
    assert "Artifact contract failed: missing entrypoint: src/main.py" in quality["failures"]


def test_runtime_errors_are_merged_into_repair_context():
    from workflows.agent_orchestration_engine import _quality_with_runtime_results

    quality = _quality_with_runtime_results(
        {"status": "success", "failures": []},
        validation_result={
            "status": "error",
            "raw_output": "ImportError: cannot import name 'compute_stability_signal'",
        },
        smoke_result={
            "status": "error",
            "checks": [
                {
                    "name": "contract_smoke_command",
                    "stderr": "ModuleNotFoundError: No module named 'src'",
                    "status": "error",
                }
            ],
        },
    )

    assert quality["status"] == "error"
    assert quality["validation"]["status"] == "error"
    assert quality["smoke"]["status"] == "error"
    assert any("Validation failed" in failure for failure in quality["failures"])
    assert any("Smoke checks failed" in failure for failure in quality["failures"])


def test_reproduction_gate_error_is_merged_into_quality_result():
    from workflows.agent_orchestration_engine import _quality_with_reproduction_gate

    quality = _quality_with_reproduction_gate(
        {"status": "success", "failures": []},
        {
            "status": "error",
            "checks": [
                {
                    "name": "claim_contract_lint",
                    "failures": ["missing required symbols: compute_stability_signal"],
                    "status": "error",
                }
            ],
        },
    )

    assert quality["status"] == "error"
    assert quality["reproduction_gate"]["status"] == "error"
    assert "Reproduction gate failed" in quality["failures"]


def test_claim_contract_prompt_block_mentions_required_symbols():
    from workflows.claim_contract import build_claim_contract

    contract = build_claim_contract(
        plan_text="implementation_components:\n  - reward: implement compute_stability_signal\n",
        critique_text="",
    )

    prompt_block = contract.to_prompt_block()

    assert "PAPER CLAIM CONTRACT" in prompt_block
    assert "`compute_stability_signal`" in prompt_block
