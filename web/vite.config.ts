import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// dev 时把 /api 代理到 Jellyfish 后端，绕开 CORS（后端只放行了 7788）
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5273,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/pipeline': { target: 'http://localhost:5280', changeOrigin: true },
    },
  },
})
