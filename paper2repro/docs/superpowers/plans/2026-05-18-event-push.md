# Event Push Mechanism Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a FastAPI HTTP server (`serve.py`) that lets a Web UI trigger paper2code pipeline runs and receive real-time progress via Server-Sent Events (SSE).

**Architecture:** Single-process FastAPI app runs the pipeline as an `asyncio.create_task()` background coroutine. A `TaskManager` holds one `asyncio.Queue` per task; the pipeline's existing `progress_callback` pushes events into the queue while an SSE endpoint drains it to the browser. Events are also appended to `output/tasks/{id}/logs/events.jsonl` for persistence and reconnect replay. `paper2code.py` (CLI) is untouched.

**Tech Stack:** FastAPI ≥ 0.111, uvicorn[standard] ≥ 0.29, python-multipart ≥ 0.0.9, pytest-asyncio ≥ 0.23

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `api/__init__.py` | Create | Package marker |
| `api/task_manager.py` | Create | `TaskRecord`, `TaskManager`, `append_event`, `make_callback`, `_check_paper_refs` |
| `api/routes/__init__.py` | Create | Package marker |
| `api/routes/tasks.py` | Create | `POST /api/tasks`, `GET /api/tasks`, `GET /api/tasks/{id}`, `GET /api/tasks/{id}/artifacts/{path}` |
| `api/routes/events.py` | Create | `GET /api/tasks/{id}/events` — SSE stream |
| `api/server.py` | Create | FastAPI app, CORS middleware, lifespan (restore_from_disk) |
| `serve.py` | Create | Entry point: `python serve.py` |
| `requirements.txt` | Modify | Add fastapi, uvicorn[standard], python-multipart, pytest-asyncio |
| `tests/test_api/__init__.py` | Create | Package marker |
| `tests/test_api/test_task_manager.py` | Create | Unit tests for `TaskManager`, `append_event`, `make_callback` |
| `tests/test_api/test_events.py` | Create | Unit tests for `_format_sse`, `_replay_from_file`, `_event_generator` |
| `tests/test_api/test_routes_tasks.py` | Create | HTTP route tests (non-SSE endpoints) |
| `.gitignore` | Modify | Add `.superpowers/` |

---

### Task 1: Add dependencies and package skeleton

**Files:**
- Modify: `requirements.txt`
- Create: `api/__init__.py`, `api/routes/__init__.py`, `tests/test_api/__init__.py`
- Modify: `.gitignore`

- [ ] **Step 1: Append new dependencies to requirements.txt**

```
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
python-multipart>=0.0.9
pytest-asyncio>=0.23.0
```

- [ ] **Step 2: Install them**

```bash
pip install "fastapi>=0.111.0" "uvicorn[standard]>=0.29.0" "python-multipart>=0.0.9" "pytest-asyncio>=0.23.0"
```
Expected: installs without errors.

- [ ] **Step 3: Create package skeleton files (all empty)**

```bash
touch api/__init__.py api/routes/__init__.py tests/test_api/__init__.py
```

- [ ] **Step 4: Configure pytest asyncio mode**

Check whether `pytest.ini` exists:
```bash
ls pytest.ini pyproject.toml setup.cfg 2>/dev/null
```

If none exist, create `pytest.ini`:
```ini
[pytest]
asyncio_mode = auto
```

If `pytest.ini` already exists, append `asyncio_mode = auto` under the `[pytest]` section.

- [ ] **Step 5: Add .superpowers/ to .gitignore**

Append to `.gitignore`:
```
.superpowers/
```

- [ ] **Step 6: Commit**

```bash
git add requirements.txt api/__init__.py api/routes/__init__.py tests/test_api/__init__.py .gitignore pytest.ini
git commit -m "chore: add fastapi deps and api package skeleton"
```

---

### Task 2: TaskRecord and TaskManager

**Files:**
- Create: `api/task_manager.py`
- Create: `tests/test_api/test_task_manager.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_api/test_task_manager.py`:
```python
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_api/test_task_manager.py -v 2>&1 | head -15
```
Expected: `ModuleNotFoundError: No module named 'api.task_manager'`

- [ ] **Step 3: Create api/task_manager.py**

