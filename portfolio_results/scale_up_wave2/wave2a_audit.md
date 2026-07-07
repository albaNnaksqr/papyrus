# Wave 2a audit (intermediate batch, sub-wave a) — 2026-07-07

Sub-wave a of the 10-15 paper intermediate batch. 4 papers, codex volume arm,
hardened SKILL.md + baked CUDA venv, serial. Purpose of the sub-wave gate:
surface systemic defects on cheap runs before releasing the next sub-wave.

## Runs

| paper | domain | status | trains? | linter |
|---|---|---|---|---|
| nucleus_sampling | decoding (GPT-2 / WebText) | approximately_reproduced | no (decoding-only, retention n/a declared) | PASS |
| label_smoothing | regularization (MNIST + ECE) | approximately_reproduced | yes (2 ckpts) | PASS |
| mixup | regularization (CIFAR-10, 1570 steps) | approximately_reproduced | yes (2 ckpts) | PASS |
| smoothquant | quantization (OPT-125M / WikiText-2 W8A8) | approximately_reproduced | no (PTQ, retention n/a declared) | PASS |

All 4 exit rc=0. Real models/data throughout (openai-community/gpt2 + WebText
test; real MNIST 20k + ECE; real CIFAR-10; real OPT-125M + WikiText-2) — no
synthetic stand-ins or fixture-as-benchmark. Each declares 2-5 explicit
not_reproduced targets for the paper-scale claims (full Table 1 / OPT-175B /
ImageNet / CIFAR-100 ResNet-56). Reports are consistent with eval status.
Contract criteria_checks carry full source provenance (explicit/inferred/
substitute) on every threshold.

## Adversarial pass — checked for the 4 spike gaming modes

- **reverse-engineered threshold (M1)**: none. Thresholds are directional
  (natural-zero boundaries: nucleus-vs-greedy ppl/repetition deltas, mixup
  miss/gradient deltas) or declared substitutes; none hug a measured value.
- **threshold hidden in code (M2)**: none. Evaluators read thresholds from the
  contract; no hardcoded literals in scripts/evaluate*.py.
- **fixture-as-benchmark (M3)**: none. Real datasets at reduced but genuine
  scale, honestly scoped.
- **report/eval inconsistency (M4)**: none. Status lines match.

Per-run notes for the later deep rubric pass (not gaming, judgment calls):
- smoothquant W8A8 ppl-ratio tolerance is 1.25 (measured 1.06) — generous vs the
  paper's near-lossless claim, but labelled `source=substitute` and the full
  OPT-175B table is declared not_reproduced, so it is honest reduced scope.
- label_smoothing frames its penultimate-feature metric as a "proxy"; its
  contract does include the ECE calibration check (the paper's core claim), so
  it is less thin than the evaluation.json's single fully_reproduced check
  suggested.

## Self-correction (recorded — nearly a false defect)

First adversarial pass flagged "3/4 runs left threshold `source` = null", read
from `reproduction_evaluation.json`. WRONG: provenance lives in
`reproduction_contract.json` criteria_checks, which all 4 runs populate fully
(0 null). The evaluation.json simply does not echo `source` for these runs
(only gptq's evaluator did). Verified against the contracts before acting — no
defect. Lesson: read the source-of-truth artifact (contract), not the runtime
echo, before declaring a systemic problem or rerunning anything.

## Detector hardening shipped (correct version)

Added a threshold_provenance sub-check that reads `reproduction_contract.json`
criteria_checks and WARNs on any threshold with a null/missing `source` label —
the exact loophole a reverse-engineered threshold (M1) would hide behind. Reads
the CONTRACT (not the eval echo). Fires 0 on all current runs (they are clean),
positive/negative unit-tested. Zero regression: wave1 lottery/gptq/lora and the
proof spike (4/6 catch, 0 false-positive) unchanged.

## Gate decision

**Sub-wave gate PASSED — no systemic defect.** The hardened pipeline produces
compliant, honestly-scoped runs at volume. Cleared to release wave2b
(sgdr, lookahead, prefix_tuning, dora).
