/**
 * Nexus Proxy Server (Production-ready)
 *
 * What it does:
 * - Serves the static frontend (repo root) on the same origin
 * - Provides POST /proxy and POST /api/proxy to relay requests to AI providers (fixes browser CORS)
 *
 * Run:
 *   node nexus-proxy/server.js
 *
 * Env:
 *   PORT=8080                      (default: 8080; auto-fallback to next ports if busy)
 *   NEXUS_ALLOWED_ORIGINS=...       (optional comma list; if unset allows same-origin/no-origin)
 *
 * Security:
 * - HTTPS-only upstream + allowlist to avoid becoming an open proxy.
 */

import express from 'express';
import cors from 'cors';
import path from 'path';
import http from 'http';
import fs from 'fs';
import { createProxyMiddleware, fixRequestBody } from 'http-proxy-middleware';
import { fileURLToPath } from 'url';

const app = express();

// -----------------------------
// Paths (ESM-safe __dirname)
// -----------------------------
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Repo root = one level above nexus-proxy/
const REPO_ROOT = path.resolve(__dirname, '..');



// -----------------------------
// Config
// -----------------------------
const BASE_PORT = Number(process.env.PORT || 8080);

// Optional strict frontend origins
const allowedOriginsEnv = (process.env.NEXUS_ALLOWED_ORIGINS || '').trim();
const allowedOrigins = allowedOriginsEnv
    ? allowedOriginsEnv
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean)
    : null;

// Upstream allowlist (prevents open relay)
const ALLOW = [
    'https://api.openai.com',
    'https://api.anthropic.com',
    'https://iam.cloud.ibm.com',
    'https://us-south.ml.cloud.ibm.com',
    'https://eu-de.ml.cloud.ibm.com',
    'https://ruslanmv-ollabridge.hf.space',
    'https://ollabridge.com',
    'https://cloud.ollabridge.com',
];

// -----------------------------
// Middleware
// -----------------------------
app.use(express.json({ limit: '10mb' }));

app.use(
    cors({
        origin: (origin, cb) => {
            // Same-origin requests often have no Origin header
            if (!origin) return cb(null, true);

            // Allow chrome-extension:// origins (FoveAI Control Panel popup)
            if (origin && origin.startsWith('chrome-extension://')) return cb(null, true);

            // If no allowedOrigins configured, allow (good for dev)
            if (!allowedOrigins) return cb(null, true);

            return allowedOrigins.includes(origin)
                ? cb(null, true)
                : cb(new Error(`CORS blocked by proxy: origin not allowed: ${origin}`), false);
        },
        methods: ['GET', 'POST', 'OPTIONS'],
        allowedHeaders: ['Content-Type', 'Authorization', 'X-Requested-With', 'anthropic-version', 'anthropic-beta'],
        maxAge: 600,
    })
);

// Preflight: always succeed quickly
app.options('*', (req, res) => res.sendStatus(204));

// Inject security headers required for WebVM SharedArrayBuffer
app.use((req, res, next) => {
    console.log(`[REQ] ${req.method} ${req.url}`);
    res.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
    res.setHeader('Cross-Origin-Embedder-Policy', 'require-corp');
    next();
});

// -----------------------------
// FoveAI Memory API
// -----------------------------
app.get('/api/memory/history', (req, res) => {
    // REPO_ROOT is Frontend/3D_Avatar_Chatbot
    // We need to go up two levels to reach FoveAI root
    const memPath = path.resolve(REPO_ROOT, '..', '..', '.logs', 'memory_index.json');
    if (fs.existsSync(memPath)) {
        res.sendFile(memPath);
    } else {
        res.json({ conversations: [] });
    }
});

const MEMORY_BACKUP_DIR = path.resolve(REPO_ROOT, '..', '..', 'user_data', 'memory_backups');
const LATEST_BACKUP_FILE = path.join(MEMORY_BACKUP_DIR, 'memory_latest.json');

