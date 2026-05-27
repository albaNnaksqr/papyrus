import { useState, useEffect, useMemo } from 'react'
import { Bot, User, Wrench, ChevronDown, ChevronRight, Settings } from 'lucide-react'
import { getArtifactText, TaskDetail } from '../../api/client'

interface Props {
  detail: TaskDetail
}

interface ToolCall {
  name: string
  arguments?: Record<string, unknown>
}

interface ChatMessage {
  role: string
  content: string
  // assistant messages may carry tool_calls
  tool_calls?: ToolCall[]
  tool_name?: string
}

interface LlmCall {
  timestamp: string
  phase: string
  model: string
  duration_ms: number
  status: string
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  request_preview: ChatMessage[]
  response_preview: string
  tool_calls: ToolCall[]
}

interface RichContentBlock {
  type: string
  text?: string
  name?: string
  input?: Record<string, unknown>
  tool_name?: string
  content?: string
}

interface TrajectoryMessage {
  role: string
  content: string | RichContentBlock[]
  tool_calls?: unknown[]
}

interface TrajectorySegment {
  segment_id: number
  timestamp?: string
  messages_count?: number
  rich_messages_count?: number
  files_implemented?: string[]
  messages?: TrajectoryMessage[]
  rich_messages?: TrajectoryMessage[]
}

interface CorpusData {
  calls: LlmCall[]
  segments: TrajectorySegment[]
}

interface CorpusStats {
  llm_turns: number
  tool_calls: number
  total_tokens: number
}

const PHASE_LABEL: Record<string, string> = {
  planning: '规划',
  critique: '批判',
  implementation: '实现',
  validation: '验证',
}

const PHASE_COLOR: Record<string, string> = {
  planning: 'var(--blue)',
  critique: '#d97706',
  implementation: 'var(--green)',
  validation: '#6366f1',
}

async function loadLlmCalls(taskId: string, artifacts: string[]): Promise<LlmCall[]> {
  const llmPath = artifacts.find(a => a === 'logs/llm.jsonl')
  if (!llmPath) return []
  const text = await getArtifactText(taskId, llmPath)
  return text.trim().split('\n').filter(Boolean).map(line => {
    try { return JSON.parse(line) as LlmCall } catch { return null }
  }).filter(Boolean) as LlmCall[]
}

async function loadTrajectorySegments(taskId: string, artifacts: string[]): Promise<TrajectorySegment[]> {
  const trajectoryPath = artifacts.find(a => a === 'trajectory/segments.jsonl')
  if (!trajectoryPath) return []
  const text = await getArtifactText(taskId, trajectoryPath)
  return text.trim().split('\n').filter(Boolean).map(line => {
    try { return JSON.parse(line) as TrajectorySegment } catch { return null }
  }).filter(Boolean) as TrajectorySegment[]
}

async function loadCorpusData(taskId: string, artifacts: string[]): Promise<CorpusData> {
  const [calls, segments] = await Promise.all([
    loadLlmCalls(taskId, artifacts).catch(() => []),
    loadTrajectorySegments(taskId, artifacts).catch(() => []),
  ])
  return { calls, segments }
}

function parseMaybeJsonObject(value: unknown): Record<string, unknown> | undefined {
  if (!value) return undefined
  if (typeof value === 'object' && !Array.isArray(value)) return value as Record<string, unknown>
  if (typeof value !== 'string') return undefined
  try {
    const parsed = JSON.parse(value)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>
    }
  } catch {
    return undefined
  }
  return undefined
}

function normalizeToolCall(raw: unknown): ToolCall | null {
  if (!raw || typeof raw !== 'object') return null
  const obj = raw as {
    name?: string
    input?: unknown
    arguments?: unknown
    function?: { name?: string; arguments?: unknown }
  }
  const name = obj.name ?? obj.function?.name
  if (!name) return null
  const args = parseMaybeJsonObject(obj.input)
    ?? parseMaybeJsonObject(obj.arguments)
    ?? parseMaybeJsonObject(obj.function?.arguments)
  return { name, arguments: args }
}

