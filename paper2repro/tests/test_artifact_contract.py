import json

from workflows.artifact_contract import (
    ArtifactContract,
    _top_level_py_roots,
    build_contract_from_plan,
    find_file_under_root,
    is_blocked_smoke_command,
    validate_generated_tree_against_contract,
)


def test_build_contract_extracts_single_source_root_and_entrypoint():
    plan = """
file_structure:
  - src/main.py
  - src/extraction/chunker.py
environment_setup:
  package_name: hyper_kggen
implementation_strategy:
  entrypoint: src/main.py
validation_approach:
  smoke_command: python src/main.py --help
"""

    contract = build_contract_from_plan(plan)

    assert contract.project_root == "src"
    assert contract.entrypoint == "src/main.py"
    assert contract.package_name == "hyper_kggen"
    assert contract.smoke_commands == ["python src/main.py --help"]


def test_build_contract_handles_flat_main_py_plan():
    contract = build_contract_from_plan(
        """
file_structure:
  - main.py
"""
    )

    assert contract.project_root == "."
    assert contract.entrypoint == "main.py"
    assert contract.smoke_commands == ["python main.py --help"]


def test_build_contract_filters_pytest_smoke_commands():
    plan = """
file_structure:
  - src/main.py
validation_approach:
  smoke_command: python -m pytest tests/ -v
  smoke_command: python src/main.py --help
"""

    contract = build_contract_from_plan(plan)

    assert contract.smoke_commands == ["python src/main.py --help"]


def test_is_blocked_smoke_command_detects_pytest_forms():
    assert is_blocked_smoke_command("pytest tests")
    assert is_blocked_smoke_command("python -m pytest tests/ -v")
    assert is_blocked_smoke_command("timeout 15 python -m pytest tests | head -60")
    assert not is_blocked_smoke_command("python src/main.py --help")


