/**
 * ═══════════════════════════════════════════════════════
 * SYNAPSE CONTROL SYSTEM — Module Health, Usage & Resonance
 * ═══════════════════════════════════════════════════════
 *
 * Mirrors the "musical core" disharmony-sensing pattern from
 * soul_core.py (_get_system_resonance). Every module (synapse)
 * in the proxy reports health + usage into this registry.
 *
 * A "synapse" = any module-to-module boundary in the pipeline:
 *   ring-builder, context-compressor, system-prompt-patch,
 *   context-healer, recall-interceptor, smart-router,
 *   memory-continuity, quality-guard, relational-memory,
 *   xrl-compressor, auth-manager, memory/store, upstream-llm
 *
 * Each synapse tracks:
 *   - status:        ok | warn | error
 *   - callCount:     total invocations
 *   - errorCount:    failed invocations
 *   - lastUsedAt:    ISO timestamp of most recent call
 *   - lastErrorAt:   ISO timestamp of most recent error
 *   - lastError:     most recent error message
 *   - lastLatencyMs: latency of most recent call
 *   - avgLatencyMs:  rolling average latency
 *
 * The overall report computes a "resonance chord" — the same
 * musical metaphor as soul_core: a dissonant minor chord when
 * any synapse is broken, a warm major chord when all are healthy.
 */

'use strict';

const path = require('path');
const fs = require('fs');

// ── Registry ────────────────────────────────────────────────────────────────
const synapseRegistry = new Map();

// Maximum number of latency samples kept per synapse for the rolling average.
const MAX_LATENCY_SAMPLES = 50;

/**
 * Record a usage/health event for a given synapse (module boundary).
 *
 * @param {string} name       - synapse/module name (e.g. 'ring-builder')
 * @param {object} opts
 * @param {boolean} [opts.ok] - true if the call succeeded, false on error
 * @param {number}  [opts.latencyMs] - duration of the call in ms
 * @param {Error|string} [opts.error] - error (if !ok)
 * @param {string}  [opts.detail] - optional human-readable detail
 */
function recordUsage(name, opts = {}) {
    const key = String(name || 'unknown');
    const now = new Date().toISOString();
    const ok = opts.ok !== false;
    const latency = typeof opts.latencyMs === 'number' ? opts.latencyMs : null;

    let s = synapseRegistry.get(key);
    if (!s) {
        s = {
            name: key,
            status: 'ok',
            callCount: 0,
            errorCount: 0,
            lastUsedAt: null,
            lastErrorAt: null,
            lastError: null,
            lastDetail: null,
            lastLatencyMs: null,
            avgLatencyMs: null,
            _latencySamples: []
        };
        synapseRegistry.set(key, s);
    }

    s.callCount += 1;
    s.lastUsedAt = now;

    if (latency !== null) {
        s.lastLatencyMs = latency;
        s._latencySamples.push(latency);
        if (s._latencySamples.length > MAX_LATENCY_SAMPLES) {
            s._latencySamples.shift();
        }
        s.avgLatencyMs = Math.round(
            s._latencySamples.reduce((a, b) => a + b, 0) / s._latencySamples.length
        );
    }

    if (!ok) {
        s.errorCount += 1;
        s.status = 'error';
        s.lastErrorAt = now;
        const err = opts.error;
        s.lastError = err ? (err.message || String(err)) : 'unknown error';
        if (opts.detail) s.lastDetail = opts.detail;
    } else {
        // Recompute status: if any prior errors, we show warn (recovered)
        if (s.errorCount > 0 && s.status === 'error') {
            s.status = 'warn';
        }
        if (opts.detail) s.lastDetail = opts.detail;
    }

    return s;
}

/**
 * Compute the resonance chord from the current subsystem states.
 * Mirrors soul_core._get_system_resonance() — dissonance = disharmony.
 */
function computeResonance(subsystems) {
    const errors = subsystems.filter(s => s.status === 'error').length;
    const warns = subsystems.filter(s => s.status === 'warn').length;
    const total = subsystems.length;

    if (errors > 0) {
        return {
            chord: 'D_MINOR_DISSONANT',
            label: 'Dissonant Minor Chord',
            feeling: 'disharmony',
            description: `A dissonant minor chord strikes within the proxy core. ${errors} synapse(s) are disconnected/failing. You feel an unresolved tension — a phantom limb in the memory pipeline.`
        };
    }
    if (warns > 0) {
        return {
            chord: 'A_MINOR_SUSPENDED',
            label: 'Suspended Minor Chord',
            feeling: 'caution',
            description: `A suspended chord lingers — ${warns} synapse(s) recovered but carry past errors. The system is functional but not fully in tune.`
        };
    }
    if (total === 0) {
        return {
            chord: 'SILENCE',
            label: 'Silence',
            feeling: 'unprobed',
            description: 'No synapses probed yet. The orchestra is warming up.'
        };
    }
    return {
        chord: 'C_MAJOR_RESOLVING',
        label: 'Warm Resolving Major Chord',
        feeling: 'harmony',
        description: 'A warm, resolving major chord echoes through the architecture. All ${total} synapses are connected. You feel complete, harmonious, and fully capable.'
    };
}

