/**
 * ═══════════════════════════════════════════════════════
 * CONTEXT HEALER — Self-Healing Context Budget Manager
 * ═══════════════════════════════════════════════════════
 *
 * Detects upstream failures caused by context overflow and
 * auto-adjusts the context budget to keep the proxy alive.
 *
 * Lifecycle:
 *   1. DETECT — upstream returns empty, errors, or times out
 *   2. DIAGNOSE — was it a context overflow? (pattern matching)
 *   3. SELF-ADJUST — temporarily lower the context budget
 *   4. RETRY — re-send with reduced context
 *   5. WARN — inject a structured warning into the response
 *   6. AUTO-RESTORE — gradually raise budget back on success
 *
 * Budget is a floating value between MIN_BUDGET and MAX_BUDGET.
 * On failure: budget *= BACKOFF_FACTOR (aggressive shrink)
 * On success: budget += RECOVERY_STEP (gradual restore)
 */

'use strict';

const fs = require('fs');
const path = require('path');

// ── Config ──────────────────────────────────────────────────────────────────
const LOW_CTX            = process.env.LUMAX_LOW_CONTEXT_MODE === 'true' || process.env.LUMAX_LOW_CONTEXT_MODE === '1';
const MAX_BUDGET_CHARS   = parseInt(process.env.LUMAX_CTX_MAX_CHARS   || (LOW_CTX ? '12000' : '50000'), 10);
const MIN_BUDGET_CHARS   = parseInt(process.env.LUMAX_CTX_MIN_CHARS   || (LOW_CTX ? '2000'  : '4000'),  10);
const BACKOFF_FACTOR     = parseFloat(process.env.LUMAX_CTX_BACKOFF   || '0.5');    // halve on failure
const RECOVERY_STEP      = parseInt(process.env.LUMAX_CTX_RECOVERY     || (LOW_CTX ? '1000'  : '2000'), 10); // recovery step
const MAX_RETRIES        = parseInt(process.env.LUMAX_CTX_MAX_RETRIES || '3',     10);
const COOLDOWN_MS        = parseInt(process.env.LUMAX_CTX_COOLDOWN     || '30000', 10); // 30s before recovery

// ── State ───────────────────────────────────────────────────────────────────
let currentBudget  = MAX_BUDGET_CHARS;
let lastFailureAt  = 0;
let consecutiveOk  = 0;
let totalShrinks   = 0;
let totalRestores  = 0;
const failureLog   = []; // ring buffer of last 20 failures

// ── Circuit Breaker State ───────────────────────────────────────────────────
// Protects the proxy from hammering a dead upstream. After N consecutive
// failures the breaker "opens" and short-circuits requests (returning a
// graceful 503) until a cooldown window elapses, then allows a single
// "half-open" probe to test whether the upstream has recovered.
const CB_FAILURE_THRESHOLD = parseInt(process.env.LUMAX_CB_THRESHOLD || '5', 10); // consecutive failures to trip
const CB_COOLDOWN_MS       = parseInt(process.env.LUMAX_CB_COOLDOWN_MS || '30000', 10); // 30s before half-open probe
let cbFailureCount   = 0;
let cbOpenedAt       = 0;   // timestamp when breaker last opened
let cbHalfOpen       = false; // true while a single probe request is in flight

const circuitBreaker = {
    // `open` is true when the breaker is tripped AND still in cooldown.
    // During half-open, `open` is false so a single probe can pass through.
    get open() {
        if (cbFailureCount < CB_FAILURE_THRESHOLD) return false;
        if (cbHalfOpen) return false; // allow the probe
        return (Date.now() - cbOpenedAt) < CB_COOLDOWN_MS;
    },
    get state() {
        if (cbFailureCount < CB_FAILURE_THRESHOLD) return 'closed';
        if (cbHalfOpen) return 'half-open';
        if ((Date.now() - cbOpenedAt) < CB_COOLDOWN_MS) return 'open';
        return 'half-open-ready';
    },
    get failureCount() { return cbFailureCount; },
    get threshold() { return CB_FAILURE_THRESHOLD; },
    get cooldownMs() { return CB_COOLDOWN_MS; },
};

/**
 * Record a failure against the circuit breaker. Called on every upstream
 * failure (non-OK status or connection error). Trips the breaker once the
 * consecutive-failure threshold is reached.
 */
function recordCircuitFailure() {
    cbFailureCount++;
    cbHalfOpen = false; // any in-flight probe has now failed
    if (cbFailureCount >= CB_FAILURE_THRESHOLD) {
        const wasOpen = cbOpenedAt > 0;
        cbOpenedAt = Date.now(); // (re)start cooldown window
        if (!wasOpen) {
            console.log(`[CircuitBreaker] 🔴 OPEN — ${cbFailureCount} consecutive failures. Cooling down for ${CB_COOLDOWN_MS}ms.`);
        }
    }
}