app.post('/api/memory/backup', (req, res) => {
    try {
        if (!fs.existsSync(MEMORY_BACKUP_DIR)) {
            fs.mkdirSync(MEMORY_BACKUP_DIR, { recursive: true });
        }
        
        fs.writeFileSync(LATEST_BACKUP_FILE, JSON.stringify(req.body, null, 2), 'utf-8');
        
        // Save history timestamped for rotation (simplified version of python's logic)
        const timestamp = new Date().toISOString().replace(/[:\.\-]/g, '');
        const backupFile = path.join(MEMORY_BACKUP_DIR, `memory_snapshot_${timestamp}.json`);
        fs.writeFileSync(backupFile, JSON.stringify(req.body, null, 2), 'utf-8');
        
        res.json({ status: 'ok', file: LATEST_BACKUP_FILE, timestamp });
    } catch (e) {
        console.error('[Memory Backup] Failed:', e.message);
        res.status(500).json({ error: e.message });
    }
});

app.post('/api/memory/restore', (req, res) => {
    try {
        if (fs.existsSync(LATEST_BACKUP_FILE)) {
            const data = fs.readFileSync(LATEST_BACKUP_FILE, 'utf-8');
            res.json(JSON.parse(data));
        } else {
            res.json({ status: 'empty', message: 'No backup available' });
        }
    } catch (e) {
        console.error('[Memory Restore] Failed:', e.message);
        res.status(500).json({ error: e.message });
    }
});


// --- Health Proxy: route /api/health-proxy/:port to any local service ---
// This lets the Chrome Extension (chrome-extension:// origin) check service
// health through the Nexus Proxy, avoiding CORS errors when fetching
// http://127.0.0.1:8000/health etc. directly from the extension popup.
// IMPORTANT: This MUST be defined BEFORE the catch-all /api proxy middleware
// otherwise the proxy would forward it to soul_core.py which doesn't handle it.
app.get('/api/health-proxy/:port', async (req, res) => {
    const targetPort = parseInt(req.params.port, 10);
    if (isNaN(targetPort) || targetPort < 1 || targetPort > 65535) {
        return res.status(400).json({ error: 'Invalid port' });
    }
    try {
        const response = await fetch(`http://127.0.0.1:${targetPort}/health`, {
            signal: AbortSignal.timeout(3000)
        });
        const body = response.ok ? await response.text() : null;
        res.json({ ok: response.ok, status: response.status, port: targetPort, body });
    } catch (e) {
        res.json({ ok: false, status: 0, port: targetPort, error: e.message });
    }
});

// --- Dynamic Generic Proxy: route /api/proxy/:port/* to any local service ---
// Supports GET, POST, SSE streams, etc.
// IMPORTANT: This MUST be defined BEFORE the catch-all /api proxy middleware
// otherwise the proxy would forward it to soul_core.py which doesn't handle it.
app.use('/api/proxy/:port', createProxyMiddleware({
    target: 'http://127.0.0.1:8000', // default fallback
    router: (req) => {
        const match = req.originalUrl.match(/\/api\/proxy\/(\d+)/);
        const port = match ? match[1] : '8000';
        return `http://127.0.0.1:${port}`;
    },
    changeOrigin: true,
    pathRewrite: (path, req) => {
        const match = req.originalUrl.match(/\/api\/proxy\/(\d+)/);
        if (match) {
            return path.replace(`/api/proxy/${match[1]}`, '');
        }
        return path;
    },
    onError: (err, req, res) => {
        const match = req.originalUrl.match(/\/api\/proxy\/(\d+)/);
        const port = match ? match[1] : 'unknown';
        console.error(`[Nexus Proxy] Dynamic proxy failed for port ${port}:`, err.message);
        if (!res.headersSent) {
            res.status(502).json({ error: 'Service not available', port });
        }
    }
}));


// --- Soundboard Context (moved from XR_Vessel xr_app.py) ---
// Returns bracket token context for AI non-verbal expression injection.
// This was the only endpoint actively used from XR Vessel (port 8101).
// GET /api/soundboard/context
const SOUNDBOARD_DIR = path.resolve(REPO_ROOT, '..', '..', 'Body', 'XR_Vessel', 'public', 'soundboard');

