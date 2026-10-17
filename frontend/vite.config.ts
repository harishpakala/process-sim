import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Browser only calls Python. GraphDB endpoint stays server-side.
export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': {
        target: process.env.PROCESS_SIM_API_URL || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
