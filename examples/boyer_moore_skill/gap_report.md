# Gap Report

Paper: A Fast String Searching Algorithm
Algorithm/System: Boyer-Moore string search
Target level: Level 3

## Blocking Or Risky Gaps

- [medium] Original benchmark corpora and random samples: exact Figure 1 numeric values cannot be reproduced (fallback: deterministic synthetic substitute sources).
- [medium] PDP-10 assembly implementation and instruction accounting: Figure 2 machine-instruction values cannot be reproduced in Python (fallback: skip instruction-count claim and evaluate string-reference trend).

## Assumptions

- Python APIs return zero-based offsets; the paper's pseudocode is one-based.
- Each text-pattern character comparison is counted as one string reference for the Section 6 analogue.
- The extracted paper text is used as the English-like source because the original online manual is not identified or bundled.
- The reproduction target is the algorithm and the Section 6 qualitative trend, not exact PDP-10 instruction counts.
