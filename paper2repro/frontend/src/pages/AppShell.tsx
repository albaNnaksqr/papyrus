import { useSearchParams, useNavigate } from 'react-router-dom'
import { useTasks } from '../hooks/useTasks'
import { deleteTask } from '../api/client'
import TaskSidebar from '../components/TaskSidebar'
import Dashboard from '../components/Dashboard'
import TaskDetail from '../components/task/TaskDetail'

export default function AppShell() {
  const { tasks, refresh } = useTasks()
  const [params] = useSearchParams()
  const nav = useNavigate()
  const activeTaskId = params.get('task')

  async function handleDelete(taskId: string) {
    await deleteTask(taskId)
    refresh()
    if (activeTaskId === taskId) nav('/app')
  }

  return (
    <div className="h-screen flex flex-col" style={{ background: 'var(--bg)' }}>
      {/* TopBar */}
      <header className="shrink-0 h-12 flex items-center justify-between px-5 shadow-sm z-10"
              style={{ background: 'rgba(255,255,255,0.9)', backdropFilter: 'blur(12px)', borderBottom: '1px solid var(--border-lt)' }}>
        <button
          onClick={() => nav('/')}
          className="flex items-center gap-2 rounded-lg px-1 py-1 transition-colors"
          title="返回首页"
        >
          <div className="w-6 h-6 rounded-lg flex items-center justify-center text-white text-xs font-bold"
               style={{ background: 'linear-gradient(135deg,#2563eb,#60a5fa)' }}>P</div>
          <span className="font-bold text-sm" style={{ color: 'var(--navy)' }}>paper2repro</span>
          <span className="text-xs px-2 py-0.5 rounded-full font-semibold"
                style={{ background: 'var(--blue-lt)', color: 'var(--blue)' }}>Beta</span>
        </button>
        <button onClick={() => nav('/app')}
                className="text-xs font-semibold px-3 py-1.5 rounded-lg text-white"
                style={{ background: 'var(--blue)' }}>
          + 新建任务
        </button>
      </header>

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        <TaskSidebar tasks={tasks} onNewTask={() => nav('/app')} onDelete={handleDelete} />

        <main className={`flex-1 ${activeTaskId ? 'overflow-hidden' : 'overflow-auto'}`}>
          {!activeTaskId ? (
            <Dashboard tasks={tasks} onTaskCreated={refresh} />
          ) : (
            <TaskDetail key={activeTaskId} taskId={activeTaskId} />
          )}
        </main>
      </div>
    </div>
  )
}
