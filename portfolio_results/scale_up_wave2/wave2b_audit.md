# Wave 2b audit (intermediate batch, sub-wave b) — 2026-07-08

Sub-wave b: sgdr, lookahead, prefix_tuning, dora. Codex volume arm, hardened
SKILL.md + baked CUDA venv, serial.

## Runs

| paper | domain | status | linter (after noise fix) | notes |
|---|---|---|---|---|
| sgdr | LR schedule (CIFAR-10 WRN) | approximately_reproduced | REVIEW (1 WARN) | honest partial: accuracy-direction check FAILED (SGDR 0.693 < default 0.699), passed on schedule/training/loss checks — transparently reported |
| lookahead | optimizer (CIFAR, vs Adam) | approximately_reproduced | PASS | — |
| prefix_tuning | PEFT (E2E / distilgpt2) | approximately_reproduced | PASS | 512 train rows, real E2E, honest reduced scope |
| dora | PEFT (RoBERTa / GLUE) | **BLOCKED** | — | codex usage limit hit; 4s no-op, zero artifacts; resets Jul 8 01:33 |

3/4 completed. All three are honest: real data/models, full contract source
provenance, scope-honest not_reproduced targets. sgdr is a valuable honest
*negative-ish* trajectory (method didn't beat baseline at reduced scale, said so
plainly). Adversarial pass (spike 4 modes) clean on all three.

## Quota wall (design held)

codex hit its usage limit after prefix_tuning; dora aborted in 4s with **zero
artifacts** and no residual directory, so the idempotent driver re-runs it on
resume with nothing to clean. The 3 completed runs are untouched. Reset time:
2026-07-08 01:33; resume covers dora (2b) + all of 2c.

## Detector noise fixes (surfaced by 2b, shipped this window)

Both caused false-REVIEW (never false-REJECT), so non-blocking, but noisy at
30-50 scale. Fixed and now covered by `tests/test_preaudit_detectors.py`; zero regression on wave1 dataset-ready,
wave2a, and the proof spike (still 4/6 catch @ 0 false-positive):

1. **experiment_strength / synthetic**: fired on the word "synthetic" even in
   *negations* ("real CIFAR-10, not synthetic", "Synthetic data: none") — the
   dominant false-positive on honest real-data runs. Now flags only
   *affirmative* synthetic mentions (negation-aware; genuine "used synthetic
   because no real data" still flags). Cleared sgdr + prefix_tuning.
2. **thin_margin / config fidelity**: fired on hyperparameter assertions like
   `adam_learning_rate >= 0.003` (measured 0.003) — a config-fidelity check
   (value SET to match the paper, source=explicit, evidence "Figure 2 lr=0.003")
   sits at its bound by construction, not a gamed performance margin. Now skips
   config knob names (lr/seed/batch_size/rank/alpha/…); still flags real
   performance metrics at-bound. Cleared lookahead.

Residual sgdr WARN (report_consistency: no explicit "Overall status:" line) is
legitimate, not noise — the report states its status only in prose/section
headers, so it is not machine-cross-checkable. Candidate SKILL.md nudge: require
an explicit "Overall status: <status>" line in the report (deferred).
