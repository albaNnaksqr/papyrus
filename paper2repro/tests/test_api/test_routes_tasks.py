import io
import zipfile

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


def test_get_task_returns_persisted_events(client):
    from api.task_manager import append_event

    mgr = TaskManager.get()
    record = mgr.create("paper_events")
    append_event(
        record,
        {
            "type": "progress",
            "pct": 85,
            "message": "Code implementation progress: 2/30 files completed",
            "ts": "2026-05-25T03:02:00+00:00",
        },
    )
    append_event(
        record,
        {
            "type": "file_written",
            "path": "src/main.py",
            "phase": "impl",
            "ts": "2026-05-25T03:02:01+00:00",
        },
    )

    resp = client.get("/api/tasks/paper_events")

    assert resp.status_code == 200
    body = resp.json()
    assert body["events"][0]["pct"] == 85
    assert body["events"][0]["message"].startswith("Code implementation progress")
    assert body["events"][1]["path"] == "src/main.py"


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


def test_export_task_archive_includes_artifacts(client, tmp_path):
    mgr = TaskManager.get()
    record = mgr.create("paper_export")
    record.status = "done"
    (record.output_dir / "generate_code").mkdir()
    (record.output_dir / "generate_code" / "main.py").write_text("print('hello')")
    (record.output_dir / "document_segments").mkdir()
    (record.output_dir / "document_segments" / "segment_0001.md").write_text("chunk")

    resp = client.get("/api/tasks/paper_export/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/zip")

    archive = zipfile.ZipFile(io.BytesIO(resp.content))
    names = set(archive.namelist())
    assert "paper_export/generate_code/main.py" in names
    assert "paper_export/document_segments/segment_0001.md" in names


def test_export_task_blocked_when_running(client):
    mgr = TaskManager.get()
    record = mgr.create("paper_export2")
    record.status = "running"
    resp = client.get("/api/tasks/paper_export2/export")
    assert resp.status_code == 409


def test_upload_pdf_returns_path(tmp_path, monkeypatch, client):
    import api.routes.tasks as tasks_mod
    monkeypatch.setattr(tasks_mod, "PAPERS_ROOT", tmp_path)
    pdf_bytes = b"%PDF-1.4 fake"
    resp = client.post("/api/upload", files={"file": ("test.pdf", io.BytesIO(pdf_bytes), "application/pdf")})
    assert resp.status_code == 200
    body = resp.json()
    assert body["filename"] == "test.pdf"
    assert body["path"].startswith("papers/")


def test_upload_rejects_non_pdf(tmp_path, monkeypatch, client):
    import api.routes.tasks as tasks_mod
    monkeypatch.setattr(tasks_mod, "PAPERS_ROOT", tmp_path)
    resp = client.post("/api/upload", files={"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")})
    assert resp.status_code == 400


def test_get_paper_serves_file(tmp_path, monkeypatch, client):
    import api.routes.tasks as tasks_mod
    monkeypatch.setattr(tasks_mod, "PAPERS_ROOT", tmp_path)
    (tmp_path / "sample.pdf").write_bytes(b"%PDF-1.4 fake")
    resp = client.get("/api/papers/sample.pdf")
    assert resp.status_code == 200


def test_get_paper_path_traversal_blocked(tmp_path, monkeypatch, client):
    import api.routes.tasks as tasks_mod
    monkeypatch.setattr(tasks_mod, "PAPERS_ROOT", tmp_path)
    # Create a file outside PAPERS_ROOT
    outside_file = tmp_path.parent / "secret.pdf"
    outside_file.write_bytes(b"%PDF secret")
    # Create a symlink inside PAPERS_ROOT that points outside
    (tmp_path / "escape.pdf").symlink_to(outside_file)
    resp = client.get("/api/papers/escape.pdf")
    # The resolved path of the symlink is outside PAPERS_ROOT, so must be blocked
    assert resp.status_code in (403, 404)
    outside_file.unlink()