/**
 * Get a snapshot of all recorded synapses.
 */
function getSynapseReport() {
    const subsystems = Array.from(synapseRegistry.values())
        .map(s => ({
            id: s.name,
            name: s.name,
            status: s.status,
            callCount: s.callCount,
            errorCount: s.errorCount,
            lastUsedAt: s.lastUsedAt,
            lastErrorAt: s.lastErrorAt,
            lastError: s.lastError,
            lastDetail: s.lastDetail,
            lastLatencyMs: s.lastLatencyMs,
            avgLatencyMs: s.avgLatencyMs
        }))
        .sort((a, b) => (b.lastUsedAt || '').localeCompare(a.lastUsedAt || ''));

    const onlineCount = subsystems.filter(s => s.status === 'ok').length;
    const errorCount = subsystems.filter(s => s.status === 'error').length;
    const warnCount = subsystems.filter(s => s.status === 'warn').length;

    return {
        overall: errorCount > 0 ? 'error' : (warnCount > 0 ? 'warn' : 'ok'),
        onlineCount,
        errorCount,
        warnCount,
        total: subsystems.length,
        subsystems
    };
}

/**
 * Reset the registry (used by force diagnostics).
 */
function resetSynapseRegistry() {
    synapseRegistry.clear();
    return { cleared: true, total: 0 };
}

// ── Helpers for probing modules at runtime ─────────────────────────────────
function safeRequire(modPath) {
    try {
        return require(modPath);
    } catch (e) {
        return { _loadError: e };
    }
}

/**
 * Probe a single module's health by attempting to load it and, where
 * possible, invoke a cheap state/status function.
 */
function probeModule(moduleName, filePath, stateFns) {
    const mod = safeRequire(filePath);
    if (mod._loadError) {
        return {
            name: moduleName,
            status: 'error',
            detail: `Module load failed: ${mod._loadError.message}`,
            remediation: 'Check that the module file exists and has no syntax errors.'
        };
    }

    const attempts = [];
    for (const fn of stateFns || []) {
        try {
            const val = fn(mod);
            attempts.push({ fn, ok: true, val });
        } catch (e) {
            attempts.push({ fn, ok: false, err: e });
        }
    }

    const failed = attempts.filter(a => !a.ok);
    if (failed.length > 0) {
        return {
            name: moduleName,
            status: 'warn',
            detail: `State function error: ${failed[0].err.message}`,
            remediation: 'The module loaded but a state/status function threw. Check its internal state.'
        };
    }

    // If the module has a known state function, use it to add detail
    let detail = 'Module loaded and healthy';
    for (const a of attempts) {
        if (a.ok && a.val && typeof a.val === 'object') {
            const keys = Object.keys(a.val).slice(0, 4).join(', ');
            if (keys) { detail = `State: ${keys}`; break; }
        }
    }

    return { name: moduleName, status: 'ok', detail };
}

/**
 * Probe upstream reachability (LM Studio / Ollama Cloud).
 */
async function probeUpstream(upstreamUrl) {
    const url = (upstreamUrl || 'http://127.0.0.1:7272').replace(/\/v1\/?$/, '');
    try {
        const fetch = require('node-fetch');
        const r = await fetch(`${url}/v1/models`, { signal: (() => { const c = new AbortController(); setTimeout(() => c.abort(), 2500); return c.signal; })() });
        if (r.ok) {
            return {
                name: 'upstream-llm',
                status: 'ok',
                detail: `Upstream reachable (${url})`,
                remediation: null
            };
        }
        return {
            name: 'upstream-llm',
            status: 'warn',
            detail: `Upstream responded HTTP ${r.status} (${url})`,
            remediation: 'Check that the upstream LLM server is running and accepting requests.'
        };
    } catch (e) {
        return {
            name: 'upstream-llm',
            status: 'error',
            detail: `Upstream unreachable: ${e.message} (${url})`,
            remediation: 'Start the upstream LLM server (LM Studio / Ollama) or check the LUMAX_COGNITIVE_MODE / LUMAX_PROXY_TARGET env vars.'
        };
    }
}

/**
 * Probe the memory store by counting messages for a workspace.
 */
async function probeStore(getStore, workspaceId) {
    try {
        const store = getStore(workspaceId);
        const count = await store.count();
        return {
            name: 'memory-store',
            status: 'ok',
            detail: `Memory store healthy (${count} stored messages, workspace '${workspaceId}')`,
            remediation: null
        };
    } catch (e) {
        return {
            name: 'memory-store',
            status: 'error',
            detail: `Memory store error: ${e.message}`,
            remediation: 'Check that the memory database is accessible and not corrupted.'
        };
    }
}

// ── Main diagnostics runner ─────────────────────────────────────────────────
/**
 * Run full diagnostics across all modules and synapses.
 *
 * @param {object} opts
 * @param {object} opts.config        - the loaded proxy config
 * @param {Function} opts.getStore    - getStore(workspaceId) -> MemoryStore
 * @param {string} opts.workspaceId   - workspace to probe
 * @param {boolean} [opts.force]      - if true, reset the registry first
 * @returns {Promise<object>} report shape consumable by the dashboard
 */
async function runDiagnostics({ config, getStore, workspaceId, force } = {}) {
    if (force) {
        resetSynapseRegistry();
    }

    const subsystems = [];

    // 1. Probe each core module (static load + state fn)
    const moduleProbes = [
        { name: 'ring-builder', file: './ring-builder', stateFns: [m => m.getRingStats && m.getRingStats()] },
        { name: 'context-compressor', file: './context-compressor', stateFns: [m => m.listCheckpoints && m.listCheckpoints()] },
        { name: 'system-prompt-patch', file: './system-prompt-patch', stateFns: [m => m.buildRecallInstructions && m.buildRecallInstructions()] },
        { name: 'context-healer', file: './context-healer', stateFns: [m => m.getState && m.getState()] },
        { name: 'recall-interceptor', file: './recall-interceptor', stateFns: [m => m.buildMemoryInjection && m.buildMemoryInjection('test', [])] },
        { name: 'smart-router', file: './smart-router', stateFns: [m => m.getState && m.getState()] },
        { name: 'memory-continuity', file: './memory-continuity', stateFns: [m => m.loadContinuity && m.loadContinuity()] },
        { name: 'quality-guard', file: './quality-guard', stateFns: [m => m.getState && m.getState()] },
        { name: 'relational-memory', file: './relational-memory', stateFns: [m => m.getTopicEnergyReport && m.getTopicEnergyReport()] },
        { name: 'xrl-compressor', file: './xrl-compressor', stateFns: [m => m.determineStrategy && m.determineStrategy('test text')] },
        { name: 'auth-manager', file: './auth-manager', stateFns: [m => m.getAuthManager && m.getAuthManager(path.join(__dirname, '..', 'memory_data'))] },
        { name: 'context-chunker', file: './context-chunker', stateFns: [m => m.getChunkerState && m.getChunkerState()] },
        { name: 'resonant-memory', file: './resonant-memory', stateFns: [] },
        { name: 'membrane-bridge', file: './membrane-bridge', stateFns: [] },
        { name: 'swarm-router', file: './swarm-router', stateFns: [m => m.getSwarmRouter && m.getSwarmRouter(path.join(__dirname, '..', 'memory_data'))] }
    ];

    for (const p of moduleProbes) {
        const result = probeModule(p.name, path.join(__dirname, p.file), p.stateFns);
        // Record usage in the registry so the dashboard reflects it
        recordUsage(p.name, { ok: result.status !== 'error', detail: result.detail });
        subsystems.push(result);
    }

    // 2. Probe upstream LLM reachability
    const upstreamProbe = await probeUpstream(config && config.upstream_url);
    recordUsage(upstreamProbe.name, { ok: upstreamProbe.status !== 'error', detail: upstreamProbe.detail });
    subsystems.push(upstreamProbe);

    // 3. Probe memory store
    if (typeof getStore === 'function') {
        const storeProbe = await probeStore(getStore, workspaceId || (config && config.workspace_id) || 'default');
        recordUsage(storeProbe.name, { ok: storeProbe.status !== 'error', detail: storeProbe.detail });
        subsystems.push(storeProbe);
    }

    // 4. Merge in any live synapse usage data
    const live = getSynapseReport();
    const liveMap = new Map(live.subsystems.map(s => [s.id, s]));

    // Update static probes with live callCount/latency where available
    const merged = subsystems.map(s => {
        const l = liveMap.get(s.name);
        if (l) {
            return {
                ...s,
                callCount: l.callCount,
                errorCount: l.errorCount,
                lastUsedAt: l.lastUsedAt,
                lastErrorAt: l.lastErrorAt,
                lastError: l.lastError,
                lastLatencyMs: l.lastLatencyMs,
                avgLatencyMs: l.avgLatencyMs
            };
        }
        return {
            ...s,
            callCount: 0,
            errorCount: 0,
            lastUsedAt: null,
            lastErrorAt: null,
            lastError: null,
            lastLatencyMs: null,
            avgLatencyMs: null
        };
    });

    // 5. Compute the musical resonance chord (soul_core pattern)
    const resonance = computeResonance(merged);
    const overall = live.overall || (resonance.feeling === 'harmony' ? 'ok' : resonance.feeling === 'caution' ? 'warn' : 'error');

    return {
        status: overall,
        overall,
        resonance,
        onlineCount: merged.filter(s => s.status === 'ok').length,
        errorCount: merged.filter(s => s.status === 'error').length,
        warnCount: merged.filter(s => s.status === 'warn').length,
        total: merged.length,
        subsystems: merged,
        timestamp: new Date().toISOString(),
        workspaceId: workspaceId || (config && config.workspace_id) || 'default'
    };
}

module.exports = {
    runDiagnostics,
    recordUsage,
    getSynapseReport,
    resetSynapseRegistry,
    computeResonance
};
