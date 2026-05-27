# ArtifactContract 重构 — project_root 模型 设计文档

**日期**：2026-05-24
**作者**：shiqirui（用户） + Claude（设计协作）
**Status**：approved, ready for plan

## 背景

Run1-Run19 累积过程中，`ArtifactContract.source_root` 这个字段反复成为修补对象。从 `b02cb75` 到 `ddabf82` 共 **7 个 commit** 都在围绕"如何放宽 source_root 检查以匹配 agent 的合理行为"打补丁：

| Commit | 加了什么例外 / 放宽 |
|---|---|
| `b02cb75` Plan A 阶段1 | `_source_root_consistent` ancestor/descendant 模糊匹配 |
| `bc004b1` Plan A 阶段2 | smoke 命令路径重写 + README 路径模糊匹配 |
| `3415530` 入口兜底 | 找不到 main.py 时用 run_*.py |
| `2a6b742` per-write unlink | reject 时删文件 |
| `e9cb01b` 末尾扫 + YAML detect | 末尾再扫一遍，加 YAML 解析 |
| `ddabf82` 包根接受 | accept 任何 pkg/* 子目录 |

**根因**：`source_root` 模型本身错了。

真实 Python 项目长这样：
```
pkg/
├── main.py                # entrypoint
├── src/  (or core/)       # 源代码
├── experiments/           # 实验脚本
├── tests/                 # 测试
├── configs/               # 配置
```

`source_root` 这个字段强行抠出"代码住哪"做为契约门槛。每次发现真实项目里有 `experiments/`、`analysis/`、`configs/` 这类同级目录就加例外，最后例外列表本身变成 bug 来源。

## 目标

把 `ArtifactContract.source_root` 替换为 `project_root`，重新定义校验规则：**"代码必须在 project_root 下"** 而不是 **"代码必须在 source_root 下"**。

具体目标：
- 删除 `_source_root_consistent`、`within_package_root` 派生、entrypoint exact 例外、`scripts/` 例外
- 用 `_top_level_py_roots` 取代 `_active_source_roots`
- 让 LoRA / hyper_kggen / Attention 等真实论文 plan 都能干净通过 contract 检查

## 非目标

- 不改 `package_name` 字段语义（虽然跟 project_root 重叠，保留向后语义）
- 不修改 mypy gate、Plan 规模 cap 等其它本周期已落地的修复
- 不调整 frontend metadata schema（无前端消费者）

## 关键设计决策（用户确认）

| 维度 | 决定 |
|---|---|
| 字段命名 | `source_root` → `project_root`（clean break，无 alias） |
| allowlist | 保留 `tests/` + `validate_paper_claims.py`；**删 `scripts/`** |
| multi-root 规则 | 重命名为 "multiple project roots"，仅计 top-level 含 .py 的目录（除 tests/） |
| package_name 字段 | 保留，default = project_root（None 表 "."） |
| metadata JSON | 同步 `"source_root"` → `"project_root"`（确认无前端消费者） |

## 架构

### 模块边界

```
workflows/
├── artifact_contract.py          ← 重写约 40% 代码
├── code_acceptance.py            ← accept + prune 规则同步
├── smoke_tests.py                ← 文案 / 字段名同步
├── implementation_quality.py     ← 文案 / 字段名同步（保持本地 _detect_source_roots）
├── repair_planner.py             ← 文案 source root → project root
└── agent_orchestration_engine.py ← wire-up 字段名同步
```

### 数据模型

```python
@dataclass(frozen=True)
class ArtifactContract:
    project_root: str                          # "pkg" or "." (扁平)
    entrypoint: str                            # 任意 path
    package_name: str | None = None            # default = project_root (None when ".")
    smoke_commands: list[str] = field(default_factory=list)
    
    def to_prompt_block(self) -> str:
        """Authoritative project-layout block injected into implement prompt.
        Updated: 'source root' wording → 'project root'."""
        ...
```

**clean break**：`source_root` 字段移除，无 deprecated alias。已确认：
- 8 处非测试引用全部在 `workflows/` 内部（同步修改）
- 0 处前端引用（frontend 不消费 metadata.source_root）
- 56 处测试引用（机械替换）

## 详细设计

### Step 1 — accept_written_file 新规则

```python
def accept_written_file(code_directory, file_path, contract):
    root = Path(code_directory).resolve()
    full_path = (root / file_path).resolve()
    
    # ① path escape check
    try:
        full_path.relative_to(root)
    except ValueError:
        return reject("file path escapes code directory")
    
    # ② existence check
    if not full_path.is_file():
        return reject("file does not exist")
    
    rel = full_path.relative_to(root).as_posix()
    
    # ③ syntax / empty check（__init__ 跳过 empty）
    if rel.endswith(".py") and full_path.name != "__init__.py":
        if not full_path.read_text(encoding="utf-8").strip():
            return reject("empty implementation file")
        try:
            ast.parse(full_path.read_text(encoding="utf-8"), filename=rel)
        except SyntaxError as exc:
            return reject(f"syntax error: {exc}")
    
    # ④ project root 归属（核心简化）
    pr = contract.project_root.rstrip("/")
    in_project = (pr == "." or rel.startswith(pr + "/"))
    allowed = (
        in_project
        or rel.startswith("tests/")
        or rel == "validate_paper_claims.py"
    )
    if rel.endswith(".py") and not allowed:
        try:
            full_path.unlink()
        except OSError:
            pass
        return reject(f"file outside project root: {rel}")
    
    return accepted
```

**消失的逻辑**：
- `within_source_root` 派生
- `within_package_root` 派生（package-root 兜底）
- `entrypoint == rel` 例外
- `scripts/` 例外

**保留**：unlink-on-reject 行为（Run17/18 验证有效）

### Step 2 — prune_out_of_root_py_files 同步

跟 acceptance 用同一套规则：

```python
def prune_out_of_root_py_files(code_directory, contract):
    root = Path(code_directory).resolve()
    if not root.exists():
        return {"pruned": []}
    
    pr = contract.project_root.rstrip("/")
    pruned: list[str] = []
    
    for py_file in root.rglob("*.py"):
        if any(part in _PRUNE_SKIP_PARTS for part in py_file.parts):
            continue
        if not py_file.is_file():
            continue
        rel = py_file.relative_to(root).as_posix()
        
        in_project = (pr == "." or rel.startswith(pr + "/"))
        allowed = (
            in_project
            or rel.startswith("tests/")
            or rel == "validate_paper_claims.py"
            or py_file.name == "__init__.py"
        )
        if allowed:
            continue
        try:
            py_file.unlink()
            pruned.append(rel)
        except OSError:
            pass
    
    return {"pruned": sorted(pruned)}
```

### Step 3 — validate_generated_tree_against_contract 新规则

```python
def validate_generated_tree_against_contract(code_directory, contract):
    root = Path(code_directory)
    failures: list[str] = []
    
    # ① 单 project root：top-level 含 .py 的目录只能有一个
    top_level_roots = _top_level_py_roots(root)
    
    if len(top_level_roots) > 1:
        failures.append(f"multiple project roots: {sorted(top_level_roots)}")
    
    # ② project_root 实际存在
    pr = contract.project_root.rstrip("/")
    if pr == ".":
        if "." not in top_level_roots and top_level_roots:
            failures.append(
                f"contract project_root '.' but disk roots are: {sorted(top_level_roots)}"
            )
    elif pr not in top_level_roots:
        failures.append(
            f"contract project_root '{pr}' not found on disk; have: {sorted(top_level_roots)}"
        )
    
    # ③ entrypoint 找得到 + 非空（复用 find_file_under_root）
    entrypoint = find_file_under_root(root, contract.entrypoint)
    if entrypoint is None:
        failures.append(f"missing entrypoint: {contract.entrypoint}")
    elif not entrypoint.read_text(encoding="utf-8").strip():
        failures.append(f"empty entrypoint: {contract.entrypoint}")
    
    return {
        "status": "error" if failures else "success",
        "failures": failures,
        "project_roots": sorted(top_level_roots),
        "contract": {
            "project_root": contract.project_root,
            "entrypoint": contract.entrypoint,
            "package_name": contract.package_name,
            "smoke_commands": contract.smoke_commands,
        },
    }
```

**新 helper**：
```python
# 跟 _NON_PACKAGE_ROOT_DIRS 不同：那个用于 detect_source_layout 识别
# 包装结构；这个用于 multi-root 校验，只豁免 tests/docs/ 这种
# 公认的"非项目源"目录。data/ config/ 等可能含真 .py，不豁免。
_NON_PROJECT_TOP_DIRS = {"tests", "docs"}

def _top_level_py_roots(root: Path) -> set[str]:
    """Top-level entries containing .py files (excluding tests/, caches)."""
    roots: set[str] = set()
    if not root.exists():
        return roots
    # 顶层 .py 文件 → root "."
    if any(
        c.is_file() and c.suffix == ".py"
        and c.name not in _ROOT_SUPPORT_PY_FILES
        for c in root.iterdir()
    ):
        roots.add(".")
    # 顶层目录递归含 .py
    for child in root.iterdir():
        if not child.is_dir():
            continue
        if child.name in _NON_PROJECT_TOP_DIRS:
            continue
        if any(child.rglob("*.py")):
            roots.add(child.name)
    return roots
```

**消失的逻辑**：
- `_active_source_roots`（被 `_top_level_py_roots` 取代）
- `_source_root_consistent`（不需要 ancestor/descendant 模糊匹配）
- `_resolve_entrypoint`（直接用 `find_file_under_root`）

### Step 4 — build_contract_from_plan 简化

```python
def build_contract_from_plan(plan_text):
    text = plan_text or ""
    paths = sorted(set(_PY_PATH_RE.findall(text)))
    
    # ① project_root 从 plan tree 顶推（YAML-aware 已在 e9cb01b 修过）
    package_root, _ = _detect_source_layout(text)
    project_root = package_root if package_root else "."
    
    # ② package_name default 到 project_root
    package_match = _PACKAGE_RE.search(text)
    if package_match:
        package_name = package_match.group(1)
    else:
        package_name = project_root if project_root != "." else None
    
    # ③ entrypoint
    entry_match = _ENTRY_RE.search(text)
    if entry_match:
        entrypoint = entry_match.group(1)
    else:
        entrypoint = _guess_entrypoint_from_paths(paths) or "main.py"
    
    # ④ entrypoint 规范化到 project_root 下
    if project_root != "." and not entrypoint.startswith(project_root + "/"):
        entrypoint = f"{project_root}/{entrypoint.lstrip('./')}"
    
    # ⑤ smoke commands
    smoke_commands = []
    for match in _SMOKE_RE.finditer(text):
        cmd = match.group(1).strip()
        if cmd and not is_blocked_smoke_command(cmd):
            smoke_commands.append(cmd)
    if not smoke_commands:
        smoke_commands = [f"python {entrypoint} --help"]
    
    return ArtifactContract(
        project_root=project_root,
        entrypoint=entrypoint,
        package_name=package_name,
        smoke_commands=smoke_commands,
    )
```

**消失**：
- `source_root = "src" if "src" in roots else (roots[0] if roots else "src")` 那行
- `_source_root_for(path)` helper（无 caller）
- 复杂的 source_subdir 派生分支

**保留**：
- `_detect_source_layout`（YAML-aware）
- `_guess_entrypoint_from_paths`
- `_ENTRY_RE`、`_SMOKE_RE`、`_PACKAGE_RE`

### Step 5 — 联动修改

| 文件 | 改动 |
|---|---|
| `smoke_tests.py` | `_rewrite_smoke_command` 不变；文案 source root → project root |
| `implementation_quality.py` | `_detect_source_roots` 行为不变（独立函数）；文案同步 |
| `repair_planner.py` | "source root conflict" → "project root conflict" |
| `agent_orchestration_engine.py` | `_quality_with_*` helpers wire-up 字段名同步；metadata 出 `"project_root"` |

## 测试策略

新建/修改：

**Mechanical rename**（~50 个测试）：
- `tests/test_artifact_contract.py`：`source_root=` → `project_root=`，assertion 同步
- `tests/test_code_acceptance.py`：同上
- `tests/test_smoke_tests.py`：同上
- `tests/test_reproduction_gate.py`：同上

**新增测试**：

`tests/test_artifact_contract.py`:
- `test_validate_rejects_multiple_project_roots`
- `test_validate_passes_when_project_root_matches`
- `test_validate_rejects_when_project_root_not_on_disk`
- `test_top_level_py_roots_excludes_tests_dir`
- `test_top_level_py_roots_excludes_caches`
- `test_build_contract_sets_package_name_from_project_root`
- `test_build_contract_normalizes_entrypoint_into_project_root`

`tests/test_code_acceptance.py`:
- `test_acceptance_no_longer_allowlists_scripts_dir`
- `test_acceptance_accepts_any_py_under_project_root`

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| 测试机械替换出错 | 全套测试一次跑完确认 |
| 字段名同步遗漏（任务 metadata 残留 source_root） | `grep -r "source_root"` 最后扫一遍 |
| `scripts/` 删除引发回归 | 既往 20 个 Run 无 scripts/ 真实使用 |
| 隐藏 caller 没找到 | scan 已确认 8 处内部 + 0 处 frontend |
| 重构破坏 mypy gate / Plan 规模 cap | 独立模块，无字段耦合，测试覆盖 |

## 验收标准

- [ ] 211 → ~210 测试全 pass（机械替换 + 新增 + 部分删除）
- [ ] `grep -r "source_root"` 在非历史文档下返回 0 处
- [ ] 跑一次 Run 验证 LoRA 任务能完成所有 quality gate（特别关注：entrypoint 找得到、无 multiple project roots、no false reject）

## 不在本设计范围

- mypy gate 调整
- Plan 规模 cap 调整
- Repair 精准化（只改 buggy 文件）
- LLM-as-judge 论文 KPI 检测
- 前端展示 project_root metadata（已有数据，前端按需消费）
