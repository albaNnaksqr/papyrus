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
        if not full_path.read_text(encoding="utf-8").strip():
            return {"accepted": False, "reason": "empty implementation file"}
        try:
            ast.parse(full_path.read_text(encoding="utf-8"), filename=rel)
        except SyntaxError as exc:
            return {"accepted": False, "reason": f"syntax error: {exc}"}

    pr = contract.project_root.rstrip("/")
    in_project = pr == "." or rel.startswith(pr + "/")
    allowed = (
        in_project
        or rel.startswith("tests/")
        or rel == "validate_paper_claims.py"
    )
    if rel.endswith(".py") and not allowed:
        # Unlink the rejected file so the on-disk tree reflects only
        # accepted writes. Without this, downstream filesystem scans
        # (`_top_level_py_roots`) see the rejected files and falsely
        # report "multiple project roots". Other reject reasons (empty
        # file, syntax error) intentionally leave the file in place so
        # the agent can iterate on its own content.
        try:
            full_path.unlink()
        except OSError:
            pass
        return {
            "accepted": False,
            "reason": f"file outside project root: {rel}",
        }

    return {"accepted": True, "reason": "accepted"}


_PRUNE_SKIP_PARTS = {
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".git",
    ".venv",
    "venv",
}


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
