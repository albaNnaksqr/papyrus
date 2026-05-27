# Papyrus

A learning-oriented toolkit for working with academic papers, built while exploring
AI-assisted software engineering.

Papyrus contains three tools that address adjacent problems around academic papers.
They share a worldview — *papers are not just text to read, they contain a research
process worth structuring* — but each tool works independently.

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

## Honest context

- This is a **learning project**, not a product. It exists because the author
  recently started using AI-assisted coding and used it to build something
  non-trivial. The reproduction quality, data flywheel narrative, and
  multi-agent design have **not** been formally benchmarked.
- `paper2repro/` is a **fork of [HKUDS/DeepCode](https://github.com/HKUDS/DeepCode)**
  (MIT). The fork retains the original `core/`, `tools/`, and most of `workflows/`
  scaffolding; the additions are documented in
  [`paper2repro/NOTICE.md`](./paper2repro/NOTICE.md).
- `paper2trace` and `paper2repro-skill` are original to this repository.

## Status

Each subdirectory has (or will have) its own README with run instructions and
dependencies. Treat each tool as an independent project that happens to share a
repository and license.

## License

MIT. See [LICENSE](./LICENSE). DeepCode's original copyright notice is retained.
