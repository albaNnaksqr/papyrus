from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any


_IGNORED_PARTS = {
    "__pycache__",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "venv",
}


def _relative_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _is_ignored(path: Path) -> bool:
    return any(part in _IGNORED_PARTS for part in path.parts)


def _python_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*.py")
        if path.is_file() and not _is_ignored(path)
    )


def _has_python_files(path: Path) -> bool:
    return any(child.is_file() for child in path.rglob("*.py") if not _is_ignored(child))


def _detect_source_roots(root: Path) -> list[str]:
    source_roots: set[str] = set()
    direct_src = root / "src"
    if direct_src.is_dir() and _has_python_files(direct_src):
        source_roots.add("src")

    for child in root.iterdir() if root.exists() else []:
        if not child.is_dir() or child.name in _IGNORED_PARTS:
            continue
        nested_src = child / "src"
        if nested_src.is_dir() and _has_python_files(nested_src):
            source_roots.add(f"{child.name}/src")

    return sorted(source_roots)


_PYTHON_COMMAND_RE = re.compile(
    r"\bpython(?:3(?:\.\d+)?)?\s+(?!-m\b)(?:-[A-Za-z]\s+)*([^\s`\"']+\.py)\b"
)


def _clean_advertised_path(raw_path: str) -> str | None:
    cleaned = raw_path.strip().strip("\"'`")
    if not cleaned or "://" in cleaned:
        return None
    path = Path(cleaned)
    if path.is_absolute() or ".." in path.parts:
        return None
    return path.as_posix().lstrip("./")


def _extract_python_commands(text: str) -> set[str]:
    paths: set[str] = set()
    for match in _PYTHON_COMMAND_RE.finditer(text):
        cleaned = _clean_advertised_path(match.group(1))
        if cleaned:
            paths.add(cleaned)
    return paths


def _strip_tree_comment(name: str) -> str:
    return name.split("#", 1)[0].strip()


def _extract_tree_paths_from_readme(text: str, *, root_name: str | None = None) -> set[str]:
    """Extract Python file paths from common README tree diagrams."""
    advertised: set[str] = set()
    in_fence = False
    stack: list[str] = []
    explicit_root = False

    for raw_line in text.splitlines():
        stripped = raw_line.rstrip()
        if stripped.strip().startswith("```"):
            in_fence = not in_fence
            stack = []
            explicit_root = False
            continue
        if not in_fence:
            continue

        line = stripped.strip()
        if not line:
            continue

        marker_index = -1
        for marker in ("├──", "└──"):
            marker_index = line.find(marker)
            if marker_index != -1:
                break

        if marker_index == -1:
            name = _strip_tree_comment(line)
            if name.endswith("/") and not any(ch.isspace() for ch in name.rstrip("/")):
                dirname = name.rstrip("/")
                stack = [] if root_name and dirname == root_name else [dirname]
                explicit_root = True
            continue

        prefix = line[:marker_index]
        name = _strip_tree_comment(line[marker_index + 3 :])
        if not name:
            continue

        depth = len(prefix) // 4 + 1
        if explicit_root:
            parent_parts = stack[:depth]
            dir_index = depth
        else:
            parent_parts = stack[: max(depth - 1, 0)]
            dir_index = max(depth - 1, 0)

        if name.endswith("/"):
            dirname = name.rstrip("/")
            if len(stack) <= dir_index:
                stack.extend([""] * (dir_index + 1 - len(stack)))
            stack[dir_index] = dirname
            del stack[dir_index + 1 :]
            continue

        cleaned = _clean_advertised_path("/".join([*parent_parts, name]))
        if cleaned and cleaned.endswith(".py"):
            advertised.add(cleaned)

    return advertised


def _advertised_python_files(root: Path) -> set[str]:
    advertised: set[str] = set()
    for readme in sorted(root.rglob("README*")):
        if not readme.is_file() or _is_ignored(readme):
            continue
        try:
            text = readme.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        advertised.update(_extract_python_commands(text))
        advertised.update(_extract_tree_paths_from_readme(text, root_name=root.name))
    return advertised


def _module_name_from_parts(parts: tuple[str, ...]) -> str | None:
    if not parts or not parts[-1].endswith(".py"):
        return None
    module_parts = [*parts[:-1], parts[-1][:-3]]
    if module_parts[-1] == "__init__":
        module_parts = module_parts[:-1]
    module_parts = [part for part in module_parts if part]
    return ".".join(module_parts) if module_parts else None


def _add_module_names(
    *,
    root: Path,
    py_file: Path,
    module_names: set[str],
    package_names: set[str],
    base: Path,
) -> None:
    try:
        rel_parts = py_file.relative_to(base).parts
    except ValueError:
        return

    module_name = _module_name_from_parts(rel_parts)
    if not module_name:
        return

    if py_file.name == "__init__.py":
        package_names.add(module_name)
    else:
        module_names.add(module_name)

    # Also retain the full path from the generated root when base is a source
    # root, so both `src.foo` and `foo` style imports can be checked.
    if base != root:
        try:
            full_module = _module_name_from_parts(py_file.relative_to(root).parts)
        except ValueError:
            full_module = None
        if full_module:
            if py_file.name == "__init__.py":
                package_names.add(full_module)
            else:
                module_names.add(full_module)


def _known_local_modules(
    *,
    root: Path,
    py_files: list[Path],
    source_roots: list[str],
) -> tuple[set[str], set[str], set[str]]:
    module_names: set[str] = set()
    package_names: set[str] = set()
    bases = [root, *[root / source_root for source_root in source_roots]]

    for py_file in py_files:
        for base in bases:
            _add_module_names(
                root=root,
                py_file=py_file,
                module_names=module_names,
                package_names=package_names,
                base=base,
            )

    known = module_names | package_names
    local_tops = {name.split(".", 1)[0] for name in known if name}
    return known, package_names, local_tops


