import { useState, useEffect, useMemo } from 'react'
import { Quote } from 'lucide-react'
import { getArtifactText, TaskDetail } from '../../api/client'
import { getOfflineArtifactText, isOfflineDemo } from '../../demo/offlineDemo'
import PdfViewer from '../PdfViewer'

interface MustImplement {
  claim: string
  section: string
  quote?: string
  code_hint?: string
}
interface ImplementationTrap {
  trap: string
  section: string
  quote?: string
}
interface ExternalDep {
  dep: string
  mitigation: string
  quote?: string
  section?: string
}
interface CritiqueData {
  must_implement: MustImplement[]
  implementation_traps: ImplementationTrap[]
  external_deps: ExternalDep[]
  complexity_score?: number
}

type SelectedItem =
  | { kind: 'must'; idx: number }
  | { kind: 'trap'; idx: number }
  | { kind: 'dep'; idx: number }

interface Props {
  detail: TaskDetail
}

function firstSelectionFromData(data: CritiqueData): SelectedItem | null {
  if (data.must_implement?.length) return { kind: 'must', idx: 0 }
  if (data.implementation_traps?.length) return { kind: 'trap', idx: 0 }
  if (data.external_deps?.length) return { kind: 'dep', idx: 0 }
  return null
}

function clampSelection(data: CritiqueData, selection: SelectedItem | null): SelectedItem | null {
  if (!selection) return firstSelectionFromData(data)
  if (selection.kind === 'must' && selection.idx < (data.must_implement?.length ?? 0)) return selection
  if (selection.kind === 'trap' && selection.idx < (data.implementation_traps?.length ?? 0)) return selection
  if (selection.kind === 'dep' && selection.idx < (data.external_deps?.length ?? 0)) return selection
  return firstSelectionFromData(data)
}

