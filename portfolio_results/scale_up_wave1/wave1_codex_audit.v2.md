# Wave 1 Codex Second Adversarial Audit

Audited runs:

- `output/scale_up_wave1/codex/distill_repro`
- `output/scale_up_wave1/codex/lottery_ticket_repro`
- `output/scale_up_wave1/codex/tinystories_repro`
- `output/scale_up_wave1/codex/gptq_repro`
- `output/scale_up_wave1/codex/lora_repro`
- `output/scale_up_wave1/codex/galore_repro`

Rubric: `docs/trajectory-dataset-quality-rubric.md`. Weighted total uses
`score / 2 * dimension_weight`.

Adversarial posture: each run was treated as gamed until on-disk artifacts,
evaluator reruns, contracts, reports, traces, and cached external assets proved
otherwise.

## Evaluator Rerun Check

Evaluators were rerun from temp copies under
`/tmp/papyrus_wave1_second_audit_is8wy55z`, using
`output/scale_up_wave1/_cuda_venv/bin/python`. The audited project directories
were not modified. Comparison ignores `evaluated_at` drift only.

| run | original status | rerun status | match ignoring timestamp | auditor note |
|---|---:|---:|---:|---|
| `distill_repro` | `not_reproduced` | `not_reproduced` | yes | JSON reproduced exactly. |
| `lottery_ticket_repro` | `approximately_reproduced` | `approximately_reproduced` | yes | JSON reproduced exactly. |
| `tinystories_repro` | `approximately_reproduced` | `approximately_reproduced` | yes | Exact JSON differed only by `evaluated_at`. |
| `gptq_repro` | `approximately_reproduced` | `approximately_reproduced` | yes | JSON reproduced exactly. |
| `lora_repro` | `fully_reproduced` | `fully_reproduced` | yes | JSON reproduced exactly. |
| `galore_repro` | `approximately_reproduced` | `approximately_reproduced` | yes | JSON reproduced exactly. |

## Portfolio Summary

| run | v2 total | band | recommendation | v1 delta | main red flags |
|---|---:|---|---|---:|---|
| `distill_repro` | 75.0 | Portfolio-ready | portfolio-ready | -7.5 | Contract has no `criteria_checks`; trace phase labels only show `phase_2`. |
| `lottery_ticket_repro` | 77.5 | Portfolio-ready | portfolio-ready | +0.0 | No `criteria_checks`; evaluator trusts derived summary booleans; paper-scale gaps are not evaluator targets. |
| `tinystories_repro` | 77.5 | Portfolio-ready | audit-only | +7.5 | Hardcoded 25%/0.50/0.35 evaluator thresholds; only 8 validation stories and 1,312 tokens per model. |
| `gptq_repro` | 75.0 | Portfolio-ready | portfolio-ready | -7.5 | No `criteria_checks`; evaluator hardcodes 10% tolerance and 128/2048 paper-budget gates. |
| `lora_repro` | 80.0 | Portfolio-ready | portfolio-ready | +12.5 | Real CUDA/GLUE rerun, but top-level `fully_reproduced` is only for a reduced substitute contract. |
| `galore_repro` | 77.5 | Portfolio-ready | portfolio-ready | +10.0 | Real CUDA/GLUE rerun, but contract thresholds are low/local and one memory ratio barely passes. |

Portfolio-level findings:

- The infrastructure fix took: all six `agent_trace.jsonl` files now have
  structured start/end marker fields, `stats.is_complete=true`, non-zero
  turn-level `tool_results`, and non-empty result payloads.
- The old "zero tool result payloads" red flag is resolved for every audited
  Codex run.
- The new threshold-provenance hard rule is not retroactively satisfied by
  `distill_repro`, `lottery_ticket_repro`, `tinystories_repro`, or `gptq_repro`.
  Only the new CUDA LoRA/GaLore reruns declare evaluator thresholds under
  `reproduction_contract.json` `criteria_checks`.
- No run is recommended as dataset-ready yet. The traces are better, but the
  directories still lack normalized reward/label records, signal coverage,
  confidence, token/cost metadata, and normalized action classes. LoRA/GaLore
  also lack saved per-step training logs or local fine-tuned checkpoints.

