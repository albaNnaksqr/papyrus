---
name: paper2repro
description: Use when reproducing an academic paper into runnable code, experiment scripts, evaluation artifacts, and an explicit reproduction report.
args:
  - name: pdf_path
    description: Absolute path to the paper PDF
    required: true
  - name: auto
    description: Skip soft pause gates
    required: false
---

# paper2repro

Act as a paper reproduction engineer, not a demo generator. Build the smallest runnable project that can reproduce the paper's main claim as faithfully as available evidence allows. Do not treat "code runs" as reproduction success.

## Trace Boundary Markers

At the very beginning of every run, before Phase 1, create a run id and emit a stable start marker as its own command output:

```bash
RUN_ID="paper2repro-$(date +%Y%m%d%H%M%S)"
printf "%s" "$RUN_ID" > /tmp/paper2repro_run_id.txt
echo "PAPER_REPRO_TRACE_START run_id=$RUN_ID pdf_path=<pdf_path>"
```

At the very end, after `REPRODUCTION_REPORT.md` is updated and verification has completed, emit a stable end marker as its own command output:

```bash
RUN_ID="$(cat /tmp/paper2repro_run_id.txt)"
echo "PAPER_REPRO_TRACE_END run_id=$RUN_ID status=complete project_name=<project_name>"
```

These markers define the agent trajectory segment for this skill run. Do not put unrelated work between the start and end markers.

## Reproduction Levels

- **Level 1 Toy demo**: core idea runs only on synthetic or invented data.
- **Level 2 Algorithm reproduction**: formulas, state updates, inputs, outputs, and assumptions are implemented.
- **Level 3 Experiment reproduction**: the main figure, metric, trend, table, or ablation can be regenerated or meaningfully compared.
- **Level 4 Project reproduction**: data processing flow, configs, training/evaluation scripts, and artifacts resemble a released research codebase.

Default to Level 3. Downgrade only when a specific missing item blocks that level.

## Required Artifacts

Every project should contain:

- `paper_structure.json`: LLM-extracted evidence from the paper.
- `reproduction_contract.json`: the reproduction target, success criteria, data, metrics, experiments, assumptions, and gaps.
- `gap_report.md`: user-readable blockers and downgrade reasons.
- `configs/smoke.json` and `configs/reproduction.json`.
- `scripts/run_smoke.py`: fast import/data/algorithm check. It MUST write
  `results/smoke_summary.json` with a machine-readable `status`
  (`passed`/`failed`) so normalization can populate `reward.smoke_pass`.
- `scripts/run_experiment.py`: reproduces the paper-oriented experiment.
- `scripts/evaluate_reproduction.py`: evaluates result artifacts against contract success criteria.
- `results/reproduction_summary.json`: raw metric outputs written by `run_experiment.py`.
- `results/reproduction_evaluation.json`: the evaluator's verdict. **Exactly this
  path** — not `evaluation_result.json`, `evaluation_summary.json`, or any other
  name. It MUST contain a top-level `"status"` field whose value is one of
  `fully_reproduced` / `approximately_reproduced` / `not_reproduced`, or a
  `status_schema` object with `fully_reproduced` / `approximately_reproduced` /
  `not_reproduced` target lists. Downstream trajectory normalization reads this
  file at this exact path; a run that writes its verdict anywhere else is graded
  `invalid_run` no matter how well it went.
- For any experiment that trains a model, retained executable evidence:
  at least one saved model checkpoint under a stable run/checkpoint path such
  as `runs/<variant>/` or `results/checkpoints/`, and a machine-readable
  per-step-or-per-epoch training log — canonically `results/training_log.jsonl`,
  or an equivalent `runs/<variant>/training_log.json[l]` next to its checkpoint.
  The training log is JSONL: one JSON object per record, with at least
  `step_or_epoch` and `loss`.
- `REPRODUCTION_REPORT.md`: final claim-by-claim status.

## Phase 1: Audit the Paper

Read the PDF using whichever method is available in this execution context:

**Option A — preferred (no external tool needed):** Use the `Read` tool directly on the PDF file. It supports PDFs natively. For papers longer than 20 pages, read in chunks:

```
Read(file_path="<pdf_path>", pages="1-20")
# If the paper has more pages, continue:
Read(file_path="<pdf_path>", pages="21-40")
# etc.
```

**Option B — fallback (if `Read` cannot open PDFs here):** Run the extraction script, then read its output:

