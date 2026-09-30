import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev server proxies the API so cookies stay same-origin, as they are behind Traefik.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://localhost:8000", changeOrigin: false } },
  },
  build: {
    target: "es2022",
    sourcemap: false,
    // Never inline assets as data: URLs; the CSP only allows same-origin fonts (SEC-050).
    assetsInlineLimit: 0,
    // Budget is 300 kB gzipped (NFR-006); this limit is on minified size.
    chunkSizeWarningLimit: 450,
  },
});
