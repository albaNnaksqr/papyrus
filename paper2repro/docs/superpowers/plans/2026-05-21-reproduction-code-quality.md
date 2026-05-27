# Reproduction Code Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve first-pass generated paper reproduction code so it is runnable, claim-oriented, and harder to pass as a toy scaffold.

**Architecture:** Keep the existing Paper2Code workflow and add a reproduction-quality layer around code generation. The layer derives a paper-specific claim contract, injects it into implementation prompts, runs lightweight bounded gates during and after generation, and turns failures into focused repair prompts without running heavy full-suite tests by default.

**Tech Stack:** Python 3.13, pytest, AST parsing, subprocess with timeouts, existing `workflows/*` modules, existing implementation and repair agents.

---

## Problem Statement

The Hyper-KGGen generated output showed the current quality boundary is too weak:

- The implementation advertised paper concepts but produced a toy scaffold.
- The CLI failed immediately due to `ModuleNotFoundError`.
- The generated chunking logic could hang on short documents.
- The validation file expected paper-core APIs that were missing.
- README commands and actual CLI flags diverged.
- The plan listed many paper modules, but implementation collapsed them into one partial `pipeline.py`.

The target state is not "every first pass fully reproduces every paper." The target state is:

- First-pass output has a runnable entrypoint.
- Core paper claims are represented as executable contract requirements.
- Toy placeholder implementations are rejected early.
- Failures are cheap, bounded, and specific enough for repair.
- Heavy integration checks are opt-in and do not overload a live backend.

## File Structure

- Create: `workflows/claim_contract.py`
  - Owns paper-specific reproduction claims, required symbols, required modules, and minimal demo expectations.
- Create: `workflows/generated_project_lint.py`
  - Owns deterministic anti-scaffold checks for generated projects.
- Create: `workflows/reproduction_gate.py`
  - Owns bounded compile, CLI, minimal demo, and generated validation checks.
- Modify: `workflows/repair_planner.py`
  - Includes claim-contract, anti-scaffold, and bounded gate failures in repair prompts.
- Modify: `workflows/code_implementation_workflow.py`
  - Injects claim contract and anti-scaffold rules into first-pass implementation.
- Modify: `workflows/code_implementation_workflow_index.py`
  - Mirrors the same prompt injection for indexed implementation.
- Modify: `workflows/agent_orchestration_engine.py`
  - Builds the claim contract after planning, runs the reproduction gate after implementation and repair, and avoids full heavy tests by default.
- Modify: `workflows/agents/validation_agent.py`
  - Runs generated claim tests with timeout and environment variables that disable pytest plugin autoload.
- Test: `tests/test_claim_contract.py`
- Test: `tests/test_generated_project_lint.py`
- Test: `tests/test_reproduction_gate.py`
- Test: extend `tests/test_repair_planner.py`
- Test: extend `tests/test_pipeline_critique_wiring.py`

---

## Task 1: Paper Claim Contract

**Files:**
- Create: `workflows/claim_contract.py`
- Test: `tests/test_claim_contract.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_claim_contract.py`:

```python
from workflows.claim_contract import build_claim_contract


def test_claim_contract_extracts_required_symbols_from_plan():
    plan = """
implementation_components:
  - stability-based reward signal: implement compute_stability_signal
  - parallel rollout: implement sample_with_temperature
  - skill library retrieval: implement retrieve_skills and merge_skills
validation_approach:
  required_api:
    - compute_stability_signal
    - sample_with_temperature
    - retrieve_skills
    - merge_skills
"""

    contract = build_claim_contract(plan_text=plan, critique_text="")

    assert contract.required_symbols == [
        "compute_stability_signal",
        "merge_skills",
        "retrieve_skills",
        "sample_with_temperature",
    ]
    assert any("stability" in claim.description.lower() for claim in contract.claims)
    assert any("rollout" in claim.description.lower() for claim in contract.claims)


def test_claim_contract_is_json_serializable():
    contract = build_claim_contract(
        plan_text="implementation_components:\n  - inference pipeline: implement run_inference\n",
        critique_text="risk: dataset unavailable",
    )

    payload = contract.to_dict()

    assert payload["required_symbols"] == ["run_inference"]
    assert payload["limitations"] == ["dataset unavailable"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_claim_contract.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'workflows.claim_contract'`.

