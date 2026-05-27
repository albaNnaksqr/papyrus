# mypy 集成到 code generation pipeline — 设计文档

**日期**：2026-05-23
**作者**：shiqirui（用户） + Claude（设计协作）
**Status**：approved, ready for plan

## 背景

paper2code 的 10-phase pipeline 已上多道 quality gate（artifact_contract、claim_contract、code_acceptance、reproduction_gate、smoke_tests、generated_project_lint），但 Run4（`paper_20260523-0018_2602-19543v1_f9f1f860`）的代码人工审查显示：

- `hyper_kggen/main.py --help` smoke 通过 ✅
- 但 `mypy --ignore-missing-imports hyper_kggen/` 报 **79 个错** —— 其中 **48 个 attr-defined + 8 个 call-arg = 56 个跨模块契约 bug**，会让算法路径全部跑崩
- 典型例子：
  - `Node` 在 `hypergraph.py:23` 定义 `.id`，但 `hyperedge_extractor.py:69`、`deduplicator.py:75`、`semantic_matcher.py:121` 三个文件统一使用 `.node_id`
  - `Hypergraph.add_hyperedge(relation_type, node_ids, ...)` 被 `hyperedge_extractor.py:107`、`deduplicator.py:57, 166` 当作 `add_hyperedge(he: Hyperedge)` 调

这是 LLM 写大型多文件项目的典型死法：单文件读起来自洽，跨文件契约对不上。**之前所有 gate 都抓不到，只有 mypy 抓得到**。

## 目标

在 implementation 阶段结束后引入 mypy，作为 **"深度信号 + 重试驱动"**（不参与 task `final_status` 判定），结构化地把跨模块 bug 反馈给 repair loop，让 agent 有机会自我修复。

## 非目标

- 不追求论文复现的完美性 —— 当前阶段是 demo
- 不让 mypy 错误降低 task 的"成功"显示
- 不引入完整类型系统约束（不开 `--strict`、`--check-untyped-defs`）
- 不替代 / 修改现有 artifact_contract、reproduction_gate

## 关键设计决策（用户确认）

| 维度 | 决定 |
|---|---|
| 触发时机 | implementation 完全结束后跑一次 |
| 错误过滤 | 仅 `[attr-defined]` + `[call-arg]` |
| 反馈形式 | 按符号分组、附 AST 推出的根因 |
| Repair 迭代 | 每轮 repair 后重跑 mypy，最多 3 轮 |
| 落地位置 | 新建 `workflows/type_check_gate.py`，subprocess 调 mypy |
| Status 影响 | **不参与 `final_status`**；只挂到 `quality_result["type_check_gate"]` |

## 架构

### 模块边界

```
workflows/
├── type_check_gate.py          ← 本期新增
├── code_acceptance.py          ← 不动
├── artifact_contract.py        ← 不动
├── reproduction_gate.py        ← 不动
└── agent_orchestration_engine.py  ← 加 wire-up（约 30 行）
```

`type_check_gate.py` 暴露三个对外 API + 两个 dataclass，纯函数式（无类、无全局状态、无副作用，方便测试）。

### 公开 API

```python
@dataclass(frozen=True)
class CallSite:
    file: str           # 相对 code_directory 的 posix 路径
    line: int

@dataclass(frozen=True)
class SymbolError:
    symbol: str         # 如 "Node.node_id" 或 "Hypergraph.add_hyperedge"
    error_code: str     # "attr-defined" | "call-arg"
    root_cause: str     # 人类可读，由 AST 反查得到
    call_sites: list[CallSite]

@dataclass(frozen=True)
class TypeCheckResult:
    status: str         # "success" | "errors" | "skipped" | "timeout"
    raw_error_count: int    # mypy 全部错误数
    filtered_count: int     # attr-defined + call-arg 数
    errors_by_symbol: list[SymbolError]
    mypy_exit_code: int
    duration_seconds: float


def run_type_check_gate(
    code_directory: str,
    *,
    timeout_seconds: int = 60,
) -> TypeCheckResult:
    """Run mypy in subprocess, parse output, group by symbol.

    Status semantics:
        - success: mypy exit 0 (clean)
        - errors:  mypy exit 1 (typed errors) AND filtered_count > 0
        - skipped: mypy not installed, code_dir doesn't exist, no .py files,
                   mypy internal error (exit 2), or code base > 5MB
        - timeout: subprocess.TimeoutExpired
    """


def format_errors_for_repair(
    result: TypeCheckResult,
    max_symbols: int = 8,
    max_call_sites_per_symbol: int = 5,
) -> str:
    """Render symbol-grouped errors as markdown for the repair prompt."""
```

## 详细设计

### Step 1 — mypy 调用

**命令**：
```bash
python -m mypy \
    --ignore-missing-imports \
    --no-color-output \
    --show-error-codes \
    --no-error-summary \
    --hide-error-context \
    <code_directory>
```

