# ArtifactContract → project_root Refactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `ArtifactContract.source_root` with `project_root` model, collapsing 7 commits of layered patches into one principle: "code must live under project_root".

**Architecture:** Single dataclass refactor + 3-file logic rewrite (`artifact_contract.py`, `code_acceptance.py`, downstream callers). Clean break — no alias. Mechanical test rename + new tests for the redefined invariants.

**Tech Stack:** Python 3.11+, `dataclasses`, `pathlib`, `yaml`, pytest.

**Spec:** `docs/superpowers/specs/2026-05-24-contract-project-root-refactor-design.md`

---

## File Structure

**Modify (no new files):**
- `workflows/artifact_contract.py` — field rename, validate rewrite, helper consolidation
- `workflows/code_acceptance.py` — accept + prune rules simplified
- `workflows/smoke_tests.py` — pure rename (1-2 lines text)
- `workflows/implementation_quality.py` — text/comment rename
- `workflows/repair_planner.py` — text rename
- `workflows/agent_orchestration_engine.py` — wire-up `_quality_with_*` field names
- `tests/test_artifact_contract.py` — mechanical rename + new tests
- `tests/test_code_acceptance.py` — mechanical rename + new tests
- `tests/test_smoke_tests.py` — mechanical rename
- `tests/test_reproduction_gate.py` — mechanical rename

**Delete (functions, not files):**
- `_source_root_consistent` (in artifact_contract.py)
- `_resolve_entrypoint` (in artifact_contract.py) — replaced by direct `find_file_under_root` call
- `_source_root_for` (in artifact_contract.py) — no remaining caller
- `_active_source_roots` (in artifact_contract.py) — replaced by `_top_level_py_roots`

---

### Task 1: Rename dataclass field `source_root` → `project_root`

**Files:**
- Modify: `workflows/artifact_contract.py:9-58` (dataclass + to_prompt_block)
- Modify: `tests/test_artifact_contract.py` — assertions + constructor args

- [ ] **Step 1: Write the failing test (new model assertion)**

Append to `tests/test_artifact_contract.py` (replace the now-failing line 27 expectation):

Find this test and update:
```python
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
```

(Rename the test too for clarity. The actual current test is named `test_build_contract_extracts_single_source_root_and_entrypoint` — keep the name for now; we rename later.)

- [ ] **Step 2: Run failing test**

Run: `pytest tests/test_artifact_contract.py::test_build_contract_extracts_single_source_root_and_entrypoint -v`
Expected: FAIL — `AttributeError: 'ArtifactContract' object has no attribute 'project_root'`

- [ ] **Step 3: Rewrite the dataclass**

Replace `workflows/artifact_contract.py` lines 9-58 with:
```python
@dataclass(frozen=True)
class ArtifactContract:
    project_root: str
    entrypoint: str
    package_name: str | None = None
    smoke_commands: list[str] = field(default_factory=list)

    def to_prompt_block(self) -> str:
        """Authoritative project-layout block injected into the implement prompt.

        Tells the agent exactly which project root and entrypoint it must
        use. code_acceptance enforces this server-side; this block makes
        the constraint visible to the model so it does not write parallel
        trees that get silently rejected.
        """
        root = self.project_root.rstrip("/") or "."
        if root == ".":
            project_line = (
                "Project root: . (flat layout — all implementation files "
                "live at the project root, no nested package directory)"
            )
            scope_rule = (
                "- All implementation files MUST live at the project root "
                "(no nested package directory)."
            )
        else:
            project_line = f"Project root: {root}/"
            scope_rule = f"- All implementation files MUST live under `{root}/`."

        lines = [
            "# AUTHORITATIVE PROJECT LAYOUT",
            "code_acceptance will reject any file written outside this layout.",
            "",
            project_line,
            f"Entrypoint: {self.entrypoint}",
        ]
        if self.package_name:
            lines.append(f"Package name: {self.package_name}")
        lines.extend(
            [
                "",
                "Rules:",
                scope_rule,
                "- Do not create parallel source trees "
                f"(e.g. `{root}/src/` alongside `src/`).",
                "- Tests go under `tests/`.",
                f"- The entrypoint file `{self.entrypoint}` MUST exist and be runnable.",
            ]
        )
        return "\n".join(lines)
```

- [ ] **Step 4: Update `build_contract_from_plan` return to use new field**

