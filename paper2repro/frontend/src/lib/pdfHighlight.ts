const GREEK_AND_MATH: Array<[RegExp, string]> = [
  [/[∆Δδ]/g, ' delta '],
  [/[αΑ]/g, ' alpha '],
  [/[βΒ]/g, ' beta '],
  [/[γΓ]/g, ' gamma '],
  [/[λΛ]/g, ' lambda '],
  [/[θΘ]/g, ' theta '],
  [/[πΠ]/g, ' pi '],
  [/[σΣ]/g, ' sigma '],
  [/[μΜ]/g, ' mu '],
  [/[ρΡ]/g, ' rho '],
  [/[τΤ]/g, ' tau '],
  [/[ωΩ]/g, ' omega '],
  [/[×✕]/g, ' x '],
  [/[∈]/g, ' in '],
  [/[≤]/g, ' le '],
  [/[≥]/g, ' ge '],
  [/[≠]/g, ' ne '],
  [/[∞]/g, ' infinity '],
]

const MIN_QUERY_CHARS = 8
const MIN_WINDOW_TOKENS = 5
const MAX_WINDOW_TOKENS = 14

interface IndexedText {
  normalized: string
  normalizedToItem: number[]
  compact: string
  compactToItem: number[]
}

export function normalizePdfText(value: string): string {
  let text = value.normalize('NFKD').toLowerCase()
  for (const [pattern, replacement] of GREEK_AND_MATH) {
    text = text.replace(pattern, replacement)
  }
  return text
    .replace(/[⁄/]/g, ' over ')
    .replace(/[‘’]/g, "'")
    .replace(/[“”]/g, '"')
    .replace(/[^\p{L}\p{N}\s]/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

export function hasUsableTextLayer(items: string[]): boolean {
  return normalizePdfText(items.join(' ')).length >= 32
}

function buildIndexedText(items: string[]): IndexedText {
  let normalized = ''
  const normalizedToItem: number[] = []
  let compact = ''
  const compactToItem: number[] = []

  for (let i = 0; i < items.length; i++) {
    const text = normalizePdfText(items[i])
    if (!text) continue

    if (normalized.length > 0) {
      normalized += ' '
      normalizedToItem.push(i)
    }

    for (const char of text) {
      normalized += char
      normalizedToItem.push(i)
      if (char !== ' ') {
        compact += char
        compactToItem.push(i)
      }
    }
  }

  return { normalized, normalizedToItem, compact, compactToItem }
}

function addMatchedItems(
  hits: Set<number>,
  offsetToItem: number[],
  start: number,
  end: number,
) {
  for (let i = start; i < end && i < offsetToItem.length; i++) {
    hits.add(offsetToItem[i])
  }
}

function findByIndexedString(text: string, offsetToItem: number[], query: string): Set<number> {
  const hits = new Set<number>()
  if (query.length < MIN_QUERY_CHARS) return hits

  let pos = 0
  while ((pos = text.indexOf(query, pos)) !== -1) {
    const matchEnd = pos + query.length
    addMatchedItems(hits, offsetToItem, pos, matchEnd)
    pos = matchEnd
  }
  return hits
}

function compact(value: string): string {
  return value.replace(/\s+/g, '')
}

function candidateQueries(rawQuery: string): string[] {
  const normalized = normalizePdfText(rawQuery)
  const tokens = normalized.split(' ').filter(Boolean)
  const candidates = new Set<string>()

  if (normalized.length >= MIN_QUERY_CHARS) {
    candidates.add(normalized)
  }

  for (let size = Math.min(MAX_WINDOW_TOKENS, tokens.length); size >= MIN_WINDOW_TOKENS; size--) {
    for (let start = 0; start + size <= tokens.length; start++) {
      candidates.add(tokens.slice(start, start + size).join(' '))
    }
  }

  return [...candidates].sort((a, b) => compact(b).length - compact(a).length)
}

export function findBestHighlightSet(items: string[], rawQuery: string): Set<number> {
  const index = buildIndexedText(items)
  if (!index.normalized || !rawQuery.trim()) return new Set()

  for (const query of candidateQueries(rawQuery)) {
    const exactHits = findByIndexedString(index.normalized, index.normalizedToItem, query)
    if (exactHits.size > 0) return exactHits

    const compactQuery = compact(query)
    const compactHits = findByIndexedString(index.compact, index.compactToItem, compactQuery)
    if (compactHits.size > 0) return compactHits
  }

  return new Set()
}
