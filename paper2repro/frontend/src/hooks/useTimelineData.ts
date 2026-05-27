import { useEffect, useState } from 'react'
import yaml from 'js-yaml'
import { getArtifactText, TaskDetail } from '../api/client'

export interface DocIndex {
  document_type?: string
  segmentation_strategy?: string
  total_segments?: number
  total_chars?: number
}

export interface CritiqueItem {
  claim?: string
  trap?: string
  dep?: string
  section?: string
  quote?: string
  critique_type?: string
  code_hint?: string
  mitigation?: string
}

export interface CritiqueData {
  must_implement: CritiqueItem[]
  implementation_traps: CritiqueItem[]
  external_deps: CritiqueItem[]
  complexity_score?: number
}

export interface PlanFile {
  path: string
  purpose?: string
}

export interface PlanData {
  root?: string
  files: PlanFile[]
  raw_yaml_valid: boolean
}

export interface TimelineData {
  parsed: DocIndex | null
  critique: CritiqueData | null
  plan: PlanData | null
  loading: boolean
}

const DOC_INDEX_PATH = 'document_segments/document_index.json'
const CRITIQUE_PATH = 'critique_structured.json'
const PLAN_PATH = 'initial_plan.txt'

function parsePlan(text: string): PlanData {
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const doc = yaml.load(text) as any
    const fs = doc?.file_structure
    return {
      root: fs?.root,
      files: Array.isArray(fs?.files) ? fs.files.filter((f: PlanFile) => f?.path) : [],
      raw_yaml_valid: true,
    }
  } catch {
    return { files: [], raw_yaml_valid: false }
  }
}

export function useTimelineData(detail: TaskDetail | null): TimelineData {
  const [parsed, setParsed] = useState<DocIndex | null>(null)
  const [critique, setCritique] = useState<CritiqueData | null>(null)
  const [plan, setPlan] = useState<PlanData | null>(null)
  const [loading, setLoading] = useState(true)

  const artifacts = detail?.artifacts ?? []
  const hasParsed = artifacts.includes(DOC_INDEX_PATH)
  const hasCritique = artifacts.includes(CRITIQUE_PATH)
  const hasPlan = artifacts.includes(PLAN_PATH)
  const taskId = detail?.task_id

  useEffect(() => {
    if (!taskId) return
    let cancelled = false
    setLoading(true)
    const jobs: Promise<void>[] = []

    if (hasParsed && !parsed) {
      jobs.push(
        getArtifactText(taskId, DOC_INDEX_PATH)
          .then(text => { if (!cancelled) setParsed(JSON.parse(text)) })
          .catch(() => {})
      )
    }
    if (hasCritique && !critique) {
      jobs.push(
        getArtifactText(taskId, CRITIQUE_PATH)
          .then(text => { if (!cancelled) setCritique(JSON.parse(text)) })
          .catch(() => {})
      )
    }
    if (hasPlan && !plan) {
      jobs.push(
        getArtifactText(taskId, PLAN_PATH)
          .then(text => { if (!cancelled) setPlan(parsePlan(text)) })
          .catch(() => {})
      )
    }
    Promise.all(jobs).finally(() => { if (!cancelled) setLoading(false) })

    return () => { cancelled = true }
  }, [taskId, hasParsed, hasCritique, hasPlan])

  return { parsed, critique, plan, loading }
}
