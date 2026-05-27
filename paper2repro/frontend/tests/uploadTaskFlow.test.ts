import assert from 'node:assert/strict'
import { runUploadTaskFlow } from '../src/lib/uploadTaskFlow'

const phases: string[] = []
const navigations: string[] = []
let refreshed = false

const task = await runUploadTaskFlow({
  file: { name: 'paper.pdf' },
  fast: true,
  noCritique: false,
  setPhase: phase => phases.push(phase),
  uploadPdf: async file => {
    assert.deepEqual(file, { name: 'paper.pdf' })
    return { path: 'papers/paper.pdf', filename: 'paper.pdf' }
  },
  createTask: async params => {
    assert.deepEqual(params, {
      pdf_path: 'papers/paper.pdf',
      fast: true,
      no_critique: false,
    })
    return {
      task_id: 'paper_12345678',
      status: 'pending',
      created_at: '2026-05-20T00:00:00Z',
    }
  },
  navigate: url => navigations.push(url),
  onTaskCreated: () => {
    refreshed = true
  },
})

assert.deepEqual(phases, ['uploading', 'creating', 'opening'])
assert.deepEqual(navigations, ['/app?task=paper_12345678'])
assert.equal(refreshed, true)
assert.equal(task.task_id, 'paper_12345678')
