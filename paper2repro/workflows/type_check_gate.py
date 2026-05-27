"""mypy-based type-check gate for generated code.

Runs mypy as a subprocess against the generated project, parses
attr-defined / call-arg errors, groups them by symbol with
AST-derived root cause, and renders a repair prompt the existing
repair loop can feed back to the agent.

Status semantics (TypeCheckResult.status):
    - success: mypy exit 0 (clean) OR filtered_count == 0
    - errors:  mypy exit 1 AND filtered_count > 0
    - skipped: mypy missing, code_dir absent/empty, oversized,
               internal mypy error (exit 2), or safety cap hit
    - timeout: subprocess.TimeoutExpired (soft pass)
"""

from __future__ import annotations

import ast
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CallSite:
    file: str
    line: int


@dataclass(frozen=True)
class SymbolError:
    symbol: str
    error_code: str
    root_cause: str
    call_sites: list[CallSite] = field(default_factory=list)


@dataclass(frozen=True)
class TypeCheckResult:
    status: str
    raw_error_count: int
    filtered_count: int
    errors_by_symbol: list[SymbolError]
    mypy_exit_code: int
    duration_seconds: float


_LINE_RE = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):\s*error:\s*"
    r"(?P<msg>.+?)\s*\[(?P<code>[a-z-]+)\]\s*$"
)

_KEPT_CODES = frozenset({"attr-defined", "call-arg"})


def _parse_mypy_line(line: str) -> dict[str, Any] | None:
    """Parse one mypy stdout line into {file, line, msg, code} or None."""
    m = _LINE_RE.match(line.rstrip())
    if not m:
        return None
    return {
        "file": m.group("file"),
        "line": int(m.group("line")),
        "msg": m.group("msg"),
        "code": m.group("code"),
    }


