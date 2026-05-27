import { useState } from 'react'
import { ClipboardList, FileCode, FileText, ChevronDown, ChevronUp } from 'lucide-react'
import { PlanData } from '../../../hooks/useTimelineData'

interface Props {
  data: PlanData
  ts?: string
}

function FileGlyph({ path }: { path: string }) {
  if (path.endsWith('.md')) return <FileText size={11} style={{ color: 'var(--muted)' }} />
  return <FileCode size={11} style={{ color: 'var(--muted)' }} />
}

export default function PlanCard({ data, ts }: Props) {
  const [expanded, setExpanded] = useState(false)
  const files = data.files
  const count = files.length
  if (count === 0) return null

  return (
    <div className="rounded-lg border shadow-sm px-4 py-3 flex items-start gap-3"
         style={{
           background: 'var(--surface)',
           borderColor: 'var(--border-lt)',
           borderLeft: '3px solid #6366f1',
         }}>
      <ClipboardList size={18} className="shrink-0 mt-0.5" style={{ color: '#6366f1' }} />
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2 flex-wrap">
          <h4 className="text-sm font-bold" style={{ color: 'var(--navy)' }}>
            规划了 <span style={{ color: 'var(--blue)' }}>{count}</span> 个文件
          </h4>
          {ts && <span className="text-[10px] ml-auto" style={{ color: 'var(--muted)' }}>{ts}</span>}
          <button onClick={() => setExpanded(e => !e)}
                  className="text-[10px] inline-flex items-center gap-0.5 transition-colors hover:underline"
                  style={{ color: 'var(--muted)' }}>
            {expanded ? <>收起 <ChevronUp size={10} /></> : <>路径列表 <ChevronDown size={10} /></>}
          </button>
        </div>
        {!expanded && files[0] && (
          <div className="mt-1.5 flex items-center gap-1.5 text-[11px] mono truncate"
               style={{ color: 'var(--muted)' }}>
            <FileGlyph path={files[0].path} />
            <span className="truncate">{files[0].path}</span>
            {count > 1 && <span className="shrink-0">· 等 {count - 1} 个</span>}
          </div>
        )}
        {expanded && (
          <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] mono"
               style={{ color: 'var(--slate)' }}>
            {files.map((f, i) => (
              <div key={i} className="flex items-center gap-1.5 truncate">
                <FileGlyph path={f.path} />
                <span className="truncate">{f.path}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
