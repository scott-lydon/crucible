/// <reference types="vitest/config" />
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// The dev/preview server proxies /api -> the FastAPI backend. Point it at a
// running backend with VITE_API_PROXY (default http://localhost:8077). The
// in-app client base is VITE_API_BASE (default "/api", which hits this proxy).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = env.VITE_API_PROXY ?? 'http://localhost:8077'
  const proxy = { '/api': { target, rewrite: (p: string) => p.replace(/^\/api/, '') } }
  return {
    plugins: [react(), tailwindcss()],
    server: { proxy },
    preview: { proxy },
    test: { environment: 'jsdom', setupFiles: ['./src/test/setup.ts'] },
  }
})
