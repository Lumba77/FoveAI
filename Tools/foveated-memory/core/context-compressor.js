/**
 * ═══════════════════════════════════════════════════════
 * XRL CONTEXT CHECKPOINTER
 * ═══════════════════════════════════════════════════════
 *
 * Compresses old conversation turns into dense XRL-hashed
 * checkpoints using local Ollama — zero cloud tokens burned.
 *
 * Strategy:
 *  - Keep last KEEP_RECENT turns verbatim (recent context)
 *  - Every COMPRESS_EVERY turns, summarize the oldest batch
 *  - Replace with a [CKP:hash] token block (~40-80 tokens)
 *  - Net reduction: 80-90% on 20+ turn sessions
 *
 * IMPORTANT: The compression level is now driven by the UNIFIED
 * resolution scale (0-5) from ./resolution.js, NOT the old inverted
 * 1-5 aggression map. Level 0 = 65% baseline (guaranteed floor),
 * level 5 = max compression. This keeps the checkpoint compressor
 * synchronized with the ring-builder multiplier and the advertised
 * context window so models never lose the connective tissue.
 */

'use strict';

const crypto = require('crypto');
const fs     = require('fs');
const path   = require('path');
const fetch  = require('node-fetch');
const resolution = require('./resolution');
const { refineMessageAsync } = require('./xrl-compressor');

// ── Config ──────────────────────────────────────────────────────────────────

// Target ~10x reduction (e.g. 80K -> 8K) instead of ~100x, which destroys context.
// Tune with env vars without editing code.
const COMPRESS_EVERY  = parseInt(process.env.FOVEA_COMPRESS_EVERY,  10) || 6;
const FOVEA_WINDOW    = parseInt(process.env.FOVEA_WINDOW,          10) || 4;
const SUMMARY_MAX_TOKENS = parseInt(process.env.FOVEA_SUMMARY_TOKENS, 10) || 300;
const LM_STUDIO_URL   = process.env.LM_STUDIO_URL || 'http://127.0.0.1:7272';
const CHECKPOINT_DIR  = path.join(__dirname, '..', 'memory_data', 'checkpoints');

// ── Token-Based Triggering ─────────────────────────────────────────────────
// Only compress when estimated tokens exceed TOKEN_BUDGET_PCT of the real context window.
// Default: 80% of 32768 = ~26214 tokens. Prevents premature/aggressive compression.
const TOKEN_BUDGET_PCT = parseFloat(process.env.FOVEA_TOKEN_BUDGET_PCT || '0.80');
const REAL_CTX_WINDOW  = parseInt(process.env.LUMAX_CLOUD_MAX_TOKENS_CAP || process.env.LUMAX_LOCAL_N_CTX || '32768', 10);
const TOKEN_BUDGET      = Math.floor(REAL_CTX_WINDOW * TOKEN_BUDGET_PCT);

// ── Foveal Window Token Cap ─────────────────────────────────────────────
// The recent (verbatim) turns are "pure context" — but they MUST be confined
// to a hard token budget so no single message can flood the context window.
// Oversized foveal messages are passed through the LLM refinement pipeline
// (LM Studio), which identifies and strips filler — "air between words" —
// while preserving tone, decisions, file refs, and key facts. This makes the
// foveal window mathematically bounded, not arbitrary.
const FOVEA_MAX_TOKENS = parseInt(process.env.FOVEA_MAX_TOKENS, 10) || 6000;
const FOVEA_REFINE_THRESHOLD_CHARS = parseInt(process.env.FOVEA_REFINE_THRESHOLD_CHARS, 10) || 400;

// ── Anchor Protection ──────────────────────────────────────────────────────
// Patterns that identify "connective tissue" — messages that must stay verbatim.
// If a message matches any of these, it is NEVER compressed into a checkpoint.
const ANCHOR_PATTERNS = [
    /#+\s*Todo\s*List/i,           // Todo lists
    /#+\s*SOP\b/i,                 // Standard Operating Procedure markers
    /#+\s*Current\s+Goal/i,        // Current goal statements
    /#+\s*Plan\s+of\s+Action/i,    // Plan of action headers
    /DECISIONS?\s*:/i,             // Decision blocks
    /STATUS\s*:\s*(solved|pending|in-progress)/i,  // Status markers
    /\[MEMORY\s+RECALLED/i,        // Memory recall injections
    /\[CKP:/i,                     // Existing checkpoint blocks (don't re-compress)
    /<recall:\s*"[^"]+">/i,        // Active recall tokens
    /<thinking>.*?<\/thinking>/i,  // Thinking blocks
    /```[\s\S]*?```/i,             // Code blocks (preserve structure)
];

/**
 * Check if a message is an "anchor" — critical connective tissue that must
 * never be compressed away. Anchors are preserved verbatim in the context.
 */
function isAnchorMessage(msg) {
    if (!msg || !msg.content) return false;
    // System messages (custom instructions, environment details) are NEVER
    // "connective tissue" — they are massive context blobs that must be
    // eligible for compression. Only user/assistant messages can be anchors.
    if (msg.role === 'system') return false;
    const content = typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content);
    return ANCHOR_PATTERNS.some(pattern => pattern.test(content));
}

