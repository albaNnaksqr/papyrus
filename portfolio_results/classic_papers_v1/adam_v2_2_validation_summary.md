# Adam v2.2 Compatibility Validation

Generated on 2026-07-02 after adding the Claude Code compatibility layer to `normalize_skill_run.py`.

## Adam Before / After

| field | skill.v2.1 behavior | skill.v2.2 behavior |
| --- | --- | --- |
| `trajectory.turn_count` | 56 | 56 |
| `trajectory.tool_calls` | 29 | 29 |
| `trajectory.commands` | 0 | 6 Claude `Bash` commands |
| `trajectory.file_edits` | 0 | 14 Claude `Write` edits |
| `run.token_usage` | `null` | Claude session usage, `total_tokens=111253` |
| `run.status` | `unknown` | `complete_inferred` |
| `run.wall_time_seconds` | `null` | `503.351` |

The normalized Adam record for review is `portfolio_results/classic_papers_v1/adam_v2_2_check.json`.

## Codex Six-Run Regression

The six `output/code_agent_deep_runs/*/agent_trace.jsonl` records were regenerated to
`portfolio_results/code_agent_deep_runs/normalized_runs.jsonl` with `skill.v2.2`.

Comparison against the pre-change `skill.v2.1` baseline was clean after normalizing
only `provenance.created_at` and `provenance.normalizer_version`.

`portfolio_results/code_agent_deep_runs/normalized_summary.json` had no diff from
the v2.1 baseline.

## Known Cross-Host Semantics Gap (found in post-fix verification)

`total_tokens` is NOT comparable across hosts in v2.2:

- Codex branch: `input_tokens` (and therefore `total_tokens`) **includes** cached input (e.g. swe_agent: total 2,853,759 with 2,703,744 cached).
- Claude branch: `input_tokens` **excludes** cached input; cache tokens are broken out separately (adam: total 111,253 with 2,678,022 cached on the side).

Both branches expose `cached_input_tokens`, so a consistent derived metric (uncached input + output) is computable today. Before any paired Codex/Claude efficiency comparison, either normalize `total_tokens` semantics or compare on the derived metric only.