export default function CorrespondenceTab({ detail }: Props) {
  const [data, setData] = useState<CritiqueData | null>(null)
  const [unavailable, setUnavailable] = useState(false)
  const [selected, setSelected] = useState<SelectedItem | null>(null)
  const critiqueArtifact = useMemo(
    () => detail.artifacts.find(a => a.endsWith('critique_structured.json')),
    [detail.task_id, detail.artifacts],
  )

  useEffect(() => {
    setUnavailable(false)
    if (!critiqueArtifact) {
      setUnavailable(true)
      setData(null)
      setSelected(null)
      return
    }

    let cancelled = false
    getArtifactText(detail.task_id, critiqueArtifact)
      .then(text => {
        try {
          const parsed = JSON.parse(text) as CritiqueData
          if (cancelled) return
          setData(parsed)
          setSelected(current => clampSelection(parsed, current))
        } catch {
          if (cancelled) return
          setUnavailable(true)
        }
      })
      .catch(() => {
        if (!cancelled) setUnavailable(true)
      })
    return () => {
      cancelled = true
    }
  }, [critiqueArtifact, detail.task_id])

  const pdfFilename = detail.pdf_path?.split('/').pop()
  const pdfUrl = pdfFilename
    ? `/api/papers/${pdfFilename}`
    : detail.artifacts.includes('paper.pdf')
      ? `/api/tasks/${detail.task_id}/artifacts/paper.pdf`
      : null

  // Pick search text from the selected critique item. Priority: `quote`
  // (verbatim from paper, matches PDF text) over the LLM-paraphrased claim/trap/dep.
  const searchText = useMemo(() => {
    if (!data || !selected) return undefined
    if (selected.kind === 'must') {
      const item = data.must_implement[selected.idx]
      return item?.quote || item?.claim
    }
    if (selected.kind === 'trap') {
      const item = data.implementation_traps[selected.idx]
      return item?.quote || item?.trap
    }
    const item = data.external_deps[selected.idx]
    return item?.quote || item?.dep
  }, [data, selected])

  const offlinePaperText = isOfflineDemo() ? getOfflineArtifactText(detail.task_id, 'paper.md') : null
  const sourceHint = offlinePaperText
    ? '点击批判 · 查看 paper.md 原文摘录'
    : '点击批判 · 自动定位 PDF 原文'

  if (unavailable) {
    return (
      <div className="p-8 text-center">
        <p className="text-sm font-medium" style={{ color: 'var(--navy)' }}>批判分析数据暂不可用</p>
        <p className="text-xs mt-2" style={{ color: 'var(--muted)' }}>
          Pipeline 尚未完成，或任务未启用批判阶段。
        </p>
      </div>
    )
  }

  if (!data) {
    return <div className="p-8 text-sm" style={{ color: 'var(--muted)' }}>加载中…</div>
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* LEFT: source view */}
      <div className="shrink-0" style={{ width: '52%', minWidth: 360, borderRight: '1px solid var(--border-lt)' }}>
        {offlinePaperText ? (
          <OfflinePaperPanel paperText={offlinePaperText} searchText={searchText} />
        ) : pdfUrl ? (
          <PdfViewer pdfUrl={pdfUrl} searchText={searchText} />
        ) : (
          <div className="p-6 text-xs" style={{ color: 'var(--muted)' }}>未找到 PDF 文件</div>
        )}
      </div>

      {/* RIGHT: critique list */}
      <div className="flex-1 overflow-auto p-5 space-y-6" style={{ minWidth: 320, background: '#fafbfc' }}>
        <div className="flex items-center gap-3">
          <h3 className="text-sm font-bold" style={{ color: 'var(--navy)' }}>批判</h3>
          {data.complexity_score != null && (
            <span className="text-xs px-2 py-0.5 rounded-full font-semibold"
                  style={{ background: 'var(--blue-lt)', color: 'var(--blue)' }}>
              复杂度 {data.complexity_score}/10
            </span>
          )}
          <span className="text-[10px] ml-auto" style={{ color: 'var(--muted)' }}>
            {sourceHint}
          </span>
        </div>

        {data.must_implement.length > 0 && (
          <section>
            <h4 className="text-xs font-bold uppercase tracking-wider mb-2" style={{ color: 'var(--muted)' }}>
              必须实现 ({data.must_implement.length})
            </h4>
            <div className="space-y-2">
              {data.must_implement.map((item, i) => {
                const active = selected?.kind === 'must' && selected.idx === i
                return (
                  <CritiqueButton key={i} active={active} accent="var(--blue)"
                                  onClick={() => setSelected({ kind: 'must', idx: i })}
                                  section={item.section} title={item.claim} quote={item.quote} />
                )
              })}
            </div>
          </section>
        )}

        {data.implementation_traps.length > 0 && (
          <section>
            <h4 className="text-xs font-bold uppercase tracking-wider mb-2" style={{ color: 'var(--muted)' }}>
              实现陷阱 ({data.implementation_traps.length})
            </h4>
            <div className="space-y-2">
              {data.implementation_traps.map((item, i) => {
                const active = selected?.kind === 'trap' && selected.idx === i
                return (
                  <CritiqueButton key={i} active={active} accent="var(--red)"
                                  onClick={() => setSelected({ kind: 'trap', idx: i })}
                                  section={item.section} title={item.trap} quote={item.quote} />
                )
              })}
            </div>
          </section>
        )}

        {data.external_deps.length > 0 && (
          <section>
            <h4 className="text-xs font-bold uppercase tracking-wider mb-2" style={{ color: 'var(--muted)' }}>
              外部依赖与缓解 ({data.external_deps.length})
            </h4>
            <div className="space-y-2">
              {data.external_deps.map((item, i) => {
                const active = selected?.kind === 'dep' && selected.idx === i
                return (
                  <button key={i} onClick={() => setSelected({ kind: 'dep', idx: i })}
                          className="w-full text-left rounded-lg p-3 transition-colors shadow-sm"
                          style={{
                            background: active ? 'var(--blue-lt)' : 'var(--surface)',
                            border: '1px solid var(--border-lt)',
                            borderLeft: `3px solid ${active ? 'var(--blue)' : 'var(--border-lt)'}`,
                            cursor: 'pointer',
                          }}>
                    <p className="text-xs leading-relaxed font-medium mb-0.5" style={{ color: 'var(--navy)' }}>{item.dep}</p>
                    <p className="text-xs leading-relaxed" style={{ color: 'var(--muted)' }}>→ {item.mitigation}</p>
                    {item.quote && (
                      <div className="mt-2 pt-2 flex items-start gap-1.5 text-[11px] italic leading-snug"
                           style={{ color: 'var(--muted)', borderTop: '1px dashed var(--border-lt)' }}>
                        <Quote size={10} className="shrink-0 mt-0.5" style={{ color: 'var(--muted)' }} />
                        <span>{item.quote}</span>
                      </div>
                    )}
                  </button>
                )
              })}
            </div>
          </section>
        )}
      </div>
    </div>
  )
}

