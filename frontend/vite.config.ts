import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The FastAPI backend normally runs on this machine at :8000. To use a backend on another machine
// (e.g. a Mac Studio doing the rendering), point the proxy at it:
//   QI_API_URL=http://studio.local:8000 npm run dev
const target = process.env.QI_API_URL ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5180,
    strictPort: true,
    proxy: {
      '/api': { target, changeOrigin: true },
      '/outputs': { target, changeOrigin: true },
    },
  },
})