- [ ] **Step 3: Implement `workflows/claim_contract.py`**

Create `workflows/claim_contract.py` with:

```python
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


_SYMBOL_RE = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]{2,})\b")
_IMPLEMENT_RE = re.compile(r"\bimplement\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE)
_REQUIRED_API_RE = re.compile(r"^\s*-\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*$", re.MULTILINE)
_LIMITATION_RE = re.compile(r"(?:risk|limitation):\s*(.+)", re.IGNORECASE)
_CLAIM_KEYWORDS = (
    "reward",
    "rollout",
    "retrieval",
    "inference",
    "evaluation",
    "metric",
    "dataset",
    "skill",
    "reflection",
    "dedup",
)


@dataclass(frozen=True)
class ClaimRequirement:
    claim_id: str
    description: str
    required_symbols: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "description": self.description,
            "required_symbols": self.required_symbols,
        }


@dataclass(frozen=True)
class ClaimContract:
    claims: list[ClaimRequirement]
    required_symbols: list[str]
    limitations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "claims": [claim.to_dict() for claim in self.claims],
            "required_symbols": self.required_symbols,
            "limitations": self.limitations,
        }

    def to_prompt_block(self) -> str:
        lines = ["# PAPER CLAIM CONTRACT", "Implement these required symbols:"]
        for symbol in self.required_symbols:
            lines.append(f"- `{symbol}`")
        lines.append("Claim requirements:")
        for claim in self.claims:
            lines.append(f"- {claim.claim_id}: {claim.description}")
        if self.limitations:
            lines.append("Known limitations to state honestly:")
            for limitation in self.limitations:
                lines.append(f"- {limitation}")
        return "\n".join(lines)


def _extract_required_symbols(plan_text: str) -> list[str]:
    symbols: set[str] = set(_IMPLEMENT_RE.findall(plan_text or ""))
    in_required_api = False
    for line in (plan_text or "").splitlines():
        stripped = line.strip()
        if stripped.endswith(":") and "required_api" in stripped:
            in_required_api = True
            continue
        if in_required_api:
            if stripped and not stripped.startswith("-"):
                in_required_api = False
                continue
            match = _REQUIRED_API_RE.match(line)
            if match:
                symbols.add(match.group(1))
    return sorted(symbols)


def _extract_claims(plan_text: str, required_symbols: list[str]) -> list[ClaimRequirement]:
    claims: list[ClaimRequirement] = []
    for line in (plan_text or "").splitlines():
        stripped = line.strip(" -")
        if not stripped:
            continue
        lowered = stripped.lower()
        if not any(keyword in lowered for keyword in _CLAIM_KEYWORDS):
            continue
        line_symbols = [symbol for symbol in required_symbols if symbol in stripped]
        claims.append(
            ClaimRequirement(
                claim_id=f"claim_{len(claims) + 1}",
                description=stripped,
                required_symbols=line_symbols,
            )
        )
    if not claims and required_symbols:
        claims.append(
            ClaimRequirement(
                claim_id="claim_1",
                description="Implement required paper APIs with runnable behavior.",
                required_symbols=required_symbols,
            )
        )
    return claims


def _extract_limitations(critique_text: str) -> list[str]:
    return sorted(
        {
            match.group(1).strip().rstrip(".")
            for match in _LIMITATION_RE.finditer(critique_text or "")
            if match.group(1).strip()
        }
    )


def build_claim_contract(plan_text: str, critique_text: str = "") -> ClaimContract:
    required_symbols = _extract_required_symbols(plan_text)
    return ClaimContract(
        claims=_extract_claims(plan_text, required_symbols),
        required_symbols=required_symbols,
        limitations=_extract_limitations(critique_text),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_claim_contract.py -q
```

