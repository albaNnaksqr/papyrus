import json
import pytest
from api.task_manager import TaskManager, TaskRecord, append_event, OUTPUT_ROOT


@pytest.fixture(autouse=True)
def reset_singleton():
    TaskManager._instance = None
    yield
    TaskManager._instance = None


def test_create_registers_task(tmp_path, monkeypatch):
    monkeypatch.setattr("api.task_manager.OUTPUT_ROOT", tmp_path)
    mgr = TaskManager.get()
    record = mgr.create("paper_abc")
    assert record.task_id == "paper_abc"
    assert record.status == "pending"
    assert mgr.lookup("paper_abc") is record
    assert (tmp_path / "paper_abc").is_dir()


def test_lookup_missing_returns_none():
    assert TaskManager.get().lookup("nonexistent") is None


def test_all_tasks_returns_list(tmp_path, monkeypatch):
    monkeypatch.setattr("api.task_manager.OUTPUT_ROOT", tmp_path)
    mgr = TaskManager.get()
    mgr.create("paper_x")
    mgr.create("paper_y")
    ids = [r.task_id for r in mgr.all_tasks()]
    assert "paper_x" in ids and "paper_y" in ids


def test_append_event_creates_jsonl(tmp_path):
    record = TaskRecord(
        task_id="t1", status="running",
        created_at="2026-01-01T00:00:00+00:00",
        output_dir=tmp_path / "t1",
    )
    append_event(record, {"type": "progress", "pct": 50, "message": "hello", "ts": "x"})
    lines = (tmp_path / "t1" / "logs" / "events.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["pct"] == 50


def test_append_event_appends_multiple(tmp_path):
    record = TaskRecord(
        task_id="t2", status="running",
        created_at="2026-01-01T00:00:00+00:00",
        output_dir=tmp_path / "t2",
    )
    append_event(record, {"type": "progress", "pct": 10, "message": "a", "ts": "x"})
    append_event(record, {"type": "progress", "pct": 20, "message": "b", "ts": "x"})
    lines = (tmp_path / "t2" / "logs" / "events.jsonl").read_text().strip().splitlines()
    assert len(lines) == 2


def test_restore_done(tmp_path, monkeypatch):
    monkeypatch.setattr("api.task_manager.OUTPUT_ROOT", tmp_path)
    task_dir = tmp_path / "paper_done"
    (task_dir / "logs").mkdir(parents=True)
    (task_dir / "logs" / "events.jsonl").write_text(
        json.dumps({"type": "done", "pct": 100, "message": "ok", "ts": "x"}) + "\n"
    )
    mgr = TaskManager.get()
    mgr.restore_from_disk()
    assert mgr.lookup("paper_done").status == "done"


def test_restore_error_when_done_event_summary_contains_incomplete(tmp_path, monkeypatch):
    monkeypatch.setattr("api.task_manager.OUTPUT_ROOT", tmp_path)
    task_dir = tmp_path / "paper_incomplete_done_event"
    (task_dir / "logs").mkdir(parents=True)
    (task_dir / "logs" / "events.jsonl").write_text(
        json.dumps({
            "type": "done",
            "pct": 100,
            "summary": "{'status': 'incomplete', 'validation': {'status': 'error'}}",
            "ts": "x",
        }) + "\n"
    )
    mgr = TaskManager.get()
    mgr.restore_from_disk()
    assert mgr.lookup("paper_incomplete_done_event").status == "error"


def test_restore_done_when_done_event_summary_mentions_known_issues(tmp_path, monkeypatch):
    monkeypatch.setattr("api.task_manager.OUTPUT_ROOT", tmp_path)
    task_dir = tmp_path / "paper_done_known_issues"
    (task_dir / "logs").mkdir(parents=True)
    (task_dir / "logs" / "events.jsonl").write_text(
        json.dumps({
            "type": "done",
            "pct": 100,
            "summary": (
                "Implementation completed\n"
                "❌ Generated code quality gate failed "
                "(1 known issue(s) — see known_issues.md)"
            ),
            "ts": "x",
        }, ensure_ascii=False) + "\n"
    )
    mgr = TaskManager.get()
    mgr.restore_from_disk()
    assert mgr.lookup("paper_done_known_issues").status == "done"


def test_restore_error_from_incomplete_implementation_report(tmp_path, monkeypatch):
    monkeypatch.setattr("api.task_manager.OUTPUT_ROOT", tmp_path)
    task_dir = tmp_path / "paper_incomplete_report"
    task_dir.mkdir(parents=True)
    (task_dir / "code_implementation_report.txt").write_text(
        "{'status': 'incomplete', 'inner_status': 'max_iterations'}",
        encoding="utf-8",
    )
    (task_dir / "validation_report.md").write_text("## 汇总 ❌\n", encoding="utf-8")
    mgr = TaskManager.get()
    mgr.restore_from_disk()
    assert mgr.lookup("paper_incomplete_report").status == "error"


def test_restore_interrupted(tmp_path, monkeypatch):
    monkeypatch.setattr("api.task_manager.OUTPUT_ROOT", tmp_path)
    task_dir = tmp_path / "paper_mid"
    (task_dir / "logs").mkdir(parents=True)
    (task_dir / "logs" / "events.jsonl").write_text(
        json.dumps({"type": "progress", "pct": 50, "message": "x", "ts": "x"}) + "\n"
    )
    mgr = TaskManager.get()
    mgr.restore_from_disk()
    assert mgr.lookup("paper_mid").status == "interrupted"


def test_restore_interrupted_terminal_event(tmp_path, monkeypatch):
    monkeypatch.setattr("api.task_manager.OUTPUT_ROOT", tmp_path)
    task_dir = tmp_path / "paper_stop"
    (task_dir / "logs").mkdir(parents=True)
    (task_dir / "logs" / "events.jsonl").write_text(
        json.dumps({"type": "interrupted", "message": "用户停止", "ts": "x"}) + "\n"
    )
    mgr = TaskManager.get()
    mgr.restore_from_disk()
    assert mgr.lookup("paper_stop").status == "interrupted"


def test_restore_done_from_terminal_progress_pct_100(tmp_path, monkeypatch):
    monkeypatch.setattr("api.task_manager.OUTPUT_ROOT", tmp_path)
    task_dir = tmp_path / "paper_progress_done"
    (task_dir / "logs").mkdir(parents=True)
    (task_dir / "logs" / "events.jsonl").write_text(
        json.dumps({"type": "progress", "pct": 99, "message": "still running", "ts": "x"}) + "\n" +
        json.dumps({"type": "progress", "pct": 100, "message": "🎉 Finalizing results and generating summary...", "ts": "x"}) + "\n"
    )
    mgr = TaskManager.get()
    mgr.restore_from_disk()
    assert mgr.lookup("paper_progress_done").status == "done"


def test_restore_interrupted_when_no_terminal_below_100(tmp_path, monkeypatch):
    monkeypatch.setattr("api.task_manager.OUTPUT_ROOT", tmp_path)
    task_dir = tmp_path / "paper_running"
    (task_dir / "logs").mkdir(parents=True)
    (task_dir / "logs" / "events.jsonl").write_text(
        json.dumps({"type": "progress", "pct": 80, "message": "in progress", "ts": "x"}) + "\n"
    )
    mgr = TaskManager.get()
    mgr.restore_from_disk()
    assert mgr.lookup("paper_running").status == "interrupted"


def test_restore_skips_already_registered(tmp_path, monkeypatch):
    monkeypatch.setattr("api.task_manager.OUTPUT_ROOT", tmp_path)
    mgr = TaskManager.get()
    mgr.create("paper_existing")  # status=pending in memory
    task_dir = tmp_path / "paper_existing"
    (task_dir / "logs").mkdir(parents=True, exist_ok=True)
    (task_dir / "logs" / "events.jsonl").write_text(
        json.dumps({"type": "done", "pct": 100, "message": "ok", "ts": "x"}) + "\n"
    )
    mgr.restore_from_disk()
    assert mgr.lookup("paper_existing").status == "pending"  # in-memory wins


from api.task_manager import make_callback


def test_callback_puts_progress_event(tmp_path):
    record = TaskRecord(
        task_id="cb1", status="running",
        created_at="2026-01-01T00:00:00+00:00",
        output_dir=tmp_path / "cb1",
    )
    cb = make_callback(record)
    cb(33, "phase 1 done")
    event = record.queue.get_nowait()
    assert event["type"] == "progress"
    assert event["pct"] == 33
    assert event["message"] == "phase 1 done"


def test_callback_writes_events_jsonl(tmp_path):
    record = TaskRecord(
        task_id="cb2", status="running",
        created_at="2026-01-01T00:00:00+00:00",
        output_dir=tmp_path / "cb2",
    )
    make_callback(record)(10, "start")
    data = json.loads((tmp_path / "cb2" / "logs" / "events.jsonl").read_text().strip())
    assert data["pct"] == 10


def test_callback_error_flag(tmp_path):
    record = TaskRecord(
        task_id="cb3", status="running",
        created_at="2026-01-01T00:00:00+00:00",
        output_dir=tmp_path / "cb3",
    )
    make_callback(record)(0, "boom", err=True)
    assert record.queue.get_nowait()["type"] == "error"


def test_callback_emits_file_written_from_paper_refs(tmp_path):
    record = TaskRecord(
        task_id="cb4", status="running",
        created_at="2026-01-01T00:00:00+00:00",
        output_dir=tmp_path / "cb4",
    )
    (tmp_path / "cb4").mkdir(parents=True, exist_ok=True)
    ref = {
        "timestamp": "2026-01-01T00:00:01+00:00",
        "file_path": "src/model.py",
        "section_ref": "§4.1",
        "quote": "some quote",
        "critique_type": "trap",
        "critique_text": "be careful",
    }
    (tmp_path / "cb4" / "paper_refs.jsonl").write_text(json.dumps(ref) + "\n")
    make_callback(record)(50, "impl running")
    e1 = record.queue.get_nowait()
    e2 = record.queue.get_nowait()
    assert e1["type"] == "file_written"
    assert e1["path"] == "src/model.py"
    assert e1["section_ref"] == "§4.1"
    assert e2["type"] == "progress"


def test_callback_emits_file_written_from_disk_scan(tmp_path):
    record = TaskRecord(
        task_id="cb6", status="running",
        created_at="2026-01-01T00:00:00+00:00",
        output_dir=tmp_path / "cb6",
    )
    code_dir = tmp_path / "cb6" / "generate_code" / "src"
    code_dir.mkdir(parents=True)
    (code_dir / "model.py").write_text("# generated")
    (code_dir / "utils.py").write_text("# generated")
    make_callback(record)(50, "impl running")
    events = []
    while not record.queue.empty():
        events.append(record.queue.get_nowait())
    file_events = [e for e in events if e["type"] == "file_written"]
    paths = sorted(e["path"] for e in file_events)
    assert paths == ["src/model.py", "src/utils.py"]


def test_callback_disk_scan_not_double_emitted(tmp_path):
    record = TaskRecord(
        task_id="cb7", status="running",
        created_at="2026-01-01T00:00:00+00:00",
        output_dir=tmp_path / "cb7",
    )
    code_dir = tmp_path / "cb7" / "generate_code"
    code_dir.mkdir(parents=True)
    (code_dir / "a.py").write_text("# x")
    cb = make_callback(record)
    cb(10, "first")
    while not record.queue.empty():
        record.queue.get_nowait()
    cb(20, "second")  # same file, no new files
    second_events = []
    while not record.queue.empty():
        second_events.append(record.queue.get_nowait())
    # only the progress event, no duplicate file_written
    assert [e["type"] for e in second_events] == ["progress"]


def test_callback_paper_refs_and_disk_scan_dedupe(tmp_path):
    record = TaskRecord(
        task_id="cb8", status="running",
        created_at="2026-01-01T00:00:00+00:00",
        output_dir=tmp_path / "cb8",
    )
    code_dir = tmp_path / "cb8" / "generate_code"
    code_dir.mkdir(parents=True)
    (code_dir / "model.py").write_text("# x")
    ref = {"timestamp": "x", "file_path": "model.py", "section_ref": "§1",
           "quote": "q", "critique_type": "trap", "critique_text": "c"}
    (tmp_path / "cb8" / "paper_refs.jsonl").write_text(json.dumps(ref) + "\n")
    make_callback(record)(50, "impl running")
    events = []
    while not record.queue.empty():
        events.append(record.queue.get_nowait())
    file_events = [e for e in events if e["type"] == "file_written"]
    assert len(file_events) == 1
    assert file_events[0]["section_ref"] == "§1"  # the paper_refs version wins


def test_callback_paper_refs_not_double_emitted(tmp_path):
    record = TaskRecord(
        task_id="cb5", status="running",
        created_at="2026-01-01T00:00:00+00:00",
        output_dir=tmp_path / "cb5",
    )
    (tmp_path / "cb5").mkdir(parents=True, exist_ok=True)
    ref = {"timestamp": "x", "file_path": "a.py", "section_ref": "§1",
           "quote": "q", "critique_type": "trap", "critique_text": "c"}
    (tmp_path / "cb5" / "paper_refs.jsonl").write_text(json.dumps(ref) + "\n")
    cb = make_callback(record)
    cb(10, "first")
    while not record.queue.empty():
        record.queue.get_nowait()
    cb(20, "second")  # no new refs
    events = []
    while not record.queue.empty():
        events.append(record.queue.get_nowait())
    assert len(events) == 1
    assert events[0]["type"] == "progress"
