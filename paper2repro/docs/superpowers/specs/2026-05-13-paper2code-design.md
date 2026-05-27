# Paper2Code with 老师傅批判 — Design Spec

**Goal:** Fork DeepCode, strip it to Paper2Code only, and insert a 老师傅批判 Agent between document preprocessing and code planning.

**Architecture:** Sequential multi-agent pipeline inherited from DeepCode, with one new Agent (老师傅批判) added at Phase 4.5. Text report output first; structured output deferred.

**Tech Stack:** Python, mcp-agent, OpenAI-compatible API (configurable), pypdf/docling for PDF parsing.

---

## 1. Project Location & Structure

```
/home/kps_spark/workspace/paper2code/
├── workflows/
│   ├── agents/
│   │   ├── code_implementation_agent.py
│   │   ├── document_segmentation_agent.py
│   │   ├── memory_agent_concise.py
│   │   ├── memory_agent_concise_index.py
│   │   ├── memory_agent_concise_multi.py
│   │   ├── requirement_analysis_agent.py
│   │   └── critique_agent.py          # NEW
│   ├── agent_orchestration_engine.py  # MODIFIED: insert Phase 4.5
│   ├── code_implementation_workflow.py
│   ├── code_implementation_workflow_index.py
│   ├── environment.py
│   ├── planning_runtime.py
│   ├── plan_review_runtime.py
│   ├── plugins/
│   └── workflow_context.py
├── core/                              # Kept as-is from DeepCode
├── prompts/
│   ├── code_prompts.py                # Kept as-is from DeepCode
│   └── critique_prompts.py            # NEW
├── tools/                             # Kept as-is from DeepCode
├── utils/                             # Kept as-is from DeepCode
├── paper2code.py                      # NEW CLI entry (replaces deepcode.py)
├── config.yaml.example                # NEW
└── requirements.txt                   # Trimmed (remove UI deps)
```

**Removed from DeepCode:**
- `new_ui/` — web frontend/backend
- `ui/` — legacy UI
- `nanobot/` — separate agent subproject
- `deepcode.py` — web app launcher
- `cli/` — replaced by `paper2code.py`

---

## 2. 老师傅批判 Agent

### 2.1 Insertion Point

In `agent_orchestration_engine.py`, between Phase 4 (Document Preprocessing) and Phase 5 (Code Planning):

```
Phase 4 (50%): Document Segmentation & Preprocessing → paper.md ready
Phase 4.5 (58%): 老师傅批判 Agent                    ← NEW
Phase 5 (65%): Code Planning (receives critique as context)
```

### 2.2 Inputs & Outputs

- **Input:** `{task_dir}/paper.md` (produced by Phase 4)
- **Output:** `{task_dir}/critique_report.md`
- **Side effect:** critique summary string injected into Phase 5 planning prompt context

### 2.3 Prompt (`critique_prompts.py`)

```python
CRITIQUE_SYSTEM_PROMPT = """\
你是一位在{domain}领域深耕20年的资深工程师，正在审查一篇论文的可复现性。
你的任务不是总结论文，而是站在"准备实现这篇论文代码"的角度，进行批判性分析。
每条结论必须引用论文原文，不能凭空推断。
"""

CRITIQUE_USER_PROMPT = """\
【论文内容】
{paper_content}

请输出以下四个部分：

## 1. 隐含假设
论文中未明确说明、但实现时必须依赖的假设。（3-5条，每条注明原文依据）

## 2. 实现陷阱
描述模糊、极可能在代码实现时踩坑的步骤。（3-5条，每条注明章节位置）

## 3. 方法质疑
论文选择的技术路线是否最优？有无更简单或更准确的替代方案？

## 4. 复现风险
缺失的数据集、预训练权重或外部依赖，以及缓解方案。
"""
```

### 2.4 Agent Implementation (`critique_agent.py`)

- Direct LLM call (no MCP tool calls needed — only reads paper.md, writes critique_report.md via Python file I/O)
- Returns `{"status": "success", "critique_summary": str, "report_path": str}`
- On failure: returns `{"status": "skipped", "reason": str}` — pipeline continues

### 2.5 Phase 5 Integration

The critique summary (first 2000 chars of `critique_report.md`) is prepended to the planning prompt:

```python
# In orchestrate_code_planning_agent():
if critique_result["status"] == "success":
    critique_context = f"\n\n[老师傅批判摘要]\n{critique_result['critique_summary']}\n"
    paper_content = critique_context + paper_content
```

---

## 3. CLI Interface

**Entry point:** `paper2code.py`

```bash
# Basic usage
python paper2code.py --pdf path/to/paper.pdf

# Options
python paper2code.py --pdf paper.pdf --output ./output
python paper2code.py --pdf paper.pdf --fast          # skip GitHub reference analysis
python paper2code.py --pdf paper.pdf --no-critique   # skip 老师傅批判
python paper2code.py --pdf paper.pdf --config custom_config.yaml
```

---

## 4. Configuration (`config.yaml.example`)

```yaml
llm:
  base_url: "https://api.openai.com/v1"  # any OpenAI-compatible endpoint
  api_key: "${OPENAI_API_KEY}"           # or set OPENAI_API_KEY env var
  model: "gpt-4o"                        # main pipeline model
  critique_model: "gpt-4o"              # critique agent model (can differ)

output:
  base_dir: "./output"

pipeline:
  enable_indexing: true                  # Phase 6-8 GitHub reference analysis
  enable_critique: true                  # Phase 4.5 老师傅批判
```

---

## 5. Output Directory

```
output/{task_id}/
├── paper.pdf                 # original input
├── paper.md                  # parsed paper (Phase 4)
├── critique_report.md        # 老师傅批判报告 (Phase 4.5) ← NEW
├── initial_plan.txt          # code plan (Phase 5)
├── reference_analysis.txt    # GitHub reference analysis (Phase 6)
├── src/                      # generated code (Phase 9)
└── logs/
    └── system.jsonl
```

---

## 6. Out of Scope (Future)

- Structured critique output (JSON schema) that directly constrains code generation
- Web UI / API service
- Text2Web / Text2Backend modes
