# Codegen Quality Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make generated paper reproduction code become measurably more runnable, not merely easier to mark as failed.

**Architecture:** Keep the existing multi-agent pipeline, but add a deterministic artifact contract before implementation, per-file acceptance during implementation, bounded repair loops after quality checks, and final smoke tests before a task can be marked successful. The design changes success from "the workflow coroutine returned" to "the agreed project contract, static quality checks, and smoke checks all passed."

**Tech Stack:** Python 3.13, pytest, existing Paper2Code workflow modules, static AST parsing, existing `CodeImplementationWorkflow`, existing `assess_generated_code_quality`.

---

## Why The Previous Design Failed

The previous design mixed together four different concepts:

- The agent wrote a file path.
- The planned file appeared in the generated directory.
- The implementation loop stopped.
- The task should be shown as successful.

Those are not equivalent. In the Hyper-KGGen run, the system created or wrote paths, but several implementation files were empty, two incompatible source roots existed, README commands pointed at missing files, and local imports referenced modules that were never implemented. The implementation report already said `status: incomplete` and `inner_status: max_iterations`, but the outer API path still treated coroutine completion as `done`.

The first fix already added a deterministic quality gate and corrected terminal status handling. This plan implements the next layer: use those failures as feedback to improve or repair the generated code during the same pipeline run.

## Before And After Design

| Area | Previous Design | Target Design |
|---|---|---|
| Project shape | Inferred loosely from plan and agent output | Explicit artifact contract with one source root, one entrypoint, package name, README command, validation command |
| File completion | A `write_file` call could count as progress | A file only counts after acceptance checks: non-empty implementation, parseable Python, path belongs to contract |
| Empty files | Detected late or missed | Rejected immediately for non-`__init__.py` implementation files |
| Duplicate roots | Could coexist (`src/` and `hyper_kggen/src`) | Contract validation rejects multiple active source roots before success |
| Missing imports | Found by validation or runtime failure | Static local import check becomes repair input |
| Repair behavior | No structured repair loop | Bounded repair loop converts quality failures into focused implementation prompts |
| Final status | Pipeline return could become `done` | `done` requires implementation complete, quality gate success, and smoke checks success |

## File Structure

- Create: `workflows/artifact_contract.py`
  - Owns `ArtifactContract`, contract extraction from plan text, generated tree inspection, and contract validation.
- Create: `workflows/code_acceptance.py`
  - Owns per-file acceptance checks for newly written files.
- Create: `workflows/repair_planner.py`
  - Converts quality gate and smoke test failures into bounded repair instructions.
- Create: `workflows/smoke_tests.py`
  - Runs deterministic smoke checks without requiring paper-scale experiments.
- Modify: `workflows/code_implementation_workflow.py`
  - Uses `code_acceptance` before counting a file as completed.
  - Stores rejected writes and rejection reasons.
- Modify: `workflows/agent_orchestration_engine.py`
  - Builds and validates artifact contract after planning.
  - Runs quality gate and repair loop after implementation.
  - Runs smoke tests before final success.
- Modify: `api/routes/tasks.py`
  - No major behavior change expected; add smoke status awareness if returned by pipeline.
- Test: `tests/test_artifact_contract.py`
- Test: `tests/test_code_acceptance.py`
- Test: `tests/test_repair_planner.py`
- Test: `tests/test_smoke_tests.py`
- Test: extend `tests/test_pipeline_critique_wiring.py`
- Test: extend `tests/test_api/test_routes_tasks.py`

---

## Task 1: Artifact Contract

**Files:**
- Create: `workflows/artifact_contract.py`
- Test: `tests/test_artifact_contract.py`

- [ ] **Step 1: Write failing tests**

```python
from workflows.artifact_contract import (
    ArtifactContract,
    build_contract_from_plan,
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

    assert contract.source_root == "src"
    assert contract.entrypoint == "src/main.py"
    assert contract.package_name == "hyper_kggen"
    assert contract.smoke_commands == ["python src/main.py --help"]


def test_validate_generated_tree_rejects_multiple_source_roots(tmp_path):
    code_dir = tmp_path / "generate_code"
    (code_dir / "src").mkdir(parents=True)
    (code_dir / "hyper_kggen" / "src").mkdir(parents=True)
    (code_dir / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (code_dir / "hyper_kggen" / "src" / "main.py").write_text("print('bad')\n", encoding="utf-8")

    result = validate_generated_tree_against_contract(
        str(code_dir),
        ArtifactContract(
            source_root="src",
            entrypoint="src/main.py",
            package_name="hyper_kggen",
            smoke_commands=["python src/main.py --help"],
        ),
    )

    assert result["status"] == "error"
    assert "multiple source roots" in result["failures"][0]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest tests/test_artifact_contract.py -q
```

