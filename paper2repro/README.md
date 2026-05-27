# paper2repro

Self-hosted multi-agent server for academic paper reproduction. Runs a 10-phase
pipeline (PDF ingest → critique → planning → code generation → quality-gated
validation → automatic repair → reporting) with full observability and exposes
both a CLI and a FastAPI + React web layer.

Fork of [HKUDS/DeepCode](https://github.com/HKUDS/DeepCode) (MIT) with
substantial additions — see [§ What this fork adds](#what-this-fork-adds-beyond-deepcode)
below and [`NOTICE.md`](./NOTICE.md) for the per-file diff.

Part of the [Papyrus](../README.md) suite. The lightweight Claude Code skill
counterpart is [`../paper2repro-skill/`](../paper2repro-skill/).

## What this fork adds beyond DeepCode

| Capability | Upstream DeepCode | paper2repro |
|---|---|---|
| Multi-agent + MCP scaffolding | ✓ | ✓ inherited |
| Critique stage before planning | — | ✓ added |
| Structured `must_implement / traps / external_deps` | — | ✓ added |
| Artifact contract validation | — | ✓ added |
| Type-check gate (mypy integration, configurable per project) | — | ✓ added |
| Reproduction gate (post-implementation runtime validation) | — | ✓ added |
| Auto-repair loop on gate failures (up to N iterations) | — | ✓ added |
| Trajectory logging in Anthropic `rich_messages` (tool_use/tool_result blocks) | — | ✓ added |
| FastAPI + SSE event stream | — | ✓ added |
| React web UI with task list, artifact browser, event replay, trajectory viewer | nanobot (removed) | ✓ rewritten |
| Per-task observability (`events.jsonl`, structured `llm.jsonl`, `mcp.jsonl`) | basic | ✓ extended |
| Offline demo bundle (standalone HTML for sharing replay) | — | ✓ added |

These additions turn the pipeline from "generate code from a paper" into
"generate code, validate it against the paper's claims, repair on failure, and
preserve a complete audit trail."

## Pipeline

10 phases inherited from DeepCode plus a critique stage inserted between
document preprocessing and planning:

```
1. PDF ingest
2. Document segmentation
3. Paper structure extraction
4. Document preprocessing
4.5. Critique — must_implement / traps / external_deps   [added]
5. Code planning
6-8. GitHub reference analysis (skippable with --fast)
9. Code implementation (with validation / type-check / reproduction gates)   [gates added]
10. Finalize + report
```

Each run writes to `output/tasks/<task_id>/` and includes:

- `paper.md` — paper text
- `document_segments/` — structured paper segments
- `critique_structured.json` — must-implement points, traps, deps
- `initial_plan.txt` — agent-produced implementation plan
- `generate_code/<project_name>/` — generated source
- `code_implementation_report.txt` — claim-by-claim status
- `logs/events.jsonl` — full event stream
- `logs/llm.jsonl`, `logs/mcp.jsonl` — raw LLM and MCP tool call records
- `trajectory/segments.jsonl` — multi-turn agent dialogue in
  `messages` (runtime) and `rich_messages` (Anthropic `tool_use` / `tool_result`)
  formats

## Install

```bash
# Python deps
pip install -r requirements.txt

# Frontend (only needed if you want the web UI)
cd frontend
npm install
npm run build
cd ..
```

You also need a config file. Start from the example:

```bash
cp config.yaml.example config.yaml
cp deepcode_config.json.example deepcode_config.json
# edit both — set LLM base_url, api_key, model
```

## Run

### CLI (one paper, end to end)

```bash
python paper2repro.py --pdf path/to/paper.pdf
python paper2repro.py --pdf path/to/paper.pdf --fast          # skip GitHub reference analysis
python paper2repro.py --pdf path/to/paper.pdf --no-critique   # skip critique stage
python paper2repro.py --pdf path/to/paper.pdf --config custom.yaml
```

### Web server (with SSE event stream)

```bash
python serve.py
# open http://localhost:8000 (or wherever your frontend is served)
```

The frontend submits PDFs to the FastAPI backend and streams progress events
over SSE while the pipeline runs. Past runs are visible under `/app` with
artifact browser, event replay, and trajectory viewer.

## Regenerating the offline demo bundles

`demo/executive-briefing.html` (small, ~28KB) is committed to the repo for
quick at-a-glance preview. The two large React-built demos
(`frontend-static.html`, `process-replay.html`, ~22MB each) are **not** in
git because they inline absolute paths from the build machine.

To regenerate them locally after a few runs:

```bash
# 1. Make sure your output/tasks/<id>/ directories exist (runs from `paper2repro.py`)
# 2. Install frontend deps
cd frontend && npm install && cd ..
# 3. Generate
node demo/generate_demo_html.mjs
```

The script reads from `output/tasks/`, runs two vite builds (one per page),
and emits the three HTMLs under `demo/`. Total time ~10 seconds after
`npm install`.

## Export training corpus

After one or more successful runs, export per-task LLM / MCP / trajectory logs
into SFT / DPO / CoT JSONL datasets:

```bash
python scripts/export_corpus.py                          # all tasks
python scripts/export_corpus.py --task paper_87d8010e   # single task
python scripts/export_corpus.py --format sft dpo        # specific formats
python scripts/export_corpus.py --out datasets/
```

Note: the raw `llm.jsonl` and `mcp.jsonl` logs are **execution records**, not
labeled training data — `export_corpus.py` reshapes them into common training
formats but does not perform quality filtering. For high-quality SFT/DPO data
explicitly aimed at research reasoning, see the sibling
[`paper2trace`](../paper2trace/) tool.

## Configuration knobs

A few environment variables that override config.yaml at runtime:

| Variable | Purpose |
|----------|---------|
| `OPENAI_BASE_URL`, `OPENAI_API_KEY` | LLM provider for the main pipeline |
| `CRITIQUE_MODEL` | Override model for the critique stage |
| `IMPL_LOOP_MAX_ITERATIONS` | Cap on the implementation repair loop (default 1200) |
| `PLAN_FILE_CAP` | Cap on .py files in a single plan (default 12) |

## Notes

- The quality gates and repair loop are designed to **catch** broken output,
  not to *guarantee* correctness. The reproduction report is the authoritative
  source of run status — `code runs without errors` alone does not imply the
  paper's claims were faithfully reproduced.
- Reproduction quality varies with paper complexity and LLM provider strength.
  Results have not been measured against public benchmarks like PaperBench;
  per-task quality is captured in each run's `code_implementation_report.txt`.
- Trajectory data in `trajectory/segments.jsonl` is an **execution record**.
  It is suitable as raw signal for downstream training data construction; for
  curated SFT / DPO / ReAct artifacts aimed at research reasoning, use the
  sibling [`paper2trace`](../paper2trace/) tool instead.
