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
    return sorted(
        path for path in root.rglob("*.py") if path.is_file() and "__pycache__" not in path.parts
    )


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
