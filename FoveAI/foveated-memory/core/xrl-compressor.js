/**
 * ═══════════════════════════════════════════════════════
 * XRL COMPRESSOR — Foveated Memory Ring Compression
 * ═══════════════════════════════════════════════════════
 *
 * Compresses conversation turns at 6 levels of fidelity,
 * matching the gradient from fovea (raw) to outer periphery (atomic).
 *
 * Level 0 — Raw (0% compression)    — verbatim messages
 * Level 1 — Light (~50%)            — key phrases + outcome
 * Level 2 — Medium (~75%)           — topic + key fact only
 * Level 3 — Deep (~88%)             — topic + timestamp + one-liner
 * Level 4 — Ultra (~95%)            — topic label + XRL hash ref
 * Level 5 — Atomic (~98%)           — pure XRL hash only
 */

'use strict';

const crypto = require('crypto');
const { determineStrategy, strategyCompressionRatio } = require('./importance-scorer');

/**
 * Generate a short XRL hash for a message block.
 * Format: xrl://mem/<4-char-hash>
 */
function xrlHash(text) {
    const h = crypto.createHash('md5').update(text).digest('hex').slice(0, 4);
    return `xrl://mem/${h}`;
}

/**
 * Extract the dominant topic from a message using simple heuristics.
 * In a future phase, this can be replaced with an LLM call.
 */
function extractTopic(text, maxWords = 6) {
    // Strip common filler words
    const stopWords = new Set([
        'the','a','an','is','it','in','on','at','to','of','and','or',
        'for','with','this','that','was','are','be','as','we','i','you',
        'have','had','has','do','did','not','but','so','if','by','can',
        'will','just','from','they','he','she','also','been','what','how'
    ]);
    const words = text.toLowerCase()
        .replace(/[^a-z0-9\s\-]/g, ' ')
        .split(/\s+/)
        .filter(w => w.length > 2 && !stopWords.has(w));

    // Deduplicate and take first N
    const seen = new Set();
    const unique = [];
    for (const w of words) {
        if (!seen.has(w)) { seen.add(w); unique.push(w); }
        if (unique.length >= maxWords) break;
    }
    return unique.join(' ') || text.slice(0, 40);
}

/**
 * Compress a set of messages at the given level.
 * Messages is an array of { role, content, timestamp, id } objects.
 * Returns a formatted string block ready for injection into a prompt.
 */
