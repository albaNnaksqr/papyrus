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
    count_planned_py_files,
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


# ----- plan size cap -----
# Run10 (LoRA) blew up to 27-file plan during repair, burning 1268 LLM
# calls / 24M tokens for what should be ~5-file algorithm. The cap stops
# the LLM from over-engineering the project at planning time.


def test_count_planned_py_files_picks_up_paths_in_tree():
    plan = """
file_structure: |
    src/
    ├── main.py
    ├── core.py
    └── pipeline.py
"""
    assert count_planned_py_files(plan) == 3


def test_count_planned_py_files_picks_up_paths_in_list():
    plan = """
file_structure:
  - src/main.py
  - src/lora.py
  - experiments/run_glue.py
"""
    assert count_planned_py_files(plan) == 3


def test_count_planned_py_files_deduplicates_repeated_paths():
    plan = """
file_structure:
  - src/main.py
implementation_components:
  - name: foo
    files: src/main.py
"""
    assert count_planned_py_files(plan) == 1


def test_validate_plan_accepts_when_file_count_under_cap():
    plan = """
file_structure:
  - src/a.py
  - src/b.py
implementation_components:
  - name: x
"""
    result = validate_plan_text(plan)
    assert result["py_file_count"] == 2
    assert result["too_many_py_files"] is False
    assert result["valid"] is True


def test_validate_plan_rejects_when_file_count_exceeds_cap(monkeypatch):
    monkeypatch.setenv("PAPER2CODE_MAX_PLANNED_FILES", "3")
    plan = """
file_structure:
  - src/a.py
  - src/b.py
  - src/c.py
  - src/d.py
implementation_components:
  - name: x
"""
    result = validate_plan_text(plan)
    assert result["py_file_count"] == 4
    assert result["py_file_limit"] == 3
    assert result["too_many_py_files"] is True
    assert result["valid"] is False


def test_validate_plan_includes_cap_fields_even_when_yaml_breaks(monkeypatch):
    """Cap counter is computed before YAML parsing; broken YAML doesn't hide it."""
    monkeypatch.setenv("PAPER2CODE_MAX_PLANNED_FILES", "2")
    # 3 paths referenced in free-form text; bogus YAML.
    plan = "file_structure: ::: not yaml ::: src/a.py src/b.py src/c.py implementation_components: x"
    result = validate_plan_text(plan)
    assert result["py_file_count"] == 3
    assert result["too_many_py_files"] is True
    assert result["valid"] is False


def test_validate_plan_distinguishes_oversized_from_missing_core(monkeypatch):
    """For degraded acceptance: separate 'unusable plan' (missing core) from
    'usable but oversized' (LLM couldn't compress)."""
    monkeypatch.setenv("PAPER2CODE_MAX_PLANNED_FILES", "2")

    # 3 files: too many but core sections present → valid=False, but a smart
    # caller can still accept this by checking missing_core empty.
    oversized = """
file_structure:
  - src/a.py
  - src/b.py
  - src/c.py
implementation_components:
  - name: x
"""
    r = validate_plan_text(oversized)
    assert r["too_many_py_files"] is True
    assert r["missing_core"] == []  # core sections present
    assert r["valid"] is False  # strict valid still False

    # No core sections: strictly unusable.
    no_core = """
some_random_field:
  - src/a.py
  - src/b.py
"""
    r2 = validate_plan_text(no_core)
    assert r2["missing_core"]  # has missing core sections
    assert r2["valid"] is False


def test_validate_plan_env_var_zero_falls_back_to_default(monkeypatch):
    """Bad PAPER2CODE_MAX_PLANNED_FILES should not disable the cap."""
    monkeypatch.setenv("PAPER2CODE_MAX_PLANNED_FILES", "0")
    plan = """
file_structure:
""" + "\n".join(f"  - src/f{i}.py" for i in range(20)) + """
implementation_components:
  - name: x
"""
    result = validate_plan_text(plan)
    # default limit 12, plan has 20 files
    assert result["py_file_limit"] == 12
    assert result["too_many_py_files"] is True
