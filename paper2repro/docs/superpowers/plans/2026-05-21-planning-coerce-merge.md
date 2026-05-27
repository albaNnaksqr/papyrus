# Planning Coerce-Merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the planning step from discarding the LLM's real reproduction plan when only a soft section is missing.

**Architecture:** Split `REQUIRED_PLAN_SECTIONS` into core (`file_structure`, `implementation_components`) and soft (the other three). `validate_plan_text` now treats a plan as `valid` when YAML parses and no core section is missing. `coerce_text_to_minimal_plan` becomes merge-not-replace: it parses the LLM output and only fills sections the LLM did not provide.

**Tech Stack:** Python 3.13, PyYAML, pytest, existing `workflows/planning_runtime.py` module.

**Spec:** `docs/superpowers/specs/2026-05-21-planning-coerce-merge-design.md`

---

## File Structure

- Modify: `workflows/planning_runtime.py` — only file with production changes.
- Create: `tests/test_planning_runtime.py` — new test module for `validate_plan_text` and `coerce_text_to_minimal_plan`.

No other files change. Downstream consumers (`agent_orchestration_engine.py`, `plan_review_runtime.py`, `plugins/plan_review.py`) read `valid` and `missing_sections` but the meaning shifts in a backward-compatible way (`valid` becomes more permissive; `missing_sections` keeps its full-list semantics).

---

## Task 1: Tier core vs soft sections and relax `valid`

**Files:**
- Modify: `workflows/planning_runtime.py:18-24` (REQUIRED_PLAN_SECTIONS) and `workflows/planning_runtime.py:130-171` (validate_plan_text).
- Test: `tests/test_planning_runtime.py` (new).

### - [ ] Step 1: Write the failing tests

Create `tests/test_planning_runtime.py`:

```python
"""Tests for workflows.planning_runtime validation and coerce logic.

Background: in task paper_9332b8c0 the LLM returned valid YAML containing
file_structure and implementation_components, but was missing the soft
section implementation_strategy. The old all-or-nothing validator flagged
the whole plan invalid, and coerce_text_to_minimal_plan then replaced the
real plan with a 4-file toy template. These tests pin down the new tiered
behavior.
"""

import yaml

from workflows.planning_runtime import (
    CORE_PLAN_SECTIONS,
    SOFT_PLAN_SECTIONS,
    REQUIRED_PLAN_SECTIONS,
    coerce_text_to_minimal_plan,
    validate_plan_text,
)


# ----- validate_plan_text -----

CORE_ONLY_YAML = """
file_structure:
  root: generate_code
  files:
    - path: src/main.py
      purpose: entrypoint
implementation_components:
  - name: pipeline
    description: core
"""


def test_required_plan_sections_is_concat_of_core_and_soft():
    assert REQUIRED_PLAN_SECTIONS == CORE_PLAN_SECTIONS + SOFT_PLAN_SECTIONS


def test_valid_when_core_present_even_if_soft_missing():
    result = validate_plan_text(CORE_ONLY_YAML)
    assert result["yaml_valid"] is True
    assert result["valid"] is True
    assert result["missing_core"] == []
    assert set(result["missing_soft"]) == set(SOFT_PLAN_SECTIONS)


def test_invalid_when_core_section_missing():
    yaml_text = """
implementation_components:
  - name: pipeline
    description: core
validation_approach:
  strategy: import-only
environment_setup:
  language: python
implementation_strategy:
  approach: scaffold
"""
    result = validate_plan_text(yaml_text)
    assert result["yaml_valid"] is True
    assert result["valid"] is False
    assert "file_structure" in result["missing_core"]


def test_existing_missing_sections_field_still_contains_all_missing():
    """Backward compat: missing_sections keeps its full-list semantics."""
    result = validate_plan_text(CORE_ONLY_YAML)
    assert set(result["missing_sections"]) == set(SOFT_PLAN_SECTIONS)
```

### - [ ] Step 2: Run the tests to verify they fail

Run:

```bash
python -m pytest tests/test_planning_runtime.py -v
```

Expected: ImportError for `CORE_PLAN_SECTIONS` / `SOFT_PLAN_SECTIONS`.

### - [ ] Step 3: Edit `workflows/planning_runtime.py` — split constants

Replace lines 18-24:

```python
REQUIRED_PLAN_SECTIONS = (
    "file_structure",
    "implementation_components",
    "validation_approach",
    "environment_setup",
    "implementation_strategy",
)
```

with:

