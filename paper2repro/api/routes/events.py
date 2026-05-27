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


def _read_last_event_type(record: TaskRecord) -> str | None:
    events_path = record.output_dir / "logs" / "events.jsonl"
    if not events_path.exists():
        return None
    lines = events_path.read_text(encoding="utf-8").splitlines()
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        return event.get("type")
    return None


async def _event_generator(
    request: Request, record: TaskRecord, last_event_id: int | None
) -> AsyncIterator[str]:
    event_index = -1 if last_event_id is None else last_event_id

    # Replay disk history when reconnecting OR when the task is already terminal.
    # The terminal case lets a fresh page load on a done task see the full timeline;
    # otherwise the SSE would only emit the synthesized terminal event.
    needs_replay = last_event_id is not None or record.status in (
        "done", "error", "interrupted"
    )
    if needs_replay:
        start = last_event_id if last_event_id is not None else -1
        async for event, idx in _replay_from_file(record, after_id=start):
            if await request.is_disconnected():
                return
            event_index = idx
            yield _format_sse(event, event_id=idx)

    while record.status not in ("done", "error", "interrupted"):
        if await request.is_disconnected():
            return
        try:
            event = await asyncio.wait_for(record.queue.get(), timeout=25)
            if event is None:
                continue  # sentinel: task status changed, re-check while condition
            event_index += 1
            yield _format_sse(event, event_id=event_index)
        except asyncio.TimeoutError:
            yield _format_sse(None, event_id=None)

    terminal_from_disk = _read_last_event_type(record)
    if record.status == "done":
        terminal = {"type": "done", "pct": 100, "summary": record.result_summary or ""}
    elif record.status == "error":
        terminal = {"type": record.status, "message": record.error_message or ""}
    else:
        terminal = {"type": record.status, "message": record.error_message or ""}

    if terminal_from_disk not in ("done", "error", "interrupted"):
        yield _format_sse(terminal, event_id=event_index + 1)


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
