# Ambiguity Audit: A Fast String Searching Algorithm

Paper type: algorithm
Official code: NONE

## Core items

| Item | Status | Quote / Source | Our Choice | Alternatives |
|------|--------|----------------|------------|--------------|
| Core algorithm inputs | SPECIFIED | Section 1: `pat is a string of length patlen` and search in `some string string` | Python `str` text and pattern | Byte arrays or arbitrary sequences |
| Core algorithm outputs | SPECIFIED | Section 4: returns `false` or `the position of the left end` | Zero-based Python offsets; first-match API plus all-match wrapper | One-based paper offsets only |
| Key invariant | SPECIFIED | Section 4: compare `string(i)` with `pat(j)` from the right end | Right-to-left comparison at each alignment | Left-to-right verification |
| Bad-character shift | SPECIFIED | Section 4 defines `delta1(char)` from rightmost occurrence | Rightmost occurrence table | Horspool tail-character-only table |
| Good-suffix shift | SPECIFIED | Section 4 defines `delta2(j) = patlen + 1 - rpr(j)` | Standard strong good-suffix table implementing the same rule | Direct one-based rpr table |
| Termination condition | SPECIFIED | Section 4: `if i > stringlen then return false`; `if j = 0 then return i + 1` | Stop when no alignment remains; return match when all chars match | Sentinel fast-loop variant |
| Complexity claim | SPECIFIED | Abstract: worst case is `linear in i + patlen` with table space | Documented; not formally proven by code | Add proof artifact |
| Evaluation criteria | SPECIFIED | Section 6: references to string per character passed; machine instructions per character passed | Reproduce references-per-character trend; skip PDP-10 instruction counts | Exact Figure 1/2 values |
| Random seeds / reproducibility | UNSPECIFIED | Section 6 says random samples but gives no seed | Fixed seed 0 | Multiple seeds or user-provided seed |
| Hardware / environment | SPECIFIED | Section 5: PDP-10 assembly implementation | Python implementation; no instruction-count claim | PDP-10 emulator or assembly port |

## Domain-specific items

| Item | Status | Quote / Source | Our Choice | Alternatives |
|------|--------|----------------|------------|--------------|
| Alphabet size | SPECIFIED | Section 6 uses binary, English, and `100-character alphabet` sources | Deterministic binary, English-like paper text, printable 100-character random source | Original corpora |
| Pattern lengths | SPECIFIED | Section 6: `for each patlen from 1 to 14` | Pattern lengths 1..14 | Smaller smoke subset |
| Samples per length | SPECIFIED | Section 6: `300 patterns` for each length | 300 samples per length | Fewer samples for speed |
| Pattern sampling | PARTIALLY_SPECIFIED | Section 6: randomly selects a substring of a given length from a source string | Deterministic pseudo-random substrings | Exhaustive substrings |
| Search start | PARTIALLY_SPECIFIED | Section 6: starts each search in a random position in the first half | Deterministic pseudo-random first-half starts | Always start at zero |
| Original English source | UNSPECIFIED | Section 6 says an online manual but does not identify or bundle it | Extracted paper text normalized as English substitute | User-provided manual corpus |
| Instruction-count metric | PARTIALLY_SPECIFIED | Section 6 measures PDP-10 instructions and Section 5 discusses fast-loop instructions | Not reproduced; Python instruction counts are not comparable | PDP-10 assembly reimplementation |

## Contradictions found

- None found that affect implementation. The abstract and Section 6 report broad empirical claims; Section 4 is used for algorithm behavior.

## UNSPECIFIED items that will become ASSUMPTION comments in code

- Random seed: use `seed=0` (alternatives: multiple seeds, user-provided seed).
- English corpus: use normalized extracted paper text (alternatives: original online manual, another public corpus).
- Python indexing: return zero-based offsets while documenting paper one-based pseudocode (alternatives: one-based offsets).
