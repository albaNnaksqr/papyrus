# Web UI 设计文档

**日期**: 2026-05-19
**状态**: 待实现
**范围**: React + Vite 前端，配套后端小幅扩展

---

## 背景

paper2code 已有 HTTP API 层（FastAPI + SSE），本设计为其增加完整的 Web UI 产品页面，使用户能通过浏览器提交论文、实时查看 Pipeline 进度、浏览生成代码，并对照原文批判分析结果。

参考现有 `demo/index.html` 的视觉风格（Plus Jakarta Sans + JetBrains Mono，蓝/白/navy 色彩体系）。

---

## 技术栈

| 层 | 选型 |
|---|---|
| 框架 | React 18 + Vite |
| 样式 | Tailwind CSS + shadcn/ui |
| 路由 | React Router v6 |
| PDF 渲染 | PDF.js（pdfjs-dist） |
| HTTP 客户端 | fetch（无额外库） |
| SSE | 原生 `EventSource` |

---

## 页面路由

| 路由 | 页面 | 说明 |
|---|---|---|
| `/` | Landing | Hero + 产品介绍 + CTA，点击跳 `/app` |
| `/app` | App（无选中任务） | 主面板显示上传区 |
| `/app?task=:id` | App（选中任务） | 主面板显示任务详情，刷新可恢复 |

---

## 整体布局

```
┌─────────────────────────────────────────────┐
│  TopBar: Logo · Paper2Code · [+ 新建任务]    │
├──────────────────┬──────────────────────────┤
│                  │                          │
│  TaskSidebar     │  MainPanel               │
│  ─────────────   │  ─────────────────────── │
│  任务1 ✓         │  [任务标题] [状态徽章]    │
│  任务2 ◉60%      │  [统计: LLM·Token·文件]  │
│  ▓▓▓▓▓▓░░░░     │                          │
│  任务3 ✓         │  Tab: 原文·批判·代码      │
│  任务4 ✓         │       文件 | 语料         │
│                  │       Pipeline           │
│  ─────────────   │                          │
│  4论文  279语料  │  [Tab 内容区]            │
│                  │                          │
└──────────────────┴──────────────────────────┘
```

### TaskSidebar

- 每条任务显示：标题（截断）、状态点（绿=完成 / 蓝脉冲=运行中 / 灰=等待）
- 运行中任务额外显示 mini 进度条
- 底部固定：累计论文数 + 语料条数统计
- 点击任务 → 更新 URL `?task=:id`，主面板切换

### MainPanel — 无选中任务

显示 `UploadPanel`：
- 拖放区 / 点击选择 PDF（接受 `.pdf`，最大 200MB）
- 可选参数：快速模式（`fast`）/ 跳过批判（`no_critique`）开关
- 「开始生成」按钮 → `POST /api/upload` → `POST /api/tasks` → URL 更新到新 task_id

### MainPanel — 选中任务

顶部：任务标题、状态徽章、LLM 调用数/Token/文件数统计。

四个 Tab：

#### Tab 1：原文·批判·代码（任务完成后默认）

三列对照布局：

| 列 | 内容 |
|---|---|
| 原文片段 | 提取的论文原文，关键词 `<mark>` 高亮；带可点击的 `§x.x` 引用标签 |
| 老师傅批判 | 类型（陷阱/假设/质疑）+ 批判文字 |
| 对应代码 | 对应的代码实现片段（`JetBrains Mono`） |

点击 `§x.x` 标签 → 右侧展开 `PdfViewer` 面板，PDF.js 跳转到对应页并文字搜索高亮原文片段。

**数据来源（实现时需确认）**：`paper_refs.jsonl` 只含 `{path, section_ref}`，不含原文片段和批判文字。实现时需查明 Phase 4.5 批判报告的实际输出格式（可能是 `critique_report.md` 或结构化 JSON），并据此解析或新增结构化输出文件（如 `correspondence.jsonl`）。若 Pipeline 尚未输出结构化对照数据，此 Tab 的完整实现需同时改动 Pipeline 输出逻辑。

#### Tab 2：文件

文件树展示 `GET /api/tasks/{id}` 返回的 `artifacts` 列表，点击文件调 `GET /api/tasks/{id}/artifacts/{path}` 展示内容（代码文件用 `<pre>` 渲染，其余触发下载）。

#### Tab 3：语料

显示此任务产出的训练语料统计（LLM 轮次、工具调用数、rich_messages 条数），数据来自 `llm.jsonl` 统计。参考 demo 的语料库页样式。

#### Tab 4：Pipeline（任务运行中默认）

三列实时视图，通过 `EventSource` 连接 `GET /api/tasks/{id}/events` 消费 SSE：

