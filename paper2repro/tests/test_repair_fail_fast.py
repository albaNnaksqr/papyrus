"""Tests for the repair fail-fast helper.

Observation from paper_9332b8c0 run: the repair loop ran 3 attempts × 9 minutes
each, each attempt hitting max_iterations=800 with files_completed=0 and
rejected_writes=[]. The agent never touched the filesystem. Continuing to the
next attempt re-runs the same dead behavior. The helper here lets the
orchestrator short-circuit when a repair round produces no changes at all.
"""

from workflows.agent_orchestration_engine import _repair_made_changes


def test_zero_completed_and_zero_rejected_is_no_op():
    """The exact paper_9332b8c0 case: agent stalled, 0 writes attempted."""
    result = {
        "status": "incomplete",
        "inner_status": "max_iterations",
        "files_completed": 0,
        "rejected_writes": [],
    }
    assert _repair_made_changes(result) is False


def test_some_completed_files_counts_as_change():
    result = {"files_completed": 2, "rejected_writes": []}
    assert _repair_made_changes(result) is True


def test_rejected_writes_alone_counts_as_change():
    """Agent tried to write but was rejected (empty file / syntax error).
    Still an attempt — give it another round to do it right."""
    result = {
        "files_completed": 0,
        "rejected_writes": [{"file": "src/x.py", "reason": "empty implementation file"}],
    }
    assert _repair_made_changes(result) is True


def test_missing_keys_treated_as_no_op():
    """Defensive: if result dict is malformed/empty, assume no work happened."""
    assert _repair_made_changes({}) is False


def test_none_values_treated_as_no_op():
    result = {"files_completed": None, "rejected_writes": None}
    assert _repair_made_changes(result) is False