function compress(messages, level, tokenBudget = 999) {
    if (!messages || messages.length === 0) return '';

    const lines = [];
    let approxTokens = 0;

    // For levels 3-5, we batch multiple messages per line to save metadata overhead.
    // This is critical for short messages where the hash+topic costs more than the content.
    const batchSize = level >= 5 ? 5 : (level >= 4 ? 4 : (level === 3 ? 3 : 1));

    for (let batchStart = 0; batchStart < messages.length; batchStart += batchSize) {
        if (approxTokens >= tokenBudget) break;

        const batch = messages.slice(batchStart, batchStart + batchSize);
        const batchParts = [];

        for (const msg of batch) {
            const ts = msg.timestamp
                ? new Date(msg.timestamp).toISOString().slice(0, 10)
                : 'unknown';
            const role = (msg.role || 'unknown').toUpperCase();

            // ── Importance-aware compression ───────────────────────────────
            // Each message has its own preservation strategy based on its importance.
            // A "crystalline" message (overall ≥ 9) resists compression — it gets
            // treated as if it's in a closer ring. An "aggressive" message (overall ≤ 2)
            // compresses harder — it gets treated as if it's in a further ring.
            //
            // Gradient: crystalline gets -2 in near rings (stays near-raw) but only -1
            // in outer rings (still compresses, just less than balanced). This keeps
            // glowing stars recognizable in outer rings without eating too much budget.
            const msgStrategy = msg.importance?.strategy || 'balanced';
            const ratio = strategyCompressionRatio(msgStrategy, level);
            // Adjust the effective level based on the ratio and ring depth:
            //   crystalline at ring 1 → ratio 0.60 → effective level -2 (near-raw)
            //   crystalline at ring 4 → ratio 0.15 → effective level -1 (compressed but less)
            //   aggressive at ring 1 → ratio 0.10 → effective level +1 (fast evaporation)
            let effectiveLevel = level;
            if (ratio > 0.5) effectiveLevel = Math.max(0, level - 2);       // crystalline in near rings
            else if (ratio > 0.2) effectiveLevel = Math.max(0, level - 1);  // crystalline in mid rings, tone-first in near
            else if (ratio < 0.05) effectiveLevel = Math.min(5, level + 1); // aggressive: fast evaporation
            // Clamp to valid range
            effectiveLevel = Math.max(0, Math.min(5, effectiveLevel));
            const rawContent = msg.content || '';
            const content = (Array.isArray(rawContent)
                ? rawContent.filter(p => p && typeof p.text === 'string').map(p => p.text).join('\n')
                : String(rawContent)
            ).trim();
            const hash = xrlHash(content);

            let line = '';

            switch (effectiveLevel) {
                case 0:
                    // Raw — verbatim (used as fallback; fovea uses compressFovea instead)
                    line = `[${ts}] ${role}: ${content}`;
                    break;

                case 1:
                    // Steep light (~65% compression) — first sentence + last sentence only
                    {
                        const sentences = content.split(/(?<=[.!?])\s+/).filter(s => s.trim());
                        if (sentences.length <= 2) {
                            line = `${role}: ${content.slice(0, 100)}${content.length > 100 ? '…' : ''}`;
                        } else {
                            const first = sentences[0].trim().slice(0, 80);
                            const last = sentences[sentences.length - 1].trim().slice(0, 60);
                            line = `${role}: ${first} […] ${last}`;
                        }
                    }
                    break;

                case 2:
                    // Steep medium (~85% compression) — topic + first 6 words
                    {
                        const topic = extractTopic(content, 3);
                        const firstWords = content.split(/\s+/).slice(0, 6).join(' ');
                        line = `${topic}:${firstWords}`;
                    }
                    break;

                case 3:
                    // Steep deep (~93% compression) — topic + hash only
                    {
                        const topic = extractTopic(content, 2);
                        line = `${topic}·${hash.slice(-4)}`;
                    }
                    break;

                case 4:
                    // Ultra (~97% compression) — topic word + short hash
                    {
                        const topic = extractTopic(content, 1);
                        line = `${topic}·${hash.slice(-4)}`;
                    }
                    break;

                case 5:
                    // Atomic (~99% compression) — 3-char hash + 1 topic word, packed 5 per line
                    {
                        const topic = extractTopic(content, 1);
                        line = `${hash.slice(-3)}${topic}`;
                    }
                    break;

                default:
                    line = `${role}: ${content.slice(0, 80)}`;
            }

            batchParts.push(line);
        }

        // Join batch parts with | separator
        const batchLine = batchParts.join(' | ');
        const tokenEst = Math.ceil(batchLine.length / 4);
        if (approxTokens + tokenEst > tokenBudget) break;

        lines.push(batchLine);
        approxTokens += tokenEst;
    }

    return lines.join('\n');
}

/**
 * Estimate token count for a string (rough: 1 token ≈ 4 chars).
 */
function estimateTokens(text) {
    return Math.ceil((text || '').length / 4);
}

/**
 * Split text into sentences.
 */
function splitSentences(text) {
    return text
        .replace(/\s+/g, ' ')
        .split(/(?<=[.!?])\s+/)
        .map(s => s.trim())
        .filter(s => s.length > 0);
}

/**
 * Smart fovea compression — keeps messages as close to raw as possible
 * while fitting within a token budget. Never drops a message entirely.
 *
 * Strategy:
 * 1. Calculate per-message budget (totalBudget / messageCount)
 * 2. If a message fits raw, keep it raw
 * 3. If it exceeds its share, apply sentence-level trimming:
 *    - Keep first sentence (context setup)
 *    - Keep last sentence (conclusion/answer)
 *    - Fill remaining space with middle sentences (most important first)
 * 4. Stay below 65% compression (keep at least 35% of original content)
 *
 * @param {Array} messages - Array of message objects
 * @param {number} tokenBudget - Total token budget for all fovea messages
 * @returns {string} Formatted fovea block
 */
