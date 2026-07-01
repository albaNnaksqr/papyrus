# Trajectory Extraction Audit

Date: 2026-07-01

This audit checks whether the rule-based trajectory extractor can turn the six current Codex `paper2repro-skill` deep runs into useful code-agent behavior records. The goal is not to claim that every extracted event is perfect. The goal is to decide whether the new fields are good enough to support a Papyrus trajectory dataset story, and where the extraction rules still need calibration.

## Scope

Input projects were read from:

`/home/kps_spark/workspace/papyrus/output/code_agent_deep_runs/`

Generated records were written to:

- `portfolio_results/code_agent_deep_runs/normalized_runs.jsonl`
- `portfolio_results/code_agent_deep_runs/normalized_summary.json`
- `portfolio_results/code_agent_deep_runs/portfolio_summary.json`
- `portfolio_results/code_agent_deep_runs/portfolio_dataset_card.md`
- `portfolio_results/code_agent_deep_runs/code_agent_trajectory_data_pipeline.md`

The normalized records now include four derived trajectory fields:

- `trajectory.actions`: semantic actions such as `paper_inspect`, `contract_write`, `implement`, `run_smoke`, `repair`, `run_experiment`, `evaluate`, and `report`.
- `trajectory.edit_metadata`: patch operation, edited files, coarse file roles, and line counts.
- `trajectory.repair_attempts`: failed validation command, repair edit turns, next verification command, and resolved flag.
- `trajectory.reflection_events`: assistant text linked to a nearby failure and repair edit.

## Coverage Summary

| paper_id | actions | edit_metadata | repair_attempts | reflection_events | verdict |
|---|---:|---:|---:|---:|---|
| `swe_bench_repro` | 21 | 6 | 2 | 2 | Strong test-repair signal after evaluator-contract failure and pytest collection failure. |
| `agentless_repro` | 18 | 5 | 1 | 1 | Useful red-to-green signal, but the single repair remains unresolved by the immediate verification rule. |
| `swe_agent_repro` | 10 | 3 | 2 | 1 | Compact trajectory; repair loops are visible, but final report edits are classified as repair because they follow a compound validation failure. |
| `repobench_repro` | 19 | 6 | 5 | 4 | Richest repair/reflection sample; exposes repeated script-entrypoint debugging. |
| `reflexion_repro` | 20 | 6 | 4 | 3 | Strong reflection sample; captures behavior-level red tests and corrective implementation. |
| `swe_bench_multimodal_repro` | 28 | 7 | 4 | 3 | Strong multimodal repair sample; captures visual regression and nested-git patch root cause. |

All six records now have non-empty `actions`, `edit_metadata`, `repair_attempts`, and `reflection_events`.

## Rule Calibration Done In This Pass

The first extraction pass over-counted repair attempts. It treated exploratory command failures, such as `rg` no-match and `sed` file reads, as repair seeds. That caused initial implementation patches to be swallowed into `repair`.

The extractor was tightened before this audit:

- read-only commands such as `rg`, `sed`, `cat`, `find`, `ls`, `head`, and `tail` are no longer repair seeds;
- repair attempts now start only from failed validation-like commands: pytest, unittest, smoke scripts, experiment scripts, evaluator scripts, `py_compile`, or `compileall`;
- absolute patch paths under the project directory are normalized to project-relative paths;
- relative paths that include the project directory prefix are trimmed to the path inside that project.

This changed the observed repair counts from noisy values like 6-10 per record to the current 1-5 range.

## Useful Extracted Signals

### SWE-bench

The extractor captured two concrete repair episodes:

- `PYTHONPATH=src pytest -q tests/test_evaluator_contract.py` failed, followed by implementation and contract/report patches, then the same targeted pytest command resolved.
- A broad `PYTHONPATH=src pytest -q` run collected intentionally broken fixture tests. The linked reflection identifies the root cause and the repair adds pytest scoping so normal project tests collect only `tests/`.

