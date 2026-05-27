import { useState, useEffect, useMemo } from 'react'
import { useSSE } from '../../hooks/useSSE'
import type { SSEEvent } from '../../hooks/useSSE'
import { downloadTaskArchive, getTask, stopTask, TaskDetail as TaskDetailType } from '../../api/client'
import {
  getOfflineDetailPollIntervalMs,
  getOfflineInitialTab,
  isOfflineReplayDemo,
  resetOfflineReplayTask,
  shouldOfflineDemoStayOnPipelineAfterDone,
} from '../../demo/offlineDemo'
import TimelineTab from './timeline/TimelineTab'
import FilesTab from './FilesTab'
import CorpusTab from './CorpusTab'
import CorrespondenceTab from './CorrespondenceTab'
import { Download, RotateCcw } from 'lucide-react'

interface Props {
  taskId: string
}

const STATUS_LABEL: Record<string, string> = {
  pending: '等待中', running: '运行中', done: '完成', error: '失败', interrupted: '中断',
}
const STATUS_COLOR: Record<string, string> = {
  done: 'var(--green)', running: 'var(--blue)', error: 'var(--red)',
  pending: 'var(--blue)', interrupted: 'var(--muted)',
}

type TabKey = 'pipeline' | 'files' | 'corpus' | 'correspondence'

function eventKey(event: SSEEvent): string {
  return [
    event.type,
    event.ts ?? '',
    event.pct ?? '',
    event.phase ?? '',
    event.path ?? '',
    event.section_ref ?? '',
    event.message ?? '',
    event.summary ?? '',
  ].join('\u001f')
}

function mergeEvents(baseEvents: SSEEvent[] = [], liveEvents: SSEEvent[] = []): SSEEvent[] {
  const seen = new Set<string>()
  const merged: SSEEvent[] = []
  for (const event of [...baseEvents, ...liveEvents]) {
    const key = eventKey(event)
    if (seen.has(key)) continue
    seen.add(key)
    merged.push(event)
  }
  return merged
}

