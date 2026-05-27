from tools import code_implementation_server
from tools import command_executor


def test_code_implementation_server_blocks_pytest_commands():
    blocked = [
        "python -m pytest tests/ -v",
        "pytest tests/test_pipeline.py -q",
        "timeout 15 python -m pytest tests/test_pipeline.py -v 2>&1 | head -60",
        "cd generated && python -m pytest tests/ -v",
    ]

    for command in blocked:
        assert code_implementation_server._is_blocked_heavy_test_command(command)


def test_code_implementation_server_allows_lightweight_checks():
    allowed = [
        "python -m compileall -q .",
        "python - <<'PY'\nimport src.pipeline\nPY",
        "ls tests",
    ]

    for command in allowed:
        assert not code_implementation_server._is_blocked_heavy_test_command(command)


def test_execute_python_blocks_pytest_main_snippets():
    assert code_implementation_server._is_blocked_heavy_test_snippet(
        "import pytest\npytest.main(['tests', '-v'])"
    )


def test_code_implementation_validate_path_blocks_sibling_prefix_escape(tmp_path):
    old_workspace = code_implementation_server.WORKSPACE_DIR
    workspace = tmp_path / "ws"
    sibling = tmp_path / "ws_evil"
    workspace.mkdir()
    sibling.mkdir()
    try:
        code_implementation_server.WORKSPACE_DIR = workspace
        try:
            code_implementation_server.validate_path("../ws_evil/out.txt")
        except ValueError:
            pass
        else:
            raise AssertionError("validate_path allowed sibling-prefix path escape")
    finally:
        code_implementation_server.WORKSPACE_DIR = old_workspace


def test_command_executor_blocks_same_pytest_commands():
    blocked = [
        "python -m pytest tests/ -v",
        "timeout 15 python -m pytest tests/test_pipeline.py -v 2>&1 | tail -40",
        "mkdir -p src && pytest tests",
    ]

    for command in blocked:
        assert command_executor._is_blocked_heavy_test_command(command)


def test_command_executor_allows_file_tree_commands():
    allowed = [
        "mkdir -p src tests",
        "touch README.md",
        "python -m compileall -q src",
    ]

    for command in allowed:
        assert not command_executor._is_blocked_heavy_test_command(command)


# ----- touch *.py blocking -----
# Observation from paper_20260521-2243 run: the agent ran a single
# execute_commands call with 42 `touch` lines that created empty Python
# implementation files. Those files bypassed write_file acceptance and ended
# up as empty .py files that the quality gate later flagged. We refuse such
# touches so the agent must call write_file with real content instead.


def test_touch_python_implementation_file_is_blocked():
    blocked = [
        "touch hyper_kggen/src/extraction/chunker.py",
        "touch src/main.py",
        "mkdir -p src && touch src/pipeline.py",
        "touch a.py b.py c.py",
    ]
    for command in blocked:
        assert command_executor._has_touch_creating_empty_py(command), command


def test_touch_init_py_is_allowed():
    """__init__.py is intentionally empty in most projects — package marker."""
    allowed = [
        "touch src/__init__.py",
        "touch tests/__init__.py",
        "touch hyper_kggen/data/__init__.py",
    ]
    for command in allowed:
        assert not command_executor._has_touch_creating_empty_py(command), command


def test_touch_non_python_files_is_allowed():
    allowed = [
        "touch README.md",
        "touch requirements.txt",
        "touch config/config.yaml",
        "touch data/sample.json",
    ]
    for command in allowed:
        assert not command_executor._has_touch_creating_empty_py(command), command


def test_touch_mixed_batch_with_one_py_is_blocked():
    """A batched touch where any non-__init__.py Python file appears must fail."""
    command = (
        "touch hyper_kggen/__init__.py\n"
        "touch hyper_kggen/src/__init__.py\n"
        "touch hyper_kggen/src/pipeline.py"  # this one taints the whole batch
    )
    assert command_executor._has_touch_creating_empty_py(command)
