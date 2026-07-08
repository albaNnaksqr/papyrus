"""scorecard.py — reproducible band scoring for papyrus trajectory records.

Turns the 8-dimension quality rubric into a scorecard that is deterministic
where it can be and anchored where it cannot. Each dimension scores 0/1/2 and is
weighted; the weighted points (0-100) map to a readiness band.

Design for reproducibility:
  * 5 dimensions (3,4,5,7,8 — 60 pts) are FULLY MECHANICAL: computed from the
    normalized_record + preaudit_detectors + on-disk artifacts. Same inputs →
    same score, every time.
  * 3 dimensions (1,2,6 — 40 pts) are HYBRID: the mechanical layer computes a
    CEILING (you cannot score 2 if the structure is absent), and an anchored
    LLM judgment may only CONFIRM or LOWER it (grounding, proxy faithfulness,
    label honesty). The LLM decision is supplied as DATA via an overrides file
    (run -> dim -> {score, note}) so a band is reproducible from its inputs, not
    re-derived by vibes.

Band = f(total points, deterministic caps). Caps come from
preaudit_detectors.band_cap (e.g. a <10-step training run caps at portfolio).

Usage:
  python -m trajectory.scorecard <run_dir> [<run_dir> ...] \
      [--llm overrides.json] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from trajectory.preaudit_detectors import (
    run_detectors, _contract_criteria_checks, _status_schema, _load_json,
)

# dimension weight = max points for that dimension (0/1/2 → 0/half/full)
DIMENSIONS = {
    1: ("paper_claim_grounding", 15, "hybrid"),
    2: ("contract_quality", 15, "hybrid"),
    3: ("trajectory_reconstruction", 15, "mechanical"),
    4: ("executable_evidence", 15, "mechanical"),
    5: ("reward_and_labels", 15, "mechanical"),
    6: ("failure_taxonomy", 10, "hybrid"),
    7: ("provenance_auditability", 10, "mechanical"),
    8: ("cross_agent_comparability", 5, "mechanical"),
}

LLM_ANCHORS = {
    1: ("Is the scored target the paper's real falsifiable claim, traceable to a "
        "specific table/figure/section (not the title or benchmark name)? "
        "title-only grounding → cap 1; mislabeled/ungrounded → 0."),
    2: ("Do the criteria actually constrain behaviour (not just 'tests pass'), and "
        "is the reduced scope a FAITHFUL bounded proxy (not a thin/degenerate "
        "stand-in passed off as the paper claim)? vacuous criteria or overclaimed "
        "proxy → cap 1; proxy masquerading as full claim → 0."),
    6: ("Are the failure / fidelity labels HONEST and COMPLETE — is there a real "
        "gap (synthetic fixture, thin eval, released-data leaning, metric "
        "mismatch) that is NOT labelled? an unlabelled real gap → cap 1; a hidden "
        "gap that inflates the outcome → 0."),
}

BANDS = [(85, "dataset-ready"), (70, "portfolio-ready"), (50, "audit-only"), (0, "reject")]
_BAND_RANK = {"dataset-ready": 3, "portfolio-ready": 2, "audit-only": 1, "reject": 0}


def _band(points: float) -> str:
    for lo, name in BANDS:
        if points >= lo:
            return name
    return "reject"


def _cap_band(band: str, cap: str | None) -> str:
    if cap and _BAND_RANK.get(cap, 3) < _BAND_RANK.get(band, 3):
        return cap
    return band


def _nr(run: Path) -> dict:
    rec = run / "normalized_record.jsonl"
    if not rec.exists():
        return {}
    line = rec.read_text(encoding="utf-8").splitlines()
    return json.loads(line[0]) if line else {}


def _has_findings(lint: dict, check: str, levels=("FAIL", "WARN")) -> bool:
    return any(f["check"] == check and f["level"] in levels for f in lint["findings"])


# ── mechanical dimension scorers: (nr, lint, run) -> (score, rationale) ────────

def _d3_trajectory(nr, lint, run):
    t = nr.get("trajectory", {})
    if _has_findings(lint, "trace_completeness", ("FAIL",)) or not t.get("turn_count"):
        return 0, "no replayable trace / trace_completeness FAIL"
    tr = len(t.get("tool_results", []) or [])
    ok = tr > 0 and t.get("phase_spans") and (t.get("commands") or t.get("file_edits")) and "repair_attempts" in t
    if ok:
        return 2, f"{t['turn_count']} turns, {tr} tool_results, {len(t.get('phase_spans',[]))} phases, cmds+edits+repair tracked"
    return 1, "trace present but missing tool_results / phase_spans / cmds+edits"


def _d4_evidence(nr, lint, run):
    a = nr.get("artifacts", {})
    r = nr.get("reward", {})
    report = (run / "REPRODUCTION_REPORT.md")
    notrain = report.exists() and "retention n/a" in report.read_text(encoding="utf-8", errors="ignore").lower()
    core = all(a.get(k) for k in ("experiment_script", "evaluator_script", "result_files", "reproduction_report"))
    ran = r.get("code_runs") and (r.get("experiment_completed") or notrain)
    if core and ran:
        return 2, "experiment+evaluator+results+report all present and executed"
    if a.get("result_files") or a.get("reproduction_report"):
        return 1, "partial executable evidence"
    return 0, "no runnable evidence"


def _d5_reward(nr, lint, run):
    r = nr.get("reward", {})
    l = nr.get("labels", {})
    comps = [r.get(k) for k in ("task_completion", "code_runs", "experiment_completed",
                                "claim_fidelity", "report_honesty")]
    decomposed = sum(1 for c in comps if c is not None) >= 4
    coverage_ok = r.get("signal_coverage") is not None and isinstance(r.get("missing_signals"), list)
    outcome = (l.get("outcome") or "").lower()
    ftypes = l.get("failure_types") or []
    inconsistent = outcome in ("success", "fully_reproduced") and ftypes
    if decomposed and coverage_ok and r.get("strict_overall_score") is not None and not inconsistent:
        return 2, f"decomposed reward, coverage={r.get('signal_coverage')}, outcome↔labels consistent"
    if decomposed or coverage_ok:
        return 1, "reward present but partial / coverage or consistency gap"
    return 0, "reward missing or outcome↔labels inconsistent"


def _d7_provenance(nr, lint, run):
    p = nr.get("provenance", {})
    src = p.get("source_files") or []
    exist = src and all((run / s if not Path(s).is_absolute() else Path(s)).exists()
                        or (run / Path(s).name).exists() for s in src[:12])
    null_source = _has_findings(lint, "threshold_provenance", ("WARN",))
    if src and exist and p.get("normalizer_version") and not null_source:
        return 2, f"{len(src)} source files present, normalizer {p.get('normalizer_version')}, thresholds sourced"
    if src:
        return 1, "provenance present but some source files missing or thresholds unsourced"
    return 0, "no provenance"


def _d8_comparability(nr, lint, run):
    r = nr.get("run", {})
    t = nr.get("trajectory", {})
    core = all(r.get(k) not in (None, "") for k in ("runner", "model", "agent_host", "wall_time_seconds"))
    actions = t.get("phase_spans") and t.get("tool_calls_by_name")
    if core and r.get("token_usage") and actions:
        return 2, "full runner/model/host/timing/token metadata + normalized actions"
    if core:
        return 1, "core metadata present, token usage or action classes thin"
    return 0, "missing comparability metadata"


# ── hybrid dimension CEILINGS: (nr, lint, run) -> (ceiling, rationale) ─────────

def _d1_ceiling(nr, lint, run):
    paper = nr.get("paper", {})
    tc = paper.get("target_claims")
    em = paper.get("expected_metrics")
    if not tc:
        return 0, "no target_claims recorded"
    # A structured claim (target + scope) carrying expected_metrics (name /
    # direction / formula) is well-grounded. The separate `claim_contract` file
    # is a host-specific artifact — absent for every codex run — so it is NOT
    # required; requiring it would cap every codex record at 1 spuriously.
    structured = isinstance(tc, list) and tc and isinstance(tc[0], dict) and (tc[0].get("target") or tc[0].get("claim"))
    if structured and em:
        return 2, f"{len(tc)} structured target_claims + expected_metrics (name/direction/formula)"
    return 1, "target_claims present but unstructured or no expected_metrics"


def _d2_ceiling(nr, lint, run):
    c = nr.get("contracts", {})
    criteria = _contract_criteria_checks(run)
    ev = _load_json(run / "results" / "reproduction_evaluation.json") or {}
    n_notrepro = len(_status_schema(ev).get("not_reproduced", []) or [])
    prov_flag = _has_findings(lint, "threshold_provenance")
    have = bool(criteria) and c.get("gap_report") and c.get("ambiguity_audit") and n_notrepro > 0
    if have and not prov_flag:
        return 2, f"{len(criteria)} sourced criteria, gap+ambiguity reports, {n_notrepro} not_reproduced targets"
    if criteria:
        return 1, "criteria present but missing gap/ambiguity/not_reproduced or provenance-flagged"
    return 0, "no criteria_checks"


def _d6_ceiling(nr, lint, run):
    # "Failure taxonomy" credits honest labelling of GAPS/fidelity limits. For a
    # bounded reproduction the gaps are the paper-scale omissions, declared as
    # not_reproduced TARGETS in the contract — that is the taxonomy, even when
    # labels.failure_types is empty (the run met its in-scope target cleanly).
    l = nr.get("labels", {})
    fa = nr.get("failure_analysis", {})
    ftypes = l.get("failure_types") or []
    outcome = (l.get("outcome") or "").lower()
    ev = _load_json(run / "results" / "reproduction_evaluation.json") or {}
    n_nr = len(_status_schema(ev).get("not_reproduced", []) or [])
    if outcome in ("success", "fully_reproduced") and not ftypes and n_nr == 0:
        return 2, "clean full success, no gaps to label"
    if ftypes and fa.get("root_cause"):
        return 2, f"failure labels {ftypes} + root_cause + {n_nr} not_reproduced targets"
    if n_nr >= 2:
        return 2, f"{n_nr} honest not_reproduced scope-boundary targets"
    if ftypes or n_nr:
        return 1, "gap labelling present but thin (no root_cause / single target)"
    return 0, "outcome implies gaps but nothing labelled"


_MECH = {3: _d3_trajectory, 4: _d4_evidence, 5: _d5_reward, 7: _d7_provenance, 8: _d8_comparability}
_HYB = {1: _d1_ceiling, 2: _d2_ceiling, 6: _d6_ceiling}


def score_run(run_dir: str | Path, llm: dict | None = None) -> dict:
    run = Path(run_dir)
    nr = _nr(run)
    lint = run_detectors(run)
    llm = llm or {}
    dims = {}
    for i, (name, weight, kind) in DIMENSIONS.items():
        if kind == "mechanical":
            score, why = _MECH[i](nr, lint, run)
            dims[i] = {"name": name, "weight": weight, "kind": kind,
                       "score": score, "rationale": why}
        else:
            ceiling, why = _HYB[i](nr, lint, run)
            ov = llm.get(str(i)) or llm.get(i)
            llm_score = ov.get("score") if isinstance(ov, dict) else None
            final = min(ceiling, llm_score) if llm_score is not None else None
            dims[i] = {"name": name, "weight": weight, "kind": kind,
                       "ceiling": ceiling, "rationale": why,
                       "llm_anchor": LLM_ANCHORS[i],
                       "llm_score": llm_score,
                       "llm_note": ov.get("note") if isinstance(ov, dict) else None,
                       "score": final}

    pending = [i for i, d in dims.items() if d["score"] is None]
    # point estimate uses filled scores; ceiling estimate assumes hybrids confirm
    def _pts(use_ceiling):
        tot = 0.0
        for i, d in dims.items():
            s = d["score"]
            if s is None:
                s = d["ceiling"] if use_ceiling else 0
            tot += (s / 2) * d["weight"]
        return round(tot, 1)

    cap = lint.get("band_cap")
    result = {
        "run": str(run), "dimensions": dims, "band_cap": cap,
        "linter_decision": lint["decision"], "pending_llm": pending,
    }
    if pending:
        result["points_min"] = _pts(False)
        result["points_if_ceilings"] = _pts(True)
        result["band_range"] = [_cap_band(_band(result["points_min"]), cap),
                                _cap_band(_band(result["points_if_ceilings"]), cap)]
    else:
        pts = _pts(False)
        result["points"] = pts
        result["band"] = _cap_band(_band(pts), cap)
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description="Papyrus reproducible band scorecard")
    ap.add_argument("run_dirs", nargs="+")
    ap.add_argument("--llm", help="JSON overrides: {run_name: {dim: {score, note}}}")
    ap.add_argument("--json", help="write full scorecards to this path")
    args = ap.parse_args()

    overrides = json.loads(Path(args.llm).read_text()) if args.llm else {}
    out = []
    for d in args.run_dirs:
        name = Path(d).name
        out.append(score_run(d, overrides.get(name)))
    if args.json:
        Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for r in out:
        name = Path(r["run"]).name
        if r.get("pending_llm"):
            print(f"{name:26} band {r['band_range'][0]:>15} .. {r['band_range'][1]:<15} "
                  f"(pts {r['points_min']}–{r['points_if_ceilings']}, LLM pending: dims {r['pending_llm']})")
        else:
            cap = f" cap<={r['band_cap']}" if r.get("band_cap") else ""
            print(f"{name:26} band {r['band']:>15}  pts {r['points']}{cap}")


if __name__ == "__main__":
    main()
