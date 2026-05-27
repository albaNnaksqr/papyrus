from __future__ import annotations

import asyncio
import os
import shutil
from datetime import datetime, timezone
import time
import tempfile
import zipfile
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from api.task_manager import TaskManager, append_event, make_callback, read_events


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()

router = APIRouter()

PAPERS_ROOT = Path(__file__).resolve().parent.parent.parent / "papers"


class CreateTaskBody(BaseModel):
    pdf_path: str | None = None
    fast: bool = False
    no_critique: bool = False


def _terminal_state_from_pipeline_result(result: object) -> tuple[str, str]:
    """Map pipeline output to the public terminal task state.

    Demo-friendly: only mark error when the pipeline actually failed to
    produce code (orchestrator-level error or incomplete implementation).
    Post-generation gate failures (quality, smoke, reproduction
    validation) become soft signals — status stays 'done' and details
    are written to known_issues.md in the paper dir so the user can
    inspect them without the UI surfacing a red 'error' state.
    """
    summary = str(result)
    if not isinstance(result, dict):
        return "done", summary

    summary = str(result.get("summary") or result)
    pipeline_status = str(result.get("status", "")).lower()
    implementation = result.get("implementation") or {}
    quality = result.get("quality") if isinstance(result.get("quality"), dict) else {}
    smoke = result.get("smoke") if isinstance(result.get("smoke"), dict) else {}
    validation = (
        result.get("validation")
        if isinstance(result.get("validation"), dict)
        else {}
    )

    implementation_status = ""
    implementation_inner = ""
    if isinstance(implementation, dict):
        implementation_status = str(implementation.get("status", "")).lower()
        implementation_inner = str(implementation.get("inner_status", "")).lower()

    # Hard failure = implementation didn't produce code. The orchestrator's
    # pipeline_status is intentionally NOT checked here: it gets flipped to
    # "error" by _status_after_quality_gate / _status_after_validation when
    # post-gen gates complain, even though implementation succeeded. Those
    # gate failures are soft signals — see known_issues.md, not red banners.
    hard_failed = (
        implementation_status in {"error", "incomplete"}
        or implementation_inner
        in {"error", "incomplete", "max_iterations", "max_time", "aborted"}
    )

    if hard_failed:
        if (
            implementation_status == "incomplete"
            or pipeline_status == "incomplete"
        ) and "incomplete" not in summary.lower():
            summary = f"Pipeline incomplete: {summary}"
        # On hard failure the post-gen gates cascade ("no Python files",
        # "missing entrypoint", smoke can't find file) — those aren't
        # useful "known issues", just noise echoing the real error.
        return "error", summary

    issue_count = _write_known_issues(
        result.get("paper_dir"), quality, smoke, validation
    )
    if issue_count > 0:
        summary = (
            f"{summary} ({issue_count} known issue(s) — see known_issues.md)"
        )
    return "done", summary


def _write_known_issues(
    paper_dir: object,
    quality: dict[str, object],
    smoke: dict[str, object],
    validation: dict[str, object],
) -> int:
    """Persist post-generation gate failures to known_issues.md.

    Returns the number of issue sections collected. When there are no
    issues, removes any stale known_issues.md from a previous run.
    Filesystem errors are swallowed (the file is informational only).
    """
    quality_status = str(quality.get("status", "")).lower()
    smoke_status = str(smoke.get("status", "")).lower()
    validation_status = str(validation.get("status", "")).lower()

    sections: list[tuple[str, list[str]]] = []
    if quality_status == "error":
        failures = quality.get("failures", []) or []
        sections.append(("Quality gate", [str(f) for f in failures]))
    if smoke_status == "error":
        details: list[str] = []
        for check in smoke.get("checks", []) or []:
            if not isinstance(check, dict) or check.get("status") != "error":
                continue
            command = " ".join(str(p) for p in check.get("command", []) or [])
            stderr = str(check.get("stderr") or check.get("error") or "").strip()
            if stderr:
                stderr = stderr.splitlines()[0][:200]
            details.append(
                f"`{command}` → {stderr}" if stderr else f"`{command}` failed"
            )
        sections.append(("Smoke checks", details or ["(see logs)"]))
    if validation_status in {"error", "partial", "failed"}:
        details = []
        passed = validation.get("passed")
        failed = validation.get("failed")
        if passed is not None or failed is not None:
            details.append(f"passed: {passed}, failed: {failed}")
        reason = validation.get("reason")
        if reason:
            details.append(str(reason))
        sections.append(
            ("Reproduction validation", details or [f"status: {validation_status}"])
        )

    if not paper_dir:
        return len(sections)

    path = os.path.join(str(paper_dir), "known_issues.md")
    if not sections:
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass
        return 0

    lines = [
        "# Known issues",
        "",
        "Pipeline completed and code was generated, but post-generation",
        "checks flagged the following. These do not block the run.",
        "",
    ]
    for title, items in sections:
        lines.append(f"## {title}")
        lines.append("")
        for item in items:
            lines.append(f"- {item}")
        lines.append("")

    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except OSError:
        pass
    return len(sections)


