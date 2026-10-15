'use strict';
/**
 * core/residency.js — bridge between the proxy (Node) and Jen's Residency
 * controller (Python, runtime/residency.py). Phase 2 of Docs/JEN_MIND.md.
 *
 * The proxy used to assume a local model was always listening on a fixed port
 * (:8402). With residency, the brain is loaded on demand and freed when idle —
 * so "is there a model?" is now a question only jen_mind.json can answer, and
 * "nothing is resident" is a normal state, not a failure.
 *
 * Responsibilities:
 *   resident()            — which tier (if any) is currently loaded, and where
 *   managedTier(url)      — does this upstream URL name a residency-managed port?
 *   touchTurn()           — mark a live turn so idle-unload never cuts it
 *   requestWake(tier)     — drop a wake-request file (debounced); the residency
 *                           daemon (running as lumba) owns ALL load/unload. The
 *                           proxy NEVER spawns the loader — it runs as root, and
 *                           a root-launched brain can't be managed by the daemon.
 *   wakeNotice(tier)      — a human line to show while she wakes
 */
const fs = require('fs');
const path = require('path');

const REPO = path.resolve(__dirname, '..', '..');
const MIND = path.join(REPO, 'Backend', 'Cognition', 'jen_mind.json');
const TURN_LOCK = path.join(REPO, 'runtime', '.jen_turn.lock');
const WAKE_REQ = path.join(REPO, 'runtime', '.jen_wake.json');

// The ports residency owns: 8407 = tier A (background), 8408 = tier B (present).
// :8402 is the XRLF contract front that forwards to tier B — map it to B so a
// request to the soul runtime wakes the brain behind it instead of 502-ing cold.
const MANAGED = { 8407: 'A', 8408: 'B', 8402: 'B' };

const WAKE_DEBOUNCE_MS = 60000;
const _wakeRequestedAt = {};

function readMind() {
    try {
        return JSON.parse(fs.readFileSync(MIND, 'utf8'));
    } catch {
        return null;
    }
}

/** The currently resident tier, or null when Jen is not loaded. */
function resident() {
    const m = readMind();
    const r = (m && m.residency) || {};
    if (!r.tier || !r.port) return null;
    return { tier: r.tier, port: r.port, pid: r.pid || null, state: r.state || 'present' };
}

/** If `targetUrl` points at a residency-managed port, return its tier ('A'/'B'). */
function managedTier(targetUrl) {
    try {
        const u = new URL(targetUrl);
        const p = parseInt(u.port || (u.protocol === 'https:' ? '443' : '80'), 10);
        return MANAGED[p] || null;
    } catch {
        return null;
    }
}

/** Mark the current turn live so the residency daemon will not unload mid-answer. */
function touchTurn() {
    try {
        const now = new Date();
        try {
            fs.utimesSync(TURN_LOCK, now, now);
        } catch {
            fs.writeFileSync(TURN_LOCK, String(Date.now()));
        }
    } catch { /* best effort — never break a request over a lock file */ }
}

/** Ask residency to load `tier`. Writes a request file the daemon consumes.
 *  Debounced so bursts of "waking" replies don't rewrite it every turn. */
function requestWake(tier) {
    tier = tier || 'B';
    const now = Date.now();
    if (_wakeRequestedAt[tier] && now - _wakeRequestedAt[tier] < WAKE_DEBOUNCE_MS) {
        return false;
    }
    _wakeRequestedAt[tier] = now;
    try {
        const tmp = WAKE_REQ + '.tmp';
        fs.writeFileSync(tmp, JSON.stringify({ tier, ts: now / 1000 }));
        fs.renameSync(tmp, WAKE_REQ);
        console.log(`[Residency] 🌙 requested wake of tier ${tier} (daemon will load)`);
        return true;
    } catch (e) {
        console.warn('[Residency] wake request failed:', e.message);
        return false;
    }
}

function wakeNotice(tier) {
    return `🌙 Jen is waking (tier ${tier}). Her mind was not resident — the first breath takes a few seconds. Send your message again.`;
}

module.exports = { resident, managedTier, touchTurn, requestWake, wakeNotice, MANAGED, MIND, TURN_LOCK, WAKE_REQ };
