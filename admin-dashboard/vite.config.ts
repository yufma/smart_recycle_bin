import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({mode}) => ({
  base: mode === 'pages' ? '/smart_recycle_bin/' : '/',
  build: { outDir: mode === 'pages' ? 'site-dist' : 'dist' },
  plugins: [react()],
  server: { proxy: { '/api': 'http://127.0.0.1:8765' } },
}));