@router.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")
    PAPERS_ROOT.mkdir(parents=True, exist_ok=True)
    filename = Path(file.filename).name  # strips any directory components
    stem = Path(filename).stem
    target = PAPERS_ROOT / filename
    if target.exists():
        filename = f"{stem}_{int(time.time())}.pdf"
        target = PAPERS_ROOT / filename
    with open(target, "wb") as fh:
        shutil.copyfileobj(file.file, fh)
    return {"path": f"papers/{filename}", "filename": filename}


@router.get("/api/papers/{filename}")
async def get_paper(filename: str):
    PAPERS_ROOT.mkdir(parents=True, exist_ok=True)
    file_path = (PAPERS_ROOT / filename).resolve()
    try:
        file_path.relative_to(PAPERS_ROOT.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"File {filename} not found")
    return FileResponse(file_path)


@router.post("/api/tasks", status_code=202)
async def create_task(body: CreateTaskBody):
    task_id_hex = uuid.uuid4().hex[:8]
    api_task_id = f"paper_{task_id_hex}"
    manager = TaskManager.get()
    record = manager.create(api_task_id, pdf_path=body.pdf_path)
    cb = make_callback(record)
    def _append_terminal_event(event_type: str, payload: dict[str, object]) -> None:
        append_event(record, {"type": event_type, "ts": _utcnow(), **payload})

    async def _run() -> None:
        from loguru import logger
        from workflows.agent_orchestration_engine import execute_multi_agent_research_pipeline
        try:
            record.status = "running"
            result = await execute_multi_agent_research_pipeline(
                input_source=body.pdf_path,
                task_id=task_id_hex,          # pipeline uses paper_{task_id_hex} for its dir
                progress_callback=cb,
                logger=logger,
                enable_indexing=not body.fast,
                no_critique=body.no_critique,
            )
            terminal_status, terminal_message = _terminal_state_from_pipeline_result(result)
            record.result_summary = terminal_message
            record.status = terminal_status
            if terminal_status == "error":
                record.error_message = terminal_message
                _append_terminal_event("error", {"message": terminal_message})
            else:
                _append_terminal_event("done", {"pct": 100, "summary": terminal_message})
            record.queue.put_nowait(None)          # wake up SSE generator
        except asyncio.CancelledError:
            record.status = "interrupted"
            record.error_message = "已被用户停止"
            _append_terminal_event("interrupted", {"message": record.error_message})
            cb(0, "已被用户停止", err=False)
            record.queue.put_nowait(None)
            raise
        except Exception as exc:
            record.error_message = str(exc)
            record.status = "error"
            _append_terminal_event("error", {"message": record.error_message})
            cb(0, str(exc), err=True)

    record.task = asyncio.create_task(_run())
    return {"task_id": record.task_id, "status": record.status, "created_at": record.created_at}


@router.post("/api/tasks/{task_id}/stop", status_code=202)
async def stop_task(task_id: str):
    record = TaskManager.get().lookup(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    if record.status not in ("running", "pending"):
        raise HTTPException(status_code=409, detail=f"任务状态为 {record.status}，无法停止")
    if record.task is None or record.task.done():
        raise HTTPException(status_code=409, detail="任务句柄已不存在，可能已结束")
    record.task.cancel()
    return {"task_id": record.task_id, "status": "stopping"}


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
    return {
        "task_id": record.task_id,
        "status": record.status,
        "created_at": record.created_at,
        "artifacts": artifacts,
        "pdf_path": record.pdf_path,
        "events": read_events(record),
    }


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


@router.get("/api/tasks/{task_id}/export")
async def export_task(task_id: str, background_tasks: BackgroundTasks):
    record = TaskManager.get().lookup(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    if record.status in ("pending", "running"):
        raise HTTPException(status_code=409, detail="任务尚未完成，暂不支持导出")
    if not record.output_dir.exists():
        raise HTTPException(status_code=404, detail=f"任务目录 {task_id} 不存在")

    fd, zip_path = tempfile.mkstemp(suffix=".zip", prefix=f"{task_id}_")
    os.close(fd)

    archive_path = Path(zip_path)
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(record.output_dir.rglob("*")):
            if not file_path.is_file():
                continue
            arc_name = str(Path(task_id) / file_path.relative_to(record.output_dir))
            zf.write(file_path, arc_name)

    filename = f"{task_id}_artifacts.zip"
    def _cleanup_export(path: Path) -> None:
        path.unlink(missing_ok=True)

    background_tasks.add_task(_cleanup_export, archive_path)
    return FileResponse(
        path=archive_path,
        filename=filename,
        media_type="application/zip",
        background=background_tasks,
    )


@router.delete("/api/tasks/{task_id}", status_code=204)
async def delete_task(task_id: str):
    manager = TaskManager.get()
    record = manager.lookup(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    if record.status in ("running", "pending"):
        raise HTTPException(status_code=409, detail="运行中或等待中的任务无法删除")
    manager.remove(task_id)
    if record.output_dir.exists():
        shutil.rmtree(record.output_dir)
    return Response(status_code=204)
