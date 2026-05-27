import { useEffect, useRef } from 'react'
import { SSEEvent } from '../../../hooks/useSSE'

interface Props {
  events: SSEEvent[]
  open: boolean
  onClose: () => void
}

export default function RawLogDrawer({ events, open, onClose }: Props) {
  const logRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (open && logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [events, open])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-30 flex items-end justify-end pointer-events-none">
      <div className="pointer-events-auto rounded-tl-2xl shadow-2xl flex flex-col"
           style={{
             width: 480,
             height: '60vh',
             background: '#0f172a',
             border: '1px solid var(--border)',
             borderBottom: 'none',
             borderRight: 'none',
           }}>
        <div className="flex items-center justify-between px-4 py-2 shrink-0"
             style={{ borderBottom: '1px solid #1e293b' }}>
          <span className="text-xs font-bold uppercase tracking-wider" style={{ color: '#94a3b8' }}>
            原始事件流 · {events.length} 条
          </span>
          <button onClick={onClose} className="text-xs" style={{ color: '#60a5fa' }}>× 关闭</button>
        </div>
        <div ref={logRef} className="flex-1 overflow-y-auto px-4 py-3 mono text-[11px] space-y-0.5">
          {events.map((e, i) => {
            const isErr = e.type === 'error'
            const isFile = e.type === 'file_written'
            const color = isErr ? '#fca5a5' : isFile ? '#86efac' : e.pct === 100 ? '#86efac' : '#94a3b8'
            return (
              <div key={i} style={{ color }}>
                <span style={{ color: '#64748b' }}>[{e.ts?.slice(11, 19) ?? '--:--:--'}]</span>{' '}
                <span style={{ color: '#cbd5e1', fontWeight: 600 }}>{e.type}</span>{' '}
                {e.pct != null && <span style={{ color: '#60a5fa' }}>{e.pct}% </span>}
                {e.path ?? e.message ?? ''}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
