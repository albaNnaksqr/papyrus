"""Package wave2 reproduction records as an enriched dataset artifact.

The packager copies each normalized record and adds a dataset metadata block
derived from explicit source files. It does not mutate any run directory.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any


PAIRED_WITH = {
    "dora": "lora",
    "lookahead": "adam",
    "awq": "gptq",
    "medusa": "speculative_decoding",
    "smoothquant": "gptq",
    "prefix_tuning": "lora",
}

HYBRID_DIMS = ("1", "2", "6")
REPRODUCED_BUCKETS = ("fully_reproduced", "approximately_reproduced")

EVAL_SCALE_EXACT_KEYS = {
    "calibration_batches",
    "calibration_samples",
    "calibration_tokens",
    "eval_batches",
    "eval_examples",
    "eval_pair_count",
    "eval_rows_used",
    "eval_subset_size",
    "eval_tokens",
    "evaluated_prompts",
    "num_contexts",
    "test_examples",
    "valid_tokens_used",
    "val_examples",
    "validation_samples",
}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_normalized_record(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "normalized_record.jsonl"
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(lines) != 1:
        raise ValueError(f"{path} must contain exactly one non-empty JSONL record")
    return json.loads(lines[0])


def _run_key(run_dir: Path) -> str:
    return run_dir.name


def _display_name(run_dir: Path) -> str:
    name = run_dir.name
    return name[:-6] if name.endswith("_repro") else name


def _status_schema(evaluation: dict[str, Any]) -> dict[str, Any]:
    status_schema = evaluation.get("status_schema", evaluation)
    return status_schema if isinstance(status_schema, dict) else {}


def _line_count(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _reproduction_depth(d2_override: dict[str, Any]) -> str:
    note = str(d2_override.get("note") or "")
    score = d2_override.get("score")
    if "released" in note.lower():
        return "released_metrics_verification"
    if score is None:
        raise ValueError("d2 override is missing score")
    if score < 2:
        return "thin_directional_proxy"
    return "independent_real_run"


def _outcome_signal(evaluation: dict[str, Any]) -> str:
    status_schema = _status_schema(evaluation)
    for bucket in REPRODUCED_BUCKETS:
        for target in status_schema.get(bucket, []) or []:
            if not isinstance(target, dict):
                continue
            for check in target.get("checks", []) or []:
                if isinstance(check, dict) and check.get("passed") is False:
                    return "honest_negative"
    return "confirmed"


def _not_reproduced_count(evaluation: dict[str, Any]) -> int:
    return len(_status_schema(evaluation).get("not_reproduced", []) or [])


def _eval_scale_key(path: tuple[str, ...]) -> str | None:
    key = path[-1]
    parent = path[-2] if len(path) >= 2 else ""
    if key in EVAL_SCALE_EXACT_KEYS:
        return "_".join(path)
    if key == "tokens" and parent in {"calibration", "evaluation"}:
        return "_".join(path)
    if key == "records_used" and parent in {"calibration", "evaluation"}:
        return "_".join(path)
    if key == "token_count" and parent in {"validation_split", "test_split"}:
        return "_".join(path)
    return None


def _extract_eval_scale(summary: dict[str, Any]) -> dict[str, int | float] | None:
    found: dict[str, int | float] = {}

    def walk(value: Any, path: tuple[str, ...]) -> None:
        if isinstance(value, dict):
            for key in sorted(value):
                walk(value[key], path + (str(key),))
        elif isinstance(value, list):
            return
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            out_key = _eval_scale_key(path)
            if out_key is not None:
                found[out_key] = value

    walk(summary, ())
    return found or None


def _weakness_tag(dim: str, note: str) -> str:
    lower = note.lower()
    if "under-labelled" in lower or "underlabelled" in lower or "not explicitly flagged" in lower:
        return "underlabelled_thinness"
    if "single-sample" in lower or "single sample" in lower or "1 record" in lower:
        return "single_sample_calibration"
    if "released" in lower:
        return "released_data_lean"
    if "loose" in lower or "tolerance" in lower:
        return "loose_threshold"
    raise ValueError(f"cannot derive weakness tag for dim {dim} from override note: {note!r}")


def _weakness_tags(overrides: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    for dim in HYBRID_DIMS:
        override = overrides.get(dim)
        if not isinstance(override, dict):
            raise ValueError(f"missing hybrid dim {dim} override")
        score = override.get("score")
        if score is None:
            raise ValueError(f"missing hybrid dim {dim} score")
        if score < 2:
            tag = _weakness_tag(dim, str(override.get("note") or ""))
            if tag not in tags:
                tags.append(tag)
    return tags


def _scorecard_by_run(scorecard: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in scorecard:
        run = Path(str(row["run"])).name
        out[run] = row
    return out


def _git_output(args: list[str]) -> str:
    return subprocess.check_output(
        ["git", *args],
        text=True,
        encoding="utf-8",
    ).strip()


def _pipeline_commit() -> str:
    return _git_output(["rev-parse", "HEAD"])


def _created_at() -> str:
    return _git_output(["show", "-s", "--format=%cI", "HEAD"])


def enrich_record(
    run_dir: Path,
    scorecard_row: dict[str, Any],
    overrides: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    record = _load_normalized_record(run_dir)
    # Drop the legacy labels.data_split: it was a hardcoded "portfolio" heuristic
    # that predates and conflicts with the scorecard band. The authoritative band
    # is dataset.band; carry one band, not two. (The normalizer no longer emits
    # it; this also cleans older source records.)
    if isinstance(record.get("labels"), dict):
        record["labels"].pop("data_split", None)
    evaluation = _load_json(run_dir / "results" / "reproduction_evaluation.json")
    summary = _load_json(run_dir / "results" / "reproduction_summary.json")
    training_log = run_dir / "results" / "training_log.jsonl"
    optimizer_steps = _line_count(training_log) if training_log.exists() else None
    trains_model = optimizer_steps is not None and optimizer_steps >= 1
    if not trains_model:
        optimizer_steps = None

    d2_override = overrides.get("2")
    if not isinstance(d2_override, dict):
        raise ValueError(f"{run_dir.name} is missing d2 override")

    name = _display_name(run_dir)
    dataset = {
        "reproduction_depth": _reproduction_depth(d2_override),
        "outcome_signal": _outcome_signal(evaluation),
        "not_reproduced_count": _not_reproduced_count(evaluation),
        "trains_model": trains_model,
        "optimizer_steps": optimizer_steps,
        "eval_scale": _extract_eval_scale(summary),
        "has_repairs": len((record.get("trajectory") or {}).get("repair_attempts") or []) > 0,
        "paired_with": PAIRED_WITH.get(name),
        "band": scorecard_row["band"],
        "points": scorecard_row["points"],
        "weakness_tags": _weakness_tags(overrides),
    }
    record["dataset"] = dataset
    index = {
        "name": name,
        "band": dataset["band"],
        "points": dataset["points"],
        "reproduction_depth": dataset["reproduction_depth"],
        "outcome_signal": dataset["outcome_signal"],
        "not_reproduced_count": dataset["not_reproduced_count"],
        "weakness_tags": dataset["weakness_tags"],
        "paired_with": dataset["paired_with"],
    }
    return record, index


def package_dataset(
    run_dirs: list[Path],
    out_dir: Path,
    scorecard_path: Path,
    overrides_path: Path,
) -> dict[str, Any]:
    scorecard = _scorecard_by_run(_load_json(scorecard_path))
    overrides_by_run = _load_json(overrides_path)
    records: list[dict[str, Any]] = []
    index: list[dict[str, Any]] = []

    for run_dir in run_dirs:
        run_key = _run_key(run_dir)
        if run_key not in scorecard:
            raise ValueError(f"{run_key} missing from {scorecard_path}")
        if run_key not in overrides_by_run:
            raise ValueError(f"{run_key} missing from {overrides_path}")
        record, row = enrich_record(run_dir, scorecard[run_key], overrides_by_run[run_key])
        records.append(record)
        index.append(row)

    manifest = {
        "version": "wave2_v1",
        "created_at": _created_at(),
        "pipeline_commit": _pipeline_commit(),
        "record_count": len(records),
        "index": index,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "records.jsonl").write_text(
        "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _print_summary(index: list[dict[str, Any]]) -> None:
    headers = [
        "name",
        "band",
        "points",
        "reproduction_depth",
        "outcome_signal",
        "not_reproduced_count",
        "weakness_tags",
        "paired_with",
    ]
    rows = [
        [
            str(row["name"]),
            str(row["band"]),
            str(row["points"]),
            str(row["reproduction_depth"]),
            str(row["outcome_signal"]),
            str(row["not_reproduced_count"]),
            ",".join(row["weakness_tags"]) if row["weakness_tags"] else "",
            str(row["paired_with"] or ""),
        ]
        for row in index
    ]
    widths = [
        max(len(headers[i]), *(len(row[i]) for row in rows))
        for i in range(len(headers))
    ]
    print(" | ".join(headers[i].ljust(widths[i]) for i in range(len(headers))))
    print("-+-".join("-" * width for width in widths))
    for row in rows:
        print(" | ".join(row[i].ljust(widths[i]) for i in range(len(headers))))
    counts = Counter(row["band"] for row in index)
    print()
    print("band_distribution:", ", ".join(f"{band}={counts[band]}" for band in sorted(counts)))


def main() -> None:
    parser = argparse.ArgumentParser(description="Package wave2 reproduction records")
    parser.add_argument("run_dirs", nargs="+", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--scorecard", required=True, type=Path)
    parser.add_argument("--overrides", required=True, type=Path)
    args = parser.parse_args()

    manifest = package_dataset(args.run_dirs, args.out, args.scorecard, args.overrides)
    _print_summary(manifest["index"])


if __name__ == "__main__":
    main()