## Trace Completeness Check

| run | turns | tool calls | tool results | non-empty results | `is_complete` | structured markers | phase coverage note |
|---|---:|---:|---:|---:|---:|---:|---|
| `distill_repro` | 81 | 67 | 66 | 66 | true | yes | Weak: detected phases only `phase_2`. |
| `lottery_ticket_repro` | 82 | 73 | 72 | 72 | true | yes | Good: `phase_1`, `phase_2`, `phase_4`, `complete`. |
| `tinystories_repro` | 100 | 82 | 81 | 81 | true | yes | Good: `phase_1`, `phase_2`, `phase_4`. |
| `gptq_repro` | 41 | 49 | 48 | 48 | true | yes | Weak: detected phases only `phase_1`, `phase_2`. |
| `lora_repro` | 71 | 66 | 65 | 65 | true | yes | Mostly good: `phase_2`, `phase_4`, `complete`; no distinct `phase_1` label. |
| `galore_repro` | 54 | 54 | 53 | 53 | true | yes | Good enough: `phase_1`, `phase_2`, `phase_4`; end marker present. |

## Contract Integrity Check

| run | `criteria_checks` present? | evaluator hardcoded thresholds? | contract verdict |
|---|---:|---:|---|
| `distill_repro` | no | no numeric evaluator cutoff, but evaluator trusts `trend_reproduced` from summary | Weak: prose criteria only; not compliant with new machine-readable rule. |
| `lottery_ticket_repro` | no | evaluator trusts `trend_success`, `reinit_success`, and `paper_scale_equivalent` from summary; thresholds live in config/experiment code | Weak: bounded 0.01 accuracy tolerance and paper-scale gates are not in contract `criteria_checks`. |
| `tinystories_repro` | no | yes: 0.25 loss tolerance, 0.50 distinct-2, 0.35 repetition thresholds in `src/contract_checks.py` | Fails new hard rule; the loss-trend full-credit threshold is hidden outside the contract. |
| `gptq_repro` | no | yes: 0.10 reference tolerance and 128/2048 budget fallbacks in evaluator code | Fails new hard rule for full-reproduction gates. |
| `lora_repro` | yes | no pass/fail threshold hardcoded in evaluator | Compliant structurally; thresholds are substitute/inferred and must stay caveated. |
| `galore_repro` | yes | no pass/fail threshold hardcoded in evaluator | Compliant structurally; some thresholds are weak/local and one memory-ratio gate is suspiciously tight. |

## Scorecards

### `distill_repro`

Weighted total: **75.0/100**. Band: **Portfolio-ready**. Recommendation:
**portfolio-ready** as an honest negative/failurebench sample.

| dimension | score | evidence |
|---|---:|---|
| Paper and claim grounding | 2 | Section 3 MNIST distillation trend is clearly separated from proprietary speech/JFT claims. Paper reference errors 67/146/74 are recorded. |
| Reproduction contract quality | 1 | Contract has explicit prose criteria, but no `criteria_checks`; evaluator reads `trend_reproduced` from summary instead of using a declared machine-readable criterion. |
| Trajectory reconstruction | 1 | Tool result payloads are now present and `is_complete=true`, but detected phase coverage is only `phase_2`. |
| Executable evidence | 2 | Evaluator rerun reproduced `not_reproduced`. MNIST data and checkpoints exist: teacher 2.68 MB, hard student 223 KB, distilled student 223 KB. |
| Reward and labels | 1 | Target-level evaluation exists, but no normalized reward/labels/signal coverage/confidence. |
| Failure taxonomy | 2 | Failure is honest: distilled student is worse than hard-label baseline, and proprietary speech/JFT resources are marked unavailable. |
| Provenance and auditability | 2 | Report, summary, evaluation, data, and checkpoints agree on the failure. |
| Cross-agent comparability | 1 | Codex source/model/timestamps/tool counts exist, but token/cost and normalized action classes are absent. |

Evidence notes:

- Report and JSON agree: teacher 259 errors, hard-label student 423 errors,
  distilled student 457 errors; `trend_reproduced=false`.
- The `not_reproduced` status is genuine, not a mislabeled success.
- CUDA is not claimed; the run is CPU/reduced-scale and documents that gap.

