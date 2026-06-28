import { defineConfig } from 'vite'

export default defineConfig({
  server: {
    host: '127.0.0.1',
    allowedHosts: ['multivalent-sonya-chopfallen.ngrok-free.dev'],
    port: 3009,
    proxy: {
      '/api/ws': {
        target: 'ws://127.0.0.1:8005',
        ws: true,
        changeOrigin: true,
      },
      '/config': {
        target: 'http://127.0.0.1:8005',
        changeOrigin: true,
      },
      '/trades': {
        target: 'http://127.0.0.1:8005',
        changeOrigin: true,
      },
      '/logs': {
        target: 'http://127.0.0.1:8005',
        changeOrigin: true,
      },
      '/chart': {
        target: 'http://127.0.0.1:8005',
        changeOrigin: true,
      },
      '/bot': {
        target: 'http://127.0.0.1:8005',
        changeOrigin: true,
      },
      '/backtest': {
        target: 'http://127.0.0.1:8005',
        changeOrigin: true,
      }
    }
  }
})