app.get('/api/soundboard/context', (req, res) => {
    const sounds = [];
    if (fs.existsSync(SOUNDBOARD_DIR)) {
        const files = fs.readdirSync(SOUNDBOARD_DIR).sort();
        for (const f of files) {
            if (f.endsWith('.wav')) {
                sounds.push(f.replace('.wav', ''));
            }
        }
    }
    const defaults = [
        'gasp_subtle', 'laugh_soft', 'sigh_content', 'hmm_thoughtful',
        'oh_realization', 'throat_clear', 'chuckle_warm', 'mmhm_affirming',
    ];
    const allTags = [...new Set([...defaults, ...sounds])].sort();
    const lines = [
        "=== SOUNDBOARD EXPRESSIONS ===",
        "You have an expressive local soundboard and dynamic audio generation system.",
        "Use bracket tokens in your responses to express emotion non-verbally:",
        "  - Existing sounds: <audio:tag> or <flavour:tag>",
        "  - Face blendshapes: <emotion:tag> (happy, sad, surprised, curious, content, neutral, angry, fearful)",
        "  - Generate custom sound: <request:description> (synthesis pipeline handles this dynamically)",
        "",
        "Available tags:",
    ];
    for (const tag of allTags) {
        lines.push(`  ${tag}`);
    }
    res.json({ context: lines.join('\n'), tags: allTags });
});

// -----------------------------
// Proxy route (MUST be before catch-all /api proxy)
// Body: { url, method, headers, body }
// -----------------------------
async function handleProxy(req, res) {
    try {
        const { url, method, headers, body } = req.body || {};

        if (!url || typeof url !== 'string') {
            // This is useful for "supportsApiProxy()" probe — it should return 400 if route exists.
            return res.status(400).json({ error: 'Missing "url" in request body.' });
        }
        if (!httpsOnly(url)) {
            return res.status(400).json({ error: 'Only https:// URLs are allowed.' });
        }
        if (!isAllowedUrl(url)) {
            return res.status(403).json({ error: 'Target URL not in allowlist.' });
        }

        const m = String(method || 'POST').toUpperCase();
        const h = headers && typeof headers === 'object' ? headers : {};
        const fetchHeaders = new Headers(h);

        const hasBody = body !== undefined && body !== null;
        if (hasBody && !fetchHeaders.has('content-type')) {
            fetchHeaders.set('content-type', 'application/json');
        }

        const upstreamBody = !hasBody ? undefined : typeof body === 'string' ? body : JSON.stringify(body);

        console.log(`[Proxy] ${m} -> ${url}`);

        const upstream = await fetch(url, {
            method: m,
            headers: fetchHeaders,
            body: upstreamBody,
        });

        const text = await upstream.text();

        res.status(upstream.status);

        const safe = copySafeHeaders(upstream.headers);
        Object.entries(safe).forEach(([k, v]) => res.setHeader(k, v));

        return res.send(text);
    } catch (err) {
        console.error('[Proxy Error]', err);
        return res.status(500).json({ error: err?.message || String(err) });
    }
}

app.post('/proxy', handleProxy);
app.post('/api/proxy', handleProxy); // alias for old frontends

// --- XR Monetization Proxy (Port 8101) ---
app.use('/api/monetize', createProxyMiddleware({
    target: 'http://127.0.0.1:8101',
    changeOrigin: true,
    pathRewrite: {
        '^/': '/api/monetize/'
    },
    onError: (err, req, res) => {
        console.error('[Nexus Proxy] Failed to connect to xr_app.py on 8101:', err.message);
        if (!res.headersSent) {
            res.status(502).json({ error: 'XR Monetization not available', port: 8101 });
        }
    }
}));

// -----------------------------
// FoveAI Local TTS Proxy
// GET /api/tts?text=... -> POST http://127.0.0.1:8004/tts
// -----------------------------
app.get('/api/tts', async (req, res) => {
    const text = req.query.text;
    if (!text) return res.status(400).json({ error: 'Missing "text" query parameter.' });

    try {
        console.log(`[TTS Proxy] Getting audio for: "${text.substring(0, 30)}..."`);
        const upstream = await fetch('http://127.0.0.1:8004/tts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: text })
        });

        if (!upstream.ok) {
            return res.status(upstream.status).json({ error: `Upstream: ${upstream.status} ${upstream.statusText}` });
        }

        const ct = upstream.headers.get('content-type') || 'audio/wav';
        const cl = upstream.headers.get('content-length');

        res.setHeader('Content-Type', ct);
        if (cl) res.setHeader('Content-Length', cl);
        const buf = Buffer.from(await upstream.arrayBuffer());
        return res.status(200).send(buf);
    } catch (err) {
        console.error('[TTS Proxy Error]', err);
        return res.status(500).json({ error: err?.message || String(err) });
    }
});