```python
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

OUTPUT_ROOT = Path(__file__).resolve().parent.parent / "output" / "tasks"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TaskRecord:
    task_id: str
    status: str  # pending | running | done | error | interrupted
    created_at: str
    output_dir: Path
    queue: asyncio.Queue = field(default_factory=asyncio.Queue, repr=False, compare=False)
    paper_refs_offset: int = field(default=0, repr=False, compare=False)


def append_event(record: TaskRecord, event: dict[str, Any]) -> None:
    events_path = record.output_dir / "logs" / "events.jsonl"
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with open(events_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


class TaskManager:
    _instance: TaskManager | None = None

    def __init__(self) -> None:
        self._tasks: dict[str, TaskRecord] = {}

    @classmethod
    def get(cls) -> TaskManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def create(self, task_id: str) -> TaskRecord:
        output_dir = OUTPUT_ROOT / task_id
        output_dir.mkdir(parents=True, exist_ok=True)
        record = TaskRecord(
            task_id=task_id,
            status="pending",
            created_at=_utcnow(),
            output_dir=output_dir,
        )
        self._tasks[task_id] = record
        return record

    def lookup(self, task_id: str) -> TaskRecord | None:
        return self._tasks.get(task_id)

    def all_tasks(self) -> list[TaskRecord]:
        return list(self._tasks.values())

    def restore_from_disk(self) -> None:
        if not OUTPUT_ROOT.exists():
            return
        for task_dir in sorted(OUTPUT_ROOT.iterdir()):
            if not task_dir.is_dir():
                continue
            task_id = task_dir.name
            if task_id in self._tasks:
                continue
            events_path = task_dir / "logs" / "events.jsonl"
            status = "interrupted"
            if events_path.exists():
                lines = [l for l in events_path.read_text(encoding="utf-8").splitlines() if l.strip()]
                if lines:
                    last_type = json.loads(lines[-1]).get("type")
                    if last_type in ("done", "error"):
                        status = last_type
            self._tasks[task_id] = TaskRecord(
                task_id=task_id,
                status=status,
                created_at=_utcnow(),
                output_dir=task_dir,
            )
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_api/test_task_manager.py -v
```
Expected: 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add api/task_manager.py tests/test_api/test_task_manager.py pytest.ini
git commit -m "feat: add TaskRecord and TaskManager with disk restore"
```

---

### Task 3: make_callback and paper_refs polling

**Files:**
- Modify: `api/task_manager.py` (append `_check_paper_refs`, `make_callback`)
- Modify: `tests/test_api/test_task_manager.py` (append callback tests)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_api/test_task_manager.py`:
```python
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_api/test_task_manager.py::test_callback_puts_progress_event -v
```
Expected: `ImportError` — `make_callback` not defined.

- [ ] **Step 3: Append _check_paper_refs and make_callback to api/task_manager.py**

```python
def _check_paper_refs(record: TaskRecord) -> list[dict[str, Any]]:
    refs_path = record.output_dir / "paper_refs.jsonl"
    if not refs_path.exists():
        return []
    lines = refs_path.read_text(encoding="utf-8").splitlines()
    new_lines = lines[record.paper_refs_offset:]
    record.paper_refs_offset = len(lines)
    events = []
    for line in new_lines:
        line = line.strip()
        if not line:
            continue
        try:
            ref = json.loads(line)
        except json.JSONDecodeError:
            continue
        events.append({
            "type": "file_written",
            "path": ref.get("file_path", ""),
            "phase": "impl",
            "section_ref": ref.get("section_ref", ""),
            "ts": ref.get("timestamp", _utcnow()),
        })
    return events


def make_callback(record: TaskRecord):
    def callback(pct: int, msg: str, err: object = None) -> None:
        for fw_event in _check_paper_refs(record):
            record.queue.put_nowait(fw_event)
            append_event(record, fw_event)
        event: dict[str, Any] = {
            "type": "error" if err else "progress",
            "pct": pct,
            "message": msg,
            "ts": _utcnow(),
        }
        record.queue.put_nowait(event)
        append_event(record, event)
    return callback
```

- [ ] **Step 4: Run all task_manager tests**

```bash
pytest tests/test_api/test_task_manager.py -v
```
Expected: 13 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add api/task_manager.py tests/test_api/test_task_manager.py
git commit -m "feat: add make_callback with progress and file_written event emission"
```

---

### Task 4: SSE event stream generator

**Files:**
- Create: `api/routes/events.py`
- Create: `tests/test_api/test_events.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_api/test_events.py`:
```python
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


async def test_event_stream_reads_queue_event(tmp_path):
    class FakeRequest:
        async def is_disconnected(self): return False

    record = make_record(tmp_path, status="running")
    record.queue.put_nowait({"type": "progress", "pct": 42, "message": "hi", "ts": "x"})

    gen = _event_generator(FakeRequest(), record, last_event_id=None)
    chunk = await gen.__anext__()
    await gen.aclose()

    assert "42" in chunk
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_api/test_events.py -v 2>&1 | head -15
```
Expected: `ModuleNotFoundError: No module named 'api.routes.events'`

- [ ] **Step 3: Create api/routes/events.py**

```python
from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from api.task_manager import TaskManager, TaskRecord

