# Trajectory Calibration Report

This report compares rule-derived Papyrus trajectory labels against manually reviewed calibration labels. It measures whether the structured labels are credible enough to use as data signals.

## Coverage

- Records: 9 labeled / 9 total.
- Repair attempts: 20 labeled / 20 extracted.
- Reflection events: 15 labeled / 15 extracted.
- Usefulness tags: 9 runs with gold tags.

## Metrics

| signal | extracted | labeled | strict_precision | lenient_precision |
|---|---:|---:|---:|---:|
| repair_attempts | 20 | 20 | 0.25 | 0.9 |
| reflection_events | 15 | 15 | 0.6667 | 0.9333 |
| usefulness_tags | 9 runs | 9 runs | 1.0 | 0.9706 |

## Interpretation

- Strict precision counts only direct root-cause repair/reflection evidence.
- Lenient precision also credits partial repairs and plan-adjustment reflections.
- Usefulness precision/recall evaluates run-level sample tags against gold tags.

## Error Cases

### repair_attempts

| paper_id | index | label | note |
|---|---:|---|---|
| swe_agent_repro | 1 | false_positive | The compound command later passes, but the paired edit is report/result cleanup rather than a code repair of the failure. |
| reflexion_repro | 3 | false_positive | JSON report inspection is a read/display operation, not a repair attempt. |

### reflection_events

| paper_id | index | label | note |
|---|---:|---|---|
| repobench_repro | 1 | procedural | Mainly says tests are running and that scoring may be adjusted if needed. |

### usefulness_tags

| paper_id | false_positive_tags | missing_tags |
|---|---|---|
| repobench_claude | none | gap_sample |
