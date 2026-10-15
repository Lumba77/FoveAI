'use strict';

/**
 * ═══════════════════════════════════════════════════════════════════════
 * EMBEDDER — local semantic vector backend (all-MiniLM-L6-v2)
 * ═══════════════════════════════════════════════════════════════════════
 *
 * Bridges the JS memory store to the Python ONNX embedder
 * (`xrlf_embedder.py`) over a loopback TCP socket speaking newline-delimited
 * JSON:  {"input": ["a","b"]}  →  {"embedding": [[...384], [...]], "dim": 384}
 *
 * WHY A SUBPROCESS
 * memory/store.js is deliberately "pure JS, zero native deps". Putting ONNX
 * behind a socket keeps the native runtime out of the Node process and keeps
 * that guarantee intact. The trade is one local process.
 *
 * WHY LAZY-START RATHER THAN A SYSTEMD UNIT
 * The model loads in ~0.5s, so paying that on first recall is cheaper than a
 * sixth always-on unit on a box where foveai-tts already refused SIGTERM for
 * 2m45s and had to be SIGKILLed. Recall never blocks on this — if the sidecar
 * is slow or absent, encode() returns null and the caller falls back to
 * TF-IDF immediately rather than adding latency to the hot path.
 *
 * FAILURE IS LOUD, NOT SILENT
 * This is the TTS incident from the 2026-10-10 handoff: a dead backend that
 * degrades quietly presents as a broken feature. Every fallback here logs.
 */

const net = require('net');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const ROOT     = path.resolve(__dirname, '..', '..');
const SCRIPT   = path.join(ROOT, 'xrlf_embedder.py');
const PYTHON   = path.join(ROOT, '.venv', 'bin', 'python');
const HOST     = '127.0.0.1';
const PORT     = parseInt(process.env.XRLF_EMBEDDER_PORT || '8489', 10);
const DIM      = 384;

// AGENTS.md: never run heavy CPU work alongside the 9B. MiniLM is cheap but
// unbounded ORT threads will still steal cycles from llama.cpp prompt eval.
const THREADS  = parseInt(process.env.XRLF_EMBEDDER_THREADS || '2', 10);

const BOOT_TIMEOUT = 30000;   // model load + socket bind
const CALL_TIMEOUT = 15000;   // one encode() round trip (measured: ~4ms)
const IDLE_TIMEOUT = 15 * 60 * 1000;

let child     = null;
let socket    = null;
let booting   = null;        // in-flight start promise — the single-flight guard
let connected = false;
let disabled  = false;       // set by disable(); never retried
let lastUsed  = 0;
let backlog   = '';          // partial NDJSON line buffer
let waiting   = [];          // pending {resolve, reject, timer}
let idleTimer = null;
let closing   = false;       // deliberate shutdown vs. genuine fault

const log = (...a) => console.log('[MEMORY][embedder]', ...a);
const warn = (...a) => console.warn('[MEMORY][embedder]', ...a);

function available() {
    return !disabled && fs.existsSync(SCRIPT) && fs.existsSync(PYTHON);
}

function stopIdleTimer() {
    if (idleTimer) { clearTimeout(idleTimer); idleTimer = null; }
}

function armIdleTimer() {
    stopIdleTimer();
    idleTimer = setTimeout(() => { log('idle — stopping sidecar'); shutdown(); }, IDLE_TIMEOUT);
    if (idleTimer.unref) idleTimer.unref();
}

/** Kill the sidecar and drop the socket. Safe to call repeatedly. */
function shutdown() {
    stopIdleTimer();
    closing = true;              // deliberate stop: not a fault, don't warn
    if (socket) { try { socket.destroy(); } catch (_) {} socket = null; }
    if (child) {
        const p = child;
        child = null;
        try { p.kill('SIGTERM'); } catch (_) {}
        // Don't let a wedged ONNX runtime hold shutdown open — the exact
        // failure foveai-tts exhibited. Escalate on a short timer.
        const t = setTimeout(() => { try { p.kill('SIGKILL'); } catch (_) {} }, 3000);
        if (t.unref) t.unref();
    }
    connected = false;
    booting = null;
    backlog = '';
    for (const w of waiting.splice(0)) { clearTimeout(w.timer); w.reject(new Error('sidecar stopped')); }
}

function failAll(err) {
    const pending = waiting.splice(0);
    for (const w of pending) { clearTimeout(w.timer); w.reject(err); }
}

function connect() {
    return new Promise((resolve, reject) => {
        const s = net.createConnection({ host: HOST, port: PORT });
        s.setNoDelay(true);
        let settled = false;
        let live = false;

        s.on('connect', () => {
            settled = true;
            live = true;
            socket = s;
            backlog = '';
            connected = true;
            armIdleTimer();
            resolve(s);
        });

        s.on('data', chunk => {
            backlog += chunk.toString('utf8');
            let nl;
            while ((nl = backlog.indexOf('\n')) >= 0) {
                const line = backlog.slice(0, nl).trim();
                backlog = backlog.slice(nl + 1);
                if (!line) continue;
                const w = waiting.shift();
                if (!w) continue;
                clearTimeout(w.timer);
                try { w.resolve(JSON.parse(line)); }
                catch (e) { w.reject(new Error('sidecar sent invalid JSON: ' + e.message)); }
            }
        });

        const die = (why) => {
            // A boot probe that never connected is expected (the sidecar may not
            // be listening yet) and error+close both fire. Only a socket that was
            // actually live is worth reporting as a loss.
            if (!live) {
                if (!settled) { settled = true; reject(new Error('connect failed: ' + why)); }
                return;
            }
            live = false;
            connected = false;
            if (socket === s) socket = null;
            if (closing) { closing = false; return; }   // we asked for this
            warn('socket lost (' + why + ') — next recall will fall back to TF-IDF');
            failAll(new Error('sidecar socket lost'));
        };

        s.on('error', (e) => die(e.code || e.message));
        s.on('close', () => die('closed'));
    });
}

