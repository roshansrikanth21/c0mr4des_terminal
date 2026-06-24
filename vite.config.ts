import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) {
            return;
          }
          if (id.includes('@blinkdotnew')) {
            return 'blink-sdk';
          }
          if (id.includes('@react-three') || id.includes('/three/')) {
            return 'three-stack';
          }
          if (id.includes('recharts') || id.includes('plotly') || id.includes('d3')) {
            return 'charts';
          }
          if (id.includes('framer-motion')) {
            return 'motion';
          }
          if (id.includes('react-hook-form') || id.includes('@hookform') || id.includes('/zod/')) {
            return 'forms';
          }
          if (id.includes('@radix-ui') || id.includes('lucide-react') || id.includes('sonner')) {
            return 'ui-kit';
          }
          return 'vendor';
        },
      },
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    host: true,
    allowedHosts: true,
    proxy: {
      // Backend port is configurable so it can coexist with JARVIS (which owns :8000).
      '/api': {
        target: process.env.C0MR4DES_API || 'http://127.0.0.1:8100',
        changeOrigin: true,
      },
      '/auth': {
        target: process.env.C0MR4DES_API || 'http://127.0.0.1:8100',
        changeOrigin: true,
      },
    },
  }
});