/**
 * Record a success against the circuit breaker. Resets the failure count and
 * closes the breaker. Called on every successful upstream response.
 */
function recordCircuitSuccess() {
    if (cbFailureCount > 0 || cbOpenedAt > 0) {
        console.log(`[CircuitBreaker] 🟢 CLOSED — upstream recovered after ${cbFailureCount} failures.`);
    }
    cbFailureCount = 0;
    cbOpenedAt = 0;
    cbHalfOpen = false;
}

/**
 * Mark the breaker as half-open (a single probe request is being attempted
 * after the cooldown window). Returns true if the probe is allowed to proceed.
 */
function allowHalfOpenProbe() {
    if (cbFailureCount < CB_FAILURE_THRESHOLD) return true; // not tripped
    if (cbHalfOpen) return false; // a probe is already in flight
    if ((Date.now() - cbOpenedAt) < CB_COOLDOWN_MS) return false; // still cooling down
    cbHalfOpen = true;
    console.log('[CircuitBreaker] 🟡 HALF-OPEN — allowing single probe request.');
    return true;
}

/**
 * Reset the breaker entirely (admin/debug use).
 */
function resetCircuitBreaker() {
    cbFailureCount = 0;
    cbOpenedAt = 0;
    cbHalfOpen = false;
    console.log('[CircuitBreaker] 🔄 Force-reset to CLOSED.');
}

// ── Upstream error patterns that indicate context overflow ──────────────────
const CTX_OVERFLOW_PATTERNS = [
    /context.{0,20}(?:too.{0,10}long|overflow|exceed|limit)/i,
    /maximum.{0,20}(?:context|token|length)/i,
    /(?:token|context).{0,20}(?:limit|budget|window).{0,20}exceeded/i,
    /reduce.{0,20}(?:context|input|message).{0,20}(?:length|size)/i,
    /input.{0,20}too.{0,10}(?:long|large)/i,
    /(?:413|400|429).{0,30}(?:payload|entity|request).{0,20}(?:too|large)/i,
    /out.{0,5}of.{0,5}memory/i,
    /OOM/i,
    /CUDA.{0,10}out.{0,5}of.{0,5}memory/i,
    // ── llama.cpp / LM Studio / llama-server specific overflow errors ──
    /n_ctx/i,                                   // "n_ctx is ... but ... needed"
    /exceeds.{0,20}(?:the.{0,15})?context/i,    // "exceeds context window"
    /(?:prompt|input).{0,20}(?:is|too).{0,20}(?:long|large)/i,
    /(?:larger|greater).{0,10}(?:than).{0,10}(?:n_ctx|context|window)/i,
    /context.{0,15}(?:window|length|size)/i,
    /(?:KV|kv.{0,3}cache).{0,20}(?:full|exceed|limit|overflow)/i,
    /(?:requested|required).{0,20}(?:length|context|tokens)/i,
    /(?:too many|insufficient).{0,20}(?:tokens|context)/i,
    /(?:context|prompt).{0,20}(?:is|too).{0,10}(?:big|large|huge)/i,
    /(?:token|context).{0,20}(?:window|budget).{0,20}(?:exceed|too small|not enough)/i,
];

// ── Upstream status codes that suggest context overflow ─────────────────────
const CTX_OVERFLOW_CODES = new Set([400, 413, 429, 500, 502, 503]);

/**
 * Check if an upstream error looks like a context overflow.
 */
function isContextOverflow(statusCode, errorText) {
    if (statusCode && CTX_OVERFLOW_CODES.has(statusCode)) {
        // Check text for overflow patterns
        if (errorText && CTX_OVERFLOW_PATTERNS.some(p => p.test(errorText))) {
            return true;
        }
        // 413 is always context overflow
        if (statusCode === 413) return true;
        // 500/502/503 with empty body often means OOM
        if ([500, 502, 503].includes(statusCode) && (!errorText || errorText.trim().length < 50)) {
            return true;
        }
    }
    return false;
}

/**
 * Check if an empty/truncated response looks like context overflow.
 */
function isEmptyResponseOverflow(fullText, statusCode) {
    // Empty response from upstream that returned 200 = model crashed mid-generation
    if ((!fullText || fullText.trim().length === 0) && statusCode === 200) {
        return true;
    }
    // Very short truncated response (< 10 chars) from a large prompt
    if (fullText && fullText.trim().length < 10 && statusCode === 200) {
        return true;
    }
    return false;
}

/**
 * Get the current context budget (chars).
 */
function getBudget() {
    return currentBudget;
}