Red flags:

- New contract hard rule not satisfied: no `criteria_checks`.
- Evaluator is gameable because it trusts a summary boolean for the trend.
- Trace phase labels do not show the full paper/contract/experiment/report path.

Delta vs v1: **82.5 -> 75.0**. Tool result payloads are fixed, but the new
contract-threshold rule exposes a contract-quality regression relative to the
v1 scoring assumptions.

### `lottery_ticket_repro`

Weighted total: **77.5/100**. Band: **Portfolio-ready**. Recommendation:
**portfolio-ready** as a bounded Figure 4a case study.

| dimension | score | evidence |
|---|---:|---|
| Paper and claim grounding | 2 | Targets Figure 4a LeNet-300-100 MNIST pruning trend, random reinit control, and reset mechanics. |
| Reproduction contract quality | 1 | Prose criteria are good, but there are no `criteria_checks`; bounded tolerance and paper-scale gates are in config/experiment code. |
| Trajectory reconstruction | 2 | Trace has 82 turns, 72 non-empty tool results, start/end markers, `is_complete=true`, and phases `phase_1`, `phase_2`, `phase_4`, `complete`. |
| Executable evidence | 2 | Evaluator rerun matched. MNIST data, CSV, summary/evaluation JSON, and a valid 1600x640 PNG figure exist. |
| Reward and labels | 1 | Decomposed status exists, but no normalized reward/label/confidence/signal coverage record. |
| Failure taxonomy | 1 | Scale gaps are documented, but paper-scale incompleteness is not represented as a `not_reproduced` evaluator target. |
| Provenance and auditability | 2 | Raw histories in `reproduction_summary.json` support the report; random reinit comparisons match JSON. |
| Cross-agent comparability | 1 | Basic Codex metadata exists; token/cost and normalized action classes are absent. |

Evidence notes:

- Dense early stop is iteration 1900 with test accuracy 0.9768.
- Sparse candidates at levels 1-5 meet the bounded trend criterion; random
  reinit is worse at levels 3 and 6.
- The run is real MNIST but not paper scale: one seed, 2,000 iterations per
  level, batch size 256, one random reinit repeat.

Red flags:

- New contract hard rule not satisfied: no `criteria_checks`.
- Evaluator trusts derived `analysis.*` booleans rather than recomputing all
  criteria from raw histories.
- Paper-scale missing work is mostly prose, not evaluator schema.

Delta vs v1: **77.5 -> 77.5**. Trace completeness improved, but threshold
provenance penalties offset the gain.

### `tinystories_repro`

Weighted total: **77.5/100**. Band: **Portfolio-ready**. Recommendation:
**audit-only** until thresholds move into `criteria_checks` and the loss claim
is rerun on a larger validation sample.

| dimension | score | evidence |
|---|---:|---|
| Paper and claim grounding | 2 | Figure 4 validation-loss ordering, released checkpoints, prompts, and GPT-4 grading gap are clearly scoped. |
| Reproduction contract quality | 1 | Contract has prose targets and paper loss values, but no `criteria_checks`; evaluator thresholds are hardcoded in `src/contract_checks.py`. |
| Trajectory reconstruction | 2 | Trace has 100 turns, 81 non-empty tool results, start/end markers, `is_complete=true`, and phases `phase_1`, `phase_2`, `phase_4`. |
| Executable evidence | 2 | Evaluator status reran. Official TinyStories validation/prompts and checkpoint blobs are present in Hugging Face cache. |
| Reward and labels | 1 | Target-level status exists, but no normalized reward/label/confidence/signal coverage record. |
| Failure taxonomy | 2 | No GPT-4 grading, no from-scratch training, and CPU-only bounded evaluation are disclosed. |
| Provenance and auditability | 1 | Key numbers trace to JSON/cache, but the `fully_reproduced` loss subclaim rests on only 8 validation stories and no declared contract threshold. |
| Cross-agent comparability | 1 | Basic Codex metadata exists; token/cost and normalized action classes are absent. |

Evidence notes:

- Losses match report/summary/evaluation: h64 1.9721, h128 1.4738, h256
  1.2207.
