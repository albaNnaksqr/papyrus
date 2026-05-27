import { useMemo, useState } from 'react'
import { LoaderCircle, Terminal } from 'lucide-react'
import { TaskDetail } from '../../../api/client'
import { SSEEvent } from '../../../hooks/useSSE'
import { useTimelineData } from '../../../hooks/useTimelineData'
import ParseCard from './ParseCard'
import CritiqueCard from './CritiqueCard'
import PlanCard from './PlanCard'
import ImplementationCard from './ImplementationCard'
import DoneSummaryCard from './DoneSummaryCard'
import RawLogDrawer from './RawLogDrawer'

export type JumpTarget = 'files' | 'corpus' | 'correspondence'

interface Props {
  detail: TaskDetail
  events: SSEEvent[]
  taskStatus: string
  onJumpTo: (tab: JumpTarget) => void
}

function formatTime(ts?: string) {
  if (!ts) return ''
  try {
    const date = new Date(ts)
    if (Number.isNaN(date.getTime())) return ts.slice(11, 16)
    return new Intl.DateTimeFormat('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
      timeZone: 'Asia/Shanghai',
    }).format(date)
  } catch {
    return ts.slice(11, 16)
  }
}

function findEventTs(events: SSEEvent[], keywords: string[]): string | undefined {
  for (const e of events) {
    if (!e.message) continue
    const m = e.message.toLowerCase()
    if (keywords.some(k => m.includes(k.toLowerCase()))) return e.ts
  }
  return undefined
}

