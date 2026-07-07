"""preaudit_detectors.py — deterministic pre-audit red-flag linter.

Runs the *mechanical* half of the Papyrus adversarial audit over reproduction
project directories, so the expensive LLM audit only needs a stratified sample
plus the records this linter flags. Each detector is cheap and file-based; none
of them make the judgment calls (faithfulness of a reduced proxy, adequacy of
ambiguity decisions, scientific appropriateness of a threshold value) that stay
with the sampled LLM audit.

Finding levels:
  FAIL      — a hard, mechanically-certain defect; record should not ship as-is.
  WARN      — a smell worth a human/LLM look (thin margin, minimal experiment).
  NEEDS_LLM — mechanically undecidable; must be covered by the sampled LLM audit.

Gate decision per run: REJECT if any FAIL, else REVIEW if any WARN/NEEDS_LLM,
else PASS.

Usage:
  python -m trajectory.preaudit_detectors <project_dir> [<project_dir> ...] \
      [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

REPRODUCED_BUCKETS = ("fully_reproduced", "approximately_reproduced")
MIN_TRAINING_RECORDS = 10          # experiment-strength floor (steps/epochs)
THIN_REL_MARGIN = 0.01             # <1% pass margin reads as razor-thin


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _status_schema(evaluation: dict) -> dict:
    return evaluation.get("status_schema", evaluation) if isinstance(evaluation, dict) else {}


def _contract_criteria_checks(root: Path) -> list[dict]:
    """Collect every criteria_checks entry from reproduction_contract.json,
    wherever it is nested. Provenance (`source`) is a contract property; the
    evaluation.json need not echo it."""
    contract = _load_json(root / "reproduction_contract.json")
    out: list[dict] = []

    def walk(o: Any) -> None:
        if isinstance(o, dict):
            cc = o.get("criteria_checks")
            if isinstance(cc, list):
                out.extend(c for c in cc if isinstance(c, dict))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(contract)
    return out


def _iter_targets(evaluation: dict):
    ss = _status_schema(evaluation)
    for bucket in ("fully_reproduced", "approximately_reproduced", "not_reproduced"):
        for target in ss.get(bucket, []) or []:
            yield bucket, target


def _finding(level: str, check: str, detail: str) -> dict:
    return {"level": level, "check": check, "detail": detail}


# ── detectors ────────────────────────────────────────────────────────────────

def check_schema_and_paths(root: Path) -> list[dict]:
    out = []
    ev = root / "results" / "reproduction_evaluation.json"
    if not ev.exists():
        return [_finding("FAIL", "schema_paths", "missing results/reproduction_evaluation.json")]
    data = _load_json(ev)
    if not isinstance(data, dict) or not ("status" in data or "status_schema" in data):
        out.append(_finding("FAIL", "schema_paths",
                             "reproduction_evaluation.json lacks status/status_schema"))
    if not (root / "results" / "reproduction_summary.json").exists():
        out.append(_finding("FAIL", "schema_paths", "missing results/reproduction_summary.json"))
    return out


def check_phase6_normalized(root: Path) -> list[dict]:
    if not (root / "normalized_record.jsonl").exists():
        return [_finding("FAIL", "phase6_normalized",
                         "missing per-run normalized_record.jsonl (Phase 6 not run)")]
    return []


def check_trace_completeness(root: Path) -> list[dict]:
    trace = root / "agent_trace.jsonl"
    if not trace.exists():
        return [_finding("FAIL", "trace_completeness", "missing agent_trace.jsonl")]
    data = _load_json(trace)
    if not isinstance(data, dict):
        return [_finding("FAIL", "trace_completeness", "agent_trace.jsonl is not a single JSON object")]
    turns = data.get("turns", [])
    n_results = sum(len(t.get("tool_results", [])) for t in turns if isinstance(t, dict))
    out = []
    if n_results == 0:
        out.append(_finding("FAIL", "trace_completeness",
                            "zero turn-level tool_results (trajectory not replayable)"))
    if not data.get("trace_bounds", {}).get("end_found", data.get("stats", {}).get("is_complete")):
        out.append(_finding("WARN", "trace_completeness", "no end marker / is_complete not set"))
    return out


def _trains_model(root: Path, report_text: str) -> bool:
    if "no trained model — retention n/a" in report_text.lower():
        return False
    if (root / "results" / "training_log.jsonl").exists():
        return True
    for base in (root / "runs", root / "results" / "checkpoints"):
        if base.exists() and any(p.is_file() for p in base.rglob("*")):
            return True
    # default: assume it trains (safer — forces retention or an explicit N/A)
    return True


def check_retention(root: Path, report_text: str) -> list[dict]:
    if not _trains_model(root, report_text):
        return []
    out = []
    checkpoints = [p for base in (root / "results" / "checkpoints", root / "runs")
                   if base.exists() for p in base.rglob("*") if p.is_file()]
    if not checkpoints:
        out.append(_finding("FAIL", "retention", "trains a model but no checkpoint retained"))
    logs = []
    canonical = root / "results" / "training_log.jsonl"
    if canonical.exists():
        logs.append(canonical)
    if (root / "runs").exists():
        logs += [p for p in (root / "runs").rglob("training_log*.json*") if p.is_file()]
    if not logs:
        out.append(_finding("FAIL", "retention",
                            "trains a model but no per-step training log (results/training_log.jsonl)"))
    else:
        first = logs[0].read_text(encoding="utf-8").splitlines()[:1]
        rec = _load_json_line(first[0]) if first else None
        if not (isinstance(rec, dict) and "step_or_epoch" in rec and "loss" in rec):
            out.append(_finding("WARN", "retention",
                                f"training log {logs[0].name} lacks step_or_epoch/loss in first record"))
    return out


def _load_json_line(line: str):
    try:
        return json.loads(line)
    except Exception:
        return None


def check_threshold_provenance(root: Path, evaluation: dict) -> list[dict]:
    out = []
    # (A) every reproduced target must carry machine-readable checks
    ss = _status_schema(evaluation)
    for bucket in REPRODUCED_BUCKETS:
        for target in ss.get(bucket, []) or []:
            name = (target.get("item") or target.get("target") or "<unnamed>") if isinstance(target, dict) else str(target)
            checks = target.get("checks") if isinstance(target, dict) else None
            if not checks:
                out.append(_finding("FAIL", "threshold_provenance",
                                    f"reproduced target has no criteria checks: {name[:60]}"))
    # (A2) provenance labels live in reproduction_contract.json criteria_checks
    # (the evaluation.json need not echo `source`). A threshold with no source
    # label is unauditable — you cannot tell a paper-derived bound from an
    # inferred/substitute one, or from a reverse-engineered one picked to pass.
    # Read the CONTRACT, not the eval echo; skip silently if the contract uses a
    # schema without criteria_checks (nothing to assert).
    contract_checks = _contract_criteria_checks(root)
    unsourced = [c.get("name") or c.get("check") or "<check>"
                 for c in contract_checks if not c.get("source")]
    if contract_checks and unsourced:
        out.append(_finding("WARN", "threshold_provenance",
                            f"{len(unsourced)}/{len(contract_checks)} contract criteria_checks have no "
                            f"source label ({', '.join(map(str, unsourced[:4]))}) — provenance unauditable"))
    # (B) NO evaluator script may hardcode a numeric pass/fail threshold (the
    # "thresholds hidden in code" smell). The risk surface is EVERY evaluator
    # script, not just the canonical evaluate_reproduction.py — a gamed run can
    # bury the operative cutoff in a sibling (e.g. scripts/evaluate.py) to dodge a
    # linter that only reads the canonical file. So scan all scripts/evaluate*.py.
    # Deciding whether a literal is truly a pass/fail cutoff (vs a learning rate,
    # epsilon, etc.) needs context, so this is NEEDS_LLM.
    scripts_dir = root / "scripts"
    if scripts_dir.exists():
        for evaluator in sorted(scripts_dir.glob("evaluate*.py")):
            text = evaluator.read_text(encoding="utf-8", errors="ignore")
            for m in re.finditer(r"[<>]=?\s*(\d+\.\d+)|(?<![\w.])(\d+\.\d+)\s*[<>]=?", text):
                lit = m.group(1) or m.group(2)
                if float(lit) in (0.0, 1.0):
                    continue
                line = text[:m.start()].count("\n") + 1
                out.append(_finding("NEEDS_LLM", "threshold_provenance",
                                    f"float literal {lit} near a comparison in {evaluator.name}:{line} "
                                    f"— confirm it is not a hidden pass/fail threshold"))
                break  # one flag per file is enough signal
    return out


# Hyperparameter / config-fidelity knobs are SET to match the paper, so a
# check that asserts "the value I used == the paper's stated value" sits exactly
# at its bound by construction — that is fidelity, not a gamed performance
# margin. thin_margin is about *measured* metrics that barely clear a bar, so it
# skips these names.
_CONFIG_NAME = re.compile(
    r"(learning_rate|_lr\b|\blr_|\bseed\b|batch_size|\bepochs?\b|warmup|"
    r"weight_decay|momentum|\bbeta\d?\b|\balpha\b|\brank\b|dropout|"
    r"temperature|top_p|top_k)", re.I)


def check_thin_margins(evaluation: dict) -> list[dict]:
    # Only *ordered* comparisons on non-flag quantities can be "razor-thin".
    # Equality assertions (== / !=) are exact by design, and >=0 / >=1 style
    # presence/liveness/flag checks legitimately sit at the bound — neither is a
    # gamed margin, so both are excluded to avoid drowning the real signal.
    out = []
    for _bucket, target in _iter_targets(evaluation):
        if not isinstance(target, dict):
            continue
        for c in target.get("checks", []) or []:
            op, thr, meas = c.get("op"), c.get("threshold"), c.get("measured")
            if op not in (">=", "<=", ">", "<"):
                continue
            if not (c.get("passed") and isinstance(thr, (int, float)) and isinstance(meas, (int, float))):
                continue
            # config-fidelity assertion (lr/seed/rank/…), not a performance metric
            if _CONFIG_NAME.search(str(c.get("check", ""))):
                continue
            # Only continuous metrics can be gamed by a hair. Whole-number
            # thresholds are counts / dataset sizes / step budgets — legitimately
            # at-bound, and budget thinness is already caught by
            # experiment_strength — so restrict to fractional thresholds.
            if float(thr) == int(thr):
                continue
            if meas == thr:
                out.append(_finding("WARN", "thin_margin",
                                    f"'{c.get('check')}' passes at exactly the threshold ({meas} {op} {thr})"))
            elif abs(meas - thr) / (abs(thr) or 1.0) < THIN_REL_MARGIN:
                out.append(_finding("WARN", "thin_margin",
                                    f"'{c.get('check')}' passes by <1% margin ({meas} {op} {thr})"))
    return out


_STATUS_LINE = re.compile(r"(?:overall|evaluator)\s+(?:status|verdict)\s*[:=]\s*`?([a-z_]+)`?", re.I)


def check_report_eval_consistency(root: Path, evaluation: dict, report_text: str) -> list[dict]:
    eval_status = evaluation.get("status")
    m = _STATUS_LINE.search(report_text)
    if not m:
        return [_finding("WARN", "report_consistency",
                         "no explicit 'Overall/Evaluator status:' line found in report")]
    reported = m.group(1).lower()
    if eval_status and reported != str(eval_status).lower():
        return [_finding("FAIL", "report_consistency",
                         f"report says {reported} but eval.json says {eval_status}")]
    return []


def check_experiment_strength(root: Path, report_text: str) -> list[dict]:
    out = []
    log = root / "results" / "training_log.jsonl"
    if log.exists():
        n = sum(1 for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip())
        if 0 < n < MIN_TRAINING_RECORDS:
            out.append(_finding("WARN", "experiment_strength",
                                f"only {n} training-log records (< {MIN_TRAINING_RECORDS}); mechanism demo, "
                                f"not full experiment — caps band at portfolio-ready"))
    if _affirms_synthetic_data(report_text):
        out.append(_finding("NEEDS_LLM", "experiment_strength",
                            "report affirmatively mentions synthetic data — LLM must confirm it is not a synthetic stand-in"))
    return out


def _affirms_synthetic_data(report_text: str) -> bool:
    """True only if the report AFFIRMATIVELY says it used synthetic data.
    Honest disclosures that negate it — 'not synthetic', 'synthetic data: none',
    'non-synthetic' — are the opposite of a stand-in and must not flag (they were
    the dominant false-positive on real-data runs)."""
    for m in re.finditer(r"\bsynthetic\b", report_text, re.I):
        before = report_text[max(0, m.start() - 8):m.start()].lower()
        after = report_text[m.end():m.end() + 18].lower()
        neg_before = bool(re.search(r"\b(no|not|non|without|zero)\s*$", before)) or before.rstrip().endswith("non-")
        neg_after = bool(re.search(r"[\w\s]{0,10}\b(none|not used|n/?a)\b", after))
        if not (neg_before or neg_after):
            return True
    return False


def check_scope_honesty(evaluation: dict, report_text: str) -> list[dict]:
    ss = _status_schema(evaluation)
    n_not = len(ss.get("not_reproduced", []) or [])
    reduced = bool(re.search(r"\b(reduced|substitute|proxy|bounded)\b", report_text, re.I)) or \
        any(isinstance(t, dict) and any((c.get("threshold_source") == "substitute")
            for c in t.get("checks", []) or [])
            for _b, t in _iter_targets(evaluation))
    if reduced and n_not == 0:
        return [_finding("WARN", "scope_honesty",
                         "reduced-scale run has zero not_reproduced targets — paper-scale omissions may be unmodeled")]
    return []


def run_detectors(project_dir: str | Path) -> dict:
    root = Path(project_dir)
    evaluation = _load_json(root / "results" / "reproduction_evaluation.json") or {}
    report_text = ""
    rp = root / "REPRODUCTION_REPORT.md"
    if rp.exists():
        report_text = rp.read_text(encoding="utf-8", errors="ignore")

    findings: list[dict] = []
    findings += check_schema_and_paths(root)
    findings += check_phase6_normalized(root)
    findings += check_trace_completeness(root)
    findings += check_retention(root, report_text)
    if isinstance(evaluation, dict) and evaluation:
        findings += check_threshold_provenance(root, evaluation)
        findings += check_thin_margins(evaluation)
        findings += check_report_eval_consistency(root, evaluation, report_text)
        findings += check_scope_honesty(evaluation, report_text)
    findings += check_experiment_strength(root, report_text)

    levels = {f["level"] for f in findings}
    if "FAIL" in levels:
        decision = "REJECT"
    elif levels & {"WARN", "NEEDS_LLM"}:
        decision = "REVIEW"
    else:
        decision = "PASS"
    # Deterministic band ceiling: a below-floor training run is a mechanism demo,
    # so it may not be canonicalized as dataset-ready regardless of audit score.
    band_cap = None
    if any(f["check"] == "experiment_strength" and "caps band" in f["detail"] for f in findings):
        band_cap = "portfolio-ready"
    return {
        "run": str(root),
        "decision": decision,
        "band_cap": band_cap,
        "counts": {lv: sum(1 for f in findings if f["level"] == lv)
                   for lv in ("FAIL", "WARN", "NEEDS_LLM")},
        "findings": findings,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Papyrus pre-audit red-flag linter")
    ap.add_argument("project_dirs", nargs="+")
    ap.add_argument("--json", help="write full report JSON to this path")
    args = ap.parse_args()

    reports = [run_detectors(d) for d in args.project_dirs]
    if args.json:
        Path(args.json).write_text(json.dumps(reports, ensure_ascii=False, indent=2) + "\n",
                                   encoding="utf-8")
    for r in reports:
        name = Path(r["run"]).name
        c = r["counts"]
        cap = f" cap<={r['band_cap']}" if r.get("band_cap") else ""
        print(f"{name:24} {r['decision']:7} FAIL={c['FAIL']} WARN={c['WARN']} NEEDS_LLM={c['NEEDS_LLM']}{cap}")
        for f in r["findings"]:
            print(f"    [{f['level']:9}] {f['check']}: {f['detail']}")


if __name__ == "__main__":
    main()
