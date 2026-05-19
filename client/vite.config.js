import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:3000',
      '/generated': 'http://localhost:3000',
      '/uploads': 'http://localhost:3000'
    }
  }
})