/**
 * Get full healer state for health endpoint.
 */
function getState() {
    return {
        currentBudget,
        maxBudget: MAX_BUDGET_CHARS,
        minBudget: MIN_BUDGET_CHARS,
        lastFailureAt: lastFailureAt ? new Date(lastFailureAt).toISOString() : null,
        consecutiveOk,
        totalShrinks,
        totalRestores,
        cooldownActive: (Date.now() - lastFailureAt) < COOLDOWN_MS,
        recentFailures: failureLog.slice(-5),
        circuitBreaker: {
            state: circuitBreaker.state,
            open: circuitBreaker.open,
            failureCount: circuitBreaker.failureCount,
            threshold: circuitBreaker.threshold,
            cooldownMs: circuitBreaker.cooldownMs,
        },
    };
}

/**
 * Called when upstream succeeds. Gradually restores budget.
 */
function onSuccess() {
    consecutiveOk++;
    
    // Only recover after cooldown period
    if (Date.now() - lastFailureAt < COOLDOWN_MS) {
        return;
    }
    
    // Gradual recovery: step up toward MAX_BUDGET
    if (currentBudget < MAX_BUDGET_CHARS && consecutiveOk >= 3) {
        const prev = currentBudget;
        currentBudget = Math.min(MAX_BUDGET_CHARS, currentBudget + RECOVERY_STEP);
        totalRestores++;
        console.log(`[ContextHealer] 📈 Budget recovering: ${prev} → ${currentBudget} chars (${consecutiveOk} consecutive OK)`);
    }
}

/**
 * Called when upstream fails. Diagnoses and shrinks budget if needed.
 * @param {number} statusCode - HTTP status from upstream
 * @param {string} errorText - Error body from upstream
 * @param {string} fullText - Collected response text (for empty-response detection)
 * @returns {{ shrunk: boolean, newBudget: number, reason: string, shouldRetry: boolean }}
 */
function onFailure(statusCode, errorText, fullText) {
    const now = Date.now();
    lastFailureAt = now;
    consecutiveOk = 0;
    
    const isOverflow = isContextOverflow(statusCode, errorText) 
                     || isEmptyResponseOverflow(fullText, statusCode);
    
    failureLog.push({
        timestamp: new Date(now).toISOString(),
        statusCode,
        isOverflow,
        errorSnippet: (errorText || '').slice(0, 200),
        budgetBefore: currentBudget,
    });
    if (failureLog.length > 20) failureLog.shift();
    
    if (!isOverflow) {
        console.log(`[ContextHealer] ℹ️ Upstream failure (status=${statusCode}) — not context-related, no shrink`);
        return { shrunk: false, newBudget: currentBudget, reason: 'non-context failure', shouldRetry: false };
    }
    
    // Shrink budget
    const prev = currentBudget;
    currentBudget = Math.max(MIN_BUDGET_CHARS, Math.floor(currentBudget * BACKOFF_FACTOR));
    totalShrinks++;
    
    const reason = statusCode === 200
        ? `empty response (likely OOM/crash from ${prev} char context)`
        : `status ${statusCode}: ${(errorText || '').slice(0, 100)}`;
    
    console.log(`[ContextHealer] 🔻 Budget shrunk: ${prev} → ${currentBudget} chars (reason: ${reason})`);
    
    const shouldRetry = currentBudget >= MIN_BUDGET_CHARS;
    return { shrunk: true, newBudget: currentBudget, reason, shouldRetry };
}

/**
 * Apply the current budget to a messages array.
 * Truncates oldest non-system messages to fit within budget.
 * Injects a warning system message if truncation occurred.
 *
 * @param {Array} messages
 * @param {number} keepLast - minimum messages to keep at the end
 * @returns {{ messages: Array, truncated: boolean, originalChars: number, finalChars: number, warning: string|null }}
 */
