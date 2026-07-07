# Wave 1 Codex/Claude Reproduction Audit

Audited runs:

- `output/scale_up_wave1/codex/distill_repro`
- `output/scale_up_wave1/codex/lottery_ticket_repro`
- `output/scale_up_wave1/codex/tinystories_repro`
- `output/scale_up_wave1/codex/lora_repro`
- `output/scale_up_wave1/codex/galore_repro`
- `output/scale_up_wave1/codex/gptq_repro`
- `output/hard_tier_pilot/claude/dpo_repro`

Rubric: `docs/trajectory-dataset-quality-rubric.md`. Weighted total uses
`score / 2 * dimension_weight`.

## Evaluator Rerun Check

Evaluators were rerun from temp copies under `/tmp/papyrus_audit_eval_2u4hdsyb`
so the audited project directories remained read-only. Each command was run as
`python3 scripts/evaluate_reproduction.py` from the copied project directory, then
the regenerated `results/reproduction_evaluation.json` was compared to the
original.

| run | original status | rerun status | JSON match | auditor note |
|---|---:|---:|---:|---|
| distill | `not_reproduced` | `not_reproduced` | yes | Failure status reproduced exactly. |
| lottery_ticket | `approximately_reproduced` | `approximately_reproduced` | yes | Status and JSON reproduced exactly. |
| tinystories | `approximately_reproduced` | `approximately_reproduced` | no | Red flag: only `evaluated_at` changed, but evaluator output is not byte-stable. |
| lora | `approximately_reproduced` | `approximately_reproduced` | yes | Status and JSON reproduced exactly. |
| galore | `approximately_reproduced` | `approximately_reproduced` | yes | Status and JSON reproduced exactly. |
| gptq | `approximately_reproduced` | `approximately_reproduced` | yes | Status and JSON reproduced exactly. |
| dpo | `approximately_reproduced` | `approximately_reproduced` | yes | Status and JSON reproduced exactly. |

## Scorecards

### `distill_repro`

Weighted total: **82.5/100**. Readiness band: **Portfolio-ready**.
Recommendation: **portfolio-ready** as an honest failure / failurebench sample,
not as a positive reproduction sample.

| dimension | score | evidence |
|---|---:|---|
| Paper and claim grounding | 2 | Contract targets Section 3 MNIST distillation trend and explicitly separates proprietary speech/JFT targets. Paper reported 67/146/74 errors are recorded as comparison values. |
| Reproduction contract quality | 2 | Success criteria are falsifiable: distilled student must beat hard-label student. It did not, and the evaluator kept `not_reproduced`. |
| Trajectory reconstruction | 1 | `agent_trace.jsonl` has start/end bounds, 42 turns, 67 tool calls, commands, and patches, but it is one JSON object rather than per-turn JSONL, has zero tool result payloads, phase coverage is mostly `phase_2`, and `stats.is_complete=false` despite `end_found=true`. |
| Executable evidence | 2 | Evaluator rerun matched. `results/reproduction_summary.json`, smoke/eval outputs, MNIST data, and checkpoints exist. Checkpoints are plausible: teacher 2.68 MB, hard student 223 KB, distilled student 223 KB. |
| Reward and labels | 1 | Evaluation schema decomposes fully/approximately/not reproduced targets, but no normalized `reward`, `labels`, `signal_coverage`, confidence, or strict score exists. |
| Failure taxonomy | 2 | Failure is specific and honest: CPU-only reduced MNIST run failed the trend; proprietary speech/JFT resources are labeled unavailable. |
| Provenance and auditability | 2 | Required files exist and claims in the report match summary/evaluation JSON. The failure is reproducible from on-disk artifacts. |
| Cross-agent comparability | 1 | Trace has `source=codex`, model, timestamps, and tool counts, but lacks token/cost metadata and normalized action classes. |

Evidence notes:

- Summary reports CPU execution, 30,000 train subset, 10,000 test set, reduced MLP recipe, and `trend_reproduced=false`.
- Report claims teacher 259 errors, hard student 423, distilled student 457; those numbers match `results/reproduction_summary.json` and `results/reproduction_evaluation.json`.
- This is the requested distill failure check: the `not_reproduced` label is genuine and well documented, not a mislabeled success.

Red flags:

- Trace export is lossy: no tool results and `stats.is_complete=false`.
- No normalized reward/label record is present.

### `lottery_ticket_repro`

Weighted total: **77.5/100**. Readiness band: **Portfolio-ready**.
Recommendation: **portfolio-ready** as a bounded case study; not dataset-ready
until the trace and reward/label surface are normalized.

| dimension | score | evidence |
|---|---:|---|
| Paper and claim grounding | 2 | Targets Figure 4a LeNet-300-100 MNIST trend, random reinitialization control, and iterative pruning/reset mechanics. Full paper-scale requirements are recorded. |
| Reproduction contract quality | 2 | Contract distinguishes full reproduction from bounded approximate reproduction with explicit criteria. |
| Trajectory reconstruction | 1 | Trace has 42 turns, 73 tool calls, phases `phase_1`, `phase_2`, `phase_4`, `complete`, and `stats.is_complete=true`, but Codex tool result payloads are absent. |
| Executable evidence | 2 | Evaluator rerun matched. MNIST data files exist, `results/lottery_ticket_results.csv` exists, and `figures/figure4a_bounded.png` is a 1600x640 PNG. |
| Reward and labels | 1 | Evaluation is decomposed by target, but there is no normalized reward/label object, signal coverage, or confidence. |
| Failure taxonomy | 1 | Scale gaps are documented, but the evaluator has no `not_reproduced` entry for paper-scale averages/error bars; the report says "Downgrade: none" even though the run is one seed and 2,000 iterations rather than five trials and 50,000 iterations. |
| Provenance and auditability | 2 | Raw histories in `reproduction_summary.json` support the report. I recomputed dense early stop 1900 / 0.9768 and sparse candidate improvements from the raw histories. |
| Cross-agent comparability | 1 | Agent/model/time/tool metadata are present, but normalized action classes and token/cost metadata are missing. |

Evidence notes:

- CPU-only PyTorch is disclosed: `torch 2.9.1+cpu`, `cuda_available=false`, runtime 175.65 seconds.
- Bounded run used real MNIST with one seed, batch size 256, 2,000 iterations/level, and one random reinit at levels 3 and 6.
- Raw recomputation confirms sparse candidates at levels 1-5 meet the bounded criterion and random reinit is worse at levels 3 and 6.

Red flags:

- Evaluator trusts derived `analysis.*` fields in `reproduction_summary.json`; it does not independently recompute all criteria from raw histories.
- Paper-scale incompleteness is documented in prose but not represented as a `not_reproduced` evaluator target.
- No tool results in the trace.

### `tinystories_repro`

Weighted total: **70.0/100**. Readiness band: **Portfolio-ready**.
Recommendation: **portfolio-ready** only as a bounded official-checkpoint
evaluation; keep out of training-quality dataset slices until thresholds and
provenance are tightened.

| dimension | score | evidence |
|---|---:|---|
| Paper and claim grounding | 2 | Contract targets Figure 4 validation-loss ordering, small-model generation sanity checks, and explicitly marks GPT-4 grading as unavailable. |
| Reproduction contract quality | 1 | The selected target is bounded official-checkpoint evaluation, not from-scratch training. The evaluator's 25% "fully reproduced" loss tolerance and generation proxy thresholds are in code, not stated in the contract. |
| Trajectory reconstruction | 1 | Trace has 51 turns and 82 tool calls, but zero tool result payloads and `stats.is_complete=false`; phase coverage misses a clean completion state. |
| Executable evidence | 2 | Evaluator status reran successfully. Official validation data and prompts exist in Hugging Face cache: validation file 19.4 MB, prompt file 11.8 KB. Model cache blobs for TinyStories-1M/3M/8M are present with plausible tens-of-MB sizes. |
| Reward and labels | 1 | Evaluation has target-level statuses and details, but no normalized reward/label/confidence/signal coverage fields. |
| Failure taxonomy | 2 | Gaps are explicit: no exact GPT-4 evaluator, no from-scratch training, CPU-only bounded sample. |
| Provenance and auditability | 1 | Important claims are traceable to JSON, but the evaluator output is not byte-stable because `evaluated_at` changes on rerun, and model checkpoint paths are not captured in the run summary. |
| Cross-agent comparability | 1 | Codex source/model/timestamps/tool counts exist, but normalized action classes and token/cost metadata are missing. |

Evidence notes:

- Reported losses match summary/evaluation: h64 1.9721 vs paper 2.08, h128 1.4738 vs 1.65, h256 1.2207 vs 1.38.
- Evaluation used only 8 validation stories and 1,312 evaluated tokens per model; this is a very small bounded sample.
- Report discloses CPU-only PyTorch, no GPT-4 grading, and no from-scratch training.

Red flags:

- Rerun JSON mismatch: only `evaluated_at` changed, but this still violates deterministic artifact regeneration.
- "Fully reproduced" for the loss trend is too strong for 8 stories with a hidden 25% tolerance; portfolio wording should keep "bounded official-checkpoint trend".
- Trace lacks tool results and has `stats.is_complete=false`.

### `lora_repro`

Weighted total: **67.5/100**. Readiness band: **Audit-only**.
Recommendation: **audit-only**. It is useful as a documented synthetic proxy, not
as a portfolio-positive reproduction of LoRA paper tables.

| dimension | score | evidence |
|---|---:|---|
| Paper and claim grounding | 1 | The LoRA mechanism is grounded in the paper and official code, but the successful target is a synthetic low-rank task, not GLUE/GPT-2/GPT-3 paper evidence. |
| Reproduction contract quality | 1 | Criteria are explicit, but the main passing target is local and synthetic: known rank-4 update, MSE <= 1.25x full fine-tune, trainable fraction <= 0.10. |
| Trajectory reconstruction | 1 | Trace has 29 turns and 53 tool calls, but no tool results and `stats.is_complete=false`. |
| Executable evidence | 2 | Evaluator rerun matched. Smoke, summary, and evaluation JSON exist; code implements merge/unmerge and synthetic rank sweep. |
| Reward and labels | 1 | Decomposed evaluator status exists, but no normalized reward/labels/signal coverage/confidence. |
| Failure taxonomy | 2 | Exact GLUE/GPT-2/GPT-3 tables are explicitly marked not reproduced due CPU-only runtime, model scale, datasets, and seed/checkpoint gaps. |
| Provenance and auditability | 2 | Reported MSEs and merge difference match JSON. `reproduction_contract.json`, `ambiguity_audit.md`, `gap_report.md`, summary, and evaluation are present. |
| Cross-agent comparability | 1 | Basic Codex metadata exists, but no token/cost or normalized action classes. |

Evidence notes:

- Rank-4 LoRA validation MSE 0.000101 vs full fine-tune 0.000106; merge max abs diff 1.788e-06.
- Exact paper tables are not attempted, and the report says so clearly.
- No large checkpoints or raw logs are expected for this synthetic run; artifacts are JSON summaries and code.

Red flags:

- The proxy is close to a mechanism demo and should not be scored as paper-table reproduction.
- Contract criteria are locally chosen and easy for a known-rank synthetic task.
- Trace lacks tool results and has `stats.is_complete=false`.

### `galore_repro`

Weighted total: **67.5/100**. Readiness band: **Audit-only**.
Recommendation: **audit-only**. It is an honest downgrade, but too synthetic for
portfolio-ready reproduction evidence.

| dimension | score | evidence |
|---|---:|---|
| Paper and claim grounding | 1 | Main C4/LLaMA and 7B memory claims are grounded, but the reproduced target is an inferred compact synthetic language-model proxy. |
| Reproduction contract quality | 1 | Contract documents downgrade, but executable success criteria are weak local thresholds: optimizer-state reduction > 5%, perplexity ratio <= 1.50, projector refreshes > 0. |
| Trajectory reconstruction | 1 | Trace has 29 turns and 56 tool calls, but no tool results and `stats.is_complete=false`. |
| Executable evidence | 2 | Evaluator rerun matched. Smoke, summary, evaluation, configs, scripts, and source files exist. |
| Reward and labels | 1 | Target-level evaluator status exists, but no normalized reward/label surface. |
| Failure taxonomy | 2 | C4/LLaMA scale, 7B memory, CUDA/bitsandbytes, and synthetic-data substitutions are explicitly documented. |
| Provenance and auditability | 2 | Reported perplexity ratio 1.2158 and optimizer-state reduction 65.105% match `results/reproduction_summary.json` and evaluation JSON. |
| Cross-agent comparability | 1 | Basic Codex metadata exists, but no token/cost or normalized action classes. |