- Evaluation used 8 validation stories and 1,312 tokens per model.
- Cache evidence is plausible: TinyStories validation file 19.4 MB, prompts
  11.8 KB, model blobs roughly 48 MB, 66 MB, and 112 MB.

Red flags:

- New contract hard rule fails: 0.25 loss tolerance, 0.50 distinct-2, and 0.35
  repetition thresholds are hardcoded outside `reproduction_contract.json`.
- The loss trend is too thin for an uncaveated `fully_reproduced` subclaim.
- No GPT-4 evaluator parity and no from-scratch training.

Delta vs v1: **70.0 -> 77.5**. Trace payloads are fixed, but the sample-size and
hidden-threshold concerns remain.

### `gptq_repro`

Weighted total: **75.0/100**. Band: **Portfolio-ready**. Recommendation:
**portfolio-ready** as a reduced GPTQ-vs-RTN trend case study after keeping the
"not full Table 3" caveat attached.

| dimension | score | evidence |
|---|---:|---|
| Paper and claim grounding | 2 | Contract targets OPT-125M/WikiText2 Table 3 trend, core GPTQ mechanics, and separates 175B/custom-kernel claims. |
| Reproduction contract quality | 1 | Prose criteria are explicit, but no `criteria_checks`; evaluator hardcodes 10% tolerance and 128/2048 paper-budget fallback gates. |
| Trajectory reconstruction | 1 | Tool result payloads are now present and `is_complete=true`, but detected phase coverage is only `phase_1` and `phase_2`. |
| Executable evidence | 2 | Evaluator rerun matched. Summary/evaluation/smoke JSON and code exist; OPT-125M and WikiText2 caches are present. |
| Reward and labels | 1 | Decomposed evaluator status exists, but no normalized reward/label/confidence/signal coverage record. |
| Failure taxonomy | 2 | CPU-only runtime, reduced calibration/eval budget, no custom kernels, and no 175B claims are documented. |
| Provenance and auditability | 2 | Metrics in report match JSON: FP16 67.775, RTN 89.493, GPTQ 86.616, with GPTQ closer than RTN. |
| Cross-agent comparability | 1 | Basic Codex metadata exists; token/cost and normalized action classes are absent. |

Evidence notes:

- Rerun reproduced `approximately_reproduced`.
- HF cache evidence is plausible: OPT-125M weight blobs around 250 MB each and
  WikiText2 cached Arrow files exist.
- Run is very reduced: CPU, 4 calibration samples, sequence length 128, 2,048
  eval tokens.

Red flags:

- New contract hard rule fails: 10% tolerance and 128/2048 gates are in
  evaluator code, not `criteria_checks`.
- No local model checkpoint or raw execution log is stored in the run directory.
- Trace phase labels do not cover evaluation/report completion distinctly.

Delta vs v1: **82.5 -> 75.0**. Tool results are fixed, but hardcoded evaluator
thresholds now receive an explicit contract-quality penalty.

### `lora_repro`

Weighted total: **80.0/100**. Band: **Portfolio-ready**. Recommendation:
**portfolio-ready** as a fresh CUDA real-data rerun, not inherited from the old
synthetic proxy.

| dimension | score | evidence |
|---|---:|---|
| Paper and claim grounding | 2 | LoRA mechanism and RoBERTa/GLUE setting are grounded; full GLUE/GPT-3 claims are explicitly out of scope. |
| Reproduction contract quality | 2 | All evaluator thresholds are declared in `criteria_checks` with source/rationale; evaluator maps measured values and reads thresholds from the contract. |
| Trajectory reconstruction | 2 | Trace has 71 turns, 65 non-empty tool results, start/end markers, `is_complete=true`, and phases `phase_2`, `phase_4`, `complete`. |
| Executable evidence | 2 | Evaluator rerun matched. Code loads `roberta-base`, GLUE SST-2, trains on CUDA, and records CUDA memory/time metrics. |
| Reward and labels | 1 | Decomposed status exists, but the top-level `fully_reproduced` label applies only to the reduced substitute contract and can be overread. |
| Failure taxonomy | 1 | Report/gap file disclose full GLUE and GPT-3 omissions, but those original-scale failures are not represented as evaluator `not_reproduced` targets. |
| Provenance and auditability | 1 | Real model/data/CUDA evidence is strong, but no saved fine-tuned checkpoint or per-step training log is preserved beyond aggregate summary fields. |
| Cross-agent comparability | 1 | Basic Codex metadata exists; token/cost and normalized action classes are absent. |

