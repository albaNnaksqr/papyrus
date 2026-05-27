import assert from 'node:assert/strict'
import {
  findBestHighlightSet,
  hasUsableTextLayer,
  normalizePdfText,
} from '../src/lib/pdfHighlight'

function values(set: Set<number>): number[] {
  return [...set].sort((a, b) => a - b)
}

{
  const items = [
    'For a pre-trained weight matrix W',
    '0',
    'in R d x k,',
    'we constrain its update by representing the latter with a low-rank decomposition.',
  ]
  const quote = 'For a pre-trained weight matrix W0 ∈ R^{d×k}, we constrain its update by representing the latter with a low-rank decomposition'
  assert.deepEqual(values(findBestHighlightSet(items, quote)), [0, 1, 2, 3])
}

{
  const items = ['We then scale', 'Delta W x', 'by alpha over r,', 'where alpha is a constant in r.']
  const quote = 'We then scale ΔWx by α/r, where α is a constant in r.'
  assert.deepEqual(values(findBestHighlightSet(items, quote)), [0, 1, 2, 3])
}

assert.equal(normalizePdfText('W0 + ΔW = BA, α/r').includes('delta'), true)
assert.equal(hasUsableTextLayer(['', '   ', 'a']), false)
assert.equal(hasUsableTextLayer(['This page contains enough selectable paper text to align highlights.']), true)