router = APIRouter()


def _format_sse(event: dict | None, event_id: int | None) -> str:
    if event is None:
        return ": heartbeat\n\n"
    id_line = f"id: {event_id}\n" if event_id is not None else ""
    return id_line + f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


async def _replay_from_file(
    record: TaskRecord, after_id: int
) -> AsyncIterator[tuple[dict, int]]:
    events_path = record.output_dir / "logs" / "events.jsonl"
    if not events_path.exists():
        return
    lines = events_path.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if i <= after_id:
            continue
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line), i
        except json.JSONDecodeError:
            continue


async def _event_generator(
    request: Request, record: TaskRecord, last_event_id: int | None
) -> AsyncIterator[str]:
    event_index = -1 if last_event_id is None else last_event_id

    if last_event_id is not None:
        async for event, idx in _replay_from_file(record, after_id=last_event_id):
            if await request.is_disconnected():
                return
            event_index = idx
            yield _format_sse(event, event_id=idx)

    while record.status not in ("done", "error", "interrupted"):
        if await request.is_disconnected():
            return
        try:
            event = await asyncio.wait_for(record.queue.get(), timeout=25)
            event_index += 1
            yield _format_sse(event, event_id=event_index)
        except asyncio.TimeoutError:
            yield _format_sse(None, event_id=None)

    yield _format_sse({"type": record.status}, event_id=event_index + 1)