Expected: `2 passed`.

---

## Task 2: Anti-Scaffold Generated Project Lint

**Files:**
- Create: `workflows/generated_project_lint.py`
- Test: `tests/test_generated_project_lint.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_generated_project_lint.py`:

```python
from workflows.claim_contract import ClaimContract, ClaimRequirement
from workflows.generated_project_lint import lint_generated_project


def test_lint_rejects_missing_required_symbol(tmp_path):
    code_dir = tmp_path / "generate_code"
    (code_dir / "src").mkdir(parents=True)
    (code_dir / "src" / "pipeline.py").write_text("def other():\n    return 1\n")

    contract = ClaimContract(
        claims=[ClaimRequirement("claim_1", "stability", ["compute_stability_signal"])],
        required_symbols=["compute_stability_signal"],
        limitations=[],
    )

    result = lint_generated_project(str(code_dir), contract)

    assert result["status"] == "error"
    assert "missing required symbols: compute_stability_signal" in result["failures"]


def test_lint_rejects_placeholder_function_body(tmp_path):
    code_dir = tmp_path / "generate_code"
    (code_dir / "src").mkdir(parents=True)
    (code_dir / "src" / "pipeline.py").write_text(
        "def compute_stability_signal():\n    pass\n",
        encoding="utf-8",
    )
    contract = ClaimContract(claims=[], required_symbols=["compute_stability_signal"], limitations=[])

    result = lint_generated_project(str(code_dir), contract)

    assert result["status"] == "error"
    assert any("placeholder" in failure for failure in result["failures"])
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_generated_project_lint.py -q
```

Expected: fail with missing module.

- [ ] **Step 3: Implement `workflows/generated_project_lint.py`**

Create `workflows/generated_project_lint.py` with:

```python
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from workflows.claim_contract import ClaimContract


_PLACEHOLDER_STRINGS = {
    "todo",
    "placeholder",
    "not implemented",
    "mock",
    "stub",
}


def _python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if path.is_file() and "__pycache__" not in path.parts)


def _defined_symbols(root: Path) -> tuple[set[str], list[str]]:
    symbols: set[str] = set()
    placeholders: list[str] = []
    for path in _python_files(root):
        rel = path.relative_to(root).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                symbols.add(node.name)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    placeholders.append(f"{rel}:{node.name}")
                for child in ast.walk(node):
                    if isinstance(child, ast.Constant) and isinstance(child.value, str):
                        lowered = child.value.lower()
                        if any(marker in lowered for marker in _PLACEHOLDER_STRINGS):
                            placeholders.append(f"{rel}:{node.name}")
    return symbols, sorted(set(placeholders))


def lint_generated_project(code_directory: str, contract: ClaimContract) -> dict[str, Any]:
    root = Path(code_directory)
    failures: list[str] = []
    if not root.is_dir():
        return {
            "status": "error",
            "failures": [f"generated code directory does not exist: {code_directory}"],
            "defined_symbols": [],
            "placeholder_symbols": [],
        }

    defined_symbols, placeholder_symbols = _defined_symbols(root)
    missing = sorted(symbol for symbol in contract.required_symbols if symbol not in defined_symbols)
    if missing:
        failures.append("missing required symbols: " + ", ".join(missing))
    if placeholder_symbols:
        failures.append("placeholder implementations: " + ", ".join(placeholder_symbols[:10]))

    return {
        "status": "error" if failures else "success",
        "failures": failures,
        "defined_symbols": sorted(defined_symbols),
        "placeholder_symbols": placeholder_symbols,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_generated_project_lint.py -q
```

Expected: `2 passed`.

---

## Task 3: Bounded Reproduction Gate

**Files:**
- Create: `workflows/reproduction_gate.py`
- Test: `tests/test_reproduction_gate.py`
- Modify: `workflows/agents/validation_agent.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_reproduction_gate.py`:

```python
from workflows.artifact_contract import ArtifactContract
from workflows.claim_contract import ClaimContract
from workflows.reproduction_gate import run_reproduction_gate


def test_reproduction_gate_times_out_hanging_demo(tmp_path):
    code_dir = tmp_path / "generate_code"
    code_dir.mkdir()
    (code_dir / "main.py").write_text("while True:\n    pass\n", encoding="utf-8")
    contract = ArtifactContract(source_root=".", entrypoint="main.py", smoke_commands=["python main.py"])

    result = run_reproduction_gate(
        str(code_dir),
        artifact_contract=contract,
        claim_contract=ClaimContract(claims=[], required_symbols=[], limitations=[]),
        timeout_seconds=1,
    )

    assert result["status"] == "error"
    assert any(check["status"] == "timeout" for check in result["checks"])


def test_reproduction_gate_runs_minimal_demo(tmp_path):
    code_dir = tmp_path / "generate_code"
    code_dir.mkdir()
    (code_dir / "main.py").write_text(
        "import argparse\nparser=argparse.ArgumentParser(); parser.parse_args(); print('ok')\n",
        encoding="utf-8",
    )
    contract = ArtifactContract(source_root=".", entrypoint="main.py", smoke_commands=["python main.py --help"])

    result = run_reproduction_gate(
        str(code_dir),
        artifact_contract=contract,
        claim_contract=ClaimContract(claims=[], required_symbols=[], limitations=[]),
        timeout_seconds=2,
    )

    assert result["status"] == "success"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_reproduction_gate.py -q
```

Expected: fail with missing module.

- [ ] **Step 3: Implement `workflows/reproduction_gate.py`**

Create `workflows/reproduction_gate.py` with:

```python
from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from workflows.artifact_contract import ArtifactContract
from workflows.claim_contract import ClaimContract
from workflows.generated_project_lint import lint_generated_project


def _run_check(name: str, command: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            env={**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
        )
        return {
            "name": name,
            "command": command,
            "returncode": proc.returncode,
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:],
            "status": "success" if proc.returncode == 0 else "error",
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "name": name,
            "command": command,
            "returncode": -1,
            "stdout": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
            "status": "timeout",
        }


def run_reproduction_gate(
    code_directory: str,
    *,
    artifact_contract: ArtifactContract,
    claim_contract: ClaimContract,
    timeout_seconds: int = 10,
) -> dict[str, Any]:
    root = Path(code_directory)
    checks: list[dict[str, Any]] = []

    lint_result = lint_generated_project(code_directory, claim_contract)
    checks.append({"name": "claim_contract_lint", **lint_result})

    checks.append(_run_check("compileall", [sys.executable, "-m", "compileall", "-q", "."], root, timeout_seconds))
    for command in artifact_contract.smoke_commands[:2]:
        checks.append(_run_check("smoke", shlex.split(command), root, timeout_seconds))

    status = "success"
    for check in checks:
        if check.get("status") not in {"success"}:
            status = "error"
            break
    return {"status": status, "checks": checks}
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_reproduction_gate.py -q
```

Expected: `2 passed`.

- [ ] **Step 5: Add validation-agent timeout hardening**

Modify `workflows/agents/validation_agent.py` where pytest is invoked:

```python
env = {**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
proc = subprocess.run(
    [sys.executable, "-m", "pytest", VALIDATION_TEST_FILENAME, "-v", "--tb=short", "--no-header", "-q"],
    cwd=code_directory,
    text=True,
    capture_output=True,
    timeout=60,
    env=env,
)
```

Keep the existing timeout exception path, but update its raw output to `pytest timed out after 60s`.

- [ ] **Step 6: Run targeted validation-agent tests**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_reproduction_gate.py tests/test_pipeline_critique_wiring.py -q
```

Expected: tests pass.

---

## Task 4: Inject Claim Contract Into First-Pass Code Generation

**Files:**
- Modify: `workflows/code_implementation_workflow.py`
- Modify: `workflows/code_implementation_workflow_index.py`
- Test: extend `tests/test_pipeline_critique_wiring.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_pipeline_critique_wiring.py`:

```python
def test_claim_contract_prompt_block_mentions_required_symbols():
    from workflows.claim_contract import build_claim_contract

    contract = build_claim_contract(
        plan_text="implementation_components:\n  - reward: implement compute_stability_signal\n",
        critique_text="",
    )

    prompt_block = contract.to_prompt_block()

    assert "PAPER CLAIM CONTRACT" in prompt_block
    assert "`compute_stability_signal`" in prompt_block
