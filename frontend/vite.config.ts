import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // 개발 서버에서 /api/v1 호출을 Spring 백엔드(8080)로 프록시. (운영은 nginx가 처리)
    proxy: {
      '/api/v1': { target: 'http://localhost:8080', changeOrigin: true },
    },
  },
})