def test_validate_generated_tree_rejects_multiple_source_roots(tmp_path):
    code_dir = tmp_path / "generate_code"
    (code_dir / "src").mkdir(parents=True)
    (code_dir / "hyper_kggen" / "src").mkdir(parents=True)
    (code_dir / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (code_dir / "hyper_kggen" / "src" / "main.py").write_text(
        "print('bad')\n",
        encoding="utf-8",
    )

    result = validate_generated_tree_against_contract(
        str(code_dir),
        ArtifactContract(
            project_root="src",
            entrypoint="src/main.py",
            package_name="hyper_kggen",
            smoke_commands=["python src/main.py --help"],
        ),
    )

    assert result["status"] == "error"
    assert "multiple project roots" in result["failures"][0]


def test_validate_generated_tree_rejects_absent_expected_source_root(tmp_path):
    code_dir = tmp_path / "generate_code"
    code_dir.mkdir()
    (code_dir / "main.py").write_text("print('ok')\n", encoding="utf-8")

    result = validate_generated_tree_against_contract(
        str(code_dir),
        ArtifactContract(
            project_root="src",
            entrypoint="main.py",
            package_name="hyper_kggen",
            smoke_commands=["python main.py --help"],
        ),
    )

    assert result["status"] == "error"
    assert any("project_root 'src' not found" in f for f in result["failures"])


def test_validate_generated_tree_returns_success_status_and_contract(tmp_path):
    code_dir = tmp_path / "generate_code"
    (code_dir / "src").mkdir(parents=True)
    (code_dir / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
    contract = ArtifactContract(
        project_root="src",
        entrypoint="src/main.py",
        package_name="hyper_kggen",
        smoke_commands=["python src/main.py --help"],
    )

    result = validate_generated_tree_against_contract(str(code_dir), contract)

    assert result["status"] == "success"
    assert result["failures"] == []
    assert result["project_roots"] == ["src"]
    assert result["contract"] == {
        "project_root": "src",
        "entrypoint": "src/main.py",
        "package_name": "hyper_kggen",
        "smoke_commands": ["python src/main.py --help"],
    }
    json.dumps(result)


def test_validate_generated_tree_rejects_empty_entrypoint(tmp_path):
    code_dir = tmp_path / "generate_code"
    (code_dir / "src").mkdir(parents=True)
    (code_dir / "src" / "main.py").write_text("", encoding="utf-8")

    result = validate_generated_tree_against_contract(
        str(code_dir),
        ArtifactContract(
            project_root="src",
            entrypoint="src/main.py",
            package_name="hyper_kggen",
            smoke_commands=["python src/main.py --help"],
        ),
    )

    assert result["status"] == "error"
    assert "empty entrypoint: src/main.py" in result["failures"]


# ----- package-root detection -----
# paper_20260522-2035 + run3 traces showed the plan's file_structure tree
# nests everything under a package directory (e.g. `hyper_kggen/`), but
# build_contract_from_plan only saw the inner `src/...` paths and picked
# project_root=src. The agent then followed the tree (writing to
# hyper_kggen/src/) and disagreed with code_acceptance.


TREE_PLAN_WITH_PACKAGE_ROOT = """
file_structure: |
    hyper_kggen/
    ├── main.py
    ├── config.yaml
    ├── src/
    │   ├── __init__.py
    │   ├── chunking.py
    │   ├── entity_extractor.py
    │   └── hyperedge_extractor.py
    └── tests/
        └── test_pipeline.py
"""


def test_build_contract_recognizes_package_root_from_tree():
    contract = build_contract_from_plan(TREE_PLAN_WITH_PACKAGE_ROOT)
    assert contract.project_root == "hyper_kggen"
    assert contract.entrypoint == "hyper_kggen/main.py"
    # package_name is inferred from the package root when no explicit field
    assert contract.package_name == "hyper_kggen"


def test_build_contract_keeps_flat_layout_without_package_root():
    """Plans without a tree-style package directory keep the old behavior."""
    plan = """
file_structure:
  - src/main.py
  - src/pipeline.py
"""
    contract = build_contract_from_plan(plan)
    assert contract.project_root == "src"
    assert contract.entrypoint == "src/main.py"
    assert contract.package_name is None


def test_build_contract_ignores_src_as_package_root():
    """A bare `src/` at tree top is the source root, not a package wrapper."""
    plan = """
file_structure: |
    src/
    ├── main.py
    └── pipeline.py
"""
    contract = build_contract_from_plan(plan)
    assert contract.project_root == "src"
    assert contract.entrypoint == "src/main.py"


def test_build_contract_explicit_package_name_wins():
    """If the plan provides package_name explicitly, do not overwrite it."""
    plan = (
        TREE_PLAN_WITH_PACKAGE_ROOT
        + "\nenvironment_setup:\n  package_name: explicit_pkg\n"
    )
    contract = build_contract_from_plan(plan)
    # project_root still picks up the tree's package root (this is structural)
    assert contract.project_root == "hyper_kggen"
    # but the explicit package_name field wins
    assert contract.package_name == "explicit_pkg"


def test_build_contract_explicit_entrypoint_within_package_root_kept():
    """If the plan declares entrypoint: hyper_kggen/main.py explicitly, keep it."""
    plan = (
        TREE_PLAN_WITH_PACKAGE_ROOT
        + "\nimplementation_strategy:\n  entrypoint: hyper_kggen/main.py\n"
    )
    contract = build_contract_from_plan(plan)
    assert contract.entrypoint == "hyper_kggen/main.py"


# ----- Plan-tree entrypoint fallback -----
# Run9 (LoRA) showed: plan has no `entrypoint:` and no main.py anywhere in
# the file_structure tree (it uses experiments/run_glue.py). The previous
# default ("<src>/main.py") pointed at a file that doesn't exist, killing
# the run via "missing entrypoint" even though the agent wrote what the
# plan asked for.


def test_build_contract_uses_main_py_from_tree_when_no_explicit_entrypoint():
    """If plan tree contains main.py somewhere, use it as entrypoint."""
    plan = """
file_structure: |
    src/
    ├── core.py
    └── main.py
"""
    contract = build_contract_from_plan(plan)
    # main.py is in the tree (under src/) so we use that path, not a fake one.
    assert contract.entrypoint == "src/main.py"


def test_build_contract_falls_back_to_unique_run_script():
    """LoRA case: no main.py, but a single experiments/run_*.py."""
    plan = """
file_structure:
  - src/lora.py
  - src/model_utils.py
  - experiments/run_glue.py
"""
    contract = build_contract_from_plan(plan)
    assert contract.entrypoint == "experiments/run_glue.py"


def test_build_contract_picks_first_alphabetical_when_multiple_run_scripts():
    """Multiple run_*.py and no main.py: pick first alphabetically (arbitrary
    but deterministic; better to point at a real file than fabricate
    src/main.py)."""
    plan = """
file_structure:
  - src/lora.py
  - experiments/run_nlg.py
  - experiments/run_glue.py
"""
    contract = build_contract_from_plan(plan)
    # 'experiments/run_glue.py' < 'experiments/run_nlg.py' alphabetically
    assert contract.entrypoint == "experiments/run_glue.py"


def test_build_contract_prefers_main_over_run_script():
    plan = """
file_structure:
  - src/main.py
  - experiments/run_glue.py
"""
    contract = build_contract_from_plan(plan)
    assert contract.entrypoint == "src/main.py"


def test_build_contract_handles_yaml_double_quoted_file_structure():
    """Run17 (LoRA) showed: planners sometimes emit file_structure as a
    YAML double-quoted scalar with escaped newlines (\\n) instead of
    a literal block. The old splitlines()-on-raw-text scan saw one big
    line and silently failed to detect the package root, falling back
    to project_root='src' (wrong)."""
    plan = (
        'file_structure: "lora_implementation/\\n'
        '├── README.md\\n'
        '├── src/\\n'
        '│   ├── __init__.py\\n'
        '│   ├── lora.py\\n'
        '│   └── train_utils.py\\n'
        '└── experiments/\\n'
        '    └── run_glue.py"\n'
        'implementation_components: |\n'
        '  - main: lora.py\n'
    )
    contract = build_contract_from_plan(plan)
    assert contract.project_root == "lora_implementation"


def test_build_contract_main_in_package_root_preferred(plan_tree_with_package=None):
    """When tree has both `pkg/main.py` and `pkg/src/extra.py`, prefer
    pkg/main.py (top-level entry feels more like a CLI than a nested one)."""
    plan = """
file_structure: |
    hyper_kggen/
    ├── main.py
    ├── src/
    │   ├── core.py
    │   └── runner.py
"""
    contract = build_contract_from_plan(plan)
    assert contract.entrypoint == "hyper_kggen/main.py"


def test_build_contract_explicit_entrypoint_outside_package_root_promoted():
    """If the plan declares entrypoint: main.py (relative), prefix it."""
    plan = (
        TREE_PLAN_WITH_PACKAGE_ROOT
        + "\nimplementation_strategy:\n  entrypoint: main.py\n"
    )
    contract = build_contract_from_plan(plan)
    assert contract.entrypoint == "hyper_kggen/main.py"


# ----- to_prompt_block -----
# Background: in paper_20260521-2350 the agent wrote to both src/ and
# hyper_kggen/src/ because nothing in the implementation prompt told it which
# layout to follow. to_prompt_block emits an authoritative layout block that
# the orchestrator prepends to the implement message.


def test_to_prompt_block_states_source_root_and_entrypoint():
    contract = ArtifactContract(
        project_root="src",
        entrypoint="src/main.py",
        package_name="hyper_kggen",
        smoke_commands=["python src/main.py --help"],
    )
    block = contract.to_prompt_block()
    assert "AUTHORITATIVE PROJECT LAYOUT" in block
    assert "src/" in block
    assert "src/main.py" in block


def test_to_prompt_block_forbids_parallel_source_trees():
    contract = ArtifactContract(project_root="src", entrypoint="src/main.py")
    block = contract.to_prompt_block()
    # The message must explicitly tell the agent not to create parallel trees.
    assert "parallel" in block.lower() or "do not create" in block.lower()


def test_to_prompt_block_mentions_package_name_when_present():
    contract = ArtifactContract(
        project_root="src",
        entrypoint="src/main.py",
        package_name="hyper_kggen",
    )
    block = contract.to_prompt_block()
    assert "hyper_kggen" in block


def test_to_prompt_block_omits_package_section_when_absent():
    contract = ArtifactContract(project_root="src", entrypoint="src/main.py")
    block = contract.to_prompt_block()
    # No leftover label like "Package:" without a value.
    assert "Package: None" not in block
    assert "Package name: None" not in block


def test_to_prompt_block_handles_flat_layout():
    """project_root="." case from the flat-main.py plan."""
    contract = ArtifactContract(project_root=".", entrypoint="main.py")
    block = contract.to_prompt_block()
    assert "main.py" in block
    # A "." root should not produce a weird "./" or "./" -only instruction.
    assert "parallel" in block.lower() or "do not create" in block.lower()


def test_to_prompt_block_nested_project_has_import_convention():
    """Run paper_09fffdd3: validate_paper_claims.py wrote `from src.lora` but
    the project lives at lora_implementation/src/lora.py. pytest ran from
    cwd=generate_code/ so the bare `src` was not on sys.path → ImportError.

    The prompt must tell the LLM which import shape to use, both inside the
    package (where {project_root}/ is sys.path[0]) and from the real root
    (where the project_root dir is importable as a package)."""
    contract = ArtifactContract(
        project_root="lora_implementation",
        entrypoint="lora_implementation/main.py",
        package_name="lora_implementation",
    )
    block = contract.to_prompt_block()
    # Mentions import convention.
    assert "import" in block.lower()
    # In-package import shape.
    assert "from src." in block
    # From-real-root import shape (validate_paper_claims.py, tests/).
    assert "from lora_implementation.src." in block


def test_to_prompt_block_flat_project_has_import_convention():
    """Flat project (no wrapper) uses top-level imports directly."""
    contract = ArtifactContract(project_root=".", entrypoint="main.py")
    block = contract.to_prompt_block()
    assert "import" in block.lower()


# ----- Plan A relaxation -----
# paper_ef4823cd (Run6) showed: plan tree has both `hyper_kggen/` and
# `hyper_kggen/src/`, contract picked project_root="hyper_kggen/src" +
# entrypoint="hyper_kggen/main.py" (regex-derived). Agent organized
# everything under `hyper_kggen/src/` and put main at `hyper_kggen/src/main.py`.
# We want the contract validator to accept that, since the package layout
# is internally coherent — only "multiple project roots" remains the real bug.


def test_validate_accepts_entrypoint_under_active_source_root(tmp_path):
    """Contract project_root=hyper_kggen; agent put main.py at hyper_kggen/src/main.py."""
    code_dir = tmp_path / "generate_code"
    (code_dir / "hyper_kggen" / "src").mkdir(parents=True)
    (code_dir / "hyper_kggen" / "src" / "main.py").write_text(
        "print('ok')\n", encoding="utf-8"
    )
    (code_dir / "hyper_kggen" / "src" / "other.py").write_text(
        "x = 1\n", encoding="utf-8"
    )

    result = validate_generated_tree_against_contract(
        str(code_dir),
        ArtifactContract(
            project_root="hyper_kggen",
            entrypoint="hyper_kggen/main.py",
            package_name="hyper_kggen",
            smoke_commands=["python hyper_kggen/main.py --help"],
        ),
    )

    assert result["status"] == "success", result["failures"]
    assert result["failures"] == []


def test_validate_accepts_sibling_subdir_under_same_package_root(tmp_path):
    """Run4 case: contract project_root=hyper_kggen; agent organized into
    hyper_kggen/core, hyper_kggen/skill, hyper_kggen/evaluation. As long as
    there's a single coherent package root, the layout is acceptable."""
    code_dir = tmp_path / "generate_code"
    (code_dir / "hyper_kggen" / "core").mkdir(parents=True)
    (code_dir / "hyper_kggen" / "core" / "model.py").write_text(
        "x = 1\n", encoding="utf-8"
    )
    (code_dir / "hyper_kggen" / "main.py").write_text(
        "print('main')\n", encoding="utf-8"
    )

    result = validate_generated_tree_against_contract(
        str(code_dir),
        ArtifactContract(
            project_root="hyper_kggen",
            entrypoint="hyper_kggen/main.py",
            package_name="hyper_kggen",
            smoke_commands=["python hyper_kggen/main.py --help"],
        ),
    )

    assert result["status"] == "success", result["failures"]


def test_validate_still_rejects_when_entrypoint_not_findable(tmp_path):
    """Relaxation has limits: if no main.py exists anywhere reasonable, fail."""
    code_dir = tmp_path / "generate_code"
    (code_dir / "hyper_kggen" / "src").mkdir(parents=True)
    (code_dir / "hyper_kggen" / "src" / "other.py").write_text(
        "x = 1\n", encoding="utf-8"
    )

    result = validate_generated_tree_against_contract(
        str(code_dir),
        ArtifactContract(
            project_root="hyper_kggen/src",
            entrypoint="hyper_kggen/main.py",
            package_name="hyper_kggen",
            smoke_commands=["python hyper_kggen/main.py --help"],
        ),
    )

    assert result["status"] == "error"
    assert any("entrypoint" in f for f in result["failures"])


def test_find_file_under_root_returns_exact_path(tmp_path):
    (tmp_path / "a" / "b").mkdir(parents=True)
    target = tmp_path / "a" / "b" / "main.py"
    target.write_text("x = 1\n", encoding="utf-8")
    assert find_file_under_root(tmp_path, "a/b/main.py") == target


def test_find_file_under_root_falls_back_to_basename(tmp_path):
    """Plan A: when exact path misses, search basename anywhere."""
    (tmp_path / "hyper_kggen" / "src").mkdir(parents=True)
    target = tmp_path / "hyper_kggen" / "src" / "main.py"
    target.write_text("x = 1\n", encoding="utf-8")
    # Contract said hyper_kggen/main.py; agent put it at hyper_kggen/src/main.py
    assert find_file_under_root(tmp_path, "hyper_kggen/main.py") == target


def test_find_file_under_root_returns_none_when_ambiguous(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "main.py").write_text("x=1\n", encoding="utf-8")
    (tmp_path / "b" / "main.py").write_text("x=1\n", encoding="utf-8")
    assert find_file_under_root(tmp_path, "main.py") is None


def test_find_file_under_root_returns_none_when_missing(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "other.py").write_text("x=1\n", encoding="utf-8")
    assert find_file_under_root(tmp_path, "main.py") is None


def test_find_file_under_root_skips_caches(tmp_path):
    """Don't latch onto .mypy_cache/__pycache__ artifacts."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "real.py").write_text("x=1\n", encoding="utf-8")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "real.py").write_text("stale\n", encoding="utf-8")
    found = find_file_under_root(tmp_path, "real.py")
    assert found == tmp_path / "src" / "real.py"


def test_validate_still_rejects_multiple_source_roots(tmp_path):
    """The one structural bug we genuinely care about — keep this strict."""
    code_dir = tmp_path / "generate_code"
    (code_dir / "src").mkdir(parents=True)
    (code_dir / "hyper_kggen" / "src").mkdir(parents=True)
    (code_dir / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (code_dir / "hyper_kggen" / "src" / "main.py").write_text(
        "print('bad')\n", encoding="utf-8"
    )

    result = validate_generated_tree_against_contract(
        str(code_dir),
        ArtifactContract(
            project_root="src",
            entrypoint="src/main.py",
            package_name="hyper_kggen",
            smoke_commands=["python src/main.py --help"],
        ),
    )

    assert result["status"] == "error"
    assert any("multiple project roots" in f for f in result["failures"])


def test_validate_generated_tree_ignores_root_validation_helpers(tmp_path):
    code_dir = tmp_path / "generate_code"
    (code_dir / "src").mkdir(parents=True)
    (code_dir / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (code_dir / "validate_paper_claims.py").write_text(
        "def test_claim():\n    assert True\n",
        encoding="utf-8",
    )
    (code_dir / "check_files.py").write_text("print('check')\n", encoding="utf-8")

    result = validate_generated_tree_against_contract(
        str(code_dir),
        ArtifactContract(
            project_root="src",
            entrypoint="src/main.py",
            package_name="hyper_kggen",
            smoke_commands=["python src/main.py --help"],
        ),
    )

    assert result["status"] == "success"
    assert result["project_roots"] == ["src"]


# ----- _top_level_py_roots helper (Task 2) -----


def test_top_level_py_roots_flat_layout(tmp_path):
    (tmp_path / "main.py").write_text("x=1\n", encoding="utf-8")
    (tmp_path / "utils.py").write_text("y=2\n", encoding="utf-8")
    assert _top_level_py_roots(tmp_path) == {"."}


def test_top_level_py_roots_single_package(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "main.py").write_text("x=1\n", encoding="utf-8")
    (tmp_path / "pkg" / "src").mkdir()
    (tmp_path / "pkg" / "src" / "lora.py").write_text("y=2\n", encoding="utf-8")
    assert _top_level_py_roots(tmp_path) == {"pkg"}


def test_top_level_py_roots_parallel_packages(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("a\n", encoding="utf-8")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "main.py").write_text("b\n", encoding="utf-8")
    assert _top_level_py_roots(tmp_path) == {"src", "pkg"}


def test_top_level_py_roots_excludes_tests_dir(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "x.py").write_text("a\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("a\n", encoding="utf-8")
    assert _top_level_py_roots(tmp_path) == {"pkg"}


def test_top_level_py_roots_excludes_docs_dir(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "x.py").write_text("a\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "build.py").write_text("a\n", encoding="utf-8")
    assert _top_level_py_roots(tmp_path) == {"pkg"}


def test_top_level_py_roots_excludes_caches(tmp_path):
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "stale.py").write_text("a\n", encoding="utf-8")
    (tmp_path / ".mypy_cache").mkdir()
    (tmp_path / ".mypy_cache" / "stale.py").write_text("a\n", encoding="utf-8")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "x.py").write_text("a\n", encoding="utf-8")
    assert _top_level_py_roots(tmp_path) == {"pkg"}


def test_top_level_py_roots_ignores_root_support_files(tmp_path):
    """validate_paper_claims.py and check_files.py at root are not project sources."""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "x.py").write_text("a\n", encoding="utf-8")
    (tmp_path / "validate_paper_claims.py").write_text("a\n", encoding="utf-8")
    (tmp_path / "check_files.py").write_text("a\n", encoding="utf-8")
    assert _top_level_py_roots(tmp_path) == {"pkg"}


def test_top_level_py_roots_mixed_root_and_package(tmp_path):
    """A top-level .py + a package dir = 2 roots."""
    (tmp_path / "main.py").write_text("a\n", encoding="utf-8")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "x.py").write_text("a\n", encoding="utf-8")
    assert _top_level_py_roots(tmp_path) == {".", "pkg"}


def test_top_level_py_roots_empty_directory(tmp_path):
    assert _top_level_py_roots(tmp_path) == set()


def test_top_level_py_roots_missing_directory(tmp_path):
    assert _top_level_py_roots(tmp_path / "does_not_exist") == set()


# ----- validate refactor (Task 3) -----


def test_validate_rejects_multiple_project_roots(tmp_path):
    code_dir = tmp_path / "generate_code"
    (code_dir / "src").mkdir(parents=True)
    (code_dir / "src" / "main.py").write_text("a\n", encoding="utf-8")
    (code_dir / "pkg").mkdir()
    (code_dir / "pkg" / "x.py").write_text("a\n", encoding="utf-8")

    result = validate_generated_tree_against_contract(
        str(code_dir),
        ArtifactContract(project_root="pkg", entrypoint="pkg/x.py"),
    )
    assert result["status"] == "error"
    assert any("multiple project roots" in f for f in result["failures"])


def test_validate_rejects_when_project_root_not_on_disk(tmp_path):
    code_dir = tmp_path / "generate_code"
    (code_dir / "other_pkg").mkdir(parents=True)
    (code_dir / "other_pkg" / "x.py").write_text("a\n", encoding="utf-8")

    result = validate_generated_tree_against_contract(
        str(code_dir),
        ArtifactContract(project_root="my_pkg", entrypoint="my_pkg/main.py"),
    )
    assert result["status"] == "error"
    assert any("project_root 'my_pkg' not found" in f for f in result["failures"])


def test_validate_passes_when_project_root_matches(tmp_path):
    code_dir = tmp_path / "generate_code"
    (code_dir / "pkg" / "src").mkdir(parents=True)
    (code_dir / "pkg" / "src" / "lora.py").write_text("def f(): pass\n", encoding="utf-8")
    (code_dir / "pkg" / "main.py").write_text("def f(): pass\n", encoding="utf-8")

    result = validate_generated_tree_against_contract(
        str(code_dir),
        ArtifactContract(project_root="pkg", entrypoint="pkg/main.py"),
    )
    assert result["status"] == "success", result["failures"]


def test_validate_passes_for_flat_layout(tmp_path):
    code_dir = tmp_path / "generate_code"
    code_dir.mkdir(parents=True)
    (code_dir / "main.py").write_text("def f(): pass\n", encoding="utf-8")
    (code_dir / "utils.py").write_text("def g(): pass\n", encoding="utf-8")

    result = validate_generated_tree_against_contract(
        str(code_dir),
        ArtifactContract(project_root=".", entrypoint="main.py"),
    )
    assert result["status"] == "success", result["failures"]


def test_validate_returns_project_roots_field(tmp_path):
    """Return field renamed from source_roots to project_roots."""
    code_dir = tmp_path / "generate_code"
    (code_dir / "pkg").mkdir(parents=True)
    (code_dir / "pkg" / "main.py").write_text("def f(): pass\n", encoding="utf-8")

    result = validate_generated_tree_against_contract(
        str(code_dir),
        ArtifactContract(project_root="pkg", entrypoint="pkg/main.py"),
    )
    assert "project_roots" in result
    assert result["project_roots"] == ["pkg"]
    assert "source_roots" not in result


# ----- build_contract refactor (Task 4) -----


def test_build_contract_sets_package_name_from_project_root():
    plan = """
file_structure: |
    lora_implementation/
    ├── main.py
    └── src/
        └── lora.py
"""
    contract = build_contract_from_plan(plan)
    assert contract.project_root == "lora_implementation"
    # package_name defaults to project_root when no explicit field
    assert contract.package_name == "lora_implementation"


def test_build_contract_sets_package_name_none_for_flat_project():
    plan = """
file_structure:
  - main.py
  - utils.py
"""
    contract = build_contract_from_plan(plan)
    assert contract.project_root == "."
    assert contract.package_name is None


def test_build_contract_normalizes_entrypoint_into_project_root():
    """When plan declares entrypoint: main.py but tree is pkg/, prefix it."""
    plan = """
file_structure: |
    pkg/
    ├── main.py
    └── src/
        └── lora.py
implementation_strategy:
  entrypoint: main.py
"""
    contract = build_contract_from_plan(plan)
    assert contract.project_root == "pkg"
    assert contract.entrypoint == "pkg/main.py"
