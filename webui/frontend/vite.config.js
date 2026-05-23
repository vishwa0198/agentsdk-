import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const BACKEND = 'http://localhost:8000'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      // Proxy all FastAPI REST routes to the backend during local development.
      '^/(health|auth|chat|sessions|memory|upload|mcp|pipelines|monitor|schedules|webhook)': {
        target: BACKEND,
        changeOrigin: true,
      },
      // Proxy WebSocket connections.
      '/ws': {
        target: BACKEND.replace('http', 'ws'),
        ws: true,
        changeOrigin: true,
      },
    },
  },
})
