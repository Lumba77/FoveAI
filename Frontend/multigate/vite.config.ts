import { defineConfig, loadEnv } from 'vite';
import type { Plugin } from 'vite';
import react from '@vitejs/plugin-react'
import path from 'path'
import fs from 'fs'
import http from 'http'
import { execFile } from 'child_process'
import net from 'net'

const envDir = path.resolve(process.cwd(), '../..')

// ── fvs-gate plugin ───────────────────────────────────────────────────────
// The Multigate has its own account system (/api/auth/* → 30-day fvs_
// session tokens). The old site-wide password page was a second, confusing
// login — removed. What still needs a shield are the server-control
// surfaces this dev server exposes directly: /remote-api (service
// start/stop), /ignition, /novnc (x11vnc runs -nopw — passwordless control
// of the physical desktop), /rdp. The app drops the fvs_ token into a
// fvs_gate cookie on login; we verify it against the backend /api/auth/me
// (5-minute in-memory cache). Covers both HTTP and WS upgrades. /ignition
// is deliberately open — it's the cold-boot recovery path and must work
// while the backend (and thus login) is down.
const FVS_SHIELDED = ['/remote-api', '/novnc', '/rdp', '/api/agent', '/api/soul', '/api/dream', '/xrlf', '/dash']
const FVS_COOKIE = 'fvs_gate'

// Tunnel hostnames repointed to :5177 — everything on these hosts sits
// behind the same login. The app cookie is set with Domain=xarel.net so a
// single apex login unlocks the subdomains too.
const NOVNC_HOST = 'novnc.xarel.net'
const METRICS_HOST = 'metrics.xarel.net'
const NETDATA_PORT = 19999