function OfflinePaperPanel({ paperText, searchText }: { paperText: string; searchText?: string }) {
  const excerpt = useMemo(() => {
    const normalizedSearch = searchText?.trim().replace(/\s+/g, ' ')
    if (!normalizedSearch) return paperText.slice(0, 9000)
    const haystack = paperText.toLowerCase()
    const needle = normalizedSearch.toLowerCase().slice(0, 120)
    const index = haystack.indexOf(needle)
    if (index < 0) return paperText.slice(0, 9000)
    const start = Math.max(0, index - 1800)
    const end = Math.min(paperText.length, index + 5200)
    return paperText.slice(start, end)
  }, [paperText, searchText])

  return (
    <div className="h-full overflow-auto" style={{ background: 'var(--surface)' }}>
      <div className="sticky top-0 z-10 px-3 py-2"
           style={{ background: '#1e293b', borderBottom: '1px solid var(--border-lt)' }}>
        <span className="text-xs mono" style={{ color: '#94a3b8' }}>
          paper.md · 原文摘录
        </span>
      </div>
      <article className="p-5">
        {searchText && (
          <div className="mb-3 rounded-md px-3 py-2 text-xs"
               style={{ background: 'var(--blue-lt)', color: 'var(--blue)', border: '1px solid #bfdbfe' }}>
            当前批判条目已选中；单文件 HTML 展示 paper.md 原文摘录，不加载 PDF 文件。
          </div>
        )}
        <pre className="text-xs leading-relaxed whitespace-pre-wrap mono"
             style={{ color: 'var(--slate)' }}>
          {excerpt}
        </pre>
      </article>
    </div>
  )
}

interface CritiqueButtonProps {
  active: boolean
  accent: string
  section?: string
  title: string
  quote?: string
  onClick: () => void
}

function CritiqueButton({ active, accent, section, title, quote, onClick }: CritiqueButtonProps) {
  return (
    <button onClick={onClick}
            className="w-full text-left rounded-lg p-3 transition-colors shadow-sm"
            style={{
              background: active ? 'var(--blue-lt)' : 'var(--surface)',
              border: '1px solid var(--border-lt)',
              borderLeft: `3px solid ${active ? accent : 'var(--border-lt)'}`,
              cursor: 'pointer',
            }}>
      <div className="flex items-start gap-2 mb-1">
        {section && (
          <span className="text-xs font-bold px-1.5 py-0.5 rounded shrink-0"
                style={{ background: 'var(--amber-lt)', color: '#92400e' }}>
            {section}
          </span>
        )}
        <p className="text-xs leading-relaxed flex-1" style={{ color: 'var(--navy)' }}>{title}</p>
      </div>
      {quote && (
        <div className="mt-2 pt-2 flex items-start gap-1.5 text-[11px] italic leading-snug"
             style={{ color: 'var(--muted)', borderTop: '1px dashed var(--border-lt)' }}>
          <Quote size={10} className="shrink-0 mt-0.5" style={{ color: 'var(--muted)' }} />
          <span>{quote}</span>
        </div>
      )}
    </button>
  )
}