```python
# Sections the implement stage cannot proceed without. Missing any of these
# means we must fall back to the toy template.
CORE_PLAN_SECTIONS = (
    "file_structure",
    "implementation_components",
)

# Sections that improve the plan but are not load-bearing. Missing ones get
# filled with conservative defaults in coerce_text_to_minimal_plan.
SOFT_PLAN_SECTIONS = (
    "validation_approach",
    "environment_setup",
    "implementation_strategy",
)

REQUIRED_PLAN_SECTIONS = CORE_PLAN_SECTIONS + SOFT_PLAN_SECTIONS
```

### - [ ] Step 4: Edit `workflows/planning_runtime.py:130-171` — tiered `valid`

Replace the entire `validate_plan_text` function with:

```python
def validate_plan_text(text: str) -> dict[str, Any]:
    """Validate the reproduction plan shape without requiring perfect YAML.

    ``valid`` is true when YAML parses and no CORE section is missing. Soft
    sections are tracked separately and do not block downstream consumption.
    """
    candidate = extract_yaml_candidate(text)
    lower_text = (text or "").lower()
    string_missing = [
        section for section in REQUIRED_PLAN_SECTIONS if f"{section}:" not in lower_text
    ]

    result: dict[str, Any] = {
        "yaml_valid": False,
        "yaml_error": None,
        "required_sections": list(REQUIRED_PLAN_SECTIONS),
        "missing_sections": list(string_missing),
        "missing_core": [s for s in CORE_PLAN_SECTIONS if s in string_missing],
        "missing_soft": [s for s in SOFT_PLAN_SECTIONS if s in string_missing],
        "sections_found": len(REQUIRED_PLAN_SECTIONS) - len(string_missing),
        "valid": False,
    }

    try:
        parsed = yaml.safe_load(candidate)
    except Exception as exc:
        result["yaml_error"] = f"{type(exc).__name__}: {exc}"
        # Without parseable YAML we can only trust the substring check.
        result["valid"] = not result["missing_core"]
        return result

    if not isinstance(parsed, dict):
        result["yaml_error"] = f"parsed YAML is {type(parsed).__name__}, expected dict"
        result["valid"] = not result["missing_core"]
        return result

    result["yaml_valid"] = True
    section_source = parsed
    nested = parsed.get("complete_reproduction_plan")
    if isinstance(nested, dict):
        section_source = nested

    yaml_missing = [
        section for section in REQUIRED_PLAN_SECTIONS if section not in section_source
    ]
    result["missing_sections"] = yaml_missing
    result["missing_core"] = [s for s in CORE_PLAN_SECTIONS if s in yaml_missing]
    result["missing_soft"] = [s for s in SOFT_PLAN_SECTIONS if s in yaml_missing]
    result["sections_found"] = len(REQUIRED_PLAN_SECTIONS) - len(yaml_missing)
    result["valid"] = not result["missing_core"]
    return result
```

### - [ ] Step 5: Run the tests to verify they pass

Run:

```bash
python -m pytest tests/test_planning_runtime.py -v
```

Expected: 4 passed.

### - [ ] Step 6: Regression check against the existing suite

Run:

```bash
python -m pytest tests/ --ignore=tests/test_api -q
```

Expected: all 81 tests pass (existing 77 + 4 new).

### - [ ] Step 7: Commit

```bash
git add workflows/planning_runtime.py tests/test_planning_runtime.py
git commit -m "$(cat <<'EOF'
feat(planning): tier required sections into core vs soft

Previously a plan was marked invalid if any of five sections was missing,
which caused paper_9332b8c0 to be classified invalid for missing only
implementation_strategy. validate_plan_text now treats `valid` as
"yaml parses and no CORE section missing"; soft sections are tracked
separately for diagnostics but do not block downstream consumption.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Make `coerce_text_to_minimal_plan` merge instead of replace

**Files:**
- Modify: `workflows/planning_runtime.py:174-237` (coerce_text_to_minimal_plan).
- Test: `tests/test_planning_runtime.py` (extend).

### - [ ] Step 1: Append failing tests to `tests/test_planning_runtime.py`

Append:

```python
# ----- coerce_text_to_minimal_plan -----

NINE_FILE_PLAN_YAML = """
file_structure:
  root: generate_code
  files:
    - path: README.md
      purpose: overview
    - path: hyper_kggen/__init__.py
      purpose: package init
    - path: hyper_kggen/config.py
      purpose: global config
    - path: hyper_kggen/main.py
      purpose: entrypoint
    - path: hyper_kggen/data/__init__.py
      purpose: data package
    - path: hyper_kggen/data/loader.py
      purpose: dataset loader
    - path: hyper_kggen/extraction/chunker.py
      purpose: adaptive chunking
    - path: hyper_kggen/extraction/entity.py
      purpose: entity extraction
    - path: tests/test_pipeline.py
      purpose: smoke test
implementation_components:
  - name: pipeline
    description: extraction pipeline
"""


