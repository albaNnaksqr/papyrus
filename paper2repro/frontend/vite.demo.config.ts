import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

const input = process.env.PAPER2CODE_DEMO_INPUT ?? '.paper2code-demo/frontend-static.html'
const outDir = process.env.PAPER2CODE_DEMO_OUT_DIR ?? '../demo/.offline-build'

export default defineConfig({
  base: './',
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  build: {
    outDir,
    emptyOutDir: true,
    cssCodeSplit: false,
    sourcemap: false,
    assetsInlineLimit: 1024 * 1024,
    rollupOptions: {
      input: path.resolve(__dirname, input),
      output: {
        inlineDynamicImports: true,
      },
    },
  },
})
