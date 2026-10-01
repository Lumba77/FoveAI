/**
 * ═══════════════════════════════════════════════════════
 * IMPORTANCE SCORER — 3-Tier Memory Value Assessment
 * ═══════════════════════════════════════════════════════
 *
 * Scores every message on a 10-grade scale across 5 dimensions:
 *   logic      (1-10): informational/technical value
 *   emotional  (1-10): emotional/tone/relationship value
 *   personal   (1-10): identity-affirming, personally meaningful
 *   actionable (1-10): requires action, decision, or commitment
 *   overall    (1-10): weighted composite — how brightly this memory glows
 *
 * The overall score determines the "glow" of a memory:
 *   10 = legendary (life-changing, "I love you", major life event)
 *   8-9 = critical (key decisions, breakthroughs, important commitments)
 *   6-7 = significant (technical decisions, architecture, important questions)
 *   4-5 = notable (useful info, minor decisions, interesting observations)
 *   2-3 = routine (everyday chat, status updates, "how are you")
 *   1   = filler (greetings, "ok", "thanks", pure meta)
 *
 * 3-Tier Architecture:
 *   Tier 1: Heuristic (real-time, zero latency)
 *           Pattern-based scoring. Good enough for shadow context gating.
 *
 *   Tier 2: Async LLM refinement (background, after response sent)
 *           Re-scores with a small LLM for nuance. Updates stored importance.
 *
 *   Tier 3: LLM-powered re-summarization (on-demand, during temporal zoom)
 *           Uses the LLM to produce importance-weighted summaries of old messages.
 *
 * Preservation Strategies (derived from importance profile):
 *   crystalline  — overall ≥ 9 or personal ≥ 8: "glowing stars"
 *                  Minimal compression at all rings. Preserve exact words forever.
 *   tone-first   — emotional ≥ 7 AND logic < 6: "loving friend"
 *                  Preserve voice, warmth, exact phrasing. Compress logic.
 *   logic-only   — logic ≥ 7 AND emotional < 4: "router relay"
 *                  Strip tone, keep only facts/decisions/reasoning.
 *   balanced     — default: standard compression with tone awareness.
 *   aggressive   — overall ≤ 2: "filler"
 *                  Maximum compression. Evaporates fast through rings.
 *
 * Future: A small proxy model (~0.5B) can replace Tier 1+2 with a single
 * trained pass, running on GPU alongside the main model.
 */

'use strict';

const { withLocalUpstream } = require('./local-upstream-queue');

// ── Preservation Strategy Determination ─────────────────────────────────────

/**
 * Determine preservation strategy from importance dimensions.
 *
 * @param {object} imp - { logic, emotional, personal, actionable, overall }
 * @returns {string} strategy name
 */
function determineStrategy(imp) {
    if (imp.overall >= 9 || imp.personal >= 8) return 'crystalline';
    if (imp.emotional >= 7 && imp.logic < 6) return 'tone-first';
    if (imp.logic >= 7 && imp.emotional < 4) return 'logic-only';
    if (imp.overall <= 2) return 'aggressive';
    return 'balanced';
}

/**
 * Get the compression ratio for a given ring based on preservation strategy.
 * Higher ratio = more content kept. Crystalline preserves more at every ring.
 *
 * @param {string} strategy
 * @param {number} ring - 0-5
 * @returns {number} compression ratio (0.0 = keep nothing, 1.0 = keep all)
 */
function strategyCompressionRatio(strategy, ring) {
    const ratios = {
        crystalline:  [0.80, 0.60, 0.40, 0.25, 0.15, 0.08],
        'tone-first': [0.50, 0.35, 0.20, 0.12, 0.06, 0.03],
        'logic-only': [0.30, 0.20, 0.12, 0.06, 0.03, 0.01],
        balanced:     [0.33, 0.22, 0.14, 0.08, 0.04, 0.02],
        aggressive:   [0.15, 0.10, 0.05, 0.02, 0.01, 0.00]
    };
    return (ratios[strategy] || ratios.balanced)[Math.min(ring, 5)];
}

// ── Tier 1: Heuristic Scoring (real-time, zero latency) ────────────────────

