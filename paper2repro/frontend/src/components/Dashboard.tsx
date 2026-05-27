import { useNavigate } from 'react-router-dom'
import { Activity, AlertTriangle, CheckCircle2, Clock3, FileText, ArrowRight } from 'lucide-react'
import type { Task } from '../api/client'
import {
  buildDashboardSummary,
  getTaskStatusLabel,
  getTaskTitle,
} from '../lib/dashboardSummary'
import UploadPanel from './UploadPanel'

interface Props {
  tasks: Task[]
  onTaskCreated: () => void
}

const STATUS_STYLE: Record<Task['status'], { bg: string; color: string; dot: string }> = {
  pending: { bg: '#eff6ff', color: 'var(--blue)', dot: 'var(--blue)' },
  running: { bg: '#eff6ff', color: 'var(--blue)', dot: 'var(--blue)' },
  done: { bg: '#ecfdf5', color: 'var(--green)', dot: 'var(--green)' },
  error: { bg: '#fef2f2', color: 'var(--red)', dot: 'var(--red)' },
  interrupted: { bg: '#f8fafc', color: 'var(--slate)', dot: 'var(--muted)' },
}

function formatCreatedAt(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function StatCard({
  label,
  value,
  icon: Icon,
  accent,
  bg,
}: {
  label: string
  value: number
  icon: typeof FileText
  accent: string
  bg: string
}) {
  return (
    <div className="rounded-lg px-4 py-3" style={{ background: 'var(--surface)', border: '1px solid var(--border-lt)' }}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold" style={{ color: 'var(--muted)' }}>{label}</span>
        <span className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: bg, color: accent }}>
          <Icon size={16} />
        </span>
      </div>
      <div className="text-2xl font-extrabold mt-1" style={{ color: 'var(--navy)' }}>{value}</div>
    </div>
  )
}

function TaskRow({ task, compact = false }: { task: Task; compact?: boolean }) {
  const nav = useNavigate()
  const style = STATUS_STYLE[task.status]
  return (
    <button
      onClick={() => nav(`/app?task=${task.task_id}`)}
      className="w-full text-left rounded-lg px-3 py-3 transition-colors"
      style={{ background: 'var(--surface)', border: '1px solid var(--border-lt)' }}
    >
      <div className="flex items-start gap-3">
        <span className="mt-1.5 w-2 h-2 rounded-full shrink-0" style={{ background: style.dot }} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold truncate" style={{ color: 'var(--navy)' }}>
              {getTaskTitle(task)}
            </span>
            <span
              className="shrink-0 text-[10px] px-2 py-0.5 rounded-full font-semibold"
              style={{ background: style.bg, color: style.color }}
            >
              {getTaskStatusLabel(task.status)}
            </span>
          </div>
          {!compact && (
            <div className="text-xs mt-1 mono truncate" style={{ color: 'var(--muted)' }}>
              {task.task_id}
            </div>
          )}
          <div className="text-xs mt-1" style={{ color: 'var(--muted)' }}>
            {formatCreatedAt(task.created_at)}
          </div>
        </div>
        <ArrowRight size={15} style={{ color: 'var(--muted)' }} />
      </div>
    </button>
  )
}

function TaskSection({
  title,
  tasks,
  empty,
  compact,
}: {
  title: string
  tasks: Task[]
  empty: string
  compact?: boolean
}) {
  return (
    <section>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-bold" style={{ color: 'var(--navy)' }}>{title}</h3>
        <span className="text-xs font-semibold" style={{ color: 'var(--muted)' }}>{tasks.length}</span>
      </div>
      <div className="space-y-2">
        {tasks.length > 0 ? (
          tasks.map(task => <TaskRow key={task.task_id} task={task} compact={compact} />)
        ) : (
          <div className="rounded-lg px-3 py-4 text-xs" style={{ background: 'var(--surface)', border: '1px solid var(--border-lt)', color: 'var(--muted)' }}>
            {empty}
          </div>
        )}
      </div>
    </section>
  )
}

export default function Dashboard({ tasks, onTaskCreated }: Props) {
  const summary = buildDashboardSummary(tasks)

  return (
    <div className="min-h-full p-5 lg:p-6">
      <div className="mx-auto max-w-7xl space-y-5">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-extrabold" style={{ color: 'var(--navy)' }}>任务总览</h1>
            <p className="text-xs mt-1" style={{ color: 'var(--muted)' }}>
              {summary.stats.running > 0 ? `${summary.stats.running} 个任务正在处理` : '当前没有运行中的任务'}
            </p>
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard label="全部任务" value={summary.stats.total} icon={FileText} accent="var(--blue)" bg="var(--blue-lt)" />
          <StatCard label="运行中" value={summary.stats.running} icon={Activity} accent="var(--blue)" bg="var(--blue-lt)" />
          <StatCard label="已完成" value={summary.stats.done} icon={CheckCircle2} accent="var(--green)" bg="var(--green-lt)" />
          <StatCard label="需关注" value={summary.stats.failed} icon={AlertTriangle} accent="var(--red)" bg="var(--red-lt)" />
        </div>

        <div className="grid gap-5 xl:grid-cols-[minmax(360px,0.9fr)_minmax(0,1.4fr)]">
          <div className="space-y-5">
            <UploadPanel onTaskCreated={onTaskCreated} variant="embedded" />
            <TaskSection
              title="需关注"
              tasks={summary.attentionTasks}
              empty="没有失败或中断的任务"
              compact
            />
          </div>

          <div className="space-y-5">
            <TaskSection
              title="当前任务"
              tasks={summary.activeTasks}
              empty="没有等待中或运行中的任务"
            />
            <section>
              <div className="flex items-center gap-2 mb-2">
                <Clock3 size={15} style={{ color: 'var(--muted)' }} />
                <h3 className="text-sm font-bold" style={{ color: 'var(--navy)' }}>最近任务</h3>
              </div>
              <div className="grid gap-2 lg:grid-cols-2">
                {summary.recentTasks.length > 0 ? (
                  summary.recentTasks.map(task => <TaskRow key={task.task_id} task={task} compact />)
                ) : (
                  <div className="rounded-lg px-3 py-4 text-xs" style={{ background: 'var(--surface)', border: '1px solid var(--border-lt)', color: 'var(--muted)' }}>
                    暂无任务
                  </div>
                )}
              </div>
            </section>
          </div>
        </div>
      </div>
    </div>
  )
}