// --- Ears Core API Proxy (Port 8001) ---
app.use('/api/soul/stt', createProxyMiddleware({
    target: 'http://127.0.0.1:8001',
    changeOrigin: true,
    pathRewrite: {
        '^/': '/stt'
    },
    on: {
        proxyReq: fixRequestBody
    },
    onError: (err, req, res) => {
        console.error('[Nexus Proxy] Failed to connect to Ears on 8001:', err.message);
        if (!res.headersSent) {
            res.status(502).json({ error: 'Ears STT not available', port: 8001 });
        }
    }
}));

// --- Stardust Vector Memory Proxy (Port 8109) ---
app.use('/api/memory/stardust', createProxyMiddleware({
    target: 'http://127.0.0.1:8109',
    changeOrigin: true,
    pathRewrite: {
        '^/api/memory/stardust': ''
    },
    on: {
        proxyReq: fixRequestBody
    },
    onError: (err, req, res) => {
        console.error('[Nexus Proxy] Failed to connect to Stardust on 8109:', err.message);
        if (!res.headersSent) {
            res.status(502).json({ error: 'Stardust Memory not available', port: 8109 });
        }
    }
}));

// --- Soul Core API Proxy (Port 8000) ---
// Forward all /api requests to the XRLF runtime (the new Soul)
// This is a catch-all — any /api/* route not matched by specific routes above
// will be forwarded to the XRLF runtime on port 8402.
app.use('/api', createProxyMiddleware({
    target: 'http://127.0.0.1:8402',
    changeOrigin: true,
    // Express strips the /api prefix when using app.use('/api', ...)
    // so /api/soul/env becomes /soul/env. We need to add /api back.
    pathRewrite: {
        '^/': '/api/'
    },
    on: {
        proxyReq: fixRequestBody
    },
    onError: (err, req, res) => {
        console.error('[Nexus Proxy] Failed to connect to soul_core.py on 8000:', err.message);
        // Return a graceful error instead of hanging
        if (!res.headersSent) {
            res.status(502).json({ error: 'Soul Core not available', service: 'soul_core', port: 8000 });
        }
    }
}));

// Serve static frontend (repo root)
app.use(express.static(REPO_ROOT, { extensions: ['html'] }));

// -----------------------------
// Helpers
// -----------------------------
function isAllowedUrl(url) {
    const u = String(url || '');
    // Allow configured upstream APIs
    if (ALLOW.some((base) => u.startsWith(base))) return true;
    // Allow local network URLs (OllaBridge, HomePilot, Ollama on LAN)
    if (isLocalNetworkUrl(u)) return true;
    return false;
}

function isLocalNetworkUrl(url) {
    try {
        const u = new URL(url);
        const host = u.hostname;
        return (
            host === 'localhost' ||
            host === '127.0.0.1' ||
            host === '0.0.0.0' ||
            host.startsWith('192.168.') ||
            host.startsWith('10.') ||
            /^172\.(1[6-9]|2\d|3[01])\./.test(host)
        );
    } catch {
        return false;
    }
}

function httpsOnly(url) {
    const u = String(url || '');
    // Allow HTTP for local network (OllaBridge, Ollama, HomePilot)
    if (isLocalNetworkUrl(u)) return true;
    return /^https:\/\//i.test(u);
}

// Pass through only safe headers (but keep content-type)
function copySafeHeaders(upstreamHeaders) {
    const out = {};
    const ct = upstreamHeaders.get('content-type');
    if (ct) out['content-type'] = ct;

    // Optional: pass through rate-limit headers if you want them on the frontend.
    const rl = upstreamHeaders.get('x-ratelimit-remaining');
    if (rl) out['x-ratelimit-remaining'] = rl;

    return out;
}

// -----------------------------
// Health
// -----------------------------
app.get('/health', (req, res) => {
    res.json({ ok: true, service: 'nexus-proxy', port: app.get('port') });
});

app.get('/motor/subscribe', (req, res) => {
    const proxyReq = http.request('http://127.0.0.1:8110/motor/subscribe', { method: 'GET' }, (proxyRes) => {
        res.writeHead(proxyRes.statusCode, proxyRes.headers);
        proxyRes.pipe(res);
    });
    proxyReq.on('error', (err) => {
        console.error('[MotorProxy] Error:', err.message);
        res.status(502).json({ error: 'Motor daemon unreachable' });
    });
    req.pipe(proxyReq);
});

    // End motor proxy

