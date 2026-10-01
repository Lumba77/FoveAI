/**
 * Stress test — tests the proxy with spoofed 128K context window
 * and a real 16K budget. Verifies:
 *   1. Model passthrough (deepseek-v4-pro not overridden to gemma4:31b)
 *   2. Large context handling (many turns)
 *   3. Streaming and non-streaming responses
 *   4. No "empty choices" errors
 */
'use strict';

const http = require('http');
const fs = require('fs');
const path = require('path');

const PROXY_URL = 'http://127.0.0.1:8400';
const LOG_FILE = path.join(__dirname, 'stress_test.log');

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
                'Authorization': 'Bearer stress_test_agent'
            },
            timeout: 120000
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

function getJSON(urlPath) {
    return new Promise((resolve, reject) => {
        const url = new URL(urlPath, PROXY_URL);
        const options = {
            hostname: url.hostname,
            port: url.port,
            path: url.pathname + url.search,
            method: 'GET',
            headers: { 'Authorization': 'Bearer stress_test_agent' },
            timeout: 10000
        };
        const req = http.request(options, (res) => {
            let body = '';
            res.on('data', chunk => body += chunk);
            res.on('end', () => resolve({ status: res.status, headers: res.headers, body }));
        });
        req.on('error', reject);
        req.on('timeout', () => { req.destroy(); reject(new Error('Request timed out')); });
        req.end();
    });
}

