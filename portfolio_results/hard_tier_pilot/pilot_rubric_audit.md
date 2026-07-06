# Hard-tier 试点 rubric 审计 + probe 对账

日期：2026-07-06
范围：本次新归一化的 8 条记录（hard_tier_pilot 5 条 + claude_paired_runs 3 条），
按 `docs/trajectory-dataset-quality-rubric.md` 过评；附 probe 预测对账。
评分是人工判读 normalized record 字段 + 源工件抽查的结果，保留原始依据备复核。

## Rubric 评分

| record | grounding 15 | contract 15 | trajectory 15 | evidence 15 | reward/labels 15 | taxonomy 10 | provenance 10 | comparability 5 | 总分 | band |
|---|---|---|---|---|---|---|---|---|---|---|
| pilot/codex/grokking | 2 | 2 | 2 | 2 | 2 | 1 | 2 | 2 | 95 | dataset-ready |
| pilot/codex/speculative_decoding | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 100 | dataset-ready |
| pilot/codex/dpo | 2 | 2 | 2 | 2 | 2 | 1 | 2 | 2 | 95 | dataset-ready |
| pilot/claude/grokking | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 100 | dataset-ready |
| pilot/claude/speculative_decoding | 2 | 2 | 0 | 1 | 2 | 1 | 1 | 0 | 62.5 | audit-only |
| paired/claude/reflexion | 2 | 2 | 2 | 1 | 0 | 2 | 1 | 2 | 77.5 | portfolio-ready* |
| paired/claude/repobench | 2 | 2 | 2 | 1 | 0 | 0 | 1 | 2 | 67.5 | audit-only* |
| paired/claude/swe_bench_multimodal | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 100 | dataset-ready |

\* 星号：分数被下述系统性问题 A 压低，修复后重归一化可复评。

逐条依据（低分项）：

- **pilot/codex/grokking、pilot/codex/dpo taxonomy=1**：outcome 为
  partial_success 但 failure_types 为空——"partial 的原因"没有标签化，违反
  rubric 5 的一致性要求（镜像于 "outcome=success conflicts with
  failure_types" 的失败信号）。dpo 尤其反常：strict=1.00、coverage=1.00 却标
  partial_success，是 `_outcome()` 对 evaluation `status: "passed"` 的映射保守
  所致，语义上更像 success。
- **pilot/claude/speculative_decoding**：`agent_trace.jsonl` 完全缺失（该 run
  早于 skill.v2.2 的 Claude host trace 写入支持）。trajectory=0（无法行为级
  回放）、comparability=0（host=unknown、无 token/wall time）。reward 反而给
  2：coverage 0.15 / strict 0.15 / confidence low 是对证据缺失的**正确降级**，
  这正是 rubric 要求的行为。处置：audit-only，除非从
  `~/.claude/projects/...` 的原始会话记录回填 trace 后重归一化。
- **paired/claude/reflexion、repobench reward/labels=0**：outcome 被标为
  invalid_run，但两个 run 实际都有评测产物——只是文件名不符合契约
  （`evaluation_result.json`、`evaluation_summary.json` 而非规范的
  `results/reproduction_evaluation.json`）。invalid_run 是**误导性标签**（run
  并非无效，是命名不合规），按 rubric "misleading" 判 0。repobench 另有
  taxonomy=0（134 turns 的 run 零失败标签且被判 invalid，无任何解释性标签）。

## 系统性发现（比单条分数重要）

**A. Claude host 输出契约遵从性缺口。**3 条 claude 侧 run 的评测文件命名
全部偏离契约（reflexion/repobench/hard_tier speculative 各不相同），codex 侧
6+3 条全部合规。这是 paper2repro skill 在 Claude host 上的提示/约束强度问题，
不是模型能力问题。**修复优先级最高**：skill 侧加输出文件名硬校验（或
scaffold 收尾时做规范化重命名），否则 claude 侧铺量的每条轨迹都会带同样的
标签污染。修复后这 3 条重归一化，预期 2 条回到 portfolio-ready 以上。

**B. 缺失 trace 的历史 run。**pilot/claude/speculative_decoding 无
agent_trace.jsonl。它的原始 Claude 会话记录仍在本机
（`~/.claude/projects/-home-kps-spark-workspace-papyrus/`，agentcap 也捕获了
该会话），技术上可回填；性价比中等，排在 A 之后。

**C. probe 预测力接近零，不能用作铺量选题器。**对账结果：

| paper | probe 预测 | 实际失败标签（全部 run 合并） |
|---|---|---|
| grokking | dataset_unavailable, hyperparameter_missing, metric_mismatch | （无） |
| speculative_decoding | hyperparameter_missing, metric_mismatch | environment_gap, hyperparameter_missing |
| dpo | dataset_unavailable, hyperparameter_missing, metric_mismatch | （无） |

命中 1 / 误报 7 / 漏报 1 → **precision 0.12，recall 0.50**。probe 对三篇论文
输出了近乎恒定的标签集（PDF 文本启发式），没有判别力。铺量阶段的论文筛选
暂时应回退为人工按选题标准 v2 筛，probe 需要重做（至少要能区分"数据可确定
性生成的算法类"与"依赖外部数据集的实验类"）再启用。

## 修复 A 落地记录（2026-07-06 当日）

- **skill 硬化**：`paper2repro-skill/SKILL.md`（`~/.claude/skills/paper2repro`
  为同一文件的符号链接，codex 直接读仓库路径，改一处三端生效）新增两处硬约束：
  Required Artifacts 里钉死 `results/reproduction_evaluation.json` 的路径与
  `status`/`status_schema` 形状；Phase 4 增加输出路径 Hard rule + 收尾自检
  命令。
- **规范化重归一化**：reflexion、repobench 两条 run 的评测裁决被机械复制到
  规范路径（原文件内容整体嵌入 `source_evaluation`，`provenance_note` 记录
  转换来源，无任何重新判断）。重归一化后：
  reflexion `invalid_run → success`（strict 0.15→0.55，fidelity 标签保留），
  repobench `invalid_run → partial_success`（strict 0.15→0.68）。复评分数：
  reflexion 77.5→100（dataset-ready），repobench 67.5→95（dataset-ready，
  taxonomy 仍 1：partial 无失败标签）。
- **spec_dec claude 未规范化（有意）**：核查发现其 REPRODUCTION_REPORT.md
  仍是占位符（"Not evaluated yet"）——评测环节从未收尾，agent 从未做出裁决。
  给它补 status 属于编造数据，故维持 invalid_run / audit-only。该 run 从
  "命名不合规"改判为**真实的不完整 run**，是 rerun 候选（发现 B 的 trace
  缺失与此同源：该 run 早于 v2.2，多个收尾步骤缺失）。

## 对 rubric「最低公开声明标准」的进度（A 修复后）

- ≥10 条 portfolio-ready：本批 dataset-ready 共 7 条（codex×3、claude
  grokking、swe_multimodal、reflexion、repobench），加 code_agent_deep_runs
  已审计 6 条 → **达标**。
- ≥3 对同论文 codex/claude 配对：健全配对 4 对（grokking、
  swe_bench_multimodal、reflexion、repobench）→ **达标**；dpo 第 5 对在跑。
- 人工审计确认 reward/failure 标签：本文即第一次；抽查依据已列。

## 行动清单（更新后）

1. ~~修 A~~ 已完成（本文上节）。
2. claude 侧 dpo_repro 在跑（tmux-guard 看护）。
3. probe 重做前，铺量选题用人工筛选。
4. （可选）rerun 或回填 pilot/claude/speculative_decoding（trace + 评测收尾
   均缺，rerun 价值高于回填）。
