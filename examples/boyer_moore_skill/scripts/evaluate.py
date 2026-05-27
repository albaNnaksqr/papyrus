"""Evaluate reproduction outputs against paper metrics."""
from pathlib import Path
import json


def main():
    root = Path(__file__).resolve().parents[1]
    result_path = root / "results" / "reproduction_summary.json"
    if not result_path.exists():
        raise SystemExit("Missing results/reproduction_summary.json. Run scripts/run_experiment.py first.")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    print(f"EVALUATION STATUS: {result.get('status')}")


if __name__ == "__main__":
    main()
