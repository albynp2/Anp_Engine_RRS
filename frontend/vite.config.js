import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Dev: `npm run dev` -> proxy /api dan /media ke backend di :8000. Produksi: dibuild & disajikan FastAPI.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true, proxy: { '/api': 'http://127.0.0.1:8000', '/media': 'http://127.0.0.1:8000' } },
});