// -----------------------------
// Avatar Proxy (binary passthrough for CORS-blocked avatar CDNs)
// GET /api/avatar-proxy?url=https://models.readyplayer.me/...
// -----------------------------
const AVATAR_PROXY_HOSTS = [
    'api.avaturn.me',
    'cdn.avaturn.me',
    'raw.githubusercontent.com',
    'github.com',
    'hub.vroid.com',
    'api.sketchfab.com',
    'media.sketchfab.com',
    'arweave.net',
    'gateway.irys.xyz',
    'cdn.discordapp.com',
    'pub-c8f0641365ad47e5b3e1c85c39874909.r2.dev',
    'r2.dev',
    'avatars.yourfriend.online',
    'vrm-avatar-catalog.cloud-data.workers.dev',
    'homepilotai.github.io',
    's3.amazonaws.com',
    'amazonaws.com',
];

function isAllowedAvatarHost(urlStr) {
    try {
        const u = new URL(urlStr);
        return (
            u.protocol === 'https:' && AVATAR_PROXY_HOSTS.some((h) => u.hostname === h || u.hostname.endsWith('.' + h))
        );
    } catch {
        return false;
    }
}

app.get('/api/avatar-proxy', async (req, res) => {
    const targetUrl = req.query.url;
    if (!targetUrl) return res.status(400).json({ error: 'Missing "url" query parameter.' });
    if (!isAllowedAvatarHost(targetUrl)) {
        return res.status(403).json({ error: 'Host not in avatar proxy allowlist.' });
    }

    try {
        console.log(`[Avatar Proxy] GET -> ${targetUrl}`);
        const upstream = await fetch(targetUrl);
        if (!upstream.ok) {
            return res.status(upstream.status).json({ error: `Upstream: ${upstream.status} ${upstream.statusText}` });
        }

        const ct = upstream.headers.get('content-type') || 'application/octet-stream';
        const cl = upstream.headers.get('content-length');

        res.setHeader('Content-Type', ct);
        if (cl) res.setHeader('Content-Length', cl);
        res.setHeader('Cache-Control', 'public, max-age=86400');

        const buf = Buffer.from(await upstream.arrayBuffer());
        return res.status(200).send(buf);
    } catch (err) {
        console.error('[Avatar Proxy Error]', err);
        return res.status(500).json({ error: err?.message || String(err) });
    }
});

// -----------------------------
// VRoid Hub API Proxy (bypasses CORS for hub.vroid.com API)
// GET  /api/vroid-hub?action=list|search|account|...  (requires Authorization header)
// POST /api/vroid-hub  { action: 'token', params: {...} }
// -----------------------------
const VROID_API = 'https://hub.vroid.com';
const VROID_API_VERSION = '11';