```

- [ ] **Step 2: Run test to verify it fails if Task 1 has not been implemented**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_pipeline_critique_wiring.py::test_claim_contract_prompt_block_mentions_required_symbols -q
```

Expected: pass after Task 1, fail before Task 1.

- [ ] **Step 3: Add optional `claim_contract_prompt` parameter**

Modify both implementation workflows so `implement_code_pure(...)` accepts:

```python
claim_contract_prompt: str | None = None
```

When building the implementation prompt, append:

```python
if claim_contract_prompt:
    implementation_prompt += "\n\n" + claim_contract_prompt
    implementation_prompt += (
        "\n\n# QUALITY RULES\n"
        "- Do not write placeholder, mock, stub, or pass-only implementations.\n"
        "- Required symbols must be implemented with executable behavior.\n"
        "- README commands, CLI parser, and smoke commands must agree.\n"
        "- If a dataset or model is unavailable, expose a local deterministic fallback and document the limitation.\n"
    )
```

- [ ] **Step 4: Thread the prompt from orchestration**

Modify `workflows/agent_orchestration_engine.py` after reading `initial_plan.txt`:

```python
critique_path = os.path.join(dir_info["paper_dir"], "critique_report.md")
critique_text = ""
if os.path.exists(critique_path):
    with open(critique_path, "r", encoding="utf-8") as f:
        critique_text = f.read()
claim_contract = build_claim_contract(plan_content_for_contract, critique_text)
claim_contract_prompt = claim_contract.to_prompt_block()
```

Pass `claim_contract_prompt=claim_contract_prompt` into `synthesize_code_implementation_agent(...)`, then into the selected implementation workflow.

- [ ] **Step 5: Run targeted tests**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_pipeline_critique_wiring.py -q
```

Expected: pass.

---

## Task 5: Make Gate Failures Drive Repair

**Files:**
- Modify: `workflows/agent_orchestration_engine.py`
- Modify: `workflows/repair_planner.py`
- Test: extend `tests/test_repair_planner.py`
- Test: extend `tests/test_pipeline_critique_wiring.py`

- [ ] **Step 1: Write repair prompt failing test**

Append to `tests/test_repair_planner.py`:

```python
def test_repair_prompt_lists_reproduction_gate_failures():
    from workflows.repair_planner import build_repair_prompt

    prompt = build_repair_prompt(
        {
            "status": "error",
            "failures": [],
            "reproduction_gate": {
                "status": "error",
                "checks": [
                    {
                        "name": "claim_contract_lint",
                        "failures": ["missing required symbols: compute_stability_signal"],
                        "status": "error",
                    },
                    {
                        "name": "smoke",
                        "stderr": "ModuleNotFoundError: No module named 'src'",
                        "status": "error",
                    },
                ],
            },
        }
    )

    assert "missing required symbols: compute_stability_signal" in prompt
    assert "ModuleNotFoundError: No module named 'src'" in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_repair_planner.py::test_repair_prompt_lists_reproduction_gate_failures -q
```

Expected: fail because `reproduction_gate` is not included in repair prompt.

- [ ] **Step 3: Extend repair planner**

In `workflows/repair_planner.py`, add this section to `build_repair_prompt`:

```python
gate_result = quality_result.get("reproduction_gate") or {}
if gate_result:
    lines.append("\n# Reproduction gate failures to fix")
    for check in gate_result.get("checks", []) or []:
        if check.get("status") == "success":
            continue
        lines.append(f"- check: {check.get('name', 'unknown')}")
        for failure in check.get("failures", []) or []:
            lines.append(f"  failure: {failure}")
        if check.get("stderr"):
            lines.append(f"  stderr: {str(check.get('stderr'))[:1000]}")
        if check.get("stdout"):
            lines.append(f"  stdout: {str(check.get('stdout'))[:1000]}")