In `workflows/artifact_contract.py`, find the `return ArtifactContract(...)` call near line 283 and change `source_root=source_root` to `project_root=source_root` (variable name temporary; renamed in Task 4):
```python
    return ArtifactContract(
        project_root=source_root,
        entrypoint=entrypoint,
        package_name=package_name,
        smoke_commands=smoke_commands,
    )
```

- [ ] **Step 5: Update validate_generated_tree_against_contract's references**

In `workflows/artifact_contract.py` find the validate function (~line 425). Replace every `contract.source_root` with `contract.project_root` AND the JSON output key `"source_root"` with `"project_root"`. Concretely:

```python
def validate_generated_tree_against_contract(
    code_directory: str,
    contract: ArtifactContract,
) -> dict[str, Any]:
    root = Path(code_directory)
    failures: list[str] = []
    active_roots = _active_source_roots(root)

    if len(active_roots) > 1:
        failures.append("multiple source roots: " + ", ".join(active_roots))

    if not _source_root_consistent(contract.project_root, active_roots):
        failures.append(f"expected source root {contract.project_root}")

    entrypoint = _resolve_entrypoint(root, contract, active_roots)
    if entrypoint is None:
        failures.append(f"missing entrypoint: {contract.entrypoint}")
    elif not entrypoint.read_text(encoding="utf-8").strip():
        failures.append(f"empty entrypoint: {contract.entrypoint}")

    return {
        "status": "error" if failures else "success",
        "failures": failures,
        "source_roots": active_roots,
        "contract": {
            "project_root": contract.project_root,
            "entrypoint": contract.entrypoint,
            "package_name": contract.package_name,
            "smoke_commands": contract.smoke_commands,
        },
    }
```

(The text "multiple source roots" / "expected source root" / `"source_roots"` key will be renamed in Task 6 — leave for now to keep this task scope-tight.)

- [ ] **Step 6: Update other internal callers**

Two internal callers:

In `workflows/artifact_contract.py:26` (inside `to_prompt_block`): already done in Step 3.

In `workflows/code_acceptance.py:34` and `:102`: replace `contract.source_root` with `contract.project_root` (text-only rename — logic stays):
```python
# line 34 (inside accept_written_file)
    source_root = contract.project_root.rstrip("/")

# line 102 (inside prune_out_of_root_py_files)
    source_root = contract.project_root.rstrip("/")
```

- [ ] **Step 7: Update tests — mechanical replace of `source_root=` in constructor and `.source_root` in assertions**

Run:
```bash
python -c "
import re
from pathlib import Path
files = [
    'tests/test_artifact_contract.py',
    'tests/test_code_acceptance.py',
    'tests/test_smoke_tests.py',
    'tests/test_reproduction_gate.py',
]
for f in files:
    p = Path(f)
    text = p.read_text()
    # Constructor kwargs: source_root= → project_root=
    text = re.sub(r'\bsource_root=', 'project_root=', text)
    # Attribute access: .source_root → .project_root
    text = re.sub(r'\.source_root\b', '.project_root', text)
    p.write_text(text)
    print(f'updated {f}')
"
```

- [ ] **Step 8: Run all tests to verify pass**

Run: `pytest -m "not heavy" -q 2>&1 | tail -3`
Expected: 215 passed (or whatever current count) — same as before, just field renamed.

- [ ] **Step 9: Commit**

```bash
git add workflows/artifact_contract.py workflows/code_acceptance.py tests/test_artifact_contract.py tests/test_code_acceptance.py tests/test_smoke_tests.py tests/test_reproduction_gate.py
git commit -m "refactor: rename ArtifactContract.source_root to project_root

Mechanical rename + test updates. No logic change. Subsequent tasks
will simplify the validate/accept rules now that the field name
reflects the intended semantics (project_root, not source_root)."
```

---

### Task 2: Add `_top_level_py_roots` helper

**Files:**
- Modify: `workflows/artifact_contract.py` — add new helper
- Modify: `tests/test_artifact_contract.py` — add helper tests

- [ ] **Step 1: Write failing tests**

Append to `tests/test_artifact_contract.py`:
```python
from workflows.artifact_contract import _top_level_py_roots


def test_top_level_py_roots_flat_layout(tmp_path):
    (tmp_path / "main.py").write_text("x=1\n", encoding="utf-8")
    (tmp_path / "utils.py").write_text("y=2\n", encoding="utf-8")
    assert _top_level_py_roots(tmp_path) == {"."}


def test_top_level_py_roots_single_package(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "main.py").write_text("x=1\n", encoding="utf-8")
    (tmp_path / "pkg" / "src" / "lora.py").parent.mkdir(parents=True)
    (tmp_path / "pkg" / "src" / "lora.py").write_text("y=2\n", encoding="utf-8")
    # Coalesces nested subdirs under one package
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
```

