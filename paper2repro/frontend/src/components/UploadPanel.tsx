import { useState, useRef, useEffect, DragEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { uploadPdf, createTask } from '../api/client'
import { runUploadTaskFlow, UPLOAD_PHASE_TEXT, type UploadPhase } from '../lib/uploadTaskFlow'

interface Props {
  onTaskCreated: () => void
  variant?: 'standalone' | 'embedded'
}

export default function UploadPanel({ onTaskCreated, variant = 'standalone' }: Props) {
  const nav = useNavigate()
  const mountedRef = useRef(true)
  useEffect(() => () => { mountedRef.current = false }, [])
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [fast, setFast] = useState(false)
  const [noCritique, setNoCritique] = useState(false)
  const [phase, setPhase] = useState<UploadPhase>('idle')
  const [error, setError] = useState<string | null>(null)
  const loading = phase !== 'idle'

  function handleFile(f: File) {
    if (!f.name.toLowerCase().endsWith('.pdf')) {
      setError('请选择 PDF 文件')
      return
    }
    if (f.size > 200 * 1024 * 1024) {
      setError('文件不能超过 200MB')
      return
    }
    setError(null)
    setFile(f)
    setPhase('idle')
  }

  function onDrop(e: DragEvent) {
    e.preventDefault()
    setDragging(false)
    const f = e.dataTransfer.files[0]
    if (f) handleFile(f)
  }

  async function submit() {
    if (!file) return
    setError(null)
    let completed = false
    try {
      await runUploadTaskFlow({
        file,
        fast,
        noCritique,
        setPhase: nextPhase => {
          if (mountedRef.current) setPhase(nextPhase)
        },
        uploadPdf,
        createTask,
        navigate: url => {
          if (mountedRef.current) nav(url)
        },
        onTaskCreated: () => {
          if (mountedRef.current) onTaskCreated()
        },
      })
      completed = true
    } catch (e) {
      if (!mountedRef.current) return
      setError(e instanceof Error ? e.message : String(e))
      setPhase('idle')
    } finally {
      if (mountedRef.current && !completed) setPhase('idle')
    }
  }

  const embedded = variant === 'embedded'

  return (
    <div className={embedded ? '' : 'max-w-lg mx-auto mt-16 px-6'}>
      <div
        className={`${embedded ? 'rounded-lg p-5' : 'rounded-2xl p-8 shadow-md'}`}
        style={{ background: 'var(--surface)', border: '1px solid var(--border-lt)' }}
      >
        <h2 className="text-lg font-bold mb-1" style={{ color: 'var(--navy)' }}>新建复现任务</h2>
        <p className="text-sm mb-6" style={{ color: 'var(--muted)' }}>上传论文 PDF，全流程自动完成</p>

        {/* Drop zone */}
        <div
          onClick={() => inputRef.current?.click()}
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={`border-2 border-dashed rounded-xl ${embedded ? 'p-5' : 'p-8'} text-center cursor-pointer transition-all mb-5`}
          style={{ borderColor: dragging ? 'var(--blue)' : file ? 'var(--green)' : 'var(--border)', background: dragging ? 'var(--blue-lt)' : 'transparent' }}>
          <input ref={inputRef} type="file" accept=".pdf" className="hidden"
                 onChange={e => e.target.files?.[0] && handleFile(e.target.files[0])} />
          <svg className="w-8 h-8 mx-auto mb-3" style={{ color: 'var(--muted)' }} fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
            <path d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m6.75 12l-3-3m0 0l-3 3m3-3v6m-1.5-15H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
          </svg>
          {file
            ? <p className="text-sm font-medium" style={{ color: 'var(--green)' }}>✓ {file.name}</p>
            : <>
                <p className="text-sm" style={{ color: 'var(--slate)' }}>拖放 PDF，或 <span style={{ color: 'var(--blue)', fontWeight: 600 }}>点击选择</span></p>
                <p className="text-xs mt-1" style={{ color: 'var(--muted)' }}>最大 200MB</p>
              </>
          }
        </div>

        {loading && (
          <div
            className="mb-5 rounded-lg px-3 py-2 text-xs font-semibold"
            style={{
              background: phase === 'creating' || phase === 'opening' ? '#ecfdf5' : 'var(--blue-lt)',
              color: phase === 'creating' || phase === 'opening' ? 'var(--green)' : 'var(--blue)',
              border: `1px solid ${phase === 'creating' || phase === 'opening' ? '#bbf7d0' : '#bfdbfe'}`,
            }}
          >
            {UPLOAD_PHASE_TEXT[phase]}
          </div>
        )}

        {/* Options */}
        <div className="flex gap-5 mb-6">
          {[
            { label: '快速模式', value: fast, set: setFast },
            { label: '跳过批判', value: noCritique, set: setNoCritique },
          ].map(o => (
            <label key={o.label} className="flex items-center gap-2 text-sm cursor-pointer" style={{ color: 'var(--slate)' }}>
              <input type="checkbox" checked={o.value} onChange={e => o.set(e.target.checked)}
                     className="rounded accent-blue-600" />
              {o.label}
            </label>
          ))}
        </div>

        {error && <p className="text-xs mb-4" style={{ color: 'var(--red)' }}>{error}</p>}

        <button
          onClick={submit}
          disabled={!file || loading}
          className="w-full py-2.5 rounded-xl text-sm font-bold text-white transition-all disabled:opacity-50"
          style={{ background: 'var(--blue)' }}>
          {UPLOAD_PHASE_TEXT[phase]}
        </button>
      </div>
    </div>
  )
}
