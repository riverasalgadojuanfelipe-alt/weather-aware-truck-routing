import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In development, forward /api to the Django server so the browser sees one origin.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': 'http://localhost:8000' },
  },
})