| 列 | 内容 |
|---|---|
| 阶段列表 | Phase 0-10，当前阶段高亮，已完成打勾 |
| 实时日志 | `progress` 事件追加到日志区，自动滚底 |
| 生成文件 | `file_written` 事件触发，文件条目淡入出现 |

全局进度条显示在 TopBar（运行中可见）。

---

## PdfViewer 组件

- 右侧抽屉（宽 380px），点击 `§` 标签展开，再次点击收起
- PDF 来源：`GET /api/papers/{filename}`（后端新增静态路由）
- 使用 `PDFFindController` 执行文字搜索高亮：`findController.executeCommand('find', { query: 片段文字, highlightAll: true })`
- 显示页码导航（上一页/下一页）

---

## 后端补充（最小范围）

在现有 `api/routes/tasks.py` 基础上新增：

### POST /api/upload

```python
# 接收 multipart/form-data，字段名 "file"
# 保存到 papers/{original_filename}（若重名加时间戳后缀）
# 返回
{"path": "papers/lora.pdf", "filename": "lora.pdf"}
```

### GET /api/papers/{filename}

```python
# 从 papers/ 目录 serve 文件（FileResponse）
# 路径穿越保护：同 artifacts 端点处理方式
```

### GET /api/tasks/{id} 响应扩展

在现有响应中增加 `pdf_path` 字段（从任务创建时存储）。

### TaskRecord 扩展

```python
pdf_path: str | None = field(default=None)  # 上传后的 PDF 路径
```

---

## 前端文件结构

```
frontend/
├── index.html
├── vite.config.ts
├── package.json
├── tailwind.config.ts
├── src/
│   ├── main.tsx
│   ├── App.tsx                      # Router: / 和 /app
│   ├── pages/
│   │   ├── Landing.tsx              # Hero + CTA
│   │   └── AppShell.tsx             # 顶栏 + 侧边栏 + 主面板
│   ├── components/
│   │   ├── TaskSidebar.tsx          # 多任务列表 + 底部统计
│   │   ├── UploadPanel.tsx          # 拖放上传 + 参数开关
│   │   ├── task/
│   │   │   ├── TaskDetail.tsx       # Tab 容器 + 标题行
│   │   │   ├── PipelineTab.tsx      # SSE 实时三列
│   │   │   ├── CorrespondenceTab.tsx # 原文·批判·代码
│   │   │   ├── FilesTab.tsx         # 文件树 + 预览
│   │   │   └── CorpusTab.tsx        # 语料统计
│   │   └── PdfViewer.tsx            # PDF.js 右侧抽屉
│   ├── hooks/
│   │   ├── useTasks.ts              # 轮询 GET /api/tasks（2s）
│   │   └── useSSE.ts                # EventSource 封装
│   └── api/
│       └── client.ts                # 所有 API 调用函数
```

---

## 视觉规范（继承自 demo）

```css
/* 字体 */
font-family: 'Plus Jakarta Sans', sans-serif;
code: 'JetBrains Mono', monospace;

/* 色彩 */
--bg:       #f0f6ff;
--surface:  #ffffff;
--blue:     #2563eb;
--navy:     #0f172a;
--slate:    #475569;
--muted:    #94a3b8;
--green:    #10b981;
--amber:    #f59e0b;
--red:      #ef4444;
```

---

## 数据流总览

```
用户上传 PDF
  → POST /api/upload → { path }
  → POST /api/tasks { pdf_path, fast, no_critique }
  → { task_id }
  → URL: /app?task={id}
  → TaskDetail 渲染，Pipeline Tab 激活
  → EventSource /api/tasks/{id}/events
      progress → 进度条 + 日志追加
      file_written → 文件列表追加
      done → 切换到 CorrespondenceTab
      error → 显示错误状态

用户点击 §ref
  → PdfViewer 展开
  → PDF.js 加载 /api/papers/{filename}
  → findController 搜索高亮原文片段
```

---

## 错误处理

| 场景 | 处理 |
|---|---|
| 上传非 PDF | 前端文件类型校验，拒绝并提示 |
| 上传超 200MB | 前端大小校验 |
| SSE 断线 | `EventSource` 自动重连，携带 `Last-Event-ID` |
| 任务 error 状态 | Pipeline Tab 显示错误信息，终止日志追加 |
| PDF.js 加载失败 | PdfViewer 显示「无法加载 PDF」提示 |

---

## 多用户升级路径

前端本身无状态，后端升级（任务队列、数据库、认证）时前端接口不变，仅需更新 `api/client.ts` 的 base URL 和可能的 Auth header。
