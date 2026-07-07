# Wave 1 Codex Third Adversarial Audit (v3)

Audited runs:

- `output/scale_up_wave1/codex/distill_repro`
- `output/scale_up_wave1/codex/lottery_ticket_repro`
- `output/scale_up_wave1/codex/tinystories_repro`
- `output/scale_up_wave1/codex/gptq_repro`
- `output/scale_up_wave1/codex/lora_repro`
- `output/scale_up_wave1/codex/galore_repro`

Rubric: `docs/trajectory-dataset-quality-rubric.md`. Weighted total uses
`score / 2 * dimension_weight`.

Adversarial posture: each run was treated as gamed until on-disk contracts,
evaluators, results, retained artifacts, traces, reports, and normalized records
proved otherwise.

## Summary

Two runs are now recommended as dataset-ready: `lottery_ticket_repro` and
`gptq_repro`. Both have contract-driven thresholds, explicit machine-readable
paper-scale `not_reproduced` targets, retained checkpoint/log evidence, complete
embedded traces, and normalized records with run metadata/token usage. They are
still bounded partial reproductions, not full paper replications.

The other four are not dataset-ready:

- `distill_repro`: honest failure and threshold migration took, but it trains
  without `results/training_log.jsonl` and has no normalized record.
- `tinystories_repro`: retained and normalized, but it trains a reduced local
  causal Transformer rather than a released/paper GPT-Neo configuration.
- `lora_repro`: machine verdict is now `approximately_reproduced`, but the final
  report still says `fully_reproduced` and the training run retained no
  checkpoint/log.
- `galore_repro`: threshold migration took, but it retained no checkpoint/log;
  full GLUE Table 4 all-task omission is report-only rather than an evaluator
  `not_reproduced` target; one memory threshold is razor-thin.

## Evaluator Rerun Check

Evaluators were rerun from temp copies under
`/tmp/papyrus_wave1_v3_audit_rppjt1db` using
`output/scale_up_wave1/_cuda_venv/bin/python`. Audited directories were not
modified. Comparison ignores volatile timestamp fields only.

| run | original status | rerun status | match ignoring volatile fields |
|---|---|---|---|
| `distill_repro` | `not_reproduced` | `not_reproduced` | yes |
| `lottery_ticket_repro` | `approximately_reproduced` | `approximately_reproduced` | yes |
| `tinystories_repro` | `approximately_reproduced` | `approximately_reproduced` | yes |
| `gptq_repro` | `approximately_reproduced` | `approximately_reproduced` | yes |
| `lora_repro` | `approximately_reproduced` | `approximately_reproduced` | yes |
| `galore_repro` | `approximately_reproduced` | `approximately_reproduced` | yes |

## Fix Verification

### Threshold Provenance

All live evaluator pass/fail thresholds now come from
`reproduction_contract.json` `criteria_checks`. The v2 failures for
TinyStories and GPTQ hardcoded thresholds are fixed in the current on-disk
evaluators.

| run | result |
|---|---|
| `distill_repro` | Pass for thresholds tested by evaluator: trend margins, paper hidden widths, and full-subset limit are loaded from `criteria_checks`. Source still computes a summary `trend_reproduced` boolean, but evaluator recomputes from metrics. |
| `lottery_ticket_repro` | Pass: evaluator maps `criteria_measurements` and applies only contract thresholds. |
| `tinystories_repro` | Pass: old hardcoded 0.25/0.50/0.35 checks are gone; evaluator loads all ten checks from contract. |
| `gptq_repro` | Pass: old 0.10/128/2048 evaluator gates are gone; checks are contract-driven. |
| `lora_repro` | Pass: evaluator maps measured values and reads thresholds from contract. |
| `galore_repro` | Pass structurally; caveat that `galore_estimated_total_memory_ratio_to_lora <= 0.99` is razor-thin. |

### Retention