const LOGIC_MARKERS = [
    'function', 'class', 'const', 'import', 'export', 'require', 'module',
    'api', 'endpoint', 'server', 'client', 'database', 'config', 'build',
    'deploy', 'commit', 'merge', 'branch', 'bug', 'fix', 'patch', 'refactor',
    'test', 'error', 'exception', 'code', 'file', 'implement', 'architecture',
    'design pattern', 'algorithm', 'performance', 'optimize', 'benchmark',
    'decide', 'decided', 'choose', 'chose', 'decision', 'plan', 'planned',
    'will do', 'going to', "let's", 'we should', 'we must'
];

const EMOTIONAL_MARKERS = [
    'love', 'hate', 'amazing', 'terrible', 'frustrated', 'excited', 'worried',
    'angry', 'happy', 'sad', 'beautiful', 'ugly', 'wonderful', 'horrible',
    'incredible', 'disappointed', 'thrilled', 'grateful', 'thankful', 'blessed',
    'miss you', 'care about', 'mean to me', 'important to me', 'sorry',
    'apologize', 'forgive', 'hurt', 'pain', 'joy', 'delight', 'precious',
    'afraid', 'scared', 'anxious', 'proud', 'embarrassed', 'lonely', 'hopeful'
];

const PERSONAL_MARKERS = [
    'i am', "i'm", 'my life', 'my dream', 'my fear', 'my hope', 'my belief',
    'who i am', 'identity', 'proud', 'ashamed', 'vulnerable', 'honest',
    'truth', 'real me', 'myself', 'personal', 'private', 'secret',
    'you are', "you're", 'you make me', 'you changed', 'you taught',
    'friend', 'family', 'mother', 'father', 'sister', 'brother', 'daughter', 'son',
    'wife', 'husband', 'partner', 'relationship', 'marriage', 'love you',
    'i love', 'care about you', 'my name', 'call me', 'my dog', 'my cat',
    'my pet', 'my home', 'my job', 'my work', 'remember', "don't forget",
    'my favorite', 'i like', 'i prefer', 'i live', 'i work', 'i study'
];

const ACTION_MARKERS = [
    'todo', 'to-do', 'task', 'action item', 'next step', 'follow up',
    'deadline', 'due', 'by tomorrow', 'by next', 'asap', 'urgent',
    'need to', 'have to', 'must', 'should', 'please do', 'can you',
    'will you', 'assign', 'responsible', 'owner', 'blocking', 'waiting on'
];

/**
 * Tier 1: Heuristic importance scoring.
 * Scores each dimension using keyword/pattern matching.
 * Fast enough for real-time use (sub-millisecond).
 *
 * @param {string} text - Full message text
 * @param {string} role - 'user' | 'assistant' | 'system'
 * @returns {object} ImportanceProfile
 */
