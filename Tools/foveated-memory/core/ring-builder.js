/**
 * ═══════════════════════════════════════════════════════
 * RING BUILDER — Foveated Memory Ring Block Generator
 * ═══════════════════════════════════════════════════════
 *
 * Builds the 6-ring foveated memory block that gets injected
 * into every context window at session start.
 *
 * Ring 0 (Fovea)         — 6 refined messages, tone-classified, ~1/3 adaptive compression
 * Ring 1 (Parafovea)     — recent session themes, ~50% compressed
 * Ring 2 (Near Periphery)— this week, ~75% compressed
 * Ring 3 (Mid Periphery) — this month, ~88% compressed
 * Ring 4 (Far Periphery) — older, ~95% compressed (hash refs)
 * Ring 5 (Outer Periphery)— deep past, ~98% compressed (atomic hashes)
 *
 * Total token budget: configurable, default ~400 tokens.
 */

'use strict';

const xrl = require('./xrl-compressor');
const resonant = require('./resonant-memory');

// ── Ring Stats Accumulator ──────────────────────────────────────────────────
// Tracks per-ring token counts and compression ratios for observability.

/**
 * @typedef {Object} RingStat
 * @property {number} ring          - Ring number (0-5)
 * @property {string} label         - Human label (FOVEA, PARAFOVEA, etc.)
 * @property {number} msgCount      - Number of messages in this ring
 * @property {number} originalChars - Total chars of original messages
 * @property {number} compressedChars - Chars after compression
 * @property {number} budgetTokens  - Token budget for this ring
 * @property {number} actualTokens  - Estimated tokens used
 * @property {number} compressionRatio - 0.0 (raw) to ~0.98 (atomic)
 * @property {string} method        - 'verbatim', 'extractive', 'llm-summary', 'hash'
 */

/**
 * @typedef {Object} RingStats
 * @property {RingStat[]} rings       - Per-ring breakdown
 * @property {number} totalOriginalChars
 * @property {number} totalCompressedChars
 * @property {number} overallRatio   - Overall compression ratio
 * @property {number} totalTokens    - Total estimated tokens in ring block
 * @property {number} ringCount     - Number of non-empty rings
 * @property {Object} tiers          - Tiered context budget breakdown
 * @property {number} tiers.refined              - Ring 0 chars (tone-classified, ~1/3 adaptive, voice preserved)
 * @property {number} tiers.minimallyCompressed - Ring 1 chars (light compression)
 * @property {number} tiers.moderatelyCompressed - Rings 2-3 chars (medium/deep)
 * @property {number} tiers.maximallyCompressed  - Rings 4-5 chars (ultra/atomic)
 * @property {number} tiers.totalChars           - Sum of all tier chars
 */

/**
 * Build the full foveated ring block string.
 *
 * @param {import('../memory/store').MemoryStore} store
 * @param {object} config - The proxy config object
 * @param {string} sessionId - Current session ID
 * @returns {Promise<{ block: string, stats: RingStats }>}
 */
async function buildRingBlock(store, config, sessionId) {
    const budgets = config.ring_budgets || {
        0: 180, 1: 80, 2: 60, 3: 40, 4: 25, 5: 15
    };

    // Lazy-load relational memory for topic graph (avoid circular dep)
    let topicGraph = null;
    try {
        const rel = require('./relational-memory');
        topicGraph = rel.getRawGraph ? rel.getRawGraph() : null;
    } catch (_) {}

    const sections = [];
    /** @type {RingStat[]} */
    const ringStats = [];
    const RING_LABELS = ['FOVEA', 'PARAFOVEA', 'NEAR-PERIPHERY', 'MID-PERIPHERY', 'FAR-PERIPHERY', 'OUTER-PERIPHERY'];
    const RING_METHODS = ['llm-refined', 'extractive', 'extractive', 'extractive', 'hash', 'hash'];

    /**
     * Compute total original chars from an array of messages.
     */
    function originalChars(msgs) {
        return msgs.reduce((n, m) => {
            const c = typeof m.content === 'string' ? m.content : JSON.stringify(m.content || '');
            return n + c.length;
        }, 0);
    }

    try {
        // ── Task Board ───────────────────────────────────────────────────
        const tasks = await store.getTasks(sessionId);
        if (tasks && tasks.length > 0) {
            const pending = tasks.filter(t => !t.done);
            const done = tasks.filter(t => t.done);
            let taskBlock = `[ACTIVE TASK BOARD — ${pending.length} pending, ${done.length} completed]\n`;
            if (pending.length > 0) {
                taskBlock += pending.map(t => `- [ ] ${t.text}`).join('\n') + '\n';
            }
            if (done.length > 0) {
                taskBlock += done.map(t => `- [x] ${t.text}`).join('\n') + '\n';
            }
            taskBlock += `> To update, output \`- [x] task text\` in your response.`;
            sections.push(taskBlock);
        }

        // ── Ring 0 — Fovea: last N messages from THIS session only ─────
        // Filtering to active session prevents cross-session file dumps from
        // polluting every request's context window.
        const foveaCount = config.fovea_message_count || 6;
        const foveaMessages = await store.getRecentBySession(sessionId, foveaCount);
        const foveaIds = new Set(foveaMessages.map(m => m._id));

        if (foveaMessages.length > 0) {
            const origChars = originalChars(foveaMessages);
            // Use async path for Ring 0 — enables two-stage LLM refinement pipeline
            const compressed = await xrl.compressAsync(foveaMessages, 0, budgets[0]);
            sections.push(`[FOVEA — last ${foveaMessages.length} messages, LLM-analyzed, tone-classified, ~1/3 adaptive]\n${compressed}`);
            ringStats.push({
                ring: 0, label: 'FOVEA', msgCount: foveaMessages.length,
                originalChars: origChars, compressedChars: compressed.length,
                budgetTokens: budgets[0], actualTokens: xrl.estimateTokens(compressed),
                compressionRatio: origChars > 0 ? 1 - (compressed.length / origChars) : 0,
                method: 'llm-refined'
            });
        }

        // ── Ring 1 — Parafovea: messages from last 24h not in fovea ──────
        const day1Raw = await store.getByAge(1, 0, 30);
        const day1 = Array.isArray(day1Raw) ? day1Raw : [];
        const day1Filtered = day1.filter(m => !foveaIds.has(m._id));
        if (day1Filtered.length > 0) {
            const origChars = originalChars(day1Filtered);
            const compressed = await xrl.compressAsync(day1Filtered, 1, budgets[1]);
            if (compressed.trim()) {
                sections.push(`[PARAFOVEA — last 24h, light compression]\n${compressed}`);
                const isLLM = compressed.includes('[PARAFOVEA-LLM]');
                ringStats.push({
                    ring: 1, label: 'PARAFOVEA', msgCount: day1Filtered.length,
                    originalChars: origChars, compressedChars: compressed.length,
                    budgetTokens: budgets[1], actualTokens: xrl.estimateTokens(compressed),
                    compressionRatio: origChars > 0 ? 1 - (compressed.length / origChars) : 0,
                    method: isLLM ? 'llm-summary' : 'extractive'
                });
            }
        }

        // ── Ring 2 — Near Periphery: 1–7 days ago ────────────────────────
        const weekRaw = await store.getByAge(7, 1, 40);
        const week = Array.isArray(weekRaw) ? weekRaw : [];
        if (week.length > 0) {
            const origChars = originalChars(week);
            const compressed = await xrl.compressAsync(week, 2, budgets[2]);
            if (compressed.trim()) {
                sections.push(`[NEAR PERIPHERY — last week, medium compression]\n${compressed}`);
                const isLLM = compressed.includes('[NEAR-PERIPHERY-LLM]');
                ringStats.push({
                    ring: 2, label: 'NEAR-PERIPHERY', msgCount: week.length,
                    originalChars: origChars, compressedChars: compressed.length,
                    budgetTokens: budgets[2], actualTokens: xrl.estimateTokens(compressed),
                    compressionRatio: origChars > 0 ? 1 - (compressed.length / origChars) : 0,
                    method: isLLM ? 'llm-summary' : 'extractive'
                });
            }
        }

        // ── Ring 3 — Mid Periphery: 7–30 days ago ────────────────────────
        const monthRaw = await store.getByAge(30, 7, 40);
        const month = Array.isArray(monthRaw) ? monthRaw : [];
        if (month.length > 0) {
            const origChars = originalChars(month);
            const compressed = await xrl.compressAsync(month, 3, budgets[3]);
            if (compressed.trim()) {
                sections.push(`[MID PERIPHERY — last month, deep compression]\n${compressed}`);
                const isLLM = compressed.includes('[MID-PERIPHERY-LLM]');
                ringStats.push({
                    ring: 3, label: 'MID-PERIPHERY', msgCount: month.length,
                    originalChars: origChars, compressedChars: compressed.length,
                    budgetTokens: budgets[3], actualTokens: xrl.estimateTokens(compressed),
                    compressionRatio: origChars > 0 ? 1 - (compressed.length / origChars) : 0,
                    method: isLLM ? 'llm-summary' : 'extractive'
                });
            }
        }

        // ── Ring 4 — Far Periphery: 30–365 days ago ──────────────────────
        const yearRaw = await store.getByAge(365, 30, 30);
        const year = Array.isArray(yearRaw) ? yearRaw : [];
        if (year.length > 0) {
            const origChars = originalChars(year);
            const compressed = xrl.compress(year, 4, budgets[4]);
            if (compressed.trim()) {
                sections.push(`[FAR PERIPHERY — last year, ultra compression (hash refs)]\n${compressed}`);
                ringStats.push({
                    ring: 4, label: 'FAR-PERIPHERY', msgCount: year.length,
                    originalChars: origChars, compressedChars: compressed.length,
                    budgetTokens: budgets[4], actualTokens: xrl.estimateTokens(compressed),
                    compressionRatio: origChars > 0 ? 1 - (compressed.length / origChars) : 0,
                    method: 'hash'
                });
            }
        }

        // ── Ring 5 — Outer Periphery: older than 1 year ──────────────────
        const deepRaw = await store.getByAge(9999, 365, 20);
        const deep = Array.isArray(deepRaw) ? deepRaw : [];
        if (deep.length > 0) {
            const origChars = originalChars(deep);
            const compressed = xrl.compress(deep, 5, budgets[5]);
            if (compressed.trim()) {
                sections.push(`[OUTER PERIPHERY — deep past, atomic hashes only]\n${compressed}`);
                ringStats.push({
                    ring: 5, label: 'OUTER-PERIPHERY', msgCount: deep.length,
                    originalChars: origChars, compressedChars: compressed.length,
                    budgetTokens: budgets[5], actualTokens: xrl.estimateTokens(compressed),
                    compressionRatio: origChars > 0 ? 1 - (compressed.length / origChars) : 0,
                    method: 'hash'
                });
            }
        }

    } catch (err) {
        console.error('[RingBuilder] Error building rings:', err.message);
    }

    // ── Ring Ω — Resonant Intuition from Connected Entities ───────────
    let omegaBlock = '';
    let omegaResonances = [];
    try {
        if (topicGraph) {
            const omega = await resonant.buildOmegaRing(
                store.workspaceId, topicGraph, store
            );
            omegaBlock = omega.block;
            omegaResonances = omega.resonances;
        }
    } catch (err) {
        console.error('[RingBuilder] Error building Omega ring:', err.message);
    }

    // ── Build stats summary ──────────────────────────────────────────────
    const totalOriginal = ringStats.reduce((n, r) => n + r.originalChars, 0);
    const totalCompressed = ringStats.reduce((n, r) => n + r.compressedChars, 0);
    const totalTokens = ringStats.reduce((n, r) => n + r.actualTokens, 0);
    const overallRatio = totalOriginal > 0 ? 1 - (totalCompressed / totalOriginal) : 0;

    // ── Tiered context budget ────────────────────────────────────────────
    // Refined: Ring 0 (Fovea) — tone-classified, ~1/3 adaptive, voice preserved
    // Minimally compressed: Ring 1 (Parafovea) — ~50%, still dense
    // Moderately compressed: Rings 2-3 (Near+Mid) — ~75-88%
    // Maximally compressed: Rings 4-5 (Far+Outer) — ~95-98%, hash refs
    const refined = ringStats.filter(r => r.ring === 0).reduce((n, r) => n + r.compressedChars, 0);
    const minimallyCompressed = ringStats.filter(r => r.ring === 1).reduce((n, r) => n + r.compressedChars, 0);
    const moderatelyCompressed = ringStats.filter(r => r.ring === 2 || r.ring === 3).reduce((n, r) => n + r.compressedChars, 0);
    const maximallyCompressed = ringStats.filter(r => r.ring === 4 || r.ring === 5).reduce((n, r) => n + r.compressedChars, 0);

    /** @type {RingStats} */
    const stats = {
        rings: ringStats,
        totalOriginalChars: totalOriginal,
        totalCompressedChars: totalCompressed,
        overallRatio,
        totalTokens,
        ringCount: ringStats.length,
        tiers: {
            refined,
            minimallyCompressed,
            moderatelyCompressed,
            maximallyCompressed,
            totalChars: refined + minimallyCompressed + moderatelyCompressed + maximallyCompressed
        }
    };

    if (sections.length === 0 && !omegaBlock) {
        _latestStats = stats;
        return { block: '', stats };
    }

    const block = [
        '━━━ FOVEATED MEMORY RINGS ━━━',
        ...sections,
        ...(omegaBlock ? [omegaBlock] : []),
        '━━━ END OF MEMORY RINGS ━━━'
    ].join('\n\n');

    _latestStats = stats;
    return { block, stats, omegaResonances };
}

/**
 * Remove ring entries matching specific XRL hashes or content snippets.
 * Used by the saccade engine to free tokens after a recall.
 *
 * @param {string} ringBlock - The current ring block string
 * @param {string[]} removePatterns - Strings/hashes to strip from the block
 * @returns {string} Updated ring block
 */
function removeFromRingBlock(ringBlock, removePatterns) {
    let updated = ringBlock;
    for (const pat of removePatterns) {
        // Remove any line containing this pattern
        const lines = updated.split('\n').filter(l => !l.includes(pat));
        updated = lines.join('\n');
    }
    return updated;
}

module.exports = { buildRingBlock, removeFromRingBlock, getRingStats };

// ── In-memory stats cache (latest ring stats for dashboard) ──────────────
let _latestStats = null;

/**
 * Get the most recent ring stats (for dashboard / API).
 * @returns {RingStats|null}
 */
function getRingStats() {
    return _latestStats;
}
