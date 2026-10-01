/**
 * ═══════════════════════════════════════════════════════════════════
 * LumaxConProxy (V4) — AI Token-Stripping Internet Proxy
 * ═══════════════════════════════════════════════════════════════════
 *
 * System-wide HTTPS MITM proxy on port 8900.
 * - Detects AI API traffic (OpenAI, Anthropic, Google, etc.)
 * - Strips tokens via Foveated XRL pipeline before forwarding
 * - All other traffic: pure TCP passthrough (zero overhead)
 * - HTTPS MITM via local CA cert (install once via scripts/install-ca.ps1)
 * - Web dashboard on port 8901
 *
 * Usage:
 *   node proxy.js            # Start proxy
 *   node proxy.js --verbose  # Verbose logging
 */

'use strict';

const http    = require('http');
const https   = require('https');
const net     = require('net');
const url     = require('url');
const path    = require('path');
const fs      = require('fs');
const forge   = require('node-forge');

const config  = JSON.parse(fs.readFileSync(path.join(__dirname, 'config.json'), 'utf8'));
const stats   = require('./core/stats');
const strip   = require('./core/interceptor');
const dashboard = require('./core/dashboard');
const ca      = require('./core/ca-manager');

const PORT    = parseInt(process.env.LUMAX_CON_PORT || config.port, 10);
const VERBOSE = process.argv.includes('--verbose') || config.verbose;

const AI_HOSTS = new Set(config.ai_hosts.map(h => h.toLowerCase()));
const AI_PATHS = config.ai_paths;

function log(...args) { if (VERBOSE) console.log('[LumaxConProxy]', ...args); }
function info(...args) { console.log('[LumaxConProxy]', ...args); }

// ── AI Traffic Detection ──────────────────────────────────────────────────────

function isAiHost(hostname) {
    const h = (hostname || '').toLowerCase();
    if (AI_HOSTS.has(h)) return true;
    for (const host of AI_HOSTS) {
        if (h.endsWith('.' + host)) return true;
    }
    return false;
}

function isAiPath(p) {
    return AI_PATHS.some(ap => p.startsWith(ap));
}

// ── HTTPS MITM — intercept AI, tunnel everything else ────────────────────────

async function handleConnect(req, clientSocket, head) {
    const [hostname, portStr] = req.url.split(':');
    const port = parseInt(portStr || '443', 10);

    clientSocket.on('error', () => {});

    if (!isAiHost(hostname)) {
        // Pure TCP tunnel — not AI, don't touch it
        log(`TUNNEL ${hostname}:${port}`);
        const serverSocket = net.connect(port, hostname, () => {
            clientSocket.write('HTTP/1.1 200 Connection Established\r\n\r\n');
            serverSocket.write(head);
            serverSocket.pipe(clientSocket);
            clientSocket.pipe(serverSocket);
        });
        serverSocket.on('error', () => clientSocket.destroy());
        stats.record('tunnel', hostname);
        return;
    }

    // AI host → MITM with our CA cert
    log(`MITM  ${hostname}:${port}`);
    try {
        const { cert, key } = await ca.getCertForHost(hostname);
        clientSocket.write('HTTP/1.1 200 Connection Established\r\n\r\n');

        const tlsServer = new https.Server({ cert, key });
        tlsServer.on('request', (mitmReq, mitmRes) => handleAiRequest(mitmReq, mitmRes, hostname, port));
        tlsServer.on('error', () => clientSocket.destroy());

        const mitmSocket = tlsServer.emit('connection', clientSocket);
        if (head.length) clientSocket.unshift(head);

        // Start TLS with the client using our fake cert
        const tlsSocket = require('tls').connect({
            socket: clientSocket,
            isServer: true,
            cert, key,
        });
        tlsSocket.on('error', () => {});
        tlsServer.emit('secureConnection', tlsSocket);
    } catch (err) {
        // Fallback to plain tunnel if MITM fails
        console.error('[LumaxConProxy] MITM error for', hostname, ':', err.message);
        const serverSocket = net.connect(port, hostname, () => {
            clientSocket.write('HTTP/1.1 200 Connection Established\r\n\r\n');
            serverSocket.write(head);
            serverSocket.pipe(clientSocket);
            clientSocket.pipe(serverSocket);
        });
        serverSocket.on('error', () => clientSocket.destroy());
    }
}

// ── AI Request Handler — strip tokens then forward ───────────────────────────

