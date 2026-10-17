import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the engine API runs on 8765 (spongepark serve); in production the engine serves this build.
const api = "http://127.0.0.1:8765";
export default defineConfig({
  plugins: [react()],
  server: { proxy: Object.fromEntries(["/projects", "/jobs", "/fs", "/health", "/video"].map((p) => [p, api])) },
  build: { outDir: "dist", chunkSizeWarningLimit: 1200 },
});
