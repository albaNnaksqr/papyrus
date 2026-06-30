from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from trajectory.normalize_skill_run import normalize_skill_run


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _build_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    outcomes: Counter[str] = Counter()
    failure_types: Counter[str] = Counter()
    runners: Counter[str] = Counter()
    for record in records:
        outcomes.update([record.get("labels", {}).get("outcome") or "unknown"])
        runners.update([record.get("run", {}).get("runner") or "unknown"])
        failure_types.update(record.get("labels", {}).get("failure_types") or [])

    return {
        "total_runs": len(records),
        "runners": dict(sorted(runners.items())),
        "outcomes": dict(sorted(outcomes.items())),
        "failure_types": dict(sorted(failure_types.items())),
        "papers": [
            {
                "paper_id": record.get("paper", {}).get("paper_id"),
                "title": record.get("paper", {}).get("title"),
                "runner": record.get("run", {}).get("runner"),
                "outcome": record.get("labels", {}).get("outcome"),
                "overall_score": record.get("reward", {}).get("overall_score"),
                "strict_score": record.get("reward", {}).get("strict_overall_score"),
                "signal_coverage": record.get("reward", {}).get("signal_coverage"),
                "confidence": record.get("reward", {}).get("confidence"),
                "failure_types": record.get("labels", {}).get("failure_types") or [],
            }
            for record in records
        ],
    }


def normalize_projects(
    project_dirs: list[str | Path],
    *,
    jsonl_path: str | Path | None = None,
    summary_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    records = [normalize_skill_run(Path(project_dir)) for project_dir in project_dirs]
    if jsonl_path is not None:
        _write_jsonl(Path(jsonl_path), records)
    if summary_path is not None:
        path = Path(summary_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(_build_summary(records), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize one or more Papyrus skill runs")
    parser.add_argument("project_dirs", nargs="+", help="Skill reproduction project directories")
    parser.add_argument("--jsonl", required=True, help="Output normalized JSONL path")
    parser.add_argument("--summary", required=True, help="Output summary JSON path")
    args = parser.parse_args()

    normalize_projects(args.project_dirs, jsonl_path=args.jsonl, summary_path=args.summary)


if __name__ == "__main__":
    main()