function fvsGate(authMeUrl: string): Plugin {
  const cache = new Map<string, number>() // token → revalidate-after (ms)

  const tokenFrom = (cookieHeader?: string): string | null => {
    for (const c of (cookieHeader || '').split(';')) {
      const i = c.indexOf('=')
      if (i > 0 && c.slice(0, i).trim() === FVS_COOKIE) return c.slice(i + 1).trim()
    }
    return null
  }

  const isShielded = (url: string) => {
    const p = url.split('?')[0]
    return FVS_SHIELDED.some(s => p === s || p.startsWith(s + '/'))
  }

  const isValid = async (token: string): Promise<boolean> => {
    const cached = cache.get(token)
    if (cached && cached > Date.now()) return true
    try {
      const r = await fetch(authMeUrl, {
        headers: { Authorization: `Bearer ${token}` },
        signal: AbortSignal.timeout(3000),
      })
      const j: any = await r.json().catch(() => null)
      const ok = r.ok && !!j && !!j.userId && j.userId !== 'anonymous'
      if (ok) {
        if (cache.size > 500) cache.clear()
        cache.set(token, Date.now() + 5 * 60 * 1000)
      }
      return ok
    } catch {
      return false
    }
  }

  const deny = (res: any) => {
    res.writeHead(401, { 'Content-Type': 'text/plain' })
    res.end('Sign in to Xarel first.')
  }

  const hostOf = (req: any) => (req.headers.host || '').split(':')[0]

  // Whole-request pipe to netdata for metrics.xarel.net
  const pipeToNetdata = (req: any, res: any) => {
    const upstream = http.request(
      { host: '127.0.0.1', port: NETDATA_PORT, path: req.url, method: req.method,
        headers: { ...req.headers, host: `127.0.0.1:${NETDATA_PORT}` } },
      (ur) => { res.writeHead(ur.statusCode || 502, ur.headers); ur.pipe(res) },
    )
    upstream.on('error', () => { res.writeHead(502); res.end('netdata unreachable') })
    req.pipe(upstream)
  }

  // Raw WS splice to netdata for metrics host upgrades
  const spliceToNetdata = (req: any, socket: any, head: Buffer) => {
    const up = net.connect(NETDATA_PORT, '127.0.0.1', () => {
      const headers = Object.entries(req.headers)
        .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`).join('\r\n')
      up.write(`${req.method} ${req.url} HTTP/${req.httpVersion}\r\n${headers}\r\n\r\n`)
      if (head?.length) up.write(head)
      up.pipe(socket); socket.pipe(up)
    })
    up.on('error', () => socket.destroy())
    socket.on('error', () => up.destroy())
  }

  return {
    name: 'fvs-gate',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const host = hostOf(req)
        const url = req.url || ''
        const token = tokenFrom(req.headers.cookie)

        // metrics.xarel.net — entire host is netdata, shielded
        if (host === METRICS_HOST) {
          if (!token) return deny(res)
          return void isValid(token).then(ok => (ok ? pipeToNetdata(req, res) : deny(res)))
        }

        // novnc.xarel.net — entire host shielded; '/' lands on the desktop
        if (host === NOVNC_HOST) {
          if (!token) {
            res.writeHead(302, { Location: 'https://xarel.net/' })
            return res.end()
          }
          return void isValid(token).then(ok => {
            if (!ok) {
              res.writeHead(302, { Location: 'https://xarel.net/' })
              return res.end()
            }
            if (url === '/' || url === '') {
              res.writeHead(302, { Location: '/novnc/vnc.html?autoconnect=true&resize=scale&reconnect=true' })
              return res.end()
            }
            // map host-relative paths onto the /novnc proxy prefix
            if (!url.startsWith('/novnc')) req.url = '/novnc' + (url.startsWith('/') ? url : '/' + url)
            next()
          })
        }

        if (!isShielded(url)) return next()
        if (!token) return deny(res)
        isValid(token).then(ok => (ok ? next() : deny(res)))
      })

      // Middleware never sees WS upgrades — the noVNC/guac/netdata sockets
      // are shielded here instead. Registered before vite's own proxy
      // upgrade listeners (configureServer runs first), so a rewritten
      // req.url is what the proxy sees.
      server.httpServer?.on('upgrade', (req: any, socket: any, head: Buffer) => {
        const host = hostOf(req)
        const url = req.url || ''
        const token = tokenFrom(req.headers.cookie)

        if (host === METRICS_HOST) {
          if (!token) return socket.destroy()
          return void isValid(token).then(ok => (ok ? spliceToNetdata(req, socket, head) : socket.destroy()))
        }
        if (host === NOVNC_HOST) {
          if (!token) return socket.destroy()
          return void isValid(token).then(ok => {
            if (!ok) return socket.destroy()
            if (!url.startsWith('/novnc')) req.url = '/novnc' + (url.startsWith('/') ? url : '/' + url)
          })
        }
        if (!isShielded(url)) return
        if (!token) return socket.destroy()
        isValid(token).then(ok => { if (!ok) socket.destroy() })
      })
    },
  }
}

// ── Remote-access service registry ────────────────────────────────────────
// Services the Remote tab can report on / control. scope 'user' →
// systemctl --user (works from this dev-server process), 'system' →
// status-only (needs sudo we don't have), 'process' → pgrep + start/stop scripts.
const REMOTE_SERVICES = [
  { id: 'novnc',    label: 'noVNC Web Desktop',              unit: 'novnc-desktop.service',                    scope: 'user',    port: 6080  },
  { id: 'x11vnc',   label: 'VNC Bridge (x11vnc :5900)',      unit: 'x11vnc-desktop.service',                   scope: 'user',    port: 5900  },
  { id: 'sunshine', label: 'Sunshine (Moonlight/Nightfall)', unit: 'sunshine.service',                         scope: 'system',  port: 47990 },
  { id: 'xrdp',     label: 'RDP (xrdp :3389)',               unit: 'xrdp.service',                             scope: 'system',  port: 3389  },
  { id: 'guacd',    label: 'Web RDP bridge (guacd :4822)',   unit: 'guacd.service',                             scope: 'system',  port: 4822  },
  { id: 'remoteweb',label: 'Web RDP client (:6081)',         unit: 'guac-web.service',                          scope: 'user',    port: 6081  },
  { id: 'crd',      label: 'Chrome Remote Desktop',          unit: null,                                       scope: 'process', port: null  },
]

const exec = (cmd: string, args: string[], timeoutMs = 6000): Promise<{ code: number; out: string }> =>
  new Promise((resolve) => {
    execFile(cmd, args, { timeout: timeoutMs }, (err, stdout, stderr) => {
      const code = err && typeof (err as any).code === 'number' ? (err as any).code : err ? 1 : 0
      resolve({ code, out: (stdout || stderr || '').toString().trim() })
    })
  })

const tcpCheck = (port: number, timeoutMs = 1500): Promise<boolean> =>
  new Promise((resolve) => {
    const sock = new net.Socket()
    const done = (ok: boolean) => { sock.destroy(); resolve(ok) }
    sock.setTimeout(timeoutMs)
    sock.once('connect', () => done(true))
    sock.once('timeout', () => done(false))
    sock.once('error', () => done(false))
    sock.connect(port, '127.0.0.1')
  })

async function remoteServiceStatus(svc: typeof REMOTE_SERVICES[number]) {
  let status = 'unknown'
  if (svc.scope === 'process') {
    // comm name is truncated to 15 chars: 'chrome-remote-d'.
    // -x exact match avoids false hits on commands merely naming the binary
    const r = await exec('pgrep', ['-x', 'chrome-remote-d'])
    status = r.code === 0 ? 'active' : 'inactive'
  } else if (svc.unit) {
    const args = svc.scope === 'user' ? ['--user', 'is-active', svc.unit] : ['is-active', svc.unit]
    const r = await exec('systemctl', args)
    status = r.out || (r.code === 0 ? 'active' : 'inactive')
  }
  const reachable = svc.port ? await tcpCheck(svc.port) : null
  return { id: svc.id, label: svc.label, unit: svc.unit, scope: svc.scope, status, reachable }
}

// ── WebVM static host ─────────────────────────────────────────────────────
// CheerpX WASM Linux bundle lives in XR_Vessel/public/webvm. Vite's own
// proxy/static pipeline can't serve it reliably (non-/api proxy contexts
// get swallowed before the proxy middleware, and public-dir responses
// don't carry custom headers), so this middleware — registered inside
// configureServer, i.e. BEFORE vite's internal stack — streams the files
// directly with the COOP/COEP headers SharedArrayBuffer requires.
const WEBVM_DIR = path.resolve(envDir, 'Frontend/XR_Vessel/public/webvm')
const WEBVM_TYPES: Record<string, string> = {
  '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript',
  '.wasm': 'application/wasm', '.css': 'text/css', '.json': 'application/json',
  '.map': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml', '.ico': 'image/x-icon', '.txt': 'text/plain',
}
function webvmStatic(): Plugin {
  return {
    name: 'webvm-static',
    configureServer(server) {
      server.middlewares.use('/webvm', (req, res, next) => {
        if (req.method !== 'GET' && req.method !== 'HEAD') return next()
        const rel = decodeURIComponent((req.url || '/').split('?')[0])
        const file = path.normalize(path.join(WEBVM_DIR, rel === '/' ? 'index.html' : rel))
        if (!file.startsWith(WEBVM_DIR + path.sep)) {
          res.writeHead(403); res.end(); return
        }
        fs.stat(file, (err, st) => {
          if (err || !st.isFile()) return next()
          const baseHeaders = {
            'Content-Type': WEBVM_TYPES[path.extname(file).toLowerCase()] || 'application/octet-stream',
            'Accept-Ranges': 'bytes',
            'Cross-Origin-Opener-Policy': 'same-origin',
            'Cross-Origin-Embedder-Policy': 'require-corp',
          }
          // HttpBytesDevice lazy-loads the ext2 disk image with Range requests;
          // without 206 support it would pull the whole ~600MB upfront or fail.
          const rm = (req.headers.range || '').match(/^bytes=(\d*)-(\d*)$/)
          if (rm && (rm[1] || rm[2])) {
            const start = rm[1] ? parseInt(rm[1], 10) : Math.max(0, st.size - parseInt(rm[2], 10))
            const end = rm[1] ? (rm[2] ? Math.min(parseInt(rm[2], 10), st.size - 1) : st.size - 1) : st.size - 1
            if (Number.isNaN(start) || Number.isNaN(end) || start > end || start >= st.size) {
              res.writeHead(416, { ...baseHeaders, 'Content-Range': `bytes */${st.size}` })
              res.end(); return
            }
            res.writeHead(206, {
              ...baseHeaders,
              'Content-Range': `bytes ${start}-${end}/${st.size}`,
              'Content-Length': end - start + 1,
            })
            if (req.method === 'HEAD') return res.end()
            fs.createReadStream(file, { start, end }).pipe(res)
            return
          }
          res.writeHead(200, { ...baseHeaders, 'Content-Length': st.size })
          if (req.method === 'HEAD') return res.end()
          fs.createReadStream(file).pipe(res)
        })
      })
    },
  }
}

// GET  /remote-api/services                    → JSON status list
// POST /remote-api/services/:id/:action        → systemctl --user start|stop|restart
function remoteApi(): Plugin {
  return {
    name: 'remote-api',
    configureServer(server) {
      server.middlewares.use('/remote-api/services', (req, res) => {
        void (async () => {
          const url = req.url || ''
          const json = (code: number, body: any) => {
            res.writeHead(code, { 'Content-Type': 'application/json' })
            res.end(JSON.stringify(body))
          }

          if (req.method === 'GET' && (url === '/' || url === '')) {
            json(200, { services: await Promise.all(REMOTE_SERVICES.map(remoteServiceStatus)) })
            return
          }

          const m = url.match(/^\/([a-z]+)\/(start|stop|restart)\/?$/)
          if (req.method === 'POST' && m) {
            const svc = REMOTE_SERVICES.find(s => s.id === m[1])
            if (!svc) return json(404, { ok: false, error: 'unknown service' })
            if (svc.scope === 'system') {
              // Passwordless via /etc/sudoers.d/foveai-remote — scoped to
              // these exact unit actions, no blanket root. sudo -n fails
              // fast (non-interactive) if the drop-in isn't installed yet.
              const r = await exec('sudo', ['-n', 'systemctl', m[2], svc.unit!], 10000)
              if (r.code !== 0) {
                return json(403, { ok: false, error: 'needs sudoers drop-in — run: sudo systemctl ' + m[2] + ' ' + svc.unit + ' (or install /etc/sudoers.d/foveai-remote)' })
              }
              return json(200, { ok: true, detail: 'ok' })
            }
            if (svc.scope === 'process') {
              // CRD: start-host/stop-host are the *registration* tools —
              // start-host without --code just prints usage, and stop-host
              // doesn't exist at all. A registered host (config lives in
              // ~/.config/chrome-remote-desktop) is controlled via the
              // python CLI: chrome-remote-desktop --start / --stop.
              const crd = '/opt/google/chrome-remote-desktop/chrome-remote-desktop'
              if (m[2] !== 'start') await exec(crd, ['--stop'], 10000)
              const r = m[2] === 'stop'
                ? { code: 0, out: 'stopped' }
                : await exec(crd, ['--start'], 15000)
              return json(r.code === 0 ? 200 : 500, { ok: r.code === 0, detail: r.out || (r.code === 0 ? 'ok' : 'failed') })
            }
            const r = await exec('systemctl', ['--user', m[2], svc.unit!], 15000)
            return json(r.code === 0 ? 200 : 500, { ok: r.code === 0, detail: r.out || 'ok' })
          }

          json(404, { ok: false, error: 'not found' })
        })().catch((e) => {
          res.writeHead(500, { 'Content-Type': 'application/json' })
          res.end(JSON.stringify({ ok: false, error: String(e) }))
        })
      })
    },
  }
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, envDir, '')
  const proxyUrl = (env.XRLF_MEMORY_PROXY_URL || 'http://127.0.0.1:8400').replace(/\/$/, '')
  const soulUrl = (env.SOUL_URL || 'http://127.0.0.1:8405').replace(/\/$/, '')
  const mouthUrl = (env.MOUTH_URL || 'http://127.0.0.1:8406').replace(/\/$/, '')
  const proxyPort = (() => {
    try { return new URL(proxyUrl).port || '8400' } catch { return '8400' }
  })()

  return {
    plugins: [
      fvsGate(`${proxyUrl}/api/auth/me`),
      {
        name: 'ignition-availability',
        configureServer(server) {
          if (env.FOVEAI_IGNITION_URL) return
          // No external ignition service configured — ignite directly:
          // start the foveai-* user units (proxy :8400 first, then the
          // stack). Works even while the proxy is dead, which is exactly
          // when the red/grey ball needs it.
          server.middlewares.use('/ignition', async (_req, res) => {
            const units = [
              'foveai-backend.service', 'foveai-xrlf.service',
              'foveai-soul.service', 'foveai-tts.service', 'foveai-stt.service',
              'foveai-motor.service', 'foveai-subconscious.service',
              'foveai-chat-relay.service',
            ]
            const r = await exec('systemctl', ['--user', 'start', ...units], 15000)
            res.writeHead(r.code === 0 ? 202 : 500, { 'Content-Type': 'application/json' })
            res.end(JSON.stringify(r.code === 0
              ? { ok: true, started: units }
              : { ok: false, error: r.out || 'systemctl start failed' }))
          })
        },
      },
      remoteApi(),
      webvmStatic(),
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
      // VITE_HMR_MODE: 'tunnel' → HMR over wss://<page-host>:443 (rides the
      // cloudflared tunnel back to this port — needed for xarel.net access).
      // 'off' disables HMR. Unset → default local HMR.
      hmr: env.VITE_HMR_MODE === 'tunnel'
        ? { protocol: 'wss' as const, clientPort: 443 }
        : env.VITE_HMR_MODE === 'off'
          ? false
          : undefined,
      proxy: {
        ...(env.FOVEAI_IGNITION_URL ? {
          '/ignition': {
            target: env.FOVEAI_IGNITION_URL,
            changeOrigin: true,
          },
        } : {}),
        // noVNC shared desktop — websockify on :6080 serves the noVNC web UI
        // and the WS→VNC bridge. Same-origin so it works on localhost, LAN and tunnel.
        '/novnc': {
          target: 'http://127.0.0.1:6080',
          changeOrigin: true,
          ws: true,
          rewrite: (p) => p.replace(/^\/novnc/, ''),
        },
        // /rdp/* → remote-web (guacamole-lite) browser RDP client on :6081
        '/rdp': {
          target: 'http://127.0.0.1:6081',
          changeOrigin: true,
          ws: true,
          rewrite: (p) => p.replace(/^\/rdp/, '') || '/',
        },
        '/api/lmstudio': {
          target: env.LM_STUDIO_URL || 'http://127.0.0.1:1234',
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/api\/lmstudio/, ''),
        },
        // All API traffic → unified proxy on :8400 (HTTP + WS)
        // 8400 proxies chat to XRLF :8402, memory to :8407, TTS to :8406, etc.
        '/api/foveated': {
          target: proxyUrl,
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/api\/foveated/, '')
        },
        '/api/soul': {
          target: soulUrl,
          changeOrigin: true
        },
        // Creative service (Dreamscape image gen) — /api/dream + /api/dream/catalog
        '/api/dream': {
          target: env.CREATIVE_URL || 'http://127.0.0.1:8408',
          changeOrigin: true,
          timeout: 600000
        },
        // /webvm is served by the webvmStatic plugin (configureServer
        // middleware) — a proxy entry here never reaches the proxy layer.
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
        // Jen's autonomous mind — compagent :8405 owns /api/agent/* and
        // /api/thought_stream. (Was :8400, which never routed these —
        // the outbox poll silently 404'd.)
        '/api/agent': {
          target: soulUrl,
          changeOrigin: true
        },
        '/api/thought_stream': {
          target: soulUrl,
          changeOrigin: true
        },
        // ── Tunnel same-origin bridges (xarel.net / *.1um6a.se → :5177) ──
        // The CF tunnel routes apex hostnames to this port; these entries let
        // the settings panel + full API work through the tunnel with no ports.
        '/settings.html': {
          target: 'http://127.0.0.1:8401',
          changeOrigin: true
        },
        // settings.html's stylesheet must come from :8401 too — without this
        // it falls through to the SPA index.html and the panel renders unstyled
        '/settings.css': {
          target: 'http://127.0.0.1:8401',
          changeOrigin: true
        },
        // beta program intro page — same-origin via tunnel/LAN
        '/beta.html': {
          target: 'http://127.0.0.1:8401',
          changeOrigin: true
        },
        // member-facing settings page — same-origin via tunnel/LAN
        '/user-settings.html': {
          target: 'http://127.0.0.1:8401',
          changeOrigin: true
        },
        // beta downloads (jenna-vscode VSIX etc.) — same-origin via tunnel/LAN
        '/downloads': {
          target: 'http://127.0.0.1:8401',
          changeOrigin: true
        },
        // Whole :8401 public/ surface under one prefix — dashboard, companion,
        // prompt-kiosk, garage, launch — instead of per-file entries above.
        // Shielded: memory/settings panels are private surfaces.
        '/dash': {
          target: 'http://127.0.0.1:8401',
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/dash/, '') || '/'
        },
        '/xrlf': {
          target: 'http://127.0.0.1:8402',
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/xrlf/, '')
        },
        // Netdata machine metrics — same-origin so the dashboard embeds in
        // the Metrics tab on localhost, LAN and the CF tunnel (ws = live stream)
        '/netdata': {
          target: 'http://127.0.0.1:19999',
          changeOrigin: true,
          ws: true,
          rewrite: (p) => p.replace(/^\/netdata/, '') || '/'
        },
        '/v1': {
          target: proxyUrl,
          changeOrigin: true
        },
        '/health': {
          target: proxyUrl,
          changeOrigin: true
        },
        // Generic /api fallback LAST — specific /api/* routes above win
        '/api': {
          target: proxyUrl,
          changeOrigin: true
        }
      }
    }
  }
})