**Flag 说明**：
- `--ignore-missing-imports`：忽略 openai、sentence-transformers 等无 stub 的三方库噪音（强制必需）
- `--show-error-codes`：拿到 `[attr-defined]` 等标签作过滤依据
- `--no-error-summary`、`--hide-error-context`：减少非结构化噪声
- 显式不加 `--check-untyped-defs`：LLM 生成代码极少有 type hint，加这个会扯出大量 `var-annotated` 噪音

**进程**：
```python
proc = subprocess.run(
    [sys.executable, "-m", "mypy", *flags, code_directory],
    capture_output=True,
    text=True,
    timeout=timeout_seconds,
    cwd=code_directory,   # 关键：让 mypy 把 hyper_kggen/ 当顶级包看
)
```

**退出码处理**：

| 退出码 | 含义 | 处理 |
|---|---|---|
| 0 | 干净 | `status="success"` |
| 1 | 有 type 错 | 解析 → 过滤 → 分组；若过滤后非空则 `status="errors"`，否则 `status="success"` |
| 2 | mypy 内部错（解析失败等） | logger.warning(stderr)，`status="skipped"`，不阻塞 pipeline |
| `TimeoutExpired` | 卡死 | `status="timeout"`，**视为 soft pass** |
| `FileNotFoundError`（mypy 未装） | 部署问题 | logger.error，`status="skipped"`，不阻塞 |

**前置 size 守门**：调 mypy 前先扫 `code_directory` 下所有 `.py` 文件总字节数；若 > 5MB 直接 `status="skipped"`（防止 LLM 误生成巨型文件让 mypy 跑爆内存）。

### Step 2 — 错误行解析

mypy 文本格式稳定：
```
hyper_kggen/core/hyperedge_extractor.py:69: error: "Node" has no attribute "node_id"  [attr-defined]
```

正则：
```python
_LINE_RE = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):\s*error:\s*(?P<msg>.+?)\s*\[(?P<code>[a-z-]+)\]\s*$"
)
```

逐行 parse stdout，只保留 `code in {"attr-defined", "call-arg"}`。其它丢弃（不计入 filtered_count）。

### Step 3 — 符号抽取

按消息模式三条正则，按优先级 try：

| mypy 消息模板 | symbol key 形态 | 例 |
|---|---|---|
| `"X" has no attribute "Y"` | `X.Y` | `Node.node_id` |
| `Missing positional argument "Y" in call to "X"` | `X` | `add_hyperedge` |
| `Too many arguments for "X"` | `X` | `merge_nodes` |

正则示例：
```python
_ATTR_DEFINED_RE = re.compile(r'"([^"]+)" has no attribute "([^"]+)"')
_MISSING_ARG_RE = re.compile(r'Missing positional argument "[^"]+" in call to "([^"]+)"')
_TOO_MANY_ARGS_RE = re.compile(r'Too many arguments for "([^"]+)"')
```

无法匹配的错误进 `other` 桶（不丢，但展示时单独一组在末尾）。

### Step 4 — AST 反查根因

对每个 unique symbol key，遍历 code_directory 下所有 `.py` 文件 AST 一次（结果缓存到 dict）：

**attr-defined 的根因（如 `Node.node_id`）**：

1. AST walk 找 `ClassDef name="Node"`
2. 在 class body 的 `FunctionDef name="__init__"` 里抽 `self.X = ...` 的赋值目标
3. 列出 Node 实际拥有的属性集合 `{"id", "name", "type", "description"}`
4. 根因文本：`"Node 在 {file}:{lineno} 定义，真实属性是 {sorted(attrs)}；本调用引用了不存在的 .node_id"`

找不到 `class Node` → 根因：`"（类定义未找到，可能符号本身就是拼写错误）"`

**call-arg 的根因（如 `add_hyperedge`）**：

1. AST walk 找 `FunctionDef name="add_hyperedge"`（含 class method）
2. 抽签名：`(self, relation_type: str, node_ids: List[str], description: str = "", edge_id: Optional[str] = None)`
3. 根因：`"add_hyperedge 定义在 {file}:{lineno}，签名 {signature_str}"`

找不到 → `"（函数定义未找到）"`

### Step 5 — 聚合与排序

```python
# 同 symbol 合并 call_sites
grouped: dict[str, SymbolError] = {}
for parsed_error in filtered_errors:
    if parsed_error.symbol not in grouped:
        grouped[parsed_error.symbol] = SymbolError(
            symbol=parsed_error.symbol,
            error_code=parsed_error.code,
            root_cause=resolve_root_cause(parsed_error.symbol, code_directory),
            call_sites=[],
        )
    grouped[parsed_error.symbol].call_sites.append(
        CallSite(parsed_error.file, parsed_error.line)
    )

# 按 call_sites 数降序
sorted_errors = sorted(
    grouped.values(),
    key=lambda e: len(e.call_sites),
    reverse=True,
)
```

