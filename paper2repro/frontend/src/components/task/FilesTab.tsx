import { useState, useRef, useMemo, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { TaskDetail, getArtifactText } from '../../api/client'

interface Props {
  detail: TaskDetail
}

interface TreeNode {
  name: string
  path: string
  type: 'file' | 'dir'
  children: TreeNode[]
}

const CODE_EXTS = ['.py', '.ts', '.tsx', '.js', '.json', '.yaml', '.yml', '.toml', '.txt', '.md', '.sh']
const EXCLUDE_TOP = new Set(['logs', 'trajectory', 'document_segments'])
const EXCLUDE_FILES = new Set(['paper.pdf', 'planning_attempts.jsonl', 'github_download.txt', 'reference.txt'])

function fileIcon(name: string): string {
  if (name.endsWith('.py')) return '🐍'
  if (name.endsWith('.md')) return '📄'
  if (name.endsWith('.json')) return '📋'
  if (name.endsWith('.txt')) return '📝'
  return '📄'
}

function buildTree(paths: string[]): TreeNode[] {
  const dirMap = new Map<string, TreeNode>()
  const roots: TreeNode[] = []

  function getOrMakeDir(parts: string[], depth: number): TreeNode {
    const key = parts.slice(0, depth + 1).join('/')
    if (dirMap.has(key)) return dirMap.get(key)!
    const node: TreeNode = { name: parts[depth], path: key, type: 'dir', children: [] }
    dirMap.set(key, node)
    if (depth === 0) {
      roots.push(node)
    } else {
      getOrMakeDir(parts, depth - 1).children.push(node)
    }
    return node
  }

  for (const path of paths) {
    const parts = path.split('/')
    if (parts.length === 1) {
      roots.push({ name: parts[0], path, type: 'file', children: [] })
    } else {
      const parent = getOrMakeDir(parts, parts.length - 2)
      parent.children.push({ name: parts[parts.length - 1], path, type: 'file', children: [] })
    }
  }

  function sortNode(node: TreeNode) {
    node.children.sort((a, b) => {
      if (a.type !== b.type) return a.type === 'dir' ? -1 : 1
      return a.name.localeCompare(b.name)
    })
    node.children.forEach(sortNode)
  }
  roots.sort((a, b) => {
    if (a.type !== b.type) return a.type === 'dir' ? -1 : 1
    return a.name.localeCompare(b.name)
  })
  roots.forEach(sortNode)
  return roots
}

function collectAllDirs(nodes: TreeNode[], out: Set<string> = new Set()): Set<string> {
  for (const n of nodes) {
    if (n.type === 'dir') {
      out.add(n.path)
      collectAllDirs(n.children, out)
    }
  }
  return out
}

function pickDefaultFile(artifacts: string[]): string | null {
  const mds = artifacts.filter(p => p.toLowerCase().endsWith('.md'))
  if (mds.length === 0) return null
  const readme = mds.find(p => /(^|\/)readme\.md$/i.test(p))
  if (readme) return readme
  const paper = mds.find(p => /(^|\/)paper\.md$/i.test(p))
  if (paper) return paper
  // Prefer top-level markdown if any
  const topLevel = mds.find(p => !p.includes('/'))
  if (topLevel) return topLevel
  return mds[0]
}

interface TreeRowProps {
  node: TreeNode
  depth: number
  expanded: Set<string>
  setExpanded: React.Dispatch<React.SetStateAction<Set<string>>>
  selected: string | null
  onSelect: (path: string) => void
}

function TreeRow({ node, depth, expanded, setExpanded, selected, onSelect }: TreeRowProps) {
  const isOpen = expanded.has(node.path)

  function toggle() {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(node.path)) next.delete(node.path)
      else next.add(node.path)
      return next
    })
  }

  return (
    <>
      <button
        onClick={() => node.type === 'dir' ? toggle() : onSelect(node.path)}
        className="w-full text-left flex items-center gap-1 px-2 py-1 rounded text-xs transition-colors"
        style={{
          paddingLeft: `${8 + depth * 14}px`,
          background: node.type === 'file' && node.path === selected ? 'var(--blue-lt)' : 'transparent',
          color: node.type === 'file' && node.path === selected ? 'var(--blue)' : 'var(--slate)',
        }}>
        {node.type === 'dir' ? (
          <span style={{ color: 'var(--muted)', fontSize: '10px' }}>{isOpen ? '▾' : '▸'}</span>
        ) : null}
        <span>{node.type === 'dir' ? '📁' : fileIcon(node.name)}</span>
        <span className="mono truncate">{node.name}</span>
      </button>
      {node.type === 'dir' && isOpen && node.children.map(child => (
        <TreeRow key={child.path} node={child} depth={depth + 1}
                 expanded={expanded} setExpanded={setExpanded}
                 selected={selected} onSelect={onSelect} />
      ))}
    </>
  )
}

