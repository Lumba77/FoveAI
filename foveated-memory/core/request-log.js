/**
 * request-log.js — Structured request telemetry for beta observability
 * =====================================================================
 * Append-only JSONL log, buffered and flushed on a timer so request latency
 * never waits on disk. One file per day under memory_data/logs/, with a
 * simple retention sweep.
 *
 * Privacy rule: NEVER log message bodies, auth headers, or API keys.
 * Set FOVEAI_LOG_BODIES=1 to also capture a truncated prompt/reply snippet
 * while actively debugging a reported problem.
 */

const fs = require('fs');
const path = require('path');

const LOG_DIR = process.env.FOVEAI_LOG_DIR
    || path.join(__dirname, '..', 'memory_data', 'logs');
const LOG_BODIES = process.env.FOVEAI_LOG_BODIES === '1';
const FLUSH_MS = 2000;
const RETENTION_DAYS = parseInt(process.env.FOVEAI_LOG_RETENTION_DAYS || '14', 10);
const BODY_SNIP = 400;

let _buf = [];
let _timer = null;
let _lastSweepDay = null;

function _ensureDir() {
    try { fs.mkdirSync(LOG_DIR, { recursive: true }); } catch (_) {}
}

function _fileFor(d = new Date()) {
    return path.join(LOG_DIR, `requests-${d.toISOString().slice(0, 10)}.jsonl`);
}

function _sweepRetention() {
    const today = new Date().toISOString().slice(0, 10);
    if (_lastSweepDay === today) return;
    _lastSweepDay = today;
    try {
        const cutoff = Date.now() - RETENTION_DAYS * 86400000;
        for (const f of fs.readdirSync(LOG_DIR)) {
            if (!f.startsWith('requests-') || !f.endsWith('.jsonl')) continue;
            const day = Date.parse(f.slice(9, 19));
            if (!isNaN(day) && day < cutoff) {
                try { fs.unlinkSync(path.join(LOG_DIR, f)); } catch (_) {}
            }
        }
    } catch (_) {}
}

function _flush() {
    if (!_buf.length) return;
    const lines = _buf.map(e => JSON.stringify(e)).join('\n') + '\n';
    _buf = [];
    _ensureDir();
    fs.appendFile(_fileFor(), lines, () => {});
    _sweepRetention();
}

/**
 * Record one request/response cycle. `entry` fields (all optional):
 *   route, model, stream, status, latency_ms, user, workspace,
 *   prompt_chars, reply_chars, reasoning_chars, thoughts, error
 */
function logRequest(entry) {
    _buf.push({ ts: new Date().toISOString(), ...entry });
    if (!_timer) {
        _timer = setTimeout(() => { _timer = null; _flush(); }, FLUSH_MS);
        if (_timer.unref) _timer.unref();
    }
}

/** Truncated snippet — only when FOVEAI_LOG_BODIES=1. */
function bodySnippet(text) {
    if (!LOG_BODIES || typeof text !== 'string' || !text) return undefined;
    return text.length > BODY_SNIP ? text.slice(0, BODY_SNIP) + '…' : text;
}

/**
 * Read recent entries across all log days, newest last.
 * `tail` = max entries returned.
 */
function readRecent(tail = 200) {
    _ensureDir();
    const out = [];
    try {
        const files = fs.readdirSync(LOG_DIR)
            .filter(f => f.startsWith('requests-') && f.endsWith('.jsonl'))
            .sort();
        for (const f of files) {
            for (const line of fs.readFileSync(path.join(LOG_DIR, f), 'utf8').split('\n')) {
                if (!line.trim()) continue;
                try { out.push(JSON.parse(line)); } catch (_) {}
            }
        }
    } catch (_) {}
    return out.slice(-tail);
}

/** Aggregate stats for the admin console. */
function summarize(hours = 24) {
    const since = Date.now() - hours * 3600000;
    const entries = readRecent(20000).filter(e => Date.parse(e.ts) >= since);
    const byUser = {}, byRoute = {}, byModel = {}, byEndpoint = {};
    let errors = 0, latencies = [];
    for (const e of entries) {
        if (e.user) byUser[e.user] = (byUser[e.user] || 0) + 1;
        if (e.route) byRoute[e.route] = (byRoute[e.route] || 0) + 1;
        if (e.model) byModel[e.model] = (byModel[e.model] || 0) + 1;
        if (e.endpoint) byEndpoint[e.endpoint] = (byEndpoint[e.endpoint] || 0) + 1;
        if (e.error || (e.status && e.status >= 500)) errors++;
        if (typeof e.latency_ms === 'number') latencies.push(e.latency_ms);
    }
    latencies.sort((a, b) => a - b);
    const p = q => latencies.length ? latencies[Math.min(latencies.length - 1, Math.floor(latencies.length * q))] : null;
    return {
        window_hours: hours,
        requests: entries.length,
        errors,
        latency_ms: { p50: p(0.5), p95: p(0.95), max: latencies[latencies.length - 1] ?? null },
        by_user: byUser,
        by_route: byRoute,
        by_model: byModel,
        by_endpoint: byEndpoint,
    };
}

module.exports = { logRequest, bodySnippet, readRecent, summarize, LOG_DIR };
