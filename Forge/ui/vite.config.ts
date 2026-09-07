import { defineConfig } from "vite";

export default defineConfig({
  root: ".",
  publicDir: "public",
  server: {
    port: 5177,
    proxy: {
      "/api/forge": {
        target: "http://127.0.0.1:8100",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/forge/, "/api"),
      },
      "/ws/forge": {
        target: "ws://127.0.0.1:8100",
        ws: true,
        rewrite: (path) => path.replace(/^\/ws\/forge/, "/ws"),
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