function compressFovea(messages, tokenBudget = 800) {
    if (!messages || messages.length === 0) return '';

    const n = messages.length;
    // Reserve ~10% for metadata (timestamps, role labels, brackets)
    const contentBudget = Math.floor(tokenBudget * 0.9);
    const perMessageBudget = Math.floor(contentBudget / n);

    const lines = [];
    let totalUsed = 0;

    for (const msg of messages) {
        const ts = msg.timestamp
            ? new Date(msg.timestamp).toISOString().slice(0, 10)
            : 'unknown';
        const role = (msg.role || 'unknown').toUpperCase();
        const rawContent = msg.content || '';
        const content = (Array.isArray(rawContent)
            ? rawContent.filter(p => p && typeof p.text === 'string').map(p => p.text).join('\n')
            : String(rawContent)
        ).trim();

        if (!content) continue;

        const prefix = `[${ts}] ${role}: `;
        const prefixTokens = estimateTokens(prefix);
        const msgContentBudget = perMessageBudget - prefixTokens;

        if (msgContentBudget <= 0) {
            // Extremely tight budget — just keep a one-liner
            const trimmed = content.slice(0, 60);
            lines.push(`${prefix}${trimmed}…`);
            continue;
        }

        const rawTokens = estimateTokens(content);

        if (rawTokens <= msgContentBudget) {
            // Fits raw — no compression needed
            lines.push(`${prefix}${content}`);
            totalUsed += rawTokens + prefixTokens;
        } else {
            // Need to trim — use sentence-level extraction
            const sentences = splitSentences(content);
            const targetChars = msgContentBudget * 4; // tokens → chars
            const maxCompression = 0.65; // Keep at least 35% of original
            const minChars = Math.ceil(content.length * (1 - maxCompression));
            const charBudget = Math.max(targetChars, minChars);

            if (sentences.length <= 1) {
                // Single long sentence — truncate at char boundary
                const trimmed = content.slice(0, charBudget);
                lines.push(`${prefix}${trimmed}${content.length > charBudget ? ' […]' : ''}`);
            } else {
                // Multi-sentence: keep first + last + fill middle
                const parts = [];
                let used = 0;

                // Always keep first sentence
                const first = sentences[0];
                parts.push(first);
                used += first.length;

                // Always keep last sentence (if different from first)
                const last = sentences[sentences.length - 1];
                if (sentences.length > 1) {
                    parts.push(last);
                    used += last.length;
                }

                // Fill with middle sentences (skip first and last)
                const middle = sentences.slice(1, -1);
                for (const s of middle) {
                    if (used + s.length > charBudget) break;
                    parts.push(s);
                    used += s.length;
                }

                // Reassemble in original order
                const result = [parts[0]];
                const middleParts = parts.slice(1, -1).sort((a, b) => {
                    // Keep middle in original order
                    return middle.indexOf(a) - middle.indexOf(b);
                });
                if (middleParts.length > 0 && middleParts[0] !== parts[0]) {
                    result.push(...middleParts);
                }
                if (parts.length > 1 && parts[parts.length - 1] !== parts[0]) {
                    // Ensure last is actually last
                    const lastPart = parts[parts.length - 1];
                    if (!result.includes(lastPart)) {
                        result.push(lastPart);
                    }
                }

                const trimmed = result.filter((s, i, arr) => arr.indexOf(s) === i).join(' ');
                const compressionRatio = 1 - (trimmed.length / content.length);
                lines.push(`${prefix}${trimmed}${compressionRatio > 0.3 ? ' […]' : ''}`);
            }
            totalUsed += estimateTokens(lines[lines.length - 1]);
        }
    }

    return lines.join('\n');
}

module.exports = { compress, compressFovea, xrlHash, extractTopic, estimateTokens };
