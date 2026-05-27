from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ArtifactContract:
    project_root: str
    entrypoint: str
    package_name: str | None = None
    smoke_commands: list[str] = field(default_factory=list)

    def to_prompt_block(self) -> str:
        """Authoritative project-layout block injected into the implement prompt.

        Tells the agent exactly which project root and entrypoint it must
        use, and which import shape to use from inside vs. outside the
        package. code_acceptance enforces the layout server-side; the
        prompt's import convention section avoids the
        ``from src.X`` / ``from {project_root}.src.X`` confusion that
        broke validate_paper_claims.py in paper_09fffdd3.
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

        lines.extend(["", "Import paths:"])
        if root == ".":
            lines.extend(
                [
                    "- Project is flat. Use top-level imports: "
                    "`from src.X import ...` (when src/ exists) "
                    "or `from X import ...` (top-level modules).",
                    "- validate_paper_claims.py and tests/ run from the same "
                    "directory and use the same imports.",
                    "- Do NOT add `sys.path.insert(...)` workarounds.",
                ]
            )
        else:
            lines.extend(
                [
                    f"- Files INSIDE `{root}/` (entrypoint, `{root}/src/`, etc.): "
                    f"use `from src.X import ...` (Python finds src/ because "
                    f"`{root}/` is sys.path[0] when the entrypoint runs).",
                    f"- Files OUTSIDE `{root}/` (validate_paper_claims.py at the "
                    f"real root, files under tests/): use "
                    f"`from {root}.src.X import ...` (cwd is the parent of "
                    f"`{root}/`, which makes `{root}` importable as a package).",
                    "- Do NOT add `sys.path.insert(0, '..')` workarounds — they "
                    "collide with the conventions above.",
                ]
            )
        return "\n".join(lines)


_PY_PATH_RE = re.compile(r"(?<![\w/.-])([A-Za-z0-9_./-]+\.py)\b")
_SMOKE_RE = re.compile(r"smoke_command:\s*(.+)")
_ENTRY_RE = re.compile(r"entrypoint:\s*([A-Za-z0-9_./-]+\.py)")
_PACKAGE_RE = re.compile(r"package_name:\s*([A-Za-z_][A-Za-z0-9_]*)")
_PYTEST_COMMAND_RE = re.compile(
    r"(^|[;&|]\s*|timeout\s+\d+\s+)(python(?:3(?:\.\d+)?)?\s+-m\s+pytest|pytest)\b",
    re.IGNORECASE,
)
_ROOT_SUPPORT_PY_FILES = {
    "check_files.py",
    "validate_paper_claims.py",
}

# Subdirectory names that are NOT package roots — they describe sub-trees
# inside the package, not the package itself.
_NON_PACKAGE_ROOT_DIRS = {"src", "tests", "scripts", "data", "config", "docs"}

# Top-level directories that don't count as a "project root" for the
# multi-root invariant: tests/ and docs/ are conventionally outside the
# package boundary even though they can contain .py files.
_NON_PROJECT_TOP_DIRS = {"tests", "docs"}

# Cache directories that never contain real project code.
_CACHE_DIRS = {
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".git",
    ".venv",
    "venv",
}


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
        if child.name in _CACHE_DIRS:
            continue
        if any(child.rglob("*.py")):
            roots.add(child.name)

    return roots


def _detect_source_layout(plan_text: str) -> tuple[str | None, str | None]:
    """Infer source layout from a tree-style file_structure block.

    Returns ``(package_root, source_subdir)``:

    - ``package_root``: top-level package directory (e.g. ``"hyper_kggen"``)
      when the tree is wrapped in a package wrapper, else ``None``.
    - ``source_subdir``: ``"src"`` when the tree shows a ``src/`` subdirectory
      (either as the top level or as a child of the package root), else
      ``None``.

    Examples::

        file_structure: |
            hyper_kggen/
            ├── main.py
            ├── src/
            │   └── chunking.py
        # ⇒ ("hyper_kggen", "src")

        file_structure: |
            src/
            ├── main.py
        # ⇒ (None, "src")

        file_structure:
          - src/main.py
        # ⇒ (None, None)   (no tree, fall back to legacy path inference)
    """
    # If the plan is valid YAML, get file_structure as a real Python string
    # so embedded newlines are unescaped. The previous behavior of scanning
    # raw text broke when planners emitted
    #   `file_structure: "lora_implementation/\\n├── ..."`
    # (double-quoted scalar with escaped newlines) — splitlines saw one big
    # line and the tree was never detected.
    tree_text: str | None = None
    try:
        parsed = yaml.safe_load(plan_text or "")
    except Exception:
        parsed = None
    if isinstance(parsed, dict):
        for source in (parsed, parsed.get("complete_reproduction_plan")):
            if isinstance(source, dict):
                fs = source.get("file_structure")
                if isinstance(fs, str):
                    tree_text = fs
                    break

    scan_text = tree_text if tree_text is not None else (plan_text or "")
    lines = scan_text.splitlines()
    # When tree_text came from YAML, we're already inside the file_structure
    # value — start tree-walking from line 0. Otherwise wait for the header.
    in_tree_after = 0 if tree_text is not None else -1
    package_root: str | None = None
    found_top = False
    has_src_subdir = False

    for i, line in enumerate(lines):
        if in_tree_after < 0:
            if "file_structure:" in line.lower():
                in_tree_after = i
            continue
        # Limit scan to a reasonable window beyond file_structure:.
        if i - in_tree_after > 40:
            break

        stripped = line.strip()
        if not stripped or stripped in ("|", ">", "|-", "|+", ">-", ">+"):
            continue

        head = stripped.split("#", 1)[0].rstrip()

        if not found_top:
            # Inline list (`- src/main.py`) → not a tree.
            if head.startswith("-"):
                return None, None
            # Tree-branch character before we saw the root row → no top dir.
            if any(ch in head for ch in ("├", "└", "│")):
                return None, None
            m = re.match(r"^([a-zA-Z_][a-zA-Z0-9_-]*)/\s*$", head)
            if not m:
                return None, None
            found_top = True
            name = m.group(1)
            if name in _NON_PACKAGE_ROOT_DIRS:
                # The tree's top IS the source directory (e.g. `src/`).
                return None, name
            package_root = name
            continue

        # We have a package_root; scan a few more rows to spot a `src/` child.
        if "src/" in head or re.search(r"\bsrc/\s*$", head):
            has_src_subdir = True

    if package_root is not None:
        return package_root, ("src" if has_src_subdir else None)
    return None, None


def _source_root_for(path: str) -> str | None:
    parts = Path(path).parts
    if not parts:
        return None
    if len(parts) == 1 and path.endswith(".py"):
        return "."
    if parts[0] == "src":
        return "src"
    if len(parts) >= 2 and parts[1] == "src":
        return f"{parts[0]}/src"
    return parts[0] if path.endswith(".py") else None


def is_blocked_smoke_command(command: str) -> bool:
    """Return True for smoke commands that are too heavy or unsafe for gates."""
    return bool(_PYTEST_COMMAND_RE.search(command or ""))


def _guess_entrypoint_from_paths(paths: list[str]) -> str | None:
    """Pick the most likely entrypoint from the plan's listed paths.

    Preference order:
      1. main.py at a specific path (first one alphabetically if multiple)
      2. run_*.py (LoRA-style: experiments/run_glue.py is the driver)

    Returns None when neither is present.
    """
    main_candidates = sorted(
        p for p in paths
        if p == "main.py" or p.endswith("/main.py")
    )
    if main_candidates:
        return main_candidates[0]
    run_candidates = sorted(
        p for p in paths
        if Path(p).name.startswith("run_") and p.endswith(".py")
    )
    if run_candidates:
        return run_candidates[0]
    return None


def build_contract_from_plan(plan_text: str) -> ArtifactContract:
    text = plan_text or ""
    paths = sorted(set(_PY_PATH_RE.findall(text)))

    # ① project_root: tree-detected package wrapper > tree-detected source
    # subdir > path-prefix common root > "."
    package_root, source_subdir = _detect_source_layout(text)
    if package_root:
        project_root = package_root
    elif source_subdir:
        project_root = source_subdir
    else:
        path_roots = sorted(
            {root for p in paths if (root := _source_root_for(p))}
        )
        if len(path_roots) == 1:
            project_root = path_roots[0]
        else:
            # Multi-root paths (e.g. `src/` AND `experiments/`) have no
            # single wrapping directory — the project lives at ".".
            project_root = "."

    # ② package_name: explicit field wins; otherwise default to project_root
    # ONLY when the tree showed a real package wrapper. Bare "src" / "."
    # are layout markers, not package names.
    package_match = _PACKAGE_RE.search(text)
    if package_match:
        package_name = package_match.group(1)
    elif package_root:
        package_name = package_root
    else:
        package_name = None

    # ③ entrypoint: explicit > main.py / run_*.py from tree > default
    entry_match = _ENTRY_RE.search(text)
    if entry_match:
        entrypoint = entry_match.group(1)
    else:
        guessed = _guess_entrypoint_from_paths(paths)
        entrypoint = guessed if guessed else "main.py"

    # ④ Normalize entrypoint into project_root
    if project_root != "." and not entrypoint.startswith(project_root + "/"):
        entrypoint = f"{project_root}/{entrypoint.lstrip('./')}"

    # ⑤ smoke commands: explicit > derive from entrypoint
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


def find_file_under_root(root: Path, rel_path: str) -> Path | None:
    """Plan A helper: resolve a rel_path under root, falling back to a
    basename search if the exact location is missing.

    Returns the file path if found unambiguously, else None. Used by smoke
    test runner and README advertised-file checks so that the agent's right
    to reorganize a file's location doesn't sink unrelated gates.
    """
    if not rel_path:
        return None
    exact = root / rel_path
    if exact.is_file():
        return exact
    name = Path(rel_path).name
    if not name or "." not in name:
        return None
    seen: set[Path] = set()
    matches: list[Path] = []
    for found in root.rglob(name):
        if not found.is_file():
            continue
        # Skip caches and venvs to avoid pulling stale or unrelated copies.
        if any(
            part in {".mypy_cache", ".ruff_cache", "__pycache__", ".venv", "venv"}
            for part in found.parts
        ):
            continue
        resolved = found.resolve()
        if resolved not in seen:
            seen.add(resolved)
            matches.append(found)
    if len(matches) == 1:
        return matches[0]
    return None


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
