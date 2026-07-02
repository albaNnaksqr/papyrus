# Repair Extraction Manual Audit (normalizer skill.v2)

Audit date: 2026-07-02
Audit target: the 6 `unexpected_failure` repair episodes extracted by `skill.v2` backfill over `normalized_runs.jsonl`.
Method: for each episode, read the surrounding agent narration and tool output in the normalized turns; then run a strict false-negative sweep (execution-failure signatures: `Traceback (most recent call last)`, unittest/pytest `FAILED`/`ERROR:` lines, `ModuleNotFoundError`/`ImportError`/`SyntaxError`/`AssertionError`) over all tool results outside episode spans.

## Verdict per episode

| # | record | turn_span | verdict | notes |
|---|---|---|---|---|
| 1 | swe_bench_repro | [23, 26] | correct | pytest collection ImportError fixed via `pytest.ini`; genuine unexpected failure, repair succeeded. |
| 2 | repobench_repro | [7, 9] | **misclassified** | Agent narration at turn 7: "The first test run failed at the **expected** missing API boundary." This is a planned TDD red step and should be `planned_tdd_red`. Its `repair_success=false` is an episode-chaining artifact, not a real failed repair. |
| 3 | repobench_repro | [9, 10] | correct | Genuine discovery: first fixture leaked helper names via in-file imports, making the single-file baseline too strong; agent strengthened the fixture instead of weakening the contract. High-value struggle sample. |
| 4 | repobench_repro | [11, 15] | correct but **double-counted** | `run_smoke.py` and `run_experiment.py` both failed with the same root cause (`ModuleNotFoundError: No module named 'src'`, missing project root on `sys.path`). One incident, two identical episodes (same span, same edited files, same retest). |
| 5 | repobench_repro | [11, 15] | duplicate of #4 | See above. |
| 6 | swe_bench_multimodal_repro | [18, 20] | correct | Genuine failure of the git-worktree patch-application test; repair touched `fixture_runner.py` and honestly updated `reproduction_contract.json` / `ambiguity_audit.md`. |

## False-negative sweep

No true misses. Strong-signal hits outside episodes were all benign:

- paper-text extraction output containing words like ERROR/FAIL (paper content, not execution);
- file-content displays echoing source code;
- one deliberate probe in `swe_agent_repro` turn 5 (`from paper2repro_skill_path import nope`), an intentional negative check, not an unnoticed failure.

## Corrected counts

After removing the misclassification and the duplicate, the genuine unexpected-failure incident count is **4** (swe_bench 1, repobench 2, swe_bench_multimodal 1), not 6. `repair_success` labels on the genuine incidents are all consistent with the retest evidence.

## Extractor defects to fix

1. **Planned-red detection should weigh agent narration.** When the agent's own text within the failing turn declares the failure expected ("expected", "red step", tests added immediately before), classify as `planned_tdd_red` even if the failing command is not the first test run. Repro case: repobench_repro turns [7, 9].
2. **Deduplicate episodes by incident.** Multiple failing commands sharing the same turn span, root-cause signature, and edited-file set should collapse into one episode with a `failing_commands` list. Repro case: repobench_repro turns [11, 15].
3. (Minor) Chained episodes: when a failed retest opens the next episode, `repair_success=false` on the earlier episode should be distinguishable from "agent gave up" — consider a `superseded_by` link.

## Calibration takeaway

Precision on kind labels: 4/6. Span boundaries and edited-file attribution were correct in all six. Recall: no missed incidents found. The extractor is usable for hard-tier runs after fixing defects 1-2; counts derived from `repair_attempts` should deduplicate by incident until then.
