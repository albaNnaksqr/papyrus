import json
import pytest
from api.task_manager import TaskRecord
from api.routes.events import _format_sse, _replay_from_file, _event_generator


def make_record(tmp_path, status="running"):
    return TaskRecord(
        task_id="ev1", status=status,
        created_at="2026-01-01T00:00:00+00:00",
        output_dir=tmp_path / "ev1",
    )


def test_format_sse_progress():
    line = _format_sse({"type": "progress", "pct": 10}, event_id=3)
    assert line.startswith("id: 3\n")
    assert "data: " in line
    assert line.endswith("\n\n")
    payload = json.loads(line.split("data: ", 1)[1].strip())
    assert payload["pct"] == 10


def test_format_sse_heartbeat():
    assert _format_sse(None, event_id=None) == ": heartbeat\n\n"


async def test_replay_empty_when_no_file(tmp_path):
    record = make_record(tmp_path)
    results = [item async for item in _replay_from_file(record, after_id=-1)]
    assert results == []


async def test_replay_returns_events_after_id(tmp_path):
    record = make_record(tmp_path)
    (tmp_path / "ev1" / "logs").mkdir(parents=True)
    (tmp_path / "ev1" / "logs" / "events.jsonl").write_text(
        json.dumps({"type": "progress", "pct": 10}) + "\n" +
        json.dumps({"type": "progress", "pct": 20}) + "\n" +
        json.dumps({"type": "done", "pct": 100}) + "\n"
    )
    results = [item async for item in _replay_from_file(record, after_id=0)]
    assert len(results) == 2
    assert results[0][0]["pct"] == 20
    assert results[0][1] == 1


async def test_event_stream_done_task_yields_terminal(tmp_path):
    class FakeRequest:
        async def is_disconnected(self): return False

    record = make_record(tmp_path, status="done")
    chunks = [c async for c in _event_generator(FakeRequest(), record, last_event_id=None)]
    assert any("done" in c for c in chunks)


async def test_event_stream_done_task_no_duplicate_terminal_if_disk_has_done(tmp_path):
    class FakeRequest:
        async def is_disconnected(self):
            return False

    record = make_record(tmp_path, status="done")
    (tmp_path / "ev1" / "logs").mkdir(parents=True)
    (tmp_path / "ev1" / "logs" / "events.jsonl").write_text(
        json.dumps({"type": "progress", "pct": 40}) + "\n" +
        json.dumps({"type": "done", "pct": 100, "summary": "ok"}) + "\n"
    )

    chunks = [c async for c in _event_generator(FakeRequest(), record, last_event_id=None)]
    terminal_count = 0
    for chunk in chunks:
        line = chunk.strip().split("data: ", 1)[-1]
        if not line.startswith("{"):
            continue
        event = json.loads(line)
        if event.get("type") == "done":
            terminal_count += 1
    assert terminal_count == 1


async def test_event_stream_reads_queue_event(tmp_path):
    class FakeRequest:
        async def is_disconnected(self): return False

    record = make_record(tmp_path, status="running")
    record.queue.put_nowait({"type": "progress", "pct": 42, "message": "hi", "ts": "x"})

    gen = _event_generator(FakeRequest(), record, last_event_id=None)
    chunk = await gen.__anext__()
    await gen.aclose()

    assert "42" in chunk
