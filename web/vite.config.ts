import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// dev 时把 /api 代理到 Jellyfish 后端，绕开 CORS（后端只放行了 7788）
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '')
  return {
    plugins: [react()],
    server: {
      port: 5273,
      proxy: {
        '/api': { target: env.SHOTCAT_API_TARGET || 'http://localhost:8000', changeOrigin: true },
        '/pipeline': { target: env.SHOTCAT_PIPELINE_TARGET || 'http://localhost:5280', changeOrigin: true },
      },
    },
  }
})
