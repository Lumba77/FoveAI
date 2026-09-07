/**
 * ═══════════════════════════════════════════════════════
 * RING BUILDER — Foveated Memory Ring Block Generator
 * ═══════════════════════════════════════════════════════
 *
 * Builds the 6-ring foveated memory block that gets injected
 * into every context window at session start.
 *
 * Ring 0 (Fovea)         — 6 raw messages, 0% compression
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
// Also import compressFovea for smart fovea compression
const { compressFovea } = require('./xrl-compressor');

/**
 * Sort messages by importance score (highest first).
 * Messages without importance scores are placed at the end.
 * 
 * @param {Array} messages - Array of message objects with optional importance metadata
 * @returns {Array} Sorted messages
 */
function sortByImportance(messages) {
    return [...messages].sort((a, b) => {
        const importanceA = a.importance?.overall || 0;
        const importanceB = b.importance?.overall || 0;
        
        // Both have importance scores - sort descending
        if (importanceA > 0 && importanceB > 0) {
            return importanceB - importanceA;
        }
        
        // Only A has importance - A comes first
        if (importanceA > 0) return -1;
        
        // Only B has importance - B comes first  
        if (importanceB > 0) return 1;
        
        // Neither has importance - keep original order (most recent first)
        return 0;
    });
}

/**
 * Select top messages based on token budget estimation.
 * Prioritizes high-importance messages within the budget.
 * 
 * @param {Array} messages - Array of message objects (already sorted by importance)
 * @param {number} tokenBudget - Token budget for this ring
 * @returns {Array} Selected messages that fit within budget
 */
function selectTopByBudget(messages, tokenBudget) {
    if (messages.length === 0) return [];
    
    const selected = [];
    let usedTokens = 0;
    
    for (const msg of messages) {
        const msgTokens = msg.tokens_est || Math.ceil((msg.content?.length || 0) / 4);
        
        if (usedTokens + msgTokens <= tokenBudget) {
            selected.push(msg);
            usedTokens += msgTokens;
        } else {
            // Budget exceeded - stop adding messages
            break;
        }
    }
    
    return selected;
}

/**
 * Build the full foveated ring block string.
 *
 * @param {import('../memory/store').MemoryStore} store
 * @param {object} config - The proxy config object
 * @param {string} sessionId - Current session ID
 * @returns {string} The formatted ring block (ready for system prompt injection)
 */
