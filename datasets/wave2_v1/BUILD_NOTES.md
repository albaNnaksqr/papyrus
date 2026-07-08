# Wave2 V1 Build Notes

Build command:

```bash
python -m trajectory.package_dataset --out datasets/wave2_v1 --scorecard portfolio_results/scale_up_wave2/wave2_scorecard.json --overrides portfolio_results/scale_up_wave2/wave2_llm_overrides.json output/scale_up_wave2/codex/nucleus_sampling_repro output/scale_up_wave2/codex/label_smoothing_repro output/scale_up_wave2/codex/mixup_repro output/scale_up_wave2/codex/smoothquant_repro output/scale_up_wave2/codex/sgdr_repro output/scale_up_wave2/codex/lookahead_repro output/scale_up_wave2/codex/prefix_tuning_repro output/scale_up_wave2/codex/dora_repro output/scale_up_wave2/codex/alibi_repro output/scale_up_wave2/codex/medusa_repro output/scale_up_wave2/codex/double_descent_repro output/scale_up_wave2/codex/awq_repro
```

## Derived Field Rules

- `manifest.created_at`: ISO committer timestamp from `git show -s --format=%cI HEAD`, making reruns deterministic for the same `pipeline_commit`.
- `manifest.pipeline_commit`: from `git rev-parse HEAD`.
- `reproduction_depth`: from `portfolio_results/scale_up_wave2/wave2_llm_overrides.json`, d2 note and score. If the d2 note contains `released`, set `released_metrics_verification`; else if d2 score is below 2, set `thin_directional_proxy`; else set `independent_real_run`.
- `outcome_signal`: from `results/reproduction_evaluation.json`. If any check in `status_schema.fully_reproduced` or `status_schema.approximately_reproduced` has `passed == false`, set `honest_negative`; otherwise `confirmed`.
- `not_reproduced_count`: from `results/reproduction_evaluation.json`, length of `status_schema.not_reproduced`.
- `trains_model`: from `results/training_log.jsonl`; true when the file exists and has at least one non-empty record.
- `optimizer_steps`: non-empty line count of `results/training_log.jsonl`; null when `trains_model` is false.
- `eval_scale`: from `results/reproduction_summary.json`; numeric evaluation/calibration size fields with explicit matching keys are copied, otherwise null.
- `has_repairs`: from `normalized_record.jsonl`, true when `trajectory.repair_attempts` length is greater than zero.
- `paired_with`: fixed map in `trajectory/package_dataset.py`: dora->lora, lookahead->adam, awq->gptq, medusa->speculative_decoding, smoothquant->gptq, prefix_tuning->lora; otherwise null.
- `band`: copied from `portfolio_results/scale_up_wave2/wave2_scorecard.json`.
- `points`: copied from `portfolio_results/scale_up_wave2/wave2_scorecard.json`.
- `weakness_tags`: from `portfolio_results/scale_up_wave2/wave2_llm_overrides.json`; for hybrid dims 1, 2, and 6 with score below 2, map note text to tags: loose/tolerance -> `loose_threshold`; released -> `released_data_lean`; single-sample/1 record -> `single_sample_calibration`; under-labelled/not explicitly flagged -> `underlabelled_thinness`.

## Ambiguity Report

No ambiguous derivations were encountered.

- `double_descent` has `eval_scale: null` because no matching evaluation or calibration size field exists in its `reproduction_summary.json`.
- All low-scoring hybrid override notes matched one of the explicit weakness-tag rules.
- The packager raises `ValueError` rather than inventing a tag if a future low-scoring override note does not match a known source phrase.
