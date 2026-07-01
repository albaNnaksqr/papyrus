# Paired Trajectory Comparison

This report is generated from normalized Papyrus trajectory JSONL records. It pairs runs by normalized paper id and compares the data utility of each run, not the intrinsic quality of the underlying agent.

## Aggregate

| side | paired_runs | avg_strict_score | actions | edits | repairs | reflections |
|---|---:|---:|---:|---:|---:|---:|
| codex | 3 | 0.95 | 67 | 19 | 13 | 10 |
| claude | 3 | 0.625 | 61 | 27 | 2 | 1 |
| delta (claude-codex) |  | -0.325 | -6 | 8 | -11 | -9 |

## Paired Runs

| paper | codex outcome / strict | claude outcome / strict | strict_delta | action_delta | repair_delta | reflection_delta | codex tags | claude tags | preferred uses |
|---|---:|---:|---:|---:|---:|---:|---|---|---|
| Reflexion: Language Agents with Verbal Reinforcement Learning | success / 1.0 | success / 0.85 | -0.15 | -6 | -4 | -3 | `artifact_sample`, `trajectory_sample`, `repair_sample` | `artifact_sample`, `trajectory_sample`, `gap_sample` | artifact_sample:codex, trajectory_sample:codex, repair_sample:codex |
| RepoBench: Benchmarking Repository-Level Code Auto-Completion Systems | success / 0.85 | partial_success / 0.675 | -0.175 | 6 | -3 | -3 | `artifact_sample`, `trajectory_sample`, `repair_sample`, `gap_sample` | `artifact_sample`, `trajectory_sample`, `repair_sample` | artifact_sample:codex, trajectory_sample:claude, repair_sample:codex |
| SWE-bench Multimodal: Do AI Systems Generalize to Visual Software Domains? | success / 1.0 | partial_success / 0.35 | -0.65 | -6 | -4 | -3 | `artifact_sample`, `trajectory_sample`, `repair_sample`, `gap_sample` | `artifact_sample`, `trajectory_sample`, `gap_sample`, `negative_sample` | artifact_sample:codex, trajectory_sample:claude, repair_sample:codex |

## Usefulness Tags

- `artifact_sample`: useful as a bounded executable reproduction artifact.
- `trajectory_sample`: enough action/edit structure to analyze agent behavior.
- `repair_sample`: contains validation-failure to repair/reflection supervision.
- `gap_sample`: contains explicit benchmark, resource, fixture, or environment gaps.
- `negative_sample`: useful as a failed, invalid, or low-fidelity example.

## Unpaired Runs

- codex: agentless_repro, swe_agent_repro, swe_bench_repro
- claude: none