@router.get("/api/tasks/{task_id}/events")
async def stream_events(task_id: str, request: Request):
    manager = TaskManager.get()
    record = manager.lookup(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    last_id_header = request.headers.get("last-event-id")
    last_event_id = int(last_id_header) if last_id_header else None
    return StreamingResponse(
        _event_generator(request, record, last_event_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
```

- [ ] **Step 4: Run SSE tests**

```bash
pytest tests/test_api/test_events.py -v
```
Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add api/routes/events.py tests/test_api/test_events.py
git commit -m "feat: add SSE event stream endpoint with reconnect replay"
```

---

### Task 5: HTTP routes (tasks CRUD) and FastAPI app

**Files:**
- Create: `api/routes/tasks.py`
- Create: `api/server.py`
- Create: `tests/test_api/test_routes_tasks.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_api/test_routes_tasks.py`:
```python
import pytest
from fastapi.testclient import TestClient
from api.task_manager import TaskManager


@pytest.fixture(autouse=True)
def reset_manager(tmp_path, monkeypatch):
    monkeypatch.setattr("api.task_manager.OUTPUT_ROOT", tmp_path)
    TaskManager._instance = None
    yield
    TaskManager._instance = None


@pytest.fixture
def client():
    from api.server import app
    return TestClient(app)


def test_list_tasks_empty(client):
    assert client.get("/api/tasks").json() == []


def test_get_task_not_found(client):
    resp = client.get("/api/tasks/nonexistent")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_get_task_lists_artifacts(client, tmp_path):
    mgr = TaskManager.get()
    record = mgr.create("paper_t1")
    (record.output_dir / "src").mkdir()
    (record.output_dir / "src" / "model.py").write_text("# code")
    resp = client.get("/api/tasks/paper_t1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["task_id"] == "paper_t1"
    assert "src/model.py" in body["artifacts"]


def test_get_task_status(client, tmp_path):
    mgr = TaskManager.get()
    record = mgr.create("paper_t2")
    record.status = "done"
    assert client.get("/api/tasks/paper_t2").json()["status"] == "done"


def test_get_artifact_returns_file(client, tmp_path):
    mgr = TaskManager.get()
    record = mgr.create("paper_t3")
    (record.output_dir / "plan.txt").write_text("hello plan")
    resp = client.get("/api/tasks/paper_t3/artifacts/plan.txt")
    assert resp.status_code == 200
    assert resp.text == "hello plan"


def test_get_artifact_not_found(client, tmp_path):
    mgr = TaskManager.get()
    mgr.create("paper_t4")
    assert client.get("/api/tasks/paper_t4/artifacts/missing.txt").status_code == 404


def test_get_artifact_path_traversal_blocked(client, tmp_path):
    mgr = TaskManager.get()
    mgr.create("paper_t5")
    resp = client.get("/api/tasks/paper_t5/artifacts/../../secrets.txt")
    assert resp.status_code in (404, 403)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_api/test_routes_tasks.py -v 2>&1 | head -15
```
Expected: `ModuleNotFoundError: No module named 'api.routes.tasks'` or `api.server`.

- [ ] **Step 3: Create api/routes/tasks.py**

```python
from __future__ import annotations

import asyncio
import os
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from api.task_manager import TaskManager, make_callback

router = APIRouter()


class CreateTaskRequest(BaseModel):
    pdf_path: str
    fast: bool = False
    no_critique: bool = False


@router.post("/api/tasks", status_code=202)
async def create_task(body: CreateTaskRequest):
    task_id_hex = uuid.uuid4().hex[:8]
    api_task_id = f"paper_{task_id_hex}"
    manager = TaskManager.get()
    record = manager.create(api_task_id)
    cb = make_callback(record)

    async def _run() -> None:
        from loguru import logger
        from workflows.agent_orchestration_engine import execute_multi_agent_research_pipeline
        if body.no_critique:
            os.environ["PAPER2CODE_NO_CRITIQUE"] = "1"
        try:
            record.status = "running"
            result = await execute_multi_agent_research_pipeline(
                input_source=body.pdf_path,
                task_id=task_id_hex,          # pipeline uses paper_{task_id_hex} for its dir
                progress_callback=cb,
                logger=logger,
                enable_indexing=not body.fast,
            )
            record.status = "done"
            cb(100, str(result))
        except Exception as exc:
            record.status = "error"
            cb(0, str(exc), err=True)

    asyncio.create_task(_run())
    return {"task_id": record.task_id, "status": record.status, "created_at": record.created_at}


@router.get("/api/tasks")
async def list_tasks():
    return [
        {"task_id": r.task_id, "status": r.status, "created_at": r.created_at}
        for r in TaskManager.get().all_tasks()
    ]


@router.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    record = TaskManager.get().lookup(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    artifacts: list[str] = []
    if record.output_dir.exists():
        for p in sorted(record.output_dir.rglob("*")):
            if p.is_file():
                try:
                    artifacts.append(str(p.relative_to(record.output_dir)))
                except ValueError:
                    pass
    return {"task_id": record.task_id, "status": record.status,
            "created_at": record.created_at, "artifacts": artifacts}


@router.get("/api/tasks/{task_id}/artifacts/{artifact_path:path}")
async def get_artifact(task_id: str, artifact_path: str):
    record = TaskManager.get().lookup(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    file_path = (record.output_dir / artifact_path).resolve()
    try:
        file_path.relative_to(record.output_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"Artifact {artifact_path} not found")
    return FileResponse(file_path)
```

- [ ] **Step 4: Create api/server.py**

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import events, tasks
from api.task_manager import TaskManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    TaskManager.get().restore_from_disk()
    yield


app = FastAPI(title="paper2code API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks.router)
app.include_router(events.router)
```

- [ ] **Step 5: Run route tests**

```bash
pytest tests/test_api/test_routes_tasks.py -v
```
Expected: 7 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add api/routes/tasks.py api/server.py tests/test_api/test_routes_tasks.py
git commit -m "feat: add task CRUD routes and FastAPI app with CORS"
```

---

### Task 6: Entry point and end-to-end smoke test

**Files:**
- Create: `serve.py`

- [ ] **Step 1: Create serve.py**

```python
#!/usr/bin/env python3
"""HTTP server entry point.

Usage:
    python serve.py           # default port 8000
    PORT=9000 python serve.py
"""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("api.server:app", host="0.0.0.0", port=port, reload=False)
```

- [ ] **Step 2: Run the full test suite**

```bash
pytest tests/test_api/ -v
```
Expected: all tests PASS.

- [ ] **Step 3: Smoke test — start server**

In one terminal:
```bash
python serve.py
```
Expected:
```
INFO:     Started server process [...]
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

- [ ] **Step 4: Smoke test — verify list endpoint**

```bash
curl -s http://localhost:8000/api/tasks | python -m json.tool
```
Expected: `[]`

- [ ] **Step 5: Smoke test — verify SSE returns 404 for unknown task**

```bash
curl -s http://localhost:8000/api/tasks/nonexistent/events
```
Expected: `{"detail":"Task nonexistent not found"}`

- [ ] **Step 6: Smoke test — verify historical task appears**

```bash
curl -s http://localhost:8000/api/tasks | python -m json.tool
```
Expected: lists any previously completed tasks from `output/tasks/` (e.g. `paper_87d8010e` with status `done`).

- [ ] **Step 7: Commit**

```bash
git add serve.py
git commit -m "feat: add serve.py HTTP server entry point"
```
