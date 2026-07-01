# Claude Paired Pilot Report

Date: 2026-07-01

This pilot runs three Claude `paper2repro` reproductions against papers that already have Codex deep-run outputs. The goal is not to rank Claude against Codex. The goal is to test whether Papyrus can convert two agents' paper-reproduction work into comparable trajectory records: semantic actions, edit roles, validation attempts, repair loops, reward signals, and fidelity gaps.

## Scope

Paired papers:

- `RepoBench: Benchmarking Repository-Level Code Auto-Completion Systems`
- `Reflexion: Language Agents with Verbal Reinforcement Learning`
- `SWE-bench Multimodal: Do AI Systems Generalize to Visual Software Domains?`

Claude outputs were written under:

`/home/kps_spark/workspace/papyrus/output/claude_paired_runs/`

Normalized Claude records were generated at:

- `portfolio_results/code_agent_deep_runs/claude_paired_normalized_runs.jsonl`
- `portfolio_results/code_agent_deep_runs/claude_paired_normalized_summary.json`

## Harness Observation

The first normalization pass exposed a real parser gap: Claude traces store tool results as separate `turn.tool_results` entries keyed by `tool_use_id`, and use tool names such as `Read`, `Bash`, `Write`, and `Edit`. The previous extractor only handled Codex-style `exec_command` and `apply_patch` calls with inline results.

This pass added Claude trace support:

- `Read` PDF calls are classified as `paper_inspect`;
- `Bash` calls are classified as shell commands and validation steps;
- `Write` and `Edit` calls are classified as file edits with file-role metadata;
- separate Claude `tool_results` are joined back to their tool calls before success/failure and repair rules run.

This matters because it turns paired runs from unstructured transcripts into comparable code-agent behavior data.

## Claude Summary

| paper_id | outcome | strict_score | confidence | actions | edits | repairs | reflections | notes |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `repobench_claude` | partial_success | 0.675 | medium | 25 | 11 | 2 | 1 | Real RepoBench-R lexical data loaded and evaluated; semantic CodeBERT/UniXcoder path was CPU-bound and stopped. |
| `reflexion_claude` | success | 0.85 | medium | 14 | 2 | 0 | 0 | Bounded algorithm reproduction using mock LLM fixtures; reproduces Reflexion improvement and no-reflection ablation directionally. |
| `swe_bench_multimodal_claude` | partial_success | 0.35 | medium | 22 | 14 | 0 | 0 | Bounded multimodal SWE fixture; smoke/experiment/evaluator pass, but image effect is not meaningful because mock patching resolves both conditions. |

Aggregate Claude trajectory signals:

- `actions`: 61
- `edit_metadata`: 27
- `repair_attempts`: 2
- `reflection_events`: 1

## Paired Comparison

| paper | Codex outcome / strict | Claude outcome / strict | trajectory difference | interpretation |
|---|---:|---:|---|---|
| RepoBench | success / 0.85 | partial_success / 0.675 | Codex: 19 actions, 6 edits, 5 repairs, 4 reflections. Claude: 25 actions, 11 edits, 2 repairs, 1 reflection. | Claude attempted a more data-authentic path by loading real RepoBench-R data, but hit CPU limits on semantic encoders. Codex produced a cleaner bounded reproduction trace. |
| Reflexion | success / 1.0 | success / 0.85 | Codex: 20 actions, 6 edits, 4 repairs, 3 reflections. Claude: 14 actions, 2 edits, 0 repairs, 0 reflections. | Both reproduce the core bounded mechanism. Codex trace is richer as a repair/reflection training sample; Claude is shorter and more direct. |
| SWE-bench Multimodal | success / 1.0 | partial_success / 0.35 | Codex: 28 actions, 7 edits, 4 repairs, 3 reflections. Claude: 22 actions, 14 edits, 0 repairs, 0 reflections. | Claude built a larger set of modules but did not produce a clean end-to-end agent-run trace before manual validation. Codex remains the stronger trajectory sample for this paper. |

## Result Interpretation

The main positive result is not that Claude improved the reproduction portfolio. It did not. The positive result is that Papyrus can now expose useful cross-agent differences:

- Claude can choose a more authentic data route, as in RepoBench, but the trace shows where resource limits stop the run.
- Codex historical runs contain richer repair/reflection loops, which are more valuable for code-agent behavior datasets.
- A high-level reproduction score alone hides important differences. For example, Reflexion is `success` for both agents, but Codex has much richer repair trajectory supervision.
- The normalizer can now reveal whether a run is useful as an executable artifact, a trajectory training sample, or both.

## Negative Findings

This pilot also gives useful negative evidence:

- Claude paired runs are not automatically better portfolio artifacts than the existing Codex runs.
- Bounded fixture success can overstate paper fidelity. SWE-bench Multimodal with mock gold patches produces 100% resolve rate in both image/no-image conditions, so it cannot validate the paper's image benefit claim.
- Repair and reflection labels remain conservative. Claude produced many direct file writes, but few validation-failure-to-repair loops, so its records are weaker for repair-supervision extraction.
- A paired pilot needs runtime policy. RepoBench semantic retrieval on CPU became too expensive, and SWE-bench Multimodal required manual validation after Claude spent too long implementing modules.

## Implication For Papyrus

This run supports the project positioning:

> Papyrus is not just a paper reproduction collector. It can compile agent work into audit-ready trajectory data and compare agent behavior across the same technical target.

For a code-agent data role, this is the stronger story. The valuable artifact is the normalized record that separates:

- paper claim fidelity;
- executable local evidence;
- tool-use and edit trajectory;
- validation failures and repairs;
- resource or benchmark gaps;
- reward and confidence labels.

## Recommended Next Step

Turn this paired pilot into a small calibration set:

1. Add a `paired_run_id` field linking `*_repro` and `*_claude` records by paper.
2. Add manual labels for whether each run is useful as `artifact`, `trajectory_sample`, `repair_sample`, or `negative_sample`.
3. Compute pairwise deltas in strict score, action count, repair count, and benchmark fidelity.
4. Expand only after the paired report can be generated from normalized JSON without hand-written tables.

The immediate product next step is a paired-report generator, not more ad hoc runs.
