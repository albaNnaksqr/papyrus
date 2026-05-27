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
    known_files: set[str] = field(default_factory=set, repr=False, compare=False)
    result_summary: str | None = field(default=None, repr=False, compare=False)
    error_message: str | None = field(default=None, repr=False, compare=False)
    pdf_path: str | None = field(default=None, repr=False, compare=False)
    task: asyncio.Task | None = field(default=None, repr=False, compare=False)


def append_event(record: TaskRecord, event: dict[str, Any]) -> None:
    events_path = record.output_dir / "logs" / "events.jsonl"
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with open(events_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def read_events(record: TaskRecord) -> list[dict[str, Any]]:
    events_path = record.output_dir / "logs" / "events.jsonl"
    if not events_path.exists():
        return []

    events: list[dict[str, Any]] = []
    for line in events_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


class TaskManager:
    _instance: TaskManager | None = None

    def __init__(self) -> None:
        self._tasks: dict[str, TaskRecord] = {}

    @classmethod
    def get(cls) -> TaskManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def create(self, task_id: str, pdf_path: str | None = None) -> TaskRecord:
        output_dir = OUTPUT_ROOT / task_id
        output_dir.mkdir(parents=True, exist_ok=True)
        record = TaskRecord(
            task_id=task_id,
            status="pending",
            created_at=_utcnow(),
            output_dir=output_dir,
            pdf_path=pdf_path,
        )
        self._tasks[task_id] = record
        return record

    def lookup(self, task_id: str) -> TaskRecord | None:
        return self._tasks.get(task_id)

    def remove(self, task_id: str) -> None:
        self._tasks.pop(task_id, None)

    def all_tasks(self) -> list[TaskRecord]:
        return list(self._tasks.values())

    def restore_from_disk(self) -> None:
        if not OUTPUT_ROOT.exists():
            return
        terminal_types = {"done", "error", "interrupted"}
        for task_dir in sorted(OUTPUT_ROOT.iterdir()):
            if not task_dir.is_dir():
                continue
            task_id = task_dir.name
            if task_id in self._tasks:
                continue
            events_path = task_dir / "logs" / "events.jsonl"
            status = "interrupted"
            if events_path.exists():
                lines = [
                    line
                    for line in events_path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
                if lines:
                    status = self._infer_status_from_lines(lines, terminal_types, task_dir)
                else:
                    status = self._infer_status_from_artifacts(task_dir) or status
            else:
                status = self._infer_status_from_artifacts(task_dir) or status
            self._tasks[task_id] = TaskRecord(
                task_id=task_id,
                status=status,
                created_at=_utcnow(),
                output_dir=task_dir,
            )

    @staticmethod
    def _text_indicates_pipeline_failure(text: str) -> bool:
        lowered = text.lower()
        markers = (
            "'status': 'incomplete'",
            '"status": "incomplete"',
            "'status': 'error'",
            '"status": "error"',
            "finished early",
            "max_iterations",
            "max iterations",
            "unimplemented",
            "validation failed",
            "error collecting",
        )
        return any(marker in lowered for marker in markers)

    @classmethod
    def _infer_status_from_artifacts(cls, task_dir: Path) -> str | None:
        report_paths = (
            task_dir / "code_implementation_report.txt",
            task_dir / "validation_report.md",
        )
        for report_path in report_paths:
            if not report_path.exists():
                continue
            try:
                text = report_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if cls._text_indicates_pipeline_failure(text):
                return "error"

        done_markers = (
            "validation_report.md",
            "critique_report.md",
            "implement_code_summary.md",
        )
        if any((task_dir / name).exists() for name in done_markers):
            return "done"
        return None

    @classmethod
    def _infer_status_from_lines(
        cls,
        lines: list[str],
        terminal_types: set[str],
        task_dir: Path,
    ) -> str:
        saw_progress = False
        for line in reversed(lines):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            event_type = event.get("type")
            if event_type in terminal_types:
                if event_type == "done":
                    terminal_text = " ".join(
                        str(event.get(key, "")) for key in ("summary", "message")
                    )
                    if cls._text_indicates_pipeline_failure(terminal_text):
                        return "error"
                return event_type
            if event_type == "progress":
                saw_progress = True
                pct = event.get("pct")
                if isinstance(pct, int) and pct >= 100:
                    message = str(event.get("message", "")).lower()
                    if (
                        cls._text_indicates_pipeline_failure(message)
                        or "失败" in message
                        or "fail" in message
                    ):
                        return "error"
                    return "done"
                continue
        artifact_status = cls._infer_status_from_artifacts(task_dir)
        if artifact_status and (artifact_status == "error" or not saw_progress):
            return artifact_status
        return "interrupted"


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
        path = ref.get("file_path", "")
        if path:
            record.known_files.add(path)
        events.append({
            "type": "file_written",
            "path": path,
            "phase": "impl",
            "section_ref": ref.get("section_ref", ""),
            "ts": ref.get("timestamp", _utcnow()),
        })
    return events


def _check_generated_files(record: TaskRecord) -> list[dict[str, Any]]:
    code_dir = record.output_dir / "generate_code"
    if not code_dir.is_dir():
        return []
    events = []
    for path in sorted(code_dir.rglob("*")):
        if not path.is_file():
            continue
        try:
            rel = str(path.relative_to(code_dir))
        except ValueError:
            continue
        if rel in record.known_files:
            continue
        record.known_files.add(rel)
        events.append({
            "type": "file_written",
            "path": rel,
            "phase": "impl",
            "ts": _utcnow(),
        })
    return events


def make_callback(record: TaskRecord):
    def callback(pct: int, msg: str, err: object = None) -> None:
        for fw_event in _check_paper_refs(record):
            record.queue.put_nowait(fw_event)
            append_event(record, fw_event)
        for fw_event in _check_generated_files(record):
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