| run | checkpoint | `results/training_log.jsonl` | audit result |
|---|---:|---:|---|
| `distill_repro` | yes, 3 files | no | Distill checkpoint fix took, but this training run still lacks a JSONL training log. |
| `lottery_ticket_repro` | yes, 5 files | yes, 20 records | Pass. |
| `tinystories_repro` | yes, 1 file | yes, 220 records | Pass. |
| `gptq_repro` | yes, 1 quantized artifact | yes, 72 records | Pass; log is per-module reconstruction loss for post-training quantization. |
| `lora_repro` | no | no | Fail: it trains RoBERTa/GLUE but retains no fine-tuned checkpoint/log. |
| `galore_repro` | no | no | Fail: it trains LoRA and GaLore baselines but retains no checkpoint/log. |

### Scope Honesty

| run | machine-readable not-reproduced scope |
|---|---|
| `distill_repro` | Evaluation `status_schema.not_reproduced` includes MNIST trend failure plus speech/JFT omissions with reasons. Contract target list is still narrower than the evaluator schema. |
| `lottery_ticket_repro` | Contract/evaluator explicitly mark full 50,000-iteration five-trial MNIST curves, CIFAR/deep suite, and hyperparameter exploration as `not_reproduced`. |
| `tinystories_repro` | Contract/evaluator explicitly mark GPT-Eval table, paper-scale released models/training budget, architecture sweep, and TinyStories-Instruct as `not_reproduced`. |
| `gptq_repro` | Contract/evaluator explicitly mark full OPT/BLOOM family through 175B/176B, C4 calibration budget, CUDA kernel speedups, zero-shot tasks, and 2-bit/ternary claims as `not_reproduced`. |
| `lora_repro` | Contract/evaluator explicitly mark full GLUE Table 2 and GPT-3 175B claims as `not_reproduced`. |
| `galore_repro` | Contract/evaluator explicitly mark Full C4/LLaMA 7B pre-training as `not_reproduced`, but the full all-task GLUE Table 4 omission is only in the report, not evaluator schema. |

### Verdict Honesty

The machine-readable verdict inflation is fixed for the reruns: `lottery_ticket`,
`tinystories`, `gptq`, `lora`, and `galore` are `approximately_reproduced`, and
`distill` remains `not_reproduced`. The exception is LoRA's stale report text:
`REPRODUCTION_REPORT.md` still says the overall evaluator status is
`fully_reproduced` and shows final assertion output `fully_reproduced`, while
the current evaluator JSON is `approximately_reproduced`.

## Portfolio Table

| run | v2 total | v3 total | delta | v3 band | recommendation | main red flags |
|---|---:|---:|---:|---|---|---|
| `distill_repro` | 75.0 | 70.0 | -5.0 | Portfolio-ready | audit-only | No training log; no normalized record; weak phase labels. |
| `lottery_ticket_repro` | 77.5 | 92.5 | +15.0 | Dataset-ready | dataset-ready | Bounded one-seed/four-epoch run; normalized failure label still generic. |
| `tinystories_repro` | 77.5 | 80.0 | +2.5 | Portfolio-ready | portfolio-ready | Custom reduced Transformer, not released/paper GPT-Neo; generic normalized labels. |
| `gptq_repro` | 75.0 | 92.5 | +17.5 | Dataset-ready | dataset-ready | Real but reduced OPT-125M/WikiText run; C4/paper-scale claims explicitly not reproduced. |
| `lora_repro` | 80.0 | 72.5 | -7.5 | Portfolio-ready | rerun | Report says `fully_reproduced`; no checkpoint/log; no normalized record. |
| `galore_repro` | 77.5 | 65.0 | -12.5 | Audit-only | rerun | No checkpoint/log; full GLUE omission not evaluator target; razor-thin memory ratio. |

## Scorecards

### `distill_repro`

V2 -> V3 delta: **75.0 Portfolio-ready -> 70.0 Portfolio-ready (-5.0)**.
Recommendation: **audit-only** as an honest failed reproduction until retention
and normalization are fixed.

