#!/usr/bin/env python3
"""
paper2repro — Paper-to-Code CLI

Fork of DeepCode focused on paper reproduction with a critique (老师傅批判) stage.
Usage: python paper2repro.py --pdf path/to/paper.pdf [options]
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"


def _load_config(config_path: str) -> dict:
    """Load config.yaml if it exists, else return empty dict."""
    import yaml
    p = Path(config_path)
    if not p.exists():
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _apply_config(cfg: dict):
    """Push config values into environment variables (env takes precedence)."""
    llm = cfg.get("llm", {})
    if llm.get("base_url") and not os.environ.get("OPENAI_BASE_URL"):
        os.environ["OPENAI_BASE_URL"] = llm["base_url"]
    if llm.get("api_key") and not os.environ.get("OPENAI_API_KEY"):
        api_key = llm["api_key"]
        if not api_key.startswith("${"):
            os.environ["OPENAI_API_KEY"] = api_key
    if llm.get("model") and not os.environ.get("CRITIQUE_MODEL"):
        os.environ["CRITIQUE_MODEL"] = llm.get("critique_model", llm["model"])
    # workspace.root is configured via deepcode_config.json, not env var


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="paper2repro",
        description="Convert a research paper PDF into reproducible code.",
    )
    p.add_argument("--pdf", required=True, help="Path or URL to the research paper PDF")
    p.add_argument("--output", default=None, help="Output base directory (default: ./output)")
    p.add_argument("--fast", action="store_true", help="Skip GitHub reference analysis (Phase 6-8)")
    p.add_argument("--no-critique", action="store_true", help="Skip 老师傅批判 (Phase 4.5)")
    p.add_argument("--config", default="config.yaml", help="Path to config.yaml (default: config.yaml)")
    return p


async def _run(args: argparse.Namespace):
    from core.platform_compat import configure_utf8_stdio
    configure_utf8_stdio()

    from workflows.agent_orchestration_engine import execute_multi_agent_research_pipeline
    from loguru import logger

    print(f"🚀 paper2repro starting")
    print(f"   PDF    : {args.pdf}")
    print(f"   Fast   : {args.fast}")
    print(f"   Critique: {'disabled' if getattr(args, 'no_critique', False) else 'enabled'}")

    result = await execute_multi_agent_research_pipeline(
        input_source=args.pdf,
        logger=logger,
        enable_indexing=not args.fast,
        no_critique=getattr(args, "no_critique", False),
    )
    print(f"\n✅ Done:\n{result}")


def main():
    parser = build_parser()
    args = parser.parse_args()

    cfg = _load_config(args.config)
    _apply_config(cfg)

    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