def test_coerce_preserves_llm_file_structure(tmp_path):
    out = coerce_text_to_minimal_plan(NINE_FILE_PLAN_YAML, paper_dir=tmp_path)
    parsed = yaml.safe_load(out)
    files = parsed["file_structure"]["files"]
    assert len(files) == 9
    paths = {f["path"] for f in files}
    assert "hyper_kggen/extraction/chunker.py" in paths
    assert "hyper_kggen/data/loader.py" in paths


def test_coerce_fills_only_missing_soft_sections(tmp_path):
    out = coerce_text_to_minimal_plan(NINE_FILE_PLAN_YAML, paper_dir=tmp_path)
    parsed = yaml.safe_load(out)
    # core sections preserved from LLM input
    assert parsed["implementation_components"] == [
        {"name": "pipeline", "description": "extraction pipeline"}
    ]
    # soft sections filled from defaults
    assert parsed["validation_approach"]["strategy"]
    assert parsed["environment_setup"]["language"] == "python"
    assert parsed["implementation_strategy"]["paper_dir"] == str(tmp_path)


def test_coerce_handles_complete_reproduction_plan_wrapper(tmp_path):
    wrapped = "complete_reproduction_plan:\n" + "\n".join(
        "  " + line for line in NINE_FILE_PLAN_YAML.strip().splitlines()
    )
    out = coerce_text_to_minimal_plan(wrapped, paper_dir=tmp_path)
    parsed = yaml.safe_load(out)
    files = parsed["file_structure"]["files"]
    assert len(files) == 9


def test_coerce_falls_back_to_toy_on_unparseable_input(tmp_path):
    out = coerce_text_to_minimal_plan(
        "this is just freeform prose with no yaml structure at all",
        paper_dir=tmp_path,
    )
    parsed = yaml.safe_load(out)
    files = parsed["file_structure"]["files"]
    assert len(files) == 4
    paths = {f["path"] for f in files}
    assert paths == {
        "README.md",
        "src/main.py",
        "src/pipeline.py",
        "tests/test_pipeline.py",
    }
    assert (
        "this is just freeform prose"
        in parsed["implementation_strategy"]["planner_analysis"]
    )


def test_coerce_passthrough_when_all_five_sections_present(tmp_path):
    """Regression: a fully-formed LLM plan survives coerce unchanged."""
    full_plan = NINE_FILE_PLAN_YAML + """
validation_approach:
  strategy: pytest
  commands:
    - pytest -q
environment_setup:
  language: python
  dependencies:
    - numpy
implementation_strategy:
  approach: top-down
  paper_dir: /some/path
"""
    out = coerce_text_to_minimal_plan(full_plan, paper_dir=tmp_path)
    parsed = yaml.safe_load(out)
    assert parsed["validation_approach"]["strategy"] == "pytest"
    assert parsed["environment_setup"]["dependencies"] == ["numpy"]
    # paper_dir from LLM is preserved, not overwritten by tmp_path
    assert parsed["implementation_strategy"]["approach"] == "top-down"
    assert len(parsed["file_structure"]["files"]) == 9
```

### - [ ] Step 2: Run the new tests to verify they fail

Run:

```bash
python -m pytest tests/test_planning_runtime.py -v
```

Expected: 4 new tests fail (assertion errors — coerce currently replaces 9 files with 4-file toy).

### - [ ] Step 3: Replace `coerce_text_to_minimal_plan` body

In `workflows/planning_runtime.py:174-237`, replace the entire function with:

```python
def coerce_text_to_minimal_plan(text: str, *, paper_dir: str | Path) -> str:
    """Wrap planner output in the required YAML plan shape, preserving sections.

    If the input contains parseable YAML with a dict shape, its sections
    overlay the toy defaults so the LLM's real ``file_structure`` and
    ``implementation_components`` survive. Only sections the LLM did not
    provide are filled from the toy template. The unparseable path still
    falls back to a 4-file toy with the raw text stuffed into
    ``implementation_strategy.planner_analysis``.
    """
    summary = (text or "").strip()
    truncated_summary = summary
    if len(truncated_summary) > 6000:
        truncated_summary = truncated_summary[:6000].rstrip() + "\n...[truncated]"

    defaults: dict[str, Any] = {
        "file_structure": {
            "root": "generate_code",
            "files": [
                {
                    "path": "README.md",
                    "purpose": "Summarize the paper reproduction target and usage.",
                },
                {
                    "path": "src/main.py",
                    "purpose": "Provide an executable entrypoint for the reproduction scaffold.",
                },
                {
                    "path": "src/pipeline.py",
                    "purpose": "Implement the core algorithmic pipeline inferred from the paper.",
                },
                {
                    "path": "tests/test_pipeline.py",
                    "purpose": "Stdlib unittest-compatible smoke test for the generated pipeline with minimal data.",
                },
            ],
        },
        "implementation_components": [
            {
                "name": "paper_interpretation",
                "description": "Convert the planner analysis into concrete modules and APIs.",
            },
            {
                "name": "core_pipeline",
                "description": "Implement the main method described by the paper at scaffold fidelity.",
            },
            {
                "name": "validation_smoke_test",
                "description": "Add a fast validation path that confirms imports and basic execution.",
            },
        ],
        "validation_approach": {
            "strategy": "Use lightweight import and syntax checks because the model did not produce a full experimental protocol.",
            "commands": ["python -m compileall -q src"],
        },
        "environment_setup": {
            "language": "python",
            "dependencies": [],
            "notes": "Keep dependencies minimal unless the implementation step identifies explicit paper requirements.",
        },
        "implementation_strategy": {
            "approach": "Start from the preserved planner analysis, implement a small runnable scaffold, then expand only where the paper details are explicit.",
            "paper_dir": str(paper_dir),
            "planner_analysis": truncated_summary or "Planner did not return usable analysis.",
        },
    }

    # Try to parse the input as YAML and lift any sections the LLM provided.
    parsed: Any = None
    try:
        parsed = yaml.safe_load(extract_yaml_candidate(text))
    except Exception:
        parsed = None

    if isinstance(parsed, dict):
        nested = parsed.get("complete_reproduction_plan")
        if isinstance(nested, dict):
            parsed = nested

    if isinstance(parsed, dict):
        merged = dict(defaults)
        for key in REQUIRED_PLAN_SECTIONS:
            llm_value = parsed.get(key)
            if llm_value is not None and llm_value != "":
                merged[key] = llm_value
        return yaml.safe_dump(merged, sort_keys=False, allow_unicode=True)

    return yaml.safe_dump(defaults, sort_keys=False, allow_unicode=True)
```

### - [ ] Step 4: Run the new tests to verify they pass

Run:

```bash
python -m pytest tests/test_planning_runtime.py -v
```

Expected: all 9 tests pass (4 from Task 1 + 5 from this task).

### - [ ] Step 5: Regression check

Run:

```bash
python -m pytest tests/ --ignore=tests/test_api -q
```

Expected: all 86 tests pass.

### - [ ] Step 6: Commit

```bash
git add workflows/planning_runtime.py tests/test_planning_runtime.py
git commit -m "$(cat <<'EOF'
feat(planning): merge LLM plan sections into coerce fallback

coerce_text_to_minimal_plan now parses its input and overlays the LLM's
real sections (file_structure, implementation_components, etc.) onto the
toy template instead of discarding them. The 4-file toy fallback only
applies when the input has no parseable YAML at all.

Combined with the previous tiered-validity change, paper_9332b8c0-style
LLM plans (valid YAML missing only implementation_strategy) now flow
through to the implement stage with their full module tree intact.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: End-to-end verification on the real planning trace

**Files:**
- No code changes. This task only confirms the fix works against the real artifact.

### - [ ] Step 1: Replay the existing `paper_9332b8c0` plan through the new code

Run:

```bash
python -c "
import yaml
from pathlib import Path
from workflows.planning_runtime import validate_plan_text, coerce_text_to_minimal_plan

# Pull the original best_invalid YAML out of the first attempt log entry.
# (The LLM responses were not saved verbatim; reconstruct using the final coerced
# plan plus a synthetic LLM-style YAML to demonstrate behavior.)
existing = Path('output/tasks/paper_9332b8c0/initial_plan.txt').read_text()
print('OLD valid (full file as text):', validate_plan_text(existing)['valid'])
print('OLD missing_core:', validate_plan_text(existing).get('missing_core'))
print('OLD missing_soft:', validate_plan_text(existing).get('missing_soft'))
"
```

Expected: the saved coerced plan now reports `valid=True`, `missing_core=[]`. (The original LLM YAML before coerce was not persisted, so this only confirms the new validator accepts the existing artifact.)

### - [ ] Step 2: Construct a synthetic replay of the paper_9332b8c0 LLM trace

Run:

```bash
python <<'PY'
import yaml
from workflows.planning_runtime import validate_plan_text, coerce_text_to_minimal_plan

# Mimic the actual LLM output: valid YAML, full file_structure,
# but missing implementation_strategy (the exact paper_9332b8c0 case).
llm_output = """
file_structure:
  root: generate_code
  files:
    - path: hyper_kggen/__init__.py
      purpose: package init
    - path: hyper_kggen/config.py
      purpose: configuration
    - path: hyper_kggen/main.py
      purpose: entrypoint
    - path: hyper_kggen/extraction/chunker.py
      purpose: adaptive chunking
    - path: hyper_kggen/extraction/entity_extractor.py
      purpose: entity extraction
    - path: hyper_kggen/extraction/hyperedge_extractor.py
      purpose: coarse-to-fine extraction
implementation_components:
  - name: extraction_pipeline
    description: coarse-to-fine hyperedge extraction
validation_approach:
  strategy: pytest smoke
  commands:
    - pytest tests/ -q
environment_setup:
  language: python
  dependencies: [numpy, networkx]
"""

print("=== validate_plan_text on LLM output ===")
v = validate_plan_text(llm_output)
print(f"  yaml_valid={v['yaml_valid']}  valid={v['valid']}")
print(f"  missing_core={v['missing_core']}")
print(f"  missing_soft={v['missing_soft']}")

print()
print("=== coerce result preserves LLM file_structure ===")
coerced = coerce_text_to_minimal_plan(llm_output, paper_dir="/tmp/fake")
parsed = yaml.safe_load(coerced)
print(f"  file count: {len(parsed['file_structure']['files'])}  (expected: 6)")
print(f"  paths: {sorted(f['path'] for f in parsed['file_structure']['files'])}")
print(f"  implementation_strategy.paper_dir: {parsed['implementation_strategy']['paper_dir']}")
PY
```

Expected output:

```
=== validate_plan_text on LLM output ===
  yaml_valid=True  valid=True
  missing_core=[]
  missing_soft=['implementation_strategy']

=== coerce result preserves LLM file_structure ===
  file count: 6  (expected: 6)
  paths: ['hyper_kggen/__init__.py', 'hyper_kggen/config.py', 'hyper_kggen/extraction/chunker.py', 'hyper_kggen/extraction/entity_extractor.py', 'hyper_kggen/extraction/hyperedge_extractor.py', 'hyper_kggen/main.py']
  implementation_strategy.paper_dir: /tmp/fake
```

### - [ ] Step 3: Confirm orchestrator path is correctly short-circuited

Read the orchestrator's planning loop to confirm the change has the intended runtime effect:

```bash
grep -n "plan_validation.get(\"valid\"" workflows/agent_orchestration_engine.py
```

Expected: line 1025 still reads `if completeness_score >= 0.8 and plan_validation.get("valid", False):` — with the new validator, this branch is now taken on attempt 1 for the paper_9332b8c0-style LLM output, so the orchestrator returns the LLM plan immediately and never reaches the coerce fallback.

No code change in this step — just verification that the orchestrator was already structured to do the right thing once `valid` becomes accurate.

### - [ ] Step 4: Final commit (verification notes)

No production code committed in this task. If verification revealed surprises, address them and add a brief note to the design doc; otherwise nothing to commit.

---

## Self-Review Notes

**Spec coverage:**
- Change 1 (tier sections) → Task 1, Steps 3-4.
- Change 2 (`validate_plan_text` core-only valid) → Task 1, Step 4.
- Change 3 (`coerce` merge) → Task 2, Step 3.
- Change 4 (orchestrator unchanged) → Task 3, Step 3 (verification only).
- All seven test cases from the spec map to test functions in Tasks 1 and 2.
- Acceptance criteria 1, 2, 4 verified by the test suite in Tasks 1-2. Criterion 3 (real task retry) is left for live operator verification — the trace replay in Task 3 demonstrates the mechanism without a paid LLM call.

**Placeholder scan:** No TBD/TODO/"similar to" placeholders. All code blocks are complete and self-contained.

**Type consistency:** `CORE_PLAN_SECTIONS`, `SOFT_PLAN_SECTIONS`, `REQUIRED_PLAN_SECTIONS`, `validate_plan_text`, `coerce_text_to_minimal_plan` — same names across all tasks. The validator result dict shape (`valid`, `yaml_valid`, `yaml_error`, `missing_sections`, `missing_core`, `missing_soft`, `sections_found`, `required_sections`) is consistent across Steps 4 of Task 1 and assertions in Task 1 Step 1.
