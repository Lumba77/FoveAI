/**
 * Direct Ollama Cloud test — bypasses the foveated-memory proxy entirely.
 * Sends a simple chat request directly to Ollama Cloud and logs the full response.
 */
'use strict';

const fetch = require('node-fetch');
const fs = require('fs');
const path = require('path');

// Load .env manually (same as proxy)
(function loadEnv() {
    const envPath = path.resolve(__dirname, '..', '..', '.env');
    try {
        const raw = fs.readFileSync(envPath, 'utf8');
        for (const line of raw.split('\n')) {
            const trimmed = line.trim();
            if (!trimmed || trimmed.startsWith('#')) continue;
            const eqIdx = trimmed.indexOf('=');
            if (eqIdx === -1) continue;
            const key = trimmed.slice(0, eqIdx).trim();
            const val = trimmed.slice(eqIdx + 1).trim().replace(/^["']|["']$/g, '');
            if (!(key in process.env)) process.env[key] = val;
        }
    } catch (e) {}
})();

const API_KEY = process.env.LUMAX_PROXY_API_KEY || '';
const BASE_URL = 'https://ollama.com/v1';
const MODEL = process.env.LUMAX_MODEL_CLOUD_ID || 'gemma4:31b';

const LOG_FILE = path.join(__dirname, 'direct_test.log');

function log(msg) {
    const line = `[${new Date().toISOString()}] ${msg}`;
    console.log(line);
    fs.appendFileSync(LOG_FILE, line + '\n');
}

async function testDirect() {
    log('=== DIRECT OLLAMA CLOUD TEST ===');
    log(`Model: ${MODEL}`);
    log(`Base URL: ${BASE_URL}`);
    log(`API Key present: ${API_KEY ? 'YES (' + API_KEY.slice(0, 8) + '...)' : 'NO'}`);

    const body = {
        model: MODEL,
        messages: [
            { role: 'user', content: 'Say "hello world" and nothing else.' }
        ],
        max_tokens: 50,
        temperature: 0,
        stream: false
    };

    log(`Request body: ${JSON.stringify(body)}`);

    try {
        const res = await fetch(`${BASE_URL}/chat/completions`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${API_KEY}`
            },
            body: JSON.stringify(body),
            signal: (() => { const c = new AbortController(); setTimeout(() => c.abort(), 30000); return c.signal; })()
        });

        log(`HTTP Status: ${res.status} ${res.statusText}`);
        log(`Headers: ${JSON.stringify(Object.fromEntries(res.headers.entries()))}`);

        const rawText = await res.text();
        log(`Raw response (first 2000 chars): ${rawText.slice(0, 2000)}`);

        if (!res.ok) {
            log(`ERROR: Upstream returned non-OK status: ${res.status}`);
            log(`Full error body: ${rawText}`);
            return;
        }

        let parsed;
        try {
            parsed = JSON.parse(rawText);
        } catch (e) {
            log(`ERROR: Failed to parse JSON: ${e.message}`);
            log(`Raw text was: ${rawText}`);
            return;
        }

        const choices = parsed?.choices;
        if (!choices || choices.length === 0) {
            log('ERROR: Response contained NO choices!');
            log(`Full parsed response: ${JSON.stringify(parsed, null, 2)}`);
        } else {
            const content = choices[0]?.message?.content || '(empty content)';
            log(`SUCCESS: choices[0].message.content = "${content}"`);
            log(`Full parsed response: ${JSON.stringify(parsed, null, 2)}`);
        }
    } catch (err) {
        log(`FATAL: ${err.message}`);
        log(`Stack: ${err.stack}`);
    }

    log('=== TEST COMPLETE ===');
}

testDirect().catch(e => {
    console.error('Unhandled:', e);
    process.exit(1);
});