This is a good sample for teaching an agent to separate project tests from fixture tests.

### Agentless

The record captures a red-to-green shaped loop:

- unit discovery fails on missing pipeline behavior;
- implementation files and scripts are patched;
- reflection states that the missing-module failure is established and the implementation is in place.

The immediate verification is marked unresolved because the next validation command still fails. This is useful as a partial repair sample, but not as a clean success trajectory.

### SWE-agent

The extractor identifies:

- test files written first;
- missing `AgentComputerInterface` import failure;
- implementation patch for fixture creation, ACI command semantics, scripted agent, and runner/evaluator scripts;
- later compound validation success after report/gap updates.

This is a compact but useful action-pattern sample for inspect/edit/test loops.

### RepoBench

This is the best repair-rich sample:

- first unit failure at a missing API boundary;
- implementation of fixture data, lexical retrieval, completion rankers, metrics, and JSON scripts;
- repeated failures around direct script execution;
- reflection identifies `sys.path` as the root cause for `scripts/` entrypoints.

This record is valuable for failure taxonomy and repair supervision.

### Reflexion

The extracted reflections line up with the paper's core concept:

- first red run fails at import time;
- stub tightening moves the signal from missing module to behavior;
- behavioral red step confirms the second reflected attempt is still false;
- the next implementation conditions corrected behavior on reflection text.

This is a strong sample for "verbal reflection changes next action" data.

### SWE-bench Multimodal

The extracted trajectory captures a meaningful multimodal repair chain:

- red checks fail because runner package and renderer are missing;
- implementation adds fixture runner and local visual issue assets;
- later root-cause reflection identifies `git apply` resolving paths at the parent repository root;
- repair switches to a workspace-scoped patch command.

This record is useful because the failure is not only textual; it is tied to visual regression and workspace layout.

## Known Extraction Limitations

The current extractor is useful, but still not a gold labeler.

1. **Compound commands are coarse.** A command like `pip install ... && python scripts/run_smoke.py && ...` is treated as one validation event. If one subcommand fails, the rule cannot identify which sub-step caused the failure.

2. **Duplicate failures can share one repair.** If a turn runs multiple failing validation commands, each command may become its own repair attempt even when one subsequent patch addresses both. This appears in `swe_bench_multimodal_repro`.

3. **Immediate verification can understate success.** `resolved` only checks the next validation-like command after the repair edit. If the next command is a narrower regression test or still fails before a later successful full run, the repair can be marked unresolved even when the overall run succeeds.

4. **Reflection extraction is keyword-based.** It catches useful text such as "root cause" and "failed because", but it may miss quiet reasoning or include procedural notes that are not deep reflection.

5. **Edit roles are coarse.** File-role labels are strong enough for dataset filtering, but they are not yet precise enough to distinguish, for example, evaluator harness code from product implementation in all path layouts.

6. **Status often remains `observed`.** Some raw trace entries do not expose a clean exit code or pass/fail phrase. Those actions are kept rather than guessed.

## Dataset Implication

The new rule-based extraction changes the portfolio from "raw tool traces plus reward labels" into a more credible trajectory dataset:

> Papyrus can compile Codex paper-reproduction runs into auditable code-agent behavior records: semantic actions, edit roles, validation failures, repair attempts, reflection snippets, reward signals, and failure taxonomy.

The current output is good enough for a portfolio data story and for manual audit. It is not yet good enough to claim fully automatic training-label quality without human review.

## Recommended Next Step

Add a small human-labeled calibration set over these six records:

- mark each extracted `repair_attempt` as `true_positive`, `partial`, or `false_positive`;
- mark each `reflection_event` as `root_cause`, `plan_adjustment`, `procedural`, or `false_positive`;
- compute precision by record and by rule type;
- use those labels to tighten duplicate repair grouping and compound-command handling.

That would turn this audit from qualitative evidence into a measurable normalizer-quality result.
