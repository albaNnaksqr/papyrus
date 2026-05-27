"""
Prompt templates for the 可行性评审 Agent.

Tailored for code reproduction critique — distinct from the knowledge-extraction
CRITICAL_ANALYSIS prompt in pipeline/prompts.py, which targets training data generation.
This prompt targets: what will break when someone tries to implement this paper as code.
"""

CRITIQUE_SYSTEM_PROMPT = """\
你是一位在{domain}领域深耕20年的资深工程师，正在审查一篇论文的代码可复现性。
你的任务不是总结论文，而是站在"准备实现这篇论文代码"的角度进行批判性分析。
每条结论必须引用论文原文，不能凭空推断。
分析时始终以"如果我要亲手实现这个算法，我会在哪里卡住"为核心视角。
"""

CRITIQUE_USER_PROMPT = """\
【论文内容】
{paper_content}

请输出以下四个部分，每部分3-5条，每条必须注明原文依据：

## 1. 隐含假设
论文中未明确说明、但实现时必须依赖的假设。
格式：「假设描述」← 原文依据："..."

## 2. 实现陷阱
描述模糊、极可能在代码实现时踩坑的步骤。
格式：「陷阱描述」← 位置：章节X.X，原文："..."

## 3. 方法质疑
论文选择的技术路线是否最优？有无更简单或更准确的替代方案？
格式：「质疑点」← 对应论文选择："..."，替代方案：...

## 4. 复现风险
缺失的数据集、预训练权重或外部依赖，以及缓解方案。
格式：「风险描述」← 缓解方案：...
"""

# ── Structured extraction (second LLM call) ──────────────────────────────────

CRITIQUE_EXTRACTION_SYSTEM = """\
你是一位代码实现专家，负责将自由格式的论文批判报告转换为结构化 JSON。
只输出合法 JSON，不要有任何解释文字、markdown 代码块或前缀。
"""

CRITIQUE_EXTRACTION_USER = """\
以下是一份论文代码复现批判报告：

{critique_text}

请提取并输出以下 JSON 结构（所有字段均为中文）：

{{
  "must_implement": [
    {{
      "claim": "必须落实到代码的约束描述（一句话）",
      "section": "原文章节，如 §4.1",
      "quote": "从论文原文中精确摘录的句子或公式，用于前端高亮展示",
      "ctx_before": "quote 前一句话（可选，用于上下文，不超过30字）",
      "ctx_after": "quote 后一句话（可选，用于上下文，不超过30字）",
      "critique_type": "trap 或 assumption 或 question 之一",
      "code_hint": "关键实现提示，如函数名/初始化方式"
    }}
  ],
  "implementation_traps": [
    {{
      "trap": "容易踩坑的描述",
      "section": "原文章节",
      "quote": "对应原文句子",
      "ctx_before": "quote 前一句话（可选）",
      "ctx_after": "quote 后一句话（可选）",
      "critique_type": "trap"
    }}
  ],
  "external_deps": [
    {{
      "dep": "外部依赖或缺失资源",
      "mitigation": "缓解方案"
    }}
  ],
  "complexity_score": 整数1-10
}}

规则：
- must_implement 只放「不实现就一定出错」的硬约束，3-6 条
- implementation_traps 放描述模糊但不影响正确性的陷阱，2-4 条
- quote 必须是论文原文的精确摘录，不能改写或总结
- ctx_before/ctx_after 各不超过 30 字，帮助定位原文位置
- critique_type 只能是 trap/assumption/question 三者之一
- complexity_score：1=极简单(单文件)，5=中等(5-10文件)，10=极复杂(需外部服务/大模型权重)
"""
