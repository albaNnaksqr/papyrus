import { FileText } from 'lucide-react'
import { DocIndex } from '../../../hooks/useTimelineData'

interface Props {
  data: DocIndex
  ts?: string
}

export default function ParseCard({ data, ts }: Props) {
  const segments = data.total_segments
  const chars = data.total_chars
  const type = data.document_type?.replace(/_/g, ' ')

  return (
    <div className="rounded-lg border shadow-sm px-4 py-3 flex items-start gap-3"
         style={{
           background: 'var(--surface)',
           borderColor: 'var(--border-lt)',
           borderLeft: '3px solid var(--green)',
         }}>
      <FileText size={18} className="shrink-0 mt-0.5" style={{ color: 'var(--green)' }} />
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2">
          <h4 className="text-sm font-bold" style={{ color: 'var(--navy)' }}>已解析论文</h4>
          {ts && <span className="text-[10px] ml-auto" style={{ color: 'var(--muted)' }}>{ts}</span>}
        </div>
        <div className="mt-1 text-xs flex items-center gap-3 flex-wrap" style={{ color: 'var(--slate)' }}>
          {segments != null && <span><b style={{ color: 'var(--navy)' }}>{segments}</b> 段落</span>}
          {chars != null && <span><b style={{ color: 'var(--navy)' }}>{(chars / 1000).toFixed(1)}k</b> 字</span>}
          {type && <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded"
                          style={{ background: 'var(--blue-lt)', color: 'var(--blue)' }}>{type}</span>}
        </div>
      </div>
    </div>
  )
}
