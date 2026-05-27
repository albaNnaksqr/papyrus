"""Tests for utils.loop_detector.LoopDetector with arg-signature loop detection.

Background: read_code_mem and read_file are exempt from name-only loop detection
because legitimate exploration calls them repeatedly with *different* files.
But the LLM can still get stuck calling them repeatedly with the *same* file
(observed in task paper_9332b8c0: 1552 read_code_mem calls against 6 fixed
file paths over 27 minutes). These tests pin down the new behavior:

- Same (tool, args) repeated max_repeats times -> loop detected (even for exempt tools).
- Same exempt tool with *different* args repeated -> NOT a loop (legitimate exploration).
- write_file is always exempt regardless of args (sequential file writes).
- file_paths arg list normalization: order-insensitive (same files in different order
  count as the same signature).
- Backward-compatible: calling check_tool_call without args degrades to old behavior
  (exempt tools always pass).
"""

from utils.loop_detector import LoopDetector


def _make_detector(max_repeats: int = 5) -> LoopDetector:
    return LoopDetector(max_repeats=max_repeats)


def test_read_code_mem_same_args_repeated_is_loop():
    det = _make_detector(max_repeats=5)
    args = {"file_paths": ["src/pipeline.py"]}
    results = [det.check_tool_call("read_code_mem", args) for _ in range(5)]
    assert results[-1]["status"] == "loop_detected"
    assert results[-1]["should_stop"] is True


def test_read_code_mem_different_args_not_loop():
    det = _make_detector(max_repeats=5)
    files = [
        "src/a.py", "src/b.py", "src/c.py", "src/d.py", "src/e.py",
    ]
    for f in files:
        result = det.check_tool_call("read_code_mem", {"file_paths": [f]})
        assert result["should_stop"] is False, f"unexpected stop on {f}: {result}"


def test_read_file_same_path_repeated_is_loop():
    det = _make_detector(max_repeats=5)
    args = {"file_path": "src/main.py"}
    for _ in range(4):
        assert det.check_tool_call("read_file", args)["should_stop"] is False
    assert det.check_tool_call("read_file", args)["status"] == "loop_detected"


def test_write_file_same_path_repeated_not_loop():
    """write_file is always exempt regardless of args — sequential implementation."""
    det = _make_detector(max_repeats=5)
    for _ in range(10):
        result = det.check_tool_call("write_file", {"file_path": "src/x.py"})
        assert result["should_stop"] is False


def test_file_paths_order_insensitive():
    """Same file set in different orders should count as the same signature."""
    det = _make_detector(max_repeats=5)
    perms = [
        ["a.py", "b.py", "c.py"],
        ["c.py", "b.py", "a.py"],
        ["b.py", "a.py", "c.py"],
        ["a.py", "c.py", "b.py"],
        ["c.py", "a.py", "b.py"],
    ]
    last = None
    for p in perms:
        last = det.check_tool_call("read_code_mem", {"file_paths": p})
    assert last["status"] == "loop_detected"


def test_legacy_call_without_args_still_exempts():
    """Backward compat: callers that don't pass args get old exempt behavior."""
    det = _make_detector(max_repeats=5)
    for _ in range(10):
        result = det.check_tool_call("read_code_mem")
        assert result["should_stop"] is False


def test_non_exempt_tool_name_only_loop_still_works():
    """Non-exempt tool: name repetition alone is enough (args optional)."""
    det = _make_detector(max_repeats=5)
    for _ in range(4):
        assert det.check_tool_call("some_other_tool")["should_stop"] is False
    assert det.check_tool_call("some_other_tool")["status"] == "loop_detected"


def test_interleaved_same_args_not_consecutive_not_loop():
    """If reads against the same file are broken up by other tools, not a loop."""
    det = _make_detector(max_repeats=5)
    args = {"file_paths": ["src/pipeline.py"]}
    det.check_tool_call("read_code_mem", args)
    det.check_tool_call("write_file", {"file_path": "src/pipeline.py"})
    det.check_tool_call("read_code_mem", args)
    det.check_tool_call("write_file", {"file_path": "src/main.py"})
    result = det.check_tool_call("read_code_mem", args)
    assert result["should_stop"] is False


def test_should_abort_after_loop():
    """_check_without_history path must also flag the same condition."""
    det = _make_detector(max_repeats=5)
    args = {"file_paths": ["src/pipeline.py"]}
    for _ in range(5):
        det.check_tool_call("read_code_mem", args)
    assert det.should_abort() is True
    assert "Loop" in (det.get_abort_reason() or "")
