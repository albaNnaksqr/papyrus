# Planning Coerce-Merge Design

**Date:** 2026-05-21
**Status:** Approved
**Scope:** Small — fix tier; do not extend the plan schema or change downstream consumers.

## Problem

`paper_9332b8c0` produced a 6-file toy reproduction of a paper that calls for ~25 files across multiple modules. Investigation showed the LLM planner actually returned a faithful YAML plan with a full `hyper_kggen/` module tree, but the orchestrator threw it away.

### Root cause

Evidence from `output/tasks/paper_9332b8c0/planning_attempts.jsonl` and `planning_result_meta.json`:

- All three planning attempts returned `yaml_valid: true` and a real `file_structure`.
- All three were flagged `valid: false` because they were **missing one section: `implementation_strategy`**.
- After max_retries, `coerce_text_to_minimal_plan` ran and **replaced the entire LLM plan** with a hard-coded 4-file toy template (`README.md`, `src/main.py`, `src/pipeline.py`, `tests/test_pipeline.py`), shoving the LLM's real output into the `implementation_strategy.planner_analysis` free-text field.
- `planning_result_meta.json` confirms: `"source": "coerced_from_freeform"`.
- The implementation agent then implemented the 4-file toy. The README it generated (from paper knowledge) advertised the full `hyper_kggen/` tree, which `generated_project_lint` later flagged as missing files.

The bug is not in the planner LLM — its output was correct. The bug is in the validator's all-or-nothing definition of `valid` and in the coerce step's replace-not-merge behavior.

## Goal

When the planner LLM produces a parseable YAML plan with the core sections, use it. Reserve the toy fallback for the case where the LLM output has no parseable YAML at all.

## Non-goals

- Extending the plan schema with function signatures or per-file API contracts.
- Switching downstream consumers (`artifact_contract`, `claim_contract`) from regex extraction to structured field reads.
- Changing the planning prompt or model.
- Adding LLM-as-judge or any new validation layer.

These would be sensible follow-ups but are out of scope for this change.

## Design

Two changes, both in `workflows/planning_runtime.py`. The orchestrator does not change.

### Change 1: Tier the required sections

Split `REQUIRED_PLAN_SECTIONS` into core and soft:

```python
CORE_PLAN_SECTIONS = ("file_structure", "implementation_components")
SOFT_PLAN_SECTIONS = ("validation_approach", "environment_setup", "implementation_strategy")
REQUIRED_PLAN_SECTIONS = CORE_PLAN_SECTIONS + SOFT_PLAN_SECTIONS
```

`REQUIRED_PLAN_SECTIONS` is kept (same name, same contents) so any current importer still works. Only the meaning of `valid` shifts.

### Change 2: `validate_plan_text` — `valid` keyed on core only

After YAML parsing succeeds:

- `valid` is true when `yaml_valid` is true and **no core section is missing**.
- New fields in the result dict: `missing_core` (list), `missing_soft` (list).
- Existing fields (`missing_sections`, `sections_found`, `yaml_valid`, `yaml_error`) keep their current shape, so existing code reading them does not need to change.

Behavioral impact on `paper_9332b8c0`'s real trace: attempt 1 already returned a parseable YAML with `file_structure` and `implementation_components` present. With the new rule, attempt 1 is accepted, the orchestrator returns immediately, and `coerce_text_to_minimal_plan` never runs.

### Change 3: `coerce_text_to_minimal_plan` — merge, not replace

When called, the function first tries to extract and parse YAML from the input text (including the existing `complete_reproduction_plan:` wrapper convention).

- If parsing produces a dict, the LLM-provided sections overlay the toy defaults. The toy template is only used to fill keys the LLM did not provide.
- If parsing fails or returns a non-dict, the function preserves its current behavior: emit the toy template with the raw text stuffed into `implementation_strategy.planner_analysis`.

Truncation of `planner_analysis` to ~6000 chars is preserved for the unparseable path.

