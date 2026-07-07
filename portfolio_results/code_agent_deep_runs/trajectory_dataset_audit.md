# Code-Agent Trajectory Dataset Audit

Audit target: `portfolio_results/code_agent_deep_runs/normalized_runs.jsonl`

Audit date: 2026-07-01

## Executive Summary

This audit treats the six code-agent paper reproductions as trajectory-data samples, not as leaderboard replications. The main question is:

> Are the Codex skill-run reproductions normalized into useful, auditable code-agent trajectory records?

Short answer: yes for portfolio and audit use, not yet for training-scale use.

The dataset is already strong as a portfolio artifact because it preserves paper claims, reproduction contracts, tool-use trajectories, generated artifacts, reward components, fidelity labels, and failure taxonomy. The largest gaps are:

- all six current records are Codex skill runs; Claude paired runs are not yet present;
- `repair_attempts` is empty across the portfolio, so repair-loop data is underrepresented;
- token usage and cost are missing;
- file edits are counted but not yet normalized into affected files or semantic diff classes;
- several successes depend on synthetic/local fixtures and must remain fidelity-labeled.

## Portfolio Snapshot

| metric | value |
|---|---:|
| total normalized runs | 6 |
| runner | `skill` for all records |
| agent host | `codex` for all records |
| outcomes | 5 success, 1 partial success |
| confidence | 5 high, 1 medium |
| benchmark fidelity | 3 bounded fixture, 1 mechanism demo, 1 local substitute, 1 local claim reproduction |
| common failure labels | `synthetic_fixture`, `full_benchmark_not_attempted`, `environment_gap` |

## Record-Level Audit

| paper_id | paper | data value | status |
|---|---|---|---|
| `swe_bench_repro` | SWE-bench | Patch-evaluation schema: FAIL_TO_PASS/PASS_TO_PASS, patch application, evaluator semantics. | Portfolio-ready |
| `agentless_repro` | Agentless | Localization-repair-validation pipeline without autonomous tool loop. | Portfolio-ready partial-success sample |
| `swe_agent_repro` | SWE-agent | Inspect/edit/test agent-computer-interface mechanism demo. | Dataset-ready candidate |
| `repobench_repro` | RepoBench | Repository-context retrieval/completion local substitute. | Portfolio-ready with missing smoke signal |
| `reflexion_repro` | Reflexion | Verbal reflection and retry-style bounded reproduction. | Dataset-ready candidate |
| `swe_bench_multimodal_repro` | SWE-bench Multimodal | Visual issue fixture with multimodal evidence framing. | Portfolio-ready bounded sample |

## Aggregate Findings

### Strengths

The current normalized records are useful because they connect:

- paper claim and expected metrics;
- reproduction contract and fidelity scope;
- agent turns, tool calls, commands, and file edits;
- generated artifacts and result files;
- reward components and missing-signal accounting;
- failure labels and evidence paths.

This is exactly the right direction for a code-agent data role: the output is not just code, but a labeled process trace.

### Gaps

The current dataset should not yet be described as Codex-vs-Claude trajectory data. It is currently Codex-only:

```text
runner: skill
agent_host: codex
model: gpt-5.5
```

It is also not yet a complete repair dataset. The normalizer exposes `repair_attempts`, but all six records currently have an empty list. The raw traces may contain testing and correction behavior, but that behavior has not been segmented into explicit repair episodes.

Token usage and cost are also absent. This limits comparison of trajectory efficiency across agents.

## Detailed Notes By Record

### `swe_bench_repro`

Strong points:

- Clear target: issue-level patch evaluation.
- Explicit success criteria: precondition observed, patch applied, resolved, resolution rate.
- Good artifact coverage: scripts, evaluator, result files, reproduction report.
- Reward is complete: strict score and signal coverage are both 1.0.

Limitations:

- Fidelity is bounded: synthetic local fixture, not full SWE-bench.
- Failure labels correctly include `full_benchmark_not_attempted`, `environment_gap`, and `synthetic_fixture`.

Recommended use:

- Good positive example for patch-evaluation data schema.
- Not suitable as evidence that Papyrus reproduces full SWE-bench.

### `agentless_repro`

Strong points:

- Captures the paper's key structure: localization, repair, patch validation.
- Outcome is honestly marked `partial_success`.
- Reward reflects bounded fidelity: `task_completion=0.65`, `claim_fidelity=0.65`, strict score 0.86.
- Failure labels are useful for negative/preference data.

Limitations:

- Still uses a synthetic local fixture.
- Does not reproduce benchmark-scale Agentless evaluation.
- Repair phases are represented by artifacts and tool calls, not explicit normalized `repair_attempts`.

Recommended use:

- Strong partial-success sample.
- Good candidate for preference data: honest bounded reproduction beats fake full-success framing.

### `swe_agent_repro`

Strong points:

- Best aligned with trajectory-data goals.
- The claim is naturally about agent-computer interaction.
- Trajectory has inspect/edit/test behavior, tool calls, commands, and file edits.
- Fidelity label is `mechanism_demo`, which is more honest than pretending benchmark parity.

Limitations:

- Synthetic fixture remains the primary fidelity gap.
- Action classes are still implicit in tool calls rather than normalized as semantic actions.

