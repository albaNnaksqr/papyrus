"""
export_trace.py — Extract paper2repro skill-run traces from Claude Code or Codex session logs.

Usage:
    # Most recent Claude Code session
    python paper2repro/scripts/export_trace.py --latest --source claude

    # Specific session file
    python paper2repro/scripts/export_trace.py ~/.claude/projects/<proj>/<session>.jsonl --source claude
    python paper2repro/scripts/export_trace.py ~/.codex/sessions/<session>.jsonl --source codex

    # All sessions under a project directory
    python paper2repro/scripts/export_trace.py --project ~/.claude/projects/<proj>/ --source claude

    # Write output to file (default: stdout)
    python paper2repro/scripts/export_trace.py --latest --source auto --output traces.jsonl

Each line of output is one complete skill run:
{
  "session_id": "...",
  "skill": "paper2repro",
  "invoked_at": "ISO timestamp",
  "model": "claude-sonnet-4-6",
  "source": "claude" | "codex",
  "args": {"pdf_path": "..."},        # parsed from command args
  "cwd": "...",
  "trace_bounds": {
    "run_id": "...",
    "start_marker": {...},
    "end_marker": {...},
    "end_found": true
  },
  "turns": [
    {
      "role": "user" | "assistant",
      "phase": "phase_1" | "phase_1_5" | "phase_2" | "phase_3" | "phase_4" | null,
      "text": "...",                   # assistant text or human message
      "tool_calls": [...],             # tool_use blocks (assistant only)
      "tool_results": [...],           # tool_result blocks (user/tool-result only)
      "timestamp": "..."
    }
  ],
  "artifacts": {
    "paper_structure": {...} | null,
    "ambiguity_audit": "..." | null,
    "reproduction_report": "..." | null,
    "reproduction_contract": {...} | null,
    "gap_report": "..." | null
  },
  "stats": {
    "total_turns": 0,
    "tool_calls_by_name": {},
    "phases_detected": [],
    "is_complete": false               # true if REPRODUCTION_REPORT was written
  }
}
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECTS_DIR = Path.home() / ".claude" / "projects"
CODEX_SESSIONS_DIR = Path.home() / ".codex" / "sessions"
CODEX_ARCHIVED_DIR = Path.home() / ".codex" / "archived_sessions"

SKILL_NAMES = {"paper2repro", "paper-repro", "implement-paper"}
TRACE_START = "PAPER_REPRO_TRACE_START"
TRACE_END = "PAPER_REPRO_TRACE_END"

# Markers that signal which phase the agent is in.
# Checked against the text content of assistant turns.
PHASE_PATTERNS = [
    ("phase_1",   re.compile(r"Phase 1|阶段1|Step 1\]|\[解析文档\]|Audit the Paper")),
    ("phase_1_5", re.compile(r"Phase 1\.5|Ambiguity Audit|歧义审核|\[阶段1\.5")),
    ("phase_2",   re.compile(r"Phase 2|阶段2|Create the Reproduction|搭项目|scaffold")),
    ("phase_3",   re.compile(r"Phase 3|阶段3|Implement\b|开始实现")),
    ("phase_4",   re.compile(r"Phase 4|阶段4|Debug|Verify|run_smoke|run_experiment|evaluate_reproduction")),
    ("complete",  re.compile(r"REPRODUCTION_REPORT|复现完成|reproduction.*complete", re.I)),
]


# ─────────────────────────────────────────────────────────────────────────────
# Session log parsing
# ─────────────────────────────────────────────────────────────────────────────

def load_jsonl(path: Path) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records


def parse_marker(text: str) -> "tuple[str, dict] | None":
    marker_line = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(TRACE_START) or stripped.startswith(TRACE_END):
            marker_line = stripped
            break
    if marker_line is None:
        return None

    if marker_line.startswith(TRACE_START):
        kind = "start"
        raw = marker_line[len(TRACE_START):].strip()
    else:
        kind = "end"
        raw = marker_line[len(TRACE_END):].strip()

    meta = {}
    if raw.startswith("{"):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                meta.update(parsed)
                return kind, meta
        except json.JSONDecodeError:
            pass
    for pair in re.finditer(r'(\w+)=(".*?"|\S+)', raw):
        value = pair.group(2)
        if len(value) >= 2 and value[0] == value[-1] == '"':
            value = value[1:-1]
        meta[pair.group(1)] = value
    return kind, meta


def record_texts(record: dict, source: str) -> list[str]:
    texts = []
    if source == "claude":
        content = record.get("content")
        if isinstance(content, str):
            texts.append(content)
        message = record.get("message", {})
        msg_content = message.get("content")
        if isinstance(msg_content, str):
            texts.append(msg_content)
        elif isinstance(msg_content, list):
            for block in msg_content:
                if isinstance(block, dict):
                    if block.get("type") == "text" and isinstance(block.get("text"), str):
                        texts.append(block["text"])
                    elif block.get("type") == "tool_result":
                        result_content = block.get("content")
                        if isinstance(result_content, str):
                            texts.append(result_content)
    elif source == "codex":
        payload = record.get("payload", {})
        for key in ("message", "text", "output"):
            value = payload.get(key)
            if isinstance(value, str):
                texts.append(value)
    return texts


def find_marker_segments(records: list[dict], source: str) -> list[dict]:
    segments = []
    active = None
    for index, record in enumerate(records):
        for text in record_texts(record, source):
            marker = parse_marker(text)
            if marker is None:
                continue
            kind, meta = marker
            if kind == "start":
                active = {
                    "start_index": index,
                    "start_record": record,
                    "start_meta": meta,
                }
            elif kind == "end" and active is not None:
                run_id = active["start_meta"].get("run_id")
                if run_id and meta.get("run_id") and meta.get("run_id") != run_id:
                    continue
                active.update({
                    "end_index": index,
                    "end_record": record,
                    "end_meta": meta,
                    "end_found": True,
                })
                segments.append(active)
                active = None
    if active is not None:
        active.update({
            "end_index": len(records),
            "end_record": None,
            "end_meta": {},
            "end_found": False,
        })
        segments.append(active)
    return segments


def is_skill_invocation(record: dict) -> bool:
    """Return True if this record is a /paper2repro, legacy /paper-repro, or /implement-paper invocation."""
    if record.get("type") != "system":
        return False
    if record.get("subtype") != "local_command":
        return False
    content = record.get("content", "")
    # <command-name>/paper2repro</command-name>
    m = re.search(r"<command-name>/([\w-]+)</command-name>", content)
    return bool(m) and m.group(1) in SKILL_NAMES


def parse_skill_args(content: str) -> dict:
    """Parse pdf_path and auto from <command-args> tag."""
    args = {}
    m = re.search(r"<command-args>(.*?)</command-args>", content, re.DOTALL)
    if not m:
        return args
    raw = m.group(1).strip()
    # try key=value pairs
    for pair in re.finditer(r'(\w+)=([^\s]+)', raw):
        args[pair.group(1)] = pair.group(2)
    # bare path (no key)
    if not args and raw:
        args["pdf_path"] = raw
    return args


def is_session_boundary(record: dict) -> bool:
    """Return True if this record signals the end of a skill run."""
    if record.get("type") != "system":
        return False
    subtype = record.get("subtype", "")
    if subtype == "compact_boundary":
        return True
    if subtype == "local_command":
        # Another slash command starts a new skill or unrelated session segment.
        # But only treat it as a boundary if it's a DIFFERENT command.
        content = record.get("content", "")
        m = re.search(r"<command-name>/([\w-]+)</command-name>", content)
        if m:
            cmd = m.group(1)
            # same skill re-invoked = new run, still a boundary
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Turn extraction
# ─────────────────────────────────────────────────────────────────────────────

def detect_phase(text: str) -> "str | None":
    for phase, pattern in PHASE_PATTERNS:
        if pattern.search(text):
            return phase
    return None


def extract_turns(records: list[dict]) -> list[dict]:
    """
    Convert raw log records into a clean list of turns.
    Each turn is either:
      - A human message (role=user, text=string content)
      - A tool-result message (role=tool_result, results=[...])
      - An assistant message (role=assistant, text, tool_calls)
    Consecutive assistant streaming records are merged into one turn.
    """
    turns = []
    current_phase = None

    def flush_assistant(buf: list[dict]) -> dict | None:
        if not buf:
            return None
        text_parts = []
        tool_calls = []
        for rec in buf:
            for block in rec["message"].get("content", []):
                btype = block.get("type")
                if btype == "text":
                    text_parts.append(block.get("text", ""))
                elif btype == "tool_use":
                    tool_calls.append({
                        "id": block.get("id"),
                        "name": block.get("name"),
                        "input": block.get("input", {}),
                    })
        text = "\n".join(t for t in text_parts if t).strip()
        return {
            "role": "assistant",
            "phase": None,
            "text": text,
            "tool_calls": tool_calls,
            "tool_results": [],
            "timestamp": buf[0].get("timestamp", ""),
        }

    assistant_buf: list[dict] = []

    for rec in records:
        rtype = rec.get("type")

        if rtype == "assistant":
            assistant_buf.append(rec)

        elif rtype == "user":
            # Flush pending assistant turn first
            if assistant_buf:
                turn = flush_assistant(assistant_buf)
                if turn:
                    phase = detect_phase(turn["text"])
                    if phase:
                        current_phase = phase
                    turn["phase"] = current_phase
                    turns.append(turn)
                assistant_buf = []

            content = rec["message"].get("content", "")

            if isinstance(content, list):
                # tool results
                results = []
                for block in content:
                    if block.get("type") == "tool_result":
                        result_content = block.get("content", "")
                        if isinstance(result_content, list):
                            result_content = " ".join(
                                b.get("text", "") for b in result_content
                                if b.get("type") == "text"
                            )
                        results.append({
                            "tool_use_id": block.get("tool_use_id"),
                            "content": result_content,
                            "is_error": block.get("is_error", False),
                        })
                if results:
                    turns.append({
                        "role": "tool_result",
                        "phase": current_phase,
                        "text": "",
                        "tool_calls": [],
                        "tool_results": results,
                        "timestamp": rec.get("timestamp", ""),
                    })

            elif isinstance(content, str) and content.strip():
                # Human message
                turns.append({
                    "role": "user",
                    "phase": current_phase,
                    "text": content.strip(),
                    "tool_calls": [],
                    "tool_results": [],
                    "timestamp": rec.get("timestamp", ""),
                })

    # Flush trailing assistant turns
    if assistant_buf:
        turn = flush_assistant(assistant_buf)
        if turn:
            phase = detect_phase(turn["text"])
            if phase:
                current_phase = phase
            turn["phase"] = current_phase
            turns.append(turn)

    return turns


def _parse_tool_arguments(arguments):
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        try:
            return json.loads(arguments)
        except json.JSONDecodeError:
            return arguments
    return arguments


def _build_codex_tool_result(payload: dict) -> "dict | None":
    payload_type = payload.get("type")
    if payload_type not in {"function_call_output", "custom_tool_call_output"}:
        return None
    raw = payload.get("output", "")
    if not isinstance(raw, str):
        return {"raw": raw}
    out = {}
    output_lines = []
    in_output = False
    for line in raw.splitlines():
        if line.startswith("Exit code: "):
            try:
                out["exit_code"] = int(line[len("Exit code: "):].strip())
            except ValueError:
                out["exit_code"] = line[len("Exit code: "):].strip()
        elif line.startswith("Wall time: "):
            out["wall_time"] = line[len("Wall time: "):].strip()
        elif line == "Output:":
            in_output = True
        elif in_output:
            output_lines.append(line)
    if output_lines:
        out["output"] = "\n".join(output_lines).strip()
    elif raw:
        out["output"] = raw
    return out


def extract_codex_metadata(records: list[dict], session_path: Path) -> dict:
    metadata = {
        "session_id": session_path.stem,
        "cwd": "",
        "model": "codex-unknown",
        "model_provider": None,
        "start_time": "",
        "end_time": "",
    }
    for record in records:
        timestamp = record.get("timestamp", "")
        if timestamp and not metadata["start_time"]:
            metadata["start_time"] = timestamp
        if timestamp:
            metadata["end_time"] = timestamp
        payload = record.get("payload", {})
        if record.get("type") == "session_meta":
            metadata["session_id"] = payload.get("id", metadata["session_id"])
            metadata["cwd"] = payload.get("cwd", metadata["cwd"])
            metadata["model_provider"] = payload.get("model_provider", metadata["model_provider"])
        elif record.get("type") == "turn_context":
            metadata["cwd"] = payload.get("cwd", metadata["cwd"])
            metadata["model"] = payload.get("model", metadata["model"])
    return metadata


def extract_codex_turns(records: list[dict]) -> list[dict]:
    tool_results = {}
    for record in records:
        if record.get("type") != "response_item":
            continue
        payload = record.get("payload", {})
        call_id = payload.get("call_id")
        result = _build_codex_tool_result(payload)
        if call_id and result is not None:
            tool_results[call_id] = result

    turns = []
    pending_tool_calls = []
    current_phase = None

    def flush_assistant(text: str, timestamp: str):
        nonlocal pending_tool_calls, current_phase
        clean = text.strip()
        phase = detect_phase(clean)
        if phase:
            current_phase = phase
        if clean or pending_tool_calls:
            turns.append({
                "role": "assistant",
                "phase": current_phase,
                "text": clean,
                "tool_calls": pending_tool_calls,
                "tool_results": [],
                "timestamp": timestamp,
            })
            # Mirror the claude trace shape: emit results as a turn-level
            # tool_result turn so downstream consumers (normalizer, audits)
            # see the same schema regardless of agent host.
            results = []
            for tc in pending_tool_calls:
                res = tc.get("tool_result")
                if res is None:
                    continue
                if isinstance(res, dict):
                    content = res.get("output", "")
                    exit_code = res.get("exit_code")
                    meta = {k: v for k, v in res.items() if k != "output"}
                else:
                    content, exit_code, meta = str(res), None, {}
                results.append({
                    "tool_use_id": tc.get("id"),
                    "content": content,
                    "is_error": bool(exit_code) if isinstance(exit_code, int) else False,
                    "meta": meta,
                })
            if results:
                turns.append({
                    "role": "tool_result",
                    "phase": current_phase,
                    "text": "",
                    "tool_calls": [],
                    "tool_results": results,
                    "timestamp": timestamp,
                })
        pending_tool_calls = []

    for record in records:
        timestamp = record.get("timestamp", "")
        rtype = record.get("type")
        payload = record.get("payload", {})

        if rtype == "response_item":
            payload_type = payload.get("type")
            if payload_type in {"function_call", "custom_tool_call"}:
                call_id = payload.get("call_id")
                tool_call = {
                    "id": call_id,
                    "name": payload.get("name"),
                    "input": _parse_tool_arguments(payload.get("arguments", payload.get("input", {}))),
                }
                if call_id in tool_results:
                    tool_call["tool_result"] = tool_results[call_id]
                pending_tool_calls.append(tool_call)

        elif rtype == "event_msg":
            event_type = payload.get("type")
            if event_type == "agent_message":
                flush_assistant(payload.get("message", ""), timestamp)
            elif event_type == "user_message":
                if pending_tool_calls:
                    flush_assistant("", timestamp)
                text = payload.get("message", "")
                if isinstance(text, str) and text.strip():
                    turns.append({
                        "role": "user",
                        "phase": current_phase,
                        "text": text.strip(),
                        "tool_calls": [],
                        "tool_results": [],
                        "timestamp": timestamp,
                    })

    if pending_tool_calls:
        flush_assistant("", records[-1].get("timestamp", "") if records else "")
    return turns


# ─────────────────────────────────────────────────────────────────────────────
# Artifact loading
# ─────────────────────────────────────────────────────────────────────────────

def find_output_dir(cwd: str, paper_id: "str | None", project_name: "str | None" = None) -> Path | None:
    """Locate the output directory for a skill run."""
    base = Path(cwd)
    # skill writes to output/<paper_id>/ relative to cwd
    output_root = base / "output"
    names = [n for n in (project_name, paper_id) if n]
    for name in names:
        for candidate in (output_root / name, base / name):
            if candidate.exists():
                return candidate
    if not output_root.exists():
        return None
    # nested layouts, e.g. output/<batch>/<host>/<project_name>
    for name in names:
        matches = [d for d in output_root.rglob(name) if d.is_dir()]
        if matches:
            return max(matches, key=lambda d: d.stat().st_mtime)
    # fall back: most recently modified subdirectory
    subdirs = sorted(
        (d for d in output_root.iterdir() if d.is_dir()),
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    return subdirs[0] if subdirs else None


def load_artifacts(output_dir: Path | None) -> dict:
    artifacts = {
        "paper_structure": None,
        "ambiguity_audit": None,
        "reproduction_report": None,
        "reproduction_contract": None,
        "gap_report": None,
    }
    if not output_dir:
        return artifacts

    def read_json(name):
        p = output_dir / name
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    def read_text(name):
        p = output_dir / name
        return p.read_text(encoding="utf-8") if p.exists() else None

    artifacts["paper_structure"] = read_json("paper_structure.json")
    artifacts["reproduction_contract"] = read_json("reproduction_contract.json")
    artifacts["ambiguity_audit"] = read_text("ambiguity_audit.md")
    artifacts["reproduction_report"] = read_text("REPRODUCTION_REPORT.md")
    artifacts["gap_report"] = read_text("gap_report.md")
    return artifacts


# ─────────────────────────────────────────────────────────────────────────────
# Stats
# ─────────────────────────────────────────────────────────────────────────────

def compute_stats(turns: list[dict], artifacts: dict) -> dict:
    tool_counts: dict[str, int] = {}
    phases_seen: list[str] = []
    current = None
    for turn in turns:
        for tc in turn.get("tool_calls", []):
            name = tc.get("name", "unknown")
            tool_counts[name] = tool_counts.get(name, 0) + 1
        p = turn.get("phase")
        if p and p != current:
            current = p
            phases_seen.append(p)

    return {
        "total_turns": len(turns),
        "tool_calls_by_name": tool_counts,
        "phases_detected": phases_seen,
        "is_complete": artifacts.get("reproduction_report") is not None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main extraction: find all skill runs in a session
# ─────────────────────────────────────────────────────────────────────────────

def _extract_claude_skill_runs_from_markers(session_path: Path, records: list[dict]) -> list[dict]:
    session_id = records[0].get("sessionId", session_path.stem)
    runs = []
    for segment in find_marker_segments(records, "claude"):
        start_meta = segment["start_meta"]
        end_meta = segment["end_meta"]
        start_record = segment["start_record"]
        window = records[segment["start_index"] + 1:segment["end_index"]]
        turns = extract_turns(window)
        cwd = start_record.get("cwd", "") or _first_record_cwd(records)
        model = _first_claude_model(window)
        args = dict(start_meta)
        paper_id = args.get("paper_id") or _infer_paper_id(args.get("pdf_path", ""))
        project_name = end_meta.get("project_name") or start_meta.get("project_name")
        output_dir = find_output_dir(cwd, paper_id, project_name)
        artifacts = load_artifacts(output_dir)
        stats = compute_stats(turns, artifacts)
        runs.append({
            "session_id": session_id,
            "skill": "paper2repro",
            "source": "claude",
            "invoked_at": start_record.get("timestamp", ""),
            "ended_at": segment["end_record"].get("timestamp", "") if segment["end_record"] else "",
            "model": model or "unknown",
            "args": args,
            "cwd": cwd,
            "trace_bounds": {
                "run_id": start_meta.get("run_id"),
                "start_marker": start_meta,
                "end_marker": end_meta,
                "end_found": segment["end_found"],
            },
            "turns": turns,
            "artifacts": artifacts,
            "stats": stats,
        })
    return runs


def _first_record_cwd(records: list[dict]) -> str:
    for record in records:
        cwd = record.get("cwd")
        if isinstance(cwd, str) and cwd:
            return cwd
        payload_cwd = record.get("payload", {}).get("cwd")
        if isinstance(payload_cwd, str) and payload_cwd:
            return payload_cwd
    return ""


def _first_claude_model(records: list[dict]) -> "str | None":
    for record in records:
        if record.get("type") == "assistant":
            model = record.get("message", {}).get("model")
            if model:
                return model
    return None


def _extract_claude_skill_runs_from_commands(session_path: Path, records: list[dict]) -> list[dict]:
    records = load_jsonl(session_path)
    if not records:
        return []

    session_id = records[0].get("sessionId", session_path.stem)
    runs = []

    # Find every skill invocation and its window of records
    i = 0
    while i < len(records):
        rec = records[i]
        if not is_skill_invocation(rec):
            i += 1
            continue

        # Found a skill start
        start_rec = rec
        args = parse_skill_args(rec.get("content", ""))
        invoked_at = rec.get("timestamp", "")
        cwd = rec.get("cwd", "")

        # Detect model from first assistant record in the window
        model = None

        # Collect records until the next boundary
        window: list[dict] = []
        j = i + 1
        while j < len(records):
            r = records[j]
            if is_session_boundary(r):
                break
            window.append(r)
            if model is None and r.get("type") == "assistant":
                model = r.get("message", {}).get("model")
            j += 1

        # Extract turns from the window
        turns = extract_turns(window)

        # Load artifacts
        paper_id = args.get("paper_id") or _infer_paper_id(args.get("pdf_path", ""))
        output_dir = find_output_dir(cwd, paper_id)
        artifacts = load_artifacts(output_dir)
        stats = compute_stats(turns, artifacts)

        runs.append({
            "session_id": session_id,
            "skill": "paper2repro",
            "source": "claude",
            "invoked_at": invoked_at,
            "ended_at": "",
            "model": model or "unknown",
            "args": args,
            "cwd": cwd,
            "trace_bounds": {
                "run_id": None,
                "start_marker": None,
                "end_marker": None,
                "end_found": False,
                "fallback": "slash_command_boundary",
            },
            "turns": turns,
            "artifacts": artifacts,
            "stats": stats,
        })

        i = j  # continue after the boundary

    return runs


def _extract_codex_skill_runs_from_markers(session_path: Path, records: list[dict]) -> list[dict]:
    metadata = extract_codex_metadata(records, session_path)
    runs = []
    for segment in find_marker_segments(records, "codex"):
        start_meta = segment["start_meta"]
        end_meta = segment["end_meta"]
        window = records[segment["start_index"] + 1:segment["end_index"]]
        turns = extract_codex_turns(window)
        args = dict(start_meta)
        paper_id = args.get("paper_id") or _infer_paper_id(args.get("pdf_path", ""))
        project_name = end_meta.get("project_name") or start_meta.get("project_name")
        output_dir = find_output_dir(metadata["cwd"], paper_id, project_name)
        artifacts = load_artifacts(output_dir)
        stats = compute_stats(turns, artifacts)
        runs.append({
            "session_id": metadata["session_id"],
            "skill": "paper2repro",
            "source": "codex",
            "invoked_at": segment["start_record"].get("timestamp", ""),
            "ended_at": segment["end_record"].get("timestamp", "") if segment["end_record"] else "",
            "model": metadata["model"],
            "args": args,
            "cwd": metadata["cwd"],
            "trace_bounds": {
                "run_id": start_meta.get("run_id"),
                "start_marker": start_meta,
                "end_marker": end_meta,
                "end_found": segment["end_found"],
            },
            "turns": turns,
            "artifacts": artifacts,
            "stats": stats,
        })
    return runs


def extract_skill_runs(session_path: Path, source: str = "claude") -> list[dict]:
    records = load_jsonl(session_path)
    if not records:
        return []
    if source == "codex":
        return _extract_codex_skill_runs_from_markers(session_path, records)
    if source == "claude":
        marker_runs = _extract_claude_skill_runs_from_markers(session_path, records)
        if marker_runs:
            return marker_runs
        return _extract_claude_skill_runs_from_commands(session_path, records)
    raise ValueError(f"Unsupported source: {source}")


def _infer_paper_id(pdf_path: str) -> "str | None":
    if not pdf_path:
        return None
    return Path(pdf_path).stem.replace(" ", "_")[:30]


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def iter_codex_session_files() -> list[Path]:
    files = []
    if CODEX_SESSIONS_DIR.exists():
        files.extend(CODEX_SESSIONS_DIR.rglob("*.jsonl"))
    if CODEX_ARCHIVED_DIR.exists():
        files.extend(CODEX_ARCHIVED_DIR.glob("*.jsonl"))
    return sorted(files)


def find_latest_session(source: str = "claude") -> Path | None:
    """Find the most recently modified session log for a source."""
    if source == "codex":
        paths = iter_codex_session_files()
    elif source == "auto":
        claude_paths = list(PROJECTS_DIR.rglob("*.jsonl")) if PROJECTS_DIR.exists() else []
        paths = claude_paths + iter_codex_session_files()
    else:
        paths = list(PROJECTS_DIR.rglob("*.jsonl")) if PROJECTS_DIR.exists() else []
    candidates = sorted(
        paths,
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def main():
    parser = argparse.ArgumentParser(
        description="Extract paper2repro skill-run traces from Claude Code or Codex session logs."
    )
    src = parser.add_mutually_exclusive_group()
    src.add_argument("session", nargs="?", help="Path to a session .jsonl file")
    src.add_argument("--latest", action="store_true", help="Use the most recent session")
    src.add_argument("--project", metavar="DIR", help="Scan all sessions under a project directory")
    parser.add_argument("--source", choices=["claude", "codex", "auto"], default="claude",
                        help="Session source format (default: claude)")
    parser.add_argument("--output", metavar="FILE", help="Write output to FILE (default: stdout)")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON (not JSONL)")
    args = parser.parse_args()

    # Resolve session file(s)
    session_files: list[Path] = []
    if args.latest:
        latest_source = args.source
        p = find_latest_session(latest_source)
        if not p:
            if latest_source == "codex":
                location = "~/.codex/sessions/"
            elif latest_source == "auto":
                location = "~/.claude/projects/ or ~/.codex/sessions/"
            else:
                location = "~/.claude/projects/"
            print(f"No session files found under {location}", file=sys.stderr)
            sys.exit(1)
        session_files = [p]
        print(f"Using session: {p}", file=sys.stderr)
    elif args.project:
        project_dir = Path(args.project)
        session_files = sorted(project_dir.glob("*.jsonl"))
        if not session_files:
            print(f"No .jsonl files found in {project_dir}", file=sys.stderr)
            sys.exit(1)
    elif args.session:
        session_files = [Path(args.session)]
    else:
        parser.print_help()
        sys.exit(1)

    # Extract runs
    all_runs = []
    for sf in session_files:
        if args.source == "auto":
            runs = extract_skill_runs(sf, source="claude")
            if not runs:
                runs = extract_skill_runs(sf, source="codex")
        else:
            runs = extract_skill_runs(sf, source=args.source)
        all_runs.extend(runs)

    if not all_runs:
        print("No paper2repro skill runs found in the specified session(s).", file=sys.stderr)
        sys.exit(0)

    print(f"Found {len(all_runs)} skill run(s).", file=sys.stderr)

    # Output
    out = open(args.output, "w", encoding="utf-8") if args.output else sys.stdout
    try:
        if args.pretty:
            out.write(json.dumps(all_runs, ensure_ascii=False, indent=2))
            out.write("\n")
        else:
            for run in all_runs:
                out.write(json.dumps(run, ensure_ascii=False))
                out.write("\n")
    finally:
        if args.output:
            out.close()


if __name__ == "__main__":
    main()