Expected: import error for `workflows.artifact_contract`.

- [ ] **Step 3: Implement minimal contract module**

Create `workflows/artifact_contract.py` with:

```python
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ArtifactContract:
    source_root: str
    entrypoint: str
    package_name: str | None = None
    smoke_commands: list[str] = field(default_factory=list)


_PY_PATH_RE = re.compile(r"(?<![\\w/.-])([A-Za-z0-9_./-]+\\.py)\\b")
_SMOKE_RE = re.compile(r"smoke_command:\\s*(.+)")
_ENTRY_RE = re.compile(r"entrypoint:\\s*([A-Za-z0-9_./-]+\\.py)")
_PACKAGE_RE = re.compile(r"package_name:\\s*([A-Za-z_][A-Za-z0-9_]*)")


def _source_root_for(path: str) -> str | None:
    parts = Path(path).parts
    if not parts:
        return None
    if parts[0] == "src":
        return "src"
    if len(parts) >= 2 and parts[1] == "src":
        return f"{parts[0]}/src"
    return parts[0] if path.endswith(".py") else None


def build_contract_from_plan(plan_text: str) -> ArtifactContract:
    paths = sorted(set(_PY_PATH_RE.findall(plan_text or "")))
    roots = sorted({root for path in paths if (root := _source_root_for(path))})
    source_root = "src" if "src" in roots else (roots[0] if roots else "src")

    entry_match = _ENTRY_RE.search(plan_text or "")
    entrypoint = entry_match.group(1) if entry_match else f"{source_root}/main.py"

    package_match = _PACKAGE_RE.search(plan_text or "")
    package_name = package_match.group(1) if package_match else None

    smoke_commands = [
        match.group(1).strip()
        for match in _SMOKE_RE.finditer(plan_text or "")
        if match.group(1).strip()
    ]
    if not smoke_commands:
        smoke_commands = [f"python {entrypoint} --help"]

    return ArtifactContract(
        source_root=source_root,
        entrypoint=entrypoint,
        package_name=package_name,
        smoke_commands=smoke_commands,
    )


def _active_source_roots(root: Path) -> list[str]:
    roots: set[str] = set()
    if (root / "src").is_dir() and any((root / "src").rglob("*.py")):
        roots.add("src")
    for child in root.iterdir() if root.exists() else []:
        nested = child / "src"
        if child.is_dir() and nested.is_dir() and any(nested.rglob("*.py")):
            roots.add(f"{child.name}/src")
    return sorted(roots)


def validate_generated_tree_against_contract(
    code_directory: str,
    contract: ArtifactContract,
) -> dict[str, Any]:
    root = Path(code_directory)
    failures: list[str] = []
    active_roots = _active_source_roots(root)
    if len(active_roots) > 1:
        failures.append("multiple source roots: " + ", ".join(active_roots))
    if active_roots and contract.source_root not in active_roots:
        failures.append(f"expected source root {contract.source_root}, found {active_roots}")
    entrypoint_path = root / contract.entrypoint
    if not entrypoint_path.is_file():
        failures.append(f"missing entrypoint: {contract.entrypoint}")
    elif entrypoint_path.stat().st_size == 0:
        failures.append(f"empty entrypoint: {contract.entrypoint}")
    return {
        "status": "error" if failures else "success",
        "failures": failures,
        "source_roots": active_roots,
        "contract": {
            "source_root": contract.source_root,
            "entrypoint": contract.entrypoint,
            "package_name": contract.package_name,
            "smoke_commands": contract.smoke_commands,
        },
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
python -m pytest tests/test_artifact_contract.py -q
```

Expected: `2 passed`.

---

## Task 2: Per-File Acceptance

**Files:**
- Create: `workflows/code_acceptance.py`
- Modify: `workflows/code_implementation_workflow.py`
- Test: `tests/test_code_acceptance.py`

