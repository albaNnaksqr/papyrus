import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import * as pdfjsLib from 'pdfjs-dist'
import { TextLayer } from 'pdfjs-dist'
import type { PDFDocumentProxy, PDFPageProxy } from 'pdfjs-dist'
import { getCanvasBackingStore } from '../lib/pdfCanvas'
import { findBestHighlightSet, hasUsableTextLayer } from '../lib/pdfHighlight'

interface Props {
  pdfUrl: string
  searchText?: string
  onClose?: () => void
}

const SCALE_MIN = 0.5
const SCALE_MAX = 3.0
const SCALE_STEP = 0.15

export default function PdfViewer({ pdfUrl, searchText, onClose }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const textLayerRef = useRef<HTMLDivElement>(null)
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null)
  const [pageNum, setPageNum] = useState(1)
  const [numPages, setNumPages] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [scale, setScale] = useState(1.2)
  const [fitWidth, setFitWidth] = useState(true)
  const [pageNativeWidth, setPageNativeWidth] = useState<number | null>(null)
  const [highlightNotice, setHighlightNotice] = useState<string | null>(null)

  // Load PDF
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    const task = pdfjsLib.getDocument(pdfUrl)
    task.promise
      .then(doc => {
        if (cancelled) {
          doc.destroy()
          return
        }
        setPdf(doc)
        setNumPages(doc.numPages)
        setLoading(false)
      })
      .catch(err => {
        if (cancelled) return
        console.error('[PdfViewer] getDocument failed for', pdfUrl, err)
        setError(`无法加载 PDF: ${err?.message || err?.name || String(err)}`)
        setLoading(false)
      })
    return () => {
      cancelled = true
      task.destroy()
    }
  }, [pdfUrl])

  // Find page containing searchText (use same normalization as highlighter)
  useEffect(() => {
    if (!pdf || !searchText) return
    let cancelled = false
    async function findPage() {
      if (!pdf) return
      let sawUsableText = false
      for (let i = 1; i <= pdf.numPages; i++) {
        if (cancelled) return
        const page: PDFPageProxy = await pdf.getPage(i)
        const tc = await page.getTextContent()
        const items = tc.items.map(item => ((item as { str?: string }).str ?? ''))
        sawUsableText ||= hasUsableTextLayer(items)
        if (findBestHighlightSet(items, searchText!).size > 0) {
          setPageNum(i)
          setHighlightNotice(null)
          return
        }
      }
      if (!cancelled) {
        setHighlightNotice(
          sawUsableText
            ? '未能自动定位这段原文；可能是 PDF 文本层与批判引用存在公式、断行或改写差异。'
            : 'PDF 可提取文本很少，可能是扫描/图片 PDF；需要 OCR 后才能稳定高亮。',
        )
      }
    }
    findPage()
    return () => { cancelled = true }
  }, [pdf, searchText])

  // Capture the page's native (scale=1) width so fit-to-width can compute scale.
  useEffect(() => {
    if (!pdf) return
    let cancelled = false
    pdf.getPage(pageNum).then(page => {
      if (cancelled) return
      const vp = page.getViewport({ scale: 1 })
      setPageNativeWidth(vp.width)
    })
    return () => { cancelled = true }
  }, [pdf, pageNum])

  // Fit-to-width: observe container width and update scale.
  useLayoutEffect(() => {
    if (!fitWidth || !pageNativeWidth || !containerRef.current) return
    const el = containerRef.current
    const recompute = () => {
      // 16px padding margin on each side
      const available = el.clientWidth - 24
      if (available <= 0) return
      const next = Math.max(SCALE_MIN, Math.min(SCALE_MAX, available / pageNativeWidth))
      setScale(prev => Math.abs(prev - next) > 0.01 ? next : prev)
    }
    recompute()
    const ro = new ResizeObserver(recompute)
    ro.observe(el)
    return () => ro.disconnect()
  }, [fitWidth, pageNativeWidth])

  // Render page (canvas + text layer with highlights)
  useEffect(() => {
    if (!pdf || !canvasRef.current || !textLayerRef.current) return
    let cancelled = false
    let renderTask: ReturnType<PDFPageProxy['render']> | null = null
    let textLayer: TextLayer | null = null

    pdf.getPage(pageNum).then(async (page: PDFPageProxy) => {
      if (cancelled || !canvasRef.current || !textLayerRef.current) return
      const viewport = page.getViewport({ scale })
      const canvas = canvasRef.current
      const backingStore = getCanvasBackingStore({
        width: viewport.width,
        height: viewport.height,
        devicePixelRatio: window.devicePixelRatio,
      })
      canvas.width = backingStore.pixelWidth
      canvas.height = backingStore.pixelHeight
      canvas.style.width = `${backingStore.cssWidth}px`
      canvas.style.height = `${backingStore.cssHeight}px`
      const container = textLayerRef.current
      container.style.width = `${viewport.width}px`
      container.style.height = `${viewport.height}px`
      container.replaceChildren()

      const ctx = canvas.getContext('2d')
      if (!ctx) return
      ctx.setTransform(backingStore.outputScale, 0, 0, backingStore.outputScale, 0, 0)
      renderTask = page.render({ canvasContext: ctx, viewport })
      try {
        await renderTask.promise
      } catch {
        return
      }
      if (cancelled) return

      const textContent = await page.getTextContent()
      if (cancelled) return
      textLayer = new TextLayer({ textContentSource: textContent, container, viewport })
      try {
        await textLayer.render()
      } catch {
        return
      }
      if (cancelled) return

      const items = textLayer.textContentItemsStr
      if (!hasUsableTextLayer(items)) {
        setHighlightNotice(
          searchText
            ? '当前页可提取文本很少，可能是扫描/图片 PDF；需要 OCR 后才能稳定高亮。'
            : null,
        )
        return
      }

      if (searchText) {
        const hits = findBestHighlightSet(items, searchText)
        const divs = textLayer.textDivs
        hits.forEach(i => { divs[i]?.classList.add('pdf-highlight') })
        setHighlightNotice(
          hits.size > 0
            ? null
            : '当前页没有匹配到选中的原文；可尝试切页，或检查引用是否是模型改写而非 PDF 原句。',
        )
      } else {
        setHighlightNotice(null)
      }
    })

    return () => {
      cancelled = true
      renderTask?.cancel()
      textLayer?.cancel()
    }
  }, [pdf, pageNum, scale, searchText])

  function zoomIn() {
    setFitWidth(false)
    setScale(s => Math.min(SCALE_MAX, +(s + SCALE_STEP).toFixed(2)))
  }
  function zoomOut() {
    setFitWidth(false)
    setScale(s => Math.max(SCALE_MIN, +(s - SCALE_STEP).toFixed(2)))
  }

  const btnStyle = {
    background: '#334155',
    color: '#e2e8f0',
    padding: '2px 8px',
    borderRadius: 4,
    fontSize: 11,
    lineHeight: '18px',
    cursor: 'pointer',
  } as const

  return (
    <div className="flex flex-col h-full" style={{ borderLeft: '1px solid var(--border-lt)', background: 'var(--surface)' }}>
      {/* Header */}
      <div className="shrink-0 flex items-center gap-2 px-3 py-2"
           style={{ borderBottom: '1px solid var(--border-lt)', background: '#1e293b' }}>
        <span className="text-xs mono truncate flex-1" style={{ color: '#94a3b8' }}>
          {pdfUrl.split('/').pop()} {numPages > 0 && `· p.${pageNum}/${numPages}`}
        </span>
        <button onClick={zoomOut} style={btnStyle} title="缩小">−</button>
        <button
          onClick={() => setFitWidth(f => !f)}
          style={{ ...btnStyle, background: fitWidth ? '#2563eb' : '#334155' }}
          title="适应宽度"
        >适宽</button>
        <button onClick={zoomIn} style={btnStyle} title="放大">+</button>
        <span className="text-xs mono shrink-0" style={{ color: '#64748b', minWidth: 36, textAlign: 'right' }}>
          {Math.round(scale * 100)}%
        </span>
        {onClose && (
          <button onClick={onClose} className="text-xs ml-1" style={{ color: '#60a5fa' }}>× 关闭</button>
        )}
      </div>

      {/* Content */}
      <div ref={containerRef} className="flex-1 overflow-auto p-2">
        {loading && <p className="text-xs p-4" style={{ color: 'var(--muted)' }}>加载中…</p>}
        {error && <p className="text-xs p-4" style={{ color: 'var(--red)' }}>{error}</p>}
        {!loading && !error && highlightNotice && (
          <div
            className="mb-2 rounded-md px-3 py-2 text-xs"
            style={{
              border: '1px solid #fde68a',
              background: '#fffbeb',
              color: '#92400e',
            }}
          >
            {highlightNotice}
          </div>
        )}
        {!loading && !error && (
          <div className="pdf-page-wrapper" style={{ position: 'relative', display: 'inline-block' }}>
            <canvas ref={canvasRef} style={{ display: 'block' }} />
            <div ref={textLayerRef} className="textLayer" />
          </div>
        )}
      </div>

      {/* Pagination */}
      {numPages > 1 && (
        <div className="shrink-0 flex items-center justify-center gap-3 py-2"
             style={{ borderTop: '1px solid var(--border-lt)' }}>
          <button onClick={() => setPageNum(p => Math.max(1, p - 1))} disabled={pageNum === 1}
                  className="text-xs px-2 py-1 rounded disabled:opacity-30"
                  style={{ background: 'var(--border-lt)', color: 'var(--slate)' }}>← 上页</button>
          <span className="text-xs" style={{ color: 'var(--muted)' }}>{pageNum} / {numPages}</span>
          <button onClick={() => setPageNum(p => Math.min(numPages, p + 1))} disabled={pageNum === numPages}
                  className="text-xs px-2 py-1 rounded disabled:opacity-30"
                  style={{ background: 'var(--border-lt)', color: 'var(--slate)' }}>下页 →</button>
        </div>
      )}
    </div>
  )
}