export default function TimelineTab({ detail, events, taskStatus, onJumpTo }: Props) {
  const { parsed, critique, plan } = useTimelineData(detail)
  const [logOpen, setLogOpen] = useState(false)

  const isRunning = taskStatus === 'running' || taskStatus === 'pending'
  const isFinished = taskStatus === 'done' || taskStatus === 'error' || taskStatus === 'interrupted'

  const fileEvents = useMemo(
    () => events.filter(e => e.type === 'file_written' && e.path)
                .sort((a, b) => (a.ts ?? '').localeCompare(b.ts ?? '')),
    [events]
  )

  const latestProgress = useMemo(
    () => [...events].reverse().find(e => e.type === 'progress' && e.message) ?? null,
    [events]
  )
  const latestPct = useMemo(
    () => [...events].reverse().find(e => e.pct != null)?.pct ?? 0,
    [events]
  )

  const terminalEvent = useMemo(
    () => [...events].reverse().find(e => e.type === 'done' || e.type === 'error' || e.type === 'interrupted') ?? null,
    [events]
  )
  const firstEventTs = events[0]?.ts
  const lastEventTs = events[events.length - 1]?.ts
  const durationMs = firstEventTs && lastEventTs
    ? new Date(lastEventTs).getTime() - new Date(firstEventTs).getTime()
    : undefined

  const showImpl = fileEvents.length > 0

  return (
    <div className="flex h-full overflow-hidden">
      <div className="flex-1 overflow-auto relative" style={{ background: 'var(--bg)' }}>
        <div className="max-w-3xl ml-8 lg:ml-16 px-6 py-8 pb-24">

          <div className="relative pl-10">
            {/* Spine line */}
            <div className="absolute left-3 top-2 bottom-2 w-px"
                 style={{ background: 'var(--border-lt)' }} />

            {parsed && (
              <TimelineNode color="var(--green)" filled>
                <ParseCard data={parsed}
                           ts={formatTime(findEventTs(events, ['parsing', '解析', 'document parsed', '分段']))} />
              </TimelineNode>
            )}

            {critique && (
              <TimelineNode color="var(--green)" filled>
                <CritiqueCard data={critique}
                              ts={formatTime(findEventTs(events, ['批判', 'critique', 'reproducibility']))}
                              onJump={() => onJumpTo('correspondence')} />
              </TimelineNode>
            )}

            {plan && plan.files.length > 0 && (
              <TimelineNode color="var(--green)" filled>
                <PlanCard data={plan}
                          ts={formatTime(findEventTs(events, ['planning', 'implementation plan', 'code structure']))} />
              </TimelineNode>
            )}

            {showImpl && (
              <TimelineNode color={isRunning ? 'var(--blue)' : 'var(--green)'} filled>
                <ImplementationCard fileEvents={fileEvents}
                                    plan={plan}
                                    isRunning={isRunning}
                                    ts={formatTime(fileEvents[fileEvents.length - 1]?.ts)}
                                    onJump={() => onJumpTo('files')} />
              </TimelineNode>
            )}

            {isRunning && latestProgress && (
              <TimelineNode color="var(--blue)" current>
                <div className="rounded-lg border shadow-sm px-4 py-3 flex items-start gap-3"
                     style={{
                       background: 'var(--blue-lt)',
                       borderColor: 'var(--border-lt)',
                       borderLeft: '3px solid var(--blue)',
                     }}>
                  <LoaderCircle size={18} className="shrink-0 mt-0.5 animate-spin"
                                style={{ color: 'var(--blue)' }} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-baseline gap-2 flex-wrap">
                      <h4 className="text-sm font-bold" style={{ color: 'var(--blue)' }}>正在进行</h4>
                      <span className="text-[10px] font-bold px-1.5 py-0.5 rounded tabular-nums"
                            style={{ background: 'var(--blue)', color: '#fff' }}>
                        {latestPct}%
                      </span>
                      <span className="text-[10px] ml-auto" style={{ color: 'var(--muted)' }}>
                        {formatTime(latestProgress.ts)}
                      </span>
                    </div>
                    <p className="mt-1 text-xs leading-snug" style={{ color: 'var(--slate)' }}>
                      {latestProgress.message}
                    </p>
                    <div className="mt-2 h-1 rounded-full overflow-hidden" style={{ background: '#ffffff80' }}>
                      <div className="h-full transition-all duration-700"
                           style={{ width: `${latestPct}%`, background: 'var(--blue)' }} />
                    </div>
                  </div>
                </div>
              </TimelineNode>
            )}

            {isFinished && (
              <TimelineNode color={taskStatus === 'done' ? 'var(--green)' : taskStatus === 'error' ? 'var(--red)' : 'var(--muted)'} filled>
                <DoneSummaryCard status={taskStatus}
                                 fileCount={fileEvents.length}
                                 ts={formatTime(terminalEvent?.ts)}
                                 durationMs={durationMs}
                                 errorMessage={terminalEvent?.message} />
              </TimelineNode>
            )}

            {!parsed && !critique && !plan && !showImpl && !latestProgress && !isFinished && (
              <TimelineNode color="var(--border)">
                <p className="text-xs" style={{ color: 'var(--muted)' }}>等待 pipeline 启动…</p>
              </TimelineNode>
            )}
          </div>
        </div>

        <button onClick={() => setLogOpen(true)}
                className="fixed bottom-5 right-5 z-20 inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-2 rounded-full shadow-md transition-all hover:scale-105"
                style={{ background: '#0f172a', color: '#94a3b8', border: '1px solid #1e293b' }}>
          <Terminal size={12} />
          <span>原始日志 · {events.length}</span>
        </button>
      </div>

      <RawLogDrawer events={events} open={logOpen} onClose={() => setLogOpen(false)} />
    </div>
  )
}

function TimelineNode({ children, color, filled = false, current = false }: {
  children: React.ReactNode
  color: string
  filled?: boolean
  current?: boolean
}) {
  const dot = current ? 12 : 9
  return (
    <div className="relative mb-3">
      <div className="absolute -left-10 top-3.5 w-6 h-6 flex items-center justify-center">
        <div className="rounded-full transition-all"
             style={{
               width: dot,
               height: dot,
               background: filled || current ? color : 'transparent',
               border: `${current ? 2 : 1.5}px solid ${color}`,
               boxShadow: current ? `0 0 0 4px ${color}22` : undefined,
             }} />
        {current && (
          <div className="absolute inset-0 rounded-full animate-ping"
               style={{ background: color, opacity: 0.2 }} />
        )}
      </div>
      {children}
    </div>
  )
}
