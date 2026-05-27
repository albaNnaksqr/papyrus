# Boyer-Moore string search

Implementation of: A Fast String Searching Algorithm

## Reproduction Status

- Target level: Level 3.
- Fully reproduced: exact substring-search behavior for the implemented Boyer-Moore API.
- Approximately reproduced: Section 6 references-per-character-passed trend using deterministic substitute sources.
- Not reproduced: original PDP-10 machine-instruction counts and exact original benchmark corpora.

## Reproduction Targets

1. Exact string search with right-to-left comparisons and bad-character plus good-suffix shifts.
2. Synthetic analogue of the paper's Section 6 empirical claim that string references per character passed can be below 1 and decrease as pattern length grows.

## Experiments

- `scripts/run_smoke.py`: fixed examples, the paper's `AT-THAT` example, empty-pattern behavior, no-match behavior, and 100 randomized correctness cases.
- `scripts/run_experiment.py`: 300 sampled patterns for each pattern length 1 through 14 on deterministic binary, English-like, and 100-character-alphabet sources.
- `scripts/evaluate_reproduction.py`: checks the contract and writes `results/reproduction_evaluation.json`.

## Results

- Correctness target: fully reproduced.
- Randomized first-occurrence failures: 0.
- Baseline comparison case: Boyer-Moore found matches `[660, 2280, 4350]`, matching Python reference search.
- Boyer-Moore comparisons: 1217.
- Naive comparisons: 6551.
- Comparison reduction versus naive: 81.42%.
- English-like length-5 average references per character passed: 0.2768.
- 100-character alphabet length-5 average references per character passed: 0.2163.
- Binary length-5 average references per character passed: 0.8678.
- Evaluator status: `approximately_reproduced`.

## Gaps

The original paper reports experiments on source strings that are not bundled with the PDF, including an online manual corpus and random samples whose seed is not given. This project therefore reproduces the trend, not the exact original curve values.

The paper's machine-instruction results depend on a PDP-10 assembly implementation. Python instruction counts are not comparable, so Figure 2 is documented as not reproduced.

## Usage

```bash
python3 -m pip install -r requirements.txt
python3 scripts/run_smoke.py
python3 scripts/run_experiment.py
python3 scripts/evaluate_reproduction.py
```

## Trace Export

Trace export succeeded and was saved as `agent_trace.jsonl`.
