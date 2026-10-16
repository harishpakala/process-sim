import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Local dev: /kg/repositories/AAS -> http://pakala:7200/repositories/AAS.
// For production, configure the same reverse proxy route on the web server.
export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/kg': {
        target: process.env.GRAPHDB_URL || 'http://pakala:7200',
        changeOrigin: true,
        rewrite: path => path.replace(/^\/kg/, ''),
      },
    },
  },
})
