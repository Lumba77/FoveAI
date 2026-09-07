import { defineConfig } from 'vite';
import fs from 'fs';
import path from 'path';
import basicSsl from '@vitejs/plugin-basic-ssl';
import wasm from 'vite-plugin-wasm';

// If running behind a reverse proxy / tunnel (e.g. Cloudflare) on a public HTTPS domain,
// the local Vite dev server can use plain HTTP. The public URL is still HTTPS via the proxy.
const USE_HTTPS = process.env.FoveAI_XR_HTTPS === '1' || process.env.FoveAI_XR_HTTPS === 'true';

export default defineConfig({
  plugins: USE_HTTPS ? [basicSsl(), wasm()] : [wasm()],
  optimizeDeps: {
    exclude: ['@webvm/webvm'],
  },
  resolve: {
    alias: {
      'three': path.resolve(__dirname, 'node_modules/three')
    }
  },
  server: {
    host: '0.0.0.0',
    port: parseInt(process.env.VITE_PORT || '5176', 10),
    cors: true,
    https: USE_HTTPS ? {
      key: fs.readFileSync(path.resolve(__dirname, 'server.key')),
      cert: fs.readFileSync(path.resolve(__dirname, 'server.crt')),
    } : undefined,
    hmr: process.env.FoveAI_TUNNEL_HMR === 'true' ? {
      host: 'foveai.1um6a.se',
      protocol: 'wss',
      overlay: false,
    } : {
      overlay: false,
    },
    allowedHosts: [
      'foveai.1um6a.se',
      'localhost',
      '127.0.0.1',
      '0.0.0.0'
    ],
    watch: {
      usePolling: false,
      ignored: ['**/public/Uploads/**', '**/public/diagnostic_data.json', '**/public/dev_feed.json', '**/user_data/**']
    },
    headers: {
      'Permissions-Policy': 'xr-spatial-tracking=(self), camera=(self), microphone=(self)',
      'Cross-Origin-Opener-Policy': 'same-origin',
      'Cross-Origin-Embedder-Policy': 'credentialless',
    },
    proxy: {
      '/ws/soul': {
        target: 'ws://127.0.0.1:8000',
        ws: true,
      },
      '/v1': {
        target: 'http://127.0.0.1:8400',
        changeOrigin: true,
        secure: false,
        configure: (proxy, _options) => {
          proxy.on('proxyRes', (proxyRes, req, res) => {
            // Fix CORS: LM Studio doesn't set these headers
            proxyRes.headers['access-control-allow-origin'] = '*';
            proxyRes.headers['access-control-allow-methods'] = 'GET, POST, OPTIONS, PUT, DELETE';
            proxyRes.headers['access-control-allow-headers'] = '*';
          });
        },
      },
      '/api/creative': {
        target: 'http://127.0.0.1:8003',
        rewrite: (path) => path.replace(/^\/api\/creative/, ''),
      },
      '/monetize': {
        target: 'http://127.0.0.1:8000',
      },
      '/api/nav': {
        target: 'http://127.0.0.1:8000',
      },
      '/compagent': {
        target: 'http://127.0.0.1:8000',
      },
      '/api/presence': {
        target: 'http://127.0.0.1:8000',
      },
      '/api/mouth': {
        target: 'http://127.0.0.1:8004',
        rewrite: (path) => path.replace(/^\/api\/mouth/, ''),
      },
      '/api/kokoro': {
        target: 'http://127.0.0.1:8006',
        rewrite: (path) => path.replace(/^\/api\/kokoro/, ''),
      },
      '/api/proxy/soul': {
        target: 'http://127.0.0.1:8000',
        rewrite: (path) => path.replace(/^\/api\/proxy\/soul/, ''),
      },
      '/api/thought_stream': {
        target: 'http://127.0.0.1:8000',
      },
      '/api/agent': {
        target: 'http://127.0.0.1:8000',
      },
      // All other /api/* routes go through xr_app.py (port 8101) for proxy services
      '/api': {
        target: 'http://127.0.0.1:8101',
        changeOrigin: true,
      },
    },
  },
  crossorigin: 'anonymous', // Fix preload credentials mismatch for @vite/client
  build: {
    outDir: '../../Build/Web_Vessel',
    emptyOutDir: true,
    target: 'es2022',
    assetsInlineLimit: 0, // Disable inlining of assets
    chunkSizeWarningLimit: 7000, // webllm is inherently large, suppress warning
    rollupOptions: {
      checks: {
        eval: false,        // onnxruntime-web uses direct eval — can't fix third-party code
        pluginTimings: false, // build speed info, not a runtime issue
      },
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/three/')) return 'vendor-three';
          if (id.includes('node_modules/@pixiv/three-vrm') || id.includes('node_modules/@pixiv/three-vrm-animation')) return 'vendor-vrm';
          if (id.includes('node_modules/@mlc-ai/web-llm')) return 'vendor-webllm';
          if (id.includes('node_modules/@xenova/transformers') || id.includes('node_modules/@huggingface/transformers')) return 'vendor-transformers';
          if (id.includes('node_modules/dexie/')) return 'vendor-db';
        },
      },
    },
  },
  assetsInclude: ['**/*.wasm', '**/*.data', '**/*.vrm', '**/*.glb'],
});