### Step 6 — repair prompt 渲染

```markdown
# Type-check failures (mypy attr-defined + call-arg)

下列跨模块 API 不一致必须修复（共 {filtered_count} 处错误，按符号分组取前 {N} 个）。

## 1. Node.node_id (3 处调用)
**根因**：Node 在 hyper_kggen/core/hypergraph.py:13 定义，真实属性是 ['description', 'id', 'name', 'type']；本调用引用了不存在的 .node_id。
**误用位置**：
- hyper_kggen/core/hyperedge_extractor.py:69
- hyper_kggen/core/deduplicator.py:75
- hyper_kggen/evaluation/semantic_matcher.py:121

**修复方向（择一应用，全代码库一致）**：
- 选项 A：把 Node 加上 node_id 属性（或改名 .id → .node_id）
- 选项 B：把上述 3 处调用从 .node_id 改成 .id

---

## 2. add_hyperedge (3 处调用)
**根因**：add_hyperedge 定义在 hyper_kggen/core/hypergraph.py:144，签名 (self, relation_type: str, node_ids: List[str], description: str = "", edge_id: Optional[str] = None)。
**误用位置**：
- hyper_kggen/core/hyperedge_extractor.py:107
- hyper_kggen/core/deduplicator.py:57
- hyper_kggen/core/deduplicator.py:166

**修复方向（择一应用）**：
- 选项 A：改 add_hyperedge 签名接受 Hyperedge 对象
- 选项 B：把调用拆成 (relation_type, node_ids, description)

---

...

**重要**：每个符号只选一个方向。挑完再写代码，避免反复改一边、忘记同步另一边。
```

**截断规则**：
- 符号截顶 8 个（剩余下轮再修，同错断路器兜底）
- 单 symbol 内 call_sites 截顶 5 个，超出尾部加 `"...另 N 处"`

### Step 7 — wire-up 到 orchestration

**位置**：`workflows/agent_orchestration_engine.py`，紧邻 `_quality_with_reproduction_gate`（约 line 559）

**新增 helper**：
```python
def _quality_with_type_check_gate(
    quality_result: Dict[str, Any],
    type_check_result: TypeCheckResult,
) -> Dict[str, Any]:
    merged = dict(quality_result or {})
    merged["type_check_gate"] = {
        "status": type_check_result.status,
        "raw_error_count": type_check_result.raw_error_count,
        "filtered_count": type_check_result.filtered_count,
        "symbol_count": len(type_check_result.errors_by_symbol),
        "duration_seconds": type_check_result.duration_seconds,
    }
    # 关键：不改 merged["status"]，纯附加
    return merged
```

**集成策略**：mypy gate **嵌入现有 repair loop**，不另开循环。现有循环已有 `max_repair_attempts`（外部参数控制，typical 3-5），每次迭代我们额外做 mypy 检查 + 把错误融进 `build_repair_prompt` 输出。这样 LLM 在一次 repair 调用里同时处理 reproduction 问题和跨模块 bug，最省资源。

**改动点**：

1. **`workflows/agent_orchestration_engine.py` line ~2280, 2376 两个 repair loop**：在每次 iteration 计算 `quality_result` 后、`build_repair_prompt` 前，先跑 mypy 并把结果挂上去：

```python
# 现有：
quality_result = _assess_generated_code_with_reproduction_gate(...)

# 新增 wrapper 调用：
tc_result = run_type_check_gate(code_directory)
quality_result = _quality_with_type_check_gate(quality_result, tc_result)

# 现有：判断是否 break，build_repair_prompt，调 agent ...
```

2. **`workflows/repair_planner.build_repair_prompt`**：扩它读 `quality_result["type_check_gate"]`，若 `status == "errors"`，则把 `format_errors_for_repair(...)` 输出附在 prompt 末尾（用一个清晰的 markdown section 分隔，避免跟 reproduction 错误混淆）。这就是把 mypy 信息送达 LLM 的唯一路径。

3. **mypy 专属安全闸（在 type_check_gate.py 内部，跨 iteration 状态）**：

```python
# module 级缓存（per-task；用 code_directory 作 key）
_LAST_ERROR_HASH: dict[str, int] = {}
_INVOCATION_COUNT: dict[str, int] = {}
_FIRST_CALL_TS: dict[str, float] = {}

def run_type_check_gate(code_directory, ...):
    key = str(Path(code_directory).resolve())
    count = _INVOCATION_COUNT.get(key, 0)
    if count >= 3:                                     # 闸 1: mypy 自身 3 次上限
        return TypeCheckResult(status="skipped", ...)
    if key in _FIRST_CALL_TS and time.monotonic() - _FIRST_CALL_TS[key] > 300:
        return TypeCheckResult(status="skipped", ...)  # 闸 2: 墙钟 5 分钟
    _FIRST_CALL_TS.setdefault(key, time.monotonic())
    _INVOCATION_COUNT[key] = count + 1

    # ... 跑 mypy ... 解析 ... 算 error_hash ...

    if error_hash == _LAST_ERROR_HASH.get(key):        # 闸 3: 同错断路器
        return TypeCheckResult(status="success", ...)  # 假装通过，让外层 break
    _LAST_ERROR_HASH[key] = error_hash
    return result
```

并新增 `reset_type_check_state(code_directory)` 供单测和任务开始时清理 module 级缓存。

4. **复用现有 `_repair_made_changes(repair_result)`**（line 479）作 0-file fail-fast 第 4 道闸。这条已在现有 repair loop 里，本期不动。

**安全闸总览（5 道防线）**：
1. 单次 mypy `subprocess` 60s 超时（`subprocess.TimeoutExpired` → soft pass）
2. mypy 调用次数 3 次上限（per code_directory，module 级计数）
3. 墙钟 5 分钟总预算（per code_directory，从首次调用算起）
4. 同错断路器（hash 相同 → 视为已通过，让外层 repair loop 自然 break）
5. 复用现有 `_repair_made_changes` 0-file fail-fast

## 测试策略

新建 `tests/test_type_check_gate.py`。

**单元测试（快、纯函数、不跑 mypy）**：

1. `test_parse_attr_defined_line` — 正则准确
2. `test_parse_call_arg_line`
3. `test_parse_skips_non_error_lines`
4. `test_filter_excludes_arg_type_and_var_annotated`
5. `test_group_by_symbol_aggregates_call_sites`
6. `test_group_by_symbol_sorted_by_call_count_desc`
7. `test_extract_attrs_from_class_init_ast`
8. `test_extract_function_signature_ast`
9. `test_resolve_root_cause_returns_placeholder_when_not_found`
10. `test_format_for_repair_caps_to_8_symbols`
11. `test_format_for_repair_truncates_long_call_sites`
12. `test_format_for_repair_includes_root_cause`

**集成测试（少量、tmp_path 写小项目跑真 mypy，加 `@pytest.mark.heavy`）**：

13. `test_run_gate_returns_success_on_clean_project` — 2 文件洁净小项目
14. `test_run_gate_detects_attr_defined_bug` — 模拟 `Node.id` vs `.node_id`
15. `test_run_gate_detects_call_arg_bug` — 模拟函数签名不匹配
16. `test_run_gate_handles_timeout` — mock subprocess hang
17. `test_run_gate_handles_missing_mypy` — mock FileNotFoundError
18. `test_run_gate_skips_when_code_dir_oversized` — mock 文件大小

**不写**：
- 不写跑完整 PDF 的 end-to-end 测试（防服务器压力）
- 不写大文件 stress test

## 依赖

`requirements.txt` 加：
```
mypy>=1.0
```

实测 mypy 1.19.1（已装），跑 Run4 完整 `hyper_kggen/` 项目 < 5s，无需联网。

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| mypy 自身卡死 | 60s 超时 + soft pass |
| repair loop 无限循环 | 3 轮上限 + 5 分钟墙钟 + 同错断路器 |
| LLM 把代码越改越坏 | 0-file fail-fast 兜底；3 轮上限保证不会失控；同错 hash 触发只覆盖"完全无变化"场景，错误反增的情况依赖 3 轮上限和墙钟兜底 |
| mypy 三方库 stub 噪音 | `--ignore-missing-imports` + 只收 attr-defined / call-arg 两类 |
| 服务器压力（并发任务时） | mypy 单进程、不跟 LLM 调用并发、单任务最多 3 次 mypy invocation |
| Demo 因 mypy fail 显示"失败" | `type_check_gate` 不参与 `final_status` 判定，只附 metadata |

## 验收标准

- [ ] `tests/test_type_check_gate.py` 18 个测试全 pass
- [ ] 在 Run4 的 `paper_20260523-0018_*/generate_code/` 上手动跑 `run_type_check_gate` 能识别本设计正文中提到的 Node.node_id 等真 bug
- [ ] 跑一次同 PDF 验证（fast 模式），观察：
  - mypy 实际触发 repair loop
  - 错误数有下降（部分修复即可，不要求全清）
  - `quality_result["type_check_gate"]` 有数据
  - task `final_status` 仍按现行规则判定（不被 mypy 拉低）
  - 总耗时增量 < 5 分钟

## 不在本设计范围

- 前端展示 type_check_gate 卡片（数据采集到了，前端 demo 时按需做）
- 把 type_check_gate 改为 hard-fail gate（未来如复现质量要求上来再考虑）
- mypy strict mode / 完整类型注解约束
