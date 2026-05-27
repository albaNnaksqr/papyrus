import assert from 'node:assert/strict'
import { getCanvasBackingStore } from '../src/lib/pdfCanvas'

assert.deepEqual(getCanvasBackingStore({ width: 612, height: 792, devicePixelRatio: 1 }), {
  outputScale: 1,
  pixelWidth: 612,
  pixelHeight: 792,
  cssWidth: 612,
  cssHeight: 792,
})

assert.deepEqual(getCanvasBackingStore({ width: 612.4, height: 792.6, devicePixelRatio: 2.5 }), {
  outputScale: 2,
  pixelWidth: 1225,
  pixelHeight: 1586,
  cssWidth: 612.4,
  cssHeight: 792.6,
})

assert.deepEqual(getCanvasBackingStore({ width: 300, height: 400, devicePixelRatio: 0 }), {
  outputScale: 1,
  pixelWidth: 300,
  pixelHeight: 400,
  cssWidth: 300,
  cssHeight: 400,
})