- [ ] **Step 2: Run failing tests**

Run: `pytest tests/test_artifact_contract.py -v -k top_level_py_roots`
Expected: FAIL — `ImportError: cannot import name '_top_level_py_roots'`.

- [ ] **Step 3: Implement helper**

Add to `workflows/artifact_contract.py` near `_active_source_roots` (after the other private helpers). Use these constants from the existing file:
- `_ROOT_SUPPORT_PY_FILES` — already defined (~line 69)

Add new constant near `_NON_PACKAGE_ROOT_DIRS`:
```python
# Top-level directories that don't count as a "project root" for the
# multi-root invariant: tests/ and docs/ are conventionally outside the
# package boundary even though they can contain .py files.
_NON_PROJECT_TOP_DIRS = {"tests", "docs"}
```

Add the helper (place it just below `_NON_PROJECT_TOP_DIRS`):
```python
def _top_level_py_roots(root: Path) -> set[str]:
    """Return distinct top-level entries containing .py files.

    Used by validate_generated_tree_against_contract to detect the
    "multiple project roots" invariant. Excludes tests/, docs/, and
    cache directories; root-level helper files (validate_paper_claims.py,
    check_files.py) are not counted as a project source.
    """
    roots: set[str] = set()
    if not root.exists() or not root.is_dir():
        return roots

    # Top-level .py files contribute root "."
    if any(
        child.is_file()
        and child.suffix == ".py"
        and child.name not in _ROOT_SUPPORT_PY_FILES
        for child in root.iterdir()
    ):
        roots.add(".")

    for child in root.iterdir():
        if not child.is_dir() or child.name.startswith("."):
            continue
        if child.name in _NON_PROJECT_TOP_DIRS:
            continue
        if child.name in _PRUNE_SKIP_PARTS:  # __pycache__, etc
            continue
        if any(child.rglob("*.py")):
            roots.add(child.name)

    return roots
```

Note: `_PRUNE_SKIP_PARTS` lives in `workflows/code_acceptance.py`. To avoid importing it cross-module, define a local copy in artifact_contract.py:

```python
# Cache directories that never contain real project code
_CACHE_DIRS = {
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".git",
    ".venv",
    "venv",
}
```

And use `_CACHE_DIRS` instead of `_PRUNE_SKIP_PARTS`.

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_artifact_contract.py -v -k top_level_py_roots`
Expected: 10 PASSED.

- [ ] **Step 5: Commit**

```bash
git add workflows/artifact_contract.py tests/test_artifact_contract.py
git commit -m "feat: add _top_level_py_roots helper

Replaces _active_source_roots for the multi-root invariant. Excludes
tests/, docs/, caches, and root support files (validate_paper_claims.py,
check_files.py). Used by the upcoming validate refactor (Task 4)."
```

---

### Task 3: Rewrite `validate_generated_tree_against_contract` using new helper

**Files:**
- Modify: `workflows/artifact_contract.py:425-` (the validate function)
- Modify: `tests/test_artifact_contract.py` — new behavior tests

- [ ] **Step 1: Write failing tests for new behavior**

Append to `tests/test_artifact_contract.py`:
```python
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
```

- [ ] **Step 2: Run failing tests**

Run: `pytest tests/test_artifact_contract.py -v -k "rejects_multiple_project_roots or not_on_disk or passes_when_project_root_matches or passes_for_flat_layout or returns_project_roots_field"`
Expected: All 5 FAIL (different reasons — old logic still in place).

- [ ] **Step 3: Rewrite validate_generated_tree_against_contract**

Replace the entire function (~lines 425-460) with:
```python
def validate_generated_tree_against_contract(
    code_directory: str,
    contract: ArtifactContract,
) -> dict[str, Any]:
    root = Path(code_directory)
    failures: list[str] = []
    project_roots = _top_level_py_roots(root)

    if len(project_roots) > 1:
        failures.append(
            f"multiple project roots: {sorted(project_roots)}"
        )

    pr = contract.project_root.rstrip("/")
    if pr == ".":
        if "." not in project_roots and project_roots:
            failures.append(
                f"contract project_root '.' but disk has: {sorted(project_roots)}"
            )
    elif pr not in project_roots:
        failures.append(
            f"contract project_root '{pr}' not found on disk; "
            f"have: {sorted(project_roots)}"
        )

    entrypoint = find_file_under_root(root, contract.entrypoint)
    if entrypoint is None:
        failures.append(f"missing entrypoint: {contract.entrypoint}")
    elif not entrypoint.read_text(encoding="utf-8").strip():
        failures.append(f"empty entrypoint: {contract.entrypoint}")

    return {
        "status": "error" if failures else "success",
        "failures": failures,
        "project_roots": sorted(project_roots),
        "contract": {
            "project_root": contract.project_root,
            "entrypoint": contract.entrypoint,
            "package_name": contract.package_name,
            "smoke_commands": contract.smoke_commands,
        },
    }
```

Note: this removes the now-unused `_source_root_consistent` and `_resolve_entrypoint` calls. Leave the functions defined for now (delete in Task 5).

- [ ] **Step 4: Update existing tests for the renamed `source_roots` field**

Run:
```bash
python -c "
import re
from pathlib import Path
p = Path('tests/test_artifact_contract.py')
text = p.read_text()
text = re.sub(r'result\[\"source_roots\"\]', 'result[\"project_roots\"]', text)
text = re.sub(r\"'source_roots'\", \"'project_roots'\", text)
p.write_text(text)
print('updated')
"
```

Also update tests with old failure messages — these assertions need updating:
- `assert 'expected source root` → `assert 'contract project_root` or `assert 'not found on disk'`
- `assert "multiple source roots"` → `assert "multiple project roots"`

For mechanical text updates:
```bash
python -c "
import re
from pathlib import Path
p = Path('tests/test_artifact_contract.py')
text = p.read_text()
text = text.replace('multiple source roots', 'multiple project roots')
text = text.replace('expected source root', \"contract project_root\")
p.write_text(text)
"
```

- [ ] **Step 5: Run all artifact_contract tests**

Run: `pytest tests/test_artifact_contract.py -v 2>&1 | tail -15`
Expected: All PASS (existing + 5 new from Step 1).

- [ ] **Step 6: Commit**

```bash
git add workflows/artifact_contract.py tests/test_artifact_contract.py
git commit -m "refactor: rewrite validate_generated_tree_against_contract using project_root

Uses _top_level_py_roots for the multi-root check. Removes the
ancestor/descendant fuzzy matching (_source_root_consistent) — no
longer needed when contract describes a single project root.
find_file_under_root replaces _resolve_entrypoint inline.

Renames failure messages: 'multiple source roots' → 'multiple project
roots', 'expected source root' → 'contract project_root not found'.
Renames result key 'source_roots' → 'project_roots'."
```

---

### Task 4: Simplify `build_contract_from_plan`

**Files:**
- Modify: `workflows/artifact_contract.py:174-288` (the build function)
- Modify: `tests/test_artifact_contract.py` — add normalization + default tests

- [ ] **Step 1: Write failing tests**

Append to `tests/test_artifact_contract.py`:
```python
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


def test_build_contract_explicit_package_name_wins():
    """Explicit package_name in plan overrides the project_root default."""
    plan = """
file_structure: |
    pkg/
    └── main.py
environment_setup:
  package_name: explicit_pkg
"""
    contract = build_contract_from_plan(plan)
    assert contract.project_root == "pkg"
    assert contract.package_name == "explicit_pkg"
```

- [ ] **Step 2: Run failing tests**

Run: `pytest tests/test_artifact_contract.py -v -k "sets_package_name or normalizes_entrypoint_into_project_root"`
Expected: Some FAIL (current logic doesn't default package_name to project_root cleanly).

- [ ] **Step 3: Rewrite build_contract_from_plan**

Replace the function (lines 174-288) with:
```python
def build_contract_from_plan(plan_text: str) -> ArtifactContract:
    text = plan_text or ""
    paths = sorted(set(_PY_PATH_RE.findall(text)))

    # ① project_root from plan tree (YAML-aware via _detect_source_layout)
    package_root, _ = _detect_source_layout(text)
    project_root = package_root if package_root else "."

    # ② package_name: explicit → project_root → None
    package_match = _PACKAGE_RE.search(text)
    if package_match:
        package_name = package_match.group(1)
    elif project_root != ".":
        package_name = project_root
    else:
        package_name = None

    # ③ entrypoint: explicit → main.py / run_*.py from tree → default
    entry_match = _ENTRY_RE.search(text)
    if entry_match:
        entrypoint = entry_match.group(1)
    else:
        guessed = _guess_entrypoint_from_paths(paths)
        entrypoint = guessed if guessed else "main.py"

    # ④ Normalize entrypoint into project_root
    if project_root != "." and not entrypoint.startswith(project_root + "/"):
        entrypoint = f"{project_root}/{entrypoint.lstrip('./')}"

    # ⑤ smoke commands: explicit → derive from entrypoint
    smoke_commands = []
    for match in _SMOKE_RE.finditer(text):
        command = match.group(1).strip()
        if command and not is_blocked_smoke_command(command):
            smoke_commands.append(command)
    if not smoke_commands:
        smoke_commands = [f"python {entrypoint} --help"]

    return ArtifactContract(
        project_root=project_root,
        entrypoint=entrypoint,
        package_name=package_name,
        smoke_commands=smoke_commands,
    )
```

- [ ] **Step 4: Run all artifact_contract tests**

Run: `pytest tests/test_artifact_contract.py -v 2>&1 | tail -15`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add workflows/artifact_contract.py tests/test_artifact_contract.py
git commit -m "refactor: simplify build_contract_from_plan using project_root model

Removes the source_subdir branch logic (no longer needed).
Normalizes entrypoint into project_root.
package_name defaults to project_root when no explicit field."
```

---

### Task 5: Delete dead helpers

**Files:**
- Modify: `workflows/artifact_contract.py` — remove unused functions

- [ ] **Step 1: Verify functions have no callers**

Run:
```bash
grep -n "_source_root_consistent\|_resolve_entrypoint\|_source_root_for\|_active_source_roots" workflows/ tests/ -r 2>/dev/null | grep -v "__pycache__"
```
Expected: only definitions, no calls.

- [ ] **Step 2: Delete the four functions**

In `workflows/artifact_contract.py`, remove the entire bodies of:
1. `_source_root_consistent` (~lines 327-358)
2. `_resolve_entrypoint` (~lines 360-401)
3. `_source_root_for` (~lines 156-170 — single 15-line function)
4. `_active_source_roots` (~lines 291-325)

Also remove the now-unused regex `_NON_PACKAGE_ROOT_DIRS` if it's not used elsewhere (the new `_NON_PROJECT_TOP_DIRS` replaces its role).

- [ ] **Step 3: Run full test suite**

Run: `pytest -m "not heavy" -q 2>&1 | tail -3`
Expected: 220+ passed.

- [ ] **Step 4: Commit**

```bash
git add workflows/artifact_contract.py
git commit -m "refactor: delete dead helpers after project_root refactor

Removes:
- _source_root_consistent (ancestor/descendant fuzzy matching)
- _resolve_entrypoint (replaced by find_file_under_root inline)
- _source_root_for (no remaining caller)
- _active_source_roots (replaced by _top_level_py_roots)

Net: -120 lines of code."
```

---

### Task 6: Simplify `accept_written_file` rules

**Files:**
- Modify: `workflows/code_acceptance.py:34-62` (the accept function's source-root check)
- Modify: `tests/test_code_acceptance.py` — add new tests, remove scripts/ test

- [ ] **Step 1: Write failing tests**

Append to `tests/test_code_acceptance.py`:
```python
def test_acceptance_rejects_scripts_dir_now_that_allowlist_dropped(tmp_path):
    """scripts/ allowlist removed. agent must put scripts inside project_root."""
    code_dir = tmp_path / "generate_code"
    path = code_dir / "scripts" / "launch.py"
    path.parent.mkdir(parents=True)
    path.write_text("print('launch')\n", encoding="utf-8")

    result = accept_written_file(
        str(code_dir),
        "scripts/launch.py",
        ArtifactContract(project_root="pkg", entrypoint="pkg/main.py"),
    )
    assert result["accepted"] is False
    assert "outside" in result["reason"] or "project" in result["reason"]
    # And unlinked
    assert not path.exists()


def test_acceptance_accepts_entrypoint_inside_project_root(tmp_path):
    """No longer needs special-case `rel == contract.entrypoint`."""
    code_dir = tmp_path / "generate_code"
    path = code_dir / "pkg" / "main.py"
    path.parent.mkdir(parents=True)
    path.write_text("def main(): pass\n", encoding="utf-8")

    result = accept_written_file(
        str(code_dir),
        "pkg/main.py",
        ArtifactContract(project_root="pkg", entrypoint="pkg/main.py"),
    )
    assert result["accepted"] is True


def test_acceptance_accepts_validate_paper_claims_at_root(tmp_path):
    """Explicit allowlist for the paper2code-specific validation script."""
    code_dir = tmp_path / "generate_code"
    code_dir.mkdir()
    (code_dir / "validate_paper_claims.py").write_text(
        "def test(): pass\n", encoding="utf-8"
    )

    result = accept_written_file(
        str(code_dir),
        "validate_paper_claims.py",
        ArtifactContract(project_root="pkg", entrypoint="pkg/main.py"),
    )
    assert result["accepted"] is True
```

- [ ] **Step 2: Find and update the existing test for `scripts/`**

In `tests/test_code_acceptance.py`, find any test that asserts scripts/ is allowed. If found, either delete it or invert its assertion. (Likely the existing tests don't have explicit `scripts/` assertions — verify with grep.)

Run:
```bash
grep -n 'scripts/' tests/test_code_acceptance.py
```

If no match: nothing to change. If matches exist, update them to expect rejection.

- [ ] **Step 3: Run failing tests**

Run: `pytest tests/test_code_acceptance.py -v -k "rejects_scripts_dir or accepts_entrypoint_inside or accepts_validate_paper_claims"`
Expected: PASS the validate_paper_claims and entrypoint_inside tests; FAIL the rejects_scripts test (old logic still allows scripts/).

- [ ] **Step 4: Rewrite the source-root block in accept_written_file**

In `workflows/code_acceptance.py`, replace the block (~lines 34-63) with:
```python
    pr = contract.project_root.rstrip("/")
    in_project = pr == "." or rel.startswith(pr + "/")
    allowed = (
        in_project
        or rel.startswith("tests/")
        or rel == "validate_paper_claims.py"
    )
    if rel.endswith(".py") and not allowed:
        try:
            full_path.unlink()
        except OSError:
            pass
        return {
            "accepted": False,
            "reason": f"file outside project root: {rel}",
        }

    return {"accepted": True, "reason": "accepted"}
```

- [ ] **Step 5: Run all acceptance tests**

Run: `pytest tests/test_code_acceptance.py -v 2>&1 | tail -15`
Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add workflows/code_acceptance.py tests/test_code_acceptance.py
git commit -m "refactor: simplify accept_written_file using project_root rule

One rule replaces 5: in_project (or tests/ or validate_paper_claims.py).
Removes:
- within_source_root (now identical to in_project)
- within_package_root (no longer needed; in_project covers it)
- entrypoint == rel exception (entrypoint must be in project_root)
- scripts/ exception (no evidence of use; agent puts launch scripts
  under project_root if needed)"
```

---

### Task 7: Simplify `prune_out_of_root_py_files`

**Files:**
- Modify: `workflows/code_acceptance.py:90-145` (prune function)
- Modify: `tests/test_code_acceptance.py` — keep existing prune tests, drop scripts/ allowlist test

- [ ] **Step 1: Update the keeps-allowlist test**

In `tests/test_code_acceptance.py`, find `test_prune_keeps_allowlisted_paths`. Remove the `scripts/` portion:
```python
def test_prune_keeps_allowlisted_paths(tmp_path):
    """tests/, validate_paper_claims.py, entrypoint should survive."""
    from workflows.code_acceptance import prune_out_of_root_py_files

    code_dir = tmp_path / "generate_code"
    (code_dir / "src").mkdir(parents=True)
    (code_dir / "src" / "main.py").write_text("x=1\n", encoding="utf-8")
    (code_dir / "tests").mkdir()
    (code_dir / "tests" / "test_x.py").write_text(
        "def test(): pass\n", encoding="utf-8"
    )
    (code_dir / "validate_paper_claims.py").write_text(
        "print(1)\n", encoding="utf-8"
    )

    contract = ArtifactContract(project_root="src", entrypoint="src/main.py")
    result = prune_out_of_root_py_files(str(code_dir), contract)

    assert (code_dir / "src" / "main.py").exists()
    assert (code_dir / "tests" / "test_x.py").exists()
    assert (code_dir / "validate_paper_claims.py").exists()
    assert result["pruned"] == []
```

Add new test:
```python
def test_prune_removes_scripts_dir_now_that_allowlist_dropped(tmp_path):
    """scripts/ allowlist dropped: scripts/*.py at root is pruned."""
    from workflows.code_acceptance import prune_out_of_root_py_files

    code_dir = tmp_path / "generate_code"
    (code_dir / "src").mkdir(parents=True)
    (code_dir / "src" / "main.py").write_text("x=1\n", encoding="utf-8")
    (code_dir / "scripts").mkdir()
    (code_dir / "scripts" / "launch.py").write_text("print(1)\n", encoding="utf-8")

    contract = ArtifactContract(project_root="src", entrypoint="src/main.py")
    result = prune_out_of_root_py_files(str(code_dir), contract)

    assert (code_dir / "src" / "main.py").exists()
    assert not (code_dir / "scripts" / "launch.py").exists()
    assert "scripts/launch.py" in result["pruned"]
```

- [ ] **Step 2: Run failing tests**

Run: `pytest tests/test_code_acceptance.py -v -k "removes_scripts_dir_now_that_allowlist_dropped or keeps_allowlisted_paths"`
Expected: removes_scripts test FAIL; keeps_allowlisted PASS (already correct).

- [ ] **Step 3: Rewrite prune logic**

In `workflows/code_acceptance.py`, replace the prune function (~lines 90-145) with:
```python
def prune_out_of_root_py_files(
    code_directory: str,
    contract: ArtifactContract,
) -> dict[str, Any]:
    """End-of-implementation sweep: remove .py files outside the contract
    project root that survived because the agent re-wrote them after the
    last acceptance check.

    Applies the same allowlist as accept_written_file: in_project,
    tests/, validate_paper_claims.py. __init__.py is always kept. Caches
    are skipped.

    Returns ``{"pruned": [list of relative paths removed]}``.
    """
    root = Path(code_directory).resolve()
    if not root.exists() or not root.is_dir():
        return {"pruned": []}

    pr = contract.project_root.rstrip("/")
    pruned: list[str] = []

    for py_file in root.rglob("*.py"):
        if any(part in _PRUNE_SKIP_PARTS for part in py_file.parts):
            continue
        if not py_file.is_file():
            continue
        rel = py_file.relative_to(root).as_posix()

        in_project = pr == "." or rel.startswith(pr + "/")
        allowed = (
            in_project
            or rel.startswith("tests/")
            or rel == "validate_paper_claims.py"
            or py_file.name == "__init__.py"
        )
        if allowed:
            continue
        try:
            py_file.unlink()
            pruned.append(rel)
        except OSError:
            pass

    return {"pruned": sorted(pruned)}
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_code_acceptance.py -v 2>&1 | tail -10`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add workflows/code_acceptance.py tests/test_code_acceptance.py
git commit -m "refactor: simplify prune_out_of_root_py_files to mirror accept rule

Same in_project / tests / validate_paper_claims allowlist as
accept_written_file. scripts/ dropped. within_package_root derivation
removed."
```

---

### Task 8: Downstream text + field rename

**Files:**
- Modify: `workflows/repair_planner.py` — "source root" → "project root"
- Modify: `workflows/smoke_tests.py` — any text references
- Modify: `workflows/implementation_quality.py` — any text references
- Modify: `workflows/agent_orchestration_engine.py` — wire-up field names

- [ ] **Step 1: Grep remaining references**

Run:
```bash
grep -rn "source_root\|source root" workflows/ --include="*.py" | grep -v "__pycache__"
```
List everything that comes back.

- [ ] **Step 2: Update repair_planner.py**

Find lines containing `"Source root conflict"` or `"single source root"` and replace `source root` → `project root`. Use Edit tool per occurrence (this file is small).

- [ ] **Step 3: Update smoke_tests.py**

The file imports `ArtifactContract` and reads `contract.smoke_commands` (no `.source_root` access). Only text references in comments/docstrings need updating:

```bash
grep -n "source_root\|source root" workflows/smoke_tests.py
```
For each match, update to project_root / project root.

- [ ] **Step 4: Update implementation_quality.py**

Has its own `_detect_source_roots` function (independent of artifact_contract's). Keep behavior but rename if you want consistency:

```bash
grep -n "source_root\|source root\|_detect_source_roots" workflows/implementation_quality.py
```
For text consistency: failure message `"Detected multiple source roots"` → `"Detected multiple project roots"`. The internal function name can stay or be renamed (low priority).

- [ ] **Step 5: Update agent_orchestration_engine.py wire-up**

Find any reference reading from `quality_result["source_roots"]` and rename to `quality_result["project_roots"]`. Check:
```bash
grep -n "source_root\|source root" workflows/agent_orchestration_engine.py
```
Update found occurrences.

- [ ] **Step 6: Run full test suite**

Run: `pytest -m "not heavy" -q 2>&1 | tail -3`
Expected: 220+ PASSED.

- [ ] **Step 7: Final grep — should be 0 remaining production references**

Run:
```bash
grep -rn "source_root\|source root" workflows/ tools/ api/ --include="*.py" | grep -v "__pycache__"
```
Expected: 0 results (or only comments noting "previously source_root").

- [ ] **Step 8: Commit**

```bash
git add workflows/repair_planner.py workflows/smoke_tests.py workflows/implementation_quality.py workflows/agent_orchestration_engine.py
git commit -m "refactor: rename remaining source_root references to project_root

Pure text/field rename across downstream callers."
```

---

### Task 9: Verify against real plan data

**Files:**
- No code changes; verification only.

- [ ] **Step 1: Test build_contract_from_plan against past plans**

Run:
```bash
python -c "
from workflows.artifact_contract import build_contract_from_plan
plans = [
    ('LoRA Run19', 'output/tasks/paper_49ecc53b/initial_plan.txt'),
    ('hyper_kggen Run16', 'output/tasks/paper_4c51bf57/initial_plan.txt'),
    ('hyper_kggen Run8', 'output/tasks/paper_04e6e1cf/initial_plan.txt'),
]
for label, path in plans:
    try:
        with open(path) as f:
            plan = f.read()
        c = build_contract_from_plan(plan)
        print(f'{label}: project_root={c.project_root!r} entrypoint={c.entrypoint!r}')
    except FileNotFoundError:
        print(f'{label}: file not found')
"
```
Expected: LoRA → project_root='lora_implementation' or 'lora_reproduction'; hyper_kggen → project_root='hyper_kggen'. Each entrypoint should be a path inside the project root.

- [ ] **Step 2: Test validate against past outputs**

Run:
```bash
python -c "
from workflows.artifact_contract import build_contract_from_plan, validate_generated_tree_against_contract
import os
for d in ['paper_49ecc53b', 'paper_4c51bf57']:
    code_dir = f'output/tasks/{d}/generate_code'
    if not os.path.isdir(code_dir): continue
    with open(f'output/tasks/{d}/initial_plan.txt') as f:
        c = build_contract_from_plan(f.read())
    r = validate_generated_tree_against_contract(code_dir, c)
    print(f'{d}: status={r[\"status\"]} project_roots={r[\"project_roots\"]}')
    for fail in r['failures']:
        print(f'  - {fail}')
"
```
Expected: status may still be error (because real outputs had multi-root from prior runs) — but failures should now use the "multiple project roots" / "project_root not found" wording.

- [ ] **Step 3: Document baseline for next run**

Log the numbers observed in steps 1-2.

- [ ] **Step 4: Tag end of refactor (no commit needed)**

```bash
git log --oneline -10
```
Expected: 8-9 refactor commits, named clearly.

---

## Spec coverage check (self-review)

| Spec section | Implemented by |
|---|---|
| Data model: `project_root` field, clean break | Task 1 |
| `to_prompt_block` text update | Task 1 |
| `accept_written_file` new rule (in_project + tests/ + validate_paper_claims.py, drop scripts/) | Task 6 |
| `prune_out_of_root_py_files` mirroring accept rule | Task 7 |
| `validate_generated_tree_against_contract` new rule (multiple project roots, project_root on disk) | Task 3 |
| `_top_level_py_roots` helper with `_NON_PROJECT_TOP_DIRS` | Task 2 |
| `build_contract_from_plan` simplification + entrypoint normalization | Task 4 |
| Delete `_source_root_consistent`, `_resolve_entrypoint`, `_source_root_for`, `_active_source_roots` | Task 5 |
| Smoke / repair_planner / impl_quality / orchestrator text rename | Task 8 |
| Verify against real plans | Task 9 |

All spec sections covered.

## Type consistency check

- Field name: always `project_root` (Tasks 1, 3, 4, 6, 7) ✓
- Result key: always `project_roots` plural in validate result (Task 3) ✓
- Constant: `_NON_PROJECT_TOP_DIRS` defined in Task 2 and referenced in Task 2; `_CACHE_DIRS` defined and used in Task 2 ✓
- Function name `_top_level_py_roots` consistent across Tasks 2, 3 ✓
- `find_file_under_root` already exists in `workflows/artifact_contract.py` (added earlier) and is reused in Task 3 ✓

## Placeholder check

No TBD/TODO/"fill in"/"similar to" markers. Each step has concrete code or commands.
