# Gate 3 — Pre-audit red-flag detectors

Date: 2026-07-07
Tool: `trajectory/preaudit_detectors.py`
Run: `python -m trajectory.preaudit_detectors <project_dir> ... [--json out.json]`

## Purpose

A deterministic linter that runs the *mechanical* half of the adversarial audit
so the expensive LLM audit only needs a stratified sample + the records this
linter flags. Cost drops from O(records) to O(sample + flagged).

## Checks (level in parens)

- **schema_paths** (FAIL) — results/reproduction_evaluation.json at exact path
  with status/status_schema; results/reproduction_summary.json present.
- **phase6_normalized** (FAIL) — per-run normalized_record.jsonl exists.
- **trace_completeness** (FAIL/WARN) — agent_trace.jsonl has non-empty
  turn-level tool_results; end marker / is_complete set.
- **retention** (FAIL/WARN) — a training run has a checkpoint + a per-step
  training log (results/training_log.jsonl or runs/<variant>/…) whose first
  record has step_or_epoch+loss; pure-algorithm runs use the report N/A escape.
- **threshold_provenance** (FAIL/NEEDS_LLM) — every reproduced target carries
  machine-readable criteria checks (FAIL if a reproduced target has none); a
  non-trivial float literal near a comparison in evaluate_reproduction.py is
  flagged NEEDS_LLM (could be a hidden pass/fail threshold).
- **thin_margin** (WARN) — a continuous (fractional-threshold) metric that
  passes at exactly the bound or by <1% — the reverse-engineered-threshold
  smell. Whole-number counts/sizes/step-budgets are excluded (legitimately
  at-bound; budget thinness is covered by experiment_strength).
- **report_consistency** (FAIL/WARN) — REPRODUCTION_REPORT.md's stated
  Overall/Evaluator status/verdict equals eval.json status. (Parses the status
  line specifically, so a `## Fully Reproduced` section header is not mistaken
  for the overall verdict.)
- **experiment_strength** (WARN/NEEDS_LLM) — training log below the min-records
  floor (10) is a mechanism demo not a full experiment; a "synthetic" mention
  without "real data" is NEEDS_LLM.
- **scope_honesty** (WARN) — a reduced/substitute/proxy run with zero
  not_reproduced targets may have unmodeled paper-scale omissions.

## Gate decision

`REJECT` if any FAIL · `REVIEW` if any WARN/NEEDS_LLM · else `PASS`.

## Validation against the 6 labeled wave1 runs

Reproduces the manual v1–v4 triage exactly:

| run | linter | audit band (v4) |
|---|---|---|
| lottery_ticket | PASS | dataset-ready |
| gptq | PASS | dataset-ready |
| lora | PASS | dataset-ready |
| tinystories | PASS | portfolio |
| galore | REVIEW (8-step thinness) | dataset-ready (I flagged as borderline) |
| distill | REJECT (no norm_record / no training_log / no criteria checks) | audit-only |

## Boundary (what the linter does NOT decide — stays with the sampled LLM audit)

- Faithfulness of a reduced proxy to the paper's claim (this is why tinystories
  PASSes the linter yet the LLM audit held it at portfolio for using a reduced
  local Transformer instead of the exact GPT-Neo — a genuine judgment call).
- Whether paper-scale omissions are *adequately* modeled (linter only flags the
  zero-omission case).
- Scientific appropriateness of a threshold value (only whether it is declared
  and not razor-thin).
- Reasoning quality / ambiguity-decision soundness in the trajectory.

## Scale-up use

Run over every candidate record: REJECT → auto-rework (no LLM spend); PASS/REVIEW
→ eligible; send all REVIEW + NEEDS_LLM records plus a stratified sample of PASS
records to the LLM adversarial audit.
