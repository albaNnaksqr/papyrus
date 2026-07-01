from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


KNOWN_RUN_SUFFIXES = (
    "_repro",
    "_claude",
    "-repro",
    "-claude",
)


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    records = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped:
            records.append(json.loads(stripped))
    return records


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(path: str | Path, text: str) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")


def _paper_id(record: dict[str, Any]) -> str:
    return str(record.get("paper", {}).get("paper_id") or "")


def _paper_title(record: dict[str, Any]) -> str:
    return str(record.get("paper", {}).get("title") or _paper_id(record))


def _paper_key(record: dict[str, Any]) -> str:
    key = _paper_id(record).strip().lower().replace("-", "_")
    for suffix in KNOWN_RUN_SUFFIXES:
        normalized_suffix = suffix.replace("-", "_")
        if key.endswith(normalized_suffix):
            key = key[: -len(normalized_suffix)]
            break
    return key


def _count(record: dict[str, Any], field: str) -> int:
    value = record.get("trajectory", {}).get(field)
    return len(value) if isinstance(value, list) else 0


def _strict_score(record: dict[str, Any]) -> float:
    score = record.get("reward", {}).get("strict_overall_score")
    return float(score) if isinstance(score, int | float) else 0.0


def _rounded(value: float) -> float:
    return round(value, 4)


def _fmt(value: float) -> str:
    rounded = round(value, 4)
    text = f"{rounded:.4f}".rstrip("0").rstrip(".")
    if "." not in text:
        text += ".0"
    return text


def _run_summary(record: dict[str, Any]) -> dict[str, Any]:
    failure_types = record.get("labels", {}).get("failure_types") or []
    summary = {
        "paper_id": _paper_id(record),
        "title": _paper_title(record),
        "outcome": record.get("labels", {}).get("outcome") or "unknown",
        "strict_score": _rounded(_strict_score(record)),
        "overall_score": record.get("reward", {}).get("overall_score"),
        "confidence": record.get("reward", {}).get("confidence"),
        "signal_coverage": record.get("reward", {}).get("signal_coverage"),
        "actions": _count(record, "actions"),
        "edits": _count(record, "edit_metadata"),
        "repair_attempts": _count(record, "repair_attempts"),
        "reflection_events": _count(record, "reflection_events"),
        "failure_types": list(failure_types),
    }
    summary["usefulness_tags"] = _usefulness_tags(summary, record)
    return summary


def _usefulness_tags(summary: dict[str, Any], record: dict[str, Any]) -> list[str]:
    tags = []
    result_files = record.get("artifacts", {}).get("result_files") or []
    outcome = summary["outcome"]
    strict_score = summary["strict_score"]
    if outcome in {"success", "partial_success"} and (strict_score >= 0.5 or result_files):
        tags.append("artifact_sample")
    if summary["actions"] >= 10 and summary["edits"] >= 2:
        tags.append("trajectory_sample")
    if summary["repair_attempts"] > 0 or summary["reflection_events"] > 0:
        tags.append("repair_sample")
    if summary["failure_types"]:
        tags.append("gap_sample")
    if outcome in {"failure", "invalid_run"} or strict_score < 0.6:
        tags.append("negative_sample")
    return tags


def _choose_preferred(left: dict[str, Any], right: dict[str, Any], left_label: str, right_label: str) -> dict[str, str]:
    def choose(left_value: float, right_value: float) -> str:
        if left_value > right_value:
            return left_label
        if right_value > left_value:
            return right_label
        return "tie"

    left_repair = left["repair_attempts"] + left["reflection_events"]
    right_repair = right["repair_attempts"] + right["reflection_events"]
    left_trajectory = left["actions"] + left["edits"]
    right_trajectory = right["actions"] + right["edits"]
    return {
        "artifact_sample": choose(left["strict_score"], right["strict_score"]),
        "trajectory_sample": choose(left_trajectory, right_trajectory),
        "repair_sample": choose(left_repair, right_repair),
    }


def _aggregate(pairs: list[dict[str, Any]], label: str) -> dict[str, Any]:
    if not pairs:
        return {
            "paired_runs": 0,
            "avg_strict_score": 0.0,
            "actions": 0,
            "edits": 0,
            "repair_attempts": 0,
            "reflection_events": 0,
        }
    runs = [pair[label] for pair in pairs]
    return {
        "paired_runs": len(runs),
        "avg_strict_score": _rounded(sum(run["strict_score"] for run in runs) / len(runs)),
        "actions": sum(run["actions"] for run in runs),
        "edits": sum(run["edits"] for run in runs),
        "repair_attempts": sum(run["repair_attempts"] for run in runs),
        "reflection_events": sum(run["reflection_events"] for run in runs),
    }


def build_paired_comparison(
    left_records: list[dict[str, Any]],
    right_records: list[dict[str, Any]],
    *,
    left_label: str = "left",
    right_label: str = "right",
) -> dict[str, Any]:
    left_by_key = {_paper_key(record): record for record in left_records}
    right_by_key = {_paper_key(record): record for record in right_records}
    paired_keys = sorted(set(left_by_key) & set(right_by_key))

    pairs = []
    for key in paired_keys:
        left = _run_summary(left_by_key[key])
        right = _run_summary(right_by_key[key])
        pair = {
            "paper_key": key,
            "title": left["title"] if left["title"] != key else right["title"],
            left_label: left,
            right_label: right,
            "deltas": {
                "strict_score": _rounded(right["strict_score"] - left["strict_score"]),
                "actions": right["actions"] - left["actions"],
                "edits": right["edits"] - left["edits"],
                "repair_attempts": right["repair_attempts"] - left["repair_attempts"],
                "reflection_events": right["reflection_events"] - left["reflection_events"],
            },
            "preferred_for": _choose_preferred(left, right, left_label, right_label),
        }
        pairs.append(pair)

    aggregate = {
        left_label: _aggregate(pairs, left_label),
        right_label: _aggregate(pairs, right_label),
    }
    aggregate["deltas"] = {
        key: _rounded(aggregate[right_label][key] - aggregate[left_label][key])
        for key in ["avg_strict_score", "actions", "edits", "repair_attempts", "reflection_events"]
    }

    return {
        "left_label": left_label,
        "right_label": right_label,
        "total_pairs": len(pairs),
        "pairs": pairs,
        "unpaired": {
            left_label: [_paper_id(left_by_key[key]) for key in sorted(set(left_by_key) - set(right_by_key))],
            right_label: [_paper_id(right_by_key[key]) for key in sorted(set(right_by_key) - set(left_by_key))],
        },
        "aggregate": aggregate,
    }


def _tags(tags: list[str]) -> str:
    return ", ".join(f"`{tag}`" for tag in tags) if tags else "none"


def render_markdown_report(comparison: dict[str, Any]) -> str:
    left_label = comparison["left_label"]
    right_label = comparison["right_label"]
    aggregate = comparison["aggregate"]
    lines = [
        "# Paired Trajectory Comparison",
        "",
        "This report is generated from normalized Papyrus trajectory JSONL records. It pairs runs by normalized paper id and compares the data utility of each run, not the intrinsic quality of the underlying agent.",
        "",
        "## Aggregate",
        "",
        "| side | paired_runs | avg_strict_score | actions | edits | repairs | reflections |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for label in [left_label, right_label]:
        data = aggregate[label]
        lines.append(
            f"| {label} | {data['paired_runs']} | {_fmt(data['avg_strict_score'])} | "
            f"{data['actions']} | {data['edits']} | {data['repair_attempts']} | "
            f"{data['reflection_events']} |"
        )
    deltas = aggregate["deltas"]
    lines.extend(
        [
            f"| delta ({right_label}-{left_label}) |  | {_fmt(deltas['avg_strict_score'])} | "
            f"{deltas['actions']} | {deltas['edits']} | {deltas['repair_attempts']} | "
            f"{deltas['reflection_events']} |",
            "",
            "## Paired Runs",
            "",
            f"| paper | {left_label} outcome / strict | {right_label} outcome / strict | strict_delta | action_delta | repair_delta | reflection_delta | {left_label} tags | {right_label} tags | preferred uses |",
            "|---|---:|---:|---:|---:|---:|---:|---|---|---|",
        ]
    )
    for pair in comparison["pairs"]:
        left = pair[left_label]
        right = pair[right_label]
        deltas = pair["deltas"]
        preferred = ", ".join(
            f"{use}:{label}" for use, label in pair["preferred_for"].items()
        )
        lines.append(
            f"| {pair['title']} | {left['outcome']} / {_fmt(left['strict_score'])} | "
            f"{right['outcome']} / {_fmt(right['strict_score'])} | "
            f"{_fmt(deltas['strict_score'])} | {deltas['actions']} | "
            f"{deltas['repair_attempts']} | {deltas['reflection_events']} | "
            f"{_tags(left['usefulness_tags'])} | {_tags(right['usefulness_tags'])} | "
            f"{preferred} |"
        )

    lines.extend(
        [
            "",
            "## Usefulness Tags",
            "",
            "- `artifact_sample`: useful as a bounded executable reproduction artifact.",
            "- `trajectory_sample`: enough action/edit structure to analyze agent behavior.",
            "- `repair_sample`: contains validation-failure to repair/reflection supervision.",
            "- `gap_sample`: contains explicit benchmark, resource, fixture, or environment gaps.",
            "- `negative_sample`: useful as a failed, invalid, or low-fidelity example.",
            "",
            "## Unpaired Runs",
            "",
            f"- {left_label}: {', '.join(comparison['unpaired'][left_label]) or 'none'}",
            f"- {right_label}: {', '.join(comparison['unpaired'][right_label]) or 'none'}",
            "",
        ]
    )
    return "\n".join(lines)


def write_paired_outputs(
    left_jsonl: str | Path,
    right_jsonl: str | Path,
    *,
    summary_path: str | Path,
    report_path: str | Path,
    left_label: str = "left",
    right_label: str = "right",
) -> dict[str, Any]:
    comparison = build_paired_comparison(
        _read_jsonl(left_jsonl),
        _read_jsonl(right_jsonl),
        left_label=left_label,
        right_label=right_label,
    )
    _write_json(summary_path, comparison)
    _write_text(report_path, render_markdown_report(comparison))
    return comparison


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare paired normalized Papyrus runs")
    parser.add_argument("--left", required=True, help="Left normalized JSONL path")
    parser.add_argument("--right", required=True, help="Right normalized JSONL path")
    parser.add_argument("--left-label", default="left", help="Left side label")
    parser.add_argument("--right-label", default="right", help="Right side label")
    parser.add_argument("--summary", required=True, help="Output paired summary JSON path")
    parser.add_argument("--report", required=True, help="Output Markdown report path")
    args = parser.parse_args()

    write_paired_outputs(
        args.left,
        args.right,
        summary_path=args.summary,
        report_path=args.report,
        left_label=args.left_label,
        right_label=args.right_label,
    )


if __name__ == "__main__":
    main()