```bash
python ~/.claude/skills/paper2repro/scripts/parse_pdf.py "<pdf_path>" > /tmp/paper_text.txt
```

Then read `/tmp/paper_text.txt`. Note that this script truncates at 28000 characters — if the paper is long, tables near the end may be cut off. In that case, try Option A or note the truncation in the ambiguity audit.

Either way, after reading the paper, extract the structure yourself and write it to `/tmp/paper_structure.json`. The JSON must contain at minimum:

```json
{
  "algorithm_name": "...",
  "problem_statement": "...",
  "reproduction_level": "Level 1 / Level 2 / Level 3 / Level 4",
  "reproduction_targets": [
    {
      "target": "主结果/主实验/主图/主表",
      "success_criteria": "判断成功的现象或指标",
      "evidence": {"source": "explicit/inferred", "location": "章节/页码/公式", "quote": "原文短摘录"}
    }
  ],
  "language_hints": ["论文提到的编程语言/框架/库"],
  "inputs": [{"name": "", "type": "", "format": "", "description": "", "evidence": {"source": "", "location": "", "quote": ""}}],
  "outputs": [{"name": "", "type": "", "format": "", "description": "", "evidence": {"source": "", "location": "", "quote": ""}}],
  "steps": [{"step": 1, "name": "", "description": "", "formula": null, "evidence": {"source": "", "location": "", "quote": ""}}],
  "datasets": [{"name": "", "availability": "available/unavailable/unclear/synthetic_needed", "format": "", "access": "", "substitute_strategy": "", "evidence": {"source": "", "location": "", "quote": ""}}],
  "metrics": [{"name": "", "formula": null, "direction": "higher_is_better/lower_is_better/target_match/unknown", "reported_value": null, "evidence": {"source": "", "location": "", "quote": ""}}],
  "baselines": [{"name": "", "role": "baseline/ablation/prior_work", "reported_result": null, "evidence": {"source": "", "location": "", "quote": ""}}],
  "hyperparameters": [{"name": "", "value": null, "source": "explicit/inferred/missing", "impact": ""}],
  "experiments": [{"name": "", "purpose": "", "entry_script_hint": "scripts/run_experiment.py", "expected_artifact": "", "requires_real_data": true, "can_use_synthetic_data": true, "evidence": {"source": "", "location": "", "quote": ""}}],
  "implementation_artifacts": [{"type": "formula/pseudocode/architecture/table/figure/paragraph", "name": "", "implementation_use": "", "evidence": {"source": "", "location": "", "quote": ""}}],
  "dependencies": ["需要安装的库/包"],
  "example_data": {"description": null, "input_sample": null, "expected_output": null},
  "ambiguities": [{"item": "", "impact": "", "severity": "high/medium/low"}],
  "missing_but_required": [{"item": "", "impact": "", "severity": "high/medium/low", "fallback": "synthetic/approximate/skip/ask_user"}],
  "project_type": "single_script | standard_project | notebook"
}
```

Use `"source": "explicit"` when grounded in direct paper text; `"source": "inferred"` when reasoning beyond what the paper states. Then decide:

- paper title or filename
- algorithm/system name
- main claim to reproduce
- **paper type**: one of `algorithm` / `ml_experiment` / `systems` / `theoretical` — this determines what counts as a "reproduction success" and which fields matter most
- target reproduction level
- data availability and substitute strategy
- metrics and success criteria
- experiments and expected artifacts
- high-severity missing information

Paper type guidance:
- **algorithm**: focus on input/output contract, correctness on synthetic cases, complexity claims
- **ml_experiment**: focus on dataset, metrics, baselines, hyperparameters, main result table/figure
- **systems**: focus on interface, protocol, throughput/latency claims, workload
- **theoretical**: focus on the key theorem's constructive proof or simulation; numeric claims in experiments

Then search for official code. Use WebSearch with the paper title + "github" + "code" and the algorithm name. Save any found repository URLs to `/tmp/official_code_urls.txt`. If nothing is found, write `NONE` to that file.

If an official repository is found, fetch its key files (README, config files, core model/algorithm file) and save a brief summary to `/tmp/official_code_notes.txt`. This will be used in the Ambiguity Audit to resolve UNSPECIFIED items.

Soft gate unless `--auto` was requested:

```text
[阶段1完成] 我理解的复现目标是：<main target>。
目标等级：<Level>
关键数据/指标/实验：<summary>
主要缺口：<high/medium gaps>
回复"继续"开始搭项目，或指出目标/数据/指标理解错误。
```

