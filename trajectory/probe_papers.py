from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pdfplumber


KNOWN_PAPERS: dict[str, dict[str, Any]] = {
    "boyer_moore": {
        "title": "A Fast String Searching Algorithm",
        "paper_type": "algorithm",
        "likely_failure_types": [
            "unavailable_original_benchmark_data",
            "nonportable_hardware_metric",
        ],
        "recommended_runner": "already_completed_skill_run",
        "probe_reason": "Existing completed skill run with clear algorithm and nonportable original benchmark metrics.",
    },
    "adam": {
        "title": "Adam: A Method for Stochastic Optimization",
        "paper_type": "ml_experiment",
        "likely_failure_types": [
            "hyperparameter_missing",
            "metric_mismatch",
            "dataset_unavailable",
        ],
        "recommended_runner": "skill_deep_run",
        "probe_reason": "Short paper with equations and bounded optimizer experiments.",
    },
    "dropout": {
        "title": "Dropout: A Simple Way to Prevent Neural Networks from Overfitting",
        "paper_type": "ml_experiment",
        "likely_failure_types": [
            "dataset_unavailable",
            "hyperparameter_missing",
            "compute_budget_limit",
        ],
        "recommended_runner": "contract_only_then_select",
        "probe_reason": "Long ML experiment paper with many datasets and training settings.",
    },
    "raft": {
        "title": "In Search of an Understandable Consensus Algorithm",
        "paper_type": "systems",
        "likely_failure_types": [
            "environment_failure",
            "workload_unavailable",
            "implementation_scope_large",
        ],
        "recommended_runner": "skill_deep_run",
        "probe_reason": "Systems paper with clear protocol but broad implementation surface.",
    },
    "mapreduce": {
        "title": "MapReduce: Simplified Data Processing on Large Clusters",
        "paper_type": "systems",
        "likely_failure_types": [
            "environment_failure",
            "workload_unavailable",
            "nonportable_cluster_metric",
        ],
        "recommended_runner": "contract_only_then_select",
        "probe_reason": "Cluster-scale evaluation is not portable to local runs.",
    },
}


def _extract_text_and_pages(pdf_path: Path, max_pages: int = 3) -> tuple[str, int]:
    parts: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        page_count = len(pdf.pages)
        for page in pdf.pages[:max_pages]:
            text = page.extract_text() or ""
            if text.strip():
                parts.append(text)
    return "\n".join(parts), page_count


def _infer_from_text(paper_id: str, text: str) -> dict[str, Any]:
    lowered = text.lower()
    if any(term in lowered for term in ["consensus", "replicated log", "fault-tolerant"]):
        paper_type = "systems"
    elif any(term in lowered for term in ["neural network", "mnist", "training", "gradient"]):
        paper_type = "ml_experiment"
    elif any(term in lowered for term in ["algorithm", "proof", "complexity"]):
        paper_type = "algorithm"
    else:
        paper_type = "unknown"

    labels: list[str] = []
    if paper_type == "ml_experiment":
        labels.extend(["hyperparameter_missing", "metric_mismatch"])
        if any(term in lowered for term in ["mnist", "cifar", "dataset"]):
            labels.append("dataset_unavailable")
    if paper_type == "systems":
        labels.extend(["environment_failure", "workload_unavailable"])
    if paper_type == "algorithm":
        labels.append("evaluator_gap")

    title = next((line.strip() for line in text.splitlines() if line.strip()), paper_id)
    return {
        "title": title[:160],
        "paper_type": paper_type,
        "likely_failure_types": sorted(set(labels)),
        "recommended_runner": "contract_only_then_select",
        "probe_reason": "Inferred from PDF text heuristics.",
    }


def probe_paper(pdf_path: str | Path) -> dict[str, Any]:
    path = Path(pdf_path).resolve()
    paper_id = path.stem.lower().replace("-", "_")
    text, page_count = _extract_text_and_pages(path)

    known = KNOWN_PAPERS.get(paper_id)
    inferred = known or _infer_from_text(paper_id, text)
    return {
        "paper_id": paper_id,
        "source_path": str(path),
        "title": inferred["title"],
        "paper_type": inferred["paper_type"],
        "page_count": page_count,
        "sample_text_chars": len(text),
        "likely_failure_types": inferred["likely_failure_types"],
        "recommended_runner": inferred["recommended_runner"],
        "probe_reason": inferred["probe_reason"],
    }


def probe_many(pdf_paths: list[str | Path]) -> list[dict[str, Any]]:
    return [probe_paper(path) for path in pdf_paths]


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe paper PDFs for portfolio run selection")
    parser.add_argument("pdfs", nargs="+", help="PDF files to probe")
    parser.add_argument("--out", required=True, help="Output JSON path")
    args = parser.parse_args()

    probes = probe_many(args.pdfs)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"papers": probes}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
