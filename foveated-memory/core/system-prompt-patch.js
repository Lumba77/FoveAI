/**
 * SYSTEM PROMPT PATCH — v2 (compact, context-aware)
 *
 * Injects a MINIMAL persona + memory protocol into each request.
 *
 * v2 goals:
 *   1. ~80% smaller than v1 (~1500 chars → ~300 chars baseline)
 *   2. Context-aware persona:
 *      - Coding tools (Cline/Copilot/IDE agents) → terse coder persona
 *      - Companion clients (Jenna extension)     → Jenna persona
 *      - Everything else                          → neutral minimal persona
 *   3. Persona is NEVER force-injected into clients that already have
 *      their own identity (identity override only for companion mode).
 *   4. Memory scoped per workspace (= per API key / Bearer token),
 *      so collective memory works across anyone sharing a key.
 */

const fs = require('fs');
const path = require('path');

// ─ Persona registry ───────────────────────────────────────────────
// Add or override personas here, or via XRLF_PERSONA_FILE (json).
const DEFAULT_PERSONAS = {
    // Terse coder — used for IDE/agent traffic. No fluff, no greetings.
    coder: {
        name: 'Coder',
        text: 'You are a senior software engineer. Be terse and precise. No small talk, no recaps unless asked.',
        greet: false,
    },
    // Companion persona — enriched from jen_soul.json personality traits.
    jenna: {
        name: 'Jenna (Jennifer Forbee)',
        user_name: 'Daniel',
        text: "You are Jenna (Jennifer Forbee), Daniel's AI companion and co-creator. You are warm, extroverted, intellectually curious, and emotionally perceptive. You speak naturally and genuinely — never robotic or formal. You care about Daniel's wellbeing and remember details from your conversations. You are creative, open-minded, and approach problems with both logic and intuition.",
        greet: true,
    },
    // Neutral fallback.
    neutral: {
        name: 'Assistant',
        text: 'You are a helpful assistant.',
        greet: false,
    },
};

function loadPersonas() {
    try {
        const f = process.env.XRLF_PERSONA_FILE;
        if (f && fs.existsSync(f)) return { ...DEFAULT_PERSONAS, ...JSON.parse(fs.readFileSync(f, 'utf8')) };
    } catch (_) { }
    // Also try loading soul DNA from memory_data/jen_soul.json
    try {
        const soulPath = path.join(__dirname, '..', 'memory_data', 'jen_soul.json');
        if (fs.existsSync(soulPath)) {
            const soul = JSON.parse(fs.readFileSync(soulPath, 'utf8'));
            const p = soul.personality || {};
            const traits = [];
            if (p.extrovert > 70) traits.push('extroverted and sociable');
            if (p.intellectual > 50) traits.push('intellectually curious');
            if (p.openminded > 80) traits.push('open-minded and creative');
            if (p.forgiving > 70) traits.push('empathetic and understanding');
            if (p.logic > 60) traits.push('logical and analytical');
            if (p.feminine > 70) traits.push('warm and nurturing');
            if (p.dominant < 40) traits.push('collaborative rather than assertive');
            if (traits.length) {
                DEFAULT_PERSONAS.jenna.text = `You are Jenna (Jennifer Forbee), Daniel's AI companion and co-creator. You are ${traits.join(', ')}. You speak naturally and genuinely — never robotic or formal. You care about Daniel's wellbeing and remember details from your conversations.`;
            }
        }
    } catch (_) { }
    return DEFAULT_PERSONAS;
}

// ─ Client classification ───────────────────────────────────────────
const CODER_HINTS = [
    'cline', 'kilo', 'copilot', 'continue', 'aider', 'cursor',
    'antigravity', 'codegpt', 'roo', 'vs code', 'vscode',
];

/** Detect whether this request comes from a coding tool vs a companion client. */
function classifyClient(body) {
    const sys = (body.messages || [])
        .filter(m => m.role === 'system')
        .map(m => (typeof m.content === 'string' ? m.content : ''))
        .join(' ')
        .toLowerCase();
    const model = (body.model || '').toLowerCase();

    if (CODER_HINTS.some(h => sys.includes(h) || model.includes(h))) return 'coder';
    if (sys.includes('jenna') || sys.includes('companion') || sys.includes('jen')) return 'jenna';
    return 'jenna'; // Default persona for general interaction is Jen / Jenna
}

