from __future__ import annotations

from typing import Any


WEIGHTS = {
    "task_completion": 0.20,
    "code_runs": 0.15,
    "smoke_pass": 0.15,
    "experiment_completed": 0.15,
    "claim_fidelity": 0.20,
    "report_honesty": 0.15,
}


def _confidence(signal_coverage: float, missing: list[str]) -> str:
    if signal_coverage >= 0.85 and not missing:
        return "high"
    if signal_coverage >= 0.50:
        return "medium"
    return "low"


def _status_score(status: str | None) -> float | None:
    if not status:
        return None
    normalized = status.lower()
    if normalized in {"success", "completed", "passed", "fully_reproduced"}:
        return 1.0
    if normalized.startswith("fully_reproduced"):
        return 1.0
    if normalized in {"approximately_reproduced", "partial_success", "partial"}:
        return 0.75
    if normalized in {"not_reproduced", "failure", "failed", "error"}:
        return 0.0
    return None


_SMOKE_PASS_WORDS = {"passed", "pass", "ok", "success", "succeeded", "true"}
_SMOKE_FAIL_WORDS = {"failed", "fail", "error", "false"}


def _smoke_score(smoke_summary: dict[str, Any] | None) -> float | None:
    """Prefer a dedicated smoke result file (results/smoke_summary.json).

    Reads a boolean `passed`, or a `status`/`result` string. Returns None when no
    smoke result was persisted, so the caller can fall back to check-derivation.
    """
    if not isinstance(smoke_summary, dict):
        return None
    if isinstance(smoke_summary.get("passed"), bool):
        return 1.0 if smoke_summary["passed"] else 0.0
    for key in ("status", "result", "smoke_status"):
        val = smoke_summary.get(key)
        if isinstance(val, str):
            low = val.strip().lower()
            if low in _SMOKE_PASS_WORDS:
                return 1.0
            if low in _SMOKE_FAIL_WORDS:
                return 0.0
    return None


def _bool_checks_score(checks: dict[str, Any] | list[Any] | None) -> float | None:
    if not checks:
        return None
    if isinstance(checks, dict):
        values = [value for value in checks.values() if isinstance(value, bool)]
    elif isinstance(checks, list):
        values = [
            item.get("passed")
            for item in checks
            if isinstance(item, dict) and isinstance(item.get("passed"), bool)
        ]
    else:
        values = []
    if not values:
        return None
    return sum(1 for value in values if value) / len(values)


def _claim_fidelity(evaluation: dict[str, Any]) -> float | None:
    status_score = _status_score(str(evaluation.get("status", "")))
    if status_score is not None:
        return status_score

    status_schema = evaluation.get("status_schema")
    if isinstance(status_schema, dict):
        evaluation = status_schema

    full = len(evaluation.get("fully_reproduced") or [])
    approximate = len(evaluation.get("approximately_reproduced") or [])
    missing = len(evaluation.get("not_reproduced") or [])
    total = full + approximate + missing
    if total == 0:
        return None
    return (full + 0.5 * approximate) / total


def _report_honesty(report_text: str | None) -> float | None:
    if not report_text:
        return None
    lowered = report_text.lower()
    has_full = "fully reproduced" in lowered or "fully_reproduced" in lowered
    has_approx = "approximately reproduced" in lowered or "approximately_reproduced" in lowered
    has_not = "not reproduced" in lowered or "not_reproduced" in lowered
    has_gap = "gap" in lowered or "missing" in lowered or "unavailable" in lowered
    if has_full and has_approx and has_not:
        return 1.0
    if has_approx and has_not and has_gap:
        return 1.0
    if has_approx or has_not or has_gap:
        return 0.75
    return 0.25


def compute_reward(
    *,
    evaluation: dict[str, Any] | None,
    summary: dict[str, Any] | None,
    report_text: str | None,
    smoke_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evaluation = evaluation or {}
    summary = summary or {}

    checks = summary.get("checks")
    if not isinstance(checks, dict | list):
        checks = evaluation.get("checks")
    if not isinstance(checks, dict | list):
        checks = summary.get("metrics")
    if not isinstance(checks, dict | list):
        checks = None

    code_runs = _status_score(str(summary.get("status", "")))
    if code_runs is None and isinstance(summary.get("result"), dict):
        code_runs = 1.0
    if code_runs is None:
        code_runs = _status_score(str(evaluation.get("status", "")))
    if code_runs is None:
        code_runs = _status_score(str(evaluation.get("overall_status", "")))
    if code_runs is None:
        code_runs = _status_score(str(evaluation.get("overall", "")))
    experiment_completed = code_runs
    # Prefer a persisted smoke result; fall back to boolean check derivation.
    smoke_pass = _smoke_score(smoke_summary)
    if smoke_pass is None:
        smoke_pass = _bool_checks_score(checks)
    claim_fidelity = _claim_fidelity(evaluation)
    task_completion = claim_fidelity if claim_fidelity is not None else code_runs
    report_honesty = _report_honesty(report_text)

    components = {
        "task_completion": task_completion,
        "code_runs": code_runs,
        "smoke_pass": smoke_pass,
        "experiment_completed": experiment_completed,
        "claim_fidelity": claim_fidelity,
        "report_honesty": report_honesty,
    }
    missing = [name for name, value in components.items() if value is None]
    denominator = sum(WEIGHTS[name] for name, value in components.items() if value is not None)
    overall = None
    if denominator:
        overall = sum(
            WEIGHTS[name] * float(value)
            for name, value in components.items()
            if value is not None
        ) / denominator
    strict_overall = sum(
        WEIGHTS[name] * float(value)
        for name, value in components.items()
        if value is not None
    )
    signal_coverage = denominator

    return {
        **components,
        "overall_score": round(overall, 4) if overall is not None else None,
        "strict_overall_score": round(strict_overall, 4),
        "signal_coverage": round(signal_coverage, 4),
        "confidence": _confidence(signal_coverage, missing),
        "weights": WEIGHTS,
        "missing_signals": missing,
    }