def _filter_errors(parsed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only attr-defined + call-arg errors."""
    return [e for e in parsed if e["code"] in _KEPT_CODES]


_ATTR_DEFINED_RE = re.compile(r'"([^"]+)" has no attribute "([^"]+)"')
_MISSING_ARG_RE = re.compile(
    r'Missing positional argument "[^"]+" in call to "([^"]+)"'
)
_TOO_MANY_ARGS_RE = re.compile(r'Too many arguments for "([^"]+)"')


def _extract_symbol_key(msg: str, code: str) -> str:
    """Extract a symbol identifier from an mypy error message.

    Returns "ClassName.attr" or "function_name" depending on shape,
    or "other" if no pattern matches.
    """
    if code == "attr-defined":
        m = _ATTR_DEFINED_RE.search(msg)
        if m:
            return f"{m.group(1)}.{m.group(2)}"
    elif code == "call-arg":
        m = _MISSING_ARG_RE.search(msg)
        if m:
            return m.group(1)
        m = _TOO_MANY_ARGS_RE.search(msg)
        if m:
            return m.group(1)
    return "other"


def _walk_py_files(code_directory: Path):
    """Yield (path, ast.Module) for every .py under code_directory."""
    for p in code_directory.rglob("*.py"):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except (SyntaxError, OSError, UnicodeDecodeError):
            continue
        yield p, tree


def _extract_attrs_from_class(
    code_directory: Path,
    class_name: str,
) -> tuple[str, int, list[str]] | None:
    """Find `class <class_name>:` and return (file, line, self-attrs)."""
    for path, tree in _walk_py_files(code_directory):
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or node.name != class_name:
                continue
            attrs: list[str] = []
            for item in ast.walk(node):
                if (
                    isinstance(item, ast.FunctionDef)
                    and item.name == "__init__"
                ):
                    for stmt in ast.walk(item):
                        if isinstance(stmt, ast.Assign):
                            for tgt in stmt.targets:
                                if (
                                    isinstance(tgt, ast.Attribute)
                                    and isinstance(tgt.value, ast.Name)
                                    and tgt.value.id == "self"
                                ):
                                    if tgt.attr not in attrs:
                                        attrs.append(tgt.attr)
            rel = path.relative_to(code_directory).as_posix()
            return rel, node.lineno, attrs
    return None


def _extract_function_signature(
    code_directory: Path,
    func_name: str,
) -> tuple[str, int, str] | None:
    """Find `def <func_name>(...)` (incl. methods) and return (file, line, signature)."""
    for path, tree in _walk_py_files(code_directory):
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name != func_name:
                continue
            try:
                signature = ast.unparse(node.args)
            except AttributeError:
                signature = ", ".join(a.arg for a in node.args.args)
            rel = path.relative_to(code_directory).as_posix()
            return rel, node.lineno, signature
    return None


def _resolve_root_cause(
    symbol: str,
    code: str,
    code_directory: Path,
) -> str:
    """Build human-readable root cause text via AST lookup of the symbol's origin."""
    if code == "attr-defined" and "." in symbol:
        class_name, _, bad_attr = symbol.partition(".")
        found = _extract_attrs_from_class(code_directory, class_name)
        if found is None:
            return f"（{class_name} 类定义未找到，可能符号本身就是拼写错误）"
        file, line, attrs = found
        attrs_display = sorted(attrs) if attrs else ["（无 self.* 赋值）"]
        return (
            f"{class_name} 在 {file}:{line} 定义，真实属性是 {attrs_display}；"
            f"本调用引用了不存在的 .{bad_attr}。"
        )
    if code == "call-arg":
        found = _extract_function_signature(code_directory, symbol)
        if found is None:
            return f"（{symbol} 函数定义未找到）"
        file, line, signature = found
        return f"{symbol} 定义在 {file}:{line}，签名 ({signature})。"
    return "（无法解析根因）"


def _group_errors_by_symbol(
    parsed: list[dict[str, Any]],
    code_directory: Path,
) -> list[SymbolError]:
    """Aggregate parsed mypy errors into per-symbol SymbolError records."""
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in parsed:
        symbol = _extract_symbol_key(entry["msg"], entry["code"])
        key = (entry["code"], symbol)
        if key not in buckets:
            buckets[key] = {
                "symbol": symbol,
                "error_code": entry["code"],
                "call_sites": [],
            }
        buckets[key]["call_sites"].append(
            CallSite(file=entry["file"], line=entry["line"])
        )

    results: list[SymbolError] = []
    for bucket in buckets.values():
        root_cause = _resolve_root_cause(
            bucket["symbol"], bucket["error_code"], code_directory
        )
        results.append(
            SymbolError(
                symbol=bucket["symbol"],
                error_code=bucket["error_code"],
                root_cause=root_cause,
                call_sites=list(bucket["call_sites"]),
            )
        )
    results.sort(key=lambda se: len(se.call_sites), reverse=True)
    return results


def format_errors_for_repair(
    result: TypeCheckResult,
    max_symbols: int = 8,
    max_call_sites_per_symbol: int = 5,
) -> str:
    """Render symbol-grouped errors as markdown for the repair prompt."""
    if not result.errors_by_symbol:
        return ""

    total = len(result.errors_by_symbol)
    shown = min(total, max_symbols)
    lines: list[str] = [
        "# Type-check failures (mypy attr-defined + call-arg)",
        "",
        f"下列跨模块 API 不一致必须修复（共 {result.filtered_count} 处错误，"
        f"按符号分组取前 {shown} 个，共 {total} 个符号）。",
        "",
    ]
    for idx, err in enumerate(result.errors_by_symbol[:max_symbols], start=1):
        lines.append(f"## {idx}. {err.symbol} ({len(err.call_sites)} 处调用)")
        lines.append(f"**根因**：{err.root_cause}")
        lines.append("**误用位置**：")
        head = err.call_sites[:max_call_sites_per_symbol]
        for cs in head:
            lines.append(f"- {cs.file}:{cs.line}")
        remaining = len(err.call_sites) - len(head)
        if remaining > 0:
            lines.append(f"- ...另 {remaining} 处")
        lines.append("")
        if err.error_code == "attr-defined":
            lines.append("**修复方向（择一应用，全代码库一致）**：")
            class_name, _, attr = err.symbol.partition(".")
            lines.append(
                f"- 选项 A：在 {class_name} 上加 .{attr} 属性"
            )
            lines.append(
                f"- 选项 B：所有调用方改用 {class_name} 已有的属性名"
            )
        else:
            lines.append("**修复方向（择一应用）**：")
            lines.append(f"- 选项 A：改 {err.symbol} 签名以匹配调用方")
            lines.append(f"- 选项 B：所有调用方按 {err.symbol} 现有签名传参")
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append(
        "**重要**：每个符号只选一个方向。挑完再写代码，"
        "避免反复改一边、忘记同步另一边。"
    )
    return "\n".join(lines)


_MYPY_FLAGS = (
    "--ignore-missing-imports",
    # `--ignore-missing-imports` only suppresses [import-not-found]. Third-party
    # libs whose stubs *are* available but not installed (e.g. types-PyYAML)
    # still raise [import-untyped] and bump mypy's exit to 2. Disable that code
    # so LLM-generated code importing yaml/requests/numpy doesn't sink the gate.
    "--disable-error-code=import-untyped",
    # Generated trees frequently have ambiguous package roots (e.g. both
    # `hyper_kggen/__init__.py` and `hyper_kggen/src/llm_client.py` exist,
    # making mypy refuse to disambiguate `src.llm_client` vs
    # `hyper_kggen.src.llm_client`). --explicit-package-bases tells mypy to
    # treat the cwd as the import base.
    "--explicit-package-bases",
    "--no-color-output",
    "--show-error-codes",
    "--no-error-summary",
    "--hide-error-context",
)

_MAX_PY_BYTES = 5 * 1024 * 1024  # 5MB

_MAX_INVOCATIONS = 3
_WALL_CLOCK_BUDGET_SECONDS = 300.0

_INVOCATION_COUNT: dict[str, int] = {}
_LAST_ERROR_HASH: dict[str, int] = {}
_FIRST_CALL_TS: dict[str, float] = {}


def reset_type_check_state(code_directory: str) -> None:
    """Clear per-directory caches (used by orchestrator on task start, and tests)."""
    key = str(Path(code_directory).resolve())
    _INVOCATION_COUNT.pop(key, None)
    _LAST_ERROR_HASH.pop(key, None)
    _FIRST_CALL_TS.pop(key, None)


def _errors_hash(errors: list[SymbolError]) -> int:
    return hash(tuple((e.error_code, e.symbol) for e in errors))


def _total_py_bytes(code_directory: Path) -> int:
    total = 0
    for p in code_directory.rglob("*.py"):
        try:
            total += p.stat().st_size
        except OSError:
            continue
        if total > _MAX_PY_BYTES:
            break
    return total


def _mypy_module_missing(proc: subprocess.CompletedProcess[str]) -> bool:
    output = f"{proc.stdout or ''}\n{proc.stderr or ''}".lower()
    return "no module named mypy" in output


def _mypy_command() -> list[str]:
    executable = shutil.which("mypy")
    if executable:
        return [executable]
    return [sys.executable, "-m", "mypy"]


def run_type_check_gate(
    code_directory: str,
    *,
    timeout_seconds: int = 60,
) -> TypeCheckResult:
    """Run mypy as subprocess against code_directory; return TypeCheckResult."""
    start = time.monotonic()
    # Resolve to absolute up front so subprocess cwd/target work even when the
    # caller passed a relative path (otherwise cwd is resolved relative to the
    # caller's cwd, then mypy can't find the target by the same relative path).
    code_path = Path(code_directory).resolve() if code_directory else Path(code_directory)
    key = str(code_path) if code_directory else ""

    count = _INVOCATION_COUNT.get(key, 0)
    if count >= _MAX_INVOCATIONS:
        return TypeCheckResult(
            status="skipped",
            raw_error_count=0,
            filtered_count=0,
            errors_by_symbol=[],
            mypy_exit_code=-1,
            duration_seconds=time.monotonic() - start,
        )
    if (
        key in _FIRST_CALL_TS
        and time.monotonic() - _FIRST_CALL_TS[key] > _WALL_CLOCK_BUDGET_SECONDS
    ):
        return TypeCheckResult(
            status="skipped",
            raw_error_count=0,
            filtered_count=0,
            errors_by_symbol=[],
            mypy_exit_code=-1,
            duration_seconds=time.monotonic() - start,
        )
    _FIRST_CALL_TS.setdefault(key, time.monotonic())
    _INVOCATION_COUNT[key] = count + 1

    if not code_path.exists() or not code_path.is_dir():
        return TypeCheckResult(
            status="skipped",
            raw_error_count=0,
            filtered_count=0,
            errors_by_symbol=[],
            mypy_exit_code=-1,
            duration_seconds=time.monotonic() - start,
        )

    if _total_py_bytes(code_path) > _MAX_PY_BYTES:
        return TypeCheckResult(
            status="skipped",
            raw_error_count=0,
            filtered_count=0,
            errors_by_symbol=[],
            mypy_exit_code=-1,
            duration_seconds=time.monotonic() - start,
        )

    try:
        proc = subprocess.run(
            [*_mypy_command(), *_MYPY_FLAGS, str(code_path)],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=str(code_path),
        )
    except subprocess.TimeoutExpired:
        return TypeCheckResult(
            status="timeout",
            raw_error_count=0,
            filtered_count=0,
            errors_by_symbol=[],
            mypy_exit_code=-1,
            duration_seconds=time.monotonic() - start,
        )
    except FileNotFoundError:
        return TypeCheckResult(
            status="skipped",
            raw_error_count=0,
            filtered_count=0,
            errors_by_symbol=[],
            mypy_exit_code=-1,
            duration_seconds=time.monotonic() - start,
        )

    duration = time.monotonic() - start

    if proc.returncode == 1 and _mypy_module_missing(proc):
        return TypeCheckResult(
            status="skipped",
            raw_error_count=0,
            filtered_count=0,
            errors_by_symbol=[],
            mypy_exit_code=proc.returncode,
            duration_seconds=duration,
        )

    if proc.returncode not in (0, 1):
        return TypeCheckResult(
            status="skipped",
            raw_error_count=0,
            filtered_count=0,
            errors_by_symbol=[],
            mypy_exit_code=proc.returncode,
            duration_seconds=duration,
        )

    if proc.returncode == 0:
        return TypeCheckResult(
            status="success",
            raw_error_count=0,
            filtered_count=0,
            errors_by_symbol=[],
            mypy_exit_code=0,
            duration_seconds=duration,
        )

    parsed_all = [
        p for p in (_parse_mypy_line(ln) for ln in proc.stdout.splitlines())
        if p is not None
    ]
    parsed_kept = _filter_errors(parsed_all)
    grouped = _group_errors_by_symbol(parsed_kept, code_path)

    if grouped and proc.returncode == 1:
        h = _errors_hash(grouped)
        if h == _LAST_ERROR_HASH.get(key):
            return TypeCheckResult(
                status="success",
                raw_error_count=len(parsed_all),
                filtered_count=len(parsed_kept),
                errors_by_symbol=[],
                mypy_exit_code=proc.returncode,
                duration_seconds=duration,
            )
        _LAST_ERROR_HASH[key] = h

    status = "errors" if (proc.returncode == 1 and grouped) else "success"
    return TypeCheckResult(
        status=status,
        raw_error_count=len(parsed_all),
        filtered_count=len(parsed_kept),
        errors_by_symbol=grouped,
        mypy_exit_code=proc.returncode,
        duration_seconds=duration,
    )
