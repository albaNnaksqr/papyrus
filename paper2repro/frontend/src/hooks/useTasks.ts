import { useState, useEffect, useCallback } from 'react'
import { listTasks, Task } from '../api/client'

export function useTasks(pollIntervalMs = 2000) {
  const [tasks, setTasks] = useState<Task[]>([])
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const data = await listTasks()
      setTasks([...data].reverse())
      setError(null)
    } catch (e) {
      setError(String(e))
    }
  }, [])

  useEffect(() => {
    refresh()
    const iv = setInterval(refresh, pollIntervalMs)
    return () => clearInterval(iv)
  }, [refresh, pollIntervalMs])

  return { tasks, error, refresh }
}
