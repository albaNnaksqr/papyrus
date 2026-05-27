"""Tests for workflows.type_check_gate."""

import dataclasses
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from workflows.type_check_gate import (
    CallSite,
    SymbolError,
    TypeCheckResult,
    _extract_attrs_from_class,
    _extract_function_signature,
    _extract_symbol_key,
    _filter_errors,
    _group_errors_by_symbol,
    _parse_mypy_line,
    _resolve_root_cause,
    format_errors_for_repair,
    reset_type_check_state,
    run_type_check_gate,
)


def test_callsite_is_frozen_dataclass_with_file_and_line():
    cs = CallSite(file="x.py", line=10)
    assert cs.file == "x.py"
    assert cs.line == 10
    assert dataclasses.is_dataclass(CallSite)
    with pytest.raises(dataclasses.FrozenInstanceError):
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
    assert "id" in cause
    assert "node_id" in cause


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
    assert cause
    assert "未找到" in cause or "not found" in cause.lower()


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
        "    add_edge('x')\n",
        encoding="utf-8",
    )
    result = run_type_check_gate(str(tmp_path))
    assert result.status == "errors"
    symbols = {e.symbol for e in result.errors_by_symbol}
    assert "add_edge" in symbols


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


def test_run_gate_handles_missing_mypy_module_returncode_1(tmp_path: Path):
    pkg = tmp_path / "x"
    pkg.mkdir()
    (pkg / "a.py").write_text("x = 1\n", encoding="utf-8")
    fake_proc = subprocess.CompletedProcess(
        args=["python", "-m", "mypy"],
        returncode=1,
        stdout="",
        stderr="/usr/bin/python3: No module named mypy\n",
    )
    with patch(
        "workflows.type_check_gate.subprocess.run",
        return_value=fake_proc,
    ):
        result = run_type_check_gate(str(tmp_path))
    assert result.status == "skipped"
    assert result.mypy_exit_code == 1


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


def test_run_gate_skips_when_code_dir_oversized(tmp_path: Path):
    pkg = tmp_path / "big"
    pkg.mkdir()
    big_path = pkg / "huge.py"
    big_path.write_text("x = 0\n" * (1024 * 1024), encoding="utf-8")  # ~6MB
    result = run_type_check_gate(str(tmp_path))
    assert result.status == "skipped"
    assert result.mypy_exit_code == -1


def _make_buggy_project(tmp_path: Path) -> Path:
    pkg = tmp_path / "buggycaps"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "model.py").write_text(
        "class Node:\n"
        "    def __init__(self):\n"
        "        self.id = 1\n",
        encoding="utf-8",
    )
    (pkg / "user.py").write_text(
        "from buggycaps.model import Node\n"
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
