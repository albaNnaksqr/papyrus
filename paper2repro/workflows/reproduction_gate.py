from __future__ import annotations

import os
import shlex
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

from workflows.artifact_contract import ArtifactContract, is_blocked_smoke_command
from workflows.claim_contract import ClaimContract
from workflows.generated_project_lint import lint_generated_project


_OUTPUT_LIMIT = 4000


def _tail_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")[-_OUTPUT_LIMIT:]
    return value[-_OUTPUT_LIMIT:]


def _run_check(name: str, command: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
    start_new_session = os.name != "nt"
    proc: subprocess.Popen[str] | None = None
    try:
        proc = subprocess.Popen(
            command,
            cwd=str(cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
            start_new_session=start_new_session,
        )
        stdout, stderr = proc.communicate(timeout=timeout_seconds)
        return {
            "name": name,
            "command": command,
            "returncode": proc.returncode,
            "stdout": _tail_text(stdout),
            "stderr": _tail_text(stderr),
            "status": "success" if proc.returncode == 0 else "error",
        }
    except subprocess.TimeoutExpired:
        if proc is not None:
            if start_new_session:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                proc.kill()
            stdout, stderr = proc.communicate()
        else:
            stdout, stderr = "", ""
        return {
            "name": name,
            "command": command,
            "returncode": -1,
            "stdout": _tail_text(stdout),
            "stderr": _tail_text(stderr),
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

    checks.append(
        _run_check(
            "compileall",
            [sys.executable, "-m", "compileall", "-q", "."],
            root,
            timeout_seconds,
        )
    )
    smoke_commands_run = 0
    for command in artifact_contract.smoke_commands:
        if smoke_commands_run >= 2:
            break
        if is_blocked_smoke_command(command):
            checks.append(
                {
                    "name": "smoke",
                    "command": shlex.split(command),
                    "returncode": None,
                    "stdout": "",
                    "stderr": "Blocked pytest/full-suite smoke command",
                    "status": "error",
                }
            )
            break
        checks.append(_run_check("smoke", shlex.split(command), root, timeout_seconds))
        smoke_commands_run += 1

    status = "success"
    for check in checks:
        if check.get("status") != "success":
            status = "error"
            break

    return {"status": status, "checks": checks}
