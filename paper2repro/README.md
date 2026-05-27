# paper2repro

Self-hosted multi-agent server for paper reproduction. Runs its own agent
pipeline (with critique, planning, code generation, validation, and repair
stages) and exposes both a CLI and a FastAPI + React web layer.

Fork of [HKUDS/DeepCode](https://github.com/HKUDS/DeepCode) (MIT). See
[`NOTICE.md`](./NOTICE.md) for what was inherited and what was added in this
fork.

Part of the [Papyrus](../README.md) suite. The lightweight Claude Code skill
counterpart is [`../paper2repro-skill/`](../paper2repro-skill/).

## Pipeline

10 phases inherited from DeepCode plus a critique stage inserted between
document preprocessing and planning:

```
1. PDF ingest
2. Document segmentation
3. Paper structure extraction
4. Document preprocessing
4.5. Critique (老师傅批判) — must_implement / traps / external_deps   [added]
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

## Honest scope

- This is a **learning project**, not a benchmarked product. Reproduction
  success rate has not been measured against any public benchmark like
  PaperBench.
- The quality gates and repair loop **reduce** the probability of broken
  output but do not guarantee correctness — the reproduction report is the
  source of truth, not "code runs without errors".
- The DeepCode lineage is real: `core/`, `tools/`, and most of `workflows/`
  scaffolding is from upstream. The substantive additions are documented in
  [`NOTICE.md`](./NOTICE.md).
- The frontend and demo HTMLs were built to make the system observable, not
  to be a polished product surface.
