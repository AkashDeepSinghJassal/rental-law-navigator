/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Built files are served by the FastAPI app (web/app.py) from web/dist.
export default defineConfig({
  plugins: [react()],
  build: { outDir: "../web/dist", emptyOutDir: true },
  server: { proxy: { "/api": "http://127.0.0.1:8765" } },
  test: { environment: "node" },
});
