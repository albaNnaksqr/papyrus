from __future__ import annotations

import argparse
import json
import re
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
    for turn_index, turn in enumerate(turns):
        for call_index, call in enumerate(turn.get("tool_calls") or []):
            calls.append(
                {
                    "sequence_index": len(calls),
                    "turn_index": turn_index,
                    "call_index": call_index,
                    "name": call.get("name"),
                    "input": call.get("input") or {},
                    "id": call.get("id"),
                }
            )
    return calls


def _tool_results(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for turn_index, turn in enumerate(turns):
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


def _tool_events(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for turn_index, turn in enumerate(turns):
        for call_index, call in enumerate(turn.get("tool_calls") or []):
            events.append(
                {
                    "sequence_index": len(events),
                    "turn_index": turn_index,
                    "call_index": call_index,
                    "turn_text": turn.get("text") or "",
                    "name": call.get("name"),
                    "input": call.get("input") or {},
                    "id": call.get("id"),
                    "tool_result": call.get("tool_result") or {},
                }
            )
    return events


def _patch_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        for key in ("patch", "input", "payload"):
            value = payload.get(key)
            if isinstance(value, str):
                return value
    return ""


def _normalize_patch_path(raw_path: str, project_dir: Path) -> str:
    cleaned = raw_path.strip()
    if not cleaned:
        return cleaned
    path = Path(cleaned)
    if path.is_absolute():
        try:
            return str(path.resolve().relative_to(project_dir))
        except ValueError:
            return cleaned

    parts = Path(cleaned).parts
    if project_dir.name in parts:
        start = parts.index(project_dir.name) + 1
        if start < len(parts):
            return str(Path(*parts[start:]))
    return cleaned


def _target_class(path: str) -> str:
    lower = path.lower()
    parts = set(Path(lower).parts)
    name = Path(lower).name
    suffix = Path(lower).suffix

    if "tests" in parts or name.startswith("test_") or name.endswith("_test.py"):
        return "test"
    if "evaluate" in name or "evaluator" in lower:
        return "evaluator"
    if (
        "configs" in parts
        or "config" in parts
        or name in {"requirements.txt", "pytest.ini", "pyproject.toml", "setup.cfg"}
        or suffix in {".json", ".toml", ".yaml", ".yml", ".ini"}
    ):
        return "config"
    if suffix in {".md", ".rst", ".txt"} and any(
        marker in name for marker in ("report", "audit", "gap", "readme")
    ):
        return "report"
    if suffix in {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs", ".cpp", ".c"}:
        return "implementation"
    return "other"


def _parse_patch_file_edits(patch: str, project_dir: Path) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    op_map = {"Add": "create", "Update": "update", "Delete": "delete"}

    for line in patch.splitlines():
        match = re.match(r"^\*\*\* (Add|Update|Delete) File: (.+)$", line)
        if match:
            if current:
                parsed.append(current)
            operation = op_map[match.group(1)]
            path = _normalize_patch_path(match.group(2), project_dir)
            current = {"path": path, "operation": operation, "diff_line_count": 0}
            continue
        move_match = re.match(r"^\*\*\* Move to: (.+)$", line)
        if move_match and current:
            current["path"] = _normalize_patch_path(move_match.group(1), project_dir)
            continue
        if current and (line.startswith("+") or line.startswith("-")):
            current["diff_line_count"] += 1

    if current:
        parsed.append(current)
    for item in parsed:
        item["diff_line_count"] = max(1, item["diff_line_count"])
    return parsed


def _file_edits(calls: list[dict[str, Any]], project_dir: Path) -> list[dict[str, Any]]:
    edits: list[dict[str, Any]] = []
    for call in calls:
        if call.get("name") != "apply_patch":
            continue
        for parsed in _parse_patch_file_edits(_patch_text(call.get("input")), project_dir):
            edits.append(
                {
                    "turn_index": call["turn_index"],
                    "tool_call_id": call.get("id"),
                    "tool": "apply_patch",
                    "source": "agent_trace",
                    "path": parsed["path"],
                    "operation": parsed["operation"],
                    "diff_line_count": parsed["diff_line_count"],
                    "target_class": _target_class(parsed["path"]),
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


def _command_text(event: dict[str, Any]) -> str:
    payload = event.get("input") or {}
    if isinstance(payload, dict):
        return str(payload.get("cmd") or "")
    return ""


def _command_output(event: dict[str, Any]) -> str:
    result = event.get("tool_result") or {}
    return str(result.get("output") or "")


def _is_verification_command(command: str) -> bool:
    lower = command.lower()
    verification_markers = [
        "pytest",
        "unittest",
        "npm test",
        "pnpm test",
        "yarn test",
        "cargo test",
        "go test",
        "run_smoke.py",
        "run_experiment.py",
        "evaluate_reproduction.py",
        "evaluate.py",
    ]
    return any(marker in lower for marker in verification_markers)


def _command_failed(event: dict[str, Any]) -> bool:
    result = event.get("tool_result") or {}
    exit_code = result.get("exit_code")
    if isinstance(exit_code, int) and exit_code != 0:
        return True

    command = _command_text(event)
    output = _command_output(event)
    if not _is_verification_command(command) and "traceback (most recent call last)" not in output.lower():
        return False

    uppercase_failure_patterns = [
        r"Traceback \(most recent call last\)",
        r"\bFAILED\b",
        r"\bERRORS?\b",
        r"\bERROR:",
        r"\bFAIL\b",
        r"returned non-zero exit status",
        r"FAILED \(",
    ]
    exception_patterns = [
        r"AssertionError",
        r"ImportError",
        r"ModuleNotFoundError",
        r"SyntaxError",
    ]
    return any(re.search(pattern, output) for pattern in uppercase_failure_patterns) or any(
        re.search(pattern, output, flags=re.IGNORECASE) for pattern in exception_patterns
    )


def _failure_summary(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    interesting = [
        line
        for line in lines
        if re.search(
            r"Traceback|FAILED|ERROR|FAIL|AssertionError|ImportError|ModuleNotFoundError|SyntaxError",
            line,
            flags=re.IGNORECASE,
        )
    ]
    selected = interesting[:4] or lines[:4]
    summary = " | ".join(selected)
    return summary[:500]


def _normalized_command(command: str) -> str:
    command = re.sub(r"\s+", " ", command.strip())
    command = re.sub(r"^[A-Z_][A-Z0-9_]*=(\"[^\"]*\"|'[^']*'|\S+)\s+", "", command)
    return command


def _commands_similar(first: str, second: str) -> bool:
    first_norm = _normalized_command(first)
    second_norm = _normalized_command(second)
    if not first_norm or not second_norm:
        return False
    if first_norm == second_norm:
        return True
    if first_norm in second_norm or second_norm in first_norm:
        return True

    first_parts = {
        part
        for part in re.split(r"\s+|&&|\|\|", first_norm)
        if part and not part.startswith("-")
    }
    second_parts = {
        part
        for part in re.split(r"\s+|&&|\|\|", second_norm)
        if part and not part.startswith("-")
    }
    meaningful = {
        part
        for part in first_parts
        if any(marker in part for marker in ("pytest", "unittest", "run_", "evaluate"))
    }
    return bool(meaningful and meaningful <= second_parts)


def _turn_text_window(turns: list[dict[str, Any]], start: int, end: int) -> str:
    lower = max(0, start)
    upper = min(len(turns) - 1, end)
    return "\n".join(str(turns[index].get("text") or "") for index in range(lower, upper + 1))


def _planned_tdd_red(turns: list[dict[str, Any]], failure_turn: int) -> bool:
    text = _turn_text_window(turns, failure_turn - 2, failure_turn + 1).lower()
    markers = [
        "expected fail",
        "expected failure",
        "expected reason",
        "red step",
        "tdd",
        "red-green",
        "watch it fail",
        "verify they fail",
        "verify it fails",
        "tests are in place",
    ]
    return any(marker in text for marker in markers)


def _edited_files_between(
    file_edits: list[dict[str, Any]],
    edit_call_ids: set[str | None],
) -> list[str]:
    files = sorted(
        {
            edit["path"]
            for edit in file_edits
            if edit.get("tool_call_id") in edit_call_ids and edit.get("path")
        }
    )
    return files


def _repair_attempts(
    turns: list[dict[str, Any]],
    events: list[dict[str, Any]],
    file_edits: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    used_failure_sequences: set[int] = set()

    for index, event in enumerate(events):
        if event.get("name") != "exec_command" or index in used_failure_sequences:
            continue
        if not _command_failed(event):
            continue

        failing_command = _command_text(event)
        edits_after_failure: list[dict[str, Any]] = []
        retest: dict[str, Any] | None = None
        for later in events[index + 1 :]:
            if later["turn_index"] - event["turn_index"] > 10:
                break
            if later.get("name") == "apply_patch":
                edits_after_failure.append(later)
                continue
            if not edits_after_failure or later.get("name") != "exec_command":
                continue
            candidate_command = _command_text(later)
            if _commands_similar(failing_command, candidate_command):
                retest = later
                break

        if not edits_after_failure or not retest:
            continue

        edit_call_ids = {edit.get("id") for edit in edits_after_failure}
        edited_files = _edited_files_between(file_edits, edit_call_ids)
        if not edited_files:
            continue

        planned = _planned_tdd_red(turns, event["turn_index"])
        start_turn = event["turn_index"]
        if planned:
            previous_test_patch_turns = [
                previous["turn_index"]
                for previous in events[:index]
                if previous.get("name") == "apply_patch"
                and event["turn_index"] - previous["turn_index"] <= 2
            ]
            if previous_test_patch_turns:
                start_turn = min(previous_test_patch_turns)

        attempts.append(
            {
                "kind": "planned_tdd_red" if planned else "unexpected_failure",
                "turn_span": [start_turn, retest["turn_index"]],
                "failing_command": failing_command,
                "failure_summary": _failure_summary(_command_output(event)),
                "edited_files": edited_files,
                "retest_command": _command_text(retest),
                "repair_success": not _command_failed(retest),
            }
        )
        used_failure_sequences.add(index)

    return attempts


def _read_codex_token_usage(trace: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    session_id = trace.get("session_id")
    if not session_id:
        return None, ["Codex session_id missing; token_usage left null."]

    sessions_root = Path.home() / ".codex" / "sessions"
    paths = sorted(sessions_root.glob(f"**/*{session_id}*.jsonl"))
    if not paths:
        return None, [f"Codex session rollout not found for session_id={session_id}; token_usage left null."]

    usage = {
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_output_tokens": 0,
    }
    token_events = 0
    for line in paths[0].read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        payload = event.get("payload") or {}
        if payload.get("type") != "token_count":
            continue
        info = payload.get("info") or {}
        last_usage = info.get("last_token_usage") or {}
        if not last_usage:
            last_usage = info.get("total_token_usage") or {}
        if not last_usage:
            continue
        token_events += 1
        for key in usage:
            usage[key] += int(last_usage.get(key) or 0)

    if token_events == 0:
        return None, [f"Codex session rollout has no token_count events for session_id={session_id}."]

    usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]
    usage["session_id"] = session_id
    usage["source"] = "codex_session_rollout"
    usage["session_file"] = str(paths[0])
    return usage, []


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
    evaluation = _read_json(project_path / "results" / "reproduction_evaluation.json") or {}
    summary = _read_json(project_path / "results" / "reproduction_summary.json") or {}
    ambiguity_audit = _read_text(project_path / "ambiguity_audit.md")
    gap_report = _read_text(project_path / "gap_report.md")
    report_text = _read_text(project_path / "REPRODUCTION_REPORT.md")

    events = _tool_events(turns)
    calls = _tool_calls(turns)
    results = _tool_results(turns)
    failure_types = _failure_types(contract, report_text)
    file_edits = _file_edits(calls, project_path)
    repair_attempts = _repair_attempts(turns, events, file_edits)
    token_usage, provenance_notes = _read_codex_token_usage(trace)

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
            "token_usage": token_usage,
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
            "file_edits": file_edits,
            "repair_attempts": repair_attempts,
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
            "normalizer_version": "skill.v2",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "notes": provenance_notes,
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
