import { defineConfig, loadEnv, Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import crypto from 'crypto'

const envDir = path.resolve(process.cwd(), '../..')

// ── Password gate plugin ──────────────────────────────────────────────────
// Reads FoveAI_WEBUI_PASSWORD from .env. If set, shows a login page
// before serving the app. If FoveAI_WEBUI_ALLOW_INSECURE=1, no gate.
// Cookie-based: one login per browser session.
function passwordGate(password: string, allowInsecure: boolean): Plugin {
  const gateActive = !!password && !allowInsecure
  const cookieName = 'xarel_auth'
  // Hash the password to create a session token (not the password itself)
  const sessionToken = crypto.createHash('sha256').update('xarel|' + password).digest('hex').slice(0, 32)

  const loginHTML = (error = '') => `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Xarel — Enter</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    background: #0a0a0f; color: #e0faff;
    font-family: Inter, system-ui, sans-serif;
    display: flex; align-items: center; justify-content: center;
    min-height: 100vh; padding: 2rem;
  }
  .gate {
    background: rgba(20,20,35,0.8); border: 1px solid rgba(100,180,255,0.15);
    border-radius: 16px; padding: 2.5rem; max-width: 380px; width: 100%;
    backdrop-filter: blur(12px);
  }
  h1 { font-size: 1.6rem; margin-bottom: 0.5rem; }
  p { font-size: 0.9rem; color: #7a8a9a; margin-bottom: 1.5rem; }
  input {
    width: 100%; padding: 0.75rem 1rem; border-radius: 8px;
    border: 1px solid rgba(100,180,255,0.2); background: rgba(10,10,20,0.6);
    color: #e0faff; font-size: 1rem; outline: none; margin-bottom: 1rem;
  }
  input:focus { border-color: rgba(100,180,255,0.5); }
  button {
    width: 100%; padding: 0.75rem; border-radius: 8px; border: none;
    background: linear-gradient(135deg, #4a9eff, #6b5bff); color: white;
    font-size: 1rem; cursor: pointer; font-weight: 600;
  }
  button:hover { opacity: 0.9; }
  .err { color: #ff6b6b; font-size: 0.85rem; margin-bottom: 1rem; }
  .hint { font-size: 0.75rem; color: #4a5a6a; margin-top: 1rem; text-align: center; }
</style>
</head>
<body>
  <div class="gate">
    <h1>Xarel</h1>
    <p>Enter the spatial machine.</p>
    ${error ? '<div class="err">' + error + '</div>' : ''}
    <form method="POST" action="/__auth/login">
      <input type="password" name="password" placeholder="Password" autofocus />
      <button type="submit">Enter</button>
    </form>
    <div class="hint">The dragon's cave is guarded.</div>
  </div>
</body>
</html>`

  return {
    name: 'xarel-password-gate',
    configureServer(server) {
      if (!gateActive) return

      server.middlewares.use((req, res, next) => {
        const url = req.url || ''

        // Allow HMR and internal Vite requests through
        if (url.startsWith('/@') || url.startsWith('/node_modules/')) {
          return next()
        }

        // Handle login POST
        if (url === '/__auth/login' && req.method === 'POST') {
          let body = ''
          req.on('data', (chunk: any) => { body += chunk })
          req.on('end', () => {
            const params = new URLSearchParams(body)
            const given = params.get('password') || ''
            if (given === password) {
              res.setHeader('Set-Cookie', `${cookieName}=${sessionToken}; Path=/; HttpOnly; SameSite=Lax; Max-Age=86400`)
              res.writeHead(302, { Location: '/' })
              res.end()
            } else {
              res.writeHead(200, { 'Content-Type': 'text/html' })
              res.end(loginHTML('Incorrect password.'))
            }
          })
          return
        }

        // Handle logout
        if (url === '/__auth/logout') {
          res.setHeader('Set-Cookie', `${cookieName}=; Path=/; HttpOnly; Max-Age=0`)
          res.writeHead(302, { Location: '/' })
          res.end()
          return
        }

        // Check cookie
        const cookies = (req.headers.cookie || '').split(';').reduce((acc: Record<string,string>, c: string) => {
          const [k, v] = c.trim().split('=')
          if (k && v) acc[k] = v
          return acc
        }, {})

        if (cookies[cookieName] === sessionToken) {
          return next()
        }

        // Not authenticated — show login page
        res.writeHead(200, { 'Content-Type': 'text/html' })
        res.end(loginHTML())
      })
    },
  }
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, envDir, '')
  const proxyUrl = (env.XRLF_MEMORY_PROXY_URL || 'http://127.0.0.1:8400').replace(/\/$/, '')
  const soulUrl = (env.SOUL_URL || 'http://127.0.0.1:8404').replace(/\/$/, '')
  const mouthUrl = (env.MOUTH_URL || 'http://127.0.0.1:8406').replace(/\/$/, '')
  const proxyPort = (() => {
    try { return new URL(proxyUrl).port || '8400' } catch { return '8400' }
  })()

  const webuiPassword = (env.FoveAI_WEBUI_PASSWORD || '').trim()
  const allowInsecure = (env.FoveAI_WEBUI_ALLOW_INSECURE || '0').trim().toLowerCase() in { '1': 1, 'true': 1, 'yes': 1 }

  return {
    plugins: [
      passwordGate(webuiPassword, allowInsecure),
      react(),
    ],
    envPrefix: 'VITE_',
    define: {
      'import.meta.env.VITE_PROXY_PORT': JSON.stringify(proxyPort)
    },
    server: {
      port: parseInt(process.env.VITE_PORT || '5177', 10),
      host: true,
      allowedHosts: true,
      cors: true,
      proxy: {
        '/api/foveated': {
          target: proxyUrl,
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/api\/foveated/, '')
        },
        // Voice pipeline — all goes through the proxy (:8400)
        // Proxy handles STT/TTS with fallback to Soul/Mouth/Piper
        '/api/soul': {
          target: proxyUrl,
          changeOrigin: true
        },
        '/api/tts': {
          target: proxyUrl,
          changeOrigin: true
        },
        '/api/voice': {
          target: proxyUrl,
          changeOrigin: true
        },
        '/monetize': {
          target: soulUrl,
          changeOrigin: true
        },
        '/api/kokoro': {
          target: mouthUrl,
          rewrite: (p) => p.replace(/^\/api\/kokoro/, ''),
          changeOrigin: true
        },
        '/api/soundboard': {
          target: env.SOUND_URL || 'http://127.0.0.1:8006',
          changeOrigin: true
        },
        '/api/agent': {
          target: soulUrl,
          changeOrigin: true
        },
        '/api/thought_stream': {
          target: soulUrl,
          changeOrigin: true
        }
      }
    }
  }
})
