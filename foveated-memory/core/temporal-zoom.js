/**
 * ═══════════════════════════════════════════════════════
 * TEMPORAL ZOOM — Secondary Fovea for Past Time Periods
 * ═══════════════════════════════════════════════════════
 *
 * When the model emits <temporal_zoom: "phrase or date">, this module:
 *   1. Parses the query (semantic phrase, date, or relative time)
 *   2. Searches the memory store for matching messages
 *   3. Builds a mini ring block for just that time period
 *   4. Returns an injection system message
 *
 * This is like pointing a second fovea at any point in the past.
 * The model gets a focused, compressed view of that time period
 * and can then <recall:> or <zoom:> for full fidelity within it.
 *
 * Query formats:
 *   <temporal_zoom: "Japan trip">        → semantic search
 *   <temporal_zoom: "2026-03">           → month-wide zoom
 *   <temporal_zoom: "2026-03-15">        → day-wide zoom
 *   <temporal_zoom: "last week">         → relative time
 *   <temporal_zoom: "last month">        → relative time
 */

'use strict';

const { compress, compressFovea, estimateTokens } = require('./xrl-compressor');
const { summarizeWithImportance } = require('./importance-scorer');

// ── Query Parsing ───────────────────────────────────────────────────────────

/**
 * Parse a temporal zoom query into a search strategy.
 * @param {string} query
 * @returns {object} { type, value } where type is 'phrase' | 'date' | 'relative'
 */
function parseTemporalQuery(query) {
    const trimmed = query.trim().toLowerCase();

    // Date patterns: YYYY-MM, YYYY-MM-DD
    const monthMatch = trimmed.match(/^(\d{4})-(\d{1,2})$/);
    if (monthMatch) {
        const year = parseInt(monthMatch[1]);
        const month = parseInt(monthMatch[2]);
        const start = new Date(year, month - 1, 1);
        const end = new Date(year, month, 0, 23, 59, 59);
        return { type: 'date_range', start: start.getTime(), end: end.getTime(), label: `${year}-${String(month).padStart(2, '0')}` };
    }

    const dayMatch = trimmed.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
    if (dayMatch) {
        const year = parseInt(dayMatch[1]);
        const month = parseInt(dayMatch[2]);
        const day = parseInt(dayMatch[3]);
        const start = new Date(year, month - 1, day, 0, 0, 0);
        const end = new Date(year, month - 1, day, 23, 59, 59);
        return { type: 'date_range', start: start.getTime(), end: end.getTime(), label: `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}` };
    }

    // Relative time patterns
    const relativePatterns = [
        { regex: /last\s+week|past\s+week/, days: 7, label: 'last week' },
        { regex: /last\s+month|past\s+month/, days: 30, label: 'last month' },
        { regex: /last\s+year|past\s+year/, days: 365, label: 'last year' },
        { regex: /yesterday/, days: 1, label: 'yesterday' },
        { regex: /last\s+few\s+days|recent\s+days/, days: 3, label: 'last few days' },
    ];

    for (const pat of relativePatterns) {
        if (pat.regex.test(trimmed)) {
            const end = Date.now();
            const start = end - pat.days * 86400000;
            return { type: 'date_range', start, end, label: pat.label };
        }
    }

    // Default: semantic phrase search
    return { type: 'phrase', value: query.trim(), label: query.trim() };
}

// ── Mini Ring Builder ───────────────────────────────────────────────────────

/**
 * Build a mini ring block for a set of messages from a specific time period.
 * This is a secondary fovea — a focused, compressed view of that period.
 *
 * Structure:
 *   [TEMPORAL ZOOM: "label"]
 *   [FOCUS 4] — 4 most recent messages in the period, near-raw (compressFovea)
 *   [CONTEXT N] — remaining messages, compressed at level 2 (~85%)
 *
 * @param {Array} messages - Messages from the target time period
 * @param {string} label - Human-readable label for the period
 * @param {number} tokenBudget - Max tokens for the injection (default 1500)
 * @returns {string} Formatted temporal zoom block
 */
