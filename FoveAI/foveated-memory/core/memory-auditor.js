/**
 * ═══════════════════════════════════════════════════════
 * MEMORY AUDITOR — Safety Net for Misclassified Memories
 * ═══════════════════════════════════════════════════════
 *
 * The importance scorer is heuristic-first, which means it can
 * misclassify critical messages as filler. This module periodically
 * scans the shadow context for messages that:
 *
 *   1. Were scored low (overall ≤ 3) but contain high-value signals
 *   2. Were never scored at all (old messages from before the system)
 *   3. Have been accessed via <recall:> or <zoom:> but were hard to find
 *
 * For each suspicious message, it:
 *   - Re-scores with the LLM (Tier 2)
 *   - Updates the stored importance
 *   - Logs the correction for transparency
 *
 * The audit runs:
 *   - On startup (scans last 200 messages)
 *   - Every N messages (configurable, default 50)
 *   - On demand via /api/audit endpoint
 *
 * This is the safety net that makes the system production-ready.
 * Even if the heuristic scorer gets it wrong, the audit catches it.
 */

'use strict';

const { scoreHeuristic, scoreLLM } = require('./importance-scorer');

// ── High-value signal patterns that heuristic might miss ───────────────────
// These are patterns that indicate a message is important EVEN IF the
// heuristic scorer gave it a low score. The audit flags these for re-scoring.

const SUSPICIOUS_PATTERNS = [
    // Technical decisions that don't use obvious keywords
    { pattern: /\b(?:because|since|reason|why|rationale|justification)\b/gi, reason: 'reasoning_language' },
    { pattern: /\b(?:hypothesis|theory|assumption|premise|conjecture)\b/gi, reason: 'scientific_language' },
    { pattern: /\b(?:result|outcome|finding|discovery|breakthrough)\b/gi, reason: 'result_language' },
    { pattern: /\b(?:important|critical|crucial|essential|vital|key)\b/gi, reason: 'importance_language' },
    { pattern: /\b(?:remember|note|record|document|log)\b/gi, reason: 'memory_language' },
    { pattern: /\b(?:first time|last time|only|unique|rare|never before)\b/gi, reason: 'uniqueness_language' },
    // Long messages are more likely to contain important content
    { pattern: /.{200,}/gs, reason: 'long_message' },
    // Messages with numbers/data
    { pattern: /\b\d+[.,]?\d*\s*(?:percent|%\|mg|ml|kg|degrees|hours|minutes|days|weeks|months|years)\b/gi, reason: 'quantitative_data' },
];

/**
 * Check if a message is "suspicious" — scored low but might be important.
 *
 * @param {object} msg - Stored message with importance
 * @returns {object|null} { reason } if suspicious, null otherwise
 */
function isSuspicious(msg) {
    const overall = msg.importance?.overall || 0;

    // Only flag messages scored low (or not scored at all)
    if (overall > 3) return null;

    const content = msg.content || '';
    if (content.length < 10) return null;

    for (const { pattern, reason } of SUSPICIOUS_PATTERNS) {
        if (pattern.test(content)) {
            return { reason };
        }
    }

    return null;
}

/**
 * Run an audit pass on the memory store.
 *
 * Scans recent messages, finds suspicious ones, re-scores them with the LLM.
 *
 * @param {object} store - MemoryStore instance
 * @param {object} opts - { limit, llmUrl, model, dryRun }
 * @returns {Promise<object>} Audit report
 */
