import fs from 'node:fs'
import path from 'node:path'
const root = path.dirname(new URL(import.meta.url).pathname)
const reactPages = [
  {
    file: 'frontend-static.html',
    mode: 'static',
    taskCount: 'multiple',
    required: ['paper2repro', 'frontend-static', 'paper_7e8d582f', 'Attention Is All You Need', 'generate_code/transformer/README.md'],
  },
  {
    file: 'process-replay.html',
    mode: 'replay',
    taskCount: 'single',
    required: ['paper2repro', 'process-replay', 'paper_7e8d582f', 'Attention Is All You Need', 'logs/events.jsonl'],
  },
]

const staticPages = [
  {
    file: 'executive-briefing.html',
    required: [
      'paper2repro · 算法论文工程化',
      '把论文变成可审计的代码资产',
      'process-replay.html',
      'frontend-static.html',
      'Attention Is All You Need',
      '质量门禁',
    ],
  },
]

const externalPatterns = [
  /<script\b[^>]*\bsrc\s*=/i,
  /<link\b[^>]*\bhref\s*=/i,
  /<(?:img|iframe|source|video|audio|a)\b[^>]*\b(?:src|href)\s*=\s*["']?(?:https?:|file:)/i,
  /url\(\s*["']?(?:https?:|file:)/i,
  /@import\b/i,
]

let failed = false

function validateCommonHtml(page, html) {
  if (!/<meta\s+name="viewport"/i.test(html)) {
    console.error(`${page.file} is missing viewport metadata`)
    failed = true
  }
  for (const pattern of externalPatterns) {
    if (pattern.test(html)) {
      console.error(`${page.file} contains external dependency pattern: ${pattern}`)
      failed = true
    }
  }
  for (const text of page.required) {
    if (!html.includes(text)) {
      console.error(`${page.file} is missing required text: ${text}`)
      failed = true
    }
  }
}

for (const page of reactPages) {
  const target = path.join(root, page.file)
  if (!fs.existsSync(target)) {
    console.error(`Missing ${page.file}`)
    failed = true
    continue
  }

  const html = fs.readFileSync(target, 'utf8')
  if (!/<style\b/i.test(html)) {
    console.error(`${page.file} is missing inline CSS`)
    failed = true
  }
  if (!/<script\b[^>]*type=["']module["']/i.test(html)) {
    console.error(`${page.file} is missing inline module bundle`)
    failed = true
  }
  validateCommonHtml(page, html)
  if (!html.includes('data-offline-react-demo-root')) {
    console.error(`${page.file} is not using the offline React demo root`)
    failed = true
  }
  if (html.includes('id="taskList"') || html.includes('id="detailBody"')) {
    console.error(`${page.file} still contains the legacy pre-rendered demo shell`)
    failed = true
  }

  const dataMatch = html.match(/<script\b[^>]*id=["']paper2code-demo-data["'][^>]*type=["']application\/json["'][^>]*>([\s\S]*?)<\/script>/i)
  if (!dataMatch) {
    console.error(`${page.file} is missing embedded demo JSON`)
    failed = true
  } else {
    const data = JSON.parse(dataMatch[1])
    if (data.mode !== page.mode) {
      console.error(`${page.file} has wrong mode: ${data.mode}`)
      failed = true
    }
    if (!Array.isArray(data.tasks)) {
      console.error(`${page.file} embeds invalid tasks`)
      failed = true
    } else if (page.taskCount === 'single' && data.tasks.length !== 1) {
      console.error(`${page.file} must embed exactly one replay task`)
      failed = true
    } else if (page.taskCount === 'multiple' && data.tasks.length < 3) {
      console.error(`${page.file} embeds too few tasks`)
      failed = true
    }
    const transformer = data.tasks?.find(task => task.id === 'paper_7e8d582f')
    if (!transformer?.artifacts?.['generate_code/transformer/README.md']) {
      console.error(`${page.file} is missing the completed Transformer artifact content`)
      failed = true
    }
  }
}

for (const page of staticPages) {
  const target = path.join(root, page.file)
  if (!fs.existsSync(target)) {
    console.error(`Missing ${page.file}`)
    failed = true
    continue
  }

  const html = fs.readFileSync(target, 'utf8')
  validateCommonHtml(page, html)
  if (!/<style\b/i.test(html)) {
    console.error(`${page.file} is missing inline CSS`)
    failed = true
  }
  if (html.includes('data-offline-react-demo-root')) {
    console.error(`${page.file} should remain a standalone briefing page`)
    failed = true
  }
}

if (failed) {
  process.exit(1)
}

console.log('Demo HTML validation passed')
