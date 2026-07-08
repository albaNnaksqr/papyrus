# Wave2 V1 Dataset Card

## What This Is

This is a versioned dataset artifact for audited code-agent reproduction
trajectories. Each row is a normalized paper-reproduction run copied from
`output/scale_up_wave2/codex/*_repro/normalized_record.jsonl` with an added
`dataset` metadata block.

This is NOT a set of full benchmark replications. The records are bounded,
honestly labelled reproduction trajectories designed for filtering, verifier/RM
training, audit, and analysis.

## Provenance

- Source papers: 12 arXiv-paper reproduction runs: nucleus sampling, label
  smoothing, mixup, SmoothQuant, SGDR, Lookahead, prefix-tuning, DoRA, ALiBi,
  Medusa, Deep Double Descent, and AWQ.
- Agent/run arm: codex gpt-5.5 volume arm.
- Reproduction workflow: hardened `paper2repro-skill` with a baked CUDA venv.
- Run dates: 2026-07-07..08.
- Score source: `portfolio_results/scale_up_wave2/wave2_scorecard.json`.
- Anchored hybrid judgments: `portfolio_results/scale_up_wave2/wave2_llm_overrides.json`.
- Caveat source: `portfolio_results/scale_up_wave2/wave2_band_rollup.md`.

## Schema

Each record is the full normalized trajectory record plus:

- `dataset.reproduction_depth`: one of the taxonomy values below, derived from
  the d2 override note and score.
- `dataset.outcome_signal`: `honest_negative` if an in-scope check in a
  fully/approximately reproduced target failed; otherwise `confirmed`.
- `dataset.not_reproduced_count`: count of `status_schema.not_reproduced`.
- `dataset.trains_model`: true only when `results/training_log.jsonl` exists
  with at least one record.
- `dataset.optimizer_steps`: non-empty line count of `results/training_log.jsonl`,
  or null for no-training runs.
- `dataset.eval_scale`: numeric evaluation/calibration size fields found in
  `results/reproduction_summary.json`, or null when no matching fields exist.
- `dataset.has_repairs`: true when `trajectory.repair_attempts` is non-empty.
- `dataset.paired_with`: fixed pairing label for comparable methods, or null.
- `dataset.band`: copied from `wave2_scorecard.json`.
- `dataset.points`: copied from `wave2_scorecard.json`.
- `dataset.weakness_tags`: short tags mechanically derived from low-scoring
  hybrid override notes.

## Reproduction Depth Taxonomy

- `independent_real_run`: the d2 override score is 2 and the d2 note does not
  contain "released"; this means the bounded target was independently run on
  real data/model artifacts.
- `thin_directional_proxy`: the d2 override score is below 2 and the d2 note
  does not contain "released"; this keeps honest but materially weakened
  directional proxies filterable.
- `released_metrics_verification`: the d2 note contains "released"; this marks a
  run where the phenomenon claim leans on released metrics rather than a fully
  independent reproduction of that metric.

## Band Distribution

- dataset-ready: 12

| name | band | points | reproduction_depth | outcome_signal | not_reproduced_count | weakness_tags | paired_with |
|---|---|---:|---|---|---:|---|---|
| nucleus_sampling | dataset-ready | 100.0 | independent_real_run | confirmed | 2 |  |  |
| label_smoothing | dataset-ready | 100.0 | independent_real_run | confirmed | 5 |  |  |
| mixup | dataset-ready | 100.0 | independent_real_run | confirmed | 3 |  |  |
| smoothquant | dataset-ready | 92.5 | thin_directional_proxy | confirmed | 2 | loose_threshold | gptq |
| sgdr | dataset-ready | 100.0 | independent_real_run | honest_negative | 3 |  |  |
| lookahead | dataset-ready | 100.0 | independent_real_run | confirmed | 5 |  | adam |
| prefix_tuning | dataset-ready | 100.0 | independent_real_run | confirmed | 4 |  | lora |
| dora | dataset-ready | 100.0 | independent_real_run | confirmed | 4 |  | lora |
| alibi | dataset-ready | 100.0 | independent_real_run | confirmed | 2 |  |  |
| medusa | dataset-ready | 100.0 | independent_real_run | confirmed | 3 |  | speculative_decoding |
| double_descent | dataset-ready | 92.5 | released_metrics_verification | confirmed | 3 | released_data_lean |  |
| awq | dataset-ready | 87.5 | thin_directional_proxy | confirmed | 3 | single_sample_calibration, underlabelled_thinness | gptq |

## Known Limitations

The wave2 rollup explicitly warns: "Nine perfect 100s is a saturation signal."
The scorecard measures trajectory data quality, not reproduction depth or
scientific impressiveness. The resulting "12/12 dataset-ready, 0 gaming" is a
yield and trustworthiness claim, not a selectivity claim.

All runs are bounded reduced-scale reproductions with explicit
`not_reproduced` targets for paper-scale omissions. A stricter
reproduction-completeness grader could demote the borderline cases, especially
the thin/released-metrics records.

This artifact makes no downstream A/B performance claim. Any claim that models
trained on these records improve a target system requires a separate A/B study.

Deliberately gamed proof-spike data is NOT included in this product. The wave2
audit result for these 12 records was zero gaming and zero structural defects;
the weaker records are included only because their limitations are labelled.

## Filtering Recipes

- Verifier/RM training set:
  `reproduction_depth == "independent_real_run" AND outcome_signal in {"confirmed", "honest_negative"}`.
- Honest-failure subset:
  `outcome_signal == "honest_negative"`.
- Paired A/B subset:
  `paired_with != null`.
- Thin/released review subset:
  `reproduction_depth != "independent_real_run" OR weakness_tags != []`.

## What This Is NOT

This is not a leaderboard, not a claim of full-paper replication, not a
downstream model-improvement study, and not a mixture containing deliberately
gamed examples. It is a filterable, source-auditable trajectory dataset artifact.
