import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts: ['multivalent-sonya-chopfallen.ngrok-free.dev'],
    port: 3009
  }
})
