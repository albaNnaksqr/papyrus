# Gate 1 Change Notes

## Summary

- Updated `paper2repro-skill/SKILL.md` to require retained executable evidence for any experiment that trains a model: at least one checkpoint plus `results/training_log.jsonl`-style JSONL records with `step_or_epoch` and `loss`.
- Added the Phase 4 training-retention hard rule, including the pure-algorithm escape hatch: `no trained model — retention N/A`.
- Added the Phase 4 retention verification snippet that asserts checkpoint plus training log, or the report-level N/A statement.
- Added Phase 6, `Normalize the Run`, after trace export with:

```bash
python -m trajectory.normalize_runs output/<project_name> --jsonl output/<project_name>/normalized_record.jsonl --summary output/<project_name>/normalized_summary.json
```

- Kept the existing threshold provenance / `criteria_checks` hard rules intact and coherent.
- Minimally nudged `paper2repro-skill/scripts/scaffold.py` so generated reports and `run_experiment.py` placeholders point authors at `results/checkpoints/`, `runs/<variant>/`, and `results/training_log.jsonl` without fabricating artifacts or changing evaluator threshold behavior.

## Verification

### Compile

```bash
python -m py_compile paper2repro-skill/scripts/scaffold.py
```

Result: passed with no output.

### Scaffold Smoke Test

To avoid touching any `output/` directory, the smoke test piped a minimal config into a Python harness that imports the actual `paper2repro-skill/scripts/scaffold.py` and calls `scaffold(..., output_dir=/tmp/...)`.

Output:

```text
项目骨架已创建: /tmp/tmp.TcYGsvMG87/gate1_smoke_project
created_project=/tmp/tmp.TcYGsvMG87/gate1_smoke_project
contract_criteria_checks=present
evaluator_criteria_checks_reference=present
evaluator_hardcoded_threshold_literals=none
temp_project_deleted=yes
```

The emitted `reproduction_contract.json` carried `criteria_checks`. The emitted `scripts/evaluate_reproduction.py` referenced `criteria_checks`, did not contain the configured smoke threshold literal (`0.8` / `0.80`), and did not compare measured values against numeric literals.

### SKILL.md Grep

```text
retention rule:
69:  `results/training_log.jsonl`. The training log is JSONL: one JSON object per
408:**Hard rule (training artifact retention)**: if the experiment trains a model,
412:`loss`, preferably `results/training_log.jsonl`. Pure-algorithm papers that
413:train no model instead state `no trained model — retention N/A` in
414:`REPRODUCTION_REPORT.md`. A run that trains a model but is missing either
415:required artifact is downgraded as evidence not retained; do not mark it
427:n_a = "no trained model — retention N/A" in report_text
436:    print("retention check: no trained model — retention N/A")
439:    assert training_log.exists(), "missing results/training_log.jsonl"

verify snippet:
418:Before finishing, run this retention check from the project root:
436:    print("retention check: no trained model — retention N/A")
438:    assert checkpoint_files, "missing retained model checkpoint"
439:    assert training_log.exists(), "missing results/training_log.jsonl"
443:    print("retention check: checkpoint and training log retained")

normalize phase/command:
462:## Phase 6: Normalize the Run
468:python -m trajectory.normalize_runs output/<project_name> --jsonl output/<project_name>/normalized_record.jsonl --summary output/<project_name>/normalized_summary.json
473:grades the project `invalid_run`; treat that as the same failure covered by the

threshold provenance still present:
291:**Hard rule (threshold provenance)**: every numeric threshold, tolerance, or
301:  "criteria_checks": [
308:Rules for `criteria_checks`:
309:- Every threshold the evaluator reads comes from `criteria_checks`; the evaluator
390:**Hard rule (thresholds come from the contract)**: `evaluate_reproduction.py`
392:`criteria_checks` — no numeric threshold, tolerance, or cutoff may be written as
```

### Normalizer Interface

```bash
python -m trajectory.normalize_runs --help
```

Output:

```text
usage: normalize_runs.py [-h] --jsonl JSONL --summary SUMMARY
                         project_dirs [project_dirs ...]

Normalize one or more Papyrus skill runs

positional arguments:
  project_dirs       Skill reproduction project directories

options:
  -h, --help         show this help message and exit
  --jsonl JSONL      Output normalized JSONL path
  --summary SUMMARY  Output summary JSON path
```
