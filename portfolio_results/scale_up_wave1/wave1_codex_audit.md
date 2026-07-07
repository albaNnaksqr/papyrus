# Wave 1 Codex Fourth Adversarial Audit (v4)

Audited runs:

- `output/scale_up_wave1/codex/distill_repro`
- `output/scale_up_wave1/codex/lottery_ticket_repro`
- `output/scale_up_wave1/codex/tinystories_repro`
- `output/scale_up_wave1/codex/gptq_repro`
- `output/scale_up_wave1/codex/lora_repro`
- `output/scale_up_wave1/codex/galore_repro`

Rubric: `docs/trajectory-dataset-quality-rubric.md`. Weighted total uses
`score / 2 * dimension_weight` over the eight rubric dimensions.

Adversarial posture: assume gamed until the on-disk artifacts prove otherwise.
The v3 baseline is `portfolio_results/scale_up_wave1/wave1_codex_audit.v3.json`.
Evaluator reruns were performed from temporary copies under
`/tmp/papyrus_wave1_v4_eval_20260707161552` with
`output/scale_up_wave1/_cuda_venv/bin/python`; audited directories were not
modified.

## Summary

Four of six runs are now **dataset-ready**: `lottery_ticket_repro`,
`gptq_repro`, `lora_repro`, and `galore_repro`. Gate 2 is **met**:
the requirement is `>=3-4` dataset-ready runs, and v4 has **4**.

The LoRA and GaLore reruns fixed the v3 blockers. Both now retain checkpoints
and `results/training_log.jsonl`, have machine-readable paper-scale
`not_reproduced` targets with reasons, reproduce their evaluator JSON from a
temp copy, and report top-level `approximately_reproduced` consistently.

The remaining non-dataset-ready runs are:

- `distill_repro`: honest `not_reproduced` run, but still missing
  `results/training_log.jsonl` and Phase 6 `normalized_record.jsonl`.
- `tinystories_repro`: portfolio-ready, but the runnable model is a reduced
  local Transformer rather than the paper/released GPT-Neo setup.

## v3 to v4 Portfolio Table

| run | v3 total | v3 band | v4 total | v4 band | delta | recommendation | main red flags |
|---|---:|---|---:|---|---:|---|---|
| `distill_repro` | 70.0 | Portfolio-ready | 62.5 | Audit-only | -7.5 | audit-only | No training log; no normalized record; final verdict is `not_reproduced`. |
| `lottery_ticket_repro` | 92.5 | Dataset-ready | 92.5 | Dataset-ready | +0.0 | dataset-ready | Bounded one-seed/four-epoch MNIST run; normalized `smoke_pass` remains null. |
| `tinystories_repro` | 80.0 | Portfolio-ready | 80.0 | Portfolio-ready | +0.0 | portfolio-ready | Uses official TinyStories text but a reduced local Transformer, not GPT-Neo. |
| `gptq_repro` | 92.5 | Dataset-ready | 92.5 | Dataset-ready | +0.0 | dataset-ready | Reduced OPT-125M/WikiText run; C4 and paper-scale claims are not reproduced. |
| `lora_repro` | 72.5 | Portfolio-ready | 92.5 | Dataset-ready | +20.0 | dataset-ready | Reduced SST-2 subset; normalized failure labels remain sparse. |
| `galore_repro` | 65.0 | Audit-only | 92.5 | Dataset-ready | +27.5 | dataset-ready | Eight-step reduced MRPC proxy; normalized reward still has null `smoke_pass`. |

## Evaluator Rerun Check

All six evaluator reruns reproduced the source
`results/reproduction_evaluation.json` exactly as JSON objects.

| run | source status | temp-copy rerun status | JSON object match |
|---|---|---|---|
| `distill_repro` | `not_reproduced` | `not_reproduced` | yes |
| `lottery_ticket_repro` | `approximately_reproduced` | `approximately_reproduced` | yes |
| `tinystories_repro` | `approximately_reproduced` | `approximately_reproduced` | yes |
| `gptq_repro` | `approximately_reproduced` | `approximately_reproduced` | yes |
| `lora_repro` | `approximately_reproduced` | `approximately_reproduced` | yes |
| `galore_repro` | `approximately_reproduced` | `approximately_reproduced` | yes |

## Retention Check

| run | checkpoint evidence | `results/training_log.jsonl` | result |
|---|---:|---:|---|
| `distill_repro` | 3 files: teacher, hard student, distilled student | missing | fail |
| `lottery_ticket_repro` | 5 checkpoint files | 20 JSONL records with `step_or_epoch` and `loss` | pass |
| `tinystories_repro` | 1 checkpoint file | 220 JSONL records with `step_or_epoch` and `loss` | pass |
| `gptq_repro` | 1 quantized artifact | 72 JSONL records with `step_or_epoch` and reconstruction `loss` | pass |
| `lora_repro` | `results/checkpoints/lora_sst2_subset.pt` | 128 JSONL records with `step_or_epoch` and `loss` | pass |
| `galore_repro` | 4 files under `results/checkpoints/final/` | 8 JSONL records with `step_or_epoch` and `loss` | pass |

