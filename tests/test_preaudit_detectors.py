from __future__ import annotations

import json
from pathlib import Path

from trajectory.preaudit_detectors import (
    check_experiment_strength,
    check_report_eval_consistency,
    check_thin_margins,
    check_threshold_provenance,
)


def test_synthetic_negations_do_not_raise_experiment_strength_flag(tmp_path: Path) -> None:
    negated_reports = [
        "Dataset note: not synthetic. Real examples were used.",
        "Synthetic data: none. Inputs came from the public benchmark.",
    ]

    for report in negated_reports:
        findings = check_experiment_strength(tmp_path, report)
        assert not [
            f
            for f in findings
            if f["check"] == "experiment_strength" and "synthetic data" in f["detail"]
        ]


def test_affirmative_synthetic_report_raises_experiment_strength_flag(tmp_path: Path) -> None:
    findings = check_experiment_strength(
        tmp_path,
        "The model was trained on a synthetic fixture before evaluation.",
    )

    assert any(
        f["check"] == "experiment_strength"
        and f["level"] == "NEEDS_LLM"
        and "synthetic data" in f["detail"]
        for f in findings
    )


def test_thin_margin_skips_config_fidelity_but_flags_performance_metric() -> None:
    evaluation = {
        "status_schema": {
            "approximately_reproduced": [
                {
                    "item": "bounded target",
                    "checks": [
                        {
                            "check": "adam_learning_rate",
                            "op": ">=",
                            "threshold": 0.001,
                            "measured": 0.001,
                            "passed": True,
                        },
                        {
                            "check": "accuracy",
                            "op": ">=",
                            "threshold": 0.90,
                            "measured": 0.90,
                            "passed": True,
                        },
                    ],
                }
            ]
        }
    }

    findings = check_thin_margins(evaluation)

    assert [f["check"] for f in findings] == ["thin_margin"]
    assert "accuracy" in findings[0]["detail"]
    assert "adam_learning_rate" not in findings[0]["detail"]


def test_threshold_provenance_warns_only_for_contract_criteria_without_source(
    tmp_path: Path,
) -> None:
    evaluation = {
        "status_schema": {
            "fully_reproduced": [
                {
                    "item": "target",
                    "checks": [{"check": "accuracy", "passed": True}],
                }
            ]
        }
    }
    contract = {
        "targets": [
            {
                "criteria_checks": [
                    {"name": "accuracy", "source": "paper_table_1"},
                    {"name": "f1_score", "source": None},
                ]
            }
        ]
    }
    (tmp_path / "reproduction_contract.json").write_text(
        json.dumps(contract),
        encoding="utf-8",
    )

    findings = check_threshold_provenance(tmp_path, evaluation)

    warnings = [
        f
        for f in findings
        if f["check"] == "threshold_provenance" and f["level"] == "WARN"
    ]
    assert len(warnings) == 1
    assert "f1_score" in warnings[0]["detail"]
    assert "accuracy" not in warnings[0]["detail"]


def test_report_eval_status_mismatch_is_fail(tmp_path: Path) -> None:
    findings = check_report_eval_consistency(
        tmp_path,
        {"status": "approximately_reproduced"},
        "Overall status: `fully_reproduced`",
    )

    assert findings == [
        {
            "level": "FAIL",
            "check": "report_consistency",
            "detail": "report says fully_reproduced but eval.json says approximately_reproduced",
        }
    ]