Recommended use:

- Dataset-ready candidate after action-class normalization.
- Good public example for "Papyrus captures agent behavior, not only final code."

### `repobench_repro`

Strong points:

- Covers repository-level context and code-completion evaluation.
- Good artifact and trajectory coverage.
- Missing signal is represented correctly: `smoke_pass=null`, strict score 0.85, signal coverage 0.85.
- Confidence is medium, which matches the evidence.

Limitations:

- Original benchmark data is unavailable.
- Local substitute limits the strength of the claim.
- Missing smoke signal should be repaired before promoting to dataset-ready.

Recommended use:

- Portfolio-ready example of honest missing-data handling.
- Useful negative/control sample for data availability failures.

### `reflexion_repro`

Strong points:

- Complete reward signals: strict score 1.0 and signal coverage 1.0.
- No failure labels.
- Good trajectory length and artifact coverage.
- Strong candidate for reflection/failure-memory data.

Limitations:

- The current normalized schema does not explicitly extract reflection episodes or retry deltas.
- To make it valuable as Reflexion data, the normalizer should identify reflection text, prior failure, next action, and reward change.

Recommended use:

- Dataset-ready candidate after reflection-specific event extraction.
- Good anchor for future Claude/Codex paired comparison.

### `swe_bench_multimodal_repro`

Strong points:

- Covers a multimodal software-evidence setting.
- Good phase spans, tool calls, artifacts, and reward coverage.
- Explicitly fidelity-labeled as bounded.

Limitations:

- Full benchmark and environment are not reproduced.
- Visual evidence is represented as artifacts and report content, but the normalized schema does not yet expose screenshot-level fields.

Recommended use:

- Portfolio-ready bounded multimodal sample.
- Needs image/screenshot schema fields before being dataset-ready for multimodal agent work.

## Rubric Assessment

| dimension | assessment |
|---|---|
| Paper and claim grounding | Strong. Each record contains target claims and expected metrics. |
| Reproduction contract quality | Strong. Contract artifacts are consistently present. |
| Trajectory reconstruction | Medium-strong. Tool calls and commands exist; semantic action classes are not normalized yet. |
| Executable evidence | Strong. Scripts, result files, and reports are present for all records. |
| Reward and labels | Strong. Missing signals and confidence are represented. |
| Failure taxonomy | Strong for fidelity gaps; weaker for fine-grained agent behavior failures. |
| Provenance and auditability | Strong. Source files and normalizer version are included. |
| Cross-agent comparability | Weak currently. Codex-only; Claude paired runs are missing. |

Overall readiness: portfolio-ready now; dataset-ready after action-class normalization, repair/reflection extraction, and paired Claude runs.

## What To Improve Next

### 1. Add Claude Paired Runs

Run the same 3-6 papers through Claude using the same `paper2repro-skill` path. Do not compare only final success. Compare:

- claim extraction;
- reproduction level selection;
- ambiguity handling;
- tool-call mix;
- file-edit count;
- test/evaluator evidence;
- report honesty;
- failure labels.

### 2. Normalize Semantic Actions

Add a derived `trajectory.actions` list:

```json
{
  "type": "claim_extract | contract_write | implement | test | repair | evaluate | report",
  "turn_index": 12,
  "tool_refs": ["call_id"],
  "evidence_refs": ["results/reproduction_evaluation.json"],
  "status": "success | failure | partial"
}
```

This turns raw tool traces into training/evaluation-ready process data.

### 3. Extract Repair Attempts

The schema has `repair_attempts`, but current records leave it empty. Add extraction for:

- failing command;
- failure output summary;
- edited files after failure;
- follow-up test command;
- repair success label.

### 4. Add Diff Metadata

File edits should include:

- affected files;
- operation type: create/update/delete;
- approximate diff size;
- whether the edit touched evaluator, implementation, config, or report.

This matters because code-agent data quality depends on edit intent, not only edit count.

### 5. Add Multimodal Evidence Fields

For SWE-bench Multimodal-style runs, expose:

- screenshot paths;
- pre/post visual state;
- visual issue description;
- evaluator relation to screenshot evidence.

### 6. Fill Cost And Token Metadata

Codex and Claude trajectory comparison needs efficiency signals. Add:

- input tokens;
- output tokens;
- total tokens;
- wall time;
- cost if available;
- tool-call count by phase.

## Recommended Public Positioning

Use this claim:

> Papyrus compiles long-horizon paper-reproduction attempts into auditable code-agent trajectory records: claims, contracts, tool traces, artifacts, reward signals, fidelity labels, and failure taxonomy.

Avoid this claim for now:

> Papyrus has proven that its context improves code-agent solve rate.

That downstream claim requires a separate A/B study. The stronger current claim is about data production and auditability.

## Next Audit Gate

The next meaningful milestone is not more SWE-bench smoke tests. It is:

- 3 paired Codex/Claude runs on the same papers;
- explicit semantic action normalization;
- non-empty repair/reflection extraction;
- a manual audit pass on reward and failure labels.

After that, Papyrus can credibly present itself as a code-agent trajectory data compiler rather than a paper-to-code demo.
