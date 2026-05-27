import type { Task } from '../api/client'

export type UploadPhase = 'idle' | 'uploading' | 'creating' | 'opening'

export const UPLOAD_PHASE_TEXT: Record<UploadPhase, string> = {
  idle: '开始生成',
  uploading: '正在上传 PDF...',
  creating: '上传完成，正在创建任务...',
  opening: '任务已创建，正在打开任务页面...',
}

interface UploadedPdf {
  path: string
  filename: string
}

interface CreateTaskParams {
  pdf_path: string
  fast: boolean
  no_critique: boolean
}

interface RunUploadTaskFlowParams<FileLike> {
  file: FileLike
  fast: boolean
  noCritique: boolean
  setPhase: (phase: UploadPhase) => void
  uploadPdf: (file: FileLike) => Promise<UploadedPdf>
  createTask: (params: CreateTaskParams) => Promise<Task>
  navigate: (url: string) => void
  onTaskCreated: () => void
}

export async function runUploadTaskFlow<FileLike>({
  file,
  fast,
  noCritique,
  setPhase,
  uploadPdf,
  createTask,
  navigate,
  onTaskCreated,
}: RunUploadTaskFlowParams<FileLike>): Promise<Task> {
  setPhase('uploading')
  const { path } = await uploadPdf(file)

  setPhase('creating')
  const task = await createTask({ pdf_path: path, fast, no_critique: noCritique })

  setPhase('opening')
  navigate(`/app?task=${task.task_id}`)
  onTaskCreated()
  return task
}