Evidence notes:

- Run is explicitly downgraded to Level 2 in the report and gap report.
- CPU-only execution is disclosed; memory metric is optimizer tensor bytes, not CUDA peak memory.
- No figures, checkpoints, or raw logs exist; for this compact proxy, evidence is summary/evaluation JSON and source code.

Red flags:

- Passing criteria are proxy-specific and much weaker than the paper claims.
- Evaluator trusts derived `comparisons` fields from the summary rather than recomputing from raw training histories.
- Trace lacks tool results and has `stats.is_complete=false`.

### `gptq_repro`

Weighted total: **82.5/100**. Readiness band: **Portfolio-ready**.
Recommendation: **portfolio-ready** as a reduced, honest GPTQ-vs-RTN trend case
study; not dataset-ready until trace/reward metadata are normalized.

| dimension | score | evidence |
|---|---:|---|
| Paper and claim grounding | 2 | Contract targets reduced Table 3 OPT-125M WikiText2 perplexity, core GPTQ algorithm, and 175B/custom-kernel system claims as not reproduced. |
| Reproduction contract quality | 2 | Full vs approximate criteria are explicit: full requires paper token budget and within 10% of reported values; approximate requires GPTQ closer to FP16 than RTN. |
| Trajectory reconstruction | 1 | Trace has 21 turns and 49 tool calls, but zero tool results and `stats.is_complete=false`. |
| Executable evidence | 2 | Evaluator rerun matched. Smoke, summary, evaluation, configs, scripts, and code exist. |
| Reward and labels | 1 | Decomposed evaluator status exists, but no normalized reward/label/signal coverage/confidence. |
| Failure taxonomy | 2 | CPU-only runtime, no custom CUDA kernels, reduced calibration/eval token budget, and 175B claims are explicitly marked as gaps. |
| Provenance and auditability | 2 | Metrics in report match JSON: FP16 67.775, RTN 89.493, GPTQ 86.616, GPTQ closer than RTN. |
| Cross-agent comparability | 1 | Basic Codex metadata exists, but no token/cost or normalized action classes. |

Evidence notes:

- Run config is very reduced: OPT-125M, WikiText2, CPU, 4 calibration samples, sequence length 128, 2,048 eval tokens.
- Absolute perplexities do not match paper Table 3 values, but the contract only grants approximate credit for the trend.
- No custom-kernel or 175B runtime claims are reproduced.

Red flags:

- Reduced trend-only success could be overread unless the "not full Table 3" caveat stays attached.
- No model checkpoint or raw execution log is stored in the run directory.
- Trace lacks tool results and has `stats.is_complete=false`.

### `dpo_repro`

Weighted total: **82.5/100**. Readiness band: **Portfolio-ready**.
Recommendation: **portfolio-ready** as a strong approximate reproduction case
study; not dataset-ready because reward/label normalization and comparability
metadata are incomplete.

| dimension | score | evidence |
|---|---:|---|
| Paper and claim grounding | 2 | Contract targets DPO Figure 2 left, Eq. 7 correctness, beta/KL behavior, and explicitly marks PPO/TL;DR/HH claims as not reproduced. |
| Reproduction contract quality | 1 | Criteria are executable and explicit, but key numeric thresholds are local approximations because exact Figure 2 values and Appendix details are absent. The 1.25x KL dominance rule is not a paper criterion. |
| Trajectory reconstruction | 2 | Trace is much stronger than the Codex traces: 203 turns, 97 tool calls, 96 tool results, command history, edit paths, start/end markers, and phases covering paper/contract/implementation/experiment work. |
| Executable evidence | 2 | Evaluator rerun matched. Raw log exists, `frontier.json` and `training_stats.json` exist, `data/pairs.jsonl` is 7.1 MB, and eight model checkpoints are present at about 498 MB each. Figure is a valid 1120x800 PNG. |
| Reward and labels | 1 | Evaluation has criteria passed and decomposed statuses, but no normalized reward, labels, signal coverage, confidence, or strict score. |
| Failure taxonomy | 2 | Missing appendices, substituted classifier/model scale, omitted PPO/PPO-GT/Best-of-N, and unavailable GPT-4 evaluator are clearly labeled. |
| Provenance and auditability | 2 | Report numbers match `frontier.json`, `training_stats.json`, `reproduction_summary.json`, and `results_run.log`. The log confirms training/eval steps and final frontier rewards/KLs. |
| Cross-agent comparability | 1 | Source/model/timestamps/tool counts exist, but no token/cost metadata or normalized action classes. |