async function handleAiRequest(req, res, targetHost, targetPort) {
    const chunks = [];
    req.on('data', c => chunks.push(c));
    req.on('end', async () => {
        const rawBody = Buffer.concat(chunks);
        let body = rawBody;
        let tokensSaved = 0;

        if (req.method === 'POST' && isAiPath(req.url)) {
            try {
                const parsed = JSON.parse(rawBody.toString('utf8'));
                if (parsed.messages && Array.isArray(parsed.messages)) {
                    const before = JSON.stringify(parsed).length;
                    const stripped = await strip.stripMessages(parsed, config.compression);
                    const after = JSON.stringify(stripped).length;
                    tokensSaved = Math.round((before - after) / 4);
                    body = Buffer.from(JSON.stringify(stripped), 'utf8');
                    log(`Stripped ${before}→${after} chars (~${tokensSaved} tokens) for ${targetHost}${req.url}`);
                    stats.record('strip', targetHost, tokensSaved);
                }
            } catch (e) {
                log('Body parse error (non-JSON or binary), passing through:', e.message);
            }
        }

        // Forward to real upstream
        const options = {
            hostname: targetHost,
            port: targetPort || 443,
            path: req.url,
            method: req.method,
            headers: {
                ...req.headers,
                host: targetHost,
                'content-length': body.length,
            },
        };
        delete options.headers['transfer-encoding'];

        const proto = (targetPort === 80) ? http : https;
        const proxyReq = proto.request(options, (proxyRes) => {
            res.writeHead(proxyRes.statusCode, proxyRes.headers);
            proxyRes.pipe(res);
        });
        proxyReq.on('error', (e) => {
            console.error('[LumaxConProxy] upstream error:', e.message);
            res.writeHead(502);
            res.end('LumaxConProxy: upstream error — ' + e.message);
        });
        proxyReq.write(body);
        proxyReq.end();
    });
}

// ── Plain HTTP requests (non-CONNECT) ────────────────────────────────────────

function handleRequest(req, res) {
    const parsed = url.parse(req.url);
    const hostname = parsed.hostname || req.headers.host;

    const chunks = [];
    req.on('data', c => chunks.push(c));
    req.on('end', async () => {
        let body = Buffer.concat(chunks);
        let tokensSaved = 0;

        if (isAiHost(hostname) && isAiPath(parsed.path) && req.method === 'POST') {
            try {
                const json = JSON.parse(body.toString('utf8'));
                if (json.messages) {
                    const before = body.length;
                    const stripped = await strip.stripMessages(json, config.compression);
                    body = Buffer.from(JSON.stringify(stripped), 'utf8');
                    tokensSaved = Math.round((before - body.length) / 4);
                    stats.record('strip', hostname, tokensSaved);
                }
            } catch (_) {}
        } else {
            stats.record('pass', hostname);
        }

        const options = {
            hostname: parsed.hostname,
            port: parseInt(parsed.port || '80', 10),
            path: parsed.path,
            method: req.method,
            headers: { ...req.headers, host: parsed.hostname, 'content-length': body.length },
        };
        delete options.headers['transfer-encoding'];

        const proxyReq = http.request(options, (proxyRes) => {
            res.writeHead(proxyRes.statusCode, proxyRes.headers);
            proxyRes.pipe(res);
        });
        proxyReq.on('error', (e) => { res.writeHead(502); res.end('Upstream error'); });
        proxyReq.write(body);
        proxyReq.end();
    });
}

// ── Proxy Server ──────────────────────────────────────────────────────────────

const server = http.createServer(handleRequest);
server.on('connect', handleConnect);

server.listen(PORT, '127.0.0.1', () => {
    info(`════════════════════════════════════════`);
    info(`  LumaxConProxy V4 — port ${PORT}`);
    info(`  Dashboard    → http://127.0.0.1:${config.dashboardPort}`);
    info(`  MITM CA      → ${config.mitm.ca_cert_path}`);
    info(`  AI hosts     → ${config.ai_hosts.length} targets`);
    info(`════════════════════════════════════════`);

    // Start dashboard server
    dashboard.start(config.dashboardPort, stats);
});

server.on('error', (err) => {
    console.error('[LumaxConProxy] Server error:', err.message);
    process.exit(1);
});

// Graceful shutdown
process.on('SIGINT', () => { info('Shutting down...'); server.close(() => process.exit(0)); });
process.on('SIGTERM', () => { server.close(() => process.exit(0)); });
