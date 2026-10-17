/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Trong Docker, backend nằm ở http://backend:8000; chạy trên máy thì localhost.
const backend = process.env.BACKEND_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    // Demo qua Cloudflare quick tunnel (README mục "Demo từ máy dev qua Cloudflare"): link dạng *.trycloudflare.com.
    allowedHosts: [".trycloudflare.com"],
    proxy: {
      "/api": { target: backend, changeOrigin: false },
      "/webhooks": { target: backend, changeOrigin: false },
      "/healthz": { target: backend },
    },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