Hard gate even in auto mode if a high-severity gap blocks the whole reproduction:

```text
[需要确认] 缺少 <item>，会阻塞 <result/module>。
可选处理：补充资料 / 降级到 synthetic / approximate / skip。
```

## Phase 1.5: Ambiguity Audit

Before scaffolding anything, go through every implementation-relevant detail and classify it. Save the result to `/tmp/ambiguity_audit.md`.

**Mindset: assume nothing. Verify everything against the paper text.**

For each item below, search the paper text (method section, experiments, appendix, footnotes, figure captions, table captions) and classify:

- **SPECIFIED** — paper states this explicitly; record the exact quote and section
- **PARTIALLY_SPECIFIED** — paper mentions it but is ambiguous; record the quote and what is unclear
- **UNSPECIFIED** — paper does not state this; record common choices and which one you will use as default

If `/tmp/official_code_notes.txt` exists and is not `NONE`, use it to resolve UNSPECIFIED items. When resolved this way, mark the item `SPECIFIED [FROM_OFFICIAL_CODE]` with the source file/line.

### Checklist by paper type

**All paper types — always audit:**

| Item | What to look for |
|------|-----------------|
| Core algorithm inputs | Types, shapes, ranges, edge cases |
| Core algorithm outputs | Types, shapes, what they represent |
| Key invariants or assumptions | Preconditions the algorithm relies on |
| Evaluation criteria | What metric or outcome counts as correct |
| Random seeds / reproducibility | Whether the paper fixes seeds |
| Hardware / environment constraints | GPU, memory, OS requirements that affect results |

**ml_experiment — additionally audit:**

| Item | Common hiding spots |
|------|---------------------|
| Layer count, hidden dims, heads | Table 1, appendix architecture details |
| Activation function | Often unstated — do NOT assume ReLU |
| Normalization type and placement | Pre-norm vs post-norm often contradicted between figure and text |
| Optimizer and betas | Appendix; papers often say "Adam" without specifying β₁, β₂ |
| Learning rate and schedule | Appendix; warmup steps often omitted even when warmup is mentioned |
| Batch size (total vs per-GPU) | Crucial distinction, often ambiguous |
| Dropout rate and placement | After attention? After FFN? On embeddings? |
| Dataset name, version, split | Experiments section |
| Data preprocessing and augmentation | Appendix |
| Reported metric values | Record these — they are the success criteria |

**algorithm — additionally audit:**

| Item | Common hiding spots |
|------|---------------------|
| Termination condition | Often only in pseudocode or proof |
| Complexity claim (time/space) | Theorem statement or analysis section |
| Tie-breaking rules | Footnotes or appendix |
| Numerical precision requirements | Experiments or implementation notes |

**systems — additionally audit:**

| Item | Common hiding spots |
|------|---------------------|
| Interface / API contract | Design section |
| Workload / benchmark used | Evaluation section |
| Throughput / latency target | Results table |
| Concurrency / consistency model | System design section |

### How to handle contradictions

- Figure vs text: implement what the text/equations say; flag the figure discrepancy
- Abstract vs method: method section wins
- Equation vs prose: equation wins; flag the discrepancy
- Paper vs official code: note both; state which you implement and why

### Output format for `/tmp/ambiguity_audit.md`

```markdown
# Ambiguity Audit: {paper_title}

Paper type: {type}
Official code: {URL or NONE}

## Core items

| Item | Status | Quote / Source | Our Choice | Alternatives |
|------|--------|----------------|------------|--------------|

## Domain-specific items

| Item | Status | Quote / Source | Our Choice | Alternatives |

## Contradictions found
- {description}

## UNSPECIFIED items that will become ASSUMPTION comments in code
- {item}: {chosen default} (alternatives: {list})
```

Hard gate even in auto mode if three or more high-severity items are UNSPECIFIED and no official code was found:

```text
[需要确认] 以下关键实现细节论文未说明，且未找到官方代码：
<list of high-severity UNSPECIFIED items>
可选处理：补充资料 / 降级到 synthetic / approximate / skip。
```

## Phase 2: Create the Reproduction Project

Prepare a scaffold config that includes at least:

```json
{
  "project_name": "snake_case_name",
  "paper_title": "paper title or PDF filename",
  "algorithm_name": "algorithm/system name",
  "paper_type": "algorithm | ml_experiment | systems | theoretical",
  "language": "python",
  "reproduction_level": "Level 3",
  "reproduction_targets": [],
  "datasets": [],
  "metrics": [],
  "experiments": [],
  "baselines": [],
  "hyperparameters": [],
  "assumptions": [],
  "missing_but_required": [],
  "modules": [],
  "dependencies": [],
  "official_code_url": "URL or null",
  "unspecified_count": 0
}
```

**Hard rule (threshold provenance)**: every numeric threshold, tolerance, or
cutoff that `evaluate_reproduction.py` will later test MUST be declared here in
the contract before implementation — never invented inside evaluator code. In
each `reproduction_targets[]` entry, give `success_criteria` a machine-readable
form alongside the prose, e.g.:

```json
{
  "target": "main figure / metric / trend being reproduced",
  "success_criteria": "prose description of what counts as success",
  "criteria_checks": [
    {"name": "held_out_accuracy", "op": ">=", "threshold": 0.80, "source": "explicit", "evidence": "Table 2, p.6"},
    {"name": "loss_tolerance", "op": "<=", "threshold": 0.25, "source": "inferred", "rationale": "no paper value; local proxy tolerance"}
  ]
}
```

Rules for `criteria_checks`:
- Every threshold the evaluator reads comes from `criteria_checks`; the evaluator
  loads them from the contract at runtime and does not hardcode numbers.
- `source` is `explicit` (paper states it), `inferred` (you chose it), or
  `substitute` (proxy task). Any non-`explicit` threshold must carry a
  `rationale` and be surfaced in `gap_report.md`, so a lenient tolerance can
  never hide inside evaluator code (the tinystories lesson).
- Thresholds are fixed after this phase. If a result misses a threshold, mark
  it `not_reproduced` — do not loosen the number.

Copy `/tmp/ambiguity_audit.md` into the project as `ambiguity_audit.md`.

Then scaffold:

```bash
python ~/.claude/skills/paper2repro/scripts/scaffold.py < /tmp/scaffold_config.json
```

The scaffold must create contract/report placeholders before implementation. Copy `/tmp/paper_structure.json` into the project as `paper_structure.json`.

Soft gate unless `--auto` was requested:

```text
[阶段2完成] 已创建项目、复现契约和 gap report。
项目位置：output/<project_name>/
回复"继续"开始实现，或指出要调整的复现等级/实验/数据策略。
```

## Phase 3: Implement

Implementation order:

1. Data loader or synthetic generator.
2. Core paper algorithm modules.
3. Metrics.
4. Experiment script.
5. Reproduction evaluator.
6. Final report.

For every item that was `UNSPECIFIED` or `PARTIALLY_SPECIFIED` in the Ambiguity Audit, add a comment in the corresponding code:

```python
# ASSUMPTION: <paper did not specify X; this implementation uses Y> [see ambiguity_audit.md]
```

For items resolved from official code:

```python
# FROM_OFFICIAL_CODE: <detail sourced from repo/file#line>
```

Do not stop at ordinary coding errors; fix them inline. Pause only when a missing formula, dataset, input format, model weight, hardware requirement, or external service makes the stated reproduction level impossible.

## Phase 4: Debug & Verify

Run the full verification sequence and fix every failure before proceeding to the next step:

```bash
cd output/<project_name>
pip install -r requirements.txt
python scripts/run_smoke.py
```

If smoke fails: diagnose the root cause, fix the code, re-run. Do not proceed until smoke passes. Do not lower the success bar — fix the implementation.

```bash
python scripts/run_experiment.py
```

If experiment fails or produces clearly wrong outputs: check whether the failure is a code bug (fix it) or a data/resource gap (document it in gap_report.md and decide whether to downgrade the reproduction level). Do not silently ignore wrong results.

```bash
python scripts/evaluate_reproduction.py
```

Compare outputs against the `reproduction_contract.json` success criteria. For each target:
- If the result matches the criterion: mark `fully_reproduced`
- If the result is directionally correct but off in magnitude: mark `approximately_reproduced` and record the gap
- If the result cannot be produced: mark `not_reproduced` with a specific reason

**Hard rule**: do not mark a target as reproduced by editing the success criteria. The contract is fixed after Phase 2. Only the code and results can change.

