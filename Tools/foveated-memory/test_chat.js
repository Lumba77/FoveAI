// Quick test: chat completion through the proxy
const http = require('http');

const data = JSON.stringify({
    model: 'kimi-k2.7-code',
    messages: [{ role: 'user', content: 'say hello in one word' }],
    stream: false
});

const req = http.request({
    hostname: '127.0.0.1',
    port: 8200,
    path: '/v1/chat/completions',
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(data)
    },
    timeout: 30000
}, (res) => {
    let body = '';
    res.on('data', chunk => body += chunk);
    res.on('end', () => {
        console.log('STATUS:', res.statusCode);
        console.log('BODY:', body.substring(0, 500));
    });
});

req.on('timeout', () => {
    console.log('TIMEOUT after 30s');
    req.destroy();
});

req.on('error', (e) => {
    console.log('ERROR:', e.message);
});

req.write(data);
req.end();