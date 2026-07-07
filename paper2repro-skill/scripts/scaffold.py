#!/usr/bin/env python3
"""Generate standard project skeleton from structure config JSON."""
import json
import sys
from pathlib import Path

DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent / "output"

# Evaluator template. Thresholds are NOT hardcoded here: it loads every
# threshold from reproduction_contract.json's per-target `criteria_checks`
# (see SKILL.md "threshold provenance" hard rule). The agent's only job is to
# map each check `name` to the measured value in results/reproduction_summary.json
# via MEASURED_VALUES; the comparator and status logic stay contract-driven.
EVALUATE_REPRODUCTION_TEMPLATE = r'''"""Evaluate outputs against reproduction_contract.json.

Thresholds come from the contract's `criteria_checks`, never from literals in
this file. Fill in MEASURED_VALUES to point each declared check name at the
value your experiment wrote to results/reproduction_summary.json.
"""
from pathlib import Path
import json

_OPS = {
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


def _measured_values(result: dict) -> dict:
    """Map each criteria_checks `name` to a measured number from the summary.

    Replace this with the real lookup once run_experiment.py is implemented,
    e.g. {"held_out_accuracy": result["accuracy"], ...}. Do NOT put pass/fail
    thresholds here — only measured values.
    """
    return {}


def main():
    root = Path(__file__).resolve().parents[1]
    contract = json.loads((root / "reproduction_contract.json").read_text(encoding="utf-8"))
    result_path = root / "results" / "reproduction_summary.json"
    if not result_path.exists():
        raise SystemExit("Missing results/reproduction_summary.json. Run scripts/run_experiment.py first.")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    measured = _measured_values(result)

    fully, approx, not_repro = [], [], []
    for target in contract.get("reproduction_targets", []):
        if not isinstance(target, dict):
            not_repro.append({"item": target, "reason": "target is not structured"})
            continue
        name = target.get("target", "unknown")
        checks = target.get("criteria_checks") or []
        if not checks:
            not_repro.append({"item": name, "reason": "no criteria_checks declared in contract"})
            continue
        results = []
        for c in checks:
            key, op, thr = c.get("name"), c.get("op"), c.get("threshold")
            if key not in measured:
                results.append({"check": key, "passed": None, "reason": "no measured value mapped"})
                continue
            passed = _OPS[op](measured[key], thr) if op in _OPS else None
            results.append({"check": key, "op": op, "threshold": thr,
                            "measured": measured[key], "passed": passed})
        passed_flags = [r["passed"] for r in results]
        entry = {"item": name, "checks": results}
        if all(p is True for p in passed_flags):
            fully.append(entry)
        elif any(p is False for p in passed_flags) and any(p is True for p in passed_flags):
            approx.append(entry)
        else:
            not_repro.append(entry)

    if fully and not approx and not not_repro:
        status = "reproduced"
    elif fully or approx:
        status = "approximately_reproduced"
    else:
        status = "not_reproduced"

    evaluation = {
        "status": status,
        "target_level": contract.get("reproduction_level"),
        "status_schema": {
            "fully_reproduced": fully,
            "approximately_reproduced": approx,
            "not_reproduced": not_repro,
        },
    }
    out_path = root / "results" / "reproduction_evaluation.json"
    out_path.write_text(json.dumps(evaluation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"WROTE {out_path} status={status}")


if __name__ == "__main__":
    main()
'''


def _dump_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _as_list(config: dict, key: str) -> list:
    value = config.get(key, [])
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def build_reproduction_contract(config: dict) -> dict:
    """Create the stable contract every reproduction project is evaluated against."""
    return {
        "paper_title": config.get("paper_title") or config.get("source_pdf") or "unknown",
        "algorithm_name": config.get("algorithm_name") or config.get("project_name"),
        "reproduction_level": config.get("reproduction_level", "Level 3"),
        "reproduction_targets": _as_list(config, "reproduction_targets"),
        "datasets": _as_list(config, "datasets"),
        "metrics": _as_list(config, "metrics"),
        "baselines": _as_list(config, "baselines"),
        "hyperparameters": _as_list(config, "hyperparameters"),
        "experiments": _as_list(config, "experiments"),
        "assumptions": _as_list(config, "assumptions"),
        "missing_but_required": _as_list(config, "missing_but_required"),
        "status_schema": {
            "fully_reproduced": [],
            "approximately_reproduced": [],
            "not_reproduced": [],
        },
    }