/**
 * Rough token estimator: ~4 chars per token for English text, ~3 for code.
 * Conservative estimate to avoid underestimating.
 */
function estimateTokens(messages) {
    let total = 0;
    for (const msg of messages) {
        const content = typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content || '');
        // ~3.5 chars per token (conservative, between code and prose)
        total += Math.ceil(content.length / 3.5);
    }
    return total;
}

// Ensure checkpoint dir exists
if (!fs.existsSync(CHECKPOINT_DIR)) fs.mkdirSync(CHECKPOINT_DIR, { recursive: true });

// ── Helpers ──────────────────────────────────────────────────────────────────

function hashContent(text) {
    return crypto.createHash('sha256').update(text).digest('hex').slice(0, 6);
}

function saveCheckpoint(hash, data) {
    const file = path.join(CHECKPOINT_DIR, `${hash}.json`);
    fs.writeFileSync(file, JSON.stringify(data, null, 2));
}

function loadCheckpoint(hash) {
    const file = path.join(CHECKPOINT_DIR, `${hash}.json`);
    if (!fs.existsSync(file)) return null;
    return JSON.parse(fs.readFileSync(file, 'utf8'));
}

// ── LM Studio Summarizer ─────────────────────────────────────────────────────

async function summarizeWithLMStudio(messages) {
    const turns = messages.map(m =>
        `${m.role.toUpperCase()}: ${typeof m.content === 'string' ? m.content : JSON.stringify(m.content)}`
    ).join('\n\n');

    try {
        const COMPRESS_MODEL = process.env.LUMAX_COMPRESSOR_MODEL || process.env.LUMAX_TITLE_KEYWORD_MODEL || process.env.LUMAX_MIDDLEMAN_MODEL || process.env.LOCAL_LLM_MODEL || process.env.LUMAX_MODEL_LOCAL_ID || 'qwen3.5-4b-abliterated';
        const res = await fetch(`${LM_STUDIO_URL}/v1/chat/completions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model: COMPRESS_MODEL,
                messages: [
                    { role: 'system', content: 'You are a conversation checkpoint encoder. Preserve decisions, files, status, and key facts. Be concise but informative.' },
                    { role: 'user', content:
`Compress these conversation turns into a checkpoint of max ${SUMMARY_MAX_TOKENS} tokens.

Format EXACTLY:
DECISIONS: <key decisions/conclusions>
FILES: <files created/modified, or "none">
STATUS: <solved|pending|in-progress>
CONTEXT: <critical facts next agent must know>

Conversation:
${turns}

CHECKPOINT:`
                    }
                ],
                max_tokens: Math.max(100, SUMMARY_MAX_TOKENS + 50),
                temperature: 0.1,
                stream: false
            }),
            signal: (() => { const c = new AbortController(); setTimeout(() => c.abort(), 20000); return c.signal; })()
        });

        if (!res.ok) throw new Error(`LM Studio ${res.status}: ${await res.text()}`);
        const data = await res.json();
        const rawContent = data.choices?.[0]?.message?.content;
        if (!rawContent) return null;
        const text = Array.isArray(rawContent)
            ? rawContent.filter(p => p && typeof p.text === 'string').map(p => p.text).join('\n')
            : String(rawContent);
        return text.trim() || null;
    } catch (err) {
        console.warn('[Compressor] LM Studio unreachable, using extractive fallback:', err.message);
        return null;
    }
}

// ── Extractive Fallback (no LLM needed) ─────────────────────────────────────

/**
 * Refine the foveal window (recent verbatim turns) to fit a hard token budget.
 *
 * "Pure context" must never be allowed to flood the context window. Each
 * message that exceeds a size threshold is passed through the LLM refinement
 * pipeline, which strips filler while preserving tone, decisions, and facts.
 * Once the token budget is exhausted, older overflow messages are dropped —
 * but the final message is ALWAYS kept so the model sees the latest turn.
 *
 * @param {Array} toKeep - Recent turns destined for the verbatim fovea
 * @returns {Promise<Array>} Refined, budget-bounded foveal messages
 */
async function refineFovealWindow(toKeep) {
    const refined = [];
    let foveaTokens = 0;

    for (let i = 0; i < toKeep.length; i++) {
        const msg = toKeep[i];
        const raw = typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content || '');
        const rawTokens = Math.ceil(raw.length / 4);
        const isLast = (i === toKeep.length - 1);

        // Hard cap: never let the verbatim window exceed the token budget.
        // Always keep the final message regardless (the model needs the latest turn).
        if (!isLast && foveaTokens + rawTokens > FOVEA_MAX_TOKENS) {
            console.log(`[Fovea] ⏭️ Foveal budget reached (${foveaTokens}/${FOVEA_MAX_TOKENS} tok) — dropping overflow message`);
            continue;
        }

        // Refine oversized messages: LLM strips "air between words", preserves
        // tone/decisions/facts. Falls back to verbatim if the LLM is unreachable.
        let content = msg.content;
        if (raw.length > FOVEA_REFINE_THRESHOLD_CHARS) {
            try {
                const result = await refineMessageAsync(raw);
                if (result && result.refined && result.refined.trim()) {
                    content = result.refined;
                    console.log(`[Fovea] 🔬 LLM-refined foveal message: ${raw.length} → ${content.length} chars (filler stripped)`);
                }
            } catch (e) {
                console.warn('[Fovea] Refinement failed, keeping verbatim:', e.message);
            }
        }

        refined.push({ ...msg, content });
        const contentStr = typeof content === 'string' ? content : JSON.stringify(content || '');
        foveaTokens += Math.ceil(contentStr.length / 4);
    }

    return refined;
}

function extractiveSummary(messages) {
    // Extract key signal without LLM: file names, decisions, status keywords
    const combined = messages.map(m =>
        typeof m.content === 'string' ? m.content : JSON.stringify(m.content)
    ).join(' ');

    const files = [...combined.matchAll(/[\w\-]+\.(py|js|ts|json|md|txt|html|css)/g)]
        .map(m => m[0]).filter((v, i, a) => a.indexOf(v) === i).slice(0, 8).join(', ') || 'none';

    const solved = combined.match(/solved|confirmed|done|complete/i) ? 'solved' :
                   combined.match(/pending|waiting/i) ? 'pending' : 'in-progress';

    // Grab first 400 chars of last assistant message as context
    const lastAssist = [...messages].reverse().find(m => m.role === 'assistant');
    const snippet = lastAssist
        ? (typeof lastAssist.content === 'string' ? lastAssist.content : '').slice(0, 400)
        : 'no assistant message';

    const decisions = combined.match(/DECISIONS?:\s*([^\n]+)/gi)?.slice(0,3).join('; ') || 'extracted from turns';

    return `DECISIONS: ${decisions}\nFILES: ${files}\nSTATUS: ${solved}\nCONTEXT: ${snippet}`;
}

// ── Main Compressor ──────────────────────────────────────────────────────────

/**
 * Compress old conversation turns into XRL checkpoints based on the requested
 * UNIFIED resolution level (0-6). Returns a new messages array with old turns
 * replaced by checkpoint blocks.
 *
 * @param {Array} messages  - Full messages array from request body
 * @param {string} sessionId - Session identifier for tracking
 * @param {number} level     - Unified resolution level (0-5) from ./resolution
 *                            0 = 65% baseline (guaranteed floor, default)
 *                            5 = max compression (5% retention)
 * @returns {Array} - Compressed messages array
 */
async function compressContext(messages, sessionId = 'default', level = 0) {
    // Clamp to the unified 0-5 resolution scale (baseline default).
    const lvl = resolution.clampResolution(level);

    // Pull the foveal-window + checkpoint-batch params from the unified
    // resolution engine so the compressor stays in lockstep with the
    // ring-builder multiplier and the advertised context window.
    const { keepRecent, compressEvery } = resolution.COMPRESSOR_PARAMS[lvl];
    const dynamicWindow   = keepRecent;
    const dynamicCompress = compressEvery;

    // ── Token-Based Triggering ──────────────────────────────────────────
    // Only compress if estimated tokens exceed the budget.
    // This prevents premature compression when the context is still small.
    const estimatedTokens = estimateTokens(messages);
    console.log(`[Compressor] ▶️ entry | session=${sessionId} | level=${lvl} | total=${messages.length} | estTokens=${estimatedTokens} | budget=${TOKEN_BUDGET} | system=${messages.filter(m => m.role === 'system').length} | turns=${messages.filter(m => m.role !== 'system').length}`);

    if (estimatedTokens < TOKEN_BUDGET) {
        console.log(`[Compressor] ⏭️ skip (token budget) | estTokens=${estimatedTokens} < budget=${TOKEN_BUDGET}`);
        return messages;
    }

    // Filter to only user/assistant turns (exclude system messages)
    const systemMsgs  = messages.filter(m => m.role === 'system');
    const turnMsgs    = messages.filter(m => m.role !== 'system');

    // ── Anchor Protection ────────────────────────────────────────────────
    // Separate anchor messages (critical connective tissue) from compressible turns.
    // Anchors are preserved verbatim and never compressed into checkpoints.
    const anchorMsgs = [];
    const compressibleTurns = [];
    for (const msg of turnMsgs) {
        if (isAnchorMessage(msg)) {
            anchorMsgs.push(msg);
        } else {
            compressibleTurns.push(msg);
        }
    }
    if (anchorMsgs.length > 0) {
        console.log(`[Compressor] 🔒 Protected ${anchorMsgs.length} anchor messages from compression`);
    }

    // Not enough compressible turns to compress
    if (compressibleTurns.length < dynamicCompress + dynamicWindow) {
        console.log(`[Compressor] ⏭️ skip | compressibleTurns=${compressibleTurns.length} < threshold=${dynamicCompress + dynamicWindow}`);
        return messages;
    }

    // Split: batch to compress vs recent fovea window
    const compressCount = compressibleTurns.length - dynamicWindow;
    // Round down to nearest dynamicCompress batch
    const batchSize = Math.floor(compressCount / dynamicCompress) * dynamicCompress;
    if (batchSize <= 0) {
        console.log(`[Compressor] ⏭️ skip | batchSize=${batchSize}`);
        return messages;
    }
    console.log(`[Compressor] 📊 level=${lvl} compressCount=${compressCount} batchSize=${batchSize} keep=${dynamicWindow} anchors=${anchorMsgs.length}`);

    const toCompress = compressibleTurns.slice(0, batchSize);
    const toKeepRaw  = compressibleTurns.slice(batchSize);

    // Build checkpoint blocks for each dynamicCompress-sized batch
    const checkpointBlocks = [];
    for (let i = 0; i < toCompress.length; i += dynamicCompress) {
        const batch     = toCompress.slice(i, i + dynamicCompress);
        const batchText = batch.map(m =>
            `${m.role}: ${typeof m.content === 'string' ? m.content : JSON.stringify(m.content)}`
        ).join('\n');

        const hash = hashContent(batchText);

        // Check if already compressed (cached)
        let cached = loadCheckpoint(hash);
        if (!cached) {
            console.log(`[Compressor] Compressing turns ${i+1}-${i+batch.length} → [CKP:${hash}]`);
            const summary = await summarizeWithLMStudio(batch) || extractiveSummary(batch);
            cached = {
                hash,
                session: sessionId,
                turnRange: [i + 1, i + batch.length],
                timestamp: new Date().toISOString(),
                summary,
                raw: batch  // store raw for expandability
            };
            saveCheckpoint(hash, cached);
        }

        checkpointBlocks.push(`[CKP:${hash} @ turns ${cached.turnRange[0]}-${cached.turnRange[1]} | ${cached.timestamp.slice(0,10)}]\n${cached.summary}`);
    }

    // Reconstruct: system + anchors + compressed history + recent turns
    const compressedHistoryMsg = {
        role: 'system',
        content: `=== COMPRESSED HISTORY (XRL Checkpoints) ===\n${checkpointBlocks.join('\n---\n')}\n=== END COMPRESSED HISTORY ===\n\nRecent ${dynamicWindow} turns follow verbatim.`
    };

    // ── Foveal Window Token Cap ─────────────────────────────────────────
    // The kept (verbatim) turns are "pure context" and MUST be bounded so no
    // single message can flood the context. Oversized messages are refined via
    // the LLM pipeline (strips filler, preserves tone/facts), and the window is
    // hard-capped at FOVEA_MAX_TOKENS.
    const toKeep = await refineFovealWindow(toKeepRaw);

    const result = [
        ...systemMsgs,
        ...anchorMsgs,          // Anchors preserved verbatim (before compressed history)
        compressedHistoryMsg,
        ...toKeep
    ];

    const savedTurns  = toCompress.length;
    const savedTokens = Math.round(savedTurns * 600); // ~600 tokens avg per turn
    const resultTokens = estimateTokens(result);
    console.log(`[Compressor] ✅ Compressed ${savedTurns} turns → ${checkpointBlocks.length} checkpoints (~${savedTokens} tokens saved) | resultTokens=${resultTokens} | resultMessages=${result.length} | anchors=${anchorMsgs.length}`);

    return result;
}

/**
 * Expand a checkpoint hash back to full content (for debugging/recall).
 */
function expandCheckpoint(hash) {
    return loadCheckpoint(hash);
}

/**
 * List all stored checkpoints for a session.
 */
function listCheckpoints() {
    if (!fs.existsSync(CHECKPOINT_DIR)) return [];
    return fs.readdirSync(CHECKPOINT_DIR)
        .filter(f => f.endsWith('.json'))
        .map(f => {
            const data = JSON.parse(fs.readFileSync(path.join(CHECKPOINT_DIR, f), 'utf8'));
            return { hash: data.hash, session: data.session, turnRange: data.turnRange, timestamp: data.timestamp };
        });
}

module.exports = { compressContext, expandCheckpoint, listCheckpoints };
