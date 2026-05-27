# NOTICE

`paper2repro/` (formerly `paper2code/`) is a fork of
[HKUDS/DeepCode](https://github.com/HKUDS/DeepCode), released under the MIT
License.

The original DeepCode copyright notice is retained in the top-level
[`../LICENSE`](../LICENSE) file at the Papyrus suite root.

## What was inherited from DeepCode

Most of the runtime scaffolding is from upstream and used largely as-is:

- `core/` — LLM runtime, providers, sessions
- `tools/` — MCP servers for code implementation, document segmentation, etc.
- `workflows/agent_orchestration_engine.py` — main pipeline driver
- `workflows/code_implementation_workflow.py` — main implementation loop
- `prompts/code_prompts.py` — generation prompt scaffolding

## What was added or rewritten in this fork

These are the substantive additions:

- **Critique stage** — `prompts/critique_prompts.py` + `workflows/agents/critique_agent.py`.
  Inserted between document preprocessing and code planning to produce a
  structured `must_implement / implementation_traps / external_deps` list.
- **Quality gate system** — `workflows/artifact_contract.py`,
  `workflows/validation_agent.py` (now `workflows/agents/validation_agent.py`),
  `workflows/type_check_gate.py`, `workflows/reproduction_gate.py`,
  `workflows/code_acceptance.py`, `workflows/repair_planner.py`. Together they
  form a "validate → diagnose → repair" loop layered on top of the original
  implementation workflow.
- **Trajectory logger** — `workflows/agents/memory_agent_concise.py` writes
  per-task `trajectory/segments.jsonl` with `messages` (runtime format) and
  `rich_messages` (Anthropic `tool_use` / `tool_result` block format).
- **Web layer** — `api/` (FastAPI + SSE) and `frontend/` (React + Vite). The
  upstream UI (`new_ui` / `nanobot`) was removed in the fork.
- **Demo / observability** — `demo/generate_demo_html.mjs` and the offline HTML
  bundles, plus `logs/events.jsonl` event streaming.
- **CLI entry** — `paper2repro.py` (replaces upstream `deepcode.py`).

## License compliance

This fork remains under MIT, identical to upstream. The MIT permission notice
and the upstream copyright line are preserved in the top-level LICENSE. If you
redistribute this fork or substantial portions of it, you must retain both
copyright lines and the permission notice.
