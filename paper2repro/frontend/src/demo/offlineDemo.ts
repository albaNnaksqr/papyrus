import type { Task, TaskDetail } from '../api/client'
import type { SSEEvent } from '../hooks/useSSE'

export type OfflineDemoMode = 'static' | 'replay'

export interface OfflineDemoTask {
  id: string
  title: string
  shortTitle: string
  status: Task['status']
  statusLabel: string
  createdAt: string
  completedAt: string
  pdfPath?: string | null
  stats: Record<string, unknown>
  critique: Record<string, unknown>
  docIndex: Record<string, unknown> | null
  events: SSEEvent[]
  corpus: Array<Record<string, unknown>>
  artifacts: Record<string, string>
}

export interface OfflineDemoPayload {
  mode: OfflineDemoMode
  page: string
  generatedAt: string
  activeTaskId: string
  replayDelayMs: number
  stayOnPipelineAfterDone?: boolean
  tasks: OfflineDemoTask[]
}

interface ReplayTaskState {
  eventIndex: number
  terminal: boolean
}

interface OfflineDemoState {
  replay: Record<string, ReplayTaskState>
  deletedTaskIds: string[]
  stoppedTaskIds: string[]
  createdTasks: OfflineDemoTask[]
}

declare global {
  interface Window {
    __PAPER2CODE_DEMO__?: OfflineDemoPayload
    __PAPER2CODE_DEMO_STATE__?: OfflineDemoState
  }
}

let cachedPayload: OfflineDemoPayload | null | undefined

export function getOfflineDemoPayload(): OfflineDemoPayload | null {
  if (typeof window === 'undefined' || typeof document === 'undefined') return null
  if (cachedPayload !== undefined) return cachedPayload
  if (window.__PAPER2CODE_DEMO__) {
    cachedPayload = window.__PAPER2CODE_DEMO__
    return cachedPayload
  }
  const element = document.getElementById('paper2code-demo-data')
  if (!element?.textContent) {
    cachedPayload = null
    return null
  }
  try {
    cachedPayload = JSON.parse(element.textContent) as OfflineDemoPayload
    window.__PAPER2CODE_DEMO__ = cachedPayload
    return cachedPayload
  } catch (error) {
    console.error('[offline-demo] failed to parse embedded demo data', error)
    cachedPayload = null
    return null
  }
}

export function isOfflineDemo(): boolean {
  return getOfflineDemoPayload() != null
}

export function getOfflineInitialTaskId(): string | null {
  const payload = getOfflineDemoPayload()
  return payload?.activeTaskId ?? payload?.tasks[0]?.id ?? null
}

export function getOfflineInitialTab(): 'pipeline' | 'files' | undefined {
  const payload = getOfflineDemoPayload()
  if (!payload) return undefined
  return payload.mode === 'replay' ? 'pipeline' : 'files'
}

export function getOfflineDetailPollIntervalMs(): number | undefined {
  const payload = getOfflineDemoPayload()
  if (!payload || payload.mode !== 'replay') return undefined
  return Math.max(250, payload.replayDelayMs)
}

export function shouldOfflineDemoStayOnPipelineAfterDone(): boolean {
  return getOfflineDemoPayload()?.stayOnPipelineAfterDone ?? false
}

export function isOfflineReplayDemo(): boolean {
  return getOfflineDemoPayload()?.mode === 'replay'
}

function getState(): OfflineDemoState {
  if (!window.__PAPER2CODE_DEMO_STATE__) {
    window.__PAPER2CODE_DEMO_STATE__ = {
      replay: {},
      deletedTaskIds: [],
      stoppedTaskIds: [],
      createdTasks: [],
    }
  }
  return window.__PAPER2CODE_DEMO_STATE__
}

function getReplayTaskState(taskId: string): ReplayTaskState {
  const state = getState()
  if (!state.replay[taskId]) {
    state.replay[taskId] = { eventIndex: -1, terminal: false }
  }
  return state.replay[taskId]
}

function findOfflineTask(taskId: string): OfflineDemoTask | null {
  const payload = getOfflineDemoPayload()
  if (!payload) return null
  const state = getState()
  return [...state.createdTasks, ...payload.tasks]
    .filter(task => !state.deletedTaskIds.includes(task.id))
    .find(task => task.id === taskId) ?? null
}

function terminalTypeFor(status: Task['status']): SSEEvent['type'] {
  if (status === 'error') return 'error'
  if (status === 'interrupted') return 'interrupted'
  return 'done'
}

export function getOfflineTaskEvents(taskId: string): SSEEvent[] {
  const task = findOfflineTask(taskId)
  if (!task) return []
  const events = task.events ?? []
  if (events.some(event => event.type === 'done' || event.type === 'error' || event.type === 'interrupted')) {
    return events
  }
  const last = events[events.length - 1]
  return [
    ...events,
    {
      type: terminalTypeFor(task.status),
      pct: task.status === 'done' ? 100 : last?.pct,
      message: task.status === 'done' ? '离线演示：任务完成' : '离线演示：任务未完整完成',
      ts: last?.ts ?? task.completedAt,
    },
  ]
}

export function resetOfflineReplayTask(taskId: string): void {
  if (typeof window === 'undefined') return
  getState().replay[taskId] = { eventIndex: -1, terminal: false }
}

export function recordOfflineReplayEvent(taskId: string, eventIndex: number, event: SSEEvent): void {
  if (typeof window === 'undefined') return
  const state = getReplayTaskState(taskId)
  state.eventIndex = Math.max(state.eventIndex, eventIndex)
  if (event.type === 'done' || event.type === 'error' || event.type === 'interrupted') {
    state.terminal = true
  }
}

