import { defineConfig } from 'vite'

export default defineConfig({
	server: {
		allowedHosts: ['multivalent-sonya-chopfallen.ngrok-free.dev'],
		proxy: {
			// Explicit websocket path first to avoid proxy path-matching issues
			'/api/ws': { target: 'ws://127.0.0.1:8005', changeOrigin: true, ws: true },
			// Proxy backend API routes to the FastAPI server during development
			'/bot': { target: 'http://127.0.0.1:8005', changeOrigin: true },
			'/config': { target: 'http://127.0.0.1:8005', changeOrigin: true },
			'/trades': { target: 'http://127.0.0.1:8005', changeOrigin: true },
			'/logs': { target: 'http://127.0.0.1:8005', changeOrigin: true },
			'/chart': { target: 'http://127.0.0.1:8005', changeOrigin: true },
			'/backtest': { target: 'http://127.0.0.1:8005', changeOrigin: true },
			'/api': { target: 'http://127.0.0.1:8005', changeOrigin: true, ws: true }
		}
	}
})
