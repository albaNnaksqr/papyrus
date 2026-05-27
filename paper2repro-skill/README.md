# paper2repro-skill

A Claude Code / Codex **skill** that reproduces an academic paper into runnable
code by leveraging the host agent's native execution. Lightweight counterpart
to the self-hosted [`paper2repro`](../paper2repro/) server.

Part of the [Papyrus](../README.md) suite.

## How it differs from `paper2repro/`

| | `paper2repro-skill` (this) | `paper2repro` (self-hosted server) |
|---|---|---|
| Agent runtime | Borrows Claude Code / Codex's native agent | Self-hosted multi-agent pipeline |
| Install footprint | Single SKILL.md + helper scripts | FastAPI + React + MCP servers + LLM provider |
| Quality gates | Delegated to host agent + skill workflow rigor (`ambiguity_audit.md`, `gap_report.md`, claim-by-claim `REPRODUCTION_REPORT.md`) | Built-in (artifact contract, type check, reproduction gate, auto-repair loop) |
| Observability | A single `agent_trace.jsonl` segment | Per-task events / LLM / MCP / trajectory logs |
| Best for | Quick, one-off reproduction inside an existing agent session | Audited, repeatable, visualizable runs |

They are **not** lite/pro tiers of the same product. They are two architectural
shapes of the same job. Pick the one whose runtime model matches your context.

## What it produces

When the skill runs, it builds a project directory containing:

- `paper_structure.json` — LLM-extracted evidence from the paper
- `reproduction_contract.json` — target, success criteria, data, metrics, gaps
- `ambiguity_audit.md` — questions that the paper does not answer
- `gap_report.md` — user-readable blockers and downgrade reasons
- `configs/smoke.json`, `configs/reproduction.json`
- `scripts/run_smoke.py`, `scripts/run_experiment.py`, `scripts/evaluate_reproduction.py`
- `src/`, `tests/`, `requirements.txt`
- `REPRODUCTION_REPORT.md` — claim-by-claim status
- `agent_trace.jsonl` — single-segment trajectory of the skill run

See [`../examples/boyer_moore_skill/`](../examples/boyer_moore_skill/) for the
full output of a real Level-3 run.

## Reproduction levels

The skill explicitly classifies the depth of reproduction:

- **Level 1 Toy demo** — core idea on synthetic data
- **Level 2 Algorithm** — formulas / state / IO faithful to paper
- **Level 3 Experiment** — main figure / metric / trend regenerated or meaningfully compared
- **Level 4 Project** — data flow, configs, training/eval scripts mirror a released codebase

Default target is Level 3. Downgrade is explicit and logged in `gap_report.md`.

## Install as a Claude Code skill

```bash
mkdir -p ~/.claude/skills/paper2repro
cp SKILL.md ~/.claude/skills/paper2repro/
cp -r scripts ~/.claude/skills/paper2repro/
```

## Use

Inside Claude Code:

```text
/paper2repro pdf_path=/absolute/path/to/paper.pdf
/paper2repro pdf_path=/absolute/path/to/paper.pdf auto=true
```

## Trace markers

The skill emits stable markers around the run for offline trace extraction:

```text
PAPER_REPRO_TRACE_START run_id=<id> pdf_path=<path>
...
PAPER_REPRO_TRACE_END run_id=<id> status=complete project_name=<name>
```

Export the corresponding agent trajectory afterwards:

```bash
python scripts/export_trace.py --latest --source auto --output traces.jsonl
```

The exporter is backward-compatible with older `/paper-repro` invocations.
