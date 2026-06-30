from __future__ import annotations

from pathlib import Path

from trajectory.probe_papers import probe_paper


ROOT = Path(__file__).resolve().parents[1]


def test_probe_adam_pdf_identifies_ml_experiment_risks() -> None:
    probe = probe_paper(ROOT / "papers" / "portfolio_inputs" / "adam.pdf")

    assert probe["paper_id"] == "adam"
    assert probe["paper_type"] == "ml_experiment"
    assert "hyperparameter_missing" in probe["likely_failure_types"]
    assert "metric_mismatch" in probe["likely_failure_types"]
    assert probe["recommended_runner"] == "skill_deep_run"


def test_probe_boyer_moore_pdf_identifies_existing_completed_run() -> None:
    probe = probe_paper(ROOT / "examples" / "boyer_moore_source" / "boyer_moore.pdf")

    assert probe["paper_id"] == "boyer_moore"
    assert probe["paper_type"] == "algorithm"
    assert "unavailable_original_benchmark_data" in probe["likely_failure_types"]
    assert probe["recommended_runner"] == "already_completed_skill_run"


def test_probe_raft_pdf_identifies_systems_risks() -> None:
    probe = probe_paper(ROOT / "papers" / "portfolio_inputs" / "raft.pdf")

    assert probe["paper_id"] == "raft"
    assert probe["paper_type"] == "systems"
    assert "environment_failure" in probe["likely_failure_types"]
    assert "workload_unavailable" in probe["likely_failure_types"]
