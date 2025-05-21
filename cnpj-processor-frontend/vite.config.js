import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
       // target: 'http://212.85.14.78',
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false
      }
    }
  }
})
