from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


MAINLINE_PAPER_IDS = [
    "swe_bench_repro",
    "swe_agent_repro",
    "swe_bench_multimodal_repro",
]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            records.append(json.loads(stripped))
    return records


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _paper_id(record: dict[str, Any]) -> str:
    return str(record.get("paper", {}).get("paper_id") or "")


def _title(record: dict[str, Any]) -> str:
    return str(record.get("paper", {}).get("title") or _paper_id(record))


def _failure_types(record: dict[str, Any]) -> list[str]:
    return list(record.get("labels", {}).get("failure_types") or [])


def _benchmark_fidelity(record: dict[str, Any]) -> str:
    failures = set(_failure_types(record))
    if "full_benchmark_not_attempted" in failures:
        return "bounded_fixture_only"
    if "unavailable_original_benchmark_data" in failures:
        return "local_substitute"
    if "synthetic_fixture" in failures:
        return "mechanism_demo"
    return "local_claim_reproduction"


def _record_summary(record: dict[str, Any]) -> dict[str, Any]:
    reward = record.get("reward", {})
    labels = record.get("labels", {})
    failure = record.get("failure_analysis", {})
    artifacts = record.get("artifacts", {})
    return {
        "paper_id": _paper_id(record),
        "title": _title(record),
        "mainline": _paper_id(record) in MAINLINE_PAPER_IDS,
        "outcome": labels.get("outcome"),
        "reproduction_level": labels.get("reproduction_level"),
        "overall_score": reward.get("overall_score"),
        "strict_score": reward.get("strict_overall_score"),
        "signal_coverage": reward.get("signal_coverage"),
        "confidence": reward.get("confidence"),
        "benchmark_fidelity": _benchmark_fidelity(record),
        "failure_types": _failure_types(record),
        "primary_failure_type": failure.get("primary_failure_type"),
        "project_path": artifacts.get("generated_project_path"),
    }


def _build_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    papers = [_record_summary(record) for record in records]
    confidence_counts = Counter(paper["confidence"] or "unknown" for paper in papers)
    fidelity_counts = Counter(paper["benchmark_fidelity"] for paper in papers)
    outcome_counts = Counter(paper["outcome"] or "unknown" for paper in papers)
    failure_counts: Counter[str] = Counter()
    for paper in papers:
        failure_counts.update(paper["failure_types"])
    mainline = [paper for paper in papers if paper["mainline"]]

    return {
        "total_runs": len(records),
        "mainline_paper_ids": [paper["paper_id"] for paper in mainline],
        "confidence_counts": dict(sorted(confidence_counts.items())),
        "benchmark_fidelity_counts": dict(sorted(fidelity_counts.items())),
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "failure_type_counts": dict(sorted(failure_counts.items())),
        "papers": papers,
    }


def _format_score(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.4g}"


def _markdown_table(papers: list[dict[str, Any]]) -> str:
    lines = [
        "| paper | role | outcome | strict_score | confidence | benchmark_fidelity | key gaps |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for paper in papers:
        role = "mainline" if paper["mainline"] else "supporting"
        gaps = ", ".join(paper["failure_types"]) or "none"
        lines.append(
            "| "
            + " | ".join(
                [
                    paper["title"],
                    role,
                    str(paper["outcome"]),
                    _format_score(paper["strict_score"]),
                    str(paper["confidence"]),
                    paper["benchmark_fidelity"],
                    gaps,
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _portfolio_markdown(summary: dict[str, Any]) -> str:
    papers = summary["papers"]
    mainline_titles = [
        paper["title"]
        for paper in papers
        if paper["paper_id"] in summary["mainline_paper_ids"]
    ]
    return (
        "# Code Agent Reproduction Portfolio Dataset Card\n\n"
        "This portfolio treats paper reproductions as trajectory-data samples, not as "
        "leaderboard replications. Each run records a bounded claim, executable evidence, "
        "failure labels, and reward signals for downstream analysis.\n\n"
        "## Summary\n\n"
        f"- Total runs: {summary['total_runs']}\n"
        f"- Mainline case: {', '.join(mainline_titles)}\n"
        f"- Confidence counts: {summary['confidence_counts']}\n"
        f"- Benchmark fidelity counts: {summary['benchmark_fidelity_counts']}\n\n"
        "## Code Agent Trajectory Data Pipeline\n\n"
        "The mainline case focuses on SWE-bench, SWE-agent, and SWE-bench Multimodal as "
        "a three-part trajectory data pipeline.\n\n"
        "## Score Semantics\n\n"
        "- `overall_score`: compatibility score that ignores missing reward signals.\n"
        "- `strict_score`: weighted score where missing reward signals count as zero.\n"
        "- `signal_coverage`: fraction of reward weight backed by observed signals.\n"
        "- `benchmark_fidelity`: distance from the paper's original benchmark setting.\n\n"
        "## Runs\n\n"
        f"{_markdown_table(papers)}\n\n"
        "## Positioning\n\n"
        "The strongest claim is not that these are full-paper reproductions. The stronger "
        "portfolio claim is that the project converts code-agent papers into auditable "
        "trajectory data: issue or task setup, local evidence, patch or action sequence, "
        "test outcomes, honesty labels, and scoring metadata.\n"
    )


def _case_markdown(summary: dict[str, Any]) -> str:
    papers_by_id = {paper["paper_id"]: paper for paper in summary["papers"]}
    mainline = [papers_by_id[paper_id] for paper_id in MAINLINE_PAPER_IDS if paper_id in papers_by_id]
    return (
        "# Code Agent Trajectory Data Pipeline\n\n"
        "This case study packages the three most relevant runs for a code-agent data role. "
        "The common data product is a normalized trajectory record that links a paper claim "
        "to executable local evidence and explicit fidelity gaps.\n\n"
        "## Mainline Papers\n\n"
        f"{_markdown_table(mainline)}\n\n"
        "## Data Product\n\n"
        "- `SWE-bench`: patch-evaluation schema with FAIL_TO_PASS and PASS_TO_PASS evidence.\n"
        "- `SWE-agent`: inspect/edit/test action trace over a local software issue.\n"
        "- `SWE-bench Multimodal`: visual issue fixture with pre/post screenshot evidence.\n\n"
        "## Why This Matters\n\n"
        "For code-agent data work, the useful artifact is not a polished demo alone. It is "
        "the structured record that can be filtered, scored, audited, and turned into "
        "training or evaluation examples. These three runs cover patch evaluation, agent "
        "tool-use trajectories, and multimodal software evidence.\n\n"
        "## Remaining Work\n\n"
        "- Replace selected synthetic fixtures with real issue subsets where licensing and "
        "runtime allow it.\n"
        "- Add stricter schema checks for action traces, screenshots, and test status maps.\n"
        "- Separate bounded-claim success from full-benchmark fidelity in every public view.\n"
    )


def export_portfolio(
    records: list[dict[str, Any]],
    *,
    json_path: str | Path,
    markdown_path: str | Path,
    case_path: str | Path,
) -> dict[str, Any]:
    summary = _build_summary(records)
    _write_json(Path(json_path), summary)
    _write_text(Path(markdown_path), _portfolio_markdown(summary))
    _write_text(Path(case_path), _case_markdown(summary))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a portfolio view from normalized runs")
    parser.add_argument("normalized_jsonl", help="Input normalized JSONL path")
    parser.add_argument("--json", required=True, help="Output portfolio summary JSON")
    parser.add_argument("--markdown", required=True, help="Output portfolio dataset card Markdown")
    parser.add_argument("--case", required=True, help="Output mainline case-study Markdown")
    args = parser.parse_args()

    export_portfolio(
        _read_jsonl(Path(args.normalized_jsonl)),
        json_path=args.json,
        markdown_path=args.markdown,
        case_path=args.case,
    )


if __name__ == "__main__":
    main()
