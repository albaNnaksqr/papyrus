from pathlib import Path
import json
import random
import string
import sys

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boyer_moore import boyer_moore_first, boyer_moore_search, naive_search, reference_find_all


def repeated_to_length(seed: str, length: int) -> str:
    if not seed:
        raise ValueError("seed text must not be empty")
    return (seed * ((length // len(seed)) + 1))[:length]


def make_sources(seed: int = 0, length: int = 10_000) -> dict[str, str]:
    rng = random.Random(seed)
    paper_text = (REPO / "example" / "boyer_moore_source" / "boyer_moore.txt").read_text(
        encoding="utf-8",
        errors="ignore",
    )
    english = "".join(ch.upper() if ch.isalpha() else " " for ch in paper_text)
    english = " ".join(english.split())

    # ASSUMPTION: the paper's online manual corpus is unavailable; its English
    # source is approximated with the extracted paper text. [see ambiguity_audit.md]
    return {
        "binary_random": "".join(rng.choice("01") for _ in range(length)),
        "english_text": repeated_to_length(english, length),
        "alphabet_100_random": "".join(rng.choice(string.printable[:100]) for _ in range(length)),
    }


def sample_patterns(source: str, pattern_length: int, samples: int, rng: random.Random) -> list[tuple[str, int]]:
    out = []
    lo = 0
    hi = len(source) - pattern_length
    for _ in range(samples):
        start = rng.randrange(lo, hi + 1)
        out.append((source[start : start + pattern_length], start))
    return out


def first_occurrence_experiment(source: str, pattern_length: int, samples: int, seed: int) -> dict:
    rng = random.Random(seed)
    refs_per_passed = []
    alignments = []
    correctness_failures = 0

    for pattern, pattern_start in sample_patterns(source, pattern_length, samples, rng):
        # ASSUMPTION: the paper says searches start at a random position in the
        # first half, but does not publish those positions. We use deterministic
        # pseudo-random starts in the first half. [see ambiguity_audit.md]
        max_start = max(0, min(pattern_start, len(source) // 2))
        search_start = rng.randrange(0, max_start + 1) if max_start else 0
        text = source[search_start:]
        result = boyer_moore_first(text, pattern)
        expected = text.find(pattern)
        if result.match != expected:
            correctness_failures += 1
        refs_per_passed.append(result.comparisons / max(1, result.characters_passed))
        alignments.append(result.alignments)

    return {
        "samples": samples,
        "avg_references_per_character_passed": sum(refs_per_passed) / len(refs_per_passed),
        "avg_alignments": sum(alignments) / len(alignments),
        "correctness_failures": correctness_failures,
    }


def correctness_and_baseline_case() -> dict:
    rng = random.Random(123)
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    chunks = ["".join(rng.choice(alphabet) for _ in range(90)) for _ in range(70)]
    pattern = "NEEDLE"
    for idx in [7, 25, 48]:
        chunks[idx] = chunks[idx][:30] + pattern + chunks[idx][36:]
    text = "".join(chunks)
    bm = boyer_moore_search(text, pattern)
    naive = naive_search(text, pattern)
    reference = reference_find_all(text, pattern)
    return {
        "text_length": len(text),
        "pattern": pattern,
        "matches": bm.matches,
        "reference_matches": reference,
        "boyer_moore_comparisons": bm.comparisons,
        "naive_comparisons": naive.comparisons,
        "comparison_reduction": 1.0 - (bm.comparisons / naive.comparisons),
        "checks": {
            "matches_reference": bm.matches == reference,
            "matches_naive": bm.matches == naive.matches,
            "fewer_comparisons_than_naive": bm.comparisons < naive.comparisons,
        },
    }


def monotonic_nonincreasing(values: list[float], tolerance: float = 0.12) -> bool:
    return all(values[i + 1] <= values[i] + tolerance for i in range(len(values) - 1))


def main():
    config = json.loads((ROOT / "configs" / "reproduction.json").read_text(encoding="utf-8"))
    samples = int(config.get("samples_per_pattern_length", 300))
    seed = int(config.get("seed", 0))
    pattern_lengths = list(config.get("pattern_lengths", range(1, 15)))

    sources = make_sources(seed=seed)
    curves = {}
    for source_name, source in sources.items():
        rows = []
        for pattern_length in pattern_lengths:
            rows.append({
                "pattern_length": pattern_length,
                **first_occurrence_experiment(
                    source,
                    pattern_length=pattern_length,
                    samples=samples,
                    seed=seed * 10_000 + pattern_length,
                ),
            })
        curves[source_name] = rows

    correctness = correctness_and_baseline_case()
    english_values = [row["avg_references_per_character_passed"] for row in curves["english_text"]]
    alphabet100_values = [row["avg_references_per_character_passed"] for row in curves["alphabet_100_random"]]

    result = {
        "status": "completed",
        "experiment": "synthetic analogue of paper Section 6 references-per-character-passed curves",
        "pattern_lengths": pattern_lengths,
        "samples_per_pattern_length": samples,
        "source_length": 10_000,
        "curves": curves,
        "correctness_and_baseline": correctness,
        "checks": {
            **correctness["checks"],
            "no_first_occurrence_failures": all(
                row["correctness_failures"] == 0
                for rows in curves.values()
                for row in rows
            ),
            "english_length_5_below_kmp_reference_rate": curves["english_text"][4]["avg_references_per_character_passed"] < 1.0,
            "alphabet_100_length_5_below_kmp_reference_rate": curves["alphabet_100_random"][4]["avg_references_per_character_passed"] < 1.0,
            "english_curve_generally_decreases": monotonic_nonincreasing(english_values),
            "alphabet_100_curve_generally_decreases": monotonic_nonincreasing(alphabet100_values),
        },
    }

    result_path = ROOT / "results" / "reproduction_summary.json"
    result_path.parent.mkdir(exist_ok=True)
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"WROTE {result_path}")


if __name__ == "__main__":
    main()
