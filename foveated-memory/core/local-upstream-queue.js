/**
 * ═══════════════════════════════════════════════════════
 * LOCAL UPSTREAM QUEUE — serialize :8402 decode calls
 * ═══════════════════════════════════════════════════════
 *
 * llama.cpp's CUDA pool asserts (GGML_ASSERT ptr == pool_addr + pool_used →
 * SIGABRT, see runtime_stderr.log) when inference requests overlap on a
 * single context. Every call to the local XRLF runtime must go through
 * this queue so only one request is in flight at a time.
 *
 * Cloud routes (nvidia/*, cloud mode) bypass the queue — the constraint is
 * local llama.cpp only.
 *
 * IMPORTANT: only wrap the INNERMOST fetch. Wrapping a call site that
 * internally invokes another queued function deadlocks the chain.
 */
'use strict';

let _tail = Promise.resolve();

/**
 * Wait for our turn in the queue. Resolves to a release() function that
 * MUST be called when the upstream response body is fully consumed.
 */
function acquireLocalUpstream() {
    let release;
    const barrier = new Promise(r => { release = r; });
    const ticket = _tail.then(() => release);
    _tail = _tail.then(() => barrier);
    return ticket;
}

/**
 * Convenience wrapper for calls whose body is fully consumed inside fn().
 */
async function withLocalUpstream(fn) {
    const release = await acquireLocalUpstream();
    try { return await fn(); } finally { release(); }
}

module.exports = { acquireLocalUpstream, withLocalUpstream };
