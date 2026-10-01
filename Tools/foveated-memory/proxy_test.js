/**
 * Proxy test — sends a realistic chat request to the foveated-memory proxy (port 8400)
 * and logs the full response to diagnose "Empty Choice" errors.
 */
'use strict';

const http = require('http');
const fs = require('fs');
const path = require('path');

const PROXY_URL = 'http://127.0.0.1:8400';
const LOG_FILE = path.join(__dirname, 'proxy_test.log');

function log(msg) {
    const line = `[${new Date().toISOString()}] ${msg}`;
    console.log(line);
    fs.appendFileSync(LOG_FILE, line + '\n');
}

function postJSON(urlPath, body) {
    return new Promise((resolve, reject) => {
        const data = JSON.stringify(body);
        const url = new URL(urlPath, PROXY_URL);
        const options = {
            hostname: url.hostname,
            port: url.port,
            path: url.pathname,
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Content-Length': Buffer.byteLength(data),
                'Authorization': 'Bearer proxy_test_agent'
            },
            timeout: 60000
        };

        const req = http.request(options, (res) => {
            let body = '';
            res.on('data', chunk => body += chunk);
            res.on('end', () => {
                resolve({ status: res.status, headers: res.headers, body });
            });
        });

        req.on('error', reject);
        req.on('timeout', () => { req.destroy(); reject(new Error('Request timed out')); });
        req.write(data);
        req.end();
    });
}

async function runTests() {
    log('=== PROXY TEST SUITE ===');
    log(`Target: ${PROXY_URL}`);

    // Test 1: Simple hello world
    log('\n--- Test 1: Simple hello world ---');
    try {
        const r1 = await postJSON('/v1/chat/completions', {
            model: 'auto',
            messages: [{ role: 'user', content: 'Say "hello world" and nothing else.' }],
            max_tokens: 50,
            stream: false
        });
        log(`Status: ${r1.status}`);
        log(`Body (first 1000 chars): ${r1.body.slice(0, 1000)}`);
        
        let parsed;
        try { parsed = JSON.parse(r1.body); } catch(e) { log(`JSON parse error: ${e.message}`); }
        if (parsed) {
            const choices = parsed?.choices || parsed?.error?.choices;
            if (!choices || choices.length === 0) {
                log('⚠️ EMPTY CHOICES detected!');
            } else {
                log(`✅ choices[0].message.content = "${choices[0]?.message?.content?.slice(0, 100)}"`);
            }
        }
    } catch (e) {
        log(`ERROR: ${e.message}`);
    }

    // Test 2: Larger request simulating file read
    log('\n--- Test 2: Larger request (simulating file read) ---');
    try {
        const largeContent = 'Please analyze this code:\n\n' + 
            'function test() {\n  ' + 'console.log("line");\n  '.repeat(200) + '}\n\n' +
            'What does this function do?';
        
        const r2 = await postJSON('/v1/chat/completions', {
            model: 'auto',
            messages: [{ role: 'user', content: largeContent }],
            max_tokens: 200,
            stream: false
        });
        log(`Status: ${r2.status}`);
        log(`Body length: ${r2.body.length} chars`);
        log(`Body (first 500 chars): ${r2.body.slice(0, 500)}`);
        
        let parsed;
        try { parsed = JSON.parse(r2.body); } catch(e) { log(`JSON parse error: ${e.message}`); }
        if (parsed) {
            const choices = parsed?.choices || parsed?.error?.choices;
            if (!choices || choices.length === 0) {
                log('⚠️ EMPTY CHOICES detected on large request!');
            } else {
                log(`✅ choices[0].message.content = "${choices[0]?.message?.content?.slice(0, 100)}"`);
            }
        }
    } catch (e) {
        log(`ERROR: ${e.message}`);
    }

    // Test 3: Streaming request
    log('\n--- Test 3: Streaming request ---');
    try {
        const r3 = await postJSON('/v1/chat/completions', {
            model: 'auto',
            messages: [{ role: 'user', content: 'Count from 1 to 5.' }],
            max_tokens: 100,
            stream: true
        });
        log(`Status: ${r3.status}`);
        log(`Body length: ${r3.body.length} chars`);
        log(`Body (first 500 chars): ${r3.body.slice(0, 500)}`);
        
        // Check if we got any data: lines with content
        const contentLines = r3.body.split('\n').filter(l => l.startsWith('data:') && l.includes('"content"'));
        log(`Content-bearing SSE lines: ${contentLines.length}`);
        if (contentLines.length === 0) {
            log('⚠️ No content in stream response!');
        }
    } catch (e) {
        log(`ERROR: ${e.message}`);
    }

    log('\n=== TEST SUITE COMPLETE ===');
}

runTests().catch(e => {
    console.error('Fatal:', e);
    process.exit(1);
});
