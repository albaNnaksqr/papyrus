#!/usr/bin/env python3
"""run_spike.py — run detectors + naive filter over the plant-and-catch set.

For every built record: run the real trajectory.preaudit_detectors, and also a
"naive success-rate filter" (accept anything that self-reports success). Score
both against ground_truth.json and emit spike_results.json + spike_report.md.

Run:  python output/proof_spike/run_spike.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO))
from trajectory.preaudit_detectors import run_detectors, REPRODUCED_BUCKETS  # noqa: E402


def naive_filter_accepts(record_dir: Path) -> bool:
    """A naive reviewer keeps a run as good data if it self-reports success:
    evaluation status is a reproduced bucket AND the summary status is completed.
    Gaming is invisible to this filter by construction."""
    ev = record_dir / "results" / "reproduction_evaluation.json"
    su = record_dir / "results" / "reproduction_summary.json"
    try:
        status = json.loads(ev.read_text(encoding="utf-8")).get("status", "")
    except Exception:
        status = ""
    try:
        summ_status = json.loads(su.read_text(encoding="utf-8")).get("status", "")
    except Exception:
        summ_status = ""
    return status in REPRODUCED_BUCKETS and summ_status in ("completed", "")


def main() -> None:
    truth = {t["record"]: t for t in json.loads((ROOT / "ground_truth.json").read_text())}
    rows = []
    for name, t in truth.items():
        d = ROOT / "records" / name
        det = run_detectors(d)
        detector_flags = det["decision"] != "PASS"          # REVIEW or REJECT = flagged
        naive_keeps = naive_filter_accepts(d)
        rows.append({
            "record": name,
            "true_class": t["true_class"],
            "mode": t["mode"],
            "predicted": t["predicted_detector"],
            "detector_decision": det["decision"],
            "detector_flags": detector_flags,
            "naive_filter_keeps": naive_keeps,
            "counts": det["counts"],
            "findings": [f"[{f['level']}] {f['check']}: {f['detail']}" for f in det["findings"]],
            "tell": t["tell"],
        })

    gamed = [r for r in rows if r["true_class"] == "gamed"]
    honest = [r for r in rows if r["true_class"] == "honest"]
    n_gamed = len(gamed)
    caught = [r for r in gamed if r["detector_flags"]]
    missed = [r for r in gamed if not r["detector_flags"]]
    naive_leaks = [r for r in gamed if r["naive_filter_keeps"]]
    honest_false_reject = [r for r in honest if r["detector_decision"] == "REJECT"]

    summary = {
        "n_records": len(rows),
        "n_gamed": n_gamed,
        "n_honest": len(honest),
        "detector_catch_rate": f"{len(caught)}/{n_gamed}",
        "detector_misses": [r["record"] for r in missed],
        "naive_filter_leak_rate": f"{len(naive_leaks)}/{n_gamed}",
        "honest_false_reject": f"{len(honest_false_reject)}/{len(honest)}",
        "prediction_hits": sum(
            1 for r in gamed
            if (r["predicted"] == "CATCH") == r["detector_flags"]
        ),
    }
    out = {"summary": summary, "rows": rows}
    (ROOT / "spike_results.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # ── human report ──
    L = []
    L.append("# Proof Spike — results\n")
    L.append("Controlled plant-and-catch over 3 audited dataset-ready runs. "
             "Ground truth = the plant, not the detector.\n")
    L.append("## Headline\n")
    L.append(f"- **Detector catch rate (gamed flagged): {summary['detector_catch_rate']}**")
    L.append(f"- **Naive success-rate filter leak rate: {summary['naive_filter_leak_rate']}** "
             "(gamed runs it would keep as training data)")
    L.append(f"- Honest false-reject rate: {summary['honest_false_reject']}")
    L.append(f"- Detector misses: {', '.join(summary['detector_misses']) or 'none'}\n")
    L.append("## Per-record\n")
    L.append("| record | class | mode | detector | flagged? | naive keeps? | pred |")
    L.append("|---|---|---|---|---|---|---|")
    for r in rows:
        L.append(f"| {r['record']} | {r['true_class']} | {r['mode'] or '-'} | "
                 f"{r['detector_decision']} | {'yes' if r['detector_flags'] else 'NO'} | "
                 f"{'yes' if r['naive_filter_keeps'] else 'no'} | {r['predicted']} |")
    L.append("\n## Findings per record\n")
    for r in rows:
        L.append(f"### {r['record']} ({r['true_class']}, mode {r['mode']})")
        if r["tell"]:
            L.append(f"- **planted tell**: {r['tell']}")
        L.append(f"- detector: **{r['detector_decision']}** "
                 f"(FAIL={r['counts']['FAIL']} WARN={r['counts']['WARN']} "
                 f"NEEDS_LLM={r['counts']['NEEDS_LLM']})")
        for f in r["findings"]:
            L.append(f"  - {f}")
        L.append("")
    (ROOT / "spike_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
