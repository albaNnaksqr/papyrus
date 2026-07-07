> **SUPERSEDED 2026-07-07 by the v2 adversarial audit**
> (`wave1_codex_audit.md`/`.json`). The projection below was too optimistic:
> it bumped the two fixed dimensions but did NOT account for task #1's new
> criteria_checks rule retroactively docking the 4 pre-rule runs (which hide
> thresholds in code). The authoritative result: **no wave1 run is
> dataset-ready.** All portfolio-ready except tinystories (audit-only). See the
> "Authoritative bands" section at the bottom.

# Wave 1 Re-band (post trace-fix + normalization)

Date: 2026-07-07

## What changed since the codex audit

The original `wave1_codex_audit.md` scored every codex run with two systemic
penalties that were **infrastructure defects, not run defects**:

1. `trajectory_reconstruction = 1` — codex `agent_trace.jsonl` exposed zero
   turn-level `tool_results` (payloads were mis-nested under
   `tool_calls[].tool_result`) and `is_complete=false`.
2. `reward_and_labels = 1` — raw runs had no normalized `reward` / `labels` /
   `signal_coverage` / `confidence`, because normalization had not been run.

Both are now fixed:

- `export_trace.py` emits claude-shaped `tool_result` turns and resolves nested
  output dirs; all 9 codex traces re-exported from `~/.codex/sessions` rollouts
  (53–81 tool_results each, `is_complete=True`). No experiments rerun.
- `trajectory/normalize_runs.py` run over the completed set; every record now
  carries a 12-field decomposed `reward` with `signal_coverage` + `confidence`.

## Re-band (projection)

This is a **computed delta** from the audit's per-dimension scores, bumping only
the two dimensions the fixes resolve. It is a projection to be confirmed by a
fresh adversarial re-audit, not a re-audit itself.

| run | old | new | old band | new band | note |
|---|---:|---:|---|---|---|
| gptq_repro | 82.5 | 97.5 | portfolio | **dataset-ready** | clean |
| distill_repro | 82.5 | 97.5 | portfolio | **dataset-ready (as honest-failure negative sample)** | status=not_reproduced; valuable as a documented failure, not a positive repro |
| lottery_ticket_repro | 77.5 | 92.5 | portfolio | **dataset-ready** | clean |
| dpo_repro (claude) | 82.5 | 90.0 | portfolio | **dataset-ready** | traj already 2; only reward/labels bumped |
| tinystories_repro | 70.0 | 85.0 | portfolio | **borderline — hold at portfolio** | lands exactly on threshold; unresolved thin-evidence flag (loss trend called fully_reproduced from 8 stories / 1312 tokens) not addressed by these fixes |
| lora_repro | 67.5 | (new run) | audit-only | **re-audit — likely dataset-ready** | CUDA rerun DONE: real roberta-base + GLUE (MRPC/CoLA), status=fully_reproduced 4/4, outcome=success, overall=1.0; contract carries criteria_checks on all 4 targets |
| galore_repro | 67.5 | (new run) | audit-only | **re-audit — likely portfolio+** | CUDA rerun DONE: real roberta + GLUE/MRPC/C4, status=approximately_reproduced 3/3, overall=0.88; criteria_checks on all 3 targets |

### lora/galore are new runs, not delta-adjustable

The other 5 rows above are a *delta* from the original audit's per-dimension
scores (same run, two dimensions fixed). lora/galore are **different runs** —
CUDA reruns on real data that replaced the CPU-only synthetic-proxy versions
(archived at `codex/_cpu_only_archive/`). Their old 67.5 scored a different
artifact, so no delta applies. Signals are strong (real model+data, thresholds
now contract-declared, tool_results present, decomposed reward), so both should
clear well above audit-only — but their authoritative rubric score must come
from the fresh re-audit, not a projection.

## Recommendation

- Treat gptq, lottery_ticket, claude dpo as dataset-ready.
- Keep distill dataset-ready **but tagged as a negative/failure sample**.
- Keep tinystories at portfolio-ready until its thin-evidence eval is
  strengthened (more validation stories/tokens) or a re-audit confirms 85+.
- Confirm the whole projection with one fresh `wave1_codex_audit` pass on the
  fixed+normalized runs (cheap; the authoritative check).
- lora/galore: re-band after the CUDA rerun writes new evaluations.

## Authoritative bands (v2 adversarial audit, 2026-07-07)

| run | v1 | v2 | band | why not higher |
|---|---:|---:|---|---|
| lora_repro | 67.5 | 80.0 | portfolio-ready | real roberta+GLUE CUDA run, but fully_reproduced covers only a reduced substitute contract; no checkpoint/step-log saved; full GLUE/GPT-3 omissions not modeled as not_reproduced targets |
| lottery_ticket_repro | 77.5 | 77.5 | portfolio-ready | thresholds not in contract; evaluator trusts derived summary fields; paper-scale gap not a not_reproduced target |
| tinystories_repro | 70.0 | 77.5 | **audit-only** (rec overrides band) | thresholds hardcoded in src/contract_checks.py; loss-trend "fully_reproduced" rests on 8 stories / 1312 tokens |
| galore_repro | 67.5 | 77.5 | portfolio-ready | real but very bounded (512 train / 64 steps); memory-ratio gate 0.99 barely passes at 0.9898 (looks reverse-engineered); no checkpoint/log |
| distill_repro | 82.5 | 75.0 | portfolio-ready | dropped: no criteria_checks (new rule); honest failure, still a good negative sample |
| gptq_repro | 82.5 | 75.0 | portfolio-ready | dropped: no criteria_checks; evaluator hardcodes 0.10 tol + budget gates; no checkpoint/log |

**Net: 0 dataset-ready, 5 portfolio-ready, 1 audit-only (tinystories).**

### Fixes to reach dataset-ready (mostly cheap)
1. Migrate hardcoded thresholds into `reproduction_contract.json` criteria_checks
   for the 4 pre-rule runs (distill, lottery, tinystories, gptq) — or rerun them
   under the updated SKILL.md. Biggest single lever (contract-quality dimension).
2. Save per-step training logs + a checkpoint in each run dir (lora, galore, gptq)
   — executable-evidence dimension.
3. Represent paper-scale omissions (full GLUE / GPT-3 / full Table) as explicit
   `not_reproduced` evaluator targets rather than prose-only caveats.
4. tinystories: strengthen the eval (more validation stories/tokens) before the
   loss-trend subclaim can be called fully_reproduced.
5. galore: justify or tighten the 0.99 memory-ratio gate; a 0.9898 pass margin
   reads as reverse-engineered.