function scoreHeuristic(text, role = 'user') {
    // Handle non-string content (arrays of content parts, objects, etc.)
    if (typeof text !== 'string') {
        if (Array.isArray(text)) {
            text = text.filter(p => p && typeof p.text === 'string').map(p => p.text).join(' ');
        } else if (text && typeof text === 'object') {
            text = text.text || text.content || JSON.stringify(text);
        } else {
            text = String(text || '');
        }
    }
    if (!text || text.length === 0) {
        return { logic: 1, emotional: 1, personal: 1, actionable: 1, overall: 1, strategy: 'aggressive', categories: ['filler'], tier: 'heuristic' };
    }
    const lower = text.toLowerCase();
    const len = text.length;

    // ── Logic score ────────────────────────────────────────────────────
    let logic = 2;
    for (const m of LOGIC_MARKERS) {
        if (lower.includes(m)) logic += 0.7;
    }
    if (/[`'"]|\.(js|ts|py|json|md|html|css|yaml|yml|toml)\b/.test(text)) logic += 1.5;
    if (/[\w\-/\\]+\.[a-z]{1,6}\b/i.test(text)) logic += 0.7;
    logic = Math.min(10, Math.round(logic));

    // ── Emotional score ────────────────────────────────────────────────
    let emotional = 2;
    for (const m of EMOTIONAL_MARKERS) {
        if (lower.includes(m)) emotional += 1.0;
    }
    const exclamationCount = (text.match(/!/g) || []).length;
    emotional += exclamationCount * 0.5;
    if (/[:;][\-']?[)D(\]|]|<3|💙|❤|💕|😊|🥰|😢|😭/.test(text)) emotional += 1.5;
    // Strong emotional phrases get bigger boost
    if (/\b(i love you|i hate you|i'm so (happy|sad|angry|excited|scared|afraid)|passed away|miss you so much|i'm terrified|i'm grateful|i'm proud|you've changed my life|you changed my life|you mean everything|you're my best friend|i felt so alone)\b/i.test(text)) emotional += 4;
    // Vulnerability and deep feeling
    if (/\b(i feel (really|so|very)|i'm feeling|heartbroken|devastated|ecstatic|overwhelmed|grateful|terrified|anxious|vulnerable|alone|lost|found|complete)\b/i.test(text)) emotional += 2;
    emotional = Math.min(10, Math.round(emotional));

    // ── Personal score ──────────────────────────────────────────────────
    let personal = 2;
    for (const m of PERSONAL_MARKERS) {
        if (lower.includes(m)) personal += 1.0;
    }
    if (/\bi (feel|believe|think|know|realize|discovered|learned|understand)\b/i.test(text)) {
        personal += 1.0;
    }
    // User messages get a personal boost — they're the primary memory source
    if (role === 'user' && len > 30) personal += 1.5;
    // Explicit memory requests are highly personal
    if (/\b(remember|don't forget|note that|keep in mind|my favorite|my name is|call me|i want you to remember|i want to tell you)\b/i.test(text)) personal += 2;
    // Life events and identity statements
    if (/\b(my (dog|cat|pet|mother|father|sister|brother|wife|husband|partner|son|daughter|grandmother|grandfather|friend)|i (quit|decided|i'm going to|i'm moving|i'm starting))\b/i.test(text)) personal += 2;
    personal = Math.min(10, Math.round(personal));

    // ── Actionable score ────────────────────────────────────────────────
    let actionable = 2;
    for (const m of ACTION_MARKERS) {
        if (lower.includes(m)) actionable += 0.7;
    }
    if (/\[ \]|\[x\]|[-*] \[ \]|[-*] \[x\]/.test(text)) actionable += 2;
    actionable = Math.min(10, Math.round(actionable));

    // ── Overall: the "glow" rating ──────────────────────────────────────
    // The glow is NOT a simple average — it's driven by the STRONGEST signal.
    // A message with personal=10 is a glowing star regardless of other dimensions.
    // A message with all dimensions at 2 is filler.
    //
    // Formula: weighted average as a baseline, but boosted by the max dimension.
    // This ensures that a deeply personal message (personal=10) gets overall >= 8
    // even if logic and actionable are low.
    const weightedAvg = logic * 0.15 + emotional * 0.30 + personal * 0.40 + actionable * 0.15;
    const maxDim = Math.max(logic, emotional, personal, actionable);
    // The glow is 60% weighted average + 40% max dimension
    // This means a personal=10 message gets at least 0.4*10 = 4 from max alone
    // plus 0.4*10 = 4 from personal in the weighted = 8 minimum
    const overall = Math.round(weightedAvg * 0.6 + maxDim * 0.4);
    const clampedOverall = Math.max(1, Math.min(10, overall));

    // ── Categories ──────────────────────────────────────────────────────
    const categories = [];
    if (personal >= 6) categories.push('personal');
    if (actionable >= 6) categories.push('decision');
    if (logic >= 6) categories.push('technical');
    if (text.includes('?')) categories.push('question');
    if (emotional >= 6) categories.push('emotional');
    if (clampedOverall <= 2) categories.push('filler');
    if (categories.length === 0) categories.push('filler');

    const strategy = determineStrategy({
        logic, emotional, personal, actionable, overall: clampedOverall
    });

    return {
        logic, emotional, personal, actionable,
        overall: clampedOverall,
        strategy,
        categories,
        tier: 'heuristic'
    };
}

// ── Tier 2: Async LLM Refinement (background, after response) ──────────────

/**
 * Tier 2: LLM-based importance refinement.
 * Called asynchronously after the response is sent to the user.
 * Re-scores the message with a small LLM for nuance.
 *
 * The LLM sees the message and outputs structured JSON with 1-10 ratings.
 * This is NOT on the hot path — it runs in the background.
 *
 * @param {string} text - Full message text
 * @param {string} role - 'user' | 'assistant'
 * @param {object} opts - { llmUrl, model, heuristicScore }
 * @returns {Promise<object|null>} Refined ImportanceProfile, or null on failure
 */
async function scoreLLM(text, role = 'user', opts = {}) {
    const llmUrl = opts.llmUrl || process.env.XRLF_RUNTIME_URL || 'http://127.0.0.1:8402/v1';
    const model = opts.model || 'auto';
    const heuristic = opts.heuristicScore || scoreHeuristic(text, role);

    // Don't waste an LLM call on very short or very low-importance messages
    if (text.length < 20 || heuristic.overall <= 2) {
        return null;
    }

    const prompt = `Analyze this ${role} message and output ONLY valid JSON (no markdown, no explanation).

Message:
${text.slice(0, 2000)}

Output JSON with these fields:
- "logic": 1-10 informational/technical value
- "emotional": 1-10 emotional/tone/relationship value
- "personal": 1-10 identity-affirming, personally meaningful
- "actionable": 1-10 requires action, decision, or commitment
- "overall": 1-10 weighted composite — how brightly this memory should glow
- "categories": array of 1-3 tags from [personal, decision, technical, question, discovery, emotional, filler]

Importance guide:
- overall 10 = legendary (life-changing, "I love you", major life event)
- overall 8-9 = critical (key decisions, breakthroughs, important commitments)
- overall 6-7 = significant (technical decisions, architecture, important questions)
- overall 4-5 = notable (useful info, minor decisions, interesting observations)
- overall 2-3 = routine (everyday chat, status updates)
- overall 1 = filler (greetings, "ok", "thanks")
- personal >= 8 = about WHO someone is, not just WHAT they said

JSON:`;

    try {
        const res = await withLocalUpstream(() => fetch(`${llmUrl}/chat/completions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model,
                messages: [
                    { role: 'system', content: 'You are a message analyzer. Output ONLY valid JSON. No markdown, no backticks, no explanation. Just the JSON object.' },
                    { role: 'user', content: prompt }
                ],
                max_tokens: 200,
                temperature: 0.0,
                stream: false
            }),
            signal: AbortSignal.timeout(8000)
        }));

        if (!res.ok) return null;
        const data = await res.json();
        const raw = data.choices?.[0]?.message?.content;
        if (!raw) return null;

        const jsonStr = raw.replace(/```json\s*/gi, '').replace(/```\s*/g, '').trim();
        const analysis = JSON.parse(jsonStr);

        // Validate and clamp
        const clamp = (v, d) => Math.max(1, Math.min(10, parseInt(v) || d));
        const imp = {
            logic:      clamp(analysis.logic, heuristic.logic),
            emotional:  clamp(analysis.emotional, heuristic.emotional),
            personal:   clamp(analysis.personal, heuristic.personal),
            actionable: clamp(analysis.actionable, heuristic.actionable),
            overall:    clamp(analysis.overall, heuristic.overall),
        };
        imp.strategy = determineStrategy(imp);
        imp.categories = Array.isArray(analysis.categories) ? analysis.categories.slice(0, 3) : heuristic.categories;
        imp.tier = 'llm';

        return imp;
    } catch (_) {
        return null; // silent fallback to heuristic
    }
}