def _module_exists(module: str, known_modules: set[str]) -> bool:
    return module in known_modules or any(
        known.startswith(f"{module}.") for known in known_modules
    )


def _missing_local_imports(
    *,
    root: Path,
    py_files: list[Path],
    known_modules: set[str],
    local_tops: set[str],
) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for py_file in py_files:
        rel = _relative_path(py_file, root)
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=rel)
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue

        for node in ast.walk(tree):
            module: str | None = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    candidate = alias.name
                    if candidate.split(".", 1)[0] in local_tops:
                        module = candidate
                        key = (rel, module)
                        if key not in seen and not _module_exists(module, known_modules):
                            missing.append({"file": rel, "module": module})
                            seen.add(key)
                continue

            if isinstance(node, ast.ImportFrom):
                if node.level:
                    continue
                module = node.module
                if module and module.split(".", 1)[0] in local_tops:
                    key = (rel, module)
                    if key not in seen and not _module_exists(module, known_modules):
                        missing.append({"file": rel, "module": module})
                        seen.add(key)

    return missing


def _syntax_errors(root: Path, py_files: list[Path]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for py_file in py_files:
        rel = _relative_path(py_file, root)
        try:
            ast.parse(py_file.read_text(encoding="utf-8"), filename=rel)
        except SyntaxError as exc:
            errors.append({"file": rel, "error": str(exc)})
        except (OSError, UnicodeDecodeError) as exc:
            errors.append({"file": rel, "error": str(exc)})
    return errors


def assess_generated_code_quality(
    code_directory: str | None,
    implementation_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run deterministic quality checks on generated code artifacts.

    This is intentionally static: it does not import or execute generated code.
    The goal is to catch obvious non-runnable artifacts before a task is marked
    successful.
    """
    failures: list[str] = []
    root = Path(code_directory).resolve() if code_directory else None
    if root is None or not root.is_dir():
        return {
            "status": "error",
            "code_directory": code_directory,
            "failures": [f"Generated code directory does not exist: {code_directory}"],
            "python_file_count": 0,
            "empty_python_files": [],
            "source_roots": [],
            "missing_advertised_files": [],
            "empty_advertised_files": [],
            "syntax_errors": [],
            "missing_local_imports": [],
        }

    py_files = _python_files(root)
    if not py_files:
        failures.append("Generated code directory contains no Python files")

    empty_python_files = [
        _relative_path(path, root)
        for path in py_files
        if path.name != "__init__.py" and path.stat().st_size == 0
    ]
    if empty_python_files:
        failures.append(
            "Found empty Python implementation files: "
            + ", ".join(empty_python_files[:10])
        )

    source_roots = _detect_source_roots(root)
    if len(source_roots) > 1:
        failures.append(
            "Detected multiple project roots: " + ", ".join(source_roots)
        )

    advertised = _advertised_python_files(root)
    missing_advertised_files: list[str] = []
    empty_advertised_files: list[str] = []
    # Plan A: accept advertised file if its basename is found unambiguously
    # somewhere under root (agent may organize files differently than README).
    from workflows.artifact_contract import find_file_under_root
    for rel in sorted(advertised):
        path = root / rel
        if not path.is_file():
            resolved = find_file_under_root(root, rel)
            if resolved is None:
                missing_advertised_files.append(rel)
            elif resolved.name != "__init__.py" and resolved.stat().st_size == 0:
                empty_advertised_files.append(rel)
            continue
        if path.name != "__init__.py" and path.stat().st_size == 0:
            empty_advertised_files.append(rel)

    if missing_advertised_files:
        failures.append(
            "README advertises missing files: "
            + ", ".join(missing_advertised_files[:10])
        )
    if empty_advertised_files:
        failures.append(
            "README advertises empty files: "
            + ", ".join(empty_advertised_files[:10])
        )

    syntax_errors = _syntax_errors(root, py_files)
    if syntax_errors:
        failures.append(
            "Generated Python files contain syntax errors: "
            + ", ".join(error["file"] for error in syntax_errors[:10])
        )

    known_modules, _package_names, local_tops = _known_local_modules(
        root=root,
        py_files=py_files,
        source_roots=source_roots,
    )
    missing_local_imports = _missing_local_imports(
        root=root,
        py_files=py_files,
        known_modules=known_modules,
        local_tops=local_tops,
    )
    if missing_local_imports:
        preview = ", ".join(
            f"{item['file']} -> {item['module']}" for item in missing_local_imports[:10]
        )
        failures.append(f"Generated Python files import missing local modules: {preview}")

    status = "error" if failures else "success"
    result: dict[str, Any] = {
        "status": status,
        "code_directory": str(root),
        "failures": failures,
        "python_file_count": len(py_files),
        "empty_python_files": empty_python_files,
        "source_roots": source_roots,
        "missing_advertised_files": missing_advertised_files,
        "empty_advertised_files": empty_advertised_files,
        "syntax_errors": syntax_errors,
        "missing_local_imports": missing_local_imports,
    }
    if implementation_result:
        result["implementation_status"] = implementation_result.get("status")
        result["implementation_inner_status"] = implementation_result.get("inner_status")
    return result


def status_after_quality_gate(
    pipeline_status: str,
    quality_result: dict[str, Any] | None,
) -> str:
    if pipeline_status not in {"completed", "completed_with_warnings"}:
        return pipeline_status
    quality_status = str((quality_result or {}).get("status", "")).lower()
    if quality_status == "error":
        return "error"
    return pipeline_status
