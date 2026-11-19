import { defineConfig } from 'vite';

export default defineConfig({
  esbuild: {
    jsx: 'automatic',
  },
  server: {
    proxy: {
      // локальная разработка: /api уходит на uvicorn
      '/api': 'http://localhost:8000',
    },
  },
});
