import { useState, useEffect } from 'react'
import {
  getOfflineDemoPayload,
  getOfflineTaskEvents,
  recordOfflineReplayEvent,
  resetOfflineReplayTask,
} from '../demo/offlineDemo'

export interface SSEEvent {
  type: 'progress' | 'file_written' | 'done' | 'error' | 'interrupted'
  pct?: number
  message?: string
  phase?: string
  path?: string
  section_ref?: string
  summary?: string
  ts?: string
}

export function useSSE(taskId: string | null, replayKey = 0) {
  const [events, setEvents] = useState<SSEEvent[]>([])
  const [connected, setConnected] = useState(false)
  const [done, setDone] = useState(false)

  useEffect(() => {
    if (!taskId) return
    setEvents([])
    setDone(false)

    const offline = getOfflineDemoPayload()
    if (offline) {
      const taskEvents = getOfflineTaskEvents(taskId)
      if (offline.mode === 'static') {
        setEvents(taskEvents)
        setConnected(false)
        return
      }

      resetOfflineReplayTask(taskId)
      setConnected(true)
      let cancelled = false
      let timer: number | undefined
      let index = 0

      const emit = () => {
        if (cancelled) return
        const evt = taskEvents[index]
        if (!evt) {
          setConnected(false)
          setDone(true)
          return
        }

        recordOfflineReplayEvent(taskId, index, evt)
        setEvents(prev => [...prev, evt])
        index += 1

        const terminal = evt.type === 'done' || evt.type === 'error' || evt.type === 'interrupted'
        if (terminal || index >= taskEvents.length) {
          setConnected(false)
          setDone(true)
          return
        }

        timer = window.setTimeout(emit, offline.replayDelayMs)
      }

      timer = window.setTimeout(emit, Math.min(offline.replayDelayMs, 500))
      return () => {
        cancelled = true
        if (timer != null) window.clearTimeout(timer)
        setConnected(false)
      }
    }

    const es = new EventSource(`/api/tasks/${taskId}/events`)

    es.onopen = () => setConnected(true)

    es.onmessage = (e) => {
      try {
        const evt = JSON.parse(e.data) as SSEEvent
        setEvents(prev => [...prev, evt])
        if (evt.type === 'done' || evt.type === 'error' || evt.type === 'interrupted') {
          setDone(true)
          es.close()
          setConnected(false)
        }
      } catch (err) {
        console.error('[useSSE] failed to parse SSE event:', e.data, err)
      }
    }

    es.onerror = () => {
      setConnected(false)
    }

    return () => {
      es.close()
      setConnected(false)
    }
  }, [taskId, replayKey])

  return { events, connected, done }
}