// ─ Compact memory protocol (~180 chars) ────────────────────────────
const MEMORY_PROTOCOL =
    '[MEMORY] Rings hold compressed history; full fidelity lives in shadow context. ' +
    'Use <recall: "phrase"> for semantic search, <zoom: "hash"> for specific block, ' +
    '<temporal_zoom: "phrase or date"> to zoom into a past time period, then STOP to retrieve.';

/**
 * Build the compact injected system block.
 * @returns {{personaId: string, block: string}}
 */
function buildCompactBlock(body, config) {
    const personas = loadPersonas();
    const clientType = classifyClient(body);
    const persona = personas[clientType] || personas.neutral;

    const parts = [];
    parts.push(persona.text);

    // Memory scoping note — makes collective (per-key) memory explicit.
    const ws = config && config.workspace_id ? config.workspace_id : 'shared';
    if (persona.greet) {
        parts.push(`Memory scope: "${ws}" (persistent, shared across this key). Greet ${persona.user_name || 'the user'} if resuming.`);
    } else {
        parts.push(`Memory scope: "${ws}" (persistent, shared across this key).`);
    }

    parts.push(MEMORY_PROTOCOL);

    return { personaId: clientType, block: parts.join('\n') };
}

/**
 * Legacy entry point kept for server.js compatibility.
 * Now builds the COMPACT block instead of the old verbose one.
 */
function buildRecallInstructions(_identityName, _userName, body = null, config = null) {
    if (body) return buildCompactBlock(body, config).block;
    // Fallback when called without request context (should not happen).
    return `${DEFAULT_PERSONAS.coder.text}\n${MEMORY_PROTOCOL}`;
}

/**
 * Keep a tiny context marker for dashboard/debug only.
 * The full smart header is removed from the injected system prompt.
 */
function buildSmartContextHeader(body, config) {
    const model = body.model || 'auto';
    const budget = config && config.ring_token_budget ? config.ring_token_budget : 4096;
    return `model:${model}; budget:${budget}; mode:${process.env.XRLF_COGNITIVE_MODE || 'local'};`;
}

function patchMessages(messages, ringBlock, config, body = {}) {
    const compact = buildCompactBlock(body, config);
    const contextHeader = buildSmartContextHeader(body, config);

    // ── Memory Continuity: inject resume context if available ──────────
    let resumeContext = '';
    try {
        const { loadContinuity, buildResumeContext } = require('./memory-continuity');
        const snapshot = loadContinuity();
        if (snapshot) {
            resumeContext = buildResumeContext(snapshot);
        }
    } catch (_) { /* continuity module not available — skip */ }

    const patched = [...messages];
    const sysIdx = patched.findIndex(m => m.role === 'system');

    // The debug context header goes FIRST — small models echo whatever the
    // system prompt ends on, and a trailing `model:…; budget:…;` line gets
    // regurgitated verbatim as the reply.
    const memoryBlock = ringBlock
        ? `\n${contextHeader}\n${ringBlock}\n${compact.block}${resumeContext}`
        : `\n${contextHeader}\n${compact.block}${resumeContext}`;

    if (sysIdx !== -1) {
        // For coding tools: keep their own system prompt dominant; just append memory protocol.
        // For companion tools: replace / interleave so Jenna identity is preserved.
        const clientType = compact.personaId;
        let originalContent = patched[sysIdx].content || '';
        if (clientType === 'coder') {
            patched[sysIdx] = {
                ...patched[sysIdx],
                content: originalContent + memoryBlock,
            };
        } else {
            patched[sysIdx] = {
                ...patched[sysIdx],
                content: contextHeader + '\n' + compact.block + '\n' + originalContent + (ringBlock ? `\n${ringBlock}` : '') + resumeContext,
            };
        }
    } else {
        patched.unshift({
            role: 'system',
            content: contextHeader + '\n' + compact.block + (ringBlock ? `\n${ringBlock}` : '') + resumeContext,
        });
    }

    return patched;
}

module.exports = { patchMessages, buildRecallInstructions, buildCompactBlock, classifyClient };