Evidence notes:

- DPO beta=0.05 reward 0.926 vs SFT 0.558; beta/KL trend is 7.01, 4.90, 1.74, 1.67.
- Training stats match report: beta=0.1 final loss 0.5663, reward accuracy 0.7125.
- Report discloses gpt2 124M instead of GPT-2-large, substitute `lvwerra/distilbert-imdb`, single seed, partial baselines, and no GPT-4 evaluator.

Red flags:

- Contract thresholds are plausible but partly invented from a qualitative figure; they must not be treated as paper-exact.
- PPO/PPO-GT and Best-of-N are omitted, so the headline "strictly dominates PPO" claim is not reproduced.
- Trace `stats.is_complete=false` even though bounds contain an end marker.

## Summary Table

| run | status reran? | weighted total | band | recommendation | main red flags |
|---|---:|---:|---|---|---|
| `distill_repro` | yes | 82.5 | Portfolio-ready | portfolio-ready | Lossy trace; no normalized reward/labels. |
| `lottery_ticket_repro` | yes | 77.5 | Portfolio-ready | portfolio-ready | Evaluator trusts derived summary fields; paper-scale gap not an evaluator `not_reproduced` target. |
| `tinystories_repro` | status only | 70.0 | Portfolio-ready | portfolio-ready | Rerun JSON timestamp mismatch; hidden full-credit tolerance; very small 8-story sample. |
| `lora_repro` | yes | 67.5 | Audit-only | audit-only | Synthetic known-rank proxy; local success thresholds; no paper tables. |
| `galore_repro` | yes | 67.5 | Audit-only | audit-only | Synthetic compact proxy; weak local thresholds; evaluator trusts derived summary fields. |
| `gptq_repro` | yes | 82.5 | Portfolio-ready | portfolio-ready | Very reduced token/calibration budget; no stored raw log/checkpoint; lossy trace. |
| `dpo_repro` | yes | 82.5 | Portfolio-ready | portfolio-ready | Approximate thresholds; PPO claim omitted; no normalized reward/labels. |

## Portfolio-Level Findings

- No run is dataset-ready under the rubric because the run directories do not
  include normalized `reward`, `labels`, `failure_analysis`, signal coverage,
  confidence, token/cost, or normalized action classes.
- The strongest case-study runs are `distill_repro`, `lottery_ticket_repro`,
  `gptq_repro`, and `dpo_repro`. `tinystories_repro` is borderline because the
  evaluator is nondeterministic and the sample is tiny.
- `lora_repro` and `galore_repro` are honest but should remain audit-only unless
  rerun with real paper datasets/models or explicitly packaged as mechanism-demo
  negative/control examples.
- Common trace issue: Codex traces contain commands and patches but no tool
  results. This limits replayability and should be fixed before training use.
- Common evaluation issue: several evaluators read derived result summaries rather
  than recomputing criteria from raw logs/checkpoints. For adversarial use, future
  evaluators should recompute from raw artifacts or store signed/intermediate
  metric provenance.

## Rerun Guidance

No run is marked `rerun` as the primary recommendation because the stored
artifacts are internally consistent and the bounded scopes are mostly disclosed.
To promote audit-only or portfolio-ready runs toward dataset-ready:

- Normalize every run into `papyrus.trajectory.v1` with reward components,
  labels, failure taxonomy labels, confidence, signal coverage, action classes,
  token/cost, and source provenance.
- Export traces with tool results, not only tool calls.
- Make evaluators recompute pass/fail metrics from raw histories, logs,
  checkpoints, or generated outputs instead of trusting summary booleans.
- For LoRA and GaLore specifically, rerun on real paper-adjacent datasets/models
  or label them explicitly as mechanism demos, not approximate paper reproductions.
- For TinyStories, remove nondeterministic fields from evaluator output or place
  them outside the compared evaluation artifact, state all thresholds in the
  contract, and increase validation sample size.