def render_gap_report(contract: dict) -> str:
    gaps = contract.get("missing_but_required", [])
    assumptions = contract.get("assumptions", [])
    lines = [
        "# Gap Report",
        "",
        f"Paper: {contract.get('paper_title', 'unknown')}",
        f"Algorithm/System: {contract.get('algorithm_name', 'unknown')}",
        f"Target level: {contract.get('reproduction_level', 'Level 3')}",
        "",
        "## Blocking Or Risky Gaps",
    ]
    if gaps:
        for gap in gaps:
            if isinstance(gap, dict):
                severity = gap.get("severity", "unknown")
                item = gap.get("item", gap.get("name", "unknown"))
                impact = gap.get("impact", "impact not specified")
                fallback = gap.get("fallback", "fallback not specified")
                lines.append(f"- [{severity}] {item}: {impact} (fallback: {fallback})")
            else:
                lines.append(f"- {gap}")
    else:
        lines.append("- None recorded yet.")

    lines.extend(["", "## Assumptions"])
    if assumptions:
        for assumption in assumptions:
            lines.append(f"- {assumption}")
    else:
        lines.append("- None recorded yet.")
    lines.append("")
    return "\n".join(lines)


def render_reproduction_report(contract: dict) -> str:
    targets = contract.get("reproduction_targets", [])
    experiments = contract.get("experiments", [])
    lines = [
        f"# {contract.get('algorithm_name', 'Paper Reproduction')}",
        "",
        f"Implementation of: {contract.get('paper_title', 'unknown')}",
        "",
        "## Reproduction Status",
        "",
        f"- Target level: {contract.get('reproduction_level', 'Level 3')}",
        "- Fully reproduced: Not evaluated yet.",
        "- Approximately reproduced: Not evaluated yet.",
        "- Not reproduced: Not evaluated yet.",
        "",
        "## Reproduction Targets",
    ]
    if targets:
        for target in targets:
            if isinstance(target, dict):
                lines.append(f"- {target.get('target', target.get('name', 'unnamed target'))}")
            else:
                lines.append(f"- {target}")
    else:
        lines.append("- Not recorded yet.")

    lines.extend(["", "## Experiments"])
    if experiments:
        for experiment in experiments:
            if isinstance(experiment, dict):
                name = experiment.get("name", "unnamed experiment")
                artifact = experiment.get("expected_artifact", "artifact not specified")
                lines.append(f"- {name}: {artifact}")
            else:
                lines.append(f"- {experiment}")
    else:
        lines.append("- Not recorded yet.")

    lines.extend([
        "",
        "## Retention Artifacts",
        "",
        "- Model checkpoint: Not recorded yet. If the experiment trains model state, retain at least one file under `results/checkpoints/` or `runs/<variant>/`.",
        "- Training log: Not recorded yet. If the experiment trains model state, write JSONL records with `step_or_epoch` and `loss` to `results/training_log.jsonl`.",
        "- If no model state is trained, replace these bullets with the required retention N/A statement from the skill.",
    ])

    lines.extend([
        "",
        "## Usage",
        "",
        "```bash",
        "pip install -r requirements.txt",
        "python scripts/run_smoke.py",
        "python scripts/run_experiment.py",
        "python scripts/evaluate_reproduction.py",
        "```",
        "",
        "## Notes",
        "",
        "Update this report after running the evaluator. Do not mark a target as reproduced until it is supported by an artifact and a contract criterion.",
        "",
    ])
    return "\n".join(lines)


