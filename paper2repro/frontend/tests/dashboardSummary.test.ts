import assert from 'node:assert/strict'
import {
  buildDashboardSummary,
  buildLandingStatItems,
  getTaskTitle,
  getTaskStatusLabel,
} from '../src/lib/dashboardSummary'

const tasks = [
  { task_id: 'paper_done_old', status: 'done', created_at: '2026-05-18T09:00:00Z', pdf_path: 'papers/old.pdf' },
  { task_id: 'paper_error', status: 'error', created_at: '2026-05-19T10:00:00Z', pdf_path: 'papers/broken.pdf' },
  { task_id: 'paper_running', status: 'running', created_at: '2026-05-20T11:00:00Z', pdf_path: 'papers/running.pdf' },
  { task_id: 'paper_pending', status: 'pending', created_at: '2026-05-20T12:00:00Z', pdf_path: 'papers/pending.pdf' },
  { task_id: 'paper_done_new', status: 'done', created_at: '2026-05-20T13:00:00Z', pdf_path: 'papers/new.pdf' },
] as const

const summary = buildDashboardSummary(tasks, { now: new Date('2026-05-20T14:00:00Z') })

assert.deepEqual(summary.stats, {
  total: 5,
  running: 2,
  done: 2,
  failed: 1,
})
assert.deepEqual(summary.activeTasks.map(task => task.task_id), ['paper_pending', 'paper_running'])
assert.deepEqual(summary.attentionTasks.map(task => task.task_id), ['paper_error'])
assert.deepEqual(summary.recentTasks.map(task => task.task_id), [
  'paper_done_new',
  'paper_pending',
  'paper_running',
  'paper_error',
  'paper_done_old',
])
assert.equal(getTaskTitle(tasks[4]), 'new')
assert.equal(getTaskStatusLabel('pending'), '等待中')
assert.deepEqual(buildLandingStatItems(summary.stats), [
  { label: '全部任务', value: 5, tone: 'blue' },
  { label: '运行中', value: 2, tone: 'amber' },
  { label: '已完成', value: 2, tone: 'green' },
  { label: '需关注', value: 1, tone: 'red' },
])
