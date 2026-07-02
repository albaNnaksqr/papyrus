# Normalized Run Backfill Summary

Generated on 2026-07-02 for `portfolio_results/code_agent_deep_runs/normalized_runs.jsonl`.

## Scope

- Re-normalized the six existing code-agent portfolio runs.
- Excluded `swe_bench_eval_harness`, which has no `agent_trace.jsonl` in the current tree.
- Upgraded `provenance.normalizer_version` from `skill.v1` to `skill.v2`.

## Before / After

| run | before | after |
| --- | --- | --- |
| `swe_bench_repro` | 0 repair attempts; 6 apply_patch edit stubs without paths; null token usage | 2 repair attempts (1 planned TDD red, 1 unexpected; 2 successful); 23 file-level edit rows; token total 4,174,825 |
| `agentless_repro` | 0 repair attempts; 5 apply_patch edit stubs without paths; null token usage | 1 repair attempt (1 planned TDD red; 1 successful); 24 file-level edit rows; token total 4,082,523 |
| `swe_agent_repro` | 0 repair attempts; 3 apply_patch edit stubs without paths; null token usage | 1 repair attempt (planned TDD red at turns 7-10; successful); 14 file-level edit rows; token total 2,853,759 |
| `repobench_repro` | 0 repair attempts; 6 apply_patch edit stubs without paths; null token usage | 5 repair attempts (1 planned TDD red, 4 unexpected; 4 successful); 17 file-level edit rows; token total 4,023,631 |
| `reflexion_repro` | 0 repair attempts; 6 apply_patch edit stubs without paths; null token usage | 3 repair attempts (3 planned TDD red; 1 successful); 22 file-level edit rows; token total 4,084,042 |
| `swe_bench_multimodal_repro` | 0 repair attempts; 7 apply_patch edit stubs without paths; null token usage | 4 repair attempts (3 planned TDD red, 1 unexpected; 1 successful); 29 file-level edit rows; token total 4,863,212 |

## Acceptance Notes

- `swe_agent_repro` turns 7-10 are classified as `planned_tdd_red`, not `unexpected_failure`.
- Every `apply_patch` call in all six runs has at least one `file_edits` row with `path`, `operation`, `diff_line_count`, and `target_class`.
- All six records retain the required top-level sections: `paper`, `run`, `contracts`, `trajectory`, `artifacts`, `reward`, `labels`, `failure_analysis`, and `provenance`.
