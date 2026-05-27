from __future__ import annotations

import os
import shlex
import signal
import subprocess
from pathlib import Path
from typing import Any

from workflows.artifact_contract import (
    ArtifactContract,
    find_file_under_root,
    is_blocked_smoke_command,
)


def _rewrite_smoke_command(argv: list[str], root: Path) -> list[str]:
    """Plan A: when the contract's smoke command references a .py file path
    that doesn't exist at the literal location (because the agent organized
    files under a subdirectory), try to resolve it by basename so smoke can
    still run.
    """
    rewritten: list[str] = []
    for arg in argv:
        if arg.endswith(".py"):
            resolved = find_file_under_root(root, arg)
            if resolved is not None:
                try:
                    rewritten.append(resolved.relative_to(root).as_posix())
                    continue
                except ValueError:
                    pass
        rewritten.append(arg)
    return rewritten


def _tail(text: str) -> str:
    return text[-4000:]


def _run_command(
    command: list[str],
    cwd: Path,
    timeout_seconds: int,
    name: str,
) -> dict[str, Any]:
    start_new_session = os.name != "nt"
    proc: subprocess.Popen[str] | None = None
    try:
        proc = subprocess.Popen(
            command,
            cwd=str(cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=start_new_session,
        )
        stdout, stderr = proc.communicate(timeout=timeout_seconds)
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
        return {
            "name": name,
            "command": command,
            "returncode": None,
            "stdout": _tail(stdout or ""),
            "stderr": _tail(stderr or f"Timed out after {timeout_seconds} seconds"),
            "status": "error",
        }
    except OSError as exc:
        return {
            "name": name,
            "command": command,
            "returncode": None,
            "stdout": "",
            "stderr": _tail(str(exc)),
            "status": "error",
        }

    return {
        "name": name,
        "command": command,
        "returncode": proc.returncode if proc is not None else None,
        "stdout": _tail(stdout),
        "stderr": _tail(stderr),
        "status": "success" if proc is not None and proc.returncode == 0 else "error",
    }


def run_smoke_checks(
    code_directory: str,
    contract: ArtifactContract,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    root = Path(code_directory).resolve()
    if not root.is_dir():
        return {
            "status": "error",
            "checks": [
                {
                    "name": "code_directory",
                    "command": [],
                    "returncode": None,
                    "stdout": "",
                    "stderr": f"Code directory does not exist: {code_directory}",
                    "status": "error",
                }
            ],
        }
    checks: list[dict[str, Any]] = [
        _run_command(
            ["python", "-m", "compileall", "-q", "."],
            root,
            timeout_seconds,
            "compileall",
        )
    ]

    if checks[-1]["status"] == "success":
        for command in contract.smoke_commands:
            if not command.strip():
                continue
            if is_blocked_smoke_command(command):
                checks.append(
                    {
                        "name": "contract_smoke_command",
                        "command": shlex.split(command),
                        "returncode": None,
                        "stdout": "",
                        "stderr": "Blocked pytest/full-suite smoke command",
                        "status": "error",
                    }
                )
                break

            argv = _rewrite_smoke_command(shlex.split(command), root)
            checks.append(
                _run_command(
                    argv,
                    root,
                    timeout_seconds,
                    "contract_smoke_command",
                )
            )
            if checks[-1]["status"] == "error":
                break

    return {
        "status": "success"
        if all(check["status"] == "success" for check in checks)
        else "error",
        "checks": checks,
    }
