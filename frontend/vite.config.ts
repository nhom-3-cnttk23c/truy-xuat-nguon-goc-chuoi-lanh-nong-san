import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/health': {
        target: process.env.VITE_BACKEND_TARGET || 'https://ttcs-backend-staging.onrender.com',
        changeOrigin: true,
        secure: false,
      },
      '/api': {
        target: process.env.VITE_BACKEND_TARGET || 'https://ttcs-backend-staging.onrender.com',
        changeOrigin: true,
        secure: false,
      },
    },
  },
})