- [ ] **Step 1: Write failing tests**

```python
from workflows.artifact_contract import ArtifactContract
from workflows.code_acceptance import accept_written_file


def test_acceptance_rejects_empty_implementation_file(tmp_path):
    code_dir = tmp_path / "generate_code"
    path = code_dir / "src" / "main.py"
    path.parent.mkdir(parents=True)
    path.write_text("", encoding="utf-8")

    result = accept_written_file(
        str(code_dir),
        "src/main.py",
        ArtifactContract(source_root="src", entrypoint="src/main.py"),
    )

    assert result["accepted"] is False
    assert "empty implementation file" in result["reason"]


def test_acceptance_allows_empty_init_file(tmp_path):
    code_dir = tmp_path / "generate_code"
    path = code_dir / "src" / "__init__.py"
    path.parent.mkdir(parents=True)
    path.write_text("", encoding="utf-8")

    result = accept_written_file(
        str(code_dir),
        "src/__init__.py",
        ArtifactContract(source_root="src", entrypoint="src/main.py"),
    )

    assert result["accepted"] is True


def test_acceptance_rejects_python_syntax_error(tmp_path):
    code_dir = tmp_path / "generate_code"
    path = code_dir / "src" / "main.py"
    path.parent.mkdir(parents=True)
    path.write_text("def broken(:\n", encoding="utf-8")

    result = accept_written_file(
        str(code_dir),
        "src/main.py",
        ArtifactContract(source_root="src", entrypoint="src/main.py"),
    )

    assert result["accepted"] is False
    assert "syntax error" in result["reason"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_code_acceptance.py -q
```

Expected: import error for `workflows.code_acceptance`.

- [ ] **Step 3: Implement acceptance function**

Create `workflows/code_acceptance.py`:

```python
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from workflows.artifact_contract import ArtifactContract


def accept_written_file(
    code_directory: str,
    file_path: str,
    contract: ArtifactContract,
) -> dict[str, Any]:
    root = Path(code_directory).resolve()
    full_path = (root / file_path).resolve()
    try:
        full_path.relative_to(root)
    except ValueError:
        return {"accepted": False, "reason": "file path escapes code directory"}

    if not full_path.is_file():
        return {"accepted": False, "reason": "file does not exist"}

    rel = full_path.relative_to(root).as_posix()
    if rel.endswith(".py") and full_path.name != "__init__.py":
        if full_path.stat().st_size == 0:
            return {"accepted": False, "reason": "empty implementation file"}
        try:
            ast.parse(full_path.read_text(encoding="utf-8"), filename=rel)
        except SyntaxError as exc:
            return {"accepted": False, "reason": f"syntax error: {exc}"}

    if rel.endswith(".py") and not (
        rel == contract.entrypoint
        or rel.startswith(contract.source_root.rstrip("/") + "/")
        or rel.startswith("tests/")
        or rel.startswith("scripts/")
        or rel == "validate_paper_claims.py"
    ):
        return {
            "accepted": False,
            "reason": f"file is outside artifact contract source root: {rel}",
        }

    return {"accepted": True, "reason": "accepted"}
```

- [ ] **Step 4: Integrate acceptance into implementation progress**

Modify `workflows/code_implementation_workflow.py` in the `if tool_call["name"] == "write_file":` block. Replace direct progress completion with:

```python
acceptance = accept_written_file(
    code_directory,
    filename,
    artifact_contract,
)
if acceptance["accepted"]:
    completed_first_time = self.progress_tracker.complete_file(
        memory_agent.normalize_file_path(filename)
    )
else:
    self.logger.warning(
        "Rejected generated file %s: %s",
        filename,
        acceptance["reason"],
    )
    self.loop_detector.record_error(
        f"write_file rejected for {filename}: {acceptance['reason']}"
    )
    completed_first_time = False
```

Also add imports:

```python
from workflows.artifact_contract import ArtifactContract, build_contract_from_plan
from workflows.code_acceptance import accept_written_file
```

At the start of `implement_code_pure`, after `code_directory` is known:

```python
artifact_contract = build_contract_from_plan(plan_content)
```

- [ ] **Step 5: Run focused tests**

```bash
python -m pytest tests/test_code_acceptance.py -q
```

Expected: `3 passed`.

---

## Task 3: Quality Failure Repair Planner

