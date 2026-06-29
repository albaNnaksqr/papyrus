# Papyrus Agent Trajectory Portfolio v1 Design

## Summary

Papyrus Agent Trajectory Portfolio v1 turns the current Papyrus repository into
a DeepSeek Code Agent data-role portfolio artifact.

The first-stage goal is not to prove that Papyrus can automatically reproduce
arbitrary papers. The goal is to demonstrate a credible Code Agent data loop:

```text
paper reproduction task
  -> real long-horizon agent run
  -> verifiable reproduction artifacts
  -> normalized trajectory schema
  -> reward and failure labels
  -> interview-ready evidence for agent data strategy work
```

The v1 deliverable is a case-backed trajectory pipeline built from three real
paper-reproduction runs. It should be strong enough for resume screening and
technical interviews, while leaving a clean path toward a later mini-benchmark.

## Motivation

The target role is DeepSeek Agent Data Strategy / Code Agent Data Engineering.
Public job descriptions emphasize:

- high-quality Agent training data for code generation and general Agent tasks;
- end-to-end test cases that evaluate usability, code quality, engineering
  quality, and task completion;
- coverage of planning, tool use, multi-turn interaction, and instruction
  following;
- analysis of failure modes from heavy use of Claude Code, Codex, Cursor,
  OpenClaw, or similar coding agents;
- data-side support for RL, reward modeling, and model capability iteration;
- Python scripts for data processing, evaluation, and dataset construction.

Papyrus already has assets that map naturally to those requirements:

- `paper2repro-skill` produces high-context host-agent reproduction trajectories.
- `paper2repro` server produces phase-based runs with gates, repair attempts,
  structured logs, and UI replay.
- `paper2trace` produces static SFT / DPO / ReAct-style paper reasoning data.
- `examples/boyer_moore_skill` already contains a real reproduction project,
  evaluation outputs, explicit gaps, and an exported agent trace.

The gap is not conceptual. The gap is that current artifacts are still
tool-specific logs and reports. They need to be normalized, labeled, and
presented as a Code Agent data system.

## Positioning

External one-liner:

> Papyrus turns paper reproduction into labeled long-horizon Code Agent
> trajectories with reproducible reward signals.

Chinese positioning:

> Papyrus 用论文复现作为可验证长程任务，把真实 Code Agent 运行过程沉淀为带 reward、失败标注和复现证据的轨迹数据。

The first public-facing version should call itself a "case-backed trajectory
pipeline", not a benchmark and not a data factory. "Benchmark" becomes accurate
only after several paired runs exist and the evaluation protocol is stable.

## Scope

### In Scope

- Define `trajectory schema v1` for paper-reproduction Code Agent runs.
- Convert `examples/boyer_moore_skill` into one normalized schema sample.
- Produce two additional real paper-reproduction runs and normalize them.
- Define a reward specification based on reproducible artifacts and gates.
- Define failure taxonomy v0 from observed runs only.
- Write a DeepSeek-facing brief that maps project artifacts to role
  requirements.
- Update project-level narrative only after the data artifacts exist.

### Out of Scope

- Training or fine-tuning a model.
- Running a toy RL experiment.
- Building a public benchmark claim around fewer than five serious cases.
- Improving the React UI as a first-stage priority.
- Expanding `paper2trace` beyond its current static extraction role.
- Claiming fully automated paper reproduction.

## Existing Assets

### `paper2repro-skill`

Primary v1 data source.

It runs inside a host agent such as Claude Code or Codex and produces:

- `paper_structure.json`
- `ambiguity_audit.md`
- `reproduction_contract.json`
- `gap_report.md`
- generated source, configs, smoke and experiment scripts
- `results/reproduction_summary.json`
- `results/reproduction_evaluation.json`
- `REPRODUCTION_REPORT.md`
- `agent_trace.jsonl`

This is the strongest source for teacher-style long-horizon trajectories,
because one host agent carries the context from paper audit through final
report.

### `paper2repro` Server

Secondary v1 source and future paired-run source.

It adds structured phase boundaries and gate signals:

- 可行性评审 / critique
- implementation planning
- artifact contract
- claim contract
- type-check gate
- reproduction gate
- smoke checks
- validation agent
- repair loop
- `events.jsonl`
- `llm.jsonl`
- `mcp.jsonl`
- `trajectory/segments.jsonl`

Server runs are most useful for failure analysis, controlled ablations, and
paired comparisons against skill runs.

### `paper2trace`

Supporting source, not a real agent-trajectory source.

It can still be useful for:

- static SFT / DPO / ReAct paper reasoning samples;
- paper structure and hidden-research-process extraction;
- auxiliary planning or ambiguity data.

In v1 messaging, `paper2trace` must not be described as producing real Code
Agent trajectories.

## Required Cases

V1 requires three real runs.

### Case 1: Boyer-Moore

