import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const frontendRoot = fileURLToPath(new URL(".", import.meta.url));
const apiProxyTarget =
  process.env.DEV_API_PROXY_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  root: frontendRoot,
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api/v1/": {
        target: apiProxyTarget,
        changeOrigin: false,
      },
    },
    fs: {
      strict: true,
      allow: [frontendRoot],
    },
    watch:
      process.env.DEV_VITE_POLLING === "1"
        ? { usePolling: true, interval: 500 }
        : undefined,
  },
  preview: {
    host: "127.0.0.1",
    port: 4173,
    strictPort: true,
  },
  test: {
    environment: "jsdom",
    globals: false,
    setupFiles: ["./src/test/setup.ts"],
  },
});