async function runAudit(store, opts = {}) {
    const limit = opts.limit || 200;
    const dryRun = opts.dryRun || false;

    console.log(`[MemoryAudit] 🔍 Scanning last ${limit} messages for misclassifications...`);

    const messages = await store.getRecent(limit);
    const suspicious = [];
    const corrected = [];
    const stats = {
        scanned: messages.length,
        suspicious: 0,
        corrected: 0,
        upgrades: 0,
        downgrades: 0,
        unchanged: 0,
    };

    for (const msg of messages) {
        const suspicion = isSuspicious(msg);
        if (!suspicion) continue;

        stats.suspicious++;
        suspicious.push({
            id: msg._id,
            content: (msg.content || '').slice(0, 80),
            currentScore: msg.importance?.overall || 0,
            reason: suspicion.reason,
        });

        if (dryRun) continue;

        // Re-score with LLM
        const oldScore = msg.importance?.overall || 0;
        const refined = await scoreLLM(msg.content || '', msg.role || 'user', {
            heuristicScore: msg.importance || scoreHeuristic(msg.content || '', msg.role),
            llmUrl: opts.llmUrl,
            model: opts.model,
        });

        if (refined) {
            const newScore = refined.overall;
            stats.corrected++;

            if (newScore > oldScore + 1) {
                stats.upgrades++;
                console.log(`[MemoryAudit] ⬆️  Upgraded: ${oldScore}→${newScore} (${refined.strategy}) — "${(msg.content || '').slice(0, 50)}..."`);
            } else if (newScore < oldScore - 1) {
                stats.downgrades++;
                console.log(`[MemoryAudit] ⬇️  Downgraded: ${oldScore}→${newScore} — "${(msg.content || '').slice(0, 50)}..."`);
            } else {
                stats.unchanged++;
            }

            // Update the stored message
            if (newScore !== oldScore) {
                try {
                    await store.updateImportance(msg.session_id, msg.content, refined);
                    corrected.push({
                        id: msg._id,
                        oldScore,
                        newScore,
                        strategy: refined.strategy,
                    });
                } catch (e) {
                    console.warn(`[MemoryAudit] Failed to update: ${e.message}`);
                }
            }
        }
    }

    const report = {
        timestamp: new Date().toISOString(),
        stats,
        suspicious: suspicious.slice(0, 20),  // first 20 for display
        corrected: corrected.slice(0, 20),
    };

    console.log(`[MemoryAudit] ✅ Done: ${stats.scanned} scanned, ${stats.suspicious} suspicious, ${stats.corrected} corrected (${stats.upgrades} upgrades, ${stats.downgrades} downgrades)`);

    return report;
}

// ── Auto-audit scheduler ───────────────────────────────────────────────────

let auditInterval = null;
let messageCounter = 0;
const AUDIT_EVERY_N_MESSAGES = parseInt(process.env.XRLF_AUDIT_EVERY_N || '50', 10);

/**
 * Increment the message counter and trigger audit if threshold reached.
 * Called after each conversation turn.
 *
 * @param {object} store - MemoryStore instance
 */
function tick(store) {
    messageCounter++;
    if (messageCounter >= AUDIT_EVERY_N_MESSAGES) {
        messageCounter = 0;
        // Fire async — don't block the response
        runAudit(store, { limit: 100 }).catch(e => {
            console.warn(`[MemoryAudit] Auto-audit failed: ${e.message}`);
        });
    }
}

/**
 * Start the auto-audit scheduler.
 * Runs an initial audit on startup, then ticks with each message.
 *
 * @param {object} store - MemoryStore instance
 */
function startAutoAudit(store) {
    if (process.env.XRLF_MEMORY_AUDIT === '0' || process.env.XRLF_MEMORY_AUDIT === 'false') {
        console.log('[MemoryAudit] Disabled (XRLF_MEMORY_AUDIT=false)');
        return;
    }

    console.log(`[MemoryAudit] 🛡️  Auto-audit enabled (every ${AUDIT_EVERY_N_MESSAGES} messages)`);

    // Run initial audit after 10 seconds (let the system stabilize)
    setTimeout(() => {
        runAudit(store, { limit: 200 }).catch(e => {
            console.warn(`[MemoryAudit] Startup audit failed: ${e.message}`);
        });
    }, 10000);
}

module.exports = { runAudit, isSuspicious, tick, startAutoAudit };
