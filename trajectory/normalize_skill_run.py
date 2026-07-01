from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trajectory import SCHEMA_VERSION
from trajectory.reward import compute_reward


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _read_text(path: Path) -> str | None:
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def _read_first_jsonl(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped:
            return json.loads(stripped)
    return None


def _normalize_evaluation_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    if not normalized.get("status") and normalized.get("verdict"):
        normalized["status"] = normalized["verdict"]
    verdicts = normalized.get("verdicts")
    if isinstance(verdicts, list):
        fully = [item for item in verdicts if item.get("verdict") == "fully_reproduced"]
        approx = [
            item for item in verdicts if item.get("verdict") == "approximately_reproduced"
        ]
        missing = [item for item in verdicts if item.get("verdict") == "not_reproduced"]
        normalized.setdefault("fully_reproduced", fully)
        normalized.setdefault("approximately_reproduced", approx)
        normalized.setdefault("not_reproduced", missing)
        if not normalized.get("status"):
            if fully and not approx and not missing and len(fully) == len(verdicts):
                normalized["status"] = "fully_reproduced"
            elif fully or approx:
                normalized["status"] = "approximately_reproduced"
            else:
                normalized["status"] = "not_reproduced"
    return normalized


def _read_evaluation(project_dir: Path) -> dict[str, Any]:
    results_dir = project_dir / "results"
    for name in [
        "reproduction_evaluation.json",
        "evaluation_summary.json",
        "evaluation_result.json",
    ]:
        payload = _read_json(results_dir / name)
        if payload:
            return _normalize_evaluation_payload(payload)
    return {}


def _canonical_tool_name(name: str | None) -> str | None:
    if name == "Bash":
        return "exec_command"
    if name == "Write":
        return "file_write"
    if name in {"Edit", "MultiEdit"}:
        return "file_edit"
    if name == "Read":
        return "read_file"
    return name


def _relative(project_dir: Path, path: Path) -> str:
    return str(path.relative_to(project_dir))


def _existing_files(project_dir: Path) -> list[str]:
    ignored_parts = {"__pycache__", ".pytest_cache", ".mypy_cache"}
    files = []
    for path in sorted(project_dir.rglob("*")):
        if not path.is_file():
            continue
        if any(part in ignored_parts for part in path.relative_to(project_dir).parts):
            continue
        files.append(_relative(project_dir, path))
    return files


def _tool_calls(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    results_by_id = _tool_results_by_id(turns)
    for turn_index, turn in enumerate(turns):
        for call in turn.get("tool_calls") or []:
            tool_call = {
                "turn_index": turn_index,
                "name": _canonical_tool_name(call.get("name")),
                "raw_name": call.get("name"),
                "input": call.get("input") or {},
                "id": call.get("id"),
            }
            if call.get("tool_result") is not None:
                tool_call["tool_result"] = call.get("tool_result")
            elif call.get("id") in results_by_id:
                tool_call["tool_result"] = results_by_id[call.get("id")]
            calls.append(tool_call)
    return calls


def _tool_results_by_id(turns: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for turn in turns:
        for result in turn.get("tool_results") or []:
            tool_use_id = result.get("tool_use_id")
            if tool_use_id:
                results[tool_use_id] = result
        for call in turn.get("tool_calls") or []:
            if call.get("id") and call.get("tool_result") is not None:
                results[call["id"]] = call["tool_result"]
    return results


def _tool_results(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for turn_index, turn in enumerate(turns):
        for result in turn.get("tool_results") or []:
            results.append(
                {
                    "turn_index": turn_index,
                    "tool_call_id": result.get("tool_use_id"),
                    "tool_name": None,
                    "result": result,
                }
            )
        for call in turn.get("tool_calls") or []:
            if "tool_result" not in call:
                continue
            result = call.get("tool_result") or {}
            results.append(
                {
                    "turn_index": turn_index,
                    "tool_call_id": call.get("id"),
                    "tool_name": call.get("name"),
                    "result": result,
                }
            )
    return results


def _is_file_edit_call(call: dict[str, Any]) -> bool:
    return call.get("name") in {"apply_patch", "file_write", "file_edit"}


def _file_edits(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    edits = []
    for call in calls:
        if not _is_file_edit_call(call):
            continue
        edits.append(
            {
                "turn_index": call["turn_index"],
                "tool": call.get("raw_name") or call.get("name"),
                "source": "agent_trace",
            }
        )
    return edits


def _commands(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    commands = []
    for call in calls:
        if call.get("name") != "exec_command":
            continue
        payload = call.get("input") or {}
        commands.append(
            {
                "turn_index": call["turn_index"],
                "cmd": payload.get("cmd"),
                "workdir": payload.get("workdir"),
            }
        )
    return commands


def _call_input(call: dict[str, Any]) -> Any:
    return call.get("input") or {}


def _command_text(call: dict[str, Any]) -> str:
    payload = _call_input(call)
    if isinstance(payload, dict):
        return str(payload.get("cmd") or payload.get("command") or "")
    return ""


def _tool_result(call: dict[str, Any]) -> dict[str, Any]:
    result = call.get("tool_result") or {}
    if not isinstance(result, dict):
        return {}
    return result


def _result_output(result: dict[str, Any]) -> str:
    chunks = []
    for key in ["output", "content", "stdout", "stderr"]:
        value = result.get(key)
        if value is not None:
            chunks.append(str(value))
    return "\n".join(chunks)


def _result_exit_code(result: dict[str, Any]) -> int | None:
    metadata = result.get("metadata")
    if isinstance(metadata, dict) and isinstance(metadata.get("exit_code"), int):
        return metadata["exit_code"]
    output = _result_output(result).strip()
    if not output:
        return None
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        metadata = parsed.get("metadata")
        if isinstance(metadata, dict) and isinstance(metadata.get("exit_code"), int):
            return metadata["exit_code"]
    return None


def _result_failed(call: dict[str, Any]) -> bool:
    result = _tool_result(call)
    if result.get("is_error") is True:
        return True
    exit_code = _result_exit_code(result)
    if exit_code is not None:
        return exit_code != 0
    lowered = _result_output(result).lower()
    return any(
        marker in lowered
        for marker in ["traceback", "assertionerror", "failed", "error:"]
    )


def _result_succeeded(call: dict[str, Any]) -> bool:
    result = _tool_result(call)
    exit_code = _result_exit_code(result)
    if exit_code is not None:
        return exit_code == 0
    lowered = _result_output(result).lower()
    return any(
        marker in lowered
        for marker in ["passed", "smoke pass", "success", "fully_reproduced"]
    )


def _is_read_only_command(command: str) -> bool:
    lowered = command.strip().lower()
    return lowered.startswith(
        (
            "cat ",
            "find ",
            "grep ",
            "head ",
            "ls ",
            "nl ",
            "rg ",
            "sed ",
            "tail ",
            "wc ",
        )
    )


def _is_test_command(command: str) -> bool:
    if _is_read_only_command(command):
        return False
    lowered = command.lower()
    return any(
        marker in lowered
        for marker in [
            "pytest",
            "python -m unittest",
            "unittest discover",
            "run_smoke.py",
            "run_smoke",
        ]
    )


def _is_experiment_command(command: str) -> bool:
    if _is_read_only_command(command):
        return False
    lowered = command.lower()
    return "run_experiment.py" in lowered or "run_experiment" in lowered


def _is_evaluator_command(command: str) -> bool:
    if _is_read_only_command(command):
        return False
    lowered = command.lower()
    return "evaluate_reproduction.py" in lowered or "reproduction_evaluation" in lowered


def _is_validation_command(command: str) -> bool:
    lowered = command.lower()
    return (
        _is_test_command(command)
        or _is_experiment_command(command)
        or _is_evaluator_command(command)
        or "py_compile" in lowered
        or "compileall" in lowered
    )


def _is_paper_inspect_command(command: str) -> bool:
    lowered = command.lower()
    return any(
        marker in lowered
        for marker in ["pdfinfo", "pdftotext", "parse_pdf", ".pdf", "paper_structure"]
    )


def _failure_type_for_command(command: str, output: str) -> str:
    lowered = f"{command}\n{output}".lower()
    if "pytest" in lowered or "failed" in lowered or "assertionerror" in lowered:
        return "pytest_failure"
    if "evaluate" in lowered:
        return "evaluator_failure"
    return "command_failure"


def _patch_text(call: dict[str, Any]) -> str:
    payload = _call_input(call)
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        for key in ["patch", "content", "input"]:
            value = payload.get(key)
            if isinstance(value, str):
                return value
    return ""


def _normalize_patch_path(path: str, project_path: Path) -> str:
    cleaned = path.strip().strip('"').strip("'")
    for prefix in ["a/", "b/"]:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
    candidate = Path(cleaned)
    if candidate.is_absolute():
        try:
            return str(candidate.relative_to(project_path))
        except ValueError:
            return cleaned
    parts = candidate.parts
    if project_path.name in parts:
        index = len(parts) - 1 - list(reversed(parts)).index(project_path.name)
        tail = parts[index + 1 :]
        if tail:
            return str(Path(*tail))
    return cleaned


def _patch_files(patch_text: str, project_path: Path) -> list[str]:
    files: list[str] = []
    for line in patch_text.splitlines():
        path = None
        if line.startswith(("*** Add File: ", "*** Update File: ", "*** Delete File: ")):
            path = line.split(": ", 1)[1]
        elif line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                path = parts[3]
        elif line.startswith("+++ ") and not line.startswith("+++ /dev/null"):
            path = line.split(maxsplit=1)[1]
        if not path:
            continue
        normalized = _normalize_patch_path(path, project_path)
        if normalized and normalized != "/dev/null" and normalized not in files:
            files.append(normalized)
    return files


def _patch_operation(patch_text: str) -> str:
    if "*** Add File: " in patch_text:
        return "create"
    if "*** Delete File: " in patch_text:
        return "delete"
    return "update"


def _patch_line_counts(patch_text: str) -> tuple[int, int]:
    added = 0
    deleted = 0
    for line in patch_text.splitlines():
        if line.startswith(("+++", "---", "***")):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            deleted += 1
    return added, deleted


def _edit_role(path: str) -> str:
    lowered = path.lower().lstrip("./")
    name = Path(lowered).name
    if name in {"reproduction_contract.json", "paper_structure.json"}:
        return "contract"
    if name in {"ambiguity_audit.md", "gap_report.md", "claim_contract.json"}:
        return "contract"
    if name == "reproduction_report.md" or ("report" in name and lowered.endswith(".md")):
        return "report"
    if lowered.startswith("tests/") or "/tests/" in lowered or name.startswith("test_"):
        return "test"
    if "evaluate" in name:
        return "evaluator"
    if lowered.startswith("scripts/"):
        return "script"
    if lowered.startswith("configs/") or name.endswith(".json"):
        return "config"
    if lowered.startswith("src/") or name.endswith(".py"):
        return "implementation"
    return "other"


def _ordered_roles(files: list[str]) -> list[str]:
    order = [
        "contract",
        "implementation",
        "test",
        "script",
        "evaluator",
        "config",
        "report",
        "other",
    ]
    roles = {_edit_role(path) for path in files}
    return [role for role in order if role in roles]


def _edit_metadata(calls: list[dict[str, Any]], project_path: Path) -> list[dict[str, Any]]:
    edits = []
    for call in calls:
        if not _is_file_edit_call(call):
            continue
        payload = _call_input(call)
        if call.get("name") == "apply_patch":
            patch = _patch_text(call)
            files = _patch_files(patch, project_path)
            added, deleted = _patch_line_counts(patch)
            operation = _patch_operation(patch)
        else:
            path = payload.get("file_path") if isinstance(payload, dict) else None
            files = [_normalize_patch_path(str(path), project_path)] if path else []
            operation = "write" if call.get("name") == "file_write" else "update"
            if isinstance(payload, dict) and call.get("name") == "file_write":
                added = len(str(payload.get("content") or "").splitlines())
                deleted = 0
            elif isinstance(payload, dict) and isinstance(payload.get("edits"), list):
                added = sum(
                    len(str(edit.get("new_string") or "").splitlines())
                    for edit in payload["edits"]
                    if isinstance(edit, dict)
                )
                deleted = sum(
                    len(str(edit.get("old_string") or "").splitlines())
                    for edit in payload["edits"]
                    if isinstance(edit, dict)
                )
            elif isinstance(payload, dict):
                added = len(str(payload.get("new_string") or "").splitlines())
                deleted = len(str(payload.get("old_string") or "").splitlines())
            else:
                added = 0
                deleted = 0
        edits.append(
            {
                "turn_index": call["turn_index"],
                "tool_call_id": call.get("id"),
                "operation": operation,
                "files": files,
                "roles": _ordered_roles(files),
                "lines_added": added,
                "lines_deleted": deleted,
            }
        )
    return edits


def _iter_turn_calls(turns: list[dict[str, Any]]) -> list[tuple[int, dict[str, Any]]]:
    return [(call["turn_index"], call) for call in _tool_calls(turns)]


def _failed_exec_calls(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failures = []
    for turn_index, call in _iter_turn_calls(turns):
        if call.get("name") != "exec_command" or not _result_failed(call):
            continue
        command = _command_text(call)
        if not _is_validation_command(command):
            continue
        output = _result_output(_tool_result(call))
        failures.append(
            {
                "turn_index": turn_index,
                "command": command,
                "failure_type": _failure_type_for_command(command, output),
            }
        )
    return failures


def _repair_attempts(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    attempts = []
    pairs = _iter_turn_calls(turns)
    failures = _failed_exec_calls(turns)
    for failure in failures:
        failure_turn = failure["turn_index"]
        edit_turns = [
            turn_index
            for turn_index, call in pairs
            if turn_index > failure_turn and _is_file_edit_call(call)
        ]
        if not edit_turns:
            continue
        first_edit = edit_turns[0]
        verification_turn = None
        verification_command = None
        resolved = False
        for turn_index, call in pairs:
            if turn_index <= first_edit or call.get("name") != "exec_command":
                continue
            command = _command_text(call)
            if not (_is_test_command(command) or _is_evaluator_command(command)):
                continue
            verification_turn = turn_index
            verification_command = command
            resolved = _result_succeeded(call)
            break
        attempts.append(
            {
                "failure_turn": failure_turn,
                "failure_type": failure["failure_type"],
                "failure_command": failure["command"],
                "repair_edit_turns": [
                    turn
                    for turn in edit_turns
                    if verification_turn is None or turn < verification_turn
                ],
                "verification_turn": verification_turn,
                "verification_command": verification_command,
                "resolved": resolved,
            }
        )
    return attempts


def _reflection_events(
    turns: list[dict[str, Any]],
    repair_attempts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    events = []
    failure_turns = [attempt["failure_turn"] for attempt in repair_attempts]
    edit_turns = [turn for attempt in repair_attempts for turn in attempt["repair_edit_turns"]]
    markers = [
        "failed",
        "failure",
        "root cause",
        "i see",
        "adjust",
        "instead",
        "wrong",
        "error",
        "traceback",
        "失败",
        "原因",
        "修复",
    ]
    for turn_index, turn in enumerate(turns):
        text = str(turn.get("text") or "")
        lowered = text.lower()
        if not any(marker in lowered for marker in markers):
            continue
        linked_failure = next(
            (failure for failure in reversed(failure_turns) if 0 <= turn_index - failure <= 3),
            None,
        )
        linked_edit = next((edit for edit in edit_turns if turn_index <= edit <= turn_index + 2), None)
        if linked_failure is None or linked_edit is None:
            continue
        events.append(
            {
                "turn_index": turn_index,
                "linked_failure_turn": linked_failure,
                "linked_edit_turn": linked_edit,
                "text": text,
            }
        )
    return events


def _semantic_actions(
    calls: list[dict[str, Any]],
    edit_metadata: list[dict[str, Any]],
    repair_attempts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    edits_by_call = {edit["tool_call_id"]: edit for edit in edit_metadata}
    repair_edit_turns = {turn for attempt in repair_attempts for turn in attempt["repair_edit_turns"]}
    actions = []

    def add(
        action_type: str,
        turn_index: int,
        tool_id: str | None,
        status: str = "observed",
    ) -> None:
        actions.append(
            {
                "type": action_type,
                "turn_index": turn_index,
                "tool_refs": [tool_id] if tool_id else [],
                "status": status,
            }
        )

    for call in calls:
        turn_index = call["turn_index"]
        tool_id = call.get("id")
        if call.get("name") == "exec_command":
            command = _command_text(call)
            if _result_failed(call):
                status = "failure"
            elif _result_succeeded(call):
                status = "success"
            else:
                status = "observed"
            if _is_paper_inspect_command(command):
                add("paper_inspect", turn_index, tool_id, status)
            elif _is_test_command(command):
                add("run_smoke", turn_index, tool_id, status)
            elif _is_experiment_command(command):
                add("run_experiment", turn_index, tool_id, status)
            elif _is_evaluator_command(command):
                add("evaluate", turn_index, tool_id, status)
        elif call.get("name") == "read_file":
            payload = _call_input(call)
            file_path = payload.get("file_path") if isinstance(payload, dict) else ""
            if str(file_path).lower().endswith(".pdf"):
                status = "failure" if _result_failed(call) else "success" if _result_succeeded(call) else "observed"
                add("paper_inspect", turn_index, tool_id, status)
        elif _is_file_edit_call(call):
            edit = edits_by_call.get(tool_id) or {}
            roles = edit.get("roles") or []
            if _result_succeeded(call):
                status = "success"
            elif _result_failed(call):
                status = "failure"
            else:
                status = "observed"
            if turn_index in repair_edit_turns:
                add("repair", turn_index, tool_id, status)
                continue
            if "contract" in roles:
                add("contract_write", turn_index, tool_id, status)
            if any(role in roles for role in ["implementation", "test", "script", "evaluator", "config"]):
                add("implement", turn_index, tool_id, status)
            if "report" in roles:
                add("report", turn_index, tool_id, status)
    return actions


def _failure_types(contract: dict[str, Any], report_text: str | None) -> list[str]:
    gap_items = contract.get("missing_but_required") or []
    assumptions = contract.get("assumptions") or []
    text = json.dumps(gap_items, ensure_ascii=False).lower()
    if report_text:
        text += "\n" + report_text.lower()
    labels: list[str] = []
    if "original benchmark" in text or "original corpora" in text:
        labels.append("unavailable_original_benchmark_data")
    if "pdp-10" in text or "machine-instruction" in text or "instruction-count" in text:
        labels.append("nonportable_hardware_metric")
    if "numeric values" in text or "exact-loss" in text or "relative ranking" in text:
        labels.append("metric_mismatch")
    if "full benchmark" in text or "leaderboard" in text:
        labels.append("full_benchmark_not_attempted")
    if "docker" in text or "conda" in text or "official harness" in text:
        labels.append("environment_gap")
    if "synthetic" in text and "fixture" in text:
        labels.append("synthetic_fixture")
    if any(
        "dataset" in json.dumps(item, ensure_ascii=False).lower()
        and (
            "unavailable" in json.dumps(item, ensure_ascii=False).lower()
            or "not bundled" in json.dumps(item, ensure_ascii=False).lower()
        )
        for item in gap_items
    ):
        labels.append("dataset_unavailable")
    assumption_text = json.dumps(assumptions, ensure_ascii=False).lower()
    if any(
        word in assumption_text
        for word in [
            "learning rate",
            "learning_rate",
            "batch size",
            "batch_size",
            "lambda",
            "momentum",
            "random seed",
            "random_seed",
            "weight_init",
        ]
    ):
        labels.append("hyperparameter_missing")
    if any(
        word in assumption_text
        for word in ["scaled down", "1 million weight updates", "runtime", "cpu execution"]
    ):
        labels.append("compute_budget_limit")
    return labels


def _outcome(evaluation: dict[str, Any] | None) -> str:
    if not evaluation:
        return "invalid_run"
    status = str(evaluation.get("status") or "").lower()
    if status in {"fully_reproduced", "success"}:
        return "success"
    if status in {"approximately_reproduced", "partial", "partial_success"}:
        return "partial_success"
    status_schema = evaluation.get("status_schema")
    if isinstance(status_schema, dict):
        evaluation = status_schema
    full = len(evaluation.get("fully_reproduced") or [])
    approx = len(evaluation.get("approximately_reproduced") or [])
    missing = len(evaluation.get("not_reproduced") or [])
    if full and not approx and not missing:
        return "success"
    if full or approx:
        return "partial_success"
    return "failure"


def _phase_spans(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    active: dict[str, Any] | None = None
    for index, turn in enumerate(turns):
        phase = turn.get("phase")
        if not phase:
            continue
        if active and active["phase"] == phase:
            active["end_turn"] = index
            continue
        if active:
            spans.append(active)
        active = {"phase": phase, "start_turn": index, "end_turn": index}
    if active:
        spans.append(active)
    return spans


def normalize_skill_run(project_dir: str | Path) -> dict[str, Any]:
    project_path = Path(project_dir).resolve()
    trace_path = project_path / "agent_trace.jsonl"
    trace = _read_first_jsonl(trace_path) or {}
    turns = trace.get("turns") or []
    if not isinstance(turns, list):
        turns = []

    paper_structure = _read_json(project_path / "paper_structure.json") or {}
    contract = _read_json(project_path / "reproduction_contract.json") or {}
    evaluation = _read_evaluation(project_path)
    summary = _read_json(project_path / "results" / "reproduction_summary.json") or {}
    ambiguity_audit = _read_text(project_path / "ambiguity_audit.md")
    gap_report = _read_text(project_path / "gap_report.md")
    report_text = _read_text(project_path / "REPRODUCTION_REPORT.md")

    calls = _tool_calls(turns)
    results = _tool_results(turns)
    failure_types = _failure_types(contract, report_text)
    edit_metadata = _edit_metadata(calls, project_path)
    repair_attempts = _repair_attempts(turns)
    reflection_events = _reflection_events(turns, repair_attempts)
    actions = _semantic_actions(calls, edit_metadata, repair_attempts)

    title = contract.get("paper_title") or paper_structure.get("paper_title") or project_path.name
    trace_bounds = trace.get("trace_bounds") or {}
    run_id = trace_bounds.get("run_id") or trace.get("args", {}).get("run_id")

    return {
        "schema_version": SCHEMA_VERSION,
        "paper": {
            "paper_id": project_path.name,
            "title": title,
            "domain": paper_structure.get("domain"),
            "paper_type": contract.get("paper_type") or paper_structure.get("paper_type"),
            "source_path": trace.get("args", {}).get("pdf_path"),
            "target_claims": contract.get("reproduction_targets") or [],
            "expected_metrics": contract.get("metrics") or [],
        },
        "run": {
            "run_id": run_id,
            "runner": "skill",
            "agent_host": trace.get("source") or "unknown",
            "model": trace.get("model"),
            "started_at": trace.get("invoked_at"),
            "ended_at": trace.get("ended_at"),
            "wall_time_seconds": _wall_time_seconds(trace.get("invoked_at"), trace.get("ended_at")),
            "token_usage": None,
            "cost_usd": None,
            "status": trace_bounds.get("end_marker", {}).get("status") or "unknown",
        },
        "contracts": {
            "paper_structure": paper_structure,
            "ambiguity_audit": ambiguity_audit,
            "reproduction_contract": contract,
            "claim_contract": None,
            "gap_report": gap_report,
        },
        "trajectory": {
            "turn_count": len(turns),
            "turns": turns,
            "phase_spans": _phase_spans(turns),
            "tool_calls": calls,
            "tool_results": results,
            "tool_calls_by_name": trace.get("stats", {}).get("tool_calls_by_name") or {},
            "commands": _commands(calls),
            "file_edits": _file_edits(calls),
            "actions": actions,
            "edit_metadata": edit_metadata,
            "repair_attempts": repair_attempts,
            "reflection_events": reflection_events,
            "final_report_summary": _report_summary(report_text),
        },
        "artifacts": {
            "generated_project_path": str(project_path),
            "files": _existing_files(project_path),
            "configs": sorted(
                _relative(project_path, path)
                for path in (project_path / "configs").glob("*.json")
            )
            if (project_path / "configs").is_dir()
            else [],
            "smoke_script": "scripts/run_smoke.py"
            if (project_path / "scripts" / "run_smoke.py").is_file()
            else None,
            "experiment_script": "scripts/run_experiment.py"
            if (project_path / "scripts" / "run_experiment.py").is_file()
            else None,
            "evaluator_script": "scripts/evaluate_reproduction.py"
            if (project_path / "scripts" / "evaluate_reproduction.py").is_file()
            else None,
            "result_files": sorted(
                _relative(project_path, path)
                for path in (project_path / "results").glob("*.json")
            )
            if (project_path / "results").is_dir()
            else [],
            "reproduction_report": {
                "path": "REPRODUCTION_REPORT.md"
                if (project_path / "REPRODUCTION_REPORT.md").is_file()
                else None,
                "text": report_text,
            },
        },
        "reward": compute_reward(evaluation=evaluation, summary=summary, report_text=report_text),
        "labels": {
            "reproduction_level": contract.get("reproduction_level"),
            "outcome": _outcome(evaluation),
            "failure_types": failure_types,
            "repair_success": None,
            "human_preference": None,
            "data_split": "portfolio",
        },
        "failure_analysis": {
            "primary_failure_type": failure_types[0] if failure_types else None,
            "secondary_failure_types": failure_types[1:],
            "evidence": _failure_evidence(project_path, failure_types),
            "root_cause": _root_cause(failure_types),
            "data_remedy": _data_remedy(failure_types),
            "evaluation_remedy": _evaluation_remedy(failure_types),
        },
        "provenance": {
            "source_files": [
                _relative(project_path, path)
                for path in [
                    trace_path,
                    project_path / "paper_structure.json",
                    project_path / "reproduction_contract.json",
                    project_path / "ambiguity_audit.md",
                    project_path / "gap_report.md",
                    project_path / "results" / "reproduction_evaluation.json",
                    project_path / "results" / "reproduction_summary.json",
                    project_path / "REPRODUCTION_REPORT.md",
                ]
                if path.is_file()
            ],
            "normalizer_version": "skill.v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "notes": [],
        },
    }


def _wall_time_seconds(started_at: str | None, ended_at: str | None) -> float | None:
    if not started_at or not ended_at:
        return None
    try:
        start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        end = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return round((end - start).total_seconds(), 3)


def _report_summary(report_text: str | None) -> str | None:
    if not report_text:
        return None
    lines = [line.strip() for line in report_text.splitlines() if line.strip()]
    return "\n".join(lines[:12])


def _failure_evidence(project_path: Path, failure_types: list[str]) -> list[dict[str, str]]:
    evidence = []
    if not failure_types:
        return evidence
    for path in ["gap_report.md", "REPRODUCTION_REPORT.md", "reproduction_contract.json"]:
        if (project_path / path).is_file():
            evidence.append({"path": path, "reason": "mentions observed reproduction gap"})
    return evidence


def _root_cause(failure_types: list[str]) -> str | None:
    if "unavailable_original_benchmark_data" in failure_types:
        return "Original benchmark inputs were not bundled or identifiable from the paper."
    if "nonportable_hardware_metric" in failure_types:
        return "The reported metric depends on original hardware or implementation details."
    if "dataset_unavailable" in failure_types:
        return "The run could not access the original dataset needed for exact reproduction."
    if "hyperparameter_missing" in failure_types:
        return "The paper omitted hyperparameters required for exact reproduction."
    return None


def _data_remedy(failure_types: list[str]) -> str | None:
    if not failure_types:
        return None
    return (
        "Add boundary cases that require the agent to detect missing reproduction "
        "inputs and explicitly downgrade or request data instead of claiming success."
    )


def _evaluation_remedy(failure_types: list[str]) -> str | None:
    if not failure_types:
        return None
    return (
        "Keep exact-claim and approximate-claim checks separate so honest partial "
        "reproductions score above fake success but below exact reproduction."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize a paper2repro skill run")
    parser.add_argument("project_dir", help="Path to a skill-generated reproduction project")
    parser.add_argument("--out", help="Output JSON path. Defaults to stdout.")
    args = parser.parse_args()

    payload = normalize_skill_run(args.project_dir)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