async function buildRingBlock(store, config, sessionId) {
    // Steep compression gradient — optimized for 8K context window.
    // Total: ~2000 tokens for memory, leaving ~6000 for system prompt + conversation + response.
    //
    // Philosophy: few messages near-raw, then steeply compressed, then masses of headlines.
    // The outer rings are incredibly cheap (2-3 tokens/msg) so we give them more budget.
    // The model sees hundreds of headlines and uses <recall:> / <zoom:> to decompress.
    //
    // Ring    Budget  Compression  ~Tokens/msg  ~Messages fit
    // 0 Fovea    600   0-35%        40           4-6 msgs (smart trimmed, near-raw)
    // 1 24h      200   ~65%          8           ~25 msgs (first + last sentence)
    // 2 7d       300   ~85%          4           ~75 msgs (topic + first 8 words)
    // 3 30d      300   ~93%          3           ~100 msgs (topic + hash)
    // 4 1yr      300   ~97%          2           ~150 msgs (role:topic + hash)
    // 5 1yr+     200   ~99%          1.5         ~130 msgs (hash·topic)
    //                                                    Total: ~480 messages
    const budgets = config.ring_budgets || {
        0: 600,   // Fovea:      last 4-6 msgs, ~0-35% compression
        1: 200,   // Parafovea:  last 24h,      ~65% compression  → ~25 msgs
        2: 300,   // Near:       1-7 days,      ~85% compression  → ~75 msgs
        3: 300,   // Mid:        7-30 days,     ~93% compression  → ~100 msgs
        4: 300,   // Far:        30-365 days,   ~97% compression  → ~150 msgs
        5: 200,   // Outer:      1yr+,          ~99% compression  → ~130 msgs
    };

    const sections = [];

    try {
        // ── Task Board ───────────────────────────────────────────────────
        const tasks = await store.getTasks(sessionId);
        if (tasks && tasks.length > 0) {
            const pending = tasks.filter(t => !t.done);
            const done = tasks.filter(t => t.done);
            let taskBlock = `[T ${pending.length}/${done.length}]`;
            if (pending.length > 0) {
                taskBlock += '\n' + pending.map(t => `-${t.text}`).join('|');
            }
            if (done.length > 0) {
                taskBlock += '\n✓' + done.map(t => t.text).join('|');
            }
            sections.push(taskBlock);
        }

        // ── Ring 0 — Fovea: last N messages, smartly trimmed ─────────────
        // The fovea is never fully raw — it's lightly compressed to fit
        // a token budget. Below 65% compression there's no content
        // degradation, so we keep messages as close to raw as possible.
        const foveaCount = config.fovea_message_count || 6;
        const foveaBudget = config.fovea_token_budget || 800;
        const foveaMessages = await store.getRecent(foveaCount);
        const foveaIds = new Set(foveaMessages.map(m => m._id));

        if (foveaMessages.length > 0) {
            // Keep chronological order for fovea (not importance-sorted)
            // — recency matters more than importance in the fovea
            const compressed = compressFovea(foveaMessages, foveaBudget);
            sections.push(`[0 ${foveaMessages.length}]\n${compressed}`);
        }

        // ── Ring 1 — Parafovea: messages from last 24h not in fovea ──────
        // getByAge(1, 0) means "older than 1 day" — NOT what we want.
        // We want "within the last 1 day" = all recent messages minus fovea.
        // So we fetch a larger recent set and filter out fovea messages.
        const day1Raw = await store.getRecent(100);
        const day1 = Array.isArray(day1Raw) ? day1Raw.slice().reverse() : []; // newest last
        const day1Filtered = day1.filter(m => !foveaIds.has(m._id));
        if (day1Filtered.length > 0) {
            const sortedDay1 = sortByImportance(day1Filtered);
            const selectedDay1 = selectTopByBudget(sortedDay1, budgets[1]);
            if (selectedDay1.length > 0) {
                const compressed = xrl.compress(selectedDay1, 1, budgets[1]);
                if (compressed.trim()) {
                    sections.push(`[1 ${selectedDay1.length}/${day1Filtered.length}]\n${compressed}`);
                }
            }
        }

        // ── Ring 2 — Near Periphery: 1–7 days ago ────────────────────────
        const weekRaw = await store.getByAge(7, 1, 200);
        const week = Array.isArray(weekRaw) ? weekRaw : [];
        if (week.length > 0) {
            const sortedWeek = sortByImportance(week);
            const selectedWeek = selectTopByBudget(sortedWeek, budgets[2]);
            if (selectedWeek.length > 0) {
                const compressed = xrl.compress(selectedWeek, 2, budgets[2]);
                if (compressed.trim()) {
                    sections.push(`[2 ${selectedWeek.length}/${week.length}]\n${compressed}`);
                }
            }
        }

        // ── Ring 3 — Mid Periphery: 7–30 days ago ────────────────────────
        const monthRaw = await store.getByAge(30, 7, 300);
        const month = Array.isArray(monthRaw) ? monthRaw : [];
        if (month.length > 0) {
            const sortedMonth = sortByImportance(month);
            const selectedMonth = selectTopByBudget(sortedMonth, budgets[3]);
            if (selectedMonth.length > 0) {
                const compressed = xrl.compress(selectedMonth, 3, budgets[3]);
                if (compressed.trim()) {
                    sections.push(`[3 ${selectedMonth.length}/${month.length}]\n${compressed}`);
                }
            }
        }

        // ── Ring 4 — Far Periphery: 30–365 days ago ──────────────────────
        const yearRaw = await store.getByAge(365, 30, 500);
        const year = Array.isArray(yearRaw) ? yearRaw : [];
        if (year.length > 0) {
            const sortedYear = sortByImportance(year);
            const selectedYear = selectTopByBudget(sortedYear, budgets[4]);
            if (selectedYear.length > 0) {
                const compressed = xrl.compress(selectedYear, 4, budgets[4]);
                if (compressed.trim()) {
                    sections.push(`[4 ${selectedYear.length}/${year.length}]\n${compressed}`);
                }
            }
        }

        // ── Ring 5 — Outer Periphery: older than 1 year ──────────────────
        const deepRaw = await store.getByAge(9999, 365, 500);
        const deep = Array.isArray(deepRaw) ? deepRaw : [];
        if (deep.length > 0) {
            const sortedDeep = sortByImportance(deep);
            const selectedDeep = selectTopByBudget(sortedDeep, budgets[5]);
            if (selectedDeep.length > 0) {
                const compressed = xrl.compress(selectedDeep, 5, budgets[5]);
                if (compressed.trim()) {
                    sections.push(`[5 ${selectedDeep.length}/${deep.length}]\n${compressed}`);
                }
            }
        }

    } catch (err) {
        console.error('[RingBuilder] Error building rings:', err.message);
    }

    if (sections.length === 0) return '';

    // Compressed format: [MEM] sections... [/MEM] with minimal whitespace
    const block = '[MEM]\n' + sections.join('\n') + '\n[/MEM]';

    return block;
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

module.exports = { buildRingBlock, removeFromRingBlock };
