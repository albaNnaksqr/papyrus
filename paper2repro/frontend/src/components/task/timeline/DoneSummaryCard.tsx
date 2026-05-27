import { CircleCheck, CircleX, CirclePause } from 'lucide-react'

interface Props {
  status: string
  fileCount: number
  ts?: string
  durationMs?: number
  errorMessage?: string
}

function fmtDuration(ms?: number): string {
  if (!ms || ms < 0) return ''
  const sec = Math.floor(ms / 1000)
  const m = Math.floor(sec / 60)
  const s = sec % 60
  if (m < 60) return `${m} 分 ${s} 秒`
  return `${Math.floor(m / 60)} 时 ${m % 60} 分`
}

export default function DoneSummaryCard({ status, fileCount, ts, durationMs, errorMessage }: Props) {
  const isDone = status === 'done'
  const isError = status === 'error'

  const Icon = isDone ? CircleCheck : isError ? CircleX : CirclePause
  const title = isDone ? '完成' : isError ? '失败' : '已停止'
  const color = isDone ? 'var(--green)' : isError ? 'var(--red)' : 'var(--muted)'
  const bg = isDone ? 'var(--green-lt)' : isError ? 'var(--red-lt)' : 'var(--border-lt)'

  return (
    <div className="rounded-lg border shadow-sm px-4 py-3 flex items-start gap-3"
         style={{
           background: bg,
           borderColor: 'var(--border-lt)',
           borderLeft: `3px solid ${color}`,
         }}>
      <Icon size={18} className="shrink-0 mt-0.5" style={{ color }} />
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2 flex-wrap">
          <h4 className="text-sm font-bold" style={{ color }}>{title}</h4>
          {isDone && <span className="text-xs" style={{ color: 'var(--slate)' }}>
            · {fileCount} 个文件
          </span>}
          {durationMs && <span className="text-xs" style={{ color: 'var(--slate)' }}>· 用时 {fmtDuration(durationMs)}</span>}
          {ts && <span className="text-[10px] ml-auto" style={{ color: 'var(--muted)' }}>{ts}</span>}
        </div>
        {errorMessage && (
          <p className="mt-2 text-xs mono" style={{ color: 'var(--red)' }}>{errorMessage}</p>
        )}
      </div>
    </div>
  )
}
