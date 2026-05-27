from pathlib import Path
import json


def main():
    root = Path(__file__).resolve().parents[1]
    contract = json.loads((root / "reproduction_contract.json").read_text(encoding="utf-8"))
    result_path = root / "results" / "reproduction_summary.json"
    if not result_path.exists():
        raise SystemExit("Missing results/reproduction_summary.json. Run scripts/run_experiment.py first.")

    result = json.loads(result_path.read_text(encoding="utf-8"))
    checks = result.get("checks", {})
    passed = result.get("status") == "completed" and all(checks.values())

    correctness = result.get("correctness_and_baseline", {})
    curves = result.get("curves", {})
    english_len5 = curves.get("english_text", [{}] * 5)[4].get("avg_references_per_character_passed")
    alphabet100_len5 = curves.get("alphabet_100_random", [{}] * 5)[4].get("avg_references_per_character_passed")

    evaluation = {
        "status": "approximately_reproduced" if passed else "not_reproduced",
        "target_level": contract.get("reproduction_level"),
        "fully_reproduced": [
            {
                "item": "Exact substring search input/output behavior",
                "evidence": {
                    "matches": correctness.get("matches"),
                    "reference_matches": correctness.get("reference_matches"),
                    "randomized_first_occurrence_failures": 0
                    if checks.get("no_first_occurrence_failures")
                    else "nonzero",
                },
            }
        ] if checks.get("matches_reference") and checks.get("no_first_occurrence_failures") else [],
        "approximately_reproduced": [
            {
                "item": "Paper Section 6 sublinear reference trend",
                "evidence": {
                    "english_length_5_references_per_character_passed": english_len5,
                    "alphabet_100_length_5_references_per_character_passed": alphabet100_len5,
                    "comparison_reduction_vs_naive": correctness.get("comparison_reduction"),
                    "checks": checks,
                },
            }
        ] if passed else [],
        "not_reproduced": [] if passed else [
            {
                "item": "Synthetic Section 6 trend contract",
                "reason": "One or more evaluator checks failed.",
                "failed_checks": [name for name, ok in checks.items() if not ok],
            }
        ],
        "limitations": [
            "Original PDP-10 machine-instruction counts are not reproduced.",
            "Original online manual corpus and random samples are unavailable; deterministic substitute sources are used.",
        ],
    }

    out_path = root / "results" / "reproduction_evaluation.json"
    out_path.write_text(json.dumps(evaluation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"WROTE {out_path}")


if __name__ == "__main__":
    main()
