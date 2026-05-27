import {
  createOfflineTask,
  deleteOfflineTask,
  getOfflineArtifactText,
  getOfflineTask,
  listOfflineTasks,
  stopOfflineTask,
  uploadOfflinePdf,
} from '../demo/offlineDemo'
import type { SSEEvent } from '../hooks/useSSE'

const BASE = ''  // same origin in dev (Vite proxies /api → :8000)

export interface Task {
  task_id: string
  status: 'pending' | 'running' | 'done' | 'error' | 'interrupted'
  created_at: string
  pdf_path?: string | null
}

export interface TaskDetail extends Task {
  artifacts: string[]
  events?: SSEEvent[]
}

export async function listTasks(): Promise<Task[]> {
  const offline = listOfflineTasks()
  if (offline) return offline
  const res = await fetch(`${BASE}/api/tasks`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function getTask(taskId: string): Promise<TaskDetail> {
  const offline = getOfflineTask(taskId)
  if (offline) return offline
  const res = await fetch(`${BASE}/api/tasks/${taskId}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function uploadPdf(file: File): Promise<{ path: string; filename: string }> {
  const offline = uploadOfflinePdf(file)
  if (offline) return offline
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE}/api/upload`, { method: 'POST', body: form })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function createTask(params: {
  pdf_path: string
  fast: boolean
  no_critique: boolean
}): Promise<Task> {
  const offline = createOfflineTask(params)
  if (offline) return offline
  const res = await fetch(`${BASE}/api/tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function deleteTask(taskId: string): Promise<void> {
  if (deleteOfflineTask(taskId)) return
  const res = await fetch(`${BASE}/api/tasks/${taskId}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(await res.text())
}

export async function stopTask(taskId: string): Promise<void> {
  if (stopOfflineTask(taskId)) return
  const res = await fetch(`${BASE}/api/tasks/${taskId}/stop`, { method: 'POST' })
  if (!res.ok) throw new Error(await res.text())
}

export async function getArtifactText(taskId: string, artifactPath: string): Promise<string> {
  const offline = getOfflineArtifactText(taskId, artifactPath)
  if (offline != null) return offline
  const res = await fetch(`${BASE}/api/tasks/${taskId}/artifacts/${encodeURIComponent(artifactPath)}`)
  if (!res.ok) throw new Error(await res.text())
  return res.text()
}

export function getExportFilename(taskId: string): string {
  return `paper2repro_${taskId}_artifacts.zip`
}

export async function downloadTaskArchive(taskId: string, filename?: string): Promise<void> {
  const res = await fetch(`${BASE}/api/tasks/${taskId}/export`)
  if (!res.ok) {
    throw new Error(await res.text())
  }
  const blob = await res.blob()
  const href = URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = href
  link.download = filename ?? getExportFilename(taskId)
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(href)
}