app.get('/api/vroid-hub', async (req, res) => {
    const action = req.query.action;

    // env_config — tell client whether server has pre-configured credentials (no auth required)
    if (action === 'env_config') {
        const ENV_APP_ID = process.env.VROID_APP_ID || '';
        const ENV_APP_SECRET = process.env.VROID_APP_SECRET || '';
        return res.json({
            hasEnvCredentials: !!(ENV_APP_ID && ENV_APP_SECRET),
            appId: ENV_APP_ID || null,
        });
    }

    const token = (req.headers.authorization || '').replace(/^Bearer\s+/i, '');

    if (!token) return res.status(401).json({ error: 'Missing Authorization header' });

    const vroidHeaders = {
        'X-Api-Version': VROID_API_VERSION,
        Authorization: `Bearer ${token}`,
    };

    try {
        let apiPath;
        if (action === 'account') {
            apiPath = '/api/account';
        } else if (action === 'staff_picks') {
            const count = req.query.count || '50';
            apiPath = `/api/staff_picks?count=${count}${req.query.max_id ? `&max_id=${req.query.max_id}` : ''}`;
        } else if (action === 'list') {
            const count = req.query.count || '50';
            apiPath = `/api/account/character_models?count=${count}${req.query.max_id ? `&max_id=${req.query.max_id}` : ''}`;
        } else if (action === 'hearts') {
            const count = req.query.count || '50';
            let p = `/api/hearts?count=${count}`;
            if (req.query.application_id) p += `&application_id=${req.query.application_id}`;
            if (req.query.max_id) p += `&max_id=${req.query.max_id}`;
            apiPath = p;
        } else if (action === 'search') {
            if (!req.query.keyword) return res.status(400).json({ error: 'Missing keyword' });
            let p = `/api/search/character_models?keyword=${encodeURIComponent(req.query.keyword)}&count=${req.query.count || '50'}`;
            // Pass through official VRoid Hub search filter params
            const searchFilters = ['is_downloadable', 'characterization_allowed_user', 'sort'];
            searchFilters.forEach((f) => {
                if (req.query[f]) p += `&${f}=${encodeURIComponent(req.query[f])}`;
            });
            // Cursor-based pagination: search_after[] from _links.next.href
            if (req.query['search_after[]']) {
                const sa = Array.isArray(req.query['search_after[]'])
                    ? req.query['search_after[]']
                    : [req.query['search_after[]']];
                sa.forEach((v) => {
                    p += `&search_after[]=${encodeURIComponent(v)}`;
                });
            }
            apiPath = p;
        } else if (action === 'heart') {
            if (!req.query.character_model_id) return res.status(400).json({ error: 'Missing character_model_id' });
            const heartRes = await fetch(`${VROID_API}/api/hearts`, {
                method: 'POST',
                headers: { ...vroidHeaders, 'Content-Type': 'application/json' },
                body: JSON.stringify({ character_model_id: req.query.character_model_id }),
            });
            // 200 = hearted, 409 = already hearted (both are fine)
            if (heartRes.ok || heartRes.status === 409) {
                return res.status(200).json({ success: true });
            }
            const heartData = await heartRes.json().catch(() => ({}));
            return res.status(heartRes.status).json(heartData);
        } else if (action === 'download_license') {
            if (!req.query.character_model_id) return res.status(400).json({ error: 'Missing character_model_id' });
            const dlRes = await fetch(`${VROID_API}/api/download_licenses`, {
                method: 'POST',
                headers: { ...vroidHeaders, 'Content-Type': 'application/json' },
                body: JSON.stringify({ character_model_id: req.query.character_model_id }),
            });
            return res.status(dlRes.status).json(await dlRes.json());
        } else if (action === 'download') {
            if (!req.query.license_id) return res.status(400).json({ error: 'Missing license_id' });
            const dlRes = await fetch(`${VROID_API}/api/download_licenses/${req.query.license_id}/download`, {
                headers: vroidHeaders,
                redirect: 'manual',
            });
            if (dlRes.status === 302 || dlRes.status === 301) {
                return res.json({ download_url: dlRes.headers.get('location') });
            }
            return res.status(dlRes.status).json(await dlRes.json().catch(() => ({})));
        } else {
            return res.status(400).json({ error: 'Unknown action' });
        }

        const upstream = await fetch(`${VROID_API}${apiPath}`, { headers: vroidHeaders });
        return res.status(upstream.status).json(await upstream.json());
    } catch (err) {
        console.error('[vroid-hub] error:', err);
        return res.status(500).json({ error: err?.message || String(err) });
    }
});

app.post('/api/vroid-hub', async (req, res) => {
    const { action, params } = req.body || {};
    if (action === 'token' && params) {
        try {
            const tokenRes = await fetch(`${VROID_API}/oauth/token`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'X-Api-Version': VROID_API_VERSION },
                body: new URLSearchParams(params).toString(),
            });
            return res.status(tokenRes.status).json(await tokenRes.json());
        } catch (err) {
            return res.status(500).json({ error: err?.message || String(err) });
        }
    }
    return res.status(400).json({ error: 'Unknown POST action' });
});

