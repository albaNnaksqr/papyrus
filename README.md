# Papyrus

A toolkit for engineering academic papers: extract the implicit research
process as training data, reproduce the paper as runnable code, and orchestrate
that reproduction in an audit-ready multi-agent pipeline.

Papyrus bundles three tools that share a worldview — *papers are not just
text to read; they contain a research process worth structuring* — but each
tool runs independently and addresses a different stage of paper engineering.

## The three tools

| Tool | Form | What it does |
|------|------|--------------|
| **[`paper2trace`](./paper2trace/)** | Standalone Python script | Extracts the implicit research process from a paper (hypothesis chains, critical analysis, decisions) and emits structured artifacts including SFT / DPO / ReAct trace data. |
| **[`paper2repro-skill`](./paper2repro-skill/)** | Claude Code / Codex skill | Lightweight paper reproduction that runs *inside* an existing agent. Produces runnable code, evaluation scripts, and a claim-by-claim reproduction report. |
| **[`paper2repro`](./paper2repro/)** | Self-hosted multi-agent server | Heavier paper reproduction with its own multi-agent runtime, quality gates (artifact contract / type check / reproduction gate), web UI, and trajectory logging in Anthropic `rich_messages` format. |

`paper2repro` and `paper2repro-skill` are **not** lite/pro tiers of the same product.
They are two architectural shapes of the same problem — the skill borrows Claude
Code's native agent; the server runs its own. Use the skill when you have Claude
Code and want a fast result. Use the server when you want a self-contained, audited,
visualizable run with explicit quality gates.

## Examples

End-to-end examples live in [`examples/`](./examples/). The
[`boyer_moore_*`](./examples/) set demonstrates a Level-3 reproduction (algorithm
+ experiment trend) of *Boyer & Moore 1977 — A Fast String Searching Algorithm*,
including the `paper2trace` artifacts and an agent trace.

## Architecture & lineage

`paper2trace` and `paper2repro-skill` are original to this repository.

`paper2repro` is a fork of [HKUDS/DeepCode](https://github.com/HKUDS/DeepCode)
(MIT). It retains DeepCode's multi-agent + MCP scaffolding (`core/`, `tools/`,
most of `workflows/`) and adds the following capabilities on top:

- **Critique stage (老师傅批判)** inserted between document preprocessing and
  code planning — produces structured `must_implement / traps / external_deps`
  before any code is written
- **Quality gate system** — artifact contract validation, mypy-backed type
  check, reproduction gate, and automatic repair loop that rewrites failing
  artifacts in place
- **Trajectory logging** in Anthropic `rich_messages` format (`tool_use` /
  `tool_result` structured blocks), suitable for downstream agent fine-tuning
- **FastAPI + SSE event stream** replacing the upstream nanobot UI
- **React web layer** with task list, artifact browser, event replay, and
  trajectory viewer
- **Offline demo bundle** for sharing pipeline replay as standalone HTML

Full per-file diff against upstream documented in
[`paper2repro/NOTICE.md`](./paper2repro/NOTICE.md).

## Repository layout

Each subdirectory ships its own README with installation and run instructions.
The three tools share this repo and license but evolve independently.

## License

MIT. See [LICENSE](./LICENSE). DeepCode's original copyright notice is retained.