export default function FilesTab({ detail }: Props) {
  const reqRef = useRef(0)
  const [selected, setSelected] = useState<string | null>(null)
  const [content, setContent] = useState<string>('')
  const [loading, setLoading] = useState(false)

  const tree = useMemo(() => {
    const filtered = detail.artifacts.filter(p => {
      const topDir = p.split('/')[0]
      if (p.includes('/') && EXCLUDE_TOP.has(topDir)) return false
      const filename = p.split('/').pop() ?? ''
      if (EXCLUDE_FILES.has(filename)) return false
      return CODE_EXTS.some(ext => p.endsWith(ext))
    })
    return buildTree(filtered)
  }, [detail.artifacts])

  const [expanded, setExpanded] = useState<Set<string>>(() => collectAllDirs(tree))

  async function openFile(path: string) {
    const req = ++reqRef.current
    setSelected(path)
    setLoading(true)
    try {
      const text = await getArtifactText(detail.task_id, path)
      if (req !== reqRef.current) return
      setContent(text)
    } catch {
      if (req !== reqRef.current) return
      setContent('(无法加载文件内容)')
    } finally {
      if (req === reqRef.current) setLoading(false)
    }
  }

  // Auto-open a sensible default (README.md / paper.md / first .md)
  // when nothing is selected yet. Re-runs only when defaultFile changes
  // (e.g. when new artifacts arrive for a running task).
  const defaultFile = useMemo(() => pickDefaultFile(detail.artifacts), [detail.artifacts])
  useEffect(() => {
    if (selected) return
    if (!defaultFile) return
    openFile(defaultFile)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [defaultFile])

  const isMarkdown = selected?.toLowerCase().endsWith('.md') ?? false

  return (
    <div className="flex h-full overflow-hidden">
      {/* File tree */}
      <div className="w-60 shrink-0 border-r overflow-y-auto py-2"
           style={{ borderColor: 'var(--border-lt)', background: 'var(--surface)' }}>
        <p className="text-xs font-bold uppercase tracking-wider mb-1 px-3"
           style={{ color: 'var(--muted)' }}>生成文件</p>
        {tree.length === 0 && (
          <p className="text-xs px-3" style={{ color: 'var(--muted)' }}>暂无文件</p>
        )}
        {tree.map(node => (
          <TreeRow key={node.path} node={node} depth={0}
                   expanded={expanded} setExpanded={setExpanded}
                   selected={selected} onSelect={openFile} />
        ))}
      </div>

      {/* File content */}
      <div className="flex-1 overflow-auto" style={{ background: '#f8fafc' }}>
        {!selected ? (
          <p className="text-sm p-4" style={{ color: 'var(--muted)' }}>← 点击左侧文件查看内容</p>
        ) : loading ? (
          <p className="text-sm p-4" style={{ color: 'var(--muted)' }}>加载中…</p>
        ) : isMarkdown ? (
          <div className="max-w-3xl mx-auto px-8 py-6">
            <p className="text-xs font-bold mono mb-4 pb-2 border-b"
               style={{ color: 'var(--slate)', borderColor: 'var(--border-lt)' }}>{selected}</p>
            <article className="prose prose-sm prose-slate max-w-none
                                prose-headings:font-bold prose-headings:text-[color:var(--navy)]
                                prose-h1:text-2xl prose-h1:mt-0 prose-h1:mb-4
                                prose-h2:text-lg prose-h2:mt-6
                                prose-h3:text-base
                                prose-p:text-[color:var(--slate)] prose-p:leading-relaxed
                                prose-a:text-[color:var(--blue)] prose-a:no-underline hover:prose-a:underline
                                prose-strong:text-[color:var(--navy)]
                                prose-code:text-[color:var(--blue)] prose-code:bg-[color:var(--blue-lt)] prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-[0.85em] prose-code:before:content-none prose-code:after:content-none
                                prose-pre:bg-[#0f172a] prose-pre:text-[#e2e8f0] prose-pre:rounded-md prose-pre:text-xs
                                prose-blockquote:border-l-4 prose-blockquote:border-[color:var(--blue)] prose-blockquote:bg-[color:var(--blue-lt)] prose-blockquote:py-0.5 prose-blockquote:px-3 prose-blockquote:not-italic prose-blockquote:text-[color:var(--slate)]
                                prose-li:text-[color:var(--slate)]
                                prose-table:text-xs prose-th:bg-[color:var(--border-lt)]">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  img: ({ src, alt }) => {
                    if (!src) return null
                    const isAbsolute = /^(https?:)?\/\//.test(src) || src.startsWith('data:')
                    if (isAbsolute) return <img src={src} alt={alt} />
                    // Resolve relative image paths against the artifact API,
                    // relative to the directory of the markdown file.
                    const baseDir = selected!.includes('/') ? selected!.replace(/\/[^/]*$/, '/') : ''
                    const resolved = (baseDir + src).replace(/^\.\//, '')
                    const url = `/api/tasks/${detail.task_id}/artifacts/${encodeURIComponent(resolved)}`
                    return <img src={url} alt={alt} />
                  },
                }}>
                {content}
              </ReactMarkdown>
            </article>
          </div>
        ) : (
          <div className="p-4">
            <p className="text-xs font-bold mono mb-3" style={{ color: 'var(--slate)' }}>{selected}</p>
            <pre className="text-xs leading-relaxed mono" style={{ color: 'var(--slate)', whiteSpace: 'pre-wrap' }}>
              {content}
            </pre>
          </div>
        )}
      </div>
    </div>
  )
}
