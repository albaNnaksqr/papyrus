#!/usr/bin/env python3
"""
Export paper2repro run logs to SFT / DPO / CoT training datasets.

Usage:
    python scripts/export_corpus.py                          # all tasks
    python scripts/export_corpus.py --task paper_87d8010e   # single task
    python scripts/export_corpus.py --format sft dpo        # specific formats
    python scripts/export_corpus.py --out datasets/          # output dir

Output files:
    sft.jsonl   — (system, user, assistant) conversation turns for supervised fine-tuning
    dpo.jsonl   — (prompt, chosen, rejected) pairs; rejected = truncated / error turns
    cot.jsonl   — full multi-turn chains with tool calls and reasoning traces
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_jsonl(path: Path) -> list[dict]:
    records = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def _find_task_dirs(output_root: Path) -> list[Path]:
    tasks_dir = output_root / "tasks"
    if not tasks_dir.is_dir():
        return []
    return sorted(d for d in tasks_dir.iterdir() if d.is_dir())


# ---------------------------------------------------------------------------
# SFT export
# Each LLM record that has full messages becomes one SFT sample:
#   {"messages": [{"role": "system", ...}, {"role": "user", ...}, {"role": "assistant", ...}]}
# ---------------------------------------------------------------------------

def _build_sft_sample(record: dict) -> dict | None:
    req = record.get("request_preview")
    if not isinstance(req, list) or len(req) < 1:
        return None

    resp = record.get("response_preview", "")
    tool_calls = record.get("tool_calls", [])
    if not resp and not tool_calls:
        return None

    # Build assistant turn
    if tool_calls:
        assistant_content: str | list = [{"type": "text", "text": resp}] if resp else []
        for tc in tool_calls:
            assistant_content.append({
                "type": "tool_use",
                "id": tc.get("id", ""),
                "name": tc.get("name", ""),
                "input": tc.get("input", {}),
            })
    else:
        assistant_content = resp

    messages = list(req) + [{"role": "assistant", "content": assistant_content}]

    return {
        "messages": messages,
        "metadata": {
            "task_id": record.get("task_id"),
            "phase": record.get("phase"),
            "model": record.get("model"),
            "timestamp": record.get("timestamp"),
            "tokens": {
                "prompt": record.get("prompt_tokens"),
                "completion": record.get("completion_tokens"),
            },
        },
    }


# ---------------------------------------------------------------------------
# DPO export
# "chosen" = successful turns (finish_reason=stop or tool_calls, status=ok)
# "rejected" = failed / truncated turns (finish_reason=length, status=error)
# We pair each rejected turn with the nearest successful turn from the same
# phase/task as chosen.
# ---------------------------------------------------------------------------

def _build_dpo_samples(records: list[dict]) -> list[dict]:
    by_phase: dict[str, list[dict]] = {}
    rejected_pool: list[dict] = []

    for r in records:
        req = r.get("request_preview")
        if not isinstance(req, list):
            continue
        resp = r.get("response_preview", "")
        status = r.get("status", "ok")
        finish = r.get("finish_reason", "stop")

        phase = r.get("phase") or "unknown"
        prompt = req

        if status == "error" or finish == "length":
            rejected_pool.append({"prompt": prompt, "rejected": resp, "phase": phase, "record": r})
        else:
            by_phase.setdefault(phase, []).append({"prompt": prompt, "chosen": resp, "record": r})

    samples = []
    for rej in rejected_pool:
        phase = rej["phase"]
        candidates = by_phase.get(phase, []) or sum(by_phase.values(), [])
        if not candidates:
            continue
        chosen_entry = candidates[0]
        samples.append({
            "prompt": rej["prompt"],
            "chosen": chosen_entry["chosen"],
            "rejected": rej["rejected"],
            "metadata": {
                "task_id": rej["record"].get("task_id"),
                "phase": phase,
                "reject_reason": rej["record"].get("finish_reason"),
            },
        })

    return samples


# ---------------------------------------------------------------------------
# CoT export
# Group records by task_id, emit one long multi-turn chain per task.
# Each chain preserves the full request messages + assistant response + tool calls.
# ---------------------------------------------------------------------------

def _build_cot_chain(task_id: str, records: list[dict]) -> dict | None:
    turns = []
    for r in sorted(records, key=lambda x: x.get("timestamp", "")):
        req = r.get("request_preview")
        if not isinstance(req, list):
            continue
        resp = r.get("response_preview", "")
        tool_calls = r.get("tool_calls", [])

        assistant_parts = []
        if resp:
            assistant_parts.append({"type": "text", "text": resp})
        for tc in tool_calls:
            assistant_parts.append({
                "type": "tool_use",
                "name": tc.get("name"),
                "input": tc.get("input", {}),
            })

        turns.append({
            "phase": r.get("phase"),
            "request": req,
            "response": assistant_parts if assistant_parts else resp,
            "tokens": {
                "prompt": r.get("prompt_tokens"),
                "completion": r.get("completion_tokens"),
            },
        })

    if not turns:
        return None

    return {
        "task_id": task_id,
        "turns": turns,
        "total_turns": len(turns),
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Export paper2repro corpus to training datasets")
    parser.add_argument("--output-root", default="output", help="paper2repro output/ directory")
    parser.add_argument("--task", help="Export a single task by ID (e.g. paper_87d8010e)")
    parser.add_argument("--format", nargs="+", choices=["sft", "dpo", "cot"], default=["sft", "dpo", "cot"])
    parser.add_argument("--out", default="datasets", help="Output directory for .jsonl files")
    args = parser.parse_args()

    output_root = Path(args.output_root)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Collect task directories
    if args.task:
        task_dirs = [output_root / "tasks" / args.task]
    else:
        task_dirs = _find_task_dirs(output_root)

    if not task_dirs:
        print("No tasks found.", file=sys.stderr)
        sys.exit(1)

    all_llm: list[dict] = []
    task_llm: dict[str, list[dict]] = {}

    for td in task_dirs:
        llm_path = td / "logs" / "llm.jsonl"
        if not llm_path.exists():
            continue
        records = _load_jsonl(llm_path)
        task_id = td.name
        task_llm[task_id] = records
        all_llm.extend(records)

    print(f"Loaded {len(all_llm)} LLM records from {len(task_llm)} tasks")

    stats: dict[str, int] = {}

    # SFT
    if "sft" in args.format:
        sft_path = out_dir / "sft.jsonl"
        count = 0
        with sft_path.open("w") as f:
            for r in all_llm:
                sample = _build_sft_sample(r)
                if sample:
                    f.write(json.dumps(sample, ensure_ascii=False) + "\n")
                    count += 1
        stats["sft"] = count
        print(f"SFT: {count} samples → {sft_path}")

    # DPO
    if "dpo" in args.format:
        dpo_path = out_dir / "dpo.jsonl"
        samples = _build_dpo_samples(all_llm)
        with dpo_path.open("w") as f:
            for s in samples:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
        stats["dpo"] = len(samples)
        print(f"DPO: {len(samples)} pairs → {dpo_path}")

    # CoT
    if "cot" in args.format:
        cot_path = out_dir / "cot.jsonl"
        count = 0
        with cot_path.open("w") as f:
            for task_id, records in task_llm.items():
                chain = _build_cot_chain(task_id, records)
                if chain:
                    f.write(json.dumps(chain, ensure_ascii=False) + "\n")
                    count += 1
        stats["cot"] = count
        print(f"CoT: {count} chains → {cot_path}")

    print("\nDone. Summary:", stats)


if __name__ == "__main__":
    main()
