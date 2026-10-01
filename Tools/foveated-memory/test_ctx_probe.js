// E2E context persistence probe for FoveatedMemory proxy
// Tests: (1) chat completion via proxy, (2) memory stored, (3) context survives
const http = require('http');

const PROXY = 'http://127.0.0.1:8400';

function post(path, body, headers = {}) {
    return new Promise((resolve, reject) => {
        const data = JSON.stringify(body);
        const u = new URL(PROXY + path);
        const req = http.request({
            hostname: u.hostname,
            port: u.port,
            path: u.pathname,
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(data), ...headers }
        }, res => {
            let raw = '';
            res.on('data', c => raw += c);
            res.on('end', () => {
                try { resolve({ status: res.statusCode, body: JSON.parse(raw) }); }
                catch { resolve({ status: res.statusCode, body: raw }); }
            });
        });
        req.on('error', reject);
        req.write(data);
        req.end();
    });
}

function get(path) {
    return new Promise((resolve, reject) => {
        const u = new URL(PROXY + path);
        http.get(u, res => {
            let raw = '';
            res.on('data', c => raw += c);
            res.on('end', () => {
                try { resolve({ status: res.statusCode, body: JSON.parse(raw) }); }
                catch { resolve({ status: res.statusCode, body: raw }); }
            });
        }).on('error', reject);
    });
}

(async () => {
    const token = process.argv[2] || 'testword';
    const headers = { Authorization: `Bearer ${token}` };

    console.log('=== 1. Health under token:', token, '===');
    const h = await get('/health');
    console.log(' health:', JSON.stringify(h.body));

    console.log('\n=== 2. Send chat message (store secret) ===');
    const c1 = await post('/v1/chat/completions', {
        model: 'kimi-k3',
        messages: [{ role: 'user', content: 'Remember this secret code: ORANGE-PANDA-42' }]
    }, headers);
    console.log(' status:', c1.status);
    console.log(' resp:', JSON.stringify(c1.body).slice(0, 500));

    console.log('\n=== 3. Send follow-up (should recall code) ===');
    const c2 = await post('/v1/chat/completions', {
        model: 'kimi-k3',
        messages: [{ role: 'user', content: 'What is the secret code I told you?' }]
    }, headers);
    console.log(' status:', c2.status);
    console.log(' resp:', JSON.stringify(c2.body).slice(0, 500));

    console.log('\n=== 4. Check memory store for workspace ===');
    try {
        const m = await get(`/memory?limit=5`);
        console.log(' memory:', JSON.stringify(m.body).slice(0, 800));
    } catch (e) { console.log(' memory endpoint failed:', e.message); }
})().catch(e => { console.error('FATAL:', e); process.exit(1); });
