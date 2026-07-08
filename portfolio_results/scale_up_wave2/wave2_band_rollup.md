# Wave 2 band pass — reproducible scorecard result (2026-07-08)

## What was built

`trajectory/scorecard.py` turns the 8-dimension rubric into a scorecard that is
**deterministic where it can be, anchored where it cannot**:

- **60 pts fully mechanical** (dims 3 trajectory, 4 evidence, 5 reward/labels,
  7 provenance, 8 comparability) — computed from normalized_record +
  preaudit_detectors + on-disk artifacts. Same inputs → same score.
- **40 pts hybrid** (dims 1 grounding, 2 contract/proxy faithfulness, 6 label
  honesty) — the mechanical layer sets a CEILING; an anchored LLM judgment may
  only CONFIRM or LOWER it. The judgment is recorded as data in
  `wave2_llm_overrides.json` (per-run, per-dim, with a note), so a band is
  reproducible from its inputs.
- Band = weighted points → {dataset-ready 85+, portfolio 70+, audit-only 50+,
  reject}, then deterministic caps (band_cap from preaudit_detectors).

Two calibration bugs were found and fixed while building it (this is the
"tighten" the exercise was for):
1. **d1** required `contracts.claim_contract`, which is `None` on every codex
   record (host-specific artifact) → capped all 12 at 1 spuriously. Fixed to
   score on structured `target_claims` + `expected_metrics`.
2. **d6** read only `labels.failure_types` → gave 0 to honest bounded successes
   whose gaps live in `not_reproduced` TARGETS. Fixed to credit not_reproduced
   scope-boundary labelling.

## Calibration against wave1 (known bands)

The scorecard reproduces the known wave1 bands, which is why its wave2 output is
trustworthy:
- **galore → portfolio** via the deterministic <10-step band_cap. ✓
- **distill → reject** — it has no normalized_record (never rerun), so the
  mechanical dims correctly bottom out; as a data *record* it is incomplete.
- **tinystories** — mechanically reaches dataset-ready, but its known portfolio
  band comes from a proxy-faithfulness gap (reduced local Transformer vs the
  paper's exact GPT-Neo). The scorecard correctly LOCATES that in the **d2 LLM
  judgment** — the mechanical layer can't (and shouldn't) catch it. This is the
  design working: d2 proxy-faithfulness is the main discriminator.

## Wave 2 result: 12/12 dataset-ready

| run | pts | band | note |
|---|---:|---|---|
| nucleus_sampling, label_smoothing, mixup, sgdr, lookahead, prefix_tuning, dora, alibi, medusa | 100 | dataset-ready | full marks: grounded claim, faithful proxy, honest labels |
| smoothquant | 92.5 | dataset-ready (borderline) | d2=1: W8A8 tolerance 1.25 is loose for a "near-lossless" claim |
| double_descent | 92.5 | dataset-ready (borderline) | d2=1: headline curve verified vs paper's released metrics after a CIFAR env-gap, not independently reproduced (honestly labelled) |
| awq | 87.5 | dataset-ready (borderline) | d2=1 + d6=1: single-sample calibration is a degenerate input for AWQ's calibration mechanism, thinness under-labelled |

## Honest caveat — read before quoting "12/12"

**Nine perfect 100s is a saturation signal.** The scorecard measures TRAJECTORY
DATA QUALITY — honest, auditable, well-structured, grounded, faithfully-scoped,
honestly-labelled — NOT reproduction depth or scientific impressiveness. Under
that (correct-for-papyrus) lens the hardened pipeline genuinely produces clean
records, so most runs max out. Consequences:

- "12/12 dataset-ready, 0 gaming" is a strong **yield / trustworthiness** claim.
  It is a weak **selectivity** claim — the rubric barely separates the top.
- To make "N dataset-ready" a *selective* number at 30-50 scale, add a harder
  discriminating tier (e.g. reproduction depth: independent repro vs
  released-data/directional-proxy; evidence strength beyond the 10-step floor;
  quantitative claim-match tightness). Deferred — flagged for the user.
- A stricter reproduction-completeness grader would push the 3 borderline (and
  arguably prefix_tuning's 512-row / nucleus's 48-prompt thinness) to portfolio.

The wave2 headline that is fully defensible: **the hardened pipeline produced 12
independent, adversarially-audited runs with zero gaming and zero structural
defects; the 3 weakest are honestly-bounded proxies, transparently labelled.**