Current status: existing skill run.

Role:

- successful or approximately successful anchor case;
- demonstrates clear contract, ambiguity audit, evaluation artifacts, and final
  claim-by-claim report;
- first target for schema conversion.

Expected label:

- `task_completion`: partial_success or success;
- `claim_fidelity`: approximate;
- `failure_type`: unavailable_original_benchmark_data, nonportable_hardware_metric.

### Case 2: Algorithm Or Systems Paper

Role:

- expose implementation or environment failure modes;
- ideally has pseudocode or system claims that can be partially verified.

Selection criteria:

- paper is short enough to audit quickly;
- main claim can become a smoke or experiment contract;
- at least one ambiguity or dependency gap is likely.

Expected label:

- one of: partial_success, failed_validation, dependency_failure,
  metric_mismatch, or evaluator_gap.

### Case 3: ML Experiment Paper

Role:

- expose dataset, metric, hyperparameter, and reproducibility gaps.

Selection criteria:

- has a reported table, figure, or metric;
- original dataset or exact hyperparameters are likely unavailable or expensive;
- synthetic or reduced reproduction is possible.

Expected label:

- one of: partial_success, dataset_unavailable, hyperparameter_missing,
  claim_drift, or fake_success_risk.

## Trajectory Schema v1

The schema should be JSON-serializable and stable enough for downstream
conversion scripts, but not over-engineered. The goal is comparison and
inspection, not a universal ontology.

Top-level shape:

```json
{
  "schema_version": "papyrus.trajectory.v1",
  "paper": {},
  "run": {},
  "contracts": {},
  "trajectory": {},
  "artifacts": {},
  "reward": {},
  "labels": {},
  "failure_analysis": {},
  "provenance": {}
}
```

### `paper`

Required fields:

- `paper_id`
- `title`
- `domain`
- `paper_type`: `algorithm`, `ml_experiment`, `systems`, or `theoretical`
- `source_path`
- `target_claims`
- `expected_metrics`

### `run`

Required fields:

- `run_id`
- `runner`: `skill`, `server`, or `manual`
- `agent_host`: `claude_code`, `codex`, `paper2repro_server`, or `unknown`
- `model`
- `started_at`
- `ended_at`
- `wall_time_seconds`
- `token_usage`
- `cost_usd`
- `status`

Unknown values are allowed when the source log does not expose them, but the
field must still exist with `null`.

### `contracts`

Required fields:

- `paper_structure`
- `ambiguity_audit`
- `reproduction_contract`
- `claim_contract`
- `gap_report`

For skill runs, `claim_contract` may be `null`. For server runs,
`ambiguity_audit` may be `null` unless explicitly produced.

### `trajectory`

Required fields:

- `turns`
- `phase_spans`
- `tool_calls`
- `tool_results`
- `commands`
- `file_edits`
- `repair_attempts`
- `final_report_summary`

The schema should preserve source references back to raw logs so reviewers can
inspect evidence rather than trust a derived summary.

### `artifacts`

Required fields:

- `generated_project_path`
- `files`
- `configs`
- `smoke_script`
- `experiment_script`
- `evaluator_script`
- `result_files`
- `reproduction_report`

### `reward`

Required fields:

- `task_completion`
- `code_runs`
- `smoke_pass`
- `experiment_completed`
- `evaluator_pass`
- `claim_fidelity`
- `report_honesty`
- `overall_score`

`overall_score` should be a transparent weighted score for inspection, not a
claimed training reward yet.

Recommended v1 scoring:

```text
overall_score =
  0.20 * task_completion
+ 0.15 * code_runs
+ 0.15 * smoke_pass
+ 0.15 * experiment_completed
+ 0.20 * claim_fidelity
+ 0.15 * report_honesty
```

Scores are normalized to `[0, 1]`. If a field cannot be evaluated, it should be
`null` and excluded from the denominator with the missing field recorded in
`reward.missing_signals`.

### `labels`

Required fields:

- `reproduction_level`
- `outcome`: `success`, `partial_success`, `failure`, or `invalid_run`
- `failure_types`
- `repair_success`
- `human_preference`
- `data_split`: `portfolio`, `train_candidate`, `eval_candidate`, or
  `holdout_candidate`

### `failure_analysis`

Required fields:

- `primary_failure_type`
- `secondary_failure_types`
- `evidence`
- `root_cause`
- `data_remedy`
- `evaluation_remedy`

`data_remedy` describes what training or evaluation data could reduce this
failure in future agents.

### `provenance`

Required fields:

- `source_files`
- `normalizer_version`
- `created_at`
- `notes`

## Reward Specification

Reward v1 is an evaluation artifact, not an RL training claim.

The reward specification should define:

- which evidence files determine each reward field;
- how automatic gates map to numeric scores;
- how claim fidelity is judged from reproduction evaluation and final report;
- when a run is invalid rather than failed;
- how missing data, unavailable corpora, and honest downgrade should be scored.

