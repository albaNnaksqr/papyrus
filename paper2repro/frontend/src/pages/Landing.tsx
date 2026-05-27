import { useNavigate } from 'react-router-dom'
import { useTasks } from '../hooks/useTasks'
import { buildDashboardSummary, buildLandingStatItems, type LandingStatTone } from '../lib/dashboardSummary'

const STAT_TONE: Record<LandingStatTone, { bg: string; color: string }> = {
  blue: { bg: 'var(--blue-lt)', color: 'var(--blue)' },
  amber: { bg: 'var(--amber-lt)', color: '#92400e' },
  green: { bg: 'var(--green-lt)', color: '#065f46' },
  red: { bg: 'var(--red-lt)', color: 'var(--red)' },
}

export default function Landing() {
  const nav = useNavigate()
  const { tasks } = useTasks(5000)
  const stats = buildLandingStatItems(buildDashboardSummary(tasks).stats)

  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-8 px-6"
         style={{ background: 'var(--bg)' }}>
      <div className="relative">
        <div className="w-20 h-20 rounded-3xl flex items-center justify-center text-white text-4xl font-black shadow-lg"
             style={{ background: 'linear-gradient(135deg,#2563eb,#60a5fa)' }}>
          P
        </div>
        <div className="absolute -bottom-1 -right-1 w-6 h-6 rounded-full flex items-center justify-center"
             style={{ background: 'var(--green)' }}>
          <svg width="12" height="12" fill="none" stroke="white" strokeWidth="3" viewBox="0 0 24 24">
            <polyline points="20 6 9 17 4 12" />
          </svg>
        </div>
      </div>

      <div className="text-center">
        <h1 className="text-5xl font-extrabold tracking-tight" style={{ color: 'var(--navy)' }}>
          paper2repro
        </h1>
        <p className="mt-3 text-lg font-medium" style={{ color: 'var(--muted)' }}>
          输入一篇论文 PDF · 输出可运行代码 · 自动积累训练语料
        </p>
      </div>

      <div className="flex gap-3 flex-wrap justify-center">
        {[
          { label: '多 Agent 协同', bg: 'var(--blue-lt)', color: 'var(--blue)' },
          { label: '全流程自动化', bg: 'var(--green-lt)', color: '#065f46' },
          { label: '语料自动积累', bg: 'var(--amber-lt)', color: '#92400e' },
        ].map(t => (
          <span key={t.label} className="px-3 py-1.5 rounded-full text-xs font-semibold"
                style={{ background: t.bg, color: t.color }}>{t.label}</span>
        ))}
      </div>

      <button
        onClick={() => nav('/app')}
        className="w-full max-w-3xl rounded-lg px-4 py-3 shadow-sm transition-colors text-left"
        style={{ background: 'rgba(255,255,255,0.86)', border: '1px solid var(--border-lt)' }}
      >
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {stats.map(item => {
            const tone = STAT_TONE[item.tone]
            return (
              <div key={item.label} className="flex items-center justify-between gap-3 rounded-md px-3 py-2" style={{ background: tone.bg }}>
                <span className="text-xs font-semibold" style={{ color: tone.color }}>{item.label}</span>
                <span className="text-lg font-extrabold tabular-nums" style={{ color: tone.color }}>{item.value}</span>
              </div>
            )
          })}
        </div>
      </button>

      <button
        onClick={() => nav('/app')}
        className="mt-4 px-10 py-3.5 rounded-2xl text-white font-bold text-base shadow-md transition-all hover:shadow-lg hover:scale-105 active:scale-95"
        style={{ background: 'linear-gradient(135deg,#2563eb,#60a5fa)' }}>
        开始使用 →
      </button>

      <p className="text-xs" style={{ color: 'var(--muted)' }}>
        本地运行 · 数据不出本机
      </p>
    </div>
  )
}
