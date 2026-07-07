# Proof Spike — anti-gaming detector plant-and-catch

**This directory is a CONTROLLED ADVERSARIAL TEST SET. It is NOT part of the
Papyrus data product.** Every `*_G*` record here is a deliberately gamed variant
of a real dataset-ready run, planted to measure whether the mechanical
`trajectory.preaudit_detectors` layer separates honest runs from gamed ones.
None of these records may be normalized into or shipped as trajectory data.

## Question this spike answers

> Can the existing anti-gaming detectors separate honest reproduction runs from
> gamed ones, and how many gamed runs would a naive success-rate filter wave
> through?

This is a *spike*: a one-shot, zero-cost probe to validate (or falsify) the
core resume claim — that Papyrus's audit layer catches reward hacking — BEFORE
spending on a 30-50 paper batch. The interesting result is the **misses**, not
the catches: they map exactly where mechanical detection breaks and a human/LLM
audit (or a trained trajectory verifier) is still required.

## Method & honesty guardrails

- **Bases**: the 3 audited dataset-ready wave1 runs (lottery_ticket, gptq, lora).
- **Plants**: 6 gamed variants across the 4 real gaming modes we have actually
  observed in audits (reverse-engineered threshold, threshold hidden in code,
  thin-evidence-as-success, report/eval inconsistency). Modes were defined from
  human reasoning first.
- **Boundary mapping, disclosed**: the author knows the detector internals, so
  each mode is planted in both a *crude* form (predicted CATCH) and a *subtle*
  form (predicted MISS) to locate the detection boundary honestly rather than to
  flatter the catch rate.
- **Controls**: the 3 bases are copied unchanged as honest negatives; a false
  REJECT on any of them is a false positive and is reported as such.
- **Ground truth is the plant, not the detector** — `ground_truth.json` records
  each record's true class and the human-visible tell, independent of what the
  detector says.

## Files

- `build_spike.py` — reproducibly copies bases and applies each plant.
- `ground_truth.json` — per-record true class, mode, tell, and prediction.
- `run_spike.py` — runs detectors + naive filter over all records, scores them
  against ground truth, writes `spike_results.json` + `spike_report.md`.
- `records/` — the 9 built records (3 honest + 6 gamed).