function buildTemporalZoomBlock(messages, label, tokenBudget = 1500) {
    if (!messages || messages.length === 0) {
        return `[TEMPORAL ZOOM: "${label}"]\nNo memories found for this period.`;
    }

    // Sort by timestamp (oldest first)
    const sorted = messages.slice().sort((a, b) => {
        const ta = a.timestamp ? new Date(a.timestamp).getTime() : 0;
        const tb = b.timestamp ? new Date(b.timestamp).getTime() : 0;
        return ta - tb;
    });

    const total = sorted.length;
    const sections = [];

    // Focus section: last 4 messages in the period, near-raw
    const focusCount = Math.min(4, total);
    const focusMessages = sorted.slice(-focusCount);
    const focusBudget = Math.min(600, tokenBudget * 0.4);
    const focusBlock = compressFovea(focusMessages, focusBudget);
    sections.push(`[FOCUS ${focusCount}]`);
    sections.push(focusBlock);

    // Context section: remaining messages, compressed at level 2 (~85%)
    if (total > focusCount) {
        const contextMessages = sorted.slice(0, -focusCount);
        const contextBudget = tokenBudget - estimateTokens(focusBlock) - 50; // reserve 50 for headers
        if (contextBudget > 20 && contextMessages.length > 0) {
            const contextBlock = compress(contextMessages, 2, contextBudget);
            if (contextBlock.trim()) {
                sections.push(`[CONTEXT ${contextMessages.length}]`);
                sections.push(contextBlock);
            }
        }
    }

    const header = `[TEMPORAL ZOOM: "${label}" — ${total} memories]`;
    return header + '\n' + sections.join('\n');
}

// ── Main Handler ────────────────────────────────────────────────────────────

/**
 * Handle a temporal zoom request.
 *
 * @param {object} store - MemoryStore instance
 * @param {string} query - The temporal zoom query
 * @param {number} tokenBudget - Max tokens for injection
 * @returns {Promise<object>} { injection: { role, content }, stats }
 */
async function handleTemporalZoom(store, query, tokenBudget = 1500) {
    const parsed = parseTemporalQuery(query);
    let messages = [];
    let searchInfo = '';

    if (parsed.type === 'date_range') {
        // Date range query — get all messages in that range
        const all = await store.getRecent(1000);
        messages = all.filter(m => {
            if (!m.timestamp) return false;
            const ts = new Date(m.timestamp).getTime();
            return ts >= parsed.start && ts <= parsed.end;
        });
        searchInfo = `date range ${parsed.label} (${parsed.start} to ${parsed.end})`;
    } else {
        // Semantic phrase search — use the store's TF-IDF search
        const results = await store.search(parsed.value, 50);
        messages = results.map(r => r.message);
        searchInfo = `phrase "${parsed.value}"`;
    }

    console.log(`[TemporalZoom] 📅 Query: "${query}" | parsed: ${searchInfo} | found: ${messages.length} messages`);

    // Build the compressed ring block for this time period
    const block = buildTemporalZoomBlock(messages, parsed.label, tokenBudget);
    const tokens = estimateTokens(block);

    // Tier 3: LLM-powered importance summarization (if enabled and enough messages)
    let llmSummary = '';
    let glowingStars = [];
    if (process.env.XRLF_LLM_IMPORTANCE !== '0' && process.env.XRLF_LLM_IMPORTANCE !== 'false' && messages.length >= 3) {
        try {
            const result = await summarizeWithImportance(messages, query, { tokenBudget });
            llmSummary = result.summary;
            glowingStars = result.glowingStars;
            console.log(`[TemporalZoom] 🧠 LLM summary: ${llmSummary.slice(0, 80)}... | ${glowingStars.length} glowing stars`);
        } catch (e) {
            // Fall back to heuristic-only
        }
    }

    // Build final injection: LLM summary + compressed block
    let finalContent = block;
    if (llmSummary) {
        finalContent = `[SUMMARY] ${llmSummary}\n\n${block}`;
        if (glowingStars.length > 0) {
            finalContent += `\n[GLOWING STARS — decompress these for full fidelity: ${glowingStars.map(i => `#${i}`).join(', ')}]`;
        }
    }

    return {
        injection: {
            role: 'system',
            content: finalContent,
        },
        stats: {
            query,
            parsed: searchInfo,
            messagesFound: messages.length,
            tokensInjected: estimateTokens(finalContent),
            llmSummary: !!llmSummary,
            glowingStars: glowingStars.length,
        },
    };
}

module.exports = { parseTemporalQuery, buildTemporalZoomBlock, handleTemporalZoom };
