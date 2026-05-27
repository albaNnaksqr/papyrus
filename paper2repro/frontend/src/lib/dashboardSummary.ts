import type { Task } from '../api/client'

export interface DashboardStats {
  total: number
  running: number
  done: number
  failed: number
}

export interface DashboardSummary {
  stats: DashboardStats
  activeTasks: Task[]
  attentionTasks: Task[]
  recentTasks: Task[]
}

export type LandingStatTone = 'blue' | 'amber' | 'green' | 'red'

export interface LandingStatItem {
  label: string
  value: number
  tone: LandingStatTone
}

interface BuildDashboardSummaryOptions {
  recentLimit?: number
  now?: Date
}

const STATUS_LABELS: Record<Task['status'], string> = {
  pending: '等待中',
  running: '运行中',
  done: '完成',
  error: '失败',
  interrupted: '中断',
}

export function getTaskStatusLabel(status: Task['status']): string {
  return STATUS_LABELS[status]
}

export function getTaskTitle(task: Pick<Task, 'task_id' | 'pdf_path'>): string {
  const rawName = task.pdf_path?.split('/').pop()?.replace(/\.pdf$/i, '') || task.task_id
  return rawName.length > 34 ? `${rawName.slice(0, 32)}...` : rawName
}

function newestFirst(a: Task, b: Task): number {
  return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
}

export function buildDashboardSummary(
  tasks: readonly Task[],
  options: BuildDashboardSummaryOptions = {},
): DashboardSummary {
  const recentLimit = options.recentLimit ?? 8
  const sorted = [...tasks].sort(newestFirst)
  const activeTasks = sorted.filter(task => task.status === 'running' || task.status === 'pending')
  const attentionTasks = sorted.filter(task => task.status === 'error' || task.status === 'interrupted')

  return {
    stats: {
      total: tasks.length,
      running: activeTasks.length,
      done: tasks.filter(task => task.status === 'done').length,
      failed: attentionTasks.length,
    },
    activeTasks,
    attentionTasks,
    recentTasks: sorted.slice(0, recentLimit),
  }
}

export function buildLandingStatItems(stats: DashboardStats): LandingStatItem[] {
  return [
    { label: '全部任务', value: stats.total, tone: 'blue' },
    { label: '运行中', value: stats.running, tone: 'amber' },
    { label: '已完成', value: stats.done, tone: 'green' },
    { label: '需关注', value: stats.failed, tone: 'red' },
  ]
}
