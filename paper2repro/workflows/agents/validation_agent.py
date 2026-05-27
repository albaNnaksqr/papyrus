"""
Phase 9.5 — Reproduction Validation Agent

Two-step validation after code generation:
  1. LLM generates ``validate_paper_claims.py`` with targeted pytest assertions
     derived from the paper critique and implementation plan.
  2. Run pytest and capture structured pass/fail results.

Failure is non-fatal: the agent returns {"status": "skipped", "reason": ...}
so the pipeline always proceeds to Phase 10.
"""

from __future__ import annotations

import glob
import json
import logging
import os
import re
import signal
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from workflows.artifact_contract import ArtifactContract

import openai

VALIDATION_TEST_FILENAME = "validate_paper_claims.py"
VALIDATION_REPORT_FILENAME = "validation_report.md"


def _run_pytest_validation(code_directory: str) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        "-m",
        "pytest",
        VALIDATION_TEST_FILENAME,
        "-v",
        "--tb=short",
        "--no-header",
        "-q",
    ]
    start_new_session = os.name != "nt"
    proc = subprocess.Popen(
        command,
        cwd=code_directory,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
        start_new_session=start_new_session,
    )
    try:
        stdout, stderr = proc.communicate(timeout=60)
    except subprocess.TimeoutExpired as exc:
        if start_new_session:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            proc.kill()
        stdout, stderr = proc.communicate()
        raise subprocess.TimeoutExpired(
            command,
            60,
            output=stdout,
            stderr=stderr,
        ) from exc

    return subprocess.CompletedProcess(
        args=command,
        returncode=proc.returncode,
        stdout=stdout,
        stderr=stderr,
    )

_SYSTEM_PROMPT = """\
You are an expert ML engineer writing pytest unit tests to validate a paper reproduction.

Your tests must:
- Be self-contained and runnable in the project's directory
- Import from the generated code files (use relative imports or sys.path)
- Assert STRUCTURAL and MATHEMATICAL properties described in the paper
- NOT require training, GPU, or large datasets — use tiny synthetic tensors
- Cover exactly the claims listed in the critique report

Each test function should:
1. Have a docstring quoting the paper claim it validates
2. Use torch tensors of minimal size (e.g. batch=1, dim=4, rank=2)
3. Assert numerical equalities with torch.allclose(atol=1e-5) or exact checks
4. Be independent (no shared fixtures that can fail together)

Output ONLY valid Python code with no markdown fences."""

_USER_PROMPT = """\
## Must-Implement Constraints (from structured critique — highest priority)
{must_implement}

## Implementation Plan (file structure and key modules)
{plan}

## Generated Python Files
{file_list}

## Sample code from main module
{code_sample}
{layout}
Write a complete pytest file `validate_paper_claims.py` that validates EACH constraint
listed in "Must-Implement Constraints" with a dedicated test function.
Include a module-level docstring explaining what each test validates.
"""

_MAX_TOKENS = 4500
_CODE_SAMPLE_CHARS = 3000
_CRITIQUE_CHARS = 4000
_PLAN_CHARS = 2000


def _build_user_prompt(
    must_implement: str,
    plan: str,
    file_list: str,
    code_sample: str,
    contract: "ArtifactContract | None" = None,
) -> str:
    """Format the validation agent's user prompt.

    When ``contract`` is provided, its ``to_prompt_block()`` content is
    embedded so the LLM follows the same project-root + import-path
    convention as the implementation phase. validate_paper_claims.py
    runs from the parent of project_root, so it MUST use
    ``from {project_root}.src.X`` — not ``from src.X``.
    """
    layout = ""
    if contract is not None:
        layout = "\n## Authoritative project layout\n" + contract.to_prompt_block() + "\n"
    return _USER_PROMPT.format(
        must_implement=must_implement,
        plan=plan,
        file_list=file_list,
        code_sample=code_sample,
        layout=layout,
    )


def _read_truncated(path: str, limit: int) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        return text[:limit] + ("…[truncated]" if len(text) > limit else "")
    except Exception:
        return ""


def _collect_python_files(code_dir: str) -> list[str]:
    """Return .py files in code_dir, excluding tests and __pycache__."""
    result = []
    for root, dirs, files in os.walk(code_dir):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", "node_modules")]
        for f in files:
            if f.endswith(".py") and "test" not in f.lower():
                result.append(os.path.join(root, f))
    return sorted(result)


