import { Code, FileCode, FileText, ArrowRight } from 'lucide-react'
import { SSEEvent } from '../../../hooks/useSSE'
import { PlanData } from '../../../hooks/useTimelineData'

interface Props {
  fileEvents: SSEEvent[]
  plan: PlanData | null
  isRunning: boolean
  ts?: string
  onJump: () => void
}

function FileGlyph({ path }: { path: string }) {
  if (path.endsWith('.md')) return <FileText size={11} style={{ color: 'var(--muted)' }} />
  return <FileCode size={11} style={{ color: 'var(--muted)' }} />
}

const RECENT_COUNT = 4

export default function ImplementationCard({ fileEvents, plan, isRunning, ts, onJump }: Props) {
  const written = fileEvents.length
  const total = plan?.files.length
  const recent = [...fileEvents].reverse().slice(0, RECENT_COUNT)
  const more = Math.max(0, written - recent.length)
  const pct = total ? Math.min(100, Math.round((written / total) * 100)) : 0

  const accent = isRunning ? 'var(--blue)' : 'var(--green)'

  return (
    <div className="rounded-lg border shadow-sm px-4 py-3 flex items-start gap-3"
         style={{
           background: 'var(--surface)',
           borderColor: 'var(--border-lt)',
           borderLeft: `3px solid ${accent}`,
         }}>
      <Code size={18} className="shrink-0 mt-0.5" style={{ color: accent }} />
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2 flex-wrap">
          <h4 className="text-sm font-bold" style={{ color: 'var(--navy)' }}>代码实现</h4>
          {total != null ? (
            <span className="text-xs" style={{ color: 'var(--slate)' }}>
              <b style={{ color: 'var(--blue)' }}>{written}</b> / {total} 文件
            </span>
          ) : (
            <span className="text-xs" style={{ color: 'var(--slate)' }}>
              已写入 <b style={{ color: 'var(--blue)' }}>{written}</b> 文件
            </span>
          )}
          {ts && <span className="text-[10px] ml-auto" style={{ color: 'var(--muted)' }}>{ts}</span>}
        </div>

        {total != null && total > 0 && (
          <div className="mt-2 flex items-center gap-2">
            <div className="flex-1 h-1 rounded-full overflow-hidden" style={{ background: 'var(--border-lt)' }}>
              <div className="h-full transition-all duration-500"
                   style={{
                     width: `${pct}%`,
                     background: isRunning ? 'var(--blue)' : 'var(--green)',
                   }} />
            </div>
            <span className="text-[10px] tabular-nums" style={{ color: 'var(--muted)' }}>{pct}%</span>
          </div>
        )}

        {recent.length > 0 && (
          <div className="mt-2.5 text-[11px] mono space-y-0.5"
               style={{ color: 'var(--slate)' }}>
            {recent.map((e, i) => (
              <div key={i} className="flex items-center gap-1.5 truncate">
                <FileGlyph path={e.path!} />
                <span className="truncate">{e.path}</span>
              </div>
            ))}
            {more > 0 && (
              <div className="text-[10px]" style={{ color: 'var(--muted)' }}>
                还有 {more} 个文件
              </div>
            )}
          </div>
        )}

        {written > 0 && (
          <button onClick={onJump}
                  className="mt-2 inline-flex items-center gap-1 text-xs font-semibold px-3 py-1 rounded-md transition-all hover:gap-2"
                  style={{ background: 'var(--blue-lt)', color: 'var(--blue)' }}>
            查看所有生成文件 <ArrowRight size={12} />
          </button>
        )}
      </div>
    </div>
  )
}
