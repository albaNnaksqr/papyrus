from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boyer_moore import boyer_moore_first, boyer_moore_search, naive_search, reference_find_all


def main():
    cases = [
        ("ANPANMAN PANAMA BANANA PAN", "PAN"),
        ("WHICH-FINALLY-HALTS.--AT-THAT-POINT", "AT-THAT"),
        ("AAAAAA", "AAA"),
        ("ABCDEF", "XYZ"),
        ("ABCDABD ABCDABD", "ABCDABD"),
        ("", "A"),
        ("ABC", ""),
    ]

    rng = random.Random(0)
    alphabet = "ABCD"
    for _ in range(100):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randrange(0, 80)))
        pattern = "".join(rng.choice(alphabet) for _ in range(rng.randrange(0, 8)))
        cases.append((text, pattern))

    for text, pattern in cases:
        bm = boyer_moore_search(text, pattern)
        naive = naive_search(text, pattern)
        reference = reference_find_all(text, pattern)
        assert bm.matches == reference, (text, pattern, bm.matches, reference)
        assert naive.matches == reference, (text, pattern, naive.matches, reference)
        first = boyer_moore_first(text, pattern)
        expected_first = reference[0] if reference else (0 if pattern == "" else None)
        assert first.match == expected_first, (text, pattern, first.match, expected_first)

    demo = boyer_moore_search("WHICH-FINALLY-HALTS.--AT-THAT-POINT", "AT-THAT")
    print(f"SMOKE OK: demo_matches={demo.matches} comparisons={demo.comparisons} cases={len(cases)}")


if __name__ == "__main__":
    main()