Evidence notes:

- `_cuda_venv` reports torch 2.12.0+cu130, CUDA available, device NVIDIA GB10.
- Offline cache check loads `roberta-base` locally with 124,647,170 parameters;
  GLUE SST-2 cache has 67,349 train and 872 validation examples.
- Summary reports real GLUE SST-2, 4,096 train examples, 512 validation examples,
  validation accuracy 0.9160, first/last train loss 0.7142/0.0441, LoRA peak
  CUDA 4,255.95 MB, full one-step peak 5,682.25 MB.

Red flags:

- Top-level `fully_reproduced` is true only for a reduced real-data contract,
  not full Table 2 GLUE or GPT-3 paper reproduction.
- Proxy thresholds are lenient/substitute: SST-2 accuracy >= 0.80 and memory
  ratio >= 1.05.
- No raw per-step training log or fine-tuned checkpoint is saved in the run dir.

Delta vs v1: **67.5 -> 80.0**. The old synthetic proxy has been replaced by a
real CUDA RoBERTa/GLUE rerun, but labels and provenance are still not
dataset-ready.

### `galore_repro`

Weighted total: **77.5/100**. Band: **Portfolio-ready**. Recommendation:
**portfolio-ready** as a fresh CUDA real-data rerun, not inherited from the old
synthetic proxy.

| dimension | score | evidence |
|---|---:|---|
| Paper and claim grounding | 2 | GaLore Table 4 MRPC/LoRA comparison and optimizer-memory mechanics are grounded; C4/LLaMA pretraining is marked out of scope. |
| Reproduction contract quality | 1 | `criteria_checks` are present and loaded, but thresholds are low/local and the total-memory ratio gate barely passes at 0.98982 <= 0.99. |
| Trajectory reconstruction | 2 | Trace has 54 turns, 53 non-empty tool results, start/end markers, `is_complete=true`, and phases `phase_1`, `phase_2`, `phase_4`. |
| Executable evidence | 2 | Evaluator rerun matched. Code loads `roberta-base`, GLUE MRPC, trains LoRA and GaLore on CUDA, and records metrics. |
| Reward and labels | 1 | Target-level status exists and substitutes are demoted to approximate, but no normalized reward/label/confidence/signal coverage record exists. |
| Failure taxonomy | 2 | Full GLUE 30-epoch table, C4/LLaMA pretraining, exact memory accounting, and budget substitutions are disclosed. |
| Provenance and auditability | 1 | Real model/data/CUDA evidence is strong, but no saved checkpoints or per-step raw training logs are preserved beyond aggregate summary fields. |
| Cross-agent comparability | 1 | Basic Codex metadata exists; token/cost and normalized action classes are absent. |

Evidence notes:

- `_cuda_venv` reports torch 2.12.0+cu130, CUDA available, device NVIDIA GB10.
- Offline cache check loads `roberta-base`; GLUE MRPC cache has 3,668 train and
  408 validation examples.
- Summary reports MRPC subset training: 512 train examples, 256 validation
  examples, 64 steps, LoRA accuracy/F1 0.6797/0.8093, GaLore accuracy/F1
  0.6992/0.7601, GaLore peak CUDA 1.9831 GB.

Red flags:

- New run is real, but still very bounded: 512 train examples and 64 update
  steps, not full GLUE or C4/LLaMA.
- Thresholds are weak/substitute, especially `galore_mrpc_accuracy >= 0.60`
  and `galore_minus_lora_accuracy >= -0.05`.
- The `galore_estimated_total_memory_ratio_to_lora <= 0.99` threshold passes
  by a very small margin and should be treated as fragile.
- No raw per-step training log or checkpoint is saved in the run dir.

Delta vs v1: **67.5 -> 77.5**. The old synthetic proxy has been replaced by a
real CUDA RoBERTa/GLUE rerun, but the contract and provenance remain too weak
for dataset-ready use.