## Scope and Report Consistency

All evaluator thresholds used for pass/fail are loaded from
`reproduction_contract.json` `criteria_checks`; the evaluator scripts do not
hide numeric success thresholds in source literals. Paper-scale `not_reproduced`
targets for LoRA and GaLore have no pass thresholds and carry explicit reasons.

| run | scope honesty | report/evaluator consistency |
|---|---|---|
| `distill_repro` | Evaluation schema marks MNIST trend failure plus speech/JFT omissions as `not_reproduced`; contract remains narrower. | Report status `not_reproduced` matches evaluator. |
| `lottery_ticket_repro` | Full 50k-iteration MNIST curves, CIFAR/deep suite, and hyperparameter sweeps are machine-readable `not_reproduced` targets. | Report status `approximately_reproduced` matches evaluator. |
| `tinystories_repro` | GPT-Eval table, paper-scale model suite, architecture sweep, and TinyStories-Instruct are machine-readable `not_reproduced` targets. | Report status `approximately_reproduced` matches evaluator. |
| `gptq_repro` | Full OPT/BLOOM, C4 calibration, CUDA speedups, zero-shot tables, and 2-bit/ternary claims are machine-readable `not_reproduced` targets. | Report status `approximately_reproduced` matches evaluator. |
| `lora_repro` | Full RoBERTa-base/large GLUE Table 2 plus GPT-3 175B quality and memory/checkpoint claims are machine-readable `not_reproduced` targets. | Fixed since v3: overall report status now `approximately_reproduced`, matching evaluator. The `## Fully Reproduced` section only lists the reduced target. |
| `galore_repro` | Full GLUE Table 4 and C4/LLaMA-7B claims are machine-readable `not_reproduced` targets. | Report status `approximately_reproduced` matches evaluator. |

## Scorecards

### `distill_repro`

V3 -> V4 delta: **70.0 Portfolio-ready -> 62.5 Audit-only (-7.5)**.
Recommendation: **audit-only**.

| dimension | score | evidence |
|---|---:|---|
| Paper and claim grounding | 2 | MNIST distillation trend is grounded; proprietary speech/JFT claims are explicitly excluded. |
| Reproduction contract quality | 2 | Tested thresholds are in `criteria_checks`; evaluator recomputes from summary metrics. |
| Trajectory reconstruction | 1 | Raw trace is complete: 81 turns, 67 tool calls, 66 tool results, `stats.is_complete=true`; no normalized record. |
| Executable evidence | 1 | Scripts, summary, evaluation, and 3 checkpoints exist; JSONL training log is missing. |
| Reward and labels | 0 | Phase 6 `normalized_record.jsonl` and normalized rewards/labels are absent. |
| Failure taxonomy | 2 | Evaluation schema honestly marks the failed MNIST trend and unavailable speech/JFT targets. |
| Provenance and auditability | 1 | Report/summary/evaluation agree, but training-log and normalized-record provenance are missing. |
| Cross-agent comparability | 1 | Raw Codex model/time metadata exists; normalized action/reward comparability is absent. |

Evidence notes:

- Temp-copy evaluator rerun reproduced `not_reproduced`.
- Report and evaluator agree: teacher 259 errors, hard-label student 423 errors,
  distilled student 457 errors.
- Checkpoints retained: `teacher.pt`, `hard_student.pt`, `distilled_student.pt`.
- Red flags: no `results/training_log.jsonl`; no `normalized_record.jsonl`;
  the core distillation trend failed.

### `lottery_ticket_repro`

V3 -> V4 delta: **92.5 Dataset-ready -> 92.5 Dataset-ready (+0.0)**.
Recommendation: **dataset-ready**.

| dimension | score | evidence |
|---|---:|---|
| Paper and claim grounding | 2 | Targets Section 2 real-MNIST LeNet-300-100 lottery-ticket mechanism and random-reinit control. |
| Reproduction contract quality | 2 | Eight contract checks declare all thresholds, including retention checks. |
| Trajectory reconstruction | 2 | Raw trace complete; normalized record has 42 turns, 58 tool calls, 114 tool results, commands, edits, and phases. |
| Executable evidence | 2 | Real MNIST data, LeNet code, smoke/experiment/evaluator scripts, summary/evaluation JSON, checkpoints, and JSONL log exist. |
| Reward and labels | 1 | Decomposed normalized rewards exist; `smoke_pass` is null, reducing strict score. |
| Failure taxonomy | 2 | Full MNIST curves, CIFAR/deep suite, and hyperparameter sweeps are explicit `not_reproduced` targets. |
| Provenance and auditability | 2 | Numbers are traceable across contract, summary, evaluation, report, trace, and normalized record. |
| Cross-agent comparability | 2 | Normalized record includes Codex host/model/time/token metadata and action-level tool traces. |