function computeStats(calls: LlmCall[]): CorpusStats {
  let toolCalls = 0
  let totalTokens = 0
  for (const c of calls) {
    toolCalls += c.tool_calls?.length ?? 0
    totalTokens += c.total_tokens ?? 0
  }
  return { llm_turns: calls.length, tool_calls: toolCalls, total_tokens: totalTokens }
}

function StatCards({ stats }: { stats: CorpusStats }) {
  const cards = [
    { label: 'LLM 调用', value: String(stats.llm_turns), color: 'var(--blue)' },
    { label: '工具调用', value: String(stats.tool_calls), color: 'var(--green)' },
    { label: '累计 Token', value: stats.total_tokens > 1000 ? `${(stats.total_tokens / 1000).toFixed(1)}K` : String(stats.total_tokens), color: 'var(--navy)' },
  ]
  return (
    <div className="grid grid-cols-3 gap-3 mb-4">
      {cards.map(c => (
        <div key={c.label} className="rounded-lg shadow-sm px-4 py-3"
             style={{ background: 'var(--surface)', border: '1px solid var(--border-lt)' }}>
          <div className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--muted)' }}>
            {c.label}
          </div>
          <div className="text-xl font-extrabold mt-0.5" style={{ color: c.color }}>{c.value}</div>
        </div>
      ))}
    </div>
  )
}

const LONG_CONTENT_THRESHOLD = 600

function ExpandableContent({ content, mono = false }: { content: string; mono?: boolean }) {
  const [expanded, setExpanded] = useState(false)
  const trimmed = content.trim()
  const isLong = trimmed.length > LONG_CONTENT_THRESHOLD
  const shown = expanded || !isLong ? trimmed : trimmed.slice(0, LONG_CONTENT_THRESHOLD) + '…'

  return (
    <div>
      <div
        className={`text-xs leading-relaxed whitespace-pre-wrap break-words ${mono ? 'mono' : ''}`}
        style={{ color: 'inherit' }}>
        {shown}
      </div>
      {isLong && (
        <button onClick={() => setExpanded(e => !e)}
                className="mt-1.5 text-[10px] font-semibold inline-flex items-center gap-0.5 hover:underline"
                style={{ color: 'var(--blue)' }}>
          {expanded ? <>收起 <ChevronDown size={10} className="rotate-180" /></> : <>展开全部（{trimmed.length} 字符） <ChevronDown size={10} /></>}
        </button>
      )}
    </div>
  )
}

function SystemBubble({ content, idx }: { content: string; idx: number }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div className="flex flex-col items-center gap-2">
      <button onClick={() => setExpanded(e => !e)}
              className="inline-flex items-center gap-1.5 text-[10px] uppercase tracking-wider px-3 py-1 rounded-full transition-colors"
              style={{
                background: expanded ? 'var(--border-lt)' : 'transparent',
                color: 'var(--muted)',
                border: '1px dashed var(--border-lt)',
              }}>
        <Settings size={10} />
        <span>System Prompt #{idx + 1} · {content.length} 字符</span>
        {expanded ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
      </button>
      {expanded && (
        <div className="w-full max-w-3xl rounded-lg p-3"
             style={{ background: '#f1f5f9', border: '1px solid var(--border-lt)' }}>
          <pre className="text-[11px] mono leading-relaxed whitespace-pre-wrap break-words"
               style={{ color: 'var(--slate)' }}>
            {content}
          </pre>
        </div>
      )}
    </div>
  )
}

