/*
 * FoveAI remote-web — browser RDP client bridge.
 *
 * guacamole-lite terminates the WebSocket from the page and speaks guacd
 * protocol to guacd (127.0.0.1:4822), which in turn RDPs into xrdp :3389.
 * The Multigate vite server proxies /rdp/ → http://127.0.0.1:6081 (ws:true).
 *
 *   GET  /           → client page (public/index.html)
 *   POST /token      → { host, username, password } → encrypted guac token
 *   WS   /guacamole?token=…  → guacamole-lite tunnel
 */
const path = require('path');
const crypto = require('crypto');
const express = require('express');
const http = require('http');
const GuacamoleLite = require('guacamole-lite');

const PORT = parseInt(process.env.REMOTE_WEB_PORT || '6081', 10);
const GUACD_HOST = process.env.GUACD_HOST || '127.0.0.1';
const GUACD_PORT = parseInt(process.env.GUACD_PORT || '4822', 10);
const RDP_HOST = process.env.RDP_TARGET || '127.0.0.1';
const RDP_PORT = parseInt(process.env.RDP_PORT || '3389', 10);

// guacamole-lite requires AES-256-CBC tokens; generate per-process key
// unless one is pinned in env (restart invalidates issued tokens — fine).
const CRYPT_KEY = process.env.REMOTE_WEB_KEY
  ? Buffer.from(process.env.REMOTE_WEB_KEY).subarray(0, 32)
  : crypto.randomBytes(32);

function encryptToken(obj) {
  const iv = crypto.randomBytes(16);
  const cipher = crypto.createCipheriv('aes-256-cbc', CRYPT_KEY, iv);
  const enc = Buffer.concat([cipher.update(JSON.stringify(obj), 'utf8'), cipher.final()]);
  return Buffer.from(JSON.stringify({ iv: iv.toString('base64'), value: enc.toString('base64') })).toString('base64');
}

const app = express();
app.use(express.json());

// the client page + guacamole-common-js ESM bundle (self-contained default export)
app.use(express.static(path.join(__dirname, 'public')));
app.use('/js', express.static(path.join(__dirname, 'node_modules', 'guacamole-common-js', 'dist')));

app.post('/token', (req, res) => {
  const { host, username, password } = req.body || {};
  if (!username || !password) return res.status(400).json({ error: 'username and password required' });
  const token = encryptToken({
    connection: {
      type: 'rdp',
      settings: {
        hostname: host || RDP_HOST,
        port: String(RDP_PORT),
        username, password,
        security: 'any',
        'ignore-cert': 'true',
        'enable-wallpaper': 'true',
        width: req.body.width || 1280,
        height: req.body.height || 800,
        dpi: 96,
      },
    },
  });
  res.json({ token });
});

const server = http.createServer(app);

new GuacamoleLite(
  { server, path: '/guacamole' },
  { host: GUACD_HOST, port: GUACD_PORT },
  { crypt: { cypher: 'AES-256-CBC', key: CRYPT_KEY }, log: { level: 'ERRORS', stdLog: console.error, errorLog: console.error } },
);

server.listen(PORT, '127.0.0.1', () => {
  console.log(`remote-web listening on 127.0.0.1:${PORT} → guacd ${GUACD_HOST}:${GUACD_PORT} → rdp ${RDP_HOST}:${RDP_PORT}`);
});
