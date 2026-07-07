# Gate 2 Scope Honesty Notes

Date: 2026-07-07

## output/scale_up_wave1/codex/lora_repro

Top-level status:
- Before: `fully_reproduced`
- After: `approximately_reproduced`

Added `not_reproduced` targets:
- `Full GLUE Table 2 benchmark at RoBERTa-large scale across all tasks`
  - Reason: Not run. This reproduction intentionally used a bounded real GLUE SST-2 subset with RoBERTa-base under the single-experiment 4h budget, while the run's `gap_report.md` and `REPRODUCTION_REPORT.md` both state that the full 8-task, five-seed Table 2 GLUE suite was omitted.
- `GPT-3 175B few-shot results and GPT-3-scale parameter/memory headline`
  - Reason: Not run. The run did not have GPT-3 175B model access or multi-GPU/model-parallel infrastructure; `gap_report.md` states that the original 10,000x trainable-parameter and 3x memory headline cannot be rerun here, and `REPRODUCTION_REPORT.md` limits this omission to GPT-3 175B WikiSQL/MNLI/SAMSum results and scaling figures.

Before reproduced target sets:
- `fully_reproduced`: `Reduced real-data GLUE SST-2 LoRA task quality`; `LoRA parameter efficiency and frozen-base mechanics`; `LoRA merge/no-extra-latency construction`; `CUDA memory and runtime budget`
- `approximately_reproduced`: none

After reproduced target sets:
- `fully_reproduced`: `Reduced real-data GLUE SST-2 LoRA task quality`; `LoRA parameter efficiency and frozen-base mechanics`; `LoRA merge/no-extra-latency construction`; `CUDA memory and runtime budget`
- `approximately_reproduced`: none

## output/scale_up_wave1/codex/galore_repro

Top-level status:
- Before: `approximately_reproduced`
- After: `approximately_reproduced`

Added `not_reproduced` targets:
- `Full C4 LLaMA 7B pre-training memory-and-loss claim`
  - Reason: Not run. This reproduction used a bounded real GLUE/MRPC RoBERTa fine-tuning experiment; `gap_report.md` states that C4 LLaMA 1B/7B pretraining was omitted because paper-scale C4 pretraining requires far more steps and compute, and `REPRODUCTION_REPORT.md` states that C4 LLaMA pretraining results from Tables 2, 3, and 11 up to 1B/7B and 150K steps exceed the 40GB/4h budget.

Before reproduced target sets:
- `fully_reproduced`: none
- `approximately_reproduced`: `Reduced real GLUE/MRPC RoBERTa fine-tuning: GaLore rank 4 comparable to LoRA rank 4`; `Memory-efficient optimizer-state trend versus LoRA`; `GaLore projector/optimizer semantics`

After reproduced target sets:
- `fully_reproduced`: none
- `approximately_reproduced`: `Reduced real GLUE/MRPC RoBERTa fine-tuning: GaLore rank 4 comparable to LoRA rank 4`; `Memory-efficient optimizer-state trend versus LoRA`; `GaLore projector/optimizer semantics`
