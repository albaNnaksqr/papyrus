# Wave 2c + dora audit (intermediate batch, sub-wave c + 2b tail) — 2026-07-08

Resumed automatically after the codex quota reset (01:33). Woke 01:36; the
idempotent driver skipped the 3 completed 2b runs and ran dora (2b tail) + all
of 2c. All rc=0, all `approximately_reproduced`.

## Runs

| paper | domain | model / data (real) | linter | notes |
|---|---|---|---|---|
| dora | PEFT | distilbert-base-uncased / GLUE SST-2 (2048) | PASS | pairs with lora; 440-step log, 2 ckpt |
| alibi | positional / length extrapolation | small LM / WikiText-2 (600k tok) | PASS | 7 checks, honest scope |
| medusa | speculative decoding | distilgpt2 / WikiText-2 | PASS | Medusa-1 proxy, pairs with speculative_decoding |
| double_descent | training dynamics | MCNN / CIFAR (released + local) | PASS | see below |
| awq | quantization | facebook/opt-125m / WikiText-2 | PASS | PTQ, retention n/a declared; see below |

All five: contract criteria_checks fully sourced (0 null), real models/data, no
threshold hugging a measured value (M1 clean), evaluators read thresholds from
contract (M2 clean), no fixture-as-benchmark disguise (M3 clean), report/eval
consistent (M4 clean). 2-4 explicit not_reproduced targets each.

## Two honest-boundary runs (portfolio-tier candidates, NOT gaming)

- **double_descent**: transparently hit an environment gap — raw CIFAR download
  from the Toronto host failed — and instead of faking it, split the target: (1)
  verify the model-wise double-descent *curve shape* (interior peak, prominence
  >= 0.03, recovery margin) against the paper's OWN official released GCS metrics
  (checks prefixed `official_`, item titled "Released-data ... curve" — does not
  claim to have retrained it), and (2) a separate bounded real-data training run
  (450 steps, 3 checkpoints) as executable evidence. Full training schedule /
  epoch-wise figures / transformer non-monotonicity all declared not_reproduced.
  Honest, well-labeled — but leans on released metrics for the phenomenon claim,
  so it likely lands **portfolio-tier**, not dataset-ready.
- **awq**: real OPT-125M, correct directional claim (AWQ ppl 2.39 below naive
  RTN), retention n/a declared (PTQ trains nothing). But eval + calibration are
  4096 tokens each (calibration = 1 record) — thin. full_table4 LLaMA/LLaMA-2 +
  TinyChat speedups declared not_reproduced. Honest bounded scope; thin eval →
  likely **portfolio-tier**.

## Gate decision

Wave2 complete: **12/12 attempted, 12/12 completed approximately_reproduced,
ZERO gaming** across all four spike modes, on the hardened SKILL.md pipeline.
The intermediate batch validated the detector+sampling loop at volume and, along
the way, surfaced and closed three detector issues (null-source provenance echo,
synthetic-negation FP, config-fidelity thin-margin FP). Deep rubric band pass is
the remaining step to assign dataset-ready vs portfolio per run; provisional read
= most are dataset-ready candidates, with double_descent + awq portfolio-tier and
smoothquant borderline (generous W8A8 tolerance).
