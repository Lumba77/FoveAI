import pathlib
import os

base = pathlib.Path(os.getenv("FoveAI_REPO_ROOT", pathlib.Path(__file__).resolve().parent.parent)) / "Forge" / "ui"

# ── vite.config.ts ──
vite = r'''import { defineConfig } from "vite";

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
'''
(base / 'vite.config.ts').write_text(vite)
print('OK: vite.config.ts')