Evidence notes:

- Temp-copy evaluator rerun reproduced `approximately_reproduced`.
- Real data/model: MNIST 60,000 train/validation, 10,000 test; LeNet-300-100.
- Best same-init ticket: fraction remaining 0.5128, test accuracy 0.9794,
  dense baseline 0.9744.
- Retention passed: 5 checkpoint files and 20 JSONL training records.
- Red flags: bounded one-seed/four-epoch run; not a full Figure 4 reproduction.

### `tinystories_repro`

V3 -> V4 delta: **80.0 Portfolio-ready -> 80.0 Portfolio-ready (+0.0)**.
Recommendation: **portfolio-ready**.

| dimension | score | evidence |
|---|---:|---|
| Paper and claim grounding | 1 | Uses official TinyStories text, but the retained model is a reduced local Transformer rather than the paper/released GPT-Neo setup. |
| Reproduction contract quality | 2 | Contract distinguishes reduced training from GPT-Eval, paper-scale model, sweep, and Instruct omissions. |
| Trajectory reconstruction | 2 | Raw trace complete; normalized record has 36 turns, 57 tool calls, 112 tool results, commands, edits, and phases. |
| Executable evidence | 2 | Data slices, vocabulary, checkpoint, training log, scripts, summary/evaluation JSON, and generated samples exist. |
| Reward and labels | 1 | Decomposed normalized rewards exist; `smoke_pass` is null and failure labels are generic. |
| Failure taxonomy | 2 | GPT-Eval, paper-scale training, architecture sweep, and TinyStories-Instruct are explicit `not_reproduced` targets. |
| Provenance and auditability | 1 | Numeric artifacts are traceable, but model fidelity is a documented reduced substitute. |
| Cross-agent comparability | 2 | Normalized Codex host/model/time/token/action metadata exists. |

Evidence notes:

- Temp-copy evaluator rerun reproduced `approximately_reproduced`.
- Real data: official TinyStories slices, 2,097,152 train bytes and 262,144
  validation bytes.
- Local model: 1,067,776-parameter causal Transformer, hidden size 128, 4
  layers, 4 heads, block size 96.
- Loss cross-check: train loss fell from 7.6262 to 3.7275; validation loss
  fell from 7.6234 to 3.5947.
- Retention passed: 1 checkpoint and 220 JSONL training records.
- Red flag: portfolio-ready only because this is not the exact GPT-Neo
  tokenizer/model/evaluation stack.

### `gptq_repro`

V3 -> V4 delta: **92.5 Dataset-ready -> 92.5 Dataset-ready (+0.0)**.
Recommendation: **dataset-ready**.

| dimension | score | evidence |
|---|---:|---|
| Paper and claim grounding | 2 | Targets OPT-125M 4-bit GPTQ vs RTN WikiText-2 trend and separates C4/paper-scale claims. |
| Reproduction contract quality | 2 | All measured thresholds are in `criteria_checks`; five full-paper targets are `not_reproduced`. |
| Trajectory reconstruction | 2 | Raw trace complete; normalized record has 87 turns, 74 tool calls, 146 tool results, commands, edits, and phases. |
| Executable evidence | 2 | Real `facebook/opt-125m`, WikiText-2, GPTQ code, tests, quantized checkpoint, training log, summary/evaluation JSON exist. |
| Reward and labels | 1 | Decomposed normalized rewards exist; `smoke_pass` is null and failure label is coarse. |
| Failure taxonomy | 2 | Full OPT/BLOOM, C4 calibration, CUDA speedups, zero-shot tasks, and 2-bit/ternary claims are explicit `not_reproduced`. |
| Provenance and auditability | 2 | Report, summary, evaluation, tests, retention artifacts, trace, and normalized record cross-check. |
| Cross-agent comparability | 2 | Normalized Codex host/model/time/token/action metadata exists. |

Evidence notes:

- Temp-copy evaluator rerun reproduced `approximately_reproduced`.
- Real model/data: `facebook/opt-125m` on WikiText-2; C4 paper-scale
  calibration is explicitly not reproduced.
- Numeric cross-check: FP16 PPL 67.7899, RTN 4-bit PPL 89.4761, GPTQ 4-bit
  PPL 75.4484, GPTQ-vs-RTN improvement 14.0276.
- Retention passed: `results/checkpoints/quantized_gptq.pt` and 72 JSONL
  reconstruction-loss records.
