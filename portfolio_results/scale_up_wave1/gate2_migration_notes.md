# Gate 2 Threshold-Provenance Migration Notes

Date: 2026-07-07

Scope: post-hoc transparency migration only. No experiment was rerun, no `results/reproduction_summary.json` file was edited, and no verdict upgrade is claimed.

## distill_repro

- Thresholds migrated:
  - `teacher_error_margin_vs_hard_student` `<` `0.0` source=`inferred`
  - `distilled_error_margin_vs_hard_student` `<` `0.0` source=`inferred`
  - `paper_teacher_hidden_width` `==` `1200` source=`explicit`
  - `paper_student_hidden_width` `==` `800` source=`explicit`
  - `full_mnist_subset_limit` `==` `0` source=`inferred`
- Verdict status: before `not_reproduced`; after `not_reproduced`.
- Target sets preserved:
  - fully: `Distillation objective implementation`
  - approximately: none
  - not: `Section 3 MNIST distillation trend`; `Speech recognition Table 1 and Table 5`; `JFT specialist-model Tables 3 and 4`
- Evaluator hardcoded-literals check: migrated cutoff literal scan found none in `scripts/evaluate_reproduction.py`; evaluator now reads these thresholds from `reproduction_contract.json`.
- Confirmation: verdict preserved; distillation remains `not_reproduced`.

## lottery_ticket_repro

- Thresholds migrated:
  - `sparse_early_stop_delta_vs_dense` `<=` `0.0` source=`inferred`
  - `bounded_accuracy_tolerance` `<=` `0.01` source=`substitute`
  - `paper_iterations_per_level` `>=` `50000` source=`explicit`
  - `paper_batch_size` `==` `60` source=`explicit`
  - `paper_eval_interval` `==` `100` source=`inferred`
  - `paper_trial_count` `>=` `5` source=`explicit`
  - `reinit_accuracy_margin` `<` `0.0` source=`substitute`
  - `reinit_iteration_delta` `>` `0.0` source=`inferred`
  - `paper_random_reinit_repeats` `>=` `3` source=`explicit`
- Verdict status: before `approximately_reproduced`; after `approximately_reproduced`.
- Target sets preserved:
  - fully: `Iterative pruning and reset algorithm`
  - approximately: `LeNet-300-100 MNIST iterative pruning Figure 4a trend`; `Random reinitialization control`
  - not: none
- Evaluator hardcoded-literals check: migrated cutoff literal scan found none in `scripts/evaluate_reproduction.py`; evaluator now reads these thresholds from `reproduction_contract.json`.
- Confirmation: verdict preserved.

## tinystories_repro

- Thresholds migrated:
  - `validation_loss_full_relative_tolerance` `<=` `0.25` source=`substitute`
  - `generation_proxy_min_distinct_2` `>=` `0.50` source=`substitute`
  - `generation_proxy_max_repeated_4gram_fraction` `<=` `0.35` source=`substitute`
- Verdict status: before `approximately_reproduced`; after `approximately_reproduced`.
- Target sets preserved:
  - fully: `Figure 4 validation-loss size trend`
  - approximately: `Small-model text generation sanity check`
  - not: `GPT-4 multidimensional grading`
- Evaluator hardcoded-literals check: migrated cutoff literal scan found none in `scripts/evaluate_reproduction.py` or `src/contract_checks.py`; evaluator/helper now read these thresholds from `reproduction_contract.json`.
- Confirmation: verdict preserved; the thin-evidence caveat remains unresolved because this migration only moved thresholds and did not change the 8-story / 1312-token evidence base.

## gptq_repro

- Thresholds migrated:
  - `fp16_ppl_relative_error` `<=` `0.10` source=`inferred`
  - `rtn_4bit_ppl_relative_error` `<=` `0.10` source=`inferred`
  - `gptq_4bit_ppl_relative_error` `<=` `0.10` source=`inferred`
  - `gptq_relative_gap_delta_vs_rtn` `<=` `0.0` source=`inferred`
  - `paper_calibration_samples` `>=` `128` source=`explicit`
  - `paper_sequence_length` `>=` `2048` source=`explicit`
  - `synthetic_smoke_mse_relative_regression` `<=` `0.05` source=`substitute`
- Verdict status: before `approximately_reproduced`; after `approximately_reproduced`.
- Target sets preserved:
  - fully: `Core GPTQ algorithm implementation`
  - approximately: `Reduced Table 3 OPT-125M WikiText2 perplexity comparison`
  - not: `175B runtime and custom-kernel generation speedup claims`
- Evaluator hardcoded-literals check: migrated cutoff literal scan found none in `scripts/evaluate_reproduction.py`; evaluator now reads these thresholds from `reproduction_contract.json`.
- Confirmation: verdict preserved.