**Files:**
- Create: `workflows/repair_planner.py`
- Modify: `workflows/agent_orchestration_engine.py`
- Test: `tests/test_repair_planner.py`

- [ ] **Step 1: Write failing tests**

```python
from workflows.repair_planner import build_repair_prompt


def test_repair_prompt_lists_empty_files_and_missing_imports():
    prompt = build_repair_prompt(
        {
            "status": "error",
            "empty_python_files": ["src/main.py"],
            "missing_local_imports": [
                {"file": "validate_paper_claims.py", "module": "src.skills.library"}
            ],
            "source_roots": ["hyper_kggen/src", "src"],
            "failures": ["Detected multiple source roots: hyper_kggen/src, src"],
        }
    )

    assert "src/main.py" in prompt
    assert "src.skills.library" in prompt
    assert "single source root" in prompt
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_repair_planner.py -q
```

Expected: import error for `workflows.repair_planner`.

- [ ] **Step 3: Implement repair prompt builder**

Create `workflows/repair_planner.py`:

```python
from __future__ import annotations

from typing import Any


def build_repair_prompt(quality_result: dict[str, Any]) -> str:
    empty_files = quality_result.get("empty_python_files", []) or []
    missing_imports = quality_result.get("missing_local_imports", []) or []
    source_roots = quality_result.get("source_roots", []) or []
    failures = quality_result.get("failures", []) or []

    lines = [
        "Repair the generated code so the deterministic quality gate passes.",
        "Rules:",
        "- Keep one single source root. Do not maintain duplicate src trees.",
        "- Implement empty Python files with real runnable code, not placeholders.",
        "- Add missing local modules or correct imports to existing modules.",
        "- Keep README commands aligned with actual files.",
        "",
        "Quality failures:",
    ]
    lines.extend(f"- {failure}" for failure in failures)
    if empty_files:
        lines.append("")
        lines.append("Empty Python implementation files to fill:")
        lines.extend(f"- {path}" for path in empty_files)
    if missing_imports:
        lines.append("")
        lines.append("Missing local imports to resolve:")
        lines.extend(
            f"- {item['file']} imports {item['module']}"
            for item in missing_imports
        )
    if len(source_roots) > 1:
        lines.append("")
        lines.append("Source root conflict:")
        lines.append(f"- Found {', '.join(source_roots)}; converge to a single source root.")
    return "\n".join(lines)
```

- [ ] **Step 4: Integrate bounded repair loop**

In `workflows/agent_orchestration_engine.py`, after the first `quality_result = assess_generated_code_quality(...)`, add a bounded loop:

```python
from workflows.repair_planner import build_repair_prompt
```

Then:

```python
repair_attempts: list[dict[str, Any]] = []
max_repair_attempts = 3
for repair_index in range(max_repair_attempts):
    if quality_result.get("status") == "success":
        break
    repair_prompt = build_repair_prompt(quality_result)
    repair_attempts.append(
        {
            "attempt": repair_index + 1,
            "prompt": repair_prompt,
            "quality_before": quality_result,
        }
    )
    repair_result = await synthesize_code_implementation_agent(
        dir_info,
        logger,
        progress_callback,
        enable_indexing,
        repair_prompt=repair_prompt,
    )
    quality_result = assess_generated_code_quality(
        repair_result.get("code_directory") or implementation_result.get("code_directory"),
        repair_result,
    )
```

If `synthesize_code_implementation_agent` does not yet accept `repair_prompt`, add the optional parameter and append it to the implementation message:

```python
async def synthesize_code_implementation_agent(
    dir_info: Dict[str, Any],
    logger,
    progress_callback: Optional[Callable[[int, str, Optional[str]], None]] = None,
    enable_indexing: bool = True,
    repair_prompt: str | None = None,
) -> Dict[str, Any]:
```

Inside the call to `code_workflow.run_workflow`, pass `repair_prompt=repair_prompt`. Add the same optional parameter to `CodeImplementationWorkflow.run_workflow` and `implement_code_pure`. When building the user implementation message, append:

```python
if repair_prompt:
    message += "\n\n# REQUIRED REPAIR PASS\n" + repair_prompt
```

- [ ] **Step 5: Run focused tests**

```bash
python -m pytest tests/test_repair_planner.py tests/test_pipeline_critique_wiring.py -q
```

Expected: all pass.

---