// ── Tier 3: On-Demand LLM Summarization (during temporal zoom) ─────────────

/**
 * Tier 3: LLM-powered importance-weighted summarization.
 * Used during temporal zoom to produce rich summaries of old messages.
 *
 * The LLM sees a batch of old compressed messages and produces:
 *   - A summary paragraph capturing the key themes
 *   - Per-message importance scores (for selective decompression)
 *   - A list of "glowing stars" (overall >= 8) worth full decompression
 *
 * @param {Array} messages - Array of message objects
 * @param {string} zoomContext - The temporal zoom query (for relevance)
 * @param {object} opts - { llmUrl, model, tokenBudget }
 * @returns {Promise<object>} { summary, scoredMessages, glowingStars }
 */
async function summarizeWithImportance(messages, zoomContext, opts = {}) {
    const llmUrl = opts.llmUrl || process.env.XRLF_RUNTIME_URL || 'http://127.0.0.1:8402/v1';
    const model = opts.model || 'auto';

    if (messages.length === 0) {
        return { summary: '', scoredMessages: [], glowingStars: [] };
    }

    // Build a compact message list for the LLM
    const msgList = messages.slice(0, 50).map((m, i) => {
        const content = (m.content || '').slice(0, 200);
        return `[${i}] ${m.role}: ${content}`;
    }).join('\n');

    const prompt = `You are a memory curator. Analyze these past messages (zoomed into: "${zoomContext}") and output ONLY valid JSON.

Messages:
${msgList}

Output JSON:
- "summary": 2-3 sentence summary of what was discussed
- "messages": array of { "index": number, "importance": 1-10, "reason": short phrase }
- "glowingStars": array of message indices with importance >= 8 (worth full decompression)

Focus on what matters most for the query "${zoomContext}".

JSON:`;

    try {
        const res = await withLocalUpstream(() => fetch(`${llmUrl}/chat/completions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model,
                messages: [
                    { role: 'system', content: 'You are a memory curator. Output ONLY valid JSON.' },
                    { role: 'user', content: prompt }
                ],
                max_tokens: 500,
                temperature: 0.1,
                stream: false
            }),
            signal: AbortSignal.timeout(15000)
        }));

        if (!res.ok) throw new Error('LLM unavailable');
        const data = await res.json();
        const raw = data.choices?.[0]?.message?.content;
        if (!raw) throw new Error('Empty response');

        const jsonStr = raw.replace(/```json\s*/gi, '').replace(/```\s*/g, '').trim();
        const result = JSON.parse(jsonStr);

        return {
            summary: result.summary || '',
            scoredMessages: result.messages || [],
            glowingStars: result.glowingStars || [],
        };
    } catch (_) {
        // Fallback: use heuristic scores only
        const scoredMessages = messages.map((m, i) => ({
            index: i,
            importance: scoreHeuristic(m.content || '', m.role).overall,
            reason: 'heuristic'
        }));
        const glowingStars = scoredMessages.filter(s => s.importance >= 8).map(s => s.index);
        return {
            summary: `${messages.length} messages from this period.`,
            scoredMessages,
            glowingStars
        };
    }
}

// ── Proxy Model Interface (for future small model plug-in) ─────────────────

/**
 * The proxy memory model interface.
 *
 * When a small trained model (~0.5B) is available, it replaces Tier 1+2
 * with a single trained pass. The model would be trained on:
 *   - Importance scoring (10-grade, 5-dimensional)
 *   - Preservation strategy selection
 *   - Automatic memory retrieval (which memories are relevant to current topic)
 *   - Context window assembly (which memories to include, how compressed)
 *
 * The proxy model runs on GPU alongside the main model (~300MB at Q4).
 * It handles ALL memory management, freeing the main model to focus on
 * generating responses.
 *
 * Interface:
 *   proxyModel.score(text, role) → ImportanceProfile
 *   proxyModel.retrieve(query, store) → relevant memory hashes
 *   proxyModel.assembleContext(messages, budget) → compressed ring block
 *   proxyModel.summarize(messages, context) → summary + importance scores
 *
 * For now, this falls back to heuristic + LLM. When the proxy model is
 * trained, set XRLF_PROXY_MEMORY_MODEL=path/to/model.gguf to activate it.
 */

const PROXY_MODEL_PATH = process.env.XRLF_PROXY_MEMORY_MODEL || '';
const proxyModelActive = PROXY_MODEL_PATH !== '';

/**
 * Score a message using the best available method.
 * If proxy model is active, use it. Otherwise, use heuristic (Tier 1).
 *
 * @param {string} text
 * @param {string} role
 * @returns {object} ImportanceProfile
 */
function score(text, role = 'user') {
    if (proxyModelActive) {
        // Future: call proxy model here
        // return proxyModel.score(text, role);
    }
    return scoreHeuristic(text, role);
}

/**
 * Async refinement — called after response is sent.
 * If proxy model is active, it's already done. Otherwise, use LLM (Tier 2).
 *
 * @param {string} text
 * @param {string} role
 * @param {object} heuristicScore
 * @returns {Promise<object|null>}
 */
async function refine(text, role, heuristicScore) {
    if (proxyModelActive) {
        return null; // proxy model already scored in real-time
    }
    return scoreLLM(text, role, { heuristicScore });
}

module.exports = {
    score,
    refine,
    scoreHeuristic,
    scoreLLM,
    summarizeWithImportance,
    determineStrategy,
    strategyCompressionRatio,
    proxyModelActive,
};
