import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    // 本地开发时的代理配置 (Docker中由Nginx处理)
    proxy: {
      '/api': 'http://localhost:8000'
    }
  }
})