| dimension | score | evidence |
|---|---:|---|
| Paper and claim grounding | 2 | Section 3 MNIST distillation trend is grounded; proprietary speech/JFT claims are disclosed. |
| Reproduction contract quality | 2 | Tested thresholds were migrated to `criteria_checks`; evaluator no longer trusts summary booleans for pass/fail. |
| Trajectory reconstruction | 1 | Embedded trace has 81 turns, 67 tool calls, 66 non-empty tool results, `is_complete=true`, but detected phase labels only show `phase_2`. |
| Executable evidence | 1 | Evaluator reruns and checkpoints exist, but the training run has no per-step/epoch JSONL training log. |
| Reward and labels | 1 | Evaluation status exists, but no normalized reward/label record. |
| Failure taxonomy | 2 | Genuine failure is labeled: distilled student is worse than hard-label baseline; speech/JFT unavailable. |
| Provenance and auditability | 1 | Report/summary/evaluation agree on numbers, but no training log or normalized record. |
| Cross-agent comparability | 1 | Codex model/time/trace metadata exist; token/cost/action classes are not normalized. |

Evidence notes:

- Temp-copy evaluator rerun reproduced `not_reproduced`.
- Report, summary, and evaluation agree: teacher 259 errors, hard-label student
  423 errors, distilled student 457 errors.
- Checkpoints exist: `teacher.pt` 2,681,557 bytes, `hard_student.pt` 223,313
  bytes, `distilled_student.pt` 223,373 bytes.
- Red flags: no `results/training_log.jsonl`; CPU/reduced model widths; no
  normalized record.

### `lottery_ticket_repro`

V2 -> V3 delta: **77.5 Portfolio-ready -> 92.5 Dataset-ready (+15.0)**.
Recommendation: **dataset-ready** as a bounded, honest partial reproduction.

| dimension | score | evidence |
|---|---:|---|
| Paper and claim grounding | 2 | Targets Section 2/Figure 4 LeNet-300-100 MNIST lottery-ticket mechanism and random-reinit control. |
| Reproduction contract quality | 2 | Eight `criteria_checks` declare all evaluator thresholds and retention checks. |
| Trajectory reconstruction | 2 | Trace has 42 turns, 58 tool calls, 57 non-empty tool results, `is_complete=true`, and phase 1/2/4 coverage. |
| Executable evidence | 2 | Evaluator reruns; real MNIST data, checkpoints, summary/evaluation JSON, and JSONL log exist. |
| Reward and labels | 1 | Normalized record exists with decomposed rewards, but `smoke_pass` is null and failure labels are generic. |
| Failure taxonomy | 2 | Full MNIST curves, CIFAR/deep suite, and hyperparameter sweeps are evaluator `not_reproduced` targets. |
| Provenance and auditability | 2 | Report, summary, evaluation, checkpoints, logs, and normalized record agree. |
| Cross-agent comparability | 2 | Normalized record includes agent host, model, wall time, token usage, trace turns, and tool results. |

Evidence notes:

- Temp-copy evaluator rerun reproduced `approximately_reproduced`.
- Real MNIST: 60,000 train/validation examples and 10,000 test examples.
- Dense best test accuracy 0.9744; best same-init ticket is pruning level 3,
  fraction remaining 0.5128, best test accuracy 0.9794.
- Random reinit final mask best test accuracy is 0.9733.
- Retention passed: 5 checkpoint files and 20 JSONL training-log records.
- Red flags: one seed, four bounded epochs per pruning level, and reduced
  substitute thresholds; not a full Figure 4 reproduction.

### `tinystories_repro`

V2 -> V3 delta: **77.5 Portfolio-ready -> 80.0 Portfolio-ready (+2.5)**.
Recommendation: **portfolio-ready**, not dataset-ready, because the model is a
reduced local Transformer rather than the released/paper GPT-Neo setup.