def _sample_code(py_files: list[str]) -> str:
    """Return first _CODE_SAMPLE_CHARS of the largest non-test .py file."""
    if not py_files:
        return "(no Python files found)"
    largest = max(py_files, key=lambda p: os.path.getsize(p), default=py_files[0])
    return _read_truncated(largest, _CODE_SAMPLE_CHARS)


def _parse_pytest_output(stdout: str, returncode: int) -> dict[str, Any]:
    """Extract pass/fail counts and per-test results from pytest -v output."""
    tests: list[dict] = []
    for line in stdout.splitlines():
        m = re.match(r"^(.*)::(test_\w+)\s+(PASSED|FAILED|ERROR|SKIPPED)", line)
        if m:
            tests.append({"name": m.group(2), "status": m.group(3).lower()})

    # Summary line: "5 passed, 1 failed in 0.12s"
    summary_match = re.search(
        r"(\d+) passed(?:,\s*(\d+) failed)?(?:,\s*(\d+) error)?", stdout
    )
    passed = int(summary_match.group(1)) if summary_match else sum(1 for t in tests if t["status"] == "passed")
    failed = int(summary_match.group(2) or 0) if summary_match else sum(1 for t in tests if t["status"] in ("failed", "error"))

    return {
        "passed": passed,
        "failed": failed,
        "total": passed + failed,
        "tests": tests,
        "raw_output": stdout[-3000:],  # tail to avoid huge logs
        "exit_code": returncode,
    }


async def run_validation_agent(
    paper_dir: str,
    code_directory: str | None,
    llm_config: dict[str, Any],
    logger: logging.Logger | None = None,
    artifact_contract: "ArtifactContract | None" = None,
) -> dict[str, Any]:
    """
    Phase 9.5 validation.

    Args:
        paper_dir: Task directory (contains critique_report.md, initial_plan.txt).
        code_directory: Directory where Phase 9 wrote source files.
        llm_config: Keys: base_url, api_key, critique_model.
        logger: Optional logger.
        artifact_contract: When provided, its to_prompt_block() is embedded in
            the user prompt so the LLM uses the correct import shape
            (``from {project_root}.src.X``) for validate_paper_claims.py.

    Returns:
        {"status": "success", "passed": N, "failed": N, "tests": [...], ...}
        {"status": "skipped", "reason": str}
        {"status": "error",   "reason": str, "passed": 0, "failed": 0}
    """
    log = logger or logging.getLogger(__name__)

    # ── Resolve code directory ────────────────────────────────────────────────
    if not code_directory:
        # Fallback: look for any non-hidden subdir with .py files
        for d in Path(paper_dir).iterdir():
            if d.is_dir() and not d.name.startswith("."):
                if list(d.rglob("*.py")):
                    code_directory = str(d)
                    break
    if not code_directory or not os.path.isdir(code_directory):
        return {"status": "skipped", "reason": f"No code directory found in {paper_dir}"}

    # ── Collect inputs ────────────────────────────────────────────────────────
    plan_path = os.path.join(paper_dir, "initial_plan.txt")
    plan = _read_truncated(plan_path, _PLAN_CHARS) if os.path.exists(plan_path) else "(no plan)"

    # Prefer structured JSON; fall back to freeform report
    structured_path = os.path.join(paper_dir, "critique_structured.json")
    must_implement_text = ""
    if os.path.exists(structured_path):
        try:
            with open(structured_path, "r", encoding="utf-8") as _f:
                structured = json.load(_f)
            items = structured.get("must_implement", [])
            lines = []
            for item in items:
                hint = f" — 实现提示: {item['code_hint']}" if item.get("code_hint") else ""
                lines.append(f"- {item['claim']} ({item.get('section', '')}){hint}")
            must_implement_text = "\n".join(lines)
            log.info(f"[Validation] Loaded {len(items)} must_implement constraints from structured JSON")
        except Exception as _e:
            log.warning(f"[Validation] Could not load structured JSON ({_e}), falling back to report")

    if not must_implement_text:
        critique_path = os.path.join(paper_dir, "critique_report.md")
        must_implement_text = (
            _read_truncated(critique_path, _CRITIQUE_CHARS)
            if os.path.exists(critique_path)
            else "(no critique report)"
        )

    py_files = _collect_python_files(code_directory)
    if not py_files:
        return {"status": "skipped", "reason": f"No Python source files in {code_directory}"}

    file_list = "\n".join(os.path.relpath(f, code_directory) for f in py_files)
    code_sample = _sample_code(py_files)

    # ── Step 1: LLM generates validation tests ────────────────────────────────
    try:
        client = openai.OpenAI(
            base_url=llm_config.get("base_url", "https://api.openai.com/v1"),
            api_key=llm_config.get("api_key", os.environ.get("OPENAI_API_KEY", "")),
        )
        model = llm_config.get("critique_model", "gpt-4o")
        log.info(f"[Validation] Generating test file with {model}...")

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(
                    must_implement=must_implement_text,
                    plan=plan,
                    file_list=file_list,
                    code_sample=code_sample,
                    contract=artifact_contract,
                )},
            ],
            max_tokens=_MAX_TOKENS,
            temperature=0.2,
        )
        test_code = response.choices[0].message.content or ""
    except Exception as e:
        reason = f"LLM call failed: {e}"
        log.warning(f"[Validation] Skipping: {reason}")
        return {"status": "skipped", "reason": reason}

    # Strip accidental markdown fences
    test_code = re.sub(r"^```python\s*\n?", "", test_code, flags=re.MULTILINE)
    test_code = re.sub(r"\n?```\s*$", "", test_code, flags=re.MULTILINE)

    # Verify syntax before writing — a truncated LLM response produces broken Python
    try:
        compile(test_code, VALIDATION_TEST_FILENAME, "exec")
    except SyntaxError as e:
        log.warning(f"[Validation] Generated test file has syntax errors ({e}); skipping")
        return {"status": "skipped", "reason": f"Generated test code has syntax errors: {e}"}

    # Write test file into the code directory
    test_path = os.path.join(code_directory, VALIDATION_TEST_FILENAME)
    try:
        with open(test_path, "w", encoding="utf-8") as f:
            f.write(test_code)
        log.info(f"[Validation] Test file written: {test_path}")
    except Exception as e:
        return {"status": "skipped", "reason": f"Cannot write test file: {e}"}

    # ── Step 2: Run pytest ────────────────────────────────────────────────────
    try:
        proc = _run_pytest_validation(code_directory)
        combined = proc.stdout + ("\n" + proc.stderr if proc.stderr else "")
        result = _parse_pytest_output(combined, proc.returncode)
        log.info(f"[Validation] pytest: {result['passed']} passed, {result['failed']} failed")
    except subprocess.TimeoutExpired as exc:
        combined = (exc.output or "") + ("\n" + exc.stderr if exc.stderr else "")
        result = {
            "passed": 0,
            "failed": 0,
            "total": 0,
            "tests": [],
            "raw_output": combined or "pytest timed out after 60s",
            "exit_code": -1,
        }
    except Exception as e:
        result = {"passed": 0, "failed": 0, "total": 0, "tests": [], "raw_output": str(e), "exit_code": -1}

    # ── Write validation_report.md ────────────────────────────────────────────
    _write_report(paper_dir, code_directory, test_path, result)

    status = "success" if result["exit_code"] == 0 else "partial" if result["passed"] > 0 else "error"
    return {
        "status": status,
        "passed": result["passed"],
        "failed": result["failed"],
        "total": result["total"],
        "tests": result["tests"],
        "test_file": test_path,
        "report_path": os.path.join(paper_dir, VALIDATION_REPORT_FILENAME),
        "raw_output": result["raw_output"],
    }


def _write_report(paper_dir: str, code_dir: str, test_path: str, result: dict) -> None:
    passed, failed, total = result["passed"], result["failed"], result["total"]
    icon = "✅" if failed == 0 and total > 0 else "⚠️" if passed > 0 else "❌"

    lines = [
        "# 复现验证报告\n",
        f"> 本报告由 Phase 9.5 验证 Agent 自动生成。\n",
        f"## 汇总 {icon}\n",
        f"| 通过 | 失败 | 总计 |",
        f"|------|------|------|",
        f"| {passed} | {failed} | {total} |\n",
        f"## 测试文件\n`{os.path.relpath(test_path, paper_dir)}`\n",
        "## 详细结果\n",
    ]
    for t in result.get("tests", []):
        icon_t = "✅" if t["status"] == "passed" else "❌"
        lines.append(f"- {icon_t} `{t['name']}` — {t['status']}")

    lines += ["\n## pytest 输出\n```\n" + result.get("raw_output", "") + "\n```\n"]

    report_path = os.path.join(paper_dir, VALIDATION_REPORT_FILENAME)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
