# 事件推送机制设计文档

**日期**: 2026-05-18  
**状态**: 待实现  
**范围**: 本地单机，Web UI 触发 Pipeline，SSE 实时推送进度

---

## 背景

paper2code 当前是纯 CLI 工具（`python paper2code.py --pdf ...`），无 HTTP API，前端无法触发任务或获取实时进度。本设计为其增加一套轻量 HTTP 服务层，支持 Web UI 提交任务并通过 SSE 实时接收 Pipeline 进度事件。

**约束**：
- 初期仅支持本地单机（一次只跑一个任务）
- 接口设计需为后续多用户部署预留升级路径，但不提前实现
- CLI 模式（`paper2code.py`）保持不变，两种使用方式并存

---

## 架构概览

**方案**：FastAPI + asyncio 同进程（方案 A）

```
Browser → POST /api/tasks
            ↓ asyncio.create_task()
FastAPI Server ←→ Pipeline (same process)
            ↓ asyncio.Queue → SSE stream
Browser ← GET /api/tasks/{id}/events
```

### 新增文件结构

```
paper2code/
├── api/
│   ├── server.py          # FastAPI app + uvicorn 启动
│   ├── task_manager.py    # 任务注册表，持有 asyncio.Queue
│   └── routes/
│       ├── tasks.py       # POST/GET /api/tasks, GET /api/tasks/{id}
│       └── events.py      # GET /api/tasks/{id}/events (SSE)
└── serve.py               # HTTP 服务入口（python serve.py）
```

`paper2code.py` 不做任何改动。

### 组件职责

| 组件 | 职责 | 状态存储 |
|---|---|---|
| `TaskManager` | 任务生命周期管理，持有 `asyncio.Queue` | 内存 dict + `events.jsonl` |
| `progress_callback` | Pipeline → TaskManager 的唯一事件接口 | 无状态，纯推送 |
| SSE endpoint | 从 Queue 读事件，格式化为 SSE 帧 | 无状态，断线重连读文件 |
| `events.jsonl` | 持久化事件日志 | `output/tasks/{id}/logs/events.jsonl` |

---

## API 接口

### 端点一览

| 端点 | 说明 |
|---|---|
| `POST /api/tasks` | 创建并启动任务，返回 task_id |
| `GET /api/tasks` | 列出所有任务（含历史，从 output/ 扫描） |
| `GET /api/tasks/{id}` | 查询单个任务状态和产出文件列表 |
| `GET /api/tasks/{id}/events` | SSE 流，实时推送 Pipeline 进度事件 |
| `GET /api/tasks/{id}/artifacts/{path}` | 读取任务产出文件（path 相对于 `output/tasks/{id}/`） |

### POST /api/tasks

请求体：
```json
{
  "pdf_path": "papers/xxx.pdf",
  "fast": false,
  "no_critique": false
}
```

响应：
```json
{
  "task_id": "paper_87d8010e",
  "status": "pending",
  "created_at": "2026-05-18T10:00:00Z"
}
```

### GET /api/tasks/{id}/events — SSE 事件格式

Content-Type: `text/event-stream`

每条推送：
```
data: {"type": "progress", "pct": 58, "message": "🔍 老师傅批判中...", "phase": "critique", "ts": "2026-05-18T10:02:31Z"}

data: {"type": "file_written", "path": "src/model.py", "phase": "impl", "section_ref": "§4.1"}

data: {"type": "done", "pct": 100, "summary": "..."}

data: {"type": "error", "message": "...", "phase": "planning"}
```

### SSE 事件类型

| type | 触发时机 | 关键字段 |
|---|---|---|
| `progress` | 每次 `progress_callback` 触发 | `pct`(0-100), `message`, `phase` |
| `file_written` | `progress_callback` 触发时，TaskManager 检测 `paper_refs.jsonl` 新增条目 | `path`, `phase`, `section_ref`(可选) |
| `done` | Pipeline 成功结束 | `pct=100`, `summary` |
| `error` | Pipeline 抛出未捕获异常 | `message`, `phase` |

