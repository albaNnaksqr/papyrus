"""
老师傅批判 Agent

Reads the parsed paper markdown, calls an LLM to produce a structured critique
focused on code reproduction challenges, and writes critique_report.md.

This agent uses the openai SDK directly (no MCP tools needed — only Python
file I/O). It never raises: failures return {"status": "skipped", "reason": ...}
so the pipeline continues unaffected.
"""

import glob
import json
import logging
import os
from typing import Any, Dict, Optional

import openai

from prompts.critique_prompts import (
    CRITIQUE_SYSTEM_PROMPT,
    CRITIQUE_USER_PROMPT,
    CRITIQUE_EXTRACTION_SYSTEM,
    CRITIQUE_EXTRACTION_USER,
)

CRITIQUE_REPORT_FILENAME = "critique_report.md"
CRITIQUE_STRUCTURED_FILENAME = "critique_structured.json"
_SUMMARY_MAX_CHARS = 2000
_DEFAULT_DOMAIN = "computer science and machine learning"
_DEFAULT_MAX_TOKENS = 2000
_EXTRACTION_MAX_TOKENS = 1200


def _find_paper_markdown(paper_dir: str) -> Optional[str]:
    """Return path to the main paper markdown, excluding known non-paper files."""
    excluded = {CRITIQUE_REPORT_FILENAME, "implement_code_summary.md"}
    candidates = [
        f for f in glob.glob(os.path.join(paper_dir, "*.md"))
        if os.path.basename(f) not in excluded
    ]
    return candidates[0] if candidates else None


async def run_critique_agent(
    paper_dir: str,
    llm_config: Dict[str, Any],
    domain: str = _DEFAULT_DOMAIN,
    logger: Optional[logging.Logger] = None,
) -> Dict[str, Any]:
    """
    Run 老师傅批判 on the parsed paper.

    Args:
        paper_dir: Task directory containing paper.md (produced by Phase 4).
        llm_config: Dict with keys: base_url, api_key, critique_model.
        domain: Paper domain for system prompt personalisation.
        logger: Optional logger; prints to stdout if None.

    Returns:
        {"status": "success", "critique_summary": str, "report_path": str}
        {"status": "skipped", "reason": str}
    """
    log = logger or logging.getLogger(__name__)

    # 1. Find paper markdown
    paper_md_path = _find_paper_markdown(paper_dir)
    if not paper_md_path:
        reason = f"No paper markdown found in {paper_dir}"
        log.warning(f"[Critique] Skipping: {reason}")
        return {"status": "skipped", "reason": reason}

    with open(paper_md_path, "r", encoding="utf-8") as f:
        paper_content = f.read()

    # 2. Call LLM
    try:
        client = openai.OpenAI(
            base_url=llm_config.get("base_url", "https://api.openai.com/v1"),
            api_key=llm_config.get("api_key", os.environ.get("OPENAI_API_KEY", "")),
        )
        model = llm_config.get("critique_model", "gpt-4o")
        system_prompt = CRITIQUE_SYSTEM_PROMPT.format(domain=domain)
        user_prompt = CRITIQUE_USER_PROMPT.format(paper_content=paper_content)

        log.info(f"[Critique] Calling {model} for 老师傅批判...")
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=_DEFAULT_MAX_TOKENS,
            temperature=0.3,
        )
        critique_text = response.choices[0].message.content
    except Exception as e:
        reason = f"LLM call failed: {e}"
        log.warning(f"[Critique] Skipping: {reason}")
        return {"status": "skipped", "reason": reason}

    # 3. Write freeform report
    report_path = os.path.join(paper_dir, CRITIQUE_REPORT_FILENAME)
    header = "# 老师傅批判报告\n\n> 本报告由批判 Agent 自动生成，供代码规划阶段参考。\n\n"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(header + critique_text)
    log.info(f"[Critique] Report written to {report_path}")

    # 4. Structured extraction — second LLM call
    structured_data: Dict[str, Any] = {}
    structured_path = os.path.join(paper_dir, CRITIQUE_STRUCTURED_FILENAME)
    try:
        log.info(f"[Critique] Extracting structured JSON with {model}...")
        extraction_response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": CRITIQUE_EXTRACTION_SYSTEM},
                {"role": "user", "content": CRITIQUE_EXTRACTION_USER.format(
                    critique_text=critique_text
                )},
            ],
            max_tokens=_EXTRACTION_MAX_TOKENS,
            temperature=0.1,
        )
        raw_json = extraction_response.choices[0].message.content or ""
        # Strip accidental markdown fences
        raw_json = raw_json.strip()
        if raw_json.startswith("```"):
            raw_json = raw_json.split("\n", 1)[-1]
            raw_json = raw_json.rsplit("```", 1)[0]
        structured_data = json.loads(raw_json)
        with open(structured_path, "w", encoding="utf-8") as f:
            json.dump(structured_data, f, ensure_ascii=False, indent=2)
        log.info(f"[Critique] Structured JSON written to {structured_path}")
    except Exception as e:
        log.warning(f"[Critique] Structured extraction failed (non-fatal): {e}")
        structured_path = None

    critique_summary = critique_text[:_SUMMARY_MAX_CHARS]
    return {
        "status": "success",
        "critique_summary": critique_summary,
        "report_path": report_path,
        "structured_path": structured_path,
        "structured_data": structured_data,
    }