## Task 4: Smoke Tests

**Files:**
- Create: `workflows/smoke_tests.py`
- Modify: `workflows/agent_orchestration_engine.py`
- Test: `tests/test_smoke_tests.py`
- Test: extend `tests/test_api/test_routes_tasks.py`

- [ ] **Step 1: Write failing tests**

```python
from workflows.artifact_contract import ArtifactContract
from workflows.smoke_tests import run_smoke_checks


def test_smoke_checks_compile_python_project(tmp_path):
    code_dir = tmp_path / "generate_code"
    (code_dir / "src").mkdir(parents=True)
    (code_dir / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")

    result = run_smoke_checks(
        str(code_dir),
        ArtifactContract(
            source_root="src",
            entrypoint="src/main.py",
            smoke_commands=[],
        ),
        timeout_seconds=10,
    )

    assert result["status"] == "success"
    assert result["checks"][0]["name"] == "compileall"


def test_smoke_checks_fail_on_syntax_error(tmp_path):
    code_dir = tmp_path / "generate_code"
    (code_dir / "src").mkdir(parents=True)
    (code_dir / "src" / "main.py").write_text("def broken(:\n", encoding="utf-8")

    result = run_smoke_checks(
        str(code_dir),
        ArtifactContract(source_root="src", entrypoint="src/main.py"),
        timeout_seconds=10,
    )

    assert result["status"] == "error"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_smoke_tests.py -q
```

Expected: import error for `workflows.smoke_tests`.

- [ ] **Step 3: Implement smoke runner**

Create `workflows/smoke_tests.py`:

```python
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from workflows.artifact_contract import ArtifactContract


def _run_command(
    command: list[str],
    cwd: Path,
    timeout_seconds: int,
    name: str,
) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    return {
        "name": name,
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
        "status": "success" if completed.returncode == 0 else "error",
    }


def run_smoke_checks(
    code_directory: str,
    contract: ArtifactContract,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    root = Path(code_directory).resolve()
    checks: list[dict[str, Any]] = []
    checks.append(
        _run_command(
            ["python", "-m", "compileall", "-q", "."],
            root,
            timeout_seconds,
            "compileall",
        )
    )
    if checks[-1]["status"] == "success":
        for command in contract.smoke_commands:
            if command.strip():
                checks.append(
                    _run_command(
                        command.split(),
                        root,
                        timeout_seconds,
                        "contract_smoke_command",
                    )
                )
                if checks[-1]["status"] == "error":
                    break

    return {
        "status": "success" if all(check["status"] == "success" for check in checks) else "error",
        "checks": checks,
    }
```

- [ ] **Step 4: Integrate into pipeline finalization**

In `workflows/agent_orchestration_engine.py`, import:

```python
from workflows.artifact_contract import build_contract_from_plan
from workflows.smoke_tests import run_smoke_checks
```

After final quality result succeeds:

```python
artifact_contract = build_contract_from_plan(initial_plan_result)
smoke_result = run_smoke_checks(
    implementation_result.get("code_directory"),
    artifact_contract,
)
if smoke_result["status"] == "error":
    pipeline_status = "error"
    pipeline_summary += "\n❌ Smoke checks failed"
else:
    pipeline_summary += "\n✅ Smoke checks passed"
```

Include in return:

```python
"smoke": smoke_result,
```

- [ ] **Step 5: Extend API terminal state test**

Add to `tests/test_api/test_routes_tasks.py`:

```python
def test_pipeline_smoke_error_maps_to_error_terminal_state():
    from api.routes.tasks import _terminal_state_from_pipeline_result

    status, message = _terminal_state_from_pipeline_result(
        {
            "status": "completed",
            "summary": "Implementation completed but smoke failed",
            "implementation": {"status": "success", "inner_status": "completed"},
            "quality": {"status": "success"},
            "smoke": {"status": "error"},
            "validation": {"status": "success"},
        }
    )

    assert status == "error"
    assert "smoke" in message.lower()
```

Update `_terminal_state_from_pipeline_result` to read `smoke.status == "error"` as failed.

- [ ] **Step 6: Run focused tests**

```bash
python -m pytest tests/test_smoke_tests.py tests/test_api/test_routes_tasks.py -q
```

Expected: all pass.

---

## Task 5: Final Pipeline Status Contract

