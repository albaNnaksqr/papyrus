import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Task } from '../api/client'

interface Props {
  tasks: Task[]
  onNewTask: () => void
  onDelete: (taskId: string) => Promise<void>
}

const STATUS_DOT: Record<string, string> = {
  done:        'bg-green-500',
  running:     'bg-blue-500 animate-pulse',
  pending:     'bg-blue-400 animate-pulse',
  error:       'bg-red-500',
  interrupted: 'bg-slate-400',
}

function taskTitle(task: Task): string {
  const name = task.pdf_path?.split('/').pop()?.replace('.pdf', '') ?? task.task_id
  return name.length > 28 ? name.slice(0, 26) + '…' : name
}

export default function TaskSidebar({ tasks, onNewTask, onDelete }: Props) {
  const nav = useNavigate()
  const [params] = useSearchParams()
  const activeId = params.get('task')
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const canDelete = (t: Task) => t.status !== 'running' && t.status !== 'pending'

  async function handleDelete(e: React.MouseEvent, taskId: string) {
    e.stopPropagation()
    if (!window.confirm('删除此任务及其所有输出文件？此操作不可恢复。')) return
    setDeletingId(taskId)
    try {
      await onDelete(taskId)
    } catch (err) {
      alert(err instanceof Error ? err.message : '删除失败')
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <aside className="w-52 shrink-0 flex flex-col border-r"
           style={{ background: 'var(--surface)', borderColor: 'var(--border-lt)' }}>

      {/* New task button */}
      <div className="p-3">
        <button
          onClick={onNewTask}
          className="w-full text-xs font-semibold py-2 rounded-lg text-white transition-colors"
          style={{ background: 'var(--blue)' }}>
          + 新建任务
        </button>
      </div>

      {/* Task list */}
      <div className="flex-1 overflow-y-auto px-2 pb-2 space-y-0.5">
        {tasks.length === 0 && (
          <p className="text-xs px-2 py-4 text-center" style={{ color: 'var(--muted)' }}>
            暂无任务
          </p>
        )}
        {tasks.map(t => (
          <div key={t.task_id} className="relative"
               onMouseEnter={() => setHoveredId(t.task_id)}
               onMouseLeave={() => setHoveredId(null)}>
            <button
              onClick={() => nav(`/app?task=${t.task_id}`)}
              className="w-full text-left rounded-lg px-2 py-2 pr-7 transition-colors"
              style={{
                background: t.task_id === activeId ? 'var(--blue-lt)' : 'transparent',
                border: t.task_id === activeId ? '1px solid #bfdbfe' : '1px solid transparent',
              }}>
              <div className="text-xs font-medium truncate" style={{ color: 'var(--navy)' }}>
                {taskTitle(t)}
              </div>
              <div className="flex items-center gap-1.5 mt-1">
                <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${STATUS_DOT[t.status] ?? 'bg-slate-400'}`} />
                <span className="text-xs" style={{
                  color: t.status === 'done' ? 'var(--green)'
                       : t.status === 'error' ? 'var(--red)'
                       : t.status === 'running' || t.status === 'pending' ? 'var(--blue)'
                       : 'var(--muted)'
                }}>
                  {t.status === 'done' ? '完成'
                   : t.status === 'running' ? '运行中'
                   : t.status === 'pending' ? '等待中'
                   : t.status === 'error' ? '失败'
                   : '中断'}
                </span>
              </div>
            </button>

            {/* Delete button — visible on hover, hidden for running/pending */}
            {hoveredId === t.task_id && canDelete(t) && (
              <button
                onClick={e => handleDelete(e, t.task_id)}
                disabled={deletingId === t.task_id}
                title="删除任务"
                className="absolute right-1 top-1/2 -translate-y-1/2 w-5 h-5 rounded flex items-center justify-center transition-colors disabled:opacity-40"
                style={{ background: '#fee2e2', color: '#dc2626' }}>
                {deletingId === t.task_id ? '…' : '×'}
              </button>
            )}
          </div>
        ))}
      </div>

      {/* Bottom stats */}
      <div className="border-t px-3 py-3 grid grid-cols-2 gap-2"
           style={{ borderColor: 'var(--border-lt)' }}>
        <div className="text-center">
          <div className="text-sm font-extrabold" style={{ color: 'var(--navy)' }}>
            {tasks.filter(t => t.status === 'done').length}
          </div>
          <div className="text-xs" style={{ color: 'var(--muted)' }}>论文</div>
        </div>
        <div className="text-center">
          <div className="text-sm font-extrabold" style={{ color: 'var(--blue)' }}>
            {tasks.filter(t => t.status === 'running').length}
          </div>
          <div className="text-xs" style={{ color: 'var(--muted)' }}>运行中</div>
        </div>
      </div>
    </aside>
  )
}
