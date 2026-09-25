import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In dev, Vite serves the UI on :5173 and proxies the API (incl. the terminal
// WebSocket) to the Python server on :8321. In production the Python server
// serves the built files itself.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8321", ws: true },
    },
  },
  build: {
    chunkSizeWarningLimit: 8000,
  },
  worker: {
    format: "es",
  },
});
