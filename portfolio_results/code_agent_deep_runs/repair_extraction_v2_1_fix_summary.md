# Repair Extraction v2.1 Fix Summary

Generated on 2026-07-02 after re-normalizing the six code-agent portfolio runs.

## Scope

- Input: existing `output/code_agent_deep_runs/*/agent_trace.jsonl` runs, excluding `swe_bench_eval_harness`.
- Output: `portfolio_results/code_agent_deep_runs/normalized_runs.jsonl`.
- Normalizer version: `skill.v2.1`.
- Repair-only change: reward scoring, file diff metadata extraction, and token aggregation are unchanged.

## Before / After

| run | skill.v2 repair episodes | skill.v2.1 repair episodes | change |
| --- | --- | --- | --- |
| `swe_bench_repro` | planned=1, unexpected=1, total=2 | planned=1, unexpected=1, total=2 | unchanged |
| `agentless_repro` | planned=1, unexpected=0, total=1 | planned=1, unexpected=0, total=1 | unchanged |
| `swe_agent_repro` | planned=1, unexpected=0, total=1 | planned=1, unexpected=0, total=1 | unchanged; `[7,10]` remains `planned_tdd_red` |
| `repobench_repro` | planned=1, unexpected=4, total=5 | planned=2, unexpected=2, total=4 | `[7,9]` reclassified to `planned_tdd_red`; duplicate `[11,15]` import-path failures merged |
| `reflexion_repro` | planned=3, unexpected=0, total=3 | planned=3, unexpected=0, total=3 | unchanged |
| `swe_bench_multimodal_repro` | planned=3, unexpected=1, total=4 | planned=3, unexpected=1, total=4 | unchanged |

## Merged Incident

`repobench_repro` turn span `[11,15]` is now one `unexpected_failure` episode:

- `failing_command`: `python scripts/run_smoke.py`
- `failing_commands`:
  - `python scripts/run_smoke.py`
  - `python scripts/run_experiment.py`
- root cause: `ModuleNotFoundError: No module named 'src'`
- `edited_files`: `scripts/run_experiment.py`, `scripts/run_smoke.py`, `tests/test_reproduction.py`
- `repair_success`: `true`

## Unexpected Failure Incidents After v2.1

The four manually audited genuine unexpected incidents are preserved:

| run | span | edited_files | repair_success |
| --- | --- | --- | --- |
| `swe_bench_repro` | `[23,26]` | `pytest.ini` | `true` |
| `repobench_repro` | `[9,10]` | `src/fixture.py` | `true` |
| `repobench_repro` | `[11,15]` | `scripts/run_experiment.py`, `scripts/run_smoke.py`, `tests/test_reproduction.py` | `true` |
| `swe_bench_multimodal_repro` | `[18,20]` | `ambiguity_audit.md`, `reproduction_contract.json`, `src/swebench_multimodal_repro/fixture_runner.py` | `true` |
