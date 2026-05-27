# mypy Integration as Type-Check Gate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Plug mypy into the code generation pipeline as a soft, repair-driving signal that catches cross-module API mismatches the smoke and reproduction gates miss.

**Architecture:** New `workflows/type_check_gate.py` module that subprocess-invokes mypy, parses output, groups errors by symbol with AST-derived root cause, and feeds them into the existing repair loop via `build_repair_prompt`. Module-level state caches per-`code_directory` counters and hashes for safety gating. The gate does **not** change task `final_status` — it only attaches `quality_result["type_check_gate"]`.

**Tech Stack:** Python 3.11, mypy 1.x, stdlib `subprocess` + `ast`, pytest.

**Spec:** `docs/superpowers/specs/2026-05-23-mypy-integration-design.md`

---

## File Structure

**Create:**
- `workflows/type_check_gate.py` — main module (~300 lines)
- `tests/test_type_check_gate.py` — unit + heavy integration tests

**Modify:**
- `requirements.txt` — add `mypy>=1.0`
- `workflows/repair_planner.py:build_repair_prompt` — append type_check_gate section
- `workflows/agent_orchestration_engine.py` — two wire-up sites (~lines 2280, 2376) + new helper near `_quality_with_reproduction_gate` (~line 559)
- `tests/test_repair_planner.py` — add type_check_gate cases

---

### Task 1: Scaffold module + dependency

**Files:**
- Modify: `requirements.txt`
- Create: `workflows/type_check_gate.py`
- Create: `tests/test_type_check_gate.py`

- [ ] **Step 1: Add mypy to requirements**

Append to `requirements.txt`:
```
mypy>=1.0
```

- [ ] **Step 2: Confirm dep installs**

Run: `pip install -r requirements.txt 2>&1 | tail -3`
Expected: `mypy` listed as already-satisfied or newly-installed; no errors.

- [ ] **Step 3: Create module stub**

Create `workflows/type_check_gate.py`:
```python
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
```

- [ ] **Step 4: Create empty test file**

Create `tests/test_type_check_gate.py`:
```python
"""Tests for workflows.type_check_gate."""
```

- [ ] **Step 5: Commit**

```bash
git add requirements.txt workflows/type_check_gate.py tests/test_type_check_gate.py
git commit -m "feat: scaffold type_check_gate module and add mypy dep"
```

---

### Task 2: Dataclasses (CallSite, SymbolError, TypeCheckResult)

**Files:**
- Modify: `workflows/type_check_gate.py`
- Modify: `tests/test_type_check_gate.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_type_check_gate.py`:
```python
import dataclasses

from workflows.type_check_gate import CallSite, SymbolError, TypeCheckResult


def test_callsite_is_frozen_dataclass_with_file_and_line():
    cs = CallSite(file="x.py", line=10)
    assert cs.file == "x.py"
    assert cs.line == 10
    assert dataclasses.is_dataclass(CallSite)
    with __import__("pytest").raises(dataclasses.FrozenInstanceError):
        cs.file = "y.py"  # type: ignore[misc]


def test_symbol_error_holds_symbol_code_root_cause_and_callsites():
    se = SymbolError(
        symbol="Node.id",
        error_code="attr-defined",
        root_cause="defined in foo.py:1",
        call_sites=[CallSite(file="bar.py", line=2)],
    )
    assert se.symbol == "Node.id"
    assert se.error_code == "attr-defined"
    assert se.root_cause == "defined in foo.py:1"
    assert se.call_sites[0].line == 2


def test_type_check_result_holds_status_counts_errors_exit_duration():
    result = TypeCheckResult(
        status="success",
        raw_error_count=0,
        filtered_count=0,
        errors_by_symbol=[],
        mypy_exit_code=0,
        duration_seconds=0.5,
    )
    assert result.status == "success"
    assert result.duration_seconds == 0.5
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_type_check_gate.py -v`
Expected: FAIL with `ImportError: cannot import name 'CallSite'` (or similar).

- [ ] **Step 3: Implement dataclasses**

Append to `workflows/type_check_gate.py`:
```python
from dataclasses import dataclass, field


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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_type_check_gate.py -v`
Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add workflows/type_check_gate.py tests/test_type_check_gate.py
git commit -m "feat: add type_check_gate dataclasses (CallSite, SymbolError, TypeCheckResult)"
```

---

### Task 3: Parse + filter mypy error lines

**Files:**
- Modify: `workflows/type_check_gate.py`
- Modify: `tests/test_type_check_gate.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_type_check_gate.py`:
```python
from workflows.type_check_gate import _filter_errors, _parse_mypy_line


def test_parse_attr_defined_line():
    line = (
        'hyper_kggen/core/hyperedge_extractor.py:69: error: '
        '"Node" has no attribute "node_id"  [attr-defined]'
    )
    parsed = _parse_mypy_line(line)
    assert parsed is not None
    assert parsed["file"] == "hyper_kggen/core/hyperedge_extractor.py"
    assert parsed["line"] == 69
    assert parsed["code"] == "attr-defined"
    assert parsed["msg"] == '"Node" has no attribute "node_id"'


def test_parse_call_arg_line():
    line = (
        'foo.py:107: error: Argument 1 to "add_hyperedge" of "Hypergraph" has '
        'incompatible type "Hyperedge"; expected "str"  [arg-type]'
    )
    parsed = _parse_mypy_line(line)
    assert parsed is not None
    assert parsed["file"] == "foo.py"
    assert parsed["line"] == 107
    assert parsed["code"] == "arg-type"