async function runStressTest() {
    log('═══════════════════════════════════════════════');
    log('  FOVEATED MEMORY PROXY — STRESS TEST SUITE');
    log('  Spoof: 128K | Real budget: 16K');
    log('═══════════════════════════════════════════════');
    log(`Target: ${PROXY_URL}`);

    // ── Test 0: Health check ──────────────────────────────────────────
    log('\n── Test 0: Health Check ──');
    try {
        const h = await getJSON('/health');
        log(`Status: ${h.status}`);
        const health = JSON.parse(h.body);
        log(`Service: ${health.service}`);
        log(`Mode: ${health.mode}`);
        log(`Cloud cap: ${health.cloud_cap}`);
        log(`✅ Health check passed`);
    } catch (e) {
        log(`❌ Health check failed: ${e.message}`);
    }

    // ── Test 1: Model passthrough — deepseek-v4-pro should NOT be overridden ──
    log('\n── Test 1: Model Passthrough (deepseek-v4-pro) ──');
    try {
        const r1 = await postJSON('/v1/chat/completions', {
            model: 'deepseek-v4-pro',
            messages: [{ role: 'user', content: 'Say "model test ok" and nothing else.' }],
            max_tokens: 20,
            stream: false
        });
        log(`Status: ${r1.status}`);
        const parsed = JSON.parse(r1.body);
        const modelUsed = parsed.model;
        const content = parsed?.choices?.[0]?.message?.content || '';
        log(`Model in response: "${modelUsed}"`);
        log(`Content: "${content.slice(0, 100)}"`);
        if (modelUsed === 'gemma4:31b') {
            log('❌ MODEL OVERRIDE DETECTED! deepseek-v4-pro was switched to gemma4:31b');
        } else if (modelUsed === 'deepseek-v4-pro') {
            log('✅ Model passthrough working — deepseek-v4-pro preserved');
        } else {
            log(`⚠️ Unexpected model: ${modelUsed}`);
        }
    } catch (e) {
        log(`❌ Error: ${e.message}`);
    }

    // ── Test 2: Model passthrough — kimi-k2.6 (coding model) ──
    log('\n── Test 2: Model Passthrough (kimi-k2.6) ──');
    try {
        const r2 = await postJSON('/v1/chat/completions', {
            model: 'kimi-k2.6',
            messages: [{ role: 'user', content: 'Say "kimi test ok" and nothing else.' }],
            max_tokens: 20,
            stream: false
        });
        const parsed = JSON.parse(r2.body);
        const modelUsed = parsed.model;
        log(`Model in response: "${modelUsed}"`);
        if (modelUsed === 'kimi-k2.6') {
            log('✅ Coding model passthrough working');
        } else if (modelUsed === 'gemma4:31b') {
            log('❌ Coding model was overridden to gemma4:31b');
        } else {
            log(`⚠️ Unexpected model: ${modelUsed}`);
        }
    } catch (e) {
        log(`❌ Error: ${e.message}`);
    }

    // ── Test 3: Large context — many turns simulating long conversation ──
    log('\n── Test 3: Large Context (20-turn simulated conversation) ──');
    try {
        const turns = [];
        for (let i = 1; i <= 10; i++) {
            turns.push({ role: 'user', content: `This is turn ${i}. I'm working on a project that involves building a complex web application with React, Node.js, and PostgreSQL. The application needs to handle user authentication, real-time updates via WebSockets, and file uploads. I need to make sure the architecture is scalable and the code is well-organized.` });
            turns.push({ role: 'assistant', content: `Turn ${i} response: I understand. For a scalable React+Node.js+PostgreSQL app with real-time features, I recommend using Next.js for the frontend with server-side rendering, Socket.io for WebSockets, and Prisma as the ORM. For file uploads, consider using AWS S3 with presigned URLs. The authentication can be handled with NextAuth.js or a custom JWT implementation. Let me know which specific area you'd like to dive deeper into.` });
        }
        // Add the actual question at the end
        turns.push({ role: 'user', content: 'Based on our entire conversation, what architecture did I recommend? Answer in one sentence.' });

        const r3 = await postJSON('/v1/chat/completions', {
            model: 'deepseek-v4-pro',
            messages: turns,
            max_tokens: 100,
            stream: false
        });
        log(`Status: ${r3.status}`);
        const parsed = JSON.parse(r3.body);
        const content = parsed?.choices?.[0]?.message?.content || '';
        const error = parsed?.error;
        log(`Content: "${content.slice(0, 200)}"`);
        if (error) {
            log(`❌ Error in response: ${JSON.stringify(error)}`);
        } else if (!content) {
            log('❌ EMPTY CONTENT — "no choices" error would occur here!');
        } else if (content.includes('unable to generate')) {
            log('⚠️ Fallback message returned (model may have been overloaded)');
        } else {
            log('✅ Large context handled successfully');
        }
    } catch (e) {
        log(`❌ Error: ${e.message}`);
    }

    // ── Test 4: Streaming with large context ──
    log('\n── Test 4: Streaming Large Context ──');
    try {
        const turns = [];
        for (let i = 1; i <= 8; i++) {
            turns.push({ role: 'user', content: `Turn ${i}: I need help with a Python script that processes CSV files. The script should read a CSV, filter rows based on a date column, aggregate data by category, and output a summary report.` });
            turns.push({ role: 'assistant', content: `Turn ${i}: Here's how to approach that. Use pandas for CSV reading, datetime for date filtering, groupby for aggregation. The key is to handle edge cases like missing values and malformed dates.` });
        }
        turns.push({ role: 'user', content: 'Summarize what I asked about in one sentence.' });

        const r4 = await postJSON('/v1/chat/completions', {
            model: 'deepseek-v4-pro',
            messages: turns,
            max_tokens: 100,
            stream: true
        });
        log(`Status: ${r4.status}`);
        // Count SSE content-bearing lines
        const lines = r4.body.split('\n').filter(l => l.startsWith('data:') && !l.includes('[DONE]'));
        let contentChars = 0;
        for (const line of lines) {
            try {
                const parsed = JSON.parse(line.slice(5).trim());
                contentChars += (parsed?.choices?.[0]?.delta?.content || '').length;
            } catch (_) {}
        }
        log(`SSE lines: ${lines.length}, content chars: ${contentChars}`);
        if (contentChars > 0) {
            log('✅ Streaming large context handled successfully');
        } else {
            log('❌ Streaming returned no content!');
        }
    } catch (e) {
        log(`❌ Error: ${e.message}`);
    }

    // ── Test 5: Context window spoofing verification ──
    log('\n── Test 5: Context Window Spoofing ──');
    try {
        const r5 = await getJSON('/v1/models/deepseek-v4-pro');
        const parsed = JSON.parse(r5.body);
        log(`Model: ${parsed.id}`);
        log(`context_window: ${parsed.context_window}`);
        log(`max_context_length: ${parsed.max_context_length}`);
        if (parsed.context_window === 128000) {
            log('✅ Spoofing active — reporting 128K to clients');
        } else if (parsed.context_window) {
            log(`⚠️ Spoofing reports ${parsed.context_window} (expected 128000)`);
        } else {
            log('⚠️ No context_window in model response');
        }
    } catch (e) {
        log(`❌ Error: ${e.message}`);
    }

    // ── Test 6: Tier info endpoint ──
    log('\n── Test 6: Tier Info ──');
    try {
        const r6 = await getJSON('/api/tier-info?model=deepseek-v4-pro&mode=cloud');
        const parsed = JSON.parse(r6.body);
        log(`Model: ${parsed.model}`);
        log(`Context window: ${parsed.context_window}`);
        log(`Recommended tier: ${parsed.recommended_tier}`);
        log('✅ Tier info working');
    } catch (e) {
        log(`❌ Error: ${e.message}`);
    }

    log('\n═══════════════════════════════════════════════');
    log('  STRESS TEST SUITE COMPLETE');
    log('═══════════════════════════════════════════════');
}

runStressTest().catch(e => {
    log(`FATAL: ${e.message}`);
    console.error(e);
});
