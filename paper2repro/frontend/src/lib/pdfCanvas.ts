const MAX_OUTPUT_SCALE = 2

interface CanvasBackingStoreInput {
  width: number
  height: number
  devicePixelRatio?: number
}

export interface CanvasBackingStore {
  outputScale: number
  pixelWidth: number
  pixelHeight: number
  cssWidth: number
  cssHeight: number
}

export function getCanvasBackingStore({
  width,
  height,
  devicePixelRatio = 1,
}: CanvasBackingStoreInput): CanvasBackingStore {
  const outputScale = Math.max(1, Math.min(MAX_OUTPUT_SCALE, devicePixelRatio || 1))
  return {
    outputScale,
    pixelWidth: Math.ceil(width * outputScale),
    pixelHeight: Math.ceil(height * outputScale),
    cssWidth: width,
    cssHeight: height,
  }
}