function spawnSidecar() {
    return new Promise((resolve, reject) => {
        log(`starting sidecar on ${HOST}:${PORT} (threads=${THREADS})`);
        const c = spawn(PYTHON, [SCRIPT, '--serve', String(PORT), '--threads', String(THREADS)], {
            cwd: ROOT,
            stdio: 'ignore',          // no pipes: a full pipe buffer can deadlock the child
            env: { ...process.env, OMP_NUM_THREADS: String(THREADS) },
        });
        child = c;
        c.on('error', (e) => { child = null; reject(new Error('spawn failed: ' + e.message)); });
        c.on('exit', (code, sig) => {
            if (child === c) child = null;
            if (code !== 0 && code !== null) warn(`sidecar exited code=${code} sig=${sig}`);
            connected = false;
            failAll(new Error('sidecar exited'));
        });

        // Poll for the listener rather than parsing stdout (stdio is ignored).
        const deadline = Date.now() + BOOT_TIMEOUT;
        const poll = async () => {
            while (Date.now() < deadline) {
                if (child !== c) return reject(new Error('sidecar exited during boot'));
                try { await connect(); return resolve(); }
                catch (_) { await new Promise(r => setTimeout(r, 150)); }
            }
            try { c.kill('SIGKILL'); } catch (_) {}
            reject(new Error(`sidecar did not listen within ${BOOT_TIMEOUT}ms`));
        };
        poll();
    });
}

/** Single-flight: concurrent first-callers await one boot, not N spawns. */
function ensure() {
    if (disabled) return Promise.reject(new Error('disabled'));
    if (connected) { armIdleTimer(); return Promise.resolve(); }
    if (!available()) return Promise.reject(new Error('xrlf_embedder.py or venv python missing'));
    if (booting) return booting;
    booting = (async () => {
        for (let attempt = 1; attempt <= 2; attempt++) {
            try { await spawnSidecar(); booting = null; return; }
            catch (e) {
                if (attempt === 2) { booting = null; shutdown(); throw e; }
                warn(`boot attempt ${attempt} failed (${e.message}) — retrying`);
            }
        }
    })();
    return booting;
}

/**
 * Embed texts. Returns an array of Float32Array(DIM), or null if the backend
 * is unavailable — callers must then fall back to TF-IDF and say so loudly.
 */
async function encode(texts) {
    if (!Array.isArray(texts) || texts.length === 0) return null;
    const payload = texts.map(t => (typeof t === 'string' ? t : ''));
    if (payload.every(t => t.length === 0)) return null;

    try {
        await ensure();
    } catch (e) {
        warn('unavailable (' + e.message + ') — caller falls back to TF-IDF');
        return null;
    }

    lastUsed = Date.now();
    try {
        const res = await call({ input: payload });
        if (res.error) throw new Error(res.error);
        const rows = res.embedding;
        if (!Array.isArray(rows) || rows.length !== payload.length) {
            throw new Error(`expected ${payload.length} vectors, got ${rows ? rows.length : 'none'}`);
        }
        return rows.map(r => Float32Array.from(r));
    } catch (e) {
        warn('encode failed (' + e.message + ') — caller falls back to TF-IDF');
        return null;
    }
}

function call(payload) {
    return new Promise((resolve, reject) => {
        const timer = setTimeout(() => {
            const i = waiting.findIndex(w => w.timer === timer);
            if (i >= 0) waiting.splice(i, 1);
            reject(new Error('encode timed out'));
        }, CALL_TIMEOUT);
        if (timer.unref) timer.unref();
        waiting.push({ resolve, reject, timer });
        try {
            socket.write(JSON.stringify(payload) + '\n', 'utf8');
        } catch (e) {
            clearTimeout(timer);
            waiting.pop();
            reject(e);
        }
    });
}

/** Report for /api/xrl/status — never lies about which backend is live. */
function status() {
    if (disabled)              return { backend: 'disabled', state: 'off', dim: DIM };
    if (!available())          return { backend: 'unavailable', state: 'missing-script', dim: DIM };
    if (!connected)            return { backend: 'tfidf', state: 'not-running', dim: DIM };
    return { backend: 'minilm-l6-v2', state: 'ready', dim: DIM, pid: child ? child.pid : null };
}

/** Opt out entirely (env flag); used when the operator wants TF-IDF only. */
function disable(reason) {
    if (reason) log('disabled: ' + reason);
    disabled = true;
    shutdown();
}

// Never orphan the child: an ONNX process outliving its parent is exactly the
// kind of thing that wedges a stop.
process.on('exit', shutdown);
process.on('SIGINT', () => { shutdown(); process.exit(0); });
process.on('SIGTERM', () => { shutdown(); process.exit(0); });

module.exports = { encode, status, shutdown, disable, available, DIM };