def scaffold(config: dict, output_dir: Path = None) -> Path:
    if output_dir is None:
        output_dir = DEFAULT_OUTPUT_DIR
    output_dir = Path(output_dir)

    project_name = config["project_name"].replace(" ", "_").lower()
    language = config.get("language", "python").lower()
    modules = config.get("modules", [])
    dependencies = config.get("dependencies", [])
    datasets = config.get("datasets", [])
    metrics = config.get("metrics", [])
    experiments = config.get("experiments", [])
    reproduction_level = config.get("reproduction_level", "Level 3")
    contract = build_reproduction_contract(config)
    paper_structure = config.get("paper_structure") or {
        "status": "placeholder",
        "note": "Replace with extracted paper_structure.json before implementation.",
    }

    project_dir = output_dir / project_name
    project_dir.mkdir(parents=True, exist_ok=True)

    if language == "python":
        src_dir = project_dir / "src"
        src_dir.mkdir(exist_ok=True)
        (src_dir / "__init__.py").touch()

        for module in modules:
            name = module["name"].replace(" ", "_").lower()
            desc = module.get("description", name)
            (src_dir / f"{name}.py").write_text(
                f'"""{desc}"""\n', encoding="utf-8"
            )

        for package in ["data", "evaluation", "experiments"]:
            package_dir = src_dir / package
            package_dir.mkdir(exist_ok=True)
            (package_dir / "__init__.py").touch()

        configs_dir = project_dir / "configs"
        scripts_dir = project_dir / "scripts"
        results_dir = project_dir / "results"
        figures_dir = project_dir / "figures"
        for d in [configs_dir, scripts_dir, results_dir, figures_dir]:
            d.mkdir(exist_ok=True)

        _dump_json(
            configs_dir / "smoke.json",
            {
                "reproduction_level": reproduction_level,
                "dataset": "synthetic",
                "num_samples": 16,
                "seed": 0,
            },
        )
        _dump_json(
            configs_dir / "reproduction.json",
            {
                "reproduction_level": reproduction_level,
                "datasets": datasets,
                "metrics": metrics,
                "experiments": experiments,
                "seed": 0,
            },
        )
        _dump_json(project_dir / "paper_structure.json", paper_structure)
        _dump_json(project_dir / "reproduction_contract.json", contract)
        (project_dir / "gap_report.md").write_text(
            render_gap_report(contract),
            encoding="utf-8",
        )
        (project_dir / "REPRODUCTION_REPORT.md").write_text(
            render_reproduction_report(contract),
            encoding="utf-8",
        )

        (scripts_dir / "run_smoke.py").write_text(
            '''"""End-to-end smoke test for the reproduction project.\n\nWrites results/smoke_summary.json with a machine-readable pass/fail status so\ndownstream normalization can populate reward.smoke_pass. Set status to "failed"\n(and passed=False) if any smoke assertion does not hold.\n"""\nfrom pathlib import Path\nimport json\n\n\ndef main():\n    root = Path(__file__).resolve().parents[1]\n    config = json.loads((root / "configs" / "smoke.json").read_text(encoding="utf-8"))\n    # Replace with real smoke assertions (imports, tiny forward/backward, shapes).\n    passed = True\n    detail = f"synthetic samples={config.get('num_samples')} seed={config.get('seed')}"\n    results_dir = root / "results"\n    results_dir.mkdir(exist_ok=True)\n    (results_dir / "smoke_summary.json").write_text(\n        json.dumps({"status": "passed" if passed else "failed", "passed": passed, "detail": detail},\n                   ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")\n    print(f"SMOKE {'OK' if passed else 'FAIL'}: {detail}")\n\n\nif __name__ == "__main__":\n    main()\n''',
            encoding="utf-8",
        )
        (scripts_dir / "run_experiment.py").write_text(
            '''"""Run the paper reproduction experiment.\n\nReplace the placeholder body with the paper-specific experiment once modules are implemented. If this experiment trains model state, write JSONL records to TRAINING_LOG_PATH and save checkpoints under CHECKPOINT_DIR or runs/<variant>/.\n"""\nfrom pathlib import Path\nimport json\n\n\ndef main():\n    root = Path(__file__).resolve().parents[1]\n    config = json.loads((root / "configs" / "reproduction.json").read_text(encoding="utf-8"))\n    result_path = root / "results" / "reproduction_summary.json"\n    TRAINING_LOG_PATH = root / "results" / "training_log.jsonl"\n    CHECKPOINT_DIR = root / "results" / "checkpoints"\n    result_path.write_text(json.dumps({\n        "status": "placeholder",\n        "reproduction_level": config.get("reproduction_level"),\n        "note": "Implement the paper-specific experiment here.",\n        "retention_hint": f"If training occurs, write {TRAINING_LOG_PATH} and checkpoint files under {CHECKPOINT_DIR}.",\n    }, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")\n    print(f"WROTE {result_path}")\n\n\nif __name__ == "__main__":\n    main()\n''',
            encoding="utf-8",
        )
        (scripts_dir / "evaluate.py").write_text(
            '''"""Evaluate reproduction outputs against paper metrics."""\nfrom pathlib import Path\nimport json\n\n\ndef main():\n    root = Path(__file__).resolve().parents[1]\n    result_path = root / "results" / "reproduction_summary.json"\n    if not result_path.exists():\n        raise SystemExit("Missing results/reproduction_summary.json. Run scripts/run_experiment.py first.")\n    result = json.loads(result_path.read_text(encoding="utf-8"))\n    print(f"EVALUATION STATUS: {result.get('status')}")\n\n\nif __name__ == "__main__":\n    main()\n''',
            encoding="utf-8",
        )
        (scripts_dir / "evaluate_reproduction.py").write_text(
            EVALUATE_REPRODUCTION_TEMPLATE,
            encoding="utf-8",
        )

        tests_dir = project_dir / "tests"
        tests_dir.mkdir(exist_ok=True)
        (tests_dir / "__init__.py").touch()

        (project_dir / "requirements.txt").write_text(
            "\n".join(dependencies) + ("\n" if dependencies else ""),
            encoding="utf-8",
        )
        (project_dir / "main.py").write_text(
            '"""Compatibility entry point. Prefer scripts/run_smoke.py."""\nfrom scripts.run_smoke import main\n\n\nif __name__ == "__main__":\n    main()\n',
            encoding="utf-8",
        )

    sys.stderr.write(f"项目骨架已创建: {project_dir}\n")
    return project_dir


if __name__ == "__main__":
    config = json.loads(sys.stdin.read())
    out = scaffold(config)
    print(str(out))