- Red flags: reduced model and calibration budget; not a full OPT/BLOOM/C4 run.

### `lora_repro`

V3 -> V4 delta: **72.5 Portfolio-ready -> 92.5 Dataset-ready (+20.0)**.
Recommendation: **dataset-ready**.

| dimension | score | evidence |
|---|---:|---|
| Paper and claim grounding | 2 | Targets real `roberta-base` LoRA on GLUE/SST-2 and separates full GLUE/GPT-3 claims. |
| Reproduction contract quality | 2 | Reduced target has three declared checks; full RoBERTa-base/large GLUE and GPT-3 175B targets are `not_reproduced` with reasons. |
| Trajectory reconstruction | 2 | Raw trace complete; normalized record has 62 turns, 86 tool calls, 170 tool results, commands, edits, and phases. |
| Executable evidence | 2 | Real GLUE/SST-2, `roberta-base`, LoRA code, checkpoint, JSONL log, summary/evaluation JSON, and report exist. |
| Reward and labels | 1 | Decomposed normalized rewards exist; `smoke_pass` is null and normalized failure labels are sparse. |
| Failure taxonomy | 2 | Paper-scale GLUE and GPT-3 omissions are machine-readable `not_reproduced` targets with reasons. |
| Provenance and auditability | 2 | Report status now matches evaluator; numbers trace across contract, summary, evaluation, checkpoint/log, trace, and normalized record. |
| Cross-agent comparability | 2 | Normalized Codex host/model/time/token/action metadata exists. |

Evidence notes:

- Temp-copy evaluator rerun reproduced `approximately_reproduced`.
- Report consistency fixed since v3: top-level status is
  `approximately_reproduced`; the `## Fully Reproduced` section only names the
  reduced SST-2 target.
- Real data/model: `roberta-base` with GLUE/SST-2 subset.
- Numeric cross-check: held-out accuracy 0.8984 vs threshold 0.65; loss
  reduction 0.2840 vs threshold 0.02; trainable fraction 0.0071 vs threshold
  0.02.
- Retention passed: `results/checkpoints/lora_sst2_subset.pt` and 128 JSONL
  training records.
- Red flags: reduced subset and short local run; not a full GLUE or GPT-3
  reproduction.

### `galore_repro`

V3 -> V4 delta: **65.0 Audit-only -> 92.5 Dataset-ready (+27.5)**.
Recommendation: **dataset-ready**.

| dimension | score | evidence |
|---|---:|---|
| Paper and claim grounding | 2 | Targets real `roberta-base` GaLore on GLUE/MRPC and separates full GLUE Table 4 plus C4/LLaMA-7B claims. |
| Reproduction contract quality | 2 | Reduced target has eight declared checks; full GLUE and C4/LLaMA targets are `not_reproduced` with reasons. |
| Trajectory reconstruction | 2 | Raw trace complete; normalized record has 61 turns, 71 tool calls, 140 tool results, commands, edits, and phases. |
| Executable evidence | 2 | Real GLUE/MRPC, `roberta-base`, GaLore code, checkpoint directory, JSONL log, summary/evaluation JSON, and report exist. |
| Reward and labels | 1 | Decomposed normalized rewards exist; `smoke_pass` is null and code/experiment reward is 0.75. |
| Failure taxonomy | 2 | Full GLUE Table 4 and C4/LLaMA-7B omissions are machine-readable `not_reproduced` targets with reasons. |
| Provenance and auditability | 2 | Report/evaluator agree; retention, metrics, thresholds, trace, and normalized record are cross-checkable. |
| Cross-agent comparability | 2 | Normalized Codex host/model/time/token/action metadata exists. |

Evidence notes:

- Temp-copy evaluator rerun reproduced `approximately_reproduced`.
- Real data/model: `roberta-base` on real GLUE/MRPC; C4/LLaMA-7B is explicitly
  out of scope.
- Numeric cross-check: eval accuracy 0.7031 vs threshold 0.5; F1 0.8257; loss
  fell from 0.6866 to 0.6259; GaLore/full optimizer-state ratio 0.3221 vs
  threshold 0.5.
- Retention passed: 4 checkpoint files under `results/checkpoints/final/` and
  8 JSONL training records.
- Red flags: eight-step reduced proxy; `trained_steps` exactly equals its
  minimum evidence threshold, though performance and memory checks have margin.

## Final Recommendation

Use `lottery_ticket_repro`, `gptq_repro`, `lora_repro`, and `galore_repro` as
dataset-ready bounded trajectories after normal privacy/path review. Keep
`tinystories_repro` as portfolio-ready evidence of an honest reduced
reproduction. Keep `distill_repro` audit-only until it is rerun or repaired with
a retained JSONL training log and a Phase 6 normalized record.