def test_parse_skips_non_error_lines():
    assert _parse_mypy_line("Found 12 errors in 3 files (checked 1 source file)") is None
    assert _parse_mypy_line("") is None
    assert _parse_mypy_line("foo.py:1: note: a hint") is None


def test_filter_keeps_only_attr_defined_and_call_arg():
    parsed = [
        {"file": "a.py", "line": 1, "msg": "m1", "code": "attr-defined"},
        {"file": "a.py", "line": 2, "msg": "m2", "code": "call-arg"},
        {"file": "a.py", "line": 3, "msg": "m3", "code": "arg-type"},
        {"file": "a.py", "line": 4, "msg": "m4", "code": "var-annotated"},
    ]
    kept = _filter_errors(parsed)
    assert len(kept) == 2
    assert {e["code"] for e in kept} == {"attr-defined", "call-arg"}
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_type_check_gate.py -v -k "parse or filter"`
Expected: 4 FAIL with ImportError.

- [ ] **Step 3: Implement parser and filter**

Append to `workflows/type_check_gate.py`:
```python
import re
from typing import Any

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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_type_check_gate.py -v`
Expected: 7 PASSED.

- [ ] **Step 5: Commit**

```bash
git add workflows/type_check_gate.py tests/test_type_check_gate.py
git commit -m "feat: add _parse_mypy_line and _filter_errors helpers"
```

---

### Task 4: Extract symbol key from message

**Files:**
- Modify: `workflows/type_check_gate.py`
- Modify: `tests/test_type_check_gate.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_type_check_gate.py`:
```python
from workflows.type_check_gate import _extract_symbol_key


def test_symbol_key_attr_defined_uses_class_dot_attr():
    msg = '"Node" has no attribute "node_id"'
    assert _extract_symbol_key(msg, "attr-defined") == "Node.node_id"


def test_symbol_key_missing_positional_arg_uses_callee_name():
    msg = 'Missing positional argument "node_ids" in call to "add_hyperedge"'
    assert _extract_symbol_key(msg, "call-arg") == "add_hyperedge"


def test_symbol_key_too_many_arguments_uses_callee_name():
    msg = 'Too many arguments for "merge_nodes"'
    assert _extract_symbol_key(msg, "call-arg") == "merge_nodes"


def test_symbol_key_unmatched_returns_other_bucket():
    assert _extract_symbol_key("something else entirely", "attr-defined") == "other"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_type_check_gate.py -v -k symbol_key`
Expected: 4 FAIL with ImportError.

- [ ] **Step 3: Implement symbol extractor**

Append to `workflows/type_check_gate.py`:
```python
_ATTR_DEFINED_RE = re.compile(r'"([^"]+)" has no attribute "([^"]+)"')
_MISSING_ARG_RE = re.compile(
    r'Missing positional argument "[^"]+" in call to "([^"]+)"'
)
_TOO_MANY_ARGS_RE = re.compile(r'Too many arguments for "([^"]+)"')


