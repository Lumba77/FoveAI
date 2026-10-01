/**
 * dashboard.js — LumaxConProxy Web Dashboard (port 8901)
 * Serves the management UI and stats API.
 */

'use strict';

const http = require('http');
const path = require('path');
const fs   = require('fs');

let _stats = null;
let _config = null;

function start(port, statsModule) {
    _stats = statsModule;
    try {
        _config = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'config.json'), 'utf8'));
    } catch (_) {}

    const server = http.createServer((req, res) => {
        const u = req.url;

        // Stats API
        if (u === '/api/stats') {
            res.writeHead(200, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
            return res.end(JSON.stringify(_stats.getSnapshot()));
        }

        // Config API (GET)
        if (u === '/api/config' && req.method === 'GET') {
            res.writeHead(200, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
            return res.end(JSON.stringify(_config || {}));
        }

        // Config API (POST — live update compression level)
        if (u === '/api/config' && req.method === 'POST') {
            const chunks = [];
            req.on('data', c => chunks.push(c));
            req.on('end', () => {
                try {
                    const update = JSON.parse(Buffer.concat(chunks).toString());
                    if (update.compression) Object.assign(_config.compression, update.compression);
                    fs.writeFileSync(
                        path.join(__dirname, '..', 'config.json'),
                        JSON.stringify(_config, null, 2)
                    );
                    res.writeHead(200, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ ok: true }));
                } catch (e) {
                    res.writeHead(400); res.end('Bad JSON');
                }
            });
            return;
        }

        // Serve dashboard HTML
        if (u === '/' || u === '/index.html') {
            const htmlPath = path.join(__dirname, '..', 'web', 'index.html');
            if (fs.existsSync(htmlPath)) {
                res.writeHead(200, { 'Content-Type': 'text/html' });
                return res.end(fs.readFileSync(htmlPath));
            }
        }

        res.writeHead(404); res.end('Not found');
    });

    server.listen(port, '127.0.0.1', () => {
        console.log(`[LumaxConProxy] Dashboard → http://127.0.0.1:${port}`);
    });
}

module.exports = { start };
