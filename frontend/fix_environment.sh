cat << 'END' > vite.config.js
import { defineConfig } from 'vite'

export default defineConfig({
server: {
allowedHosts: ['multivalent-sonya-chopfallen.ngrok-free.dev'],
port: 3009
}
})
END
npm run dev