def _extract_symbol_key(msg: str, code: str) -> str:
    """Extract a symbol identifier from an mypy error message.

    Returns "ClassName.attr" or "function_name" depending on shape,
    or "other" if no pattern matches (downstream groups these together).
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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_type_check_gate.py -v`
Expected: 11 PASSED.

- [ ] **Step 5: Commit**

```bash
git add workflows/type_check_gate.py tests/test_type_check_gate.py
git commit -m "feat: add _extract_symbol_key for attr-defined and call-arg messages"
```

---

### Task 5: AST root-cause helpers

**Files:**
- Modify: `workflows/type_check_gate.py`
- Modify: `tests/test_type_check_gate.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_type_check_gate.py`:
```python
from pathlib import Path

from workflows.type_check_gate import (
    _extract_attrs_from_class,
    _extract_function_signature,
    _resolve_root_cause,
)


def test_extract_attrs_from_class_finds_self_assignments_in_init(tmp_path: Path):
    f = tmp_path / "mod.py"
    f.write_text(
        "class Node:\n"
        "    def __init__(self, node_id, name):\n"
        "        self.id = node_id\n"
        "        self.name = name\n"
        "        self.type = 'Entity'\n",
        encoding="utf-8",
    )
    found = _extract_attrs_from_class(tmp_path, "Node")
    assert found is not None
    file, line, attrs = found
    assert Path(file).name == "mod.py"
    assert line == 1
    assert attrs == ["id", "name", "type"]


def test_extract_function_signature_finds_def_in_class(tmp_path: Path):
    f = tmp_path / "mod.py"
    f.write_text(
        "class Hypergraph:\n"
        "    def add_hyperedge(self, relation_type, node_ids, description=''):\n"
        "        pass\n",
        encoding="utf-8",
    )
    found = _extract_function_signature(tmp_path, "add_hyperedge")
    assert found is not None
    file, line, signature = found
    assert Path(file).name == "mod.py"
    assert line == 2
    assert "relation_type" in signature
    assert "node_ids" in signature
    assert "description" in signature


def test_resolve_root_cause_attr_defined_uses_class_definition(tmp_path: Path):
    (tmp_path / "mod.py").write_text(
        "class Node:\n"
        "    def __init__(self, node_id):\n"
        "        self.id = node_id\n",
        encoding="utf-8",
    )
    cause = _resolve_root_cause("Node.node_id", "attr-defined", tmp_path)
    assert "Node" in cause
    assert "mod.py:1" in cause
    assert "id" in cause  # real attr listed
    assert "node_id" in cause  # error attr mentioned


def test_resolve_root_cause_call_arg_uses_function_signature(tmp_path: Path):
    (tmp_path / "mod.py").write_text(
        "def add_hyperedge(relation_type, node_ids):\n"
        "    pass\n",
        encoding="utf-8",
    )
    cause = _resolve_root_cause("add_hyperedge", "call-arg", tmp_path)
    assert "add_hyperedge" in cause
    assert "mod.py:1" in cause
    assert "relation_type" in cause


def test_resolve_root_cause_returns_placeholder_when_not_found(tmp_path: Path):
    cause = _resolve_root_cause("Bogus.missing", "attr-defined", tmp_path)
    assert cause  # non-empty
    assert "未找到" in cause or "not found" in cause.lower()
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_type_check_gate.py -v -k "extract or resolve_root"`
Expected: 5 FAIL with ImportError.

- [ ] **Step 3: Implement AST helpers**

Append to `workflows/type_check_gate.py`:
```python
import ast
from pathlib import Path


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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_type_check_gate.py -v`
Expected: 16 PASSED.

- [ ] **Step 5: Commit**

```bash
git add workflows/type_check_gate.py tests/test_type_check_gate.py
git commit -m "feat: add AST-based root-cause helpers for type_check_gate"
```

---

### Task 6: Group errors by symbol

**Files:**
- Modify: `workflows/type_check_gate.py`
- Modify: `tests/test_type_check_gate.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_type_check_gate.py`:
```python
from workflows.type_check_gate import _group_errors_by_symbol


def test_group_aggregates_call_sites_under_same_symbol(tmp_path: Path):
    (tmp_path / "h.py").write_text(
        "class Node:\n    def __init__(self):\n        self.id = 1\n",
        encoding="utf-8",
    )
    parsed = [
        {"file": "a.py", "line": 10, "msg": '"Node" has no attribute "node_id"',
         "code": "attr-defined"},
        {"file": "b.py", "line": 22, "msg": '"Node" has no attribute "node_id"',
         "code": "attr-defined"},
    ]
    grouped = _group_errors_by_symbol(parsed, tmp_path)
    assert len(grouped) == 1
    se = grouped[0]
    assert se.symbol == "Node.node_id"
    assert se.error_code == "attr-defined"
    assert len(se.call_sites) == 2
    files = sorted(cs.file for cs in se.call_sites)
    assert files == ["a.py", "b.py"]


def test_group_sorted_by_call_count_descending(tmp_path: Path):
    parsed = [
        {"file": "a.py", "line": 1, "msg": '"X" has no attribute "y"',
         "code": "attr-defined"},
        {"file": "b.py", "line": 2, "msg": '"P" has no attribute "q"',
         "code": "attr-defined"},
        {"file": "c.py", "line": 3, "msg": '"P" has no attribute "q"',
         "code": "attr-defined"},
        {"file": "d.py", "line": 4, "msg": '"P" has no attribute "q"',
         "code": "attr-defined"},
    ]
    grouped = _group_errors_by_symbol(parsed, tmp_path)
    assert [g.symbol for g in grouped] == ["P.q", "X.y"]
    assert len(grouped[0].call_sites) == 3
    assert len(grouped[1].call_sites) == 1
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_type_check_gate.py -v -k group`
Expected: 2 FAIL with ImportError.

- [ ] **Step 3: Implement grouping**

Append to `workflows/type_check_gate.py`:
```python
def _group_errors_by_symbol(
    parsed: list[dict[str, Any]],
    code_directory: Path,
) -> list[SymbolError]:
    """Aggregate parsed mypy errors into per-symbol SymbolError records."""
    buckets: dict[str, dict[str, Any]] = {}
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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_type_check_gate.py -v`
Expected: 18 PASSED.

- [ ] **Step 5: Commit**

```bash
git add workflows/type_check_gate.py tests/test_type_check_gate.py
git commit -m "feat: add _group_errors_by_symbol with root-cause resolution"
```

---

### Task 7: Render repair prompt

**Files:**
- Modify: `workflows/type_check_gate.py`
- Modify: `tests/test_type_check_gate.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_type_check_gate.py`:
```python
from workflows.type_check_gate import format_errors_for_repair


def _make_symbol_error(symbol="X.y", n_sites=1, code="attr-defined"):
    return SymbolError(
        symbol=symbol,
        error_code=code,
        root_cause=f"{symbol} root cause",
        call_sites=[CallSite(f"f{i}.py", i) for i in range(n_sites)],
    )


def test_format_returns_empty_when_no_errors():
    result = TypeCheckResult(
        status="success",
        raw_error_count=0,
        filtered_count=0,
        errors_by_symbol=[],
        mypy_exit_code=0,
        duration_seconds=0.1,
    )
    out = format_errors_for_repair(result)
    assert out == ""


def test_format_caps_to_max_symbols():
    errors = [_make_symbol_error(symbol=f"S{i}.a", n_sites=2) for i in range(12)]
    result = TypeCheckResult(
        status="errors",
        raw_error_count=24,
        filtered_count=24,
        errors_by_symbol=errors,
        mypy_exit_code=1,
        duration_seconds=0.1,
    )
    out = format_errors_for_repair(result, max_symbols=8)
    # 8 sections rendered; symbols 9..12 omitted
    assert "S0.a" in out
    assert "S7.a" in out
    assert "S8.a" not in out
    assert "前 8" in out


def test_format_truncates_long_call_sites_with_more_marker():
    err = _make_symbol_error(symbol="X.y", n_sites=8)
    result = TypeCheckResult(
        status="errors",
        raw_error_count=8,
        filtered_count=8,
        errors_by_symbol=[err],
        mypy_exit_code=1,
        duration_seconds=0.1,
    )
    out = format_errors_for_repair(result, max_call_sites_per_symbol=5)
    # First 5 shown, "...另 3 处" tail line for the remaining 3
    assert "f0.py:0" in out
    assert "f4.py:4" in out
    assert "f5.py:5" not in out
    assert "另 3 处" in out


def test_format_includes_root_cause_text():
    err = _make_symbol_error()
    err = dataclasses.replace(err, root_cause="custom-root-cause-marker")
    result = TypeCheckResult(
        status="errors",
        raw_error_count=1,
        filtered_count=1,
        errors_by_symbol=[err],
        mypy_exit_code=1,
        duration_seconds=0.1,
    )
    out = format_errors_for_repair(result)
    assert "custom-root-cause-marker" in out
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_type_check_gate.py -v -k format`
Expected: 4 FAIL with ImportError.

- [ ] **Step 3: Implement format_errors_for_repair**

Append to `workflows/type_check_gate.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_type_check_gate.py -v`
Expected: 22 PASSED.

- [ ] **Step 5: Commit**

```bash
git add workflows/type_check_gate.py tests/test_type_check_gate.py
git commit -m "feat: add format_errors_for_repair markdown renderer"
```

---

### Task 8: Run gate on clean project (subprocess success path)

**Files:**
- Modify: `workflows/type_check_gate.py`
- Modify: `tests/test_type_check_gate.py`

- [ ] **Step 1: Write failing heavy integration test**

Append to `tests/test_type_check_gate.py`:
```python
import pytest

from workflows.type_check_gate import run_type_check_gate


@pytest.mark.heavy
def test_run_gate_returns_success_on_clean_project(tmp_path: Path):
    pkg = tmp_path / "cleanpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "a.py").write_text(
        "def add(x: int, y: int) -> int:\n    return x + y\n",
        encoding="utf-8",
    )
    result = run_type_check_gate(str(tmp_path))
    assert result.status == "success"
    assert result.filtered_count == 0
    assert result.errors_by_symbol == []
    assert result.mypy_exit_code == 0
    assert result.duration_seconds > 0
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_type_check_gate.py -v -k clean_project -m heavy`
Expected: FAIL with `ImportError: cannot import name 'run_type_check_gate'`.

- [ ] **Step 3: Implement subprocess wrapper (clean path only)**

Append to `workflows/type_check_gate.py`:
```python
import subprocess
import sys
import time

_MYPY_FLAGS = (
    "--ignore-missing-imports",
    "--no-color-output",
    "--show-error-codes",
    "--no-error-summary",
    "--hide-error-context",
)


def run_type_check_gate(
    code_directory: str,
    *,
    timeout_seconds: int = 60,
) -> TypeCheckResult:
    """Run mypy as subprocess against code_directory; return TypeCheckResult."""
    start = time.monotonic()
    code_path = Path(code_directory)

    if not code_path.exists() or not code_path.is_dir():
        return TypeCheckResult(
            status="skipped",
            raw_error_count=0,
            filtered_count=0,
            errors_by_symbol=[],
            mypy_exit_code=-1,
            duration_seconds=time.monotonic() - start,
        )

    proc = subprocess.run(
        [sys.executable, "-m", "mypy", *_MYPY_FLAGS, str(code_path)],
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        cwd=str(code_path),
    )
    duration = time.monotonic() - start

    if proc.returncode == 0:
        return TypeCheckResult(
            status="success",
            raw_error_count=0,
            filtered_count=0,
            errors_by_symbol=[],
            mypy_exit_code=0,
            duration_seconds=duration,
        )

    # Errors will be implemented in Task 9.
    raise NotImplementedError("non-zero exit handling lands in Task 9")
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/test_type_check_gate.py -v -k clean_project -m heavy`
Expected: PASS.

- [ ] **Step 5: Verify non-heavy tests still pass**

Run: `pytest tests/test_type_check_gate.py -v -m "not heavy"`
Expected: 22 PASSED (the earlier ones).

- [ ] **Step 6: Commit**

```bash
git add workflows/type_check_gate.py tests/test_type_check_gate.py
git commit -m "feat: run_type_check_gate handles clean project (exit 0) path"
```

---

### Task 9: Errors detected, parsed, grouped

**Files:**
- Modify: `workflows/type_check_gate.py`
- Modify: `tests/test_type_check_gate.py`

- [ ] **Step 1: Write failing heavy integration test**

Append to `tests/test_type_check_gate.py`:
```python
@pytest.mark.heavy
def test_run_gate_detects_attr_defined_bug(tmp_path: Path):
    pkg = tmp_path / "buggy"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "model.py").write_text(
        "class Node:\n"
        "    def __init__(self, node_id):\n"
        "        self.id = node_id\n",
        encoding="utf-8",
    )
    (pkg / "user.py").write_text(
        "from buggy.model import Node\n"
        "def get_id(n: Node) -> str:\n"
        "    return n.node_id\n",
        encoding="utf-8",
    )

    result = run_type_check_gate(str(tmp_path))
    assert result.status == "errors"
    assert result.filtered_count >= 1
    symbols = {e.symbol for e in result.errors_by_symbol}
    assert "Node.node_id" in symbols
    se = next(e for e in result.errors_by_symbol if e.symbol == "Node.node_id")
    assert "model.py" in se.root_cause
    assert any(cs.file.endswith("user.py") for cs in se.call_sites)


@pytest.mark.heavy
def test_run_gate_detects_call_arg_bug(tmp_path: Path):
    pkg = tmp_path / "callbug"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "api.py").write_text(
        "def add_edge(relation_type: str, node_ids: list[str]) -> None:\n"
        "    pass\n",
        encoding="utf-8",
    )
    (pkg / "caller.py").write_text(
        "from callbug.api import add_edge\n"
        "def go() -> None:\n"
        "    add_edge('x')\n",  # missing node_ids
        encoding="utf-8",
    )
    result = run_type_check_gate(str(tmp_path))
    assert result.status == "errors"
    symbols = {e.symbol for e in result.errors_by_symbol}
    assert "add_edge" in symbols
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_type_check_gate.py -v -k "detects_attr or detects_call" -m heavy`
Expected: FAIL with `NotImplementedError: non-zero exit handling lands in Task 9`.

- [ ] **Step 3: Implement error path**

Replace the `raise NotImplementedError(...)` line in `run_type_check_gate` with the error-handling branch. The full updated function:

```python
def run_type_check_gate(
    code_directory: str,
    *,
    timeout_seconds: int = 60,
) -> TypeCheckResult:
    start = time.monotonic()
    code_path = Path(code_directory)

    if not code_path.exists() or not code_path.is_dir():
        return TypeCheckResult(
            status="skipped",
            raw_error_count=0,
            filtered_count=0,
            errors_by_symbol=[],
            mypy_exit_code=-1,
            duration_seconds=time.monotonic() - start,
        )

    proc = subprocess.run(
        [sys.executable, "-m", "mypy", *_MYPY_FLAGS, str(code_path)],
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        cwd=str(code_path),
    )
    duration = time.monotonic() - start

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
    status = "errors" if (proc.returncode == 1 and grouped) else "success"
    return TypeCheckResult(
        status=status,
        raw_error_count=len(parsed_all),
        filtered_count=len(parsed_kept),
        errors_by_symbol=grouped,
        mypy_exit_code=proc.returncode,
        duration_seconds=duration,
    )
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_type_check_gate.py -v -m heavy`
Expected: 3 PASSED.

- [ ] **Step 5: Verify all tests pass**

Run: `pytest tests/test_type_check_gate.py -v`
Expected: 25 PASSED.

- [ ] **Step 6: Commit**

```bash
git add workflows/type_check_gate.py tests/test_type_check_gate.py
git commit -m "feat: run_type_check_gate parses + groups mypy errors on exit 1"
```

---

### Task 10: Timeout / missing mypy / internal error

**Files:**
- Modify: `workflows/type_check_gate.py`
- Modify: `tests/test_type_check_gate.py`

- [ ] **Step 1: Write failing tests (with subprocess mocks)**

Append to `tests/test_type_check_gate.py`:
```python
from unittest.mock import patch


def test_run_gate_handles_timeout(tmp_path: Path):
    pkg = tmp_path / "x"
    pkg.mkdir()
    (pkg / "a.py").write_text("x = 1\n", encoding="utf-8")
    with patch(
        "workflows.type_check_gate.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd=["mypy"], timeout=60),
    ):
        result = run_type_check_gate(str(tmp_path), timeout_seconds=60)
    assert result.status == "timeout"
    assert result.filtered_count == 0
    assert result.errors_by_symbol == []


def test_run_gate_handles_missing_mypy(tmp_path: Path):
    pkg = tmp_path / "x"
    pkg.mkdir()
    (pkg / "a.py").write_text("x = 1\n", encoding="utf-8")
    with patch(
        "workflows.type_check_gate.subprocess.run",
        side_effect=FileNotFoundError("mypy not found"),
    ):
        result = run_type_check_gate(str(tmp_path))
    assert result.status == "skipped"
    assert result.mypy_exit_code == -1


def test_run_gate_handles_mypy_internal_error(tmp_path: Path):
    pkg = tmp_path / "x"
    pkg.mkdir()
    (pkg / "a.py").write_text("x = 1\n", encoding="utf-8")
    fake_proc = subprocess.CompletedProcess(
        args=["mypy"], returncode=2, stdout="", stderr="mypy internal explosion",
    )
    with patch(
        "workflows.type_check_gate.subprocess.run",
        return_value=fake_proc,
    ):
        result = run_type_check_gate(str(tmp_path))
    assert result.status == "skipped"
    assert result.mypy_exit_code == 2
```

Note: we need `subprocess` imported in the test file too — add `import subprocess` near the other imports if missing.

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_type_check_gate.py -v -k "timeout or missing_mypy or internal_error"`
Expected: 3 FAIL.

- [ ] **Step 3: Implement timeout + missing + exit-2 handling**

Update `run_type_check_gate` to wrap the subprocess call in try/except. Replace the existing `proc = subprocess.run(...)` block with:

```python
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "mypy", *_MYPY_FLAGS, str(code_path)],
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

    if proc.returncode not in (0, 1):
        return TypeCheckResult(
            status="skipped",
            raw_error_count=0,
            filtered_count=0,
            errors_by_symbol=[],
            mypy_exit_code=proc.returncode,
            duration_seconds=duration,
        )
```

(Keep the rest of the function unchanged — `if proc.returncode == 0:` then parse/group.)

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_type_check_gate.py -v -k "timeout or missing_mypy or internal_error"`
Expected: 3 PASSED.

- [ ] **Step 5: Verify all tests pass**

Run: `pytest tests/test_type_check_gate.py -v`
Expected: 28 PASSED.

- [ ] **Step 6: Commit**

```bash
git add workflows/type_check_gate.py tests/test_type_check_gate.py
git commit -m "feat: handle mypy timeout / missing / internal-error as skipped/timeout"
```

---

### Task 11: Oversized-codebase size guard

**Files:**
- Modify: `workflows/type_check_gate.py`
- Modify: `tests/test_type_check_gate.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_type_check_gate.py`:
```python
def test_run_gate_skips_when_code_dir_oversized(tmp_path: Path):
    pkg = tmp_path / "big"
    pkg.mkdir()
    # Write a single .py file > 5MB
    big_path = pkg / "huge.py"
    big_path.write_text("x = 0\n" * (1024 * 1024), encoding="utf-8")  # ~6MB
    result = run_type_check_gate(str(tmp_path))
    assert result.status == "skipped"
    assert result.mypy_exit_code == -1
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_type_check_gate.py -v -k oversized`
Expected: FAIL (the heavy mypy run on a 6MB file will succeed or err, but won't be "skipped").

- [ ] **Step 3: Implement size guard**

Add helper above `run_type_check_gate`:
```python
_MAX_PY_BYTES = 5 * 1024 * 1024  # 5MB


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
```

In `run_type_check_gate`, after the `if not code_path.exists()` early return, add:
```python
    if _total_py_bytes(code_path) > _MAX_PY_BYTES:
        return TypeCheckResult(
            status="skipped",
            raw_error_count=0,
            filtered_count=0,
            errors_by_symbol=[],
            mypy_exit_code=-1,
            duration_seconds=time.monotonic() - start,
        )
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/test_type_check_gate.py -v -k oversized`
Expected: PASS.

- [ ] **Step 5: Verify all tests pass**

Run: `pytest tests/test_type_check_gate.py -v`
Expected: 29 PASSED.

- [ ] **Step 6: Commit**

```bash
git add workflows/type_check_gate.py tests/test_type_check_gate.py
git commit -m "feat: skip type_check_gate when .py total size exceeds 5MB"
```

---

### Task 12: Module-level safety caps (3-call, 5-min wall-clock, same-error hash)

**Files:**
- Modify: `workflows/type_check_gate.py`
- Modify: `tests/test_type_check_gate.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_type_check_gate.py`:
```python
from workflows.type_check_gate import reset_type_check_state


def _make_buggy_project(tmp_path: Path) -> Path:
    pkg = tmp_path / "buggy"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "model.py").write_text(
        "class Node:\n"
        "    def __init__(self):\n"
        "        self.id = 1\n",
        encoding="utf-8",
    )
    (pkg / "user.py").write_text(
        "from buggy.model import Node\n"
        "def f(n: Node) -> int:\n"
        "    return n.node_id\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.mark.heavy
def test_invocation_cap_returns_skipped_after_three_calls(tmp_path: Path):
    reset_type_check_state(str(tmp_path))
    _make_buggy_project(tmp_path)
    r1 = run_type_check_gate(str(tmp_path))
    r2 = run_type_check_gate(str(tmp_path))
    r3 = run_type_check_gate(str(tmp_path))
    r4 = run_type_check_gate(str(tmp_path))
    assert r1.status in {"errors", "success"}
    assert r4.status == "skipped"
    reset_type_check_state(str(tmp_path))


@pytest.mark.heavy
def test_same_error_hash_circuit_breaker(tmp_path: Path):
    reset_type_check_state(str(tmp_path))
    _make_buggy_project(tmp_path)
    r1 = run_type_check_gate(str(tmp_path))
    assert r1.status == "errors"
    # Same code → same errors → second run hits hash circuit, returns "success"
    # (the spec describes this as "假装通过" so the outer repair loop breaks)
    r2 = run_type_check_gate(str(tmp_path))
    assert r2.status == "success"
    reset_type_check_state(str(tmp_path))


def test_wall_clock_cap_returns_skipped_after_budget(tmp_path: Path):
    reset_type_check_state(str(tmp_path))
    pkg = tmp_path / "x"
    pkg.mkdir()
    (pkg / "a.py").write_text("x = 1\n", encoding="utf-8")
    # Simulate that the first invocation already happened > 5 minutes ago.
    from workflows import type_check_gate as tcg
    key = str(Path(tmp_path).resolve())
    tcg._FIRST_CALL_TS[key] = tcg.time.monotonic() - 400.0
    result = run_type_check_gate(str(tmp_path))
    assert result.status == "skipped"
    reset_type_check_state(str(tmp_path))


def test_reset_type_check_state_clears_caches(tmp_path: Path):
    from workflows import type_check_gate as tcg
    key = str(Path(tmp_path).resolve())
    tcg._INVOCATION_COUNT[key] = 3
    tcg._LAST_ERROR_HASH[key] = 12345
    tcg._FIRST_CALL_TS[key] = 0.0
    reset_type_check_state(str(tmp_path))
    assert key not in tcg._INVOCATION_COUNT
    assert key not in tcg._LAST_ERROR_HASH
    assert key not in tcg._FIRST_CALL_TS
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_type_check_gate.py -v -k "invocation_cap or hash_circuit or wall_clock or reset_type_check"`
Expected: 4 FAIL (ImportError for reset_type_check_state and behavior not implemented).

- [ ] **Step 3: Implement module-level caches and safety logic**

Add near the top of `workflows/type_check_gate.py` (after imports):
```python
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
```

In `run_type_check_gate`, at the very top (after `start = time.monotonic()`), insert:
```python
    key = str(Path(code_directory).resolve())
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
```

In the final `return TypeCheckResult(status="errors", ...)` branch (Task 9), wrap the grouped result with the hash circuit breaker. Replace the existing return:

```python
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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_type_check_gate.py -v`
Expected: 33 PASSED (29 previous + 4 new).

- [ ] **Step 5: Commit**

```bash
git add workflows/type_check_gate.py tests/test_type_check_gate.py
git commit -m "feat: add module-level safety caps (3-call, 5-min wall-clock, same-error hash)"
```

---

### Task 13: Extend build_repair_prompt to include type_check_gate

**Files:**
- Modify: `workflows/repair_planner.py`
- Modify: `tests/test_repair_planner.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_repair_planner.py`:
```python
def test_build_repair_prompt_includes_type_check_section_on_errors():
    quality_result = {
        "failures": [],
        "type_check_gate": {
            "status": "errors",
            "raw_error_count": 5,
            "filtered_count": 3,
            "symbol_count": 1,
            "duration_seconds": 1.2,
            "rendered_prompt": (
                "# Type-check failures (mypy attr-defined + call-arg)\n"
                "\n"
                "## 1. Node.node_id (3 处调用)\n"
                "**根因**：Node 在 model.py:1 定义...\n"
            ),
        },
    }
    out = build_repair_prompt(quality_result)
    assert "Type-check failures" in out
    assert "Node.node_id" in out


def test_build_repair_prompt_omits_type_check_section_on_success():
    quality_result = {
        "failures": [],
        "type_check_gate": {
            "status": "success",
            "raw_error_count": 0,
            "filtered_count": 0,
            "symbol_count": 0,
            "duration_seconds": 0.5,
            "rendered_prompt": "",
        },
    }
    out = build_repair_prompt(quality_result)
    assert "Type-check failures" not in out


def test_build_repair_prompt_handles_missing_type_check_gate_field():
    """No regression: existing callers without the new field still work."""
    quality_result = {"failures": ["something"]}
    out = build_repair_prompt(quality_result)
    assert "Repair the generated code" in out
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_repair_planner.py -v -k "type_check_section or omits_type or handles_missing_type"`
Expected: 2 FAIL (test 1 + 2 fail on absent assertion; test 3 should already pass).

- [ ] **Step 3: Extend build_repair_prompt**

Modify `workflows/repair_planner.py:build_repair_prompt`. Just before the final `return "\n".join(lines)`, insert:
```python
    type_check_gate = quality_result.get("type_check_gate") or {}
    if (
        str(type_check_gate.get("status", "")).lower() == "errors"
        and type_check_gate.get("rendered_prompt")
    ):
        lines.append("")
        lines.append(type_check_gate["rendered_prompt"])
```

(The orchestrator will populate `rendered_prompt` from `format_errors_for_repair` — see Task 14.)

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_repair_planner.py -v`
Expected: all green (existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add workflows/repair_planner.py tests/test_repair_planner.py
git commit -m "feat: append type_check_gate.rendered_prompt to repair prompt"
```

---

### Task 14: Wire-up to agent_orchestration_engine

**Files:**
- Modify: `workflows/agent_orchestration_engine.py`

This task has no new unit tests — it's a wiring change that integration-tests via Task 15. Steps focus on correctness against existing repair tests.

- [ ] **Step 1: Import and helper**

In `workflows/agent_orchestration_engine.py`, near the other workflow imports (look for `from workflows.reproduction_gate import run_reproduction_gate` around line 72), add:
```python
from workflows.type_check_gate import (
    format_errors_for_repair as format_type_check_errors,
    reset_type_check_state,
    run_type_check_gate,
)
```

- [ ] **Step 2: Add _quality_with_type_check_gate helper**

Immediately after the existing `_quality_with_reproduction_gate` function (around line 559-573), add:
```python
def _quality_with_type_check_gate(
    quality_result: Dict[str, Any],
    type_check_result: Any,
) -> Dict[str, Any]:
    merged = dict(quality_result or {})
    rendered = format_type_check_errors(type_check_result)
    merged["type_check_gate"] = {
        "status": type_check_result.status,
        "raw_error_count": type_check_result.raw_error_count,
        "filtered_count": type_check_result.filtered_count,
        "symbol_count": len(type_check_result.errors_by_symbol),
        "duration_seconds": type_check_result.duration_seconds,
        "rendered_prompt": rendered,
    }
    # Intentionally do NOT modify merged["status"].
    return merged
```

- [ ] **Step 3: Wire into first repair loop (~line 2280-2290)**

Find the block beginning with the first `quality_result = _assess_generated_code_with_reproduction_gate(` call inside the repair loop (the comment context above it mentions repair attempts). Right **after** `quality_result = _assess_generated_code_with_reproduction_gate(...)`, **before** the `if quality_result.get("status") == "success": break` check, insert:
```python
            tc_result = run_type_check_gate(
                implementation_result.get("code_directory") or code_directory,
            )
            quality_result = _quality_with_type_check_gate(quality_result, tc_result)
```

(Use the same `code_directory` variable that's already in scope at that point in the function.)

- [ ] **Step 4: Wire into second repair loop (~line 2376-2410)**

Find the second `quality_result = _assess_generated_code_with_reproduction_gate(...)` call in the second repair loop (look for the comment header near 2376 or the second occurrence of `for repair_index in range(max_repair_attempts):`). Insert the same two-line wrapper block right after that assignment and before any `if quality_result.get("status") == "success": break`.

- [ ] **Step 5: Reset state at task start**

Find where the implementation workflow begins (right after `code_directory = os.path.join(target_directory, "generate_code")` line in `run_workflow` of `code_implementation_workflow.py`, **OR** earlier in `agent_orchestration_engine.py` where `code_directory` is first resolved for the task). Insert:
```python
            reset_type_check_state(code_directory)
```

This ensures invocation counter and hash from a previous task don't leak into the current task. Grep for the right insertion site:

Run: `grep -n 'code_directory = os.path.join' workflows/code_implementation_workflow.py workflows/agent_orchestration_engine.py`

Expected output names the line(s). Insert the `reset_type_check_state(code_directory)` call once, right after code_directory is first computed for the task.

- [ ] **Step 6: Run existing tests for regression**

Run: `pytest tests/test_repair_planner.py tests/test_pipeline_critique_wiring.py tests/test_routes_tasks.py -v 2>&1 | tail -20`
Expected: existing tests still pass; no new failures.

Run: `pytest tests/test_repair_fail_fast.py -v 2>&1 | tail -10`
Expected: still pass (we didn't touch the fail-fast helper).

- [ ] **Step 7: Quick syntax sanity**

Run: `python -c "from workflows import agent_orchestration_engine; from workflows.type_check_gate import run_type_check_gate, format_errors_for_repair, reset_type_check_state; print('ok')"`
Expected: prints `ok` with no import errors.

- [ ] **Step 8: Commit**

```bash
git add workflows/agent_orchestration_engine.py workflows/code_implementation_workflow.py
git commit -m "feat: wire type_check_gate into repair loop and reset state per task"
```

---

### Task 15: End-to-end manual verification on Run4 output

**Files:**
- No code changes; verification only.

- [ ] **Step 1: Run the gate against Run4 generated code**

Run:
```bash
python -c "
import json
from workflows.type_check_gate import run_type_check_gate, format_errors_for_repair, reset_type_check_state

code_dir = 'output/tasks/paper_20260523-0018_2602-19543v1_f9f1f860/generate_code'
reset_type_check_state(code_dir)
result = run_type_check_gate(code_dir)
print(f'status={result.status} raw={result.raw_error_count} filtered={result.filtered_count} symbols={len(result.errors_by_symbol)} duration={result.duration_seconds:.1f}s')
print('--- top 3 symbols ---')
for e in result.errors_by_symbol[:3]:
    print(f'{e.symbol}: {len(e.call_sites)} sites — {e.root_cause[:90]}')
"
```

Expected: `status=errors`; `filtered` ≥ 50 (matches the 56 we found manually); top symbols include `Node.node_id`, `add_hyperedge`, and `Hyperedge.edge_id` or similar.

- [ ] **Step 2: Render the repair prompt and eyeball it**

Run:
```bash
python -c "
from workflows.type_check_gate import run_type_check_gate, format_errors_for_repair, reset_type_check_state

code_dir = 'output/tasks/paper_20260523-0018_2602-19543v1_f9f1f860/generate_code'
reset_type_check_state(code_dir)
result = run_type_check_gate(code_dir)
print(format_errors_for_repair(result))
" | head -80
```

Expected: A markdown section with `## 1. Node.node_id (...)` block, root-cause referencing `hypergraph.py`, and the two-option repair direction.

- [ ] **Step 3: Confirm test suite still green**

Run: `pytest -m "not heavy" -q 2>&1 | tail -10`
Expected: all pass.

Run: `pytest tests/test_type_check_gate.py -v 2>&1 | tail -10`
Expected: 33 PASSED (28 non-heavy + 5 heavy).

- [ ] **Step 4: Document the baseline (no commit needed)**

Note in the task tracker / chat the observed numbers — e.g. "Run4 baseline: filtered_count=56, top symbols Node.node_id (3 sites), add_hyperedge (3 sites), Hyperedge.edge_id (...)". This becomes the comparison anchor for the next end-to-end pipeline run.

- [ ] **Step 5: Tag end of implementation**

```bash
git log --oneline -15
```

Expected: 14 new commits since the spec commit `b56b566`, one per task above.

---

## Spec coverage check (self-review)

| Spec section | Implemented by |
|---|---|
| API surface (CallSite, SymbolError, TypeCheckResult, run_type_check_gate, format_errors_for_repair) | Tasks 2, 7, 9 |
| mypy CLI flags + cwd | Task 8, 9 |
| Status semantics (success / errors / skipped / timeout) | Tasks 8, 9, 10, 11, 12 |
| Size guard (>5MB skipped) | Task 11 |
| Error line parsing | Task 3 |
| Filtering (attr-defined + call-arg only) | Task 3 |
| Symbol key extraction (3 patterns) | Task 4 |
| AST root-cause helpers | Task 5 |
| Symbol grouping + sort desc | Task 6 |
| format_errors_for_repair with caps | Task 7 |
| Subprocess timeout + missing mypy + internal-error | Task 10 |
| Module-level caches (3-call cap, 5-min, same-error hash) | Task 12 |
| reset_type_check_state | Task 12, 14 |
| build_repair_prompt extension | Task 13 |
| Two-site repair-loop wire-up | Task 14 |
| reset_type_check_state at task start | Task 14 |
| Does NOT change final_status | Task 14 (helper does not touch `merged["status"]`) |
| Acceptance: detects Node.node_id et al on Run4 | Task 15 |

All spec sections covered.