**Files:**
- Modify: `workflows/agent_orchestration_engine.py`
- Modify: `api/routes/tasks.py`
- Test: extend `tests/test_pipeline_critique_wiring.py`

- [ ] **Step 1: Write failing status aggregation test**

Add to `tests/test_pipeline_critique_wiring.py`:

```python
def test_pipeline_success_requires_implementation_quality_validation_and_smoke():
    from workflows.agent_orchestration_engine import _final_pipeline_status

    assert _final_pipeline_status(
        implementation={"status": "success", "inner_status": "completed"},
        quality={"status": "success"},
        validation={"status": "success"},
        smoke={"status": "success"},
    ) == "completed"
    assert _final_pipeline_status(
        implementation={"status": "success", "inner_status": "completed"},
        quality={"status": "error"},
        validation={"status": "success"},
        smoke={"status": "success"},
    ) == "error"
    assert _final_pipeline_status(
        implementation={"status": "incomplete", "inner_status": "max_iterations"},
        quality={"status": "success"},
        validation={"status": "success"},
        smoke={"status": "success"},
    ) == "incomplete"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_pipeline_critique_wiring.py::test_pipeline_success_requires_implementation_quality_validation_and_smoke -q
```

Expected: import error for `_final_pipeline_status`.

- [ ] **Step 3: Implement explicit status aggregation**

Add to `workflows/agent_orchestration_engine.py`:

```python
def _final_pipeline_status(
    *,
    implementation: Dict[str, Any],
    quality: Dict[str, Any],
    validation: Dict[str, Any],
    smoke: Dict[str, Any],
) -> str:
    impl_status = str(implementation.get("status", "")).lower()
    impl_inner = str(implementation.get("inner_status", "")).lower()
    if impl_status == "incomplete" or impl_inner in {
        "incomplete",
        "max_iterations",
        "max_time",
        "aborted",
    }:
        return "incomplete"
    if impl_status == "error" or impl_inner == "error":
        return "error"
    if str(quality.get("status", "")).lower() == "error":
        return "error"
    if str(smoke.get("status", "")).lower() == "error":
        return "error"
    if str(validation.get("status", "")).lower() in {"error", "partial", "failed"}:
        return "error"
    return "completed"
```

Use this helper once in finalization instead of scattered status mutations.

- [ ] **Step 4: Run focused tests**

```bash
python -m pytest tests/test_pipeline_critique_wiring.py -q
```

Expected: all pass.

---

## Task 6: Full Verification

**Files:**
- No new files.

- [ ] **Step 1: Run all tests**

```bash
python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Compile changed Python modules**

```bash
python -m compileall -q api workflows tests
```

Expected: exit code `0`.

- [ ] **Step 3: Re-check existing Hyper-KGGen output**

```bash
python -c "import json; from workflows.implementation_quality import assess_generated_code_quality; print(json.dumps(assess_generated_code_quality('/home/kps_spark/workspace/paper2code/output/tasks/paper_5aa256dd/generate_code'), ensure_ascii=False, indent=2)[:4000])"
```

Expected: status remains `error`, with empty files, duplicate roots, README mismatch, and missing local imports reported.

- [ ] **Step 4: Manual behavior check**

Run a small paper task or a mocked task with known generated files. Confirm:

- Empty implementation files do not count as completed.
- Quality failures produce repair prompts.
- After max repair attempts, remaining failures produce terminal `error`.
- API does not emit `done` unless implementation, quality, validation, and smoke statuses pass.

---

## Rollout Notes

This should be implemented in small commits:

1. Artifact contract.
2. Per-file acceptance.
3. Repair planner and repair loop.
4. Smoke tests.
5. Final status aggregation.

The highest-risk change is Task 2 because it changes implementation progress accounting. Keep the acceptance logic conservative: reject only deterministic failures, and do not reject legitimate empty `__init__.py` files.

## Self-Review

- Spec coverage: The plan covers old vs new design, root cause, artifact contract, per-file quality, repair loop, smoke testing, API terminal status, and verification.
- Placeholder scan: No TBD/TODO/fill-in steps are present. Every task has explicit files, tests, and commands.
- Type consistency: `ArtifactContract`, `assess_generated_code_quality`, `accept_written_file`, `build_repair_prompt`, `run_smoke_checks`, and `_final_pipeline_status` have stable names across tasks.