// -----------------------------
// VRoid Hub OAuth Callback (mirrors api/vroid-hub-callback.js for local dev)
// GET /api/vroid-hub-callback?code=...&state=...
// -----------------------------
app.get('/api/vroid-hub-callback', async (req, res) => {
    const { code, state, error } = req.query;

    const html = (body) => `<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>VRoid Hub — OAuth</title>
<style>
    body { font-family: system-ui, sans-serif; display: flex; justify-content: center;
           align-items: center; min-height: 100vh; margin: 0; background: #1a1a2e; color: #e0e0e0; }
    div { text-align: center; padding: 2rem; }
    h2 { color: #7c4dff; }
</style>
</head><body><div>${body}</div></body></html>`;

    const esc = (s) =>
        String(s || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');

    if (error) {
        return res.type('html').send(
            html(`<h2>Authorization Failed</h2>
                <p>${esc(error)}: ${esc(req.query.error_description)}</p>
                <script>
                    window.opener && window.opener.postMessage({ type: 'vroid-oauth-error', error: ${JSON.stringify(error)} }, '*');
                    setTimeout(() => window.close(), 3000);
                </script>`)
        );
    }

    if (!code || !state) {
        return res.type('html').send(html('<h2>Missing Parameters</h2><p>Authorization code or state missing.</p>'));
    }

    try {
        const stateData = JSON.parse(Buffer.from(state, 'base64').toString());
        const { codeVerifier, clientId, clientSecret, redirectUri } = stateData;

        // Use server env vars as fallback
        const ENV_APP_ID = process.env.VROID_APP_ID || '';
        const ENV_APP_SECRET = process.env.VROID_APP_SECRET || '';
        const finalClientId = clientId || ENV_APP_ID;
        const finalClientSecret = clientSecret || ENV_APP_SECRET;

        const tokenRes = await fetch(`${VROID_API}/oauth/token`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-Api-Version': VROID_API_VERSION,
            },
            body: new URLSearchParams({
                grant_type: 'authorization_code',
                code,
                client_id: finalClientId,
                client_secret: finalClientSecret,
                redirect_uri: redirectUri,
                code_verifier: codeVerifier,
            }).toString(),
        });

        const tokenData = await tokenRes.json();

        if (!tokenData.access_token) {
            return res.type('html').send(
                html(`<h2>Token Exchange Failed</h2>
                    <p>${esc(tokenData.error || tokenData.error_description || 'Unknown error')}</p>
                    <script>
                        window.opener && window.opener.postMessage({
                            type: 'vroid-oauth-error',
                            error: ${JSON.stringify(tokenData.error || 'token_exchange_failed')}
                        }, '*');
                        setTimeout(() => window.close(), 3000);
                    </script>`)
            );
        }

        console.log('[vroid-hub-callback] OAuth token exchange successful');

        return res.type('html').send(
            html(`<h2>Connected!</h2>
                <p>VRoid Hub authorized successfully. This window will close automatically.</p>
                <script>
                    window.opener && window.opener.postMessage({
                        type: 'vroid-oauth-success',
                        accessToken: ${JSON.stringify(tokenData.access_token)},
                        refreshToken: ${JSON.stringify(tokenData.refresh_token || '')},
                        expiresIn: ${tokenData.expires_in || 3600}
                    }, '*');
                    setTimeout(() => window.close(), 1500);
                </script>`)
        );
    } catch (err) {
        console.error('[vroid-hub-callback] error:', err);
        return res.type('html').send(
            html(`<h2>Error</h2>
                <p>${esc(err.message)}</p>
                <script>
                    window.opener && window.opener.postMessage({ type: 'vroid-oauth-error', error: 'callback_error' }, '*');
                    setTimeout(() => window.close(), 3000);
                </script>`)
        );
    }
});

// SPA fallback: serve index.html for unknown GET routes
app.get('*', (req, res) => {
    res.sendFile(path.join(REPO_ROOT, 'index.html'));
});

// -----------------------------
// Start server (auto-port fallback with SO_REUSEADDR)
// -----------------------------
function listenWithFallback(startPort, tries = 20) {
    let port = startPort;

    // Use http.createServer + explicit server.listen so we can set SO_REUSEADDR
    // This allows binding to a port that's in TIME_WAIT on Windows, preventing
    // unnecessary fallback to higher ports when the extension expects port 8080.
    const server = http.createServer(app);
    server.on('connection', (socket) => {
        // Suppress ECONNRESET on rapid restart
        socket.on('error', () => {});
    });

    server.listen(port, () => {
        app.set('port', port);
        console.log(`🚀 Nexus (static + proxy) running: http://127.0.0.1:${port}`);
        console.log(`   Health:               http://127.0.0.1:${port}/health`);
        console.log(`   Proxy:                http://127.0.0.1:${port}/proxy`);
        console.log(`   Proxy (alias):        http://127.0.0.1:${port}/api/proxy`);
    });

    server.on('error', (err) => {
        if (err && err.code === 'EADDRINUSE' && tries > 0) {
            console.warn(`⚠️ Port ${port} in use. Trying ${port + 1}...`);
            server.close(() => listenWithFallback(port + 1, tries - 1));
            return;
        }
        console.error('❌ Server error:', err);
        process.exit(1);
    });
}

listenWithFallback(BASE_PORT);