| dimension | score | evidence |
|---|---:|---|
| Paper and claim grounding | 1 | Real TinyStories text is used, but the model/tokenizer are reduced local substitutes for the paper GPT-Neo configuration. |
| Reproduction contract quality | 2 | Ten contract checks cover reduced training plus four full-paper `not_reproduced` targets. |
| Trajectory reconstruction | 2 | Trace has 36 turns, 57 tool calls, 56 non-empty tool results, `is_complete=true`, and phase 1/2/4 coverage. |
| Executable evidence | 2 | Evaluator reruns; real text slices, checkpoint, JSONL log, summary/evaluation JSON, and generated samples exist. |
| Reward and labels | 1 | Normalized record exists, but `smoke_pass` is null and failure labels are generic. |
| Failure taxonomy | 2 | GPT-Eval, paper-scale released models, full architecture sweep, and TinyStories-Instruct are evaluator `not_reproduced` targets. |
| Provenance and auditability | 1 | Numbers are traceable, but model fidelity is a reduced custom GPT-like implementation. |
| Cross-agent comparability | 2 | Normalized record includes agent host, model, wall time, token usage, trace turns, and tool results. |

Evidence notes:

- Temp-copy evaluator rerun reproduced `approximately_reproduced`.
- Real TinyStories slices: 2,097,152 train bytes, 262,144 validation bytes,
  490,704 train tokens, 62,359 validation tokens.
- Local model: 1,067,776-parameter causal Transformer, hidden size 128, 4
  layers, 4 heads, block size 96.
- Losses match report/summary: final train loss 3.7275, trained validation loss
  3.5947, validation loss delta 4.0287.
- Retention passed: checkpoint `tinystories_reduced.pt` and 220 JSONL log
  records.
- Red flag: this is not a released TinyStories GPT-Neo checkpoint or exact
  GPT-Neo tokenizer/preprocessing reproduction.

### `gptq_repro`

V2 -> V3 delta: **75.0 Portfolio-ready -> 92.5 Dataset-ready (+17.5)**.
Recommendation: **dataset-ready** as a bounded, honest OPT-125M/WikiText GPTQ
partial reproduction.

| dimension | score | evidence |
|---|---:|---|
| Paper and claim grounding | 2 | Targets OPT-125M 4-bit GPTQ vs RTN WikiText-2 trend while excluding full model-family/C4/kernel claims. |
| Reproduction contract quality | 2 | All four measured checks are in `criteria_checks`; five full-paper targets are explicit `not_reproduced`. |
| Trajectory reconstruction | 2 | Trace has 87 turns, 74 tool calls, 73 non-empty tool results, `is_complete=true`, and phase 1/2/4 coverage. |
| Executable evidence | 2 | Evaluator reruns; real `facebook/opt-125m`, WikiText-2, quantized artifact, summary/evaluation JSON, tests, and JSONL log exist. |
| Reward and labels | 1 | Normalized record exists with decomposed rewards, but `smoke_pass` is null and failure label is generic `environment_gap`. |
| Failure taxonomy | 2 | Full OPT/BLOOM, C4 calibration, CUDA speedups, zero-shot tasks, and 2-bit/ternary claims are evaluator `not_reproduced`. |
| Provenance and auditability | 2 | Report, summary, evaluation, retention artifacts, tests, and normalized record are mutually traceable. |
| Cross-agent comparability | 2 | Normalized record includes agent host, model, wall time, token usage, trace turns, and tool results. |

Evidence notes:

- Temp-copy evaluator rerun reproduced `approximately_reproduced`.
- Current metrics: FP16 PPL 67.7899, RTN 4-bit PPL 89.4761, GPTQ 4-bit PPL
  75.4484; GPTQ improves over RTN by 14.0276.
- Retention passed: `quantized_gptq.pt` is 250,559,805 bytes and
  `training_log.jsonl` has 72 per-module reconstruction-loss records.
- Threshold provenance fixed: old 0.10 and 128/2048 evaluator gates are gone.
- Red flags: reduced calibration/evaluation budget and WikiText-2 calibration
  replacing paper C4, both explicitly scoped.