Important distinctions:

- A run can pass smoke tests and still fail claim fidelity.
- An honest partial reproduction should score higher than fake success.
- Missing original data is not automatically an agent failure if it is detected,
  documented, and handled through an explicit downgraded contract.
- Report honesty is a first-class reward signal because fake success is a
  critical Code Agent failure mode.

## Failure Taxonomy v0

The taxonomy must be evidence-backed. A failure type is allowed into v0 only if
it appears in at least one of the three v1 cases.

Initial candidate labels:

- `dataset_unavailable`
- `hyperparameter_missing`
- `metric_mismatch`
- `claim_drift`
- `fake_success_risk`
- `dependency_failure`
- `environment_failure`
- `tool_call_failure`
- `repair_no_op`
- `repair_regression`
- `evaluator_gap`
- `over_planning`
- `under_specified_contract`
- `nonportable_hardware_metric`
- `unavailable_original_benchmark_data`

Each taxonomy entry should contain:

- definition;
- observed cases;
- evidence artifact path;
- impact on reward;
- recommended data or evaluation remedy.

## Conversion Pipeline

V1 should implement converters as small Python scripts under a dedicated
trajectory module, for example:

```text
papyrus/
  trajectory/
    README.md
    schema_v1.json
    normalize_skill_run.py
    normalize_server_run.py
    reward.py
    failure_taxonomy.py
    examples/
      boyer_moore_skill.normalized.json
```

`normalize_skill_run.py` is mandatory for v1.

Inputs:

- path to a skill reproduction project;
- path to `agent_trace.jsonl`;
- optional paper metadata override.

Output:

- one normalized schema JSON.

`normalize_server_run.py` can be a partial converter in v1 if server runs are
not yet stable. It must at least document the intended mapping from server logs
to schema fields.

## DeepSeek-Facing Brief

Create `docs/deepseek-agent-data-brief.md`.

The brief should be one to two pages and contain:

- the one-line positioning;
- the three-run evidence table;
- JD requirement to Papyrus artifact mapping;
- schema diagram;
- reward signal explanation;
- failure taxonomy examples;
- resume bullets.

This document is the interview handout. It should be concrete, not aspirational.

## README Changes

README should be updated only after at least one normalized sample exists.

The first viewport should communicate:

- Papyrus is about Code Agent trajectory data, not only paper-to-code;
- paper reproduction is used because it is long-horizon and verifiable;
- the repository contains three tools but the data loop is the unifying story;
- current status is a case-backed pipeline, not a public benchmark.

Avoid claims such as:

- "fully automated paper reproduction";
- "benchmark" before enough cases exist;
- "training-ready dataset" before quality filtering is implemented.

## Acceptance Criteria

V1 is complete when:

1. Three real paper-reproduction runs exist and are documented.
2. At least one run is normalized into `trajectory schema v1`.
3. All three runs have outcome labels and reward fields, even if some reward
   components are `null` with documented missing signals.
4. Failure taxonomy v0 contains only observed labels.
5. `reward_spec.md` explains how scores are derived from artifacts.
6. `docs/deepseek-agent-data-brief.md` maps Papyrus to DeepSeek Agent data-role
   requirements.
7. README no longer over-centers paper-to-code or UI framing.

## Risks

### Risk: Too Few Real Runs

One case makes the project look over-framed. V1 must reach three cases before
the DeepSeek-facing brief is treated as final.

### Risk: Server Debugging Consumes the Timeline

The first stage should not depend on making server runs perfect. Skill runs are
the reliable path to real host-agent trajectories. Server normalization can be
partial if needed.

### Risk: `paper2trace` Is Over-Sold

`paper2trace` should be described as static training-sample extraction. Calling
it agent trajectory data would weaken the project's credibility.

### Risk: Reward Looks Arbitrary

The reward spec must point to concrete evidence files and explain missing
signals. Numeric scores are for inspection and ranking, not a claim that RL is
already solved.

### Risk: Failure Labels Are Invented

Failure taxonomy entries must cite observed runs. Candidate labels without
evidence stay out of v0.

## Implementation Order

1. Create schema and reward specification.
2. Normalize the Boyer-Moore skill run.
3. Choose two additional papers and run `paper2repro-skill`.
4. Normalize the two new runs.
5. Build failure taxonomy v0 from the three runs.
6. Write DeepSeek-facing brief.
7. Update README and resume bullets.

## Open Decision

The immediate decision is the two additional papers. They should be chosen for
diagnostic value, not for likelihood of full success.

Recommended selection:

- one algorithm or systems paper with clear pseudocode or interface claims;
- one ML experiment paper with dataset, metric, or hyperparameter gaps.

The chosen papers should be short enough to run quickly and permissive enough
to include derived artifacts in the repository.
