import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    // 联调代理（FRONTEND.md §7.2）：前端请求 /api/* → FastAPI，
    // rewrite 去掉 /api 前缀——后端按契约 13 章裸挂 /diagnoses 路由
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
});