export default function TaskDetail({ taskId }: Props) {
  const [detail, setDetail] = useState<TaskDetailType | null>(null)
  const [replayKey, setReplayKey] = useState(0)
  const { events, done } = useSSE(taskId, replayKey)
  const [tab, setTab] = useState<TabKey>(() => getOfflineInitialTab() ?? 'pipeline')
  const [stopping, setStopping] = useState(false)
  const [exporting, setExporting] = useState(false)
  const showReplay = isOfflineReplayDemo()

  async function handleStop() {
    if (stopping) return
    if (!confirm('确定要停止当前任务吗？已生成的产物会保留。')) return
    setStopping(true)
    try {
      await stopTask(taskId)
      await getTask(taskId).then(setDetail).catch(() => {})
    } catch (err) {
      console.error('[TaskDetail] stop failed:', err)
      alert('停止失败：' + (err instanceof Error ? err.message : String(err)))
    } finally {
      setStopping(false)
    }
  }

  async function handleExport() {
    if (exporting) return
    setExporting(true)
    try {
      await downloadTaskArchive(taskId)
    } catch (err) {
      console.error('[TaskDetail] export failed:', err)
      alert(err instanceof Error ? err.message : '导出失败')
    } finally {
      setExporting(false)
    }
  }

  async function handleReplay() {
    resetOfflineReplayTask(taskId)
    setTab('pipeline')
    setReplayKey(k => k + 1)
    await getTask(taskId).then(setDetail).catch(() => {})
  }

  useEffect(() => {
    getTask(taskId).then(setDetail).catch(() => {})
  }, [taskId])

  useEffect(() => {
    if (done) {
      getTask(taskId).then(setDetail).catch(() => {})
      if (!shouldOfflineDemoStayOnPipelineAfterDone()) {
        setTab('files')
      }
    }
  }, [done, taskId])

  // While task is running, poll task detail every 4s so newly-generated
  // artifacts (critique_structured.json at phase 4.5, code files in phase 9)
  // show up in the tabs without waiting for the whole pipeline to finish.
  useEffect(() => {
    const status = detail?.status
    if (status !== 'running' && status !== 'pending') return
    const handle = setInterval(() => {
      getTask(taskId).then(setDetail).catch(() => {})
    }, getOfflineDetailPollIntervalMs() ?? 4000)
    return () => clearInterval(handle)
  }, [detail?.status, taskId])

  const status = detail?.status ?? 'pending'
  const title = detail?.pdf_path?.split('/').pop()?.replace('.pdf', '') ?? taskId
  const timelineEvents = useMemo(
    () => mergeEvents(detail?.events, events),
    [detail?.events, events]
  )

  const TABS: { key: TabKey; label: string }[] = [
    { key: 'pipeline', label: 'Pipeline' },
    { key: 'files', label: '文件' },
    { key: 'corpus', label: '语料' },
    { key: 'correspondence', label: '原文·批判' },
  ]

  const latestPct = [...timelineEvents].reverse().find(e => e.pct != null)?.pct ?? 0

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="shrink-0 px-6 py-3 flex items-center gap-3"
           style={{ borderBottom: '1px solid var(--border-lt)', background: 'var(--surface)' }}>
        <span className="font-bold text-sm truncate" style={{ color: 'var(--navy)' }}>{title}</span>
        <span className="text-xs px-2 py-0.5 rounded-full font-semibold shrink-0"
              style={{ background: `${STATUS_COLOR[status]}22`, color: STATUS_COLOR[status] }}>
          {STATUS_LABEL[status] ?? status}
        </span>
        {(status === 'running' || status === 'pending') && latestPct > 0 && (
          <div className="flex-1 max-w-32 h-1.5 rounded-full ml-2" style={{ background: 'var(--border-lt)' }}>
            <div className="h-full rounded-full transition-all" style={{ width: `${latestPct}%`, background: 'var(--blue)' }} />
          </div>
        )}
        {showReplay && (
          <button onClick={handleReplay}
                  className="ml-auto text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors inline-flex items-center gap-1.5"
                  style={{
                    background: 'var(--blue)',
                    color: '#fff',
                    cursor: 'pointer',
                  }}>
            <RotateCcw size={12} />
            重放流程
          </button>
        )}
        <button onClick={handleExport} disabled={exporting || status === 'running' || status === 'pending'}
                className={`${showReplay ? '' : 'ml-auto'} text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors inline-flex items-center gap-1.5`}
                style={{
                  background: status === 'running' || status === 'pending' || exporting ? 'var(--border-lt)' : 'var(--green)',
                  color: status === 'running' || status === 'pending' || exporting ? 'var(--muted)' : '#fff',
                  cursor: status === 'running' || status === 'pending' || exporting ? 'not-allowed' : 'pointer',
                }}>
          <Download size={12} />
          {exporting ? '导出中…' : '导出'}
        </button>
        {(status === 'running' || status === 'pending') && !showReplay && (
          <button onClick={handleStop} disabled={stopping}
                  className="ml-auto text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors"
                  style={{
                    background: stopping ? 'var(--border-lt)' : 'var(--red)',
                    color: stopping ? 'var(--muted)' : '#fff',
                    cursor: stopping ? 'not-allowed' : 'pointer',
                  }}>
            {stopping ? '停止中…' : '停止'}
          </button>
        )}
      </div>

      {/* Tabs */}
      <div className="shrink-0 flex px-6" style={{ borderBottom: '1px solid var(--border-lt)', background: 'var(--surface)' }}>
        {TABS.map(t => (
          <button key={t.key} onClick={() => setTab(t.key)}
                  className="px-4 py-2.5 text-xs font-medium border-b-2 transition-colors"
                  style={{
                    borderColor: tab === t.key ? 'var(--blue)' : 'transparent',
                    color: tab === t.key ? 'var(--blue)' : 'var(--muted)',
                  }}>
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-hidden">
        {tab === 'pipeline' && detail && (
          <TimelineTab detail={detail} events={timelineEvents} taskStatus={status}
                       onJumpTo={(target) => setTab(target)} />
        )}
        {tab === 'files' && detail && (
          <FilesTab detail={detail} />
        )}
        {tab === 'corpus' && detail && (
          <CorpusTab detail={detail} />
        )}
        {tab === 'correspondence' && detail && (
          <CorrespondenceTab detail={detail} />
        )}
      </div>
    </div>
  )
}
