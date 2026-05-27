import { Sparkles, ArrowRight } from 'lucide-react'
import { CritiqueData } from '../../../hooks/useTimelineData'

interface Props {
  data: CritiqueData
  ts?: string
  onJump: () => void
}

export default function CritiqueCard({ data, ts, onJump }: Props) {
  const allItems = [...data.must_implement, ...data.implementation_traps, ...data.external_deps]
  const refCount = allItems.filter(c => c.quote || c.section).length
  const firstQuote = allItems.find(c => c.quote)?.quote

  return (
    <div className="rounded-lg border shadow-sm px-4 py-3 flex items-start gap-3"
         style={{
           background: 'var(--surface)',
           borderColor: 'var(--border-lt)',
           borderLeft: '3px solid #d97706',
         }}>
      <Sparkles size={18} className="shrink-0 mt-0.5" style={{ color: '#d97706' }} />
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2 flex-wrap">
          <h4 className="text-sm font-bold" style={{ color: 'var(--navy)' }}>老师傅批判完成</h4>
          {ts && <span className="text-[10px] ml-auto" style={{ color: 'var(--muted)' }}>{ts}</span>}
        </div>
        <div className="mt-1 text-xs flex items-center gap-3 flex-wrap" style={{ color: 'var(--slate)' }}>
          <span><b style={{ color: 'var(--navy)' }}>{data.must_implement.length}</b> 必须实现</span>
          <span><b style={{ color: '#dc2626' }}>{data.implementation_traps.length}</b> 陷阱</span>
          {data.external_deps.length > 0 && (
            <span><b style={{ color: 'var(--navy)' }}>{data.external_deps.length}</b> 外部依赖</span>
          )}
          {refCount > 0 && (
            <span><b style={{ color: 'var(--navy)' }}>{refCount}</b> 处原文索引</span>
          )}
          {data.complexity_score != null && (
            <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded"
                  style={{ background: 'var(--blue-lt)', color: 'var(--blue)' }}>
              复杂度 {data.complexity_score}/10
            </span>
          )}
        </div>
        {firstQuote && (
          <p className="mt-1.5 text-[11px] italic leading-snug line-clamp-1"
             style={{ color: 'var(--muted)' }}>
            “{firstQuote}”
          </p>
        )}
        <button onClick={onJump}
                className="mt-2 inline-flex items-center gap-1 text-xs font-semibold px-3 py-1 rounded-md transition-all hover:gap-2"
                style={{ background: 'var(--blue-lt)', color: 'var(--blue)' }}>
          查看批判详情 <ArrowRight size={12} />
        </button>
      </div>
    </div>
  )
}