### Change 4: Orchestrator code path stays the same

`workflows/agent_orchestration_engine.py:1114-1144` continues to call `coerce_text_to_minimal_plan(fallback_source, paper_dir=paper_dir)` when max_retries is exhausted. The orchestrator's behavior changes only because:

1. After Change 2, fewer attempts reach max_retries (most real LLM outputs become valid on first try).
2. After Change 3, when coerce does run, it preserves whatever the LLM gave instead of discarding it.

This means no edits to `agent_orchestration_engine.py` in this scope.

## Test plan

New tests live in `tests/test_planning_runtime.py` (or extend an existing planning test file if one exists — verify during implementation).

1. **Core-only YAML is valid** — `yaml_valid: true` with `file_structure` and `implementation_components`, missing all three soft sections, returns `valid: true` with non-empty `missing_soft`.
2. **Missing core section is invalid** — YAML with `implementation_components` but no `file_structure` returns `valid: false` and a non-empty `missing_core`.
3. **Coerce preserves LLM file_structure** — input is YAML with a 9-file `file_structure`; coerce output yaml-parses to a plan whose `file_structure.files` still has 9 entries (not the 4-file toy default).
4. **Coerce handles `complete_reproduction_plan:` wrapper** — input wraps the plan one level deep; coerce still recognizes and preserves the inner sections.
5. **Coerce fills only missing soft sections** — input has `file_structure` and `implementation_components` only; output also contains the three soft sections, populated with the existing toy defaults.
6. **Coerce falls back to toy template on unparseable input** — input is free-form prose with no YAML; output is the existing 4-file toy template with the prose preserved in `implementation_strategy.planner_analysis`.
7. **Regression: full 5-section LLM YAML still passes through unchanged** — input has all five sections; coerce output is semantically equal (key-set match for the five sections).

Run after each change:

```bash
python -m pytest tests/ --ignore=tests/test_api -q
```

Existing tests must still pass; the 77-test baseline gives a strong regression signal.

## Risks

| Risk | Mitigation |
|---|---|
| Downstream readers of `validate_plan_text` result depend on the old `valid` meaning (strict five-section requirement). | Grep shows `valid` is only read in `planning_runtime.py` itself and in the orchestrator's `is_existing_plan_usable`. Re-verify during implementation. |
| LLM YAML uses a key shape we don't expect (e.g. `file_structure` is a list instead of a dict with `files:`). | Merge logic operates at the section-key level. Whatever shape the LLM emits replaces the default for that key — downstream consumers already tolerate either shape via regex. |
| Coerce now produces plans with semantics the toy fallback never had to handle (real module trees, real dependencies). | This is the intended behavior. Downstream consumers (`artifact_contract`, `claim_contract`, `implement_code_pure`) already accept real plans — they were written to handle real plans and degraded to toys only because of this bug. |
| `coerced_from_freeform` meta marker becomes ambiguous (LLM-preserved vs. true fallback). | Out of scope for this change. The meta still says `coerced_from_freeform` whichever branch coerce took. If we need to distinguish later, it can be added in a separate observability change that touches the orchestrator's meta write site. |

## Out of scope, but worth noting

- `paper_9332b8c0`'s second-order issue: even with a faithful 9-file plan, the implement agent may still fall short. This change does not solve that — it only restores the floor (faithful plan reaches implement). Diagnosing implement-stage shortfall is a separate investigation.
- The repair-loop `read_code_mem` runaway and 0-file fail-fast were addressed in earlier sessions and are unaffected by this change.

## Acceptance

The change is accepted when:

1. All seven new tests pass.
2. The existing 77-test baseline (non-API tests) still passes.
3. A retry on `paper_9332b8c0` (or any task with a similar planner trace) produces `planning_result_meta.json` with `source` ≠ `coerced_from_freeform`, and the resulting `initial_plan.txt` contains the LLM's real `file_structure`.
4. The toy 4-file template only appears when planner output had no parseable YAML at all.
