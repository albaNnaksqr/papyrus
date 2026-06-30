# Code Agent Reproduction Portfolio Dataset Card

This portfolio treats paper reproductions as trajectory-data samples, not as leaderboard replications. Each run records a bounded claim, executable evidence, failure labels, and reward signals for downstream analysis.

## Summary

- Total runs: 6
- Mainline case: SWE-bench: Can Language Models Resolve Real-World GitHub Issues?, SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering, SWE-bench Multimodal: Do AI Systems Generalize to Visual Software Domains?
- Confidence counts: {'high': 5, 'medium': 1}
- Benchmark fidelity counts: {'bounded_fixture_only': 3, 'local_claim_reproduction': 1, 'local_substitute': 1, 'mechanism_demo': 1}

## Code Agent Trajectory Data Pipeline

The mainline case focuses on SWE-bench, SWE-agent, and SWE-bench Multimodal as a three-part trajectory data pipeline.

## Score Semantics

- `overall_score`: compatibility score that ignores missing reward signals.
- `strict_score`: weighted score where missing reward signals count as zero.
- `signal_coverage`: fraction of reward weight backed by observed signals.
- `benchmark_fidelity`: distance from the paper's original benchmark setting.

## Runs

| paper | role | outcome | strict_score | confidence | benchmark_fidelity | key gaps |
|---|---:|---:|---:|---:|---:|---|
| SWE-bench: Can Language Models Resolve Real-World GitHub Issues? | mainline | success | 1 | high | bounded_fixture_only | full_benchmark_not_attempted, environment_gap, synthetic_fixture |
| Agentless: Demystifying LLM-based Software Engineering Agents | supporting | partial_success | 0.86 | high | bounded_fixture_only | full_benchmark_not_attempted, synthetic_fixture |
| SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering | mainline | success | 1 | high | mechanism_demo | synthetic_fixture |
| RepoBench: Benchmarking Repository-Level Code Auto-Completion Systems | supporting | success | 0.85 | medium | local_substitute | unavailable_original_benchmark_data, synthetic_fixture |
| Reflexion: Language Agents with Verbal Reinforcement Learning | supporting | success | 1 | high | local_claim_reproduction | none |
| SWE-bench Multimodal: Do AI Systems Generalize to Visual Software Domains? | mainline | success | 1 | high | bounded_fixture_only | full_benchmark_not_attempted, environment_gap, synthetic_fixture |

## Positioning

The strongest claim is not that these are full-paper reproductions. The stronger portfolio claim is that the project converts code-agent papers into auditable trajectory data: issue or task setup, local evidence, patch or action sequence, test outcomes, honesty labels, and scoring metadata.
