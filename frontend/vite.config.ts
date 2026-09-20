import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': path.resolve(__dirname, 'src') } },
  server: {
    host: true,
    // In sviluppo il frontend gira su 5173 e l'API su 8000: questo proxy fa sì che
    // il codice usi sempre percorsi relativi `/api/...`, identici a come saranno in
    // produzione dietro nginx. Nessuna variabile d'ambiente con l'indirizzo dell'API.
    proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true } },
  },
})
