from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from trajectory.compare_paired_runs import _run_summary


REPAIR_STRICT_LABELS = {"true_positive"}
REPAIR_LENIENT_LABELS = {"true_positive", "partial"}
REPAIR_ERROR_LABELS = {"false_positive"}

REFLECTION_STRICT_LABELS = {"root_cause"}
REFLECTION_LENIENT_LABELS = {"root_cause", "plan_adjustment"}
REFLECTION_ERROR_LABELS = {"procedural", "false_positive"}


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    records = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped:
            records.append(json.loads(stripped))
    return records


def _read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


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


def _trajectory_count(record: dict[str, Any], field: str) -> int:
    value = record.get("trajectory", {}).get(field)
    return len(value) if isinstance(value, list) else 0


def _rounded(value: float) -> float:
    return round(value, 4)


def _fmt(value: float) -> str:
    rounded = round(value, 4)
    text = f"{rounded:.4f}".rstrip("0").rstrip(".")
    if "." not in text:
        text += ".0"
    return text


def _safe_divide(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return _rounded(numerator / denominator)


def _label_list(record_labels: dict[str, Any], field: str) -> list[dict[str, Any]]:
    value = record_labels.get(field) or []
    return value if isinstance(value, list) else []


def _gold_tags(record_labels: dict[str, Any]) -> list[str]:
    value = record_labels.get("usefulness_tags") or {}
    tags = value.get("gold") if isinstance(value, dict) else []
    return [str(tag) for tag in tags] if isinstance(tags, list) else []


def _signal_metrics(
    records: list[dict[str, Any]],
    labels_by_id: dict[str, Any],
    *,
    field: str,
    strict_labels: set[str],
    lenient_labels: set[str],
    error_labels: set[str],
) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
    labeled_count = 0
    strict_count = 0
    lenient_count = 0
    error_cases = []

    for record in records:
        paper_id = _paper_id(record)
        record_labels = labels_by_id.get(paper_id) or {}
        for label_entry in _label_list(record_labels, field):
            label = str(label_entry.get("label") or "")
            labeled_count += 1
            if label in strict_labels:
                strict_count += 1
            if label in lenient_labels:
                lenient_count += 1
            if label in error_labels:
                error_cases.append(
                    {
                        "paper_id": paper_id,
                        "index": label_entry.get("index"),
                        "label": label,
                        "note": label_entry.get("note", ""),
                    }
                )

    return (
        {
            "strict_precision": _safe_divide(strict_count, labeled_count),
            "lenient_precision": _safe_divide(lenient_count, labeled_count),
            "labeled": labeled_count,
        },
        error_cases,
        labeled_count,
    )


def _usefulness_metrics(
    records: list[dict[str, Any]],
    labels_by_id: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
    predicted_total = 0
    gold_total = 0
    correct_total = 0
    runs_with_gold = 0
    error_cases = []

    for record in records:
        paper_id = _paper_id(record)
        record_labels = labels_by_id.get(paper_id) or {}
        gold = set(_gold_tags(record_labels))
        if not gold:
            continue

        runs_with_gold += 1
        predicted = set(_run_summary(record).get("usefulness_tags") or [])
        predicted_total += len(predicted)
        gold_total += len(gold)
        correct_total += len(predicted & gold)

        false_positive_tags = sorted(predicted - gold)
        missing_tags = sorted(gold - predicted)
        if false_positive_tags or missing_tags:
            error_cases.append(
                {
                    "paper_id": paper_id,
                    "false_positive_tags": false_positive_tags,
                    "missing_tags": missing_tags,
                }
            )

    return (
        {
            "precision": _safe_divide(correct_total, predicted_total),
            "recall": _safe_divide(correct_total, gold_total),
            "predicted": predicted_total,
            "gold": gold_total,
            "correct": correct_total,
        },
        error_cases,
        runs_with_gold,
    )


def evaluate_calibration(records: list[dict[str, Any]], labels: dict[str, Any]) -> dict[str, Any]:
    labels_by_id = labels.get("records") or {}
    if not isinstance(labels_by_id, dict):
        labels_by_id = {}

    repair_metrics, repair_errors, repair_labeled = _signal_metrics(
        records,
        labels_by_id,
        field="repair_attempts",
        strict_labels=REPAIR_STRICT_LABELS,
        lenient_labels=REPAIR_LENIENT_LABELS,
        error_labels=REPAIR_ERROR_LABELS,
    )
    reflection_metrics, reflection_errors, reflection_labeled = _signal_metrics(
        records,
        labels_by_id,
        field="reflection_events",
        strict_labels=REFLECTION_STRICT_LABELS,
        lenient_labels=REFLECTION_LENIENT_LABELS,
        error_labels=REFLECTION_ERROR_LABELS,
    )
    usefulness_metrics, usefulness_errors, usefulness_runs = _usefulness_metrics(records, labels_by_id)

    labeled_record_count = sum(1 for record in records if _paper_id(record) in labels_by_id)
    return {
        "schema_version": "papyrus.calibration.summary.v1",
        "coverage": {
            "records": {"total": len(records), "labeled": labeled_record_count},
            "repair_attempts": {
                "extracted": sum(_trajectory_count(record, "repair_attempts") for record in records),
                "labeled": repair_labeled,
            },
            "reflection_events": {
                "extracted": sum(_trajectory_count(record, "reflection_events") for record in records),
                "labeled": reflection_labeled,
            },
            "usefulness_tags": {"runs_with_gold": usefulness_runs},
        },
        "repair_attempts": repair_metrics,
        "reflection_events": reflection_metrics,
        "usefulness_tags": usefulness_metrics,
        "error_cases": {
            "repair_attempts": repair_errors,
            "reflection_events": reflection_errors,
            "usefulness_tags": usefulness_errors,
        },
    }


def render_calibration_report(summary: dict[str, Any]) -> str:
    coverage = summary["coverage"]
    repair = summary["repair_attempts"]
    reflection = summary["reflection_events"]
    usefulness = summary["usefulness_tags"]
    errors = summary.get("error_cases", {})

    lines = [
        "# Trajectory Calibration Report",
        "",
        "This report compares rule-derived Papyrus trajectory labels against manually reviewed calibration labels. It measures whether the structured labels are credible enough to use as data signals.",
        "",
        "## Coverage",
        "",
        f"- Records: {coverage['records']['labeled']} labeled / {coverage['records']['total']} total.",
        f"- Repair attempts: {coverage['repair_attempts']['labeled']} labeled / {coverage['repair_attempts']['extracted']} extracted.",
        f"- Reflection events: {coverage['reflection_events']['labeled']} labeled / {coverage['reflection_events']['extracted']} extracted.",
        f"- Usefulness tags: {coverage['usefulness_tags']['runs_with_gold']} runs with gold tags.",
        "",
        "## Metrics",
        "",
        "| signal | extracted | labeled | strict_precision | lenient_precision |",
        "|---|---:|---:|---:|---:|",
        f"| repair_attempts | {coverage['repair_attempts']['extracted']} | {coverage['repair_attempts']['labeled']} | {_fmt(repair['strict_precision'])} | {_fmt(repair['lenient_precision'])} |",
        f"| reflection_events | {coverage['reflection_events']['extracted']} | {coverage['reflection_events']['labeled']} | {_fmt(reflection['strict_precision'])} | {_fmt(reflection['lenient_precision'])} |",
        f"| usefulness_tags | {coverage['usefulness_tags']['runs_with_gold']} runs | {coverage['usefulness_tags']['runs_with_gold']} runs | {_fmt(usefulness['precision'])} | {_fmt(usefulness['recall'])} |",
        "",
        "## Interpretation",
        "",
        "- Strict precision counts only direct root-cause repair/reflection evidence.",
        "- Lenient precision also credits partial repairs and plan-adjustment reflections.",
        "- Usefulness precision/recall evaluates run-level sample tags against gold tags.",
        "",
        "## Error Cases",
        "",
    ]

    for field in ["repair_attempts", "reflection_events"]:
        cases = errors.get(field) or []
        lines.extend([f"### {field}", ""])
        if not cases:
            lines.extend(["None.", ""])
            continue
        lines.extend(["| paper_id | index | label | note |", "|---|---:|---|---|"])
        for case in cases:
            note = str(case.get("note") or "").replace("|", "\\|")
            lines.append(f"| {case['paper_id']} | {case.get('index')} | {case['label']} | {note} |")
        lines.append("")

    tag_cases = errors.get("usefulness_tags") or []
    lines.extend(["### usefulness_tags", ""])
    if not tag_cases:
        lines.extend(["None.", ""])
    else:
        lines.extend(["| paper_id | false_positive_tags | missing_tags |", "|---|---|---|"])
        for case in tag_cases:
            false_positive = ", ".join(case.get("false_positive_tags") or []) or "none"
            missing = ", ".join(case.get("missing_tags") or []) or "none"
            lines.append(f"| {case['paper_id']} | {false_positive} | {missing} |")
        lines.append("")

    return "\n".join(lines)


def write_calibration_outputs(
    record_paths: list[str | Path],
    labels_path: str | Path,
    *,
    summary_path: str | Path,
    report_path: str | Path,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for path in record_paths:
        records.extend(_read_jsonl(path))

    summary = evaluate_calibration(records, _read_json(labels_path))
    _write_json(summary_path, summary)
    _write_text(report_path, render_calibration_report(summary))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Papyrus trajectory labels against calibration labels")
    parser.add_argument("--records", nargs="+", required=True, help="Normalized trajectory JSONL paths")
    parser.add_argument("--labels", required=True, help="Calibration labels JSON path")
    parser.add_argument("--summary", required=True, help="Output calibration summary JSON path")
    parser.add_argument("--report", required=True, help="Output calibration Markdown report path")
    args = parser.parse_args()

    write_calibration_outputs(
        args.records,
        args.labels,
        summary_path=args.summary,
        report_path=args.report,
    )


if __name__ == "__main__":
    main()