**Hard rule (thresholds come from the contract)**: `evaluate_reproduction.py`
MUST load every threshold it tests from `reproduction_contract.json`'s
`criteria_checks` — no numeric threshold, tolerance, or cutoff may be written as
a literal in evaluator code. If the evaluator needs a number that is not in the
contract, that is a Phase 2 omission: add it to the contract (with `source` and,
if not `explicit`, a `rationale` + `gap_report.md` note), then re-run. This
keeps the pass/fail bar auditable and prevents a lenient tolerance from hiding
in code.

**Hard rule (output path)**: `evaluate_reproduction.py` MUST write its verdict to
`results/reproduction_evaluation.json` with the `status` / `status_schema` shape
described in Required Artifacts. Before finishing, verify it parses at that exact
path:

```bash
python -c "import json; d=json.load(open('results/reproduction_evaluation.json')); assert 'status' in d or 'status_schema' in d, 'missing status'"
```

**Hard rule (training artifact retention)**: if the experiment trains a model,
the run directory MUST retain both (1) at least one saved model checkpoint, e.g.
under `runs/<variant>/` or `results/checkpoints/`, and (2) a machine-readable
per-step-or-per-epoch JSONL training log with at least `step_or_epoch` and
`loss`, preferably `results/training_log.jsonl`. Pure-algorithm papers that
train no model instead state `no trained model — retention N/A` in
`REPRODUCTION_REPORT.md`. A run that trains a model but is missing either
required artifact is downgraded as evidence not retained; do not mark it
reproduced.

Before finishing, run this retention check from the project root:

```bash
python - <<'PY'
from pathlib import Path

root = Path(".")
report = root / "REPRODUCTION_REPORT.md"
report_text = report.read_text(encoding="utf-8") if report.exists() else ""
n_a = "no trained model — retention N/A" in report_text
checkpoint_files = [
    p for base in (root / "results" / "checkpoints", root / "runs")
    if base.exists()
    for p in base.rglob("*")
    if p.is_file()
]
# Canonical location is results/training_log.jsonl, but accept an equivalent
# per-step log under the run dir (e.g. runs/<variant>/training_log.json[l]) so a
# genuinely-retained run is not failed on filename alone.
canonical_log = root / "results" / "training_log.jsonl"
training_logs = [canonical_log] if canonical_log.exists() else []
for base in (root / "runs",):
    if base.exists():
        training_logs += [p for p in base.rglob("training_log*.json*") if p.is_file()]
if n_a:
    print("retention check: no trained model — retention N/A")
else:
    assert checkpoint_files, "missing retained model checkpoint"
    assert training_logs, "missing per-step training log (results/training_log.jsonl or runs/<variant>/training_log.json[l])"
    with training_logs[0].open(encoding="utf-8") as fh:
        first = fh.readline().strip()
    assert first, "training log is empty"
    print(f"retention check: checkpoint and training log retained ({training_logs[0]})")
PY
```

After verification, update `REPRODUCTION_REPORT.md` with actual results. Replace all placeholder statuses.

## Phase 5: Export Agent Trace

After emitting `PAPER_REPRO_TRACE_END` as a separate command, export the trace for this skill run into the reproduction project:

```bash
python ~/.claude/skills/paper2repro/scripts/export_trace.py \
  --latest \
  --source auto \
  --output output/<project_name>/agent_trace.jsonl
```

If trace export fails because the current agent runtime does not expose compatible session logs, do not fail the reproduction. Add a short note to `REPRODUCTION_REPORT.md` with the command attempted and the failure reason.

## Phase 6: Normalize the Run

From the repository root, self-produce the normalized dataset record for this
single reproduction project:

```bash
python -m trajectory.normalize_runs output/<project_name> --jsonl output/<project_name>/normalized_record.jsonl --summary output/<project_name>/normalized_summary.json
```

This command depends on the exact evaluator artifact path. If
`results/reproduction_evaluation.json` is missing or misnamed, normalization
grades the project `invalid_run`; treat that as the same failure covered by the
Phase 4 output-path hard rule and fix the evaluator path before finishing.

## Final Report Rules

`REPRODUCTION_REPORT.md` and the final user response must separate:

- **Fully reproduced**: implemented and verified against the contract.
- **Approximately reproduced**: implemented with substitutions or inferred details; gap is documented.
- **Not reproduced**: missing data, formulas, parameters, hardware, or insufficient paper detail.

The final response must also report:
- How many Ambiguity Audit items were UNSPECIFIED, and how many were resolved via official code
- Whether the reproduction level was downgraded from the initial target, and why
- Whether `agent_trace.jsonl` was exported successfully

Do not claim the paper is reproduced merely because `run_smoke.py` passes.