> `file_written` 的实现说明：MCP 服务器（`code_implementation_server.py`）是独立子进程，无法直接写 asyncio Queue。替代方案：每次 `progress_callback` 触发时，`make_callback` 额外检查 `paper_refs.jsonl` 自上次以来的新增行，为每一行生成一条 `file_written` 事件推入队列。无需改动 MCP 服务器。

**断线重连**：SSE 标准 `Last-Event-ID` header，服务器从 `events.jsonl` 补送历史后切回实时队列。

---

## 核心实现逻辑

### TaskRecord 数据结构

```python
@dataclass
class TaskRecord:
    task_id: str
    status: str          # pending | running | done | error | interrupted
    created_at: datetime
    queue: asyncio.Queue # 事件队列
    output_dir: Path

class TaskManager:
    _tasks: dict[str, TaskRecord]
    # 单例，FastAPI lifespan 里初始化，启动时扫 output/ 恢复历史任务
```

### progress_callback 挂钩

```python
def make_callback(record: TaskRecord):
    def callback(pct: int, msg: str, err=None):
        event = {
            "type": "error" if err else "progress",
            "pct": pct,
            "message": msg,
            "ts": utcnow(),
        }
        record.queue.put_nowait(event)   # 非阻塞，同步上下文安全
        append_event(record, event)       # 持久化到 events.jsonl
    return callback
```

> `put_nowait()` 而非 `await queue.put()`，因为 Pipeline 深处的 `progress_callback` 是同步调用。

### Pipeline 启动

```python
async def start_task(pdf_path, fast, no_critique) -> str:
    record = TaskManager.create(pdf_path)
    cb = make_callback(record)

    async def _run():
        try:
            record.status = "running"
            await execute_multi_agent_research_pipeline(
                input_source=pdf_path,
                progress_callback=cb,      # ← 唯一接入点
                logger=logger,
                enable_indexing=not fast,
            )
            record.status = "done"
            cb(100, "Pipeline completed")
        except Exception as e:
            record.status = "error"
            cb(0, str(e), err=True)

    asyncio.create_task(_run())
    return record.task_id
```

### SSE 生成器

```python
async def event_stream(record: TaskRecord, last_event_id: str | None = None):
    # 1. 断线重连：先从文件补历史
    if last_event_id:
        async for e in replay_from_file(record, after=last_event_id):
            yield format_sse(e)

    # 2. 实时：从 Queue 读，25s 超时发心跳保活
    while record.status not in ("done", "error"):
        try:
            event = await asyncio.wait_for(record.queue.get(), timeout=25)
            yield format_sse(event)
        except asyncio.TimeoutError:
            yield ": heartbeat\n\n"

    # 3. 任务结束，推最后一条并关流
    yield format_sse({"type": record.status})
```

---

## 错误处理

| 场景 | 处理方式 |
|---|---|
| Pipeline 内部异常 | `_run()` 的 `except` 捕获，推 `error` 事件，status → "error"，SSE 流正常关闭 |
| 浏览器断线 | SSE 生成器被取消，Pipeline 继续跑，事件持续写 `events.jsonl`；重连从 `Last-Event-ID` 补送 |
| 服务重启 | `TaskManager` 启动时扫 `output/tasks/` 恢复历史，正在运行的任务标为 `interrupted` |
| 重复提交同一 PDF | 允许，生成新 `task_id` |

---

## 部署

```bash
# HTTP 服务模式（新）
python serve.py
# 默认 0.0.0.0:8000，启动 FastAPI + uvicorn，扫描恢复历史任务

# CLI 模式（不变）
python paper2code.py --pdf papers/xxx.pdf
```

新增依赖：`fastapi`、`uvicorn[standard]`、`python-multipart`

---

## 升级多用户的变更范围

升级时只需替换以下三处，**SSE 端点、事件格式、`events.jsonl` 结构完全不变**：

| 现在（本地单机） | 未来（多用户） |
|---|---|
| `asyncio.create_task()` | `arq.enqueue()` / `celery.delay()` |
| 内存 dict | SQLite / PostgreSQL |
| 无认证 | JWT / API Key 中间件 |