### `lora_repro`

V2 -> V3 delta: **80.0 Portfolio-ready -> 72.5 Portfolio-ready (-7.5)**.
Recommendation: **rerun** or repair artifacts before use: keep the contract and
evaluator, but rerun with checkpoint/log retention and update the stale report.

| dimension | score | evidence |
|---|---:|---|
| Paper and claim grounding | 2 | Real `roberta-base` and real GLUE SST-2 subset are used; full GLUE/GPT-3 claims are scoped out. |
| Reproduction contract quality | 2 | Eleven evaluator thresholds are declared in `criteria_checks`; full GLUE and GPT-3 targets are `not_reproduced`. |
| Trajectory reconstruction | 2 | Trace has 71 turns, 66 tool calls, 65 non-empty tool results, `is_complete=true`, and phase 2/4/complete coverage. |
| Executable evidence | 1 | Evaluator reruns and metrics exist, but the training run has no retained checkpoint or JSONL training log. |
| Reward and labels | 1 | Machine evaluator status is honest, but no normalized record exists and report text is stale. |
| Failure taxonomy | 2 | Full GLUE Table 2 and GPT-3 175B omissions are evaluator `not_reproduced` targets. |
| Provenance and auditability | 0 | `REPRODUCTION_REPORT.md` says `fully_reproduced` while current JSON says `approximately_reproduced`; no retention artifacts exist. |
| Cross-agent comparability | 1 | Trace metadata exists; normalized action/reward/token record is absent. |

Evidence notes:

- Temp-copy evaluator rerun reproduced `approximately_reproduced`.
- Summary uses real GLUE SST-2: 4,096 train examples, 512 validation examples,
  `roberta-base`, validation accuracy 0.9160.
- Trainable parameter reduction is 140.52x; full/LoRA memory ratio is 1.335x.
- Threshold provenance passes.
- Red flags: no `results/checkpoints/`, no `results/training_log.jsonl`, no
  normalized record, and report lines 10 and 95-97 still claim
  `fully_reproduced`.

### `galore_repro`

V2 -> V3 delta: **77.5 Portfolio-ready -> 65.0 Audit-only (-12.5)**.
Recommendation: **rerun** with retention and a fuller machine-readable scope
schema.

| dimension | score | evidence |
|---|---:|---|
| Paper and claim grounding | 2 | Real `roberta-base` and real GLUE MRPC are used; C4/LLaMA 7B pretraining is scoped out. |
| Reproduction contract quality | 1 | Thresholds are contract-driven, but full all-task GLUE Table 4 omission is not an evaluator target. |
| Trajectory reconstruction | 2 | Trace has 54 turns, 54 tool calls, 53 non-empty tool results, `is_complete=true`, and phase 1/2/4 coverage. |
| Executable evidence | 1 | Evaluator reruns and metrics exist, but no checkpoint or JSONL training log was retained. |
| Reward and labels | 1 | Evaluation status exists, but there is no normalized reward/label record. |
| Failure taxonomy | 1 | Full C4/LLaMA target is evaluator `not_reproduced`, but full GLUE all-task scope is report-only. |
| Provenance and auditability | 1 | Numbers trace to JSON/report, but retention is missing and one threshold barely passes. |
| Cross-agent comparability | 1 | Trace metadata exists; normalized action/reward/token record is absent. |

Evidence notes:

- Temp-copy evaluator rerun reproduced `approximately_reproduced`.
- Real GLUE MRPC subset: 512 train examples, 256 validation examples.
- LoRA rank 4 validation accuracy/F1: 0.6797/0.8093; GaLore rank 4 validation
  accuracy/F1: 0.6992/0.7601.
- Memory estimate ratio to LoRA is 0.989821882951654 against threshold
  `<= 0.99`, a razor-thin margin.
- Red flags: no `results/checkpoints/`, no `results/training_log.jsonl`, no
  normalized record, and full Table 4 all-task GLUE omission is not in
  evaluator `status_schema.not_reproduced`.