def test_upload_sanitizes_path_traversal_filename(tmp_path, monkeypatch, client):
    import api.routes.tasks as tasks_mod
    monkeypatch.setattr(tasks_mod, "PAPERS_ROOT", tmp_path)
    pdf_bytes = b"%PDF-1.4 fake"
    resp = client.post(
        "/api/upload",
        files={"file": ("../evil.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    )
    # Must succeed (upload is valid PDF bytes), but file must land inside tmp_path
    assert resp.status_code == 200
    assert resp.json()["filename"] == "evil.pdf"
    assert (tmp_path / "evil.pdf").exists()
    assert not (tmp_path.parent / "evil.pdf").exists()


def test_get_task_returns_pdf_path(client):
    from api.task_manager import TaskManager
    TaskManager._instance = None
    manager = TaskManager.get()
    record = manager.create("paper_test01", pdf_path="papers/lora.pdf")
    resp = client.get("/api/tasks/paper_test01")
    assert resp.status_code == 200
    assert resp.json()["pdf_path"] == "papers/lora.pdf"
    TaskManager._instance = None


def test_pipeline_incomplete_maps_to_error_terminal_state():
    """Hard failure: implementation didn't produce code. Still error."""
    from api.routes.tasks import _terminal_state_from_pipeline_result

    status, message = _terminal_state_from_pipeline_result(
        {
            "status": "incomplete",
            "summary": "Code implementation finished EARLY",
            "implementation": {"status": "incomplete"},
            "validation": {"status": "error", "passed": 0, "failed": 0},
        }
    )

    assert status == "error"
    assert "incomplete" in message.lower()


def test_pipeline_validation_error_maps_to_done_with_known_issue(tmp_path):
    """Demo-friendly: validation failure no longer flips status to error.
    Implementation succeeded → status=done; issue written to known_issues.md."""
    from api.routes.tasks import _terminal_state_from_pipeline_result

    status, message = _terminal_state_from_pipeline_result(
        {
            "status": "completed",
            "summary": "Implementation completed",
            "implementation": {"status": "success", "inner_status": "completed"},
            "validation": {"status": "error", "passed": 0, "failed": 0, "reason": "import error"},
            "paper_dir": str(tmp_path),
        }
    )

    assert status == "done"
    assert "known_issues" in message.lower()
    issues_file = tmp_path / "known_issues.md"
    assert issues_file.exists()
    text = issues_file.read_text(encoding="utf-8")
    assert "Reproduction validation" in text


def test_pipeline_quality_error_maps_to_done_with_known_issue(tmp_path):
    """Demo-friendly: quality failures become soft signals."""
    from api.routes.tasks import _terminal_state_from_pipeline_result

    status, message = _terminal_state_from_pipeline_result(
        {
            "status": "completed",
            "summary": "Implementation completed",
            "implementation": {"status": "success", "inner_status": "completed"},
            "quality": {"status": "error", "failures": ["Found empty Python files"]},
            "validation": {"status": "success", "passed": 1, "failed": 0},
            "paper_dir": str(tmp_path),
        }
    )

    assert status == "done"
    issues_file = tmp_path / "known_issues.md"
    assert issues_file.exists()
    text = issues_file.read_text(encoding="utf-8")
    assert "Quality gate" in text
    assert "Found empty Python files" in text


def test_pipeline_smoke_error_maps_to_done_with_known_issue(tmp_path):
    """Demo-friendly: smoke failures become soft signals."""
    from api.routes.tasks import _terminal_state_from_pipeline_result

    status, message = _terminal_state_from_pipeline_result(
        {
            "status": "completed",
            "summary": "Implementation completed",
            "implementation": {"status": "success", "inner_status": "completed"},
            "quality": {"status": "success"},
            "smoke": {
                "status": "error",
                "checks": [
                    {
                        "status": "error",
                        "command": ["python", "main.py", "--help"],
                        "stderr": "ModuleNotFoundError: No module named 'foo'",
                    }
                ],
            },
            "validation": {"status": "success"},
            "paper_dir": str(tmp_path),
        }
    )

    assert status == "done"
    issues_file = tmp_path / "known_issues.md"
    assert issues_file.exists()
    text = issues_file.read_text(encoding="utf-8")
    assert "Smoke checks" in text


def test_pipeline_all_gates_pass_writes_no_known_issues_file(tmp_path):
    """Healthy run: no known_issues.md created."""
    from api.routes.tasks import _terminal_state_from_pipeline_result

    status, message = _terminal_state_from_pipeline_result(
        {
            "status": "completed",
            "summary": "All good",
            "implementation": {"status": "success", "inner_status": "completed"},
            "quality": {"status": "success"},
            "smoke": {"status": "success"},
            "validation": {"status": "success", "passed": 3, "failed": 0},
            "paper_dir": str(tmp_path),
        }
    )

    assert status == "done"
    assert not (tmp_path / "known_issues.md").exists()


def test_pipeline_orchestrator_flipped_status_still_done(tmp_path):
    """The orchestrator flips its own pipeline_status to 'error' when
    post-gen gates fail (via _status_after_quality_gate etc), even when
    implementation succeeded. Demo-friendly mapping must look at
    implementation_status (the real signal) — not the orchestrator's
    derived pipeline_status — to decide hard failure.
    """
    from api.routes.tasks import _terminal_state_from_pipeline_result

    status, _ = _terminal_state_from_pipeline_result(
        {
            # Orchestrator flipped this from 'completed' after quality failed
            "status": "error",
            "summary": "Code implementation completed successfully but quality gate failed",
            "implementation": {"status": "success", "inner_status": "completed"},
            "quality": {
                "status": "error",
                "failures": ["README advertises missing files: hyper_kggen/__init__.py"],
            },
            "smoke": {"status": "success"},
            "validation": {"status": "success"},
            "paper_dir": str(tmp_path),
        }
    )

    assert status == "done"
    assert (tmp_path / "known_issues.md").exists()


def test_pipeline_hard_failure_does_not_write_known_issues(tmp_path):
    """When implementation crashes (LLM down, max_iterations), the post-gen
    gates run on an empty/incomplete tree and report cascading 'no Python files'
    failures. Surfacing those in known_issues.md is misleading — the real
    error is already in the terminal message."""
    from api.routes.tasks import _terminal_state_from_pipeline_result

    status, _ = _terminal_state_from_pipeline_result(
        {
            "status": "error",
            "summary": "LLM request failed during implementation",
            "implementation": {"status": "error", "inner_status": "error"},
            "quality": {
                "status": "error",
                "failures": ["Generated code directory contains no Python files"],
            },
            "smoke": {"status": "error"},
            "paper_dir": str(tmp_path),
        }
    )

    assert status == "error"
    # No known_issues.md on hard failure; the error itself tells the story.
    assert not (tmp_path / "known_issues.md").exists()


def test_pipeline_known_issues_file_replaced_on_rerun(tmp_path):
    """A previous run's stale known_issues.md gets removed on a clean rerun."""
    from api.routes.tasks import _terminal_state_from_pipeline_result

    stale = tmp_path / "known_issues.md"
    stale.write_text("# old issues\n", encoding="utf-8")

    _terminal_state_from_pipeline_result(
        {
            "status": "completed",
            "summary": "All good",
            "implementation": {"status": "success", "inner_status": "completed"},
            "quality": {"status": "success"},
            "smoke": {"status": "success"},
            "validation": {"status": "success"},
            "paper_dir": str(tmp_path),
        }
    )

    assert not stale.exists()
