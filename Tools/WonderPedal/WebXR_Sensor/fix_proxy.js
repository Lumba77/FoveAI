const http = require('http');
const httpProxy = require('http-proxy');

// Create a proxy server with custom application logic
const proxy = httpProxy.createProxyServer({
    target: 'https://127.0.0.1:8081',
    secure: false, // Ignore self-signed certs
    ws: true       // Proxy websockets
});

proxy.on('error', function (err, req, res) {
    console.error("Proxy error:", err);
    if (res && res.writeHead) {
        res.writeHead(502, { 'Content-Type': 'text/plain' });
        res.end('Bad Gateway from fix_proxy.js');
    }
});

const server = http.createServer(function(req, res) {
    proxy.web(req, res);
});

// Listen to the `upgrade` event and proxy the WebSocket requests
server.on('upgrade', function (req, socket, head) {
    proxy.ws(req, socket, head);
});

console.log("🚀 LUMAX Proxy Translation Layer Active.");
console.log("Listening on HTTP 5176 (for Cloudflare)...");
console.log("Proxying to HTTPS 8081 (Vite WebXR)...");
server.listen(5176);
