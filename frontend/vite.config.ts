import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const backend = process.env.BACKEND_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "./src") },
  },
  server: {
    // Same origin for the app, API and WebSocket, so the session cookie just works.
    proxy: {
      "/api": { target: backend, changeOrigin: false },
      "/ws": { target: backend, ws: true },
    },
  },
  build: { target: "chrome120" },
});
