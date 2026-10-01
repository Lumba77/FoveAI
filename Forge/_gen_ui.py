import os
import pathlib

base = (
    pathlib.Path(
        os.getenv("FoveAI_REPO_ROOT", pathlib.Path(__file__).resolve().parent.parent)
    )
    / "Forge"
    / "ui"
)

# vite.config.ts
vite = r"""import { defineConfig } from "vite";

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
"""
(base / "vite.config.ts").write_text(vite, encoding="utf-8")
print("OK: vite.config.ts")

# index.html
html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>The Forge</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body { width: 100%; height: 100%; overflow: hidden; background: #02050a; color: #e0e0e0; font-family: 'Segoe UI', system-ui, sans-serif; }
    #forge-root { width: 100%; height: 100%; }
    #loading-screen { position: fixed; inset: 0; display: flex; align-items: center; justify-content: center; background: #02050a; z-index: 9999; transition: opacity 0.5s; }
    #loading-screen.hidden { opacity: 0; pointer-events: none; }
    .loader { width: 48px; height: 48px; border: 3px solid rgba(0,243,255,0.2); border-top-color: #00f3ff; border-radius: 50%; animation: spin 0.8s linear infinite; }
    @keyframes spin { to { transform: rotate(360deg); } }
  </style>
</head>
<body>
  <div id="loading-screen"><div class="loader"></div></div>
  <div id="forge-root"></div>
  <script type="module" src="/src/main.ts"></script>
</body>
</html>
"""
(base / "index.html").write_text(html, encoding="utf-8")
print("OK: index.html")

# src/main.ts
main_ts = """
import { ForgeCore } from './ForgeCore';
import { ForgeDashboard } from './components/ForgeDashboard';

(window as any).FORGE_VERSION = '1.0.0';
(window as any).FORGE_API = 'http://127.0.0.1:8100';

async function boot() {
  console.log('[FORGE] Booting...');
  const core = new ForgeCore();
  (window as any).forgeCore = core;
  await core.connect();
  const dashboard = new ForgeDashboard(core);
  (window as any).forgeDashboard = dashboard;
  const loader = document.getElementById('loading-screen');
  if (loader) { loader.classList.add('hidden'); setTimeout(() => loader.remove(), 600); }
  console.log('[FORGE] Ready');
}

boot().catch(err => {
  console.error('[FORGE] Boot failed:', err);
  const loader = document.getElementById('loading-screen');
  if (loader) loader.innerHTML = '<div style="color:#f44;text-align:center"><h2>Boot Failed</h2><p>'+err.message+'</p></div>';
});
"""
(base / "src" / "main.ts").write_text(main_ts, encoding="utf-8")
print("OK: src/main.ts")

print("All UI files generated!")