function ToolCallChips({ calls }: { calls: ToolCall[] }) {
  if (!calls || calls.length === 0) return null
  return (
    <div className="mt-2 space-y-2">
      {calls.map((tc, i) => (
        <div key={i} className="rounded-lg px-3 py-2 text-[11px]"
             style={{ background: '#eff6ff', border: '1px solid #bfdbfe', borderLeft: '3px solid var(--blue)' }}>
          <div className="flex items-center gap-1.5 font-semibold" style={{ color: 'var(--blue)' }}>
            <Wrench size={12} />
            <span className="mono">工具调用 · {tc.name}</span>
          </div>
          {tc.arguments && Object.keys(tc.arguments).length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {Object.entries(tc.arguments).slice(0, 6).map(([k, v]) => (
                <span key={k} className="rounded px-1.5 py-0.5 mono"
                      style={{ background: '#dbeafe', color: '#1e3a8a' }}>
                  {k}: {formatToolValue(v)}
                </span>
              ))}
              {Object.keys(tc.arguments).length > 6 && (
                <span className="rounded px-1.5 py-0.5 mono" style={{ background: '#dbeafe', color: '#1e3a8a' }}>
                  +{Object.keys(tc.arguments).length - 6}
                </span>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function formatToolValue(value: unknown): string {
  const raw = typeof value === 'string' ? value : JSON.stringify(value)
  if (!raw) return ''
  return raw.length > 56 ? `${raw.slice(0, 56)}…` : raw
}

function summarizeToolResult(content: string): {
  status?: string
  title: string
  fields: { label: string; value: string }[]
  pretty: string
} {
  try {
    const parsed = JSON.parse(content) as Record<string, unknown>
    const status = typeof parsed.status === 'string' ? parsed.status : undefined
    const message = typeof parsed.message === 'string' ? parsed.message : undefined
    const error = typeof parsed.error === 'string' ? parsed.error : undefined
    const fields = [
      ['file_path', parsed.file_path],
      ['path', parsed.path],
      ['total_lines', parsed.total_lines],
      ['lines_written', parsed.lines_written],
      ['size_bytes', parsed.size_bytes],
    ].flatMap(([label, value]) => {
      if (value == null) return []
      return [{ label: String(label), value: formatToolValue(value) }]
    })
    return {
      status,
      title: message ?? error ?? status ?? '工具执行结果',
      fields,
      pretty: JSON.stringify(parsed, null, 2),
    }
  } catch {
    const title = content.trim().split('\n').find(Boolean) ?? '工具执行结果'
    return {
      title: title.length > 120 ? `${title.slice(0, 120)}…` : title,
      fields: [],
      pretty: content,
    }
  }
}

function toolStatusStyle(status?: string) {
  if (status === 'success' || status === 'ok') {
    return { bg: '#ecfdf5', border: '#bbf7d0', accent: 'var(--green)', text: '#166534' }
  }
  if (status === 'error' || status === 'failed') {
    return { bg: '#fef2f2', border: '#fecaca', accent: 'var(--red)', text: '#991b1b' }
  }
  return { bg: '#f8fafc', border: 'var(--border-lt)', accent: 'var(--muted)', text: 'var(--slate)' }
}

function AssistantBubble({ msg }: { msg: ChatMessage }) {
  const empty = !msg.content?.trim()
  return (
    <div className="flex justify-start items-start gap-2">
      <div className="shrink-0 w-7 h-7 rounded-full flex items-center justify-center mt-1"
           style={{ background: 'var(--blue-lt)', color: 'var(--blue)' }}>
        <Bot size={14} />
      </div>
      <div className="max-w-[78%] flex flex-col gap-0.5">
        <div className="text-[10px] font-semibold" style={{ color: 'var(--muted)' }}>模型回复</div>
        <div className="rounded-lg rounded-tl-sm px-3 py-2 shadow-sm"
             style={{ background: 'var(--surface)', border: '1px solid var(--border-lt)', color: 'var(--navy)' }}>
          {empty ? (
            <p className="text-xs italic" style={{ color: 'var(--muted)' }}>(无文本回复，直接调用了工具)</p>
          ) : (
            <ExpandableContent content={msg.content} />
          )}
          <ToolCallChips calls={msg.tool_calls ?? []} />
        </div>
      </div>
    </div>
  )
}

function UserBubble({ msg }: { msg: ChatMessage }) {
  return (
    <div className="flex justify-end items-start gap-2">
      <div className="max-w-[78%] flex flex-col gap-0.5 items-end">
        <div className="text-[10px] font-semibold" style={{ color: 'var(--muted)' }}>用户请求</div>
        <div className="rounded-lg rounded-tr-sm px-3 py-2 shadow-sm"
             style={{ background: 'var(--blue-lt)', border: '1px solid var(--blue)', color: 'var(--navy)' }}>
          <ExpandableContent content={msg.content} />
        </div>
      </div>
      <div className="shrink-0 w-7 h-7 rounded-full flex items-center justify-center mt-1"
           style={{ background: 'var(--blue)', color: '#fff' }}>
        <User size={14} />
      </div>
    </div>
  )
}

function ToolBubble({ msg }: { msg: ChatMessage }) {
  const [expanded, setExpanded] = useState(false)
  const summary = summarizeToolResult(msg.content)
  const tone = toolStatusStyle(summary.status)
  return (
    <div className="flex justify-start items-start gap-2">
      <div className="shrink-0 w-7 h-7 rounded-full flex items-center justify-center mt-1"
           style={{ background: tone.bg, color: tone.accent, border: `1px solid ${tone.border}` }}>
        <Wrench size={14} />
      </div>
      <div className="max-w-[78%] flex flex-col gap-0.5">
        <div className="text-[10px] font-semibold" style={{ color: 'var(--muted)' }}>
          工具回复{msg.tool_name ? ` · ${msg.tool_name}` : ''}
        </div>
        <div className="rounded-lg rounded-tl-sm px-3 py-2 shadow-sm overflow-hidden text-xs"
             style={{ background: tone.bg, border: `1px solid ${tone.border}`, borderLeft: `3px solid ${tone.accent}`, color: 'var(--navy)' }}>
          <div className="flex items-center gap-2">
            {summary.status && (
              <span className="rounded-full px-2 py-0.5 text-[10px] font-bold uppercase"
                    style={{ background: '#fff', color: tone.text, border: `1px solid ${tone.border}` }}>
                {summary.status}
              </span>
            )}
            <span className="font-medium leading-relaxed">{summary.title}</span>
          </div>
          {summary.fields.length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {summary.fields.map(field => (
                <span key={field.label} className="rounded px-1.5 py-0.5 mono text-[11px]"
                      style={{ background: '#fff', color: 'var(--slate)', border: `1px solid ${tone.border}` }}>
                  {field.label}: {field.value}
                </span>
              ))}
            </div>
          )}
          <button onClick={() => setExpanded(e => !e)}
                  className="mt-2 text-[10px] font-semibold inline-flex items-center gap-0.5 hover:underline"
                  style={{ color: tone.text }}>
            {expanded ? <>收起完整内容 <ChevronDown size={10} className="rotate-180" /></> : <>查看完整内容 <ChevronDown size={10} /></>}
          </button>
          {expanded && (
            <pre className="mt-2 rounded-md p-2 text-[11px] mono leading-relaxed whitespace-pre-wrap break-words"
                 style={{ background: '#fff', color: 'var(--slate)', border: `1px solid ${tone.border}` }}>
              {summary.pretty}
            </pre>
          )}
        </div>
      </div>
    </div>
  )
}

function normalizeTrajectoryMessages(segment: TrajectorySegment): ChatMessage[] {
  const source = (segment.rich_messages?.length ? segment.rich_messages : segment.messages) ?? []
  const messages: ChatMessage[] = []

  for (const msg of source) {
    if (Array.isArray(msg.content)) {
      if (msg.role === 'assistant') {
        const text = msg.content
          .filter(block => block.type === 'text' && block.text)
          .map(block => block.text)
          .join('\n\n')
        const toolCalls = msg.content
          .filter(block => block.type === 'tool_use')
          .map(block => normalizeToolCall(block))
          .filter(Boolean) as ToolCall[]
        messages.push({
          role: 'assistant',
          content: text,
          tool_calls: toolCalls,
        })
      } else {
        for (const block of msg.content) {
          if (block.type === 'tool_result') {
            messages.push({
              role: 'tool',
              tool_name: block.tool_name,
              content: block.content ?? '',
            })
          } else if (block.type === 'text' && block.text) {
            messages.push({ role: msg.role, content: block.text })
          }
        }
      }
      continue
    }

    messages.push({
      role: msg.role,
      content: msg.content ?? '',
      tool_calls: (msg.tool_calls ?? [])
        .map(tc => normalizeToolCall(tc))
        .filter(Boolean) as ToolCall[],
    })
  }

  return messages
}

function TrajectoryChatView({ segments }: { segments: TrajectorySegment[] }) {
  const orderedSegments = useMemo(
    () => [...segments].sort((a, b) => (a.segment_id ?? 0) - (b.segment_id ?? 0)),
    [segments],
  )
  const [activeSegmentId, setActiveSegmentId] = useState<number | null>(null)

  useEffect(() => {
    if (orderedSegments.length === 0) {
      setActiveSegmentId(null)
      return
    }
    if (activeSegmentId == null || !orderedSegments.some(s => s.segment_id === activeSegmentId)) {
      setActiveSegmentId(orderedSegments[orderedSegments.length - 1].segment_id)
    }
  }, [orderedSegments, activeSegmentId])

  const activeSegment = orderedSegments.find(s => s.segment_id === activeSegmentId) ?? orderedSegments[orderedSegments.length - 1]
  const messages = useMemo(
    () => activeSegment ? normalizeTrajectoryMessages(activeSegment) : [],
    [activeSegment],
  )

  if (!activeSegment) {
    return <p className="text-sm" style={{ color: 'var(--muted)' }}>暂无 agent 轨迹记录</p>
  }

  return (
    <div>
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <span className="text-xs font-bold mr-1" style={{ color: 'var(--navy)' }}>实现轨迹</span>
        {orderedSegments.map(segment => {
          const active = segment.segment_id === activeSegment.segment_id
          return (
            <button key={segment.segment_id} onClick={() => setActiveSegmentId(segment.segment_id)}
                    className="text-xs font-semibold px-3 py-1.5 rounded-full transition-all"
                    style={{
                      background: active ? 'var(--green)' : 'var(--surface)',
                      color: active ? '#fff' : 'var(--green)',
                      border: `1px solid ${active ? 'var(--green)' : 'var(--border-lt)'}`,
                      borderLeft: `3px solid var(--green)`,
                    }}>
              片段 {segment.segment_id + 1}
            </button>
          )
        })}
        <span className="ml-auto text-[11px]" style={{ color: 'var(--muted)' }}>
          当前 <b style={{ color: 'var(--navy)' }}>{messages.length}</b> 条消息 ·
          <b style={{ color: 'var(--navy)' }}> {activeSegment.files_implemented?.length ?? 0}</b> 文件
        </span>
      </div>

      <div className="space-y-3 relative">
        {messages.map((m, i) => {
          const key = `trajectory-${activeSegment.segment_id}-${i}`
          if (m.role === 'system') return <SystemBubble key={key} content={m.content} idx={i} />
          if (m.role === 'assistant') return <AssistantBubble key={key} msg={m} />
          if (m.role === 'tool') return <ToolBubble key={key} msg={m} />
          return <UserBubble key={key} msg={m} />
        })}
      </div>
    </div>
  )
}

function AgentChatView({ calls }: { calls: LlmCall[] }) {
  const phases = useMemo(() => {
    const seen = new Set<string>()
    const order: string[] = []
    for (const c of calls) {
      if (!seen.has(c.phase)) { seen.add(c.phase); order.push(c.phase) }
    }
    return order
  }, [calls])

  const [activePhase, setActivePhase] = useState<string | null>(null)

  useEffect(() => {
    if (!activePhase && phases.length > 0) setActivePhase(phases[0])
  }, [phases, activePhase])

  // For the active phase, take its last call (longest accumulated history)
  // and append the final response_preview as the closing assistant message.
  const messages = useMemo(() => {
    if (!activePhase) return [] as ChatMessage[]
    const phaseCalls = calls.filter(c => c.phase === activePhase)
    if (phaseCalls.length === 0) return []
    const last = phaseCalls[phaseCalls.length - 1]
    const msgs: ChatMessage[] = [...(last.request_preview ?? [])]
    if (last.response_preview || (last.tool_calls && last.tool_calls.length > 0)) {
      msgs.push({
        role: 'assistant',
        content: last.response_preview ?? '',
        tool_calls: (last.tool_calls ?? [])
          .map(tc => normalizeToolCall(tc))
          .filter(Boolean) as ToolCall[],
      })
    }
    return msgs
  }, [calls, activePhase])

  const phaseStats = useMemo(() => {
    if (!activePhase) return null
    const phaseCalls = calls.filter(c => c.phase === activePhase)
    return computeStats(phaseCalls)
  }, [calls, activePhase])

  if (phases.length === 0) {
    return <p className="text-sm" style={{ color: 'var(--muted)' }}>暂无 LLM 调用记录</p>
  }

  return (
    <div>
      {/* Phase pills */}
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        {phases.map(p => {
          const active = p === activePhase
          const color = PHASE_COLOR[p] ?? 'var(--slate)'
          return (
            <button key={p} onClick={() => setActivePhase(p)}
                    className="text-xs font-semibold px-3 py-1.5 rounded-full transition-all"
                    style={{
                      background: active ? color : 'var(--surface)',
                      color: active ? '#fff' : color,
                      border: `1px solid ${active ? color : 'var(--border-lt)'}`,
                      borderLeft: `3px solid ${color}`,
                    }}>
              {PHASE_LABEL[p] ?? p}
            </button>
          )
        })}
        {phaseStats && (
          <span className="ml-auto text-[11px]" style={{ color: 'var(--muted)' }}>
            该阶段 <b style={{ color: 'var(--navy)' }}>{phaseStats.llm_turns}</b> 次调用 ·
            <b style={{ color: 'var(--navy)' }}> {phaseStats.tool_calls}</b> 工具 ·
            <b style={{ color: 'var(--navy)' }}> {(phaseStats.total_tokens / 1000).toFixed(1)}K</b> tokens
          </span>
        )}
      </div>

      {/* Conversation */}
      <div className="space-y-3 relative">
        {messages.map((m, i) => {
          const key = `${activePhase}-${i}`
          if (m.role === 'system') return <SystemBubble key={key} content={m.content} idx={i} />
          if (m.role === 'assistant') return <AssistantBubble key={key} msg={m} />
          if (m.role === 'tool') return <ToolBubble key={key} msg={m} />
          return <UserBubble key={key} msg={m} />
        })}
      </div>
    </div>
  )
}

export default function CorpusTab({ detail }: Props) {
  const [data, setData] = useState<CorpusData | null>(null)
  const taskId = detail.task_id
  const artifactsKey = detail.artifacts.join('|')

  useEffect(() => {
    setData(null)
    loadCorpusData(taskId, detail.artifacts).then(setData).catch(() => setData({ calls: [], segments: [] }))
  }, [taskId, artifactsKey, detail.artifacts])

  const stats = data ? computeStats(data.calls) : null
  const hasTrajectory = !!data?.segments.length

  return (
    <div className="h-full overflow-auto px-6 py-5">
      {stats && <StatCards stats={stats} />}
      {data === null ? (
        <p className="text-sm" style={{ color: 'var(--muted)' }}>加载中…</p>
      ) : hasTrajectory ? (
        <TrajectoryChatView segments={data.segments} />
      ) : (
        <AgentChatView calls={data.calls} />
      )}
    </div>
  )
}