```

- [ ] **Step 4: Merge reproduction gate into quality result**

In `workflows/agent_orchestration_engine.py`, after static quality and contract checks:

```python
reproduction_gate = run_reproduction_gate(
    code_directory,
    artifact_contract=artifact_contract,
    claim_contract=claim_contract,
    timeout_seconds=10,
)
quality_result["reproduction_gate"] = reproduction_gate
if reproduction_gate.get("status") == "error":
    quality_result["status"] = "error"
    failures = list(quality_result.get("failures", []) or [])
    failures.append("Reproduction gate failed")
    quality_result["failures"] = failures
```

Use this merged `quality_result` before deciding whether to run repair.

- [ ] **Step 5: Run targeted tests**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_repair_planner.py tests/test_pipeline_critique_wiring.py tests/test_reproduction_gate.py -q
```

Expected: pass.

---

## Task 6: Keep Heavy Tests Out Of The Default Path

**Files:**
- Modify: `pytest.ini`
- Modify: `workflows/agents/validation_agent.py`
- Test: extend `tests/test_reproduction_gate.py`

- [ ] **Step 1: Add pytest markers**

Modify `pytest.ini`:

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
markers =
    heavy: tests that import full workflow stacks, generated projects, or ML/document-conversion dependencies
    integration: tests that start API clients or subprocesses
```

- [ ] **Step 2: Add a safe default command to docs in the plan**

Use this command for routine validation while the backend is running:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_claim_contract.py tests/test_generated_project_lint.py tests/test_reproduction_gate.py tests/test_repair_planner.py -q
```

Use this command only when the backend is stopped:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q
```

- [ ] **Step 3: Add generated-code pytest timeout test**

Append to `tests/test_reproduction_gate.py`:

```python
def test_reproduction_gate_uses_pytest_plugin_autoload_disabled(tmp_path, monkeypatch):
    code_dir = tmp_path / "generate_code"
    code_dir.mkdir()
    (code_dir / "main.py").write_text("print('ok')\n", encoding="utf-8")
    contract = ArtifactContract(source_root=".", entrypoint="main.py", smoke_commands=["python main.py"])

    result = run_reproduction_gate(
        str(code_dir),
        artifact_contract=contract,
        claim_contract=ClaimContract(claims=[], required_symbols=[], limitations=[]),
        timeout_seconds=2,
    )

    compile_check = next(check for check in result["checks"] if check["name"] == "compileall")
    assert compile_check["status"] == "success"
```

- [ ] **Step 4: Run safe test subset**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_claim_contract.py tests/test_generated_project_lint.py tests/test_reproduction_gate.py tests/test_repair_planner.py -q
```

Expected: pass.

---

## Verification

Run these commands when the backend is not running:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_claim_contract.py tests/test_generated_project_lint.py tests/test_reproduction_gate.py tests/test_repair_planner.py tests/test_pipeline_critique_wiring.py -q
python -m compileall -q workflows tests
```

Run full tests only when no live task is active:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q
```

Expected:

- Claim contract tests pass.
- Generated project lint tests pass.
- Reproduction gate tests pass with timeout behavior.
- Repair planner includes reproduction gate failures.
- Existing pipeline wiring tests pass.
- Full tests pass without running a live backend at the same time.

## Execution Notes

- Do not hard-code Hyper-KGGen function names in framework code. They belong in the task-specific claim contract extracted from the plan or validation requirements.
- Do not run `python -m pytest tests/ -v` while `python serve.py` is running.
- Do not run generated-project pytest without a timeout.
- Treat `validation.status == "skipped"` as non-repairable by default; skipped validation usually means environment or LLM availability, not necessarily bad generated code.
- Keep this first iteration deterministic. Model-based scoring can be added later after the deterministic gates are reliable.