function latestReplayPct(taskId: string): number {
  const state = getReplayTaskState(taskId)
  const events = getOfflineTaskEvents(taskId).slice(0, state.eventIndex + 1)
  return [...events].reverse().find(event => event.pct != null)?.pct ?? 0
}

function writtenGeneratedPaths(taskId: string): Set<string> {
  const state = getReplayTaskState(taskId)
  const events = getOfflineTaskEvents(taskId).slice(0, state.eventIndex + 1)
  const paths = new Set<string>()
  for (const event of events) {
    if (event.type !== 'file_written' || !event.path) continue
    paths.add(event.path)
    paths.add(`generate_code/${event.path}`)
  }
  return paths
}

function visibleEvents(taskId: string): SSEEvent[] {
  const payload = getOfflineDemoPayload()
  const events = getOfflineTaskEvents(taskId)
  if (!payload || payload.mode !== 'replay' || payload.activeTaskId !== taskId) {
    return events
  }
  const state = getReplayTaskState(taskId)
  if (state.terminal) return events
  return events.slice(0, state.eventIndex + 1)
}

function visibleArtifactPaths(task: OfflineDemoTask): string[] {
  const payload = getOfflineDemoPayload()
  const allPaths = Object.keys(task.artifacts)
  if (!payload || payload.mode === 'static' || payload.activeTaskId !== task.id) return allPaths

  const state = getReplayTaskState(task.id)
  if (state.terminal) return allPaths

  const pct = latestReplayPct(task.id)
  const written = writtenGeneratedPaths(task.id)

  return allPaths.filter(path => {
    if (path === 'logs/events.jsonl') return true
    if (pct >= 50 && (path === 'paper.md' || path.startsWith('document_segments/'))) return true
    if (pct >= 58 && (path === 'critique_structured.json' || path === 'critique_report.md')) return true
    if (pct >= 65 && (path === 'initial_plan.txt' || path === 'planning_result_meta.json')) return true
    if (pct >= 70 && (path === 'reference.txt' || path === 'github_download.txt')) return true
    if (pct >= 80 && path === 'codebase_index_report.txt') return true
    if (pct >= 85 && path.startsWith('generate_code/')) return written.has(path)
    if (pct >= 92 && (path === 'validation_report.md' || path.endsWith('validate_paper_claims.py'))) return true
    if (pct >= 100) return true
    return false
  })
}

function offlineStatus(task: OfflineDemoTask): Task['status'] {
  if (getState().stoppedTaskIds.includes(task.id)) return 'interrupted'
  const payload = getOfflineDemoPayload()
  if (!payload || payload.mode !== 'replay' || payload.activeTaskId !== task.id) return task.status
  const state = getReplayTaskState(task.id)
  return state.terminal ? task.status : 'running'
}

function toClientTask(task: OfflineDemoTask): Task {
  return {
    task_id: task.id,
    status: offlineStatus(task),
    created_at: task.createdAt || getOfflineDemoPayload()?.generatedAt || '',
    pdf_path: task.pdfPath ?? `${task.shortTitle || task.id}.pdf`,
  }
}

export function listOfflineTasks(): Task[] | null {
  const payload = getOfflineDemoPayload()
  if (!payload) return null
  const state = getState()
  return [...state.createdTasks, ...payload.tasks]
    .filter(task => !state.deletedTaskIds.includes(task.id))
    .map(toClientTask)
}

export function getOfflineTask(taskId: string): TaskDetail | null {
  const task = findOfflineTask(taskId)
  if (!task) return null
  return {
    ...toClientTask(task),
    artifacts: visibleArtifactPaths(task),
    events: visibleEvents(taskId),
  }
}

export function getOfflineArtifactText(taskId: string, artifactPath: string): string | null {
  const task = findOfflineTask(taskId)
  if (!task) return null
  return task.artifacts[artifactPath] ?? null
}

export function uploadOfflinePdf(file: File): { path: string; filename: string } | null {
  if (!getOfflineDemoPayload()) return null
  return { path: `demo_uploads/${file.name}`, filename: file.name }
}

export function createOfflineTask(params: {
  pdf_path: string
  fast: boolean
  no_critique: boolean
}): Task | null {
  const payload = getOfflineDemoPayload()
  if (!payload) return null
  const state = getState()
  const now = new Date().toISOString()
  const filename = params.pdf_path.split('/').pop()?.replace(/\.pdf$/i, '') || 'demo-paper'
  const id = `demo_${Date.now().toString(36)}`
  const task: OfflineDemoTask = {
    id,
    title: filename,
    shortTitle: filename,
    status: 'pending',
    statusLabel: '等待中',
    createdAt: now,
    completedAt: now,
    pdfPath: params.pdf_path,
    stats: {},
    critique: { must_implement: [], implementation_traps: [], external_deps: [] },
    docIndex: null,
    events: [{
      type: 'progress',
      pct: 1,
      message: params.fast
        ? '离线演示：快速模式任务已创建'
        : params.no_critique
          ? '离线演示：跳过批判的任务已创建'
          : '离线演示：任务已创建',
      ts: now,
    }],
    corpus: [],
    artifacts: {
      'initial_plan.txt': '离线演示任务已创建。独立 HTML 不会启动真实后端 pipeline。',
    },
  }
  state.createdTasks.unshift(task)
  return toClientTask(task)
}

export function deleteOfflineTask(taskId: string): boolean {
  if (!getOfflineDemoPayload()) return false
  const state = getState()
  if (!state.deletedTaskIds.includes(taskId)) state.deletedTaskIds.push(taskId)
  return true
}

export function stopOfflineTask(taskId: string): boolean {
  if (!getOfflineDemoPayload()) return false
  const state = getState()
  if (!state.stoppedTaskIds.includes(taskId)) state.stoppedTaskIds.push(taskId)
  getReplayTaskState(taskId).terminal = true
  return true
}