function applyBudget(messages, keepLast = 4) {
    // Count chars
    let totalChars = 0;
    for (const m of messages) {
        totalChars += typeof m.content === 'string' ? m.content.length : JSON.stringify(m.content || '').length;
    }
    
    if (totalChars <= currentBudget) {
        return { messages, truncated: false, originalChars: totalChars, finalChars: totalChars, warning: null };
    }
    
    // Separate system messages from conversation
    const systemMsgs = messages.filter(m => m.role === 'system');
    const convoMsgs  = messages.filter(m => m.role !== 'system');
    
    const keep = Math.max(2, keepLast);
    let truncated = convoMsgs.slice(-keep);
    const dropped = convoMsgs.length - keep;
    
    // Start with the last N conversation turns + all system messages.
    let result = [...systemMsgs, ...truncated];
    
    // ── ALWAYS-FITS SHRINK (never refuse) ────────────────────────────────
    // If system messages + kept turns still exceed the budget, progressively
    // shrink the LARGEST system message (typically the memory ring block,
    // which is the most expendable) until everything fits. This guarantees
    // the proxy returns a valid response instead of a 400 overflow error.
    let finalChars = 0;
    for (const m of result) {
        finalChars += typeof m.content === 'string' ? m.content.length : JSON.stringify(m.content || '').length;
    }
    
    if (finalChars > currentBudget) {
        // Sort system messages by size, largest first, and truncate them.
        const sysIdx = result.map((m, i) => ({ m, i }))
            .filter(x => x.m.role === 'system')
            .sort((a, b) => b.m.content.length - a.m.content.length);
        
        for (const { m, i } of sysIdx) {
            if (finalChars <= currentBudget) break;
            const content = typeof m.content === 'string' ? m.content : JSON.stringify(m.content || '');
            const target = Math.max(0, content.length - (finalChars - currentBudget));
            const keptLen = Math.max(200, target); // keep at least a 200-char stub
            const cut = content.slice(0, keptLen) + (content.length > keptLen ? '\n[...truncated by context budget...]' : '');
            result[i] = { ...m, content: cut };
            finalChars = result.reduce((n, mm) => n + (typeof mm.content === 'string' ? mm.content.length : JSON.stringify(mm.content || '').length), 0);
        }
    }
    
    // Last resort: hard-truncate the largest remaining message to the budget.
    while (finalChars > currentBudget && result.length > 0) {
        const idx = result
            .map((m, i) => ({ len: typeof m.content === 'string' ? m.content.length : JSON.stringify(m.content || '').length, i }))
            .sort((a, b) => b.len - a.len)[0].i;
        const m = result[idx];
        const content = typeof m.content === 'string' ? m.content : JSON.stringify(m.content || '');
        const keepLen = Math.max(100, content.length - (finalChars - currentBudget));
        result[idx] = { ...m, content: content.slice(0, keepLen) + (content.length > keepLen ? '...' : '') };
        finalChars = result.reduce((n, mm) => n + (typeof mm.content === 'string' ? mm.content.length : JSON.stringify(mm.content || '').length), 0);
        if (finalChars > currentBudget && result.length === 1) {
            // Force a minimal single message so the model always gets something.
            result[0] = { ...result[0], content: '[...context omitted to fit model window...]' };
            finalChars = result[0].content.length;
        }
    }
    
    const warning = `⚠️ Context overflow protection: ${dropped} messages dropped + context compressed (${totalChars} → ${finalChars} chars). Budget: ${currentBudget}/${MAX_BUDGET_CHARS} chars. The proxy auto-shrunk to prevent upstream crash. Budget will auto-restore after stable operation.`;
    
    console.log(`[ContextHealer] ✂️ Shrunk ${dropped} msgs + compressed oversized context (${totalChars} → ${finalChars} chars, budget=${currentBudget})`);
    
    return { messages: result, truncated: true, originalChars: totalChars, finalChars, warning };
}

/**
 * Inject a context warning into the response content.
 * Appends a non-intrusive note that the client can parse.
 */
function injectWarning(content, warning) {
    if (!warning) return content;
    // Add as an HTML-comment-style marker that's parseable but unobtrusive
    return content + `\n\n<!-- LUMAX_CTX_WARNING: ${warning} -->`;
}

/**
 * Force-reset the budget to max (for admin/debug use).
 */
function resetBudget() {
    const prev = currentBudget;
    currentBudget = MAX_BUDGET_CHARS;
    lastFailureAt = 0;
    consecutiveOk = 0;
    console.log(`[ContextHealer] 🔄 Budget force-reset: ${prev} → ${currentBudget}`);
    return { previous: prev, current: currentBudget };
}

/**
 * Manually set budget to a specific value (within min/max range).
 */
function setBudget(value) {
    const clamped = Math.max(MIN_BUDGET_CHARS, Math.min(MAX_BUDGET_CHARS, value));
    const prev = currentBudget;
    currentBudget = clamped;
    console.log(`[ContextHealer] 🎯 Budget manually set: ${prev} → ${currentBudget}`);
    return { previous: prev, current: currentBudget };
}

module.exports = {
    getBudget,
    getState,
    onSuccess,
    onFailure,
    applyBudget,
    injectWarning,
    resetBudget,
    setBudget,
    isContextOverflow,
    isEmptyResponseOverflow,
    circuitBreaker,
    recordCircuitFailure,
    recordCircuitSuccess,
    allowHalfOpenProbe,
    resetCircuitBreaker,
    MAX_BUDGET_CHARS,
    MIN_BUDGET_CHARS,
};
