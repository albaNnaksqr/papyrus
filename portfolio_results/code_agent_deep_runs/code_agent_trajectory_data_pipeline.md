# Code Agent Trajectory Data Pipeline

This case study packages the three most relevant runs for a code-agent data role. The common data product is a normalized trajectory record that links a paper claim to executable local evidence and explicit fidelity gaps.

## Mainline Papers

| paper | role | outcome | strict_score | confidence | benchmark_fidelity | key gaps |
|---|---:|---:|---:|---:|---:|---|
| SWE-bench: Can Language Models Resolve Real-World GitHub Issues? | mainline | success | 1 | high | bounded_fixture_only | full_benchmark_not_attempted, environment_gap, synthetic_fixture |
| SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering | mainline | success | 1 | high | mechanism_demo | synthetic_fixture |
| SWE-bench Multimodal: Do AI Systems Generalize to Visual Software Domains? | mainline | success | 1 | high | bounded_fixture_only | full_benchmark_not_attempted, environment_gap, synthetic_fixture |

## Data Product

- `SWE-bench`: patch-evaluation schema with FAIL_TO_PASS and PASS_TO_PASS evidence.
- `SWE-agent`: inspect/edit/test action trace over a local software issue.
- `SWE-bench Multimodal`: visual issue fixture with pre/post screenshot evidence.

## Why This Matters

For code-agent data work, the useful artifact is not a polished demo alone. It is the structured record that can be filtered, scored, audited, and turned into training or evaluation examples. These three runs cover patch evaluation, agent tool-use trajectories, and multimodal software evidence.

## Remaining Work

- Replace selected synthetic fixtures with real issue subsets where licensing and runtime allow it.
- Add stricter schema checks for action traces, screenshots, and test status maps.
- Separate bounded-claim success from full-benchmark fidelity in every public view.
