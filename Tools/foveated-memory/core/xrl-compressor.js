/**
 * ═══════════════════════════════════════════════════════
 * XRL COMPRESSOR — Foveated Memory Ring Compression
 * ═══════════════════════════════════════════════════════
 *
 * Compresses conversation turns at 6 levels of fidelity,
 * matching the gradient from fovea (raw) to outer periphery (atomic).
 *
 * Level 0 — Raw (0% compression)     — verbatim messages
 * Level 1 — Light (~50%)             — extractive: top-scoring sentences
 * Level 2 — Medium (~75%)            — extractive: key sentences + topic
 * Level 3 — Deep (~88%)              — LLM summary or extractive one-liner
 * Level 4 — Ultra (~95%)             — topic label + XRL hash ref
 * Level 5 — Atomic (~98%)            — pure XRL hash only
 *
 * KEY INSIGHT: At 50-65% compression via extractive summarization,
 * no context is lost. Truncation destroys context; sentence scoring
 * preserves it by keeping the most semantically important sentences.
 *
 * LLM summarization (rings 1-3) uses reasoning-summarizer-800m-pre
 * for high-quality compression when available, falling back to
 * extractive scoring when the model is unreachable.
 */

'use strict';

const crypto = require('crypto');
const fetch  = require('node-fetch');

// ── LLM Summarizer Config ──────────────────────────────────────────────────
const LM_STUDIO_URL = process.env.LM_STUDIO_URL || 'http://127.0.0.1:7272';
const SUMMARIZER_MODEL = process.env.LUMAX_SUMMARIZER_MODEL || 'reasoning-summarizer-800m-pre';
const LLM_SUMMARIZE_ENABLED = process.env.LUMAX_LLM_SUMMARIZE !== 'false' && process.env.LUMAX_LLM_SUMMARIZE !== '0';

// ── Stop words for topic extraction ────────────────────────────────────────
const STOP_WORDS = new Set([
    'the','a','an','is','it','in','on','at','to','of','and','or',
    'for','with','this','that','was','are','be','as','we','i','you',
    'have','had','has','do','did','not','but','so','if','by','can',
    'will','just','from','they','he','she','also','been','what','how',
    'all','no','its','your','my','me','our','us','them','then','now',
    'very','really','only','some','any','each','every','both','few',
    'more','most','other','same','such','than','too','well','get',
    'got','go','goes','going','went','come','came','make','made',
    'like','know','see','think','say','said','tell','told','ask',
    'asked','use','used','using','need','needs','needed','want',
    'wants','wanted','would','could','should','may','might','must',
    'here','there','where','when','which','who','whom','whose',
]);

/**
 * Generate a short XRL hash for a message block.
 * Format: xrl://mem/<4-char-hash>
 */
function xrlHash(text) {
    const h = crypto.createHash('md5').update(text).digest('hex').slice(0, 4);
    return `xrl://mem/${h}`;
}

/**
 * Split text into sentences (handles . ! ? and newlines).
 */
function splitSentences(text) {
    return text
        .split(/(?<=[.!?])\s+|\n+/)
        .map(s => s.trim())
        .filter(s => s.length > 3);
}

/**
 * Score a sentence for importance using multiple heuristics.
 * Higher score = more important to keep.
 */
function scoreSentence(sentence, fullText) {
    let score = 0;

    // Length: very short or very long sentences are less useful
    const len = sentence.length;
    if (len > 20 && len < 300) score += 2;
    else if (len >= 10 && len <= 400) score += 1;

    // Contains code indicators (backticks, file paths, function calls)
    if (/[`'"]|\.(js|ts|py|json|md|html|css)\b|function\b|class\b|const\b|let\b|var\b|import\b|export\b|require\b/.test(sentence))
        score += 3;

    // Contains decision/action words
    if (/\b(fix|change|update|create|delete|remove|add|implement|build|run|test|deploy|commit|push|merge|install|configure|set|get|make|done|complete|finish|solve|resolve|decide|choose|prefer|should|must|need|important|critical|urgent|broken|error|bug|crash|fail|work|works|working)\b/i.test(sentence))
        score += 2;

    // Contains file names or paths
    if (/[\w\-/\\]+\.[a-z]{1,6}\b/i.test(sentence)) score += 2;

    // Contains numbers (often version numbers, line numbers, counts)
    if (/\d+/.test(sentence)) score += 1;

    // Contains proper nouns (capitalized words not at start)
    if (/[A-Z][a-z]{2,}/.test(sentence.replace(/^[A-Z]/, ''))) score += 1;

    // Position bonus: first and last sentences tend to be important
    const sentences = splitSentences(fullText);
    const idx = sentences.indexOf(sentence);
    if (idx === 0 || idx === sentences.length - 1) score += 2;
    if (idx < 3) score += 1;

    // Penalty: pure pleasantries / filler
    if (/^(hi|hey|hello|ok|okay|sure|thanks|thank|great|nice|good|fine|alright|yes|no|bye|see you|talk soon)[\s,!.?]*$/i.test(sentence))
        score -= 3;

    return score;
}

/**
 * Extractive summarization: keep the top-scoring sentences up to a budget.
 * At ~50% compression, this preserves all meaningful context.
 */
function extractiveSummarize(text, compressionRatio = 0.5) {
    const sentences = splitSentences(text);
    if (sentences.length <= 2) return text; // too short to compress

    const scored = sentences.map(s => ({ text: s, score: scoreSentence(s, text) }));
    scored.sort((a, b) => b.score - a.score);

    const keepCount = Math.max(1, Math.ceil(sentences.length * compressionRatio));
    const keepSet = new Set(scored.slice(0, keepCount).map(s => s.text));

    // Preserve original order
    return sentences.filter(s => keepSet.has(s)).join(' ');
}

/**
 * Extract the dominant topic from a message using simple heuristics.
 */
function extractTopic(text, maxWords = 6) {
    const words = text.toLowerCase()
        .replace(/[^a-z0-9\s\-]/g, ' ')
        .split(/\s+/)
        .filter(w => w.length > 2 && !STOP_WORDS.has(w));

    const seen = new Set();
    const unique = [];
    for (const w of words) {
        if (!seen.has(w)) { seen.add(w); unique.push(w); }
        if (unique.length >= maxWords) break;
    }
    return unique.join(' ') || text.slice(0, 40);
}

/**
 * Get the first meaningful sentence (skip greetings/acknowledgments).
 */
function firstMeaningfulSentence(text) {
    const sentences = splitSentences(text);
    for (const s of sentences) {
        if (!/^(hi|hey|hello|ok|okay|sure|thanks|thank|great|nice|good|fine|alright|yes|no|bye|got it|understood|will do)[\s,!.?]*$/i.test(s))
            return s.slice(0, 150);
    }
    return sentences[0]?.slice(0, 150) || text.slice(0, 100);
}

/**
 * Generate a short descriptive headline for a compressed chunk.
 * Uses the highest-scoring sentence (truncated) as a "headline"
 * so the model can see what's inside even at high compression.
 *
 * @param {string} text - The original message content
 * @param {number} maxLen - Max headline length in chars (default 80)
 * @returns {string} Headline string, e.g. "▸ Fixed the XRL compressor truncation bug"
 */
function generateHeadline(text, maxLen = 80) {
    const sentences = splitSentences(text);
    if (sentences.length === 0) return '';

    // Score all sentences, pick the best one
    let best = sentences[0];
    let bestScore = -999;
    for (const s of sentences) {
        const sc = scoreSentence(s, text);
        if (sc > bestScore) { bestScore = sc; best = s; }
    }

    // Truncate to maxLen, breaking at word boundary
    if (best.length <= maxLen) return `▸ ${best}`;
    const truncated = best.slice(0, maxLen).replace(/\s+\S*$/, '');
    return `▸ ${truncated}…`;
}

/**
 * Refine a message for the Fovea (Ring 0).
 *
 * Unlike compression, refinement preserves the speaker's TONE and VOICE
 * while reducing uneven, rambling messages to a consistent density.
 *
 * Design principles:
 *   1. Detect tone — classify as ironic, urgent, technical, casual, etc.
 *   2. Tone-aware headline — "▸ [ironic] The compressor was totally not broken"
 *   3. Adaptive compression — short messages stay intact; long ones compress
 *      to ~1/3 of original, keeping the most personality-rich sentences
 *   4. Bounded context — the fovea never grows uncontrollably; each message
 *      gets a soft cap (~300 chars), compressed proportionally if exceeded
 *   5. Preserve voice — the compressed version still sounds like the speaker
 *
 * @param {string} text - The original message content
 * @returns {string} Refined message with tone headline + bounded body
 */
function refineMessage(text) {
    const sentences = splitSentences(text);
    if (sentences.length === 0) return text;

    // ── 1. Detect tone ──────────────────────────────────────────────────
    const tone = detectTone(text, sentences);

    // ── 2. Generate tone-classified headline ────────────────────────────
    const headline = generateToneHeadline(text, tone, 80);

    // ── 3. Single sentence or very short: keep intact ───────────────────
    if (sentences.length === 1 || text.length < 150) {
        return `${headline}\n   ${text}`;
    }

    // ── 4. Adaptive compression ─────────────────────────────────────────
    // Target: ~1/3 of original, but never more than ~300 chars
    // and never less than the single best sentence
    const targetLen = Math.min(Math.round(text.length / 3), 300);
    const bestLen = Math.max(...sentences.map(s => s.length));

    // Score sentences for BOTH information AND personality
    const scored = sentences.map(s => ({
        text: s,
        score: scoreSentence(s, text) + toneBonus(s, tone)
    }));
    scored.sort((a, b) => b.score - a.score);

    // Greedy selection: keep adding top sentences until we hit target
    const keepSet = new Set();
    let running = 0;
    for (const { text: s, score } of scored) {
        if (running >= targetLen && keepSet.size > 0) break;
        // Always keep at least the best sentence
        if (keepSet.size === 0 || running + s.length <= targetLen * 1.3) {
            keepSet.add(s);
            running += s.length;
        }
    }

    // Preserve original order
    const refined = sentences.filter(s => keepSet.has(s)).join(' ');

    // If we somehow lost everything, keep the first sentence
    if (!refined.trim()) return `${headline}\n   ${sentences[0]}`;

    return `${headline}\n   ${refined}`;
}

/**
 * Detect the dominant tone of a message.
 *
 * @param {string} text - Full message text
 * @param {string[]} sentences - Pre-split sentences
 * @returns {string} Tone label: 'ironic', 'urgent', 'technical', 'questioning',
 *                   'emotional', 'casual', or 'neutral'
 */
function detectTone(text, sentences) {
    const lower = text.toLowerCase();

    // Ironic / sarcastic markers
    const ironicMarkers = ['"', '"', 'totally', 'obviously', 'of course', 'sure it is',
        'yeah right', 'as if', 'clearly', 'naturally', 'what could go wrong',
        'perfect', 'brilliant', 'genius', 'amazing work'];
    let ironicHits = 0;
    for (const m of ironicMarkers) {
        if (lower.includes(m)) ironicHits++;
    }
    // Quoted phrases often indicate irony
    const quoteCount = (text.match(/"[^"]{3,}"/g) || []).length;
    ironicHits += quoteCount;

    // Urgent markers
    const urgentMarkers = ['urgent', 'asap', 'critical', 'broken', 'crash', 'crashing',
        'immediately', 'right now', 'emergency', 'on fire', 'deadline', 'blocking'];
    let urgentHits = 0;
    for (const m of urgentMarkers) {
        if (lower.includes(m)) urgentHits++;
    }

    // Technical markers
    const technicalMarkers = ['function', 'class', 'const', 'import', 'export', 'require',
        'module', 'component', 'api', 'endpoint', 'server', 'client', 'database',
        'config', 'build', 'deploy', 'commit', 'merge', 'branch', 'file', 'code',
        'bug', 'fix', 'patch', 'refactor', 'test', 'error', 'exception'];
    let technicalHits = 0;
    for (const m of technicalMarkers) {
        if (lower.includes(m)) technicalHits++;
    }
    // Code indicators
    if (/[`'"]|\.(js|ts|py|json|md|html|css|yaml|yml|toml)\b/.test(text)) technicalHits += 2;
    if (/[\w\-/\\]+\.[a-z]{1,6}\b/i.test(text)) technicalHits += 1;

    // Questioning
    const questionCount = sentences.filter(s => s.trim().endsWith('?')).length;
    const questionWords = ['what', 'how', 'why', 'when', 'where', 'who', 'can you',
        'could you', 'would you', 'should i', 'do you', 'is there', 'are there'];
    let questionHits = 0;
    for (const m of questionWords) {
        if (lower.includes(m)) questionHits++;
    }

    // Emotional markers
    const emotionalMarkers = ['love', 'hate', 'amazing', 'terrible', 'frustrated',
        'excited', 'worried', 'angry', 'happy', 'sad', 'beautiful', 'ugly',
        'wonderful', 'horrible', 'incredible', 'disappointed', 'thrilled'];
    let emotionalHits = 0;
    for (const m of emotionalMarkers) {
        if (lower.includes(m)) emotionalHits++;
    }
    const exclamationCount = (text.match(/!/g) || []).length;
    emotionalHits += exclamationCount;

    // Casual markers
    const casualMarkers = ['hey', 'btw', 'lol', 'haha', 'hehe', 'anyway', 'just wondering',
        'no worries', 'cool', 'nice', 'sweet', 'awesome', 'dude', 'mate'];
    let casualHits = 0;
    for (const m of casualMarkers) {
        if (lower.includes(m)) casualHits++;
    }

    // Determine dominant tone
    const scores = [
        { tone: 'ironic',     score: ironicHits * 3 },
        { tone: 'urgent',     score: urgentHits * 3 },
        { tone: 'technical',  score: technicalHits * 2 },
        { tone: 'questioning',score: questionHits * 2 + questionCount * 2 },
        { tone: 'emotional',  score: emotionalHits * 2 },
        { tone: 'casual',     score: casualHits * 2 },
    ];
    scores.sort((a, b) => b.score - a.score);

    // Only classify if there's a clear signal
    if (scores[0].score >= 3) return scores[0].tone;
    if (scores[0].score >= 2 && scores[0].score > scores[1].score) return scores[0].tone;
    return 'neutral';
}

/**
 * Bonus score for sentences that match the detected tone.
 * Sentences carrying the speaker's personality get a boost so they
 * survive compression.
 */
function toneBonus(sentence, tone) {
    const lower = sentence.toLowerCase();
    let bonus = 0;

    switch (tone) {
        case 'ironic':
            if (/["']|totally|obviously|of course|clearly|naturally|sure|right/i.test(lower))
                bonus += 2;
            break;
        case 'urgent':
            if (/now|asap|critical|broken|crash|immediately|right now|emergency/i.test(lower))
                bonus += 2;
            break;
        case 'technical':
            if (/function|class|const|import|export|require|api|endpoint|server|config|build|deploy|commit|merge|branch|file|code|bug|fix|patch|refactor|test|error/i.test(lower))
                bonus += 2;
            break;
        case 'questioning':
            if (/\?$/.test(sentence.trim())) bonus += 2;
            if (/what|how|why|when|where|who|can you|could you/i.test(lower)) bonus += 1;
            break;
        case 'emotional':
            if (/love|hate|amazing|terrible|frustrated|excited|worried|angry|happy|sad|beautiful|wonderful|horrible|incredible|disappointed|thrilled/i.test(lower))
                bonus += 2;
            if (/!/.test(sentence)) bonus += 1;
            break;
        case 'casual':
            if (/hey|btw|lol|haha|hehe|anyway|just wondering|no worries|cool|nice|sweet|awesome|dude|mate/i.test(lower))
                bonus += 2;
            break;
    }
    return bonus;
}

/**
 * Generate a tone-classified headline.
 * Format: "▸ [tone] best sentence describing the core idea"
 */
function generateToneHeadline(text, tone, maxLen = 80) {
    const sentences = splitSentences(text);
    if (sentences.length === 0) return `▸ [${tone}]`;

    // Pick the best sentence — prefer ones matching the tone
    let best = sentences[0];
    let bestScore = -999;
    for (const s of sentences) {
        const sc = scoreSentence(s, text) + toneBonus(s, tone);
        if (sc > bestScore) { bestScore = sc; best = s; }
    }

    const tag = tone === 'neutral' ? '' : `[${tone}] `;
    const prefix = `▸ ${tag}`;
    const available = maxLen - prefix.length;

    if (best.length <= available) return `▸ ${tag}${best}`;
    const truncated = best.slice(0, available).replace(/\s+\S*$/, '');
    return `▸ ${tag}${truncated}…`;
}

// ── Two-Stage Refinement Pipeline ──────────────────────────────────────────
//
// Stage 1: LLM Analyzer — sends the message to a fast model, gets back
//           structured JSON with tone, headline, sentence keep/drop indices,
//           AND multi-dimensional importance scores.
// Stage 2: Importance-Aware Executor — follows the LLM's instructions but
//           ADAPTS compression based on WHY the message matters:
//             • High emotional → preserve tone, voice, exact phrasing
//             • High logic → preserve decisions, facts, reasoning
//             • High personal → crystalline preservation, slow digestion
//             • Low everything → aggressive compression, fast digestion
//
// If the LLM is unreachable or times out, falls back to heuristic scoring.

/**
 * Multi-dimensional importance profile for a message.
 *
 * Each dimension is 1-10. The PRESERVATION STRATEGY adapts based on
 * which dimensions score high:
 *
 *   High logic + low emotional  → "router relay" — compress to pure logic
 *   High emotional + low logic  → "loving friend" — preserve tone, voice, exact words
 *   High personal               → "glowing star" — crystalline, slow digestion
 *   High actionable             → "decision point" — preserve the what + why
 *   Low everything              → "filler" — aggressive compression, fast digestion
 *
 * @typedef {Object} ImportanceProfile
 * @property {number} logic      - 1-10: informational/technical value
 * @property {number} emotional  - 1-10: emotional/tone/relationship value
 * @property {number} personal   - 1-10: identity-affirming, personally meaningful
 * @property {number} actionable - 1-10: requires action, decision, or commitment
 * @property {number} overall    - 1-10: weighted composite (the "glow" rating)
 * @property {string} strategy   - 'crystalline' | 'tone-first' | 'logic-only' | 'balanced' | 'aggressive'
 * @property {string[]} categories - tags: personal, decision, technical, question, discovery, emotional, filler
 */

/**
 * Determine preservation strategy from importance dimensions.
 *
 * The strategy controls HOW the message is compressed through the rings:
 *
 *   'crystalline'  — importance ≥ 9 overall OR personal ≥ 8
 *                    Minimal compression at all rings. Preserve exact words,
 *                    tone, and structure. These are the "glowing stars."
 *                    Ring 0: ~80% kept, Ring 1: ~60%, Ring 2: ~40%, etc.
 *
 *   'tone-first'   — emotional ≥ 7 AND logic < 6
 *                    Preserve voice, irony, warmth. Compress logic but keep
 *                    the feeling. "Sarah said I'm beautiful" — the words
 *                    matter more than the information.
 *                    Ring 0: ~50% kept (tone-heavy sentences), Ring 1: ~35%
 *
 *   'logic-only'    — logic ≥ 7 AND emotional < 4
 *                    Strip tone, keep only facts/decisions/reasoning.
 *                    "Router relay" — pure information transfer.
 *                    Ring 0: ~30% kept (logic sentences only), Ring 1: ~20%
 *
 *   'balanced'      — default for mixed signals
 *                    Standard ~1/3 compression with tone awareness.
 *
 *   'aggressive'    — overall ≤ 2
 *                    Maximum compression at every ring. Filler evaporates fast.
 *                    Ring 0: ~15% kept, Ring 1: ~10%, gone by Ring 3.
 *
 * @param {ImportanceProfile} imp
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
 *
 * Higher ratio = more kept. Crystalline preserves more at every ring.
 * Aggressive compresses harder at every ring.
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

/**
 * Stage 1: Ask a fast LLM to analyze a message and produce cutting instructions
 *          WITH multi-dimensional importance scoring.
 *
 * The LLM outputs structured JSON:
 *   { tone, headline, keep: [indices], drop: [indices], summary,
 *     importance: { logic, emotional, personal, actionable, overall },
 *     categories: [...] }
 *
 * @param {string} text - The original message content
 * @returns {Promise<object|null>} Analysis result or null on failure
 */
async function analyzeMessage(text) {
    if (!LLM_SUMMARIZE_ENABLED) return null;

    const sentences = splitSentences(text);
    if (sentences.length <= 1) return null; // too short, not worth LLM call

    // Build a numbered sentence list for the LLM to reference
    const numbered = sentences.map((s, i) => `[${i}] ${s}`).join('\n');

    const prompt = `Analyze this message and output ONLY valid JSON (no markdown, no explanation).

Message:
${numbered}

Output JSON with these fields:
- "tone": one of [ironic, urgent, technical, questioning, emotional, casual, neutral]
- "headline": a short phrase (max 70 chars) capturing the core idea WITH the tone preserved
- "keep": array of sentence indices that are ESSENTIAL
- "drop": array of sentence indices that are FILLER
- "summary": one dense sentence (max 120 chars) capturing WHAT + HOW (preserve tone)
- "importance": object with these 1-10 ratings:
  - "logic": informational/technical value — facts, code, decisions, reasoning
  - "emotional": emotional/tone/relationship value — warmth, irony, care, vulnerability
  - "personal": identity-affirming, personally meaningful to the speaker/recipient
  - "actionable": requires action, decision, or commitment
  - "overall": weighted composite — how brightly this memory should glow
- "categories": array of 1-3 tags from [personal, decision, technical, question, discovery, emotional, filler]

Importance guide:
- overall 10 = legendary (life-changing, "you are beautiful", "I love you", major life event)
- overall 8-9 = critical (key decisions, breakthroughs, important commitments)
- overall 6-7 = significant (technical decisions, architecture, important questions)
- overall 4-5 = notable (useful info, minor decisions, interesting observations)
- overall 2-3 = routine (everyday chat, status updates, "how are you")
- overall 1 = filler (greetings, "ok", "thanks", pure meta)
- personal ≥ 8 means this is about WHO someone is, not just WHAT they said
- emotional ≥ 7 AND logic < 6 means tone matters more than information
- logic ≥ 7 AND emotional < 4 means pure information — compress to facts

Rules:
- Every sentence index must appear in exactly one of keep/drop
- importance.overall should reflect the highest dimension, not an average
- A message can be high in multiple dimensions (e.g. a technical breakthrough that's also personally meaningful)
- Be honest and conservative — most messages are 2-5 overall

JSON:`;


    try {
        const res = await fetch(`${LM_STUDIO_URL}/v1/chat/completions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model: SUMMARIZER_MODEL,
                messages: [
                    { role: 'system', content: 'You are a message analyzer. Output ONLY valid JSON. No markdown, no backticks, no explanation. Just the JSON object.' },
                    { role: 'user', content: prompt }
                ],
                max_tokens: 300,
                temperature: 0.0,
                stream: false
            }),
            signal: (() => { const c = new AbortController(); setTimeout(() => c.abort(), 8000); return c.signal; })() // fast timeout — 8 seconds max
        });

        if (!res.ok) return null;
        const data = await res.json();
        const raw = data.choices?.[0]?.message?.content;
        if (!raw) return null;

        // Parse JSON — strip any markdown fences the model might have added
        const jsonStr = raw.replace(/```json\s*/gi, '').replace(/```\s*/g, '').trim();
        const analysis = JSON.parse(jsonStr);

        // Validate required fields
        if (!analysis.tone || !Array.isArray(analysis.keep) || !Array.isArray(analysis.drop)) {
            return null;
        }

        // Ensure importance object exists with defaults
        if (!analysis.importance || typeof analysis.importance !== 'object') {
            analysis.importance = scoreImportance(text, analysis.tone);
        } else {
            // Fill any missing dimensions
            const imp = analysis.importance;
            imp.logic = imp.logic ?? 3;
            imp.emotional = imp.emotional ?? 3;
            imp.personal = imp.personal ?? 3;
            imp.actionable = imp.actionable ?? 3;
            imp.overall = imp.overall ?? Math.max(imp.logic, imp.emotional, imp.personal, imp.actionable);
        }

        // Determine preservation strategy
        analysis.importance.strategy = determineStrategy(analysis.importance);

        // Ensure categories
        if (!Array.isArray(analysis.categories)) {
            analysis.categories = [];
        }

        return analysis;
    } catch (_) {
        return null; // silent fallback to heuristics
    }
}

/**
 * Heuristic importance scoring — used when LLM is unreachable.
 *
 * Scores each dimension using keyword/sentiment heuristics,
 * then determines the preservation strategy.
 *
 * @param {string} text - Full message text
 * @param {string} tone - Detected tone (from detectTone)
 * @returns {ImportanceProfile}
 */
function scoreImportance(text, tone) {
    const lower = text.toLowerCase();
    const sentences = splitSentences(text);

    // ── Logic score ────────────────────────────────────────────────────
    let logic = 3; // baseline
    const logicMarkers = [
        'function', 'class', 'const', 'import', 'export', 'require', 'module',
        'api', 'endpoint', 'server', 'client', 'database', 'config', 'build',
        'deploy', 'commit', 'merge', 'branch', 'bug', 'fix', 'patch', 'refactor',
        'test', 'error', 'exception', 'code', 'file', 'implement', 'architecture',
        'design pattern', 'algorithm', 'performance', 'optimize', 'benchmark'
    ];
    for (const m of logicMarkers) {
        if (lower.includes(m)) logic += 0.5;
    }
    if (/[`'"]|\.(js|ts|py|json|md|html|css|yaml|yml|toml)\b/.test(text)) logic += 1;
    if (/[\w\-/\\]+\.[a-z]{1,6}\b/i.test(text)) logic += 0.5;
    // Decision words
    const decisionWords = ['decide', 'decided', 'choose', 'chose', 'decision',
        'plan', 'planned', 'will do', 'going to', 'let\'s', 'we should', 'we must'];
    for (const m of decisionWords) {
        if (lower.includes(m)) logic += 0.5;
    }
    logic = Math.min(10, Math.round(logic));

    // ── Emotional score ────────────────────────────────────────────────
    let emotional = 3; // baseline
    const emotionalMarkers = [
        'love', 'hate', 'amazing', 'terrible', 'frustrated', 'excited', 'worried',
        'angry', 'happy', 'sad', 'beautiful', 'ugly', 'wonderful', 'horrible',
        'incredible', 'disappointed', 'thrilled', 'grateful', 'thankful', 'blessed',
        'miss you', 'care about', 'mean to me', 'important to me', 'sorry',
        'apologize', 'forgive', 'hurt', 'pain', 'joy', 'delight', 'precious'
    ];
    for (const m of emotionalMarkers) {
        if (lower.includes(m)) emotional += 0.5;
    }
    const exclamationCount = (text.match(/!/g) || []).length;
    emotional += exclamationCount * 0.3;
    // Emoji / emoticons
    if (/[:;][\-']?[)D(\]|]|<3|💙|❤|💕|😊|🥰|😢|😭/.test(text)) emotional += 0.5;
    // Tone boost
    if (tone === 'emotional') emotional += 2;
    if (tone === 'ironic') emotional += 1;
    emotional = Math.min(10, Math.round(emotional));

    // ── Personal score ──────────────────────────────────────────────────
    let personal = 3; // baseline
    const personalMarkers = [
        'i am', 'i\'m', 'my life', 'my dream', 'my fear', 'my hope', 'my belief',
        'who i am', 'identity', 'proud', 'ashamed', 'vulnerable', 'honest',
        'truth', 'real me', 'myself', 'personal', 'private', 'secret',
        'you are', 'you\'re', 'you make me', 'you changed', 'you taught',
        'friend', 'family', 'mother', 'father', 'sister', 'brother', 'daughter', 'son',
        'relationship', 'marriage', 'love you', 'i love', 'care about you'
    ];
    for (const m of personalMarkers) {
        if (lower.includes(m)) personal += 0.5;
    }
    // Self-disclosure: "I feel", "I believe", "I think" about personal matters
    if (/\bi (feel|believe|think|know|realize|discovered|learned|understand)\b/i.test(text)) {
        personal += 0.5;
    }
    personal = Math.min(10, Math.round(personal));

    // ── Actionable score ────────────────────────────────────────────────
    let actionable = 3; // baseline
    const actionMarkers = [
        'todo', 'to-do', 'task', 'action item', 'next step', 'follow up',
        'deadline', 'due', 'by tomorrow', 'by next', 'asap', 'urgent',
        'need to', 'have to', 'must', 'should', 'please do', 'can you',
        'will you', 'assign', 'responsible', 'owner', 'blocking', 'waiting on'
    ];
    for (const m of actionMarkers) {
        if (lower.includes(m)) actionable += 0.5;
    }
    // Checkbox patterns
    if (/\[ \]|\[x\]|[-*] \[ \]|[-*] \[x\]/.test(text)) actionable += 2;
    actionable = Math.min(10, Math.round(actionable));

    // ── Overall: weighted composite ─────────────────────────────────────
    // Personal and emotional weigh heavier for "glow" because they're rarer
    const overall = Math.round(
        logic * 0.20 + emotional * 0.30 + personal * 0.35 + actionable * 0.15
    );
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

    return { logic, emotional, personal, actionable, overall: clampedOverall, strategy, categories };
}

/**
 * Stage 2: Importance-aware deterministic executor.
 *
 * Follows the LLM's keep/drop instructions but ADAPTS compression
 * based on the preservation strategy:
 *
 *   'crystalline'  — keep more sentences, preserve exact phrasing
 *   'tone-first'   — boost tone-carrying sentences, compress logic
 *   'logic-only'    — keep only factual/decision sentences, strip tone
 *   'balanced'      — standard ~1/3 with tone awareness
 *   'aggressive'    — keep only the absolute minimum
 *
 * @param {string} text - Original message text
 * @param {object} analysis - The LLM's analysis
 * @returns {string} Refined message
 */
function executeRefinement(text, analysis) {
    const sentences = splitSentences(text);
    if (sentences.length === 0) return text;

    const { tone, headline, keep, importance } = analysis;
    const strategy = importance?.strategy || 'balanced';
    const keepSet = new Set(keep);

    // ── Strategy-aware sentence filtering ──────────────────────────────
    let kept;
    switch (strategy) {
        case 'crystalline':
            // Keep everything the LLM marked + borderline sentences
            // These are the glowing stars — preserve as much as possible
            kept = sentences.filter((_, i) => keepSet.has(i));
            // If we kept less than 60%, add more from the drop list
            if (kept.length < sentences.length * 0.4) {
                const dropSet = new Set(analysis.drop || []);
                const borderline = sentences.filter((_, i) => !keepSet.has(i) && dropSet.has(i));
                // Add back the longest dropped sentences (they likely have content)
                borderline.sort((a, b) => b.length - a.length);
                const extra = borderline.slice(0, Math.ceil(sentences.length * 0.2));
                kept = [...kept, ...extra];
                // Re-sort to original order
                kept.sort((a, b) => sentences.indexOf(a) - sentences.indexOf(b));
            }
            break;

        case 'tone-first':
            // Keep tone-carrying sentences, even if LLM marked them as drop
            // The feeling matters more than the information
            kept = sentences.filter((_, i) => {
                if (keepSet.has(i)) return true;
                const s = sentences[i];
                // Rescue dropped sentences that carry emotional weight
                return toneBonus(s, tone) >= 2;
            });
            break;

        case 'logic-only':
            // Keep only sentences with logical/technical content
            // Strip anything that's purely tonal or emotional
            kept = sentences.filter((_, i) => {
                if (!keepSet.has(i)) return false;
                const s = sentences[i];
                // Drop if it's purely emotional with no logic
                const hasLogic = scoreSentence(s, text) >= 3;
                const isPureTone = toneBonus(s, tone) >= 2 && scoreSentence(s, text) <= 1;
                return hasLogic && !isPureTone;
            });
            // If we stripped everything, keep the best logic sentence
            if (kept.length === 0) {
                const best = sentences
                    .map((s, i) => ({ s, i, sc: scoreSentence(s, text) }))
                    .sort((a, b) => b.sc - a.sc);
                kept = [best[0].s];
            }
            break;

        case 'aggressive':
            // Keep only the absolute best sentence
            kept = sentences.filter((_, i) => keepSet.has(i));
            if (kept.length > 1) {
                // Sort by score, keep only top 1-2
                const scored = kept.map(s => ({ s, sc: scoreSentence(s, text) }));
                scored.sort((a, b) => b.sc - a.sc);
                kept = scored.slice(0, Math.max(1, Math.ceil(kept.length * 0.3))).map(x => x.s);
                // Re-sort to original order
                kept.sort((a, b) => sentences.indexOf(a) - sentences.indexOf(b));
            }
            break;

        default: // balanced
            kept = sentences.filter((_, i) => keepSet.has(i));
            break;
    }

    // ── Build output ────────────────────────────────────────────────────
    if (kept.length === 0) {
        const tag = tone && tone !== 'neutral' ? `[${tone}] ` : '';
        return `▸ ${tag}${headline || sentences[0].slice(0, 70)}\n   ${sentences[0]}`;
    }

    // Strategy badge for visibility
    const strategyBadges = {
        crystalline: '💎', 'tone-first': '🎭', 'logic-only': '⚙️',
        balanced: '◆', aggressive: '➤'
    };
    const badge = strategyBadges[strategy] || '◆';

    // Importance star rating
    const overall = importance?.overall || 5;
    const stars = overall >= 9 ? '★★★★★' : overall >= 7 ? '★★★★' :
                  overall >= 5 ? '★★★' : overall >= 3 ? '★★' : '★';

    const tag = tone && tone !== 'neutral' ? `[${tone}] ` : '';
    const hl = headline || kept[0].slice(0, 70);
    const body = kept.join(' ');

    return `${badge} ${stars} ▸ ${tag}${hl}\n   ${body}`;
}

/**
 * Full two-stage refinement pipeline.
 *
 * Tries LLM analysis first → importance-aware execution.
 * Falls back to heuristic scoring + refinement if the LLM is unreachable.
 *
 * @param {string} text - Original message content
 * @returns {Promise<{refined: string, importance: ImportanceProfile}>}
 */
async function refineMessageAsync(text) {
    // Try LLM analysis
    const analysis = await analyzeMessage(text);
    if (analysis) {
        return {
            refined: executeRefinement(text, analysis),
            importance: analysis.importance
        };
    }

    // Fallback to heuristic scoring + refinement
    const tone = detectTone(text, splitSentences(text));
    const importance = scoreImportance(text, tone);
    const heuristicAnalysis = {
        tone,
        headline: generateToneHeadline(text, tone, 70),
        keep: [], // will be filled by refineMessage's internal scoring
        drop: [],
        importance,
        categories: importance.categories
    };

    return {
        refined: refineMessage(text),
        importance
    };
}

// ── LLM Summarizer (async, for rings 1-3) ──────────────────────────────────

/**
 * Summarize a batch of messages using the lightweight summarizer model.
 * Falls back to extractive summarization if the model is unreachable.
 *
 * @param {Array} messages - Array of { role, content, timestamp } objects
 * @param {number} level - Compression level (1-3)
 * @returns {Promise<string>} Summarized text block
 */
async function llmSummarize(messages, level) {
    if (!LLM_SUMMARIZE_ENABLED) return null;

    const turns = messages.map(m => {
        const role = (m.role || 'unknown').toUpperCase();
        const content = typeof m.content === 'string' ? m.content : JSON.stringify(m.content || '');
        return `${role}: ${content.slice(0, 500)}`;
    }).join('\n\n');

    const levelPrompts = {
        1: `Summarize these conversation turns at ~50% compression. Preserve ALL decisions, file names, code references, error messages, and key facts. Keep the original tone. Output as a flowing paragraph.`,
        2: `Summarize these conversation turns at ~75% compression. Keep only: key decisions, files touched, errors encountered, and the main outcome. Be terse but complete.`,
        3: `Summarize these conversation turns at ~88% compression. Output a single dense sentence per turn: what was done, what was decided, what file was changed.`
    };

    try {
        const res = await fetch(`${LM_STUDIO_URL}/v1/chat/completions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model: SUMMARIZER_MODEL,
                messages: [
                    { role: 'system', content: 'You are a conversation compressor. Preserve facts, decisions, files, and code references. Be dense and precise. Never invent information.' },
                    { role: 'user', content: `${levelPrompts[level] || levelPrompts[1]}\n\nTurns:\n${turns}\n\nCompressed summary:` }
                ],
                max_tokens: level === 1 ? 200 : level === 2 ? 120 : 60,
                temperature: 0.1,
                stream: false
            }),
            signal: (() => { const c = new AbortController(); setTimeout(() => c.abort(), 15000); return c.signal; })()
        });

        if (!res.ok) return null;
        const data = await res.json();
        const raw = data.choices?.[0]?.message?.content;
        if (!raw) return null;
        const text = Array.isArray(raw) ? raw.filter(p => p?.text).map(p => p.text).join('\n') : String(raw);
        return text.trim() || null;
    } catch (_) {
        return null; // silent fallback to extractive
    }
}

// ── Main Compress Function ──────────────────────────────────────────────────

/**
 * Compress a set of messages at the given level.
 * Messages is an array of { role, content, timestamp, id } objects.
 * Returns a formatted string block ready for injection into a prompt.
 *
 * @param {Array} messages
 * @param {number} level - 0 (raw) to 5 (atomic)
 * @param {number} tokenBudget - max tokens for this ring
 * @returns {string}
 */
function compress(messages, level, tokenBudget = 999) {
    if (!messages || messages.length === 0) return '';

    const lines = [];
    let approxTokens = 0;

    for (const msg of messages) {
        if (approxTokens >= tokenBudget) break;

        const ts = msg.timestamp
            ? new Date(msg.timestamp).toISOString().slice(0, 10)
            : 'unknown';
        const role = (msg.role || 'unknown').toUpperCase();
        const rawContent = msg.content || '';
        const content = (Array.isArray(rawContent)
            ? rawContent.filter(p => p && typeof p.text === 'string').map(p => p.text).join('\n')
            : String(rawContent)
        ).trim();
        const hash = xrlHash(content);

        let line = '';

        switch (level) {
            case 0:
                // Fovea — refined: tone-classified headline + adaptive ~1/3 compression
                // Preserves voice, irony, personality; bounds context to ~300 chars
                line = `[${ts}] ${role}: ${refineMessage(content)}`;
                break;

            case 1:
                // Light (~50%) — extractive: top-scoring sentences + headline
                {
                    const headline = generateHeadline(content, 80);
                    const summarized = extractiveSummarize(content, 0.50);
                    line = `[${ts}] ${role}: ${headline}\n   ${summarized}`;
                }
                break;

            case 2:
                // Medium (~75%) — extractive: top ~25% sentences + topic + headline
                {
                    const headline = generateHeadline(content, 70);
                    const topic = extractTopic(content);
                    const summarized = extractiveSummarize(content, 0.25);
                    line = `[${ts}] (${topic}) ${headline}\n   ${summarized}`;
                }
                break;

            case 3:
                // Deep (~88%) — headline + topic + first meaningful sentence
                {
                    const headline = generateHeadline(content, 60);
                    const topic = extractTopic(content, 4);
                    const keySentence = firstMeaningfulSentence(content);
                    line = `[${ts}] ${topic}: ${headline}\n   ${keySentence}`;
                }
                break;

            case 4:
                // Ultra (~95%) — headline + topic label + hash ref
                {
                    const headline = generateHeadline(content, 50);
                    const topic = extractTopic(content, 3);
                    line = `[${ts}] ${headline} (${topic}) ${hash}`;
                }
                break;

            case 5:
                // Atomic (~98%) — headline + hash only
                {
                    const headline = generateHeadline(content, 40);
                    line = `[${ts}] ${headline} ${hash}`;
                }
                break;

            default:
                line = `[${ts}] ${role}: ${content.slice(0, 100)}`;
        }

        // Rough token estimate: 1 token ≈ 4 chars
        const tokenEst = Math.ceil(line.length / 4);
        if (approxTokens + tokenEst > tokenBudget) break;

        lines.push(line);
        approxTokens += tokenEst;
    }

    return lines.join('\n');
}

/**
 * Async version: compress with LLM summarization for rings 1-3.
 * Falls back to extractive if LLM is unreachable.
 *
 * @param {Array} messages
 * @param {number} level - 0-5
 * @param {number} tokenBudget
 * @returns {Promise<string>}
 */
async function compressAsync(messages, level, tokenBudget = 999) {
    if (!messages || messages.length === 0) return '';

    // ── Level 0: Two-stage refinement pipeline (per-message LLM analysis) ──
    if (level === 0 && LLM_SUMMARIZE_ENABLED) {
        const lines = [];
        const importanceScores = []; // collect for caller
        let approxTokens = 0;

        for (const msg of messages) {
            if (approxTokens >= tokenBudget) break;

            const ts = msg.timestamp
                ? new Date(msg.timestamp).toISOString().slice(0, 10)
                : 'unknown';
            const role = (msg.role || 'unknown').toUpperCase();
            const rawContent = msg.content || '';
            const content = (Array.isArray(rawContent)
                ? rawContent.filter(p => p && typeof p.text === 'string').map(p => p.text).join('\n')
                : String(rawContent)
            ).trim();

            // Two-stage: LLM analyze → importance-aware execute
            const result = await refineMessageAsync(content);
            const refined = result.refined || result; // handle both old and new return types
            const importance = result.importance || null;

            const line = `[${ts}] ${role}: ${refined}`;

            const tokenEst = Math.ceil(line.length / 4);
            if (approxTokens + tokenEst > tokenBudget) break;

            lines.push(line);
            approxTokens += tokenEst;

            if (importance) {
                importanceScores.push({ ts, role, importance });
            }
        }

        return lines.join('\n');
    }

    // Only use LLM for levels 1-3 with multiple messages
    if (level >= 1 && level <= 3 && messages.length >= 2 && LLM_SUMMARIZE_ENABLED) {
        const llmResult = await llmSummarize(messages, level);
        if (llmResult) {
            // Format with timestamp of most recent message
            const latest = messages[messages.length - 1];
            const ts = latest.timestamp
                ? new Date(latest.timestamp).toISOString().slice(0, 10)
                : 'unknown';
            const role = (latest.role || 'unknown').toUpperCase();
            const hash = xrlHash(llmResult);

            // Generate a headline from the LLM summary itself
            const headline = generateHeadline(llmResult, 70);

            const ringLabels = { 1: 'PARAFOVEA', 2: 'NEAR-PERIPHERY', 3: 'MID-PERIPHERY' };
            const label = ringLabels[level] || `RING-${level}`;
            return `[${ts}] [${label}-LLM] ${role}: ${headline}\n   ${llmResult} ${hash}`;
        }
    }

    // Fallback to extractive
    return compress(messages, level, tokenBudget);
}

/**
 * Estimate token count for a string (rough: 1 token ≈ 4 chars).
 */
function estimateTokens(text) {
    return Math.ceil((text || '').length / 4);
}

// ── Intelligent Storage Preparation ────────────────────────────────────────
//
// Before a message hits the memory DB, it passes through this pipeline.
// The goal: preserve ALL contextual value while preventing 50K+ file dumps
// from bloating the database and polluting every future context window.
//
// Tiered approach based on message size:
//
//   Tier 0: < 2000 chars  → verbatim (normal chat messages)
//   Tier 1: 2000-6000     → light extractive (~50% keep), tone-aware headline
//   Tier 2: 6000-20000    → structural: detect file dumps, code blocks, prose;
//                            preserve structure skeleton + user's actual question
//   Tier 3: > 20000        → aggressive: skeleton only + topic + hash ref
//
// For file-read dumps (the most common bloat source), we:
//   1. Extract the user's actual question/request (last non-file paragraph)
//   2. For each file: keep path + first ~15 lines + last ~5 lines
//   3. Replace the middle with a [snipped N lines] marker
//   4. Preserve the file structure so the model still knows what was read

/**
 * Detect if content is a file-read dump from tools like read_file.
 * Looks for patterns like <file>, <content lines="...">, [read_file for...]
 */
function isFileReadDump(text) {
    return /<file>|<content lines=|\[read_file\s+for|\[grep_search\s+for|Result:.*<files>/i.test(text);
}

/**
 * Detect if content is primarily code (not prose).
 * Returns { isCode, codeRatio } where codeRatio is 0.0-1.0.
 */
function detectCodeDensity(text) {
    const lines = text.split('\n');
    if (lines.length === 0) return { isCode: false, codeRatio: 0 };

    let codeLines = 0;
    for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        // Code indicators: indentation, symbols, keywords, no sentence structure
        if (/^[\s]{2,}/.test(line) && !/^[A-Z][a-z]/.test(trimmed)) { codeLines++; continue; }
        if (/[{}();=<>[\]]/.test(trimmed) && trimmed.length > 10) { codeLines++; continue; }
        if (/^(import|export|const|let|var|function|class|if|for|while|return|async|await|def|from|require)\b/.test(trimmed)) { codeLines++; continue; }
        if (/^[#/]{1,2}\s/.test(trimmed)) { codeLines++; continue; } // comments
    }

    const ratio = codeLines / lines.length;
    return { isCode: ratio > 0.4, codeRatio: ratio };
}

/**
 * Extract the user's actual question/request from a file-read dump.
 * The question is typically the last non-file paragraph before or after
 * the file blocks.
 */
function extractUserQuestion(text) {
    // Try to find text after the last file block
    const afterFiles = text.split(/<\/file>|<\/files>|<\/content>/).pop() || '';
    const cleaned = afterFiles.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
    if (cleaned.length > 20 && cleaned.length < 2000) return cleaned;

    // Try to find text before the first file block
    const beforeFiles = text.split(/<file>|<files>|\[read_file/)[0] || '';
    const cleaned2 = beforeFiles.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
    if (cleaned2.length > 20 && cleaned2.length < 2000) return cleaned2;

    return '';
}

/**
 * Compress a file-read dump into a structured skeleton.
 * Preserves: file paths, first ~15 lines of each file, last ~5 lines,
 * and the user's actual question.
 */
function compressFileDump(text) {
    const question = extractUserQuestion(text);
    const parts = [];

    // Extract individual file blocks
    const fileRegex = /<file>\s*<path>([^<]+)<\/path>\s*<content[^>]*>([\s\S]*?)<\/content>\s*<\/file>/gi;
    let match;
    let fileCount = 0;

    while ((match = fileRegex.exec(text)) !== null) {
        fileCount++;
        const filePath = match[1].trim();
        const fileContent = match[2];
        const lines = fileContent.split('\n');

        if (lines.length <= 20) {
            // Small file — keep entirely
            parts.push(`📄 ${filePath} (${lines.length} lines):\n${fileContent.trim()}`);
        } else {
            // Large file — skeleton: first 15 + last 5 lines
            const head = lines.slice(0, 15).join('\n');
            const tail = lines.slice(-5).join('\n');
            const skipped = lines.length - 20;
            parts.push(`📄 ${filePath} (${lines.length} lines, ${skipped} snipped):\n${head}\n  ...[${skipped} lines snipped]...\n${tail}`);
        }
    }

    // If no structured file blocks found, try simpler patterns
    if (fileCount === 0) {
        // Try [read_file for 'file1', 'file2'] pattern
        const readMatch = text.match(/\[read_file\s+for\s+([^\]]+)\]/i);
        if (readMatch) {
            parts.push(`📋 Files read: ${readMatch[1]}`);
        }

        // Extract code blocks (```...```)
        const codeBlockRegex = /```(\w*)\n([\s\S]*?)```/g;
        let cbMatch;
        let cbCount = 0;
        while ((cbMatch = codeBlockRegex.exec(text)) !== null) {
            cbCount++;
            const lang = cbMatch[1] || 'code';
            const code = cbMatch[2];
            const codeLines = code.split('\n');
            if (codeLines.length <= 20) {
                parts.push(`\`\`\`${lang}\n${code.trim()}\n\`\`\``);
            } else {
                const head = codeLines.slice(0, 12).join('\n');
                const tail = codeLines.slice(-5).join('\n');
                parts.push(`\`\`\`${lang} (${codeLines.length} lines, snipped)\n${head}\n  ...[${codeLines.length - 17} lines]...\n${tail}\n\`\`\``);
            }
        }

        // If still nothing, fall back to extractive
        if (parts.length === 0) {
            const headline = generateHeadline(text, 80);
            const summary = extractiveSummarize(text, 0.25);
            parts.push(`${headline}\n${summary}`);
        }
    }

    // Always include the user's question if found
    if (question) {
        parts.push(`\n💬 User request: ${question}`);
    }

    // Add a hash for traceability
    const hash = xrlHash(text);
    parts.push(`\n🔗 ${hash}`);

    return parts.join('\n\n');
}

/**
 * Intelligent storage preparation pipeline.
 *
 * Analyzes message content and applies tiered compression that preserves
 * contextual value while preventing database bloat.
 *
 * @param {string} text - The raw message content to prepare for storage
 * @returns {string} Prepared content, ready for the memory DB
 */
function prepareForStorage(text) {
    if (!text || typeof text !== 'string') return text || '';
    const len = text.length;

    // ── Tier 0: Normal messages (< 2000 chars) — store verbatim ─────────
    if (len < 2000) return text;

    // ── Tier 1: Medium messages (2000-6000) — light extractive ──────────
    if (len < 6000) {
        const headline = generateHeadline(text, 80);
        const summary = extractiveSummarize(text, 0.50);
        const hash = xrlHash(text);
        return `${headline}\n${summary}\n🔗 ${hash}`;
    }

    // ── Tier 2: Large messages (6000-20000) — structural analysis ───────
    if (len < 20000) {
        // Check if it's a file-read dump
        if (isFileReadDump(text)) {
            return compressFileDump(text);
        }

        // Check code density
        const { isCode, codeRatio } = detectCodeDensity(text);
        if (isCode) {
            // Code-heavy: keep structure, compress
            const lines = text.split('\n');
            if (lines.length <= 50) return text; // manageable

            const head = lines.slice(0, 20).join('\n');
            const tail = lines.slice(-10).join('\n');
            const hash = xrlHash(text);
            return `${head}\n  ...[${lines.length - 30} lines snipped]...\n${tail}\n🔗 ${hash}`;
        }

        // Prose: extractive at ~35% keep ratio
        const headline = generateHeadline(text, 80);
        const summary = extractiveSummarize(text, 0.35);
        const hash = xrlHash(text);
        return `${headline}\n${summary}\n🔗 ${hash}`;
    }

    // ── Tier 3: Massive messages (> 20000) — aggressive skeleton ──────
    if (isFileReadDump(text)) {
        return compressFileDump(text);
    }

    const { isCode: isCode3 } = detectCodeDensity(text);
    if (isCode3) {
        const lines = text.split('\n');
        const head = lines.slice(0, 15).join('\n');
        const tail = lines.slice(-8).join('\n');
        const hash = xrlHash(text);
        return `${head}\n  ...[${lines.length - 23} lines snipped]...\n${tail}\n🔗 ${hash}`;
    }

    // Prose: heavy extractive
    const headline = generateHeadline(text, 60);
    const topic = extractTopic(text, 4);
    const summary = extractiveSummarize(text, 0.15);
    const hash = xrlHash(text);
    return `[${topic}] ${headline}\n${summary}\n🔗 ${hash}`;
}

// ── LLM-Powered Storage Compression ────────────────────────────────────────
//
// The heuristic prepareForStorage() above is fast and works offline, but it
// can't truly understand WHAT matters in a message. This async version sends
// the message to the local LLM (LM Studio) which:
//
//   1. Identifies the message type (file dump, code, prose, mixed)
//   2. Determines what's CRITICAL (must preserve verbatim)
//   3. Determines what's IMPORTANT (preserve meaning, can rephrase)
//   4. Determines what's FILLER (can summarize aggressively or drop)
//   5. Returns a compressed version targeting 50-80% reduction
//
// The LLM is instructed to preserve:
//   - File paths, function names, error messages, line numbers
//   - Decisions, conclusions, action items
//   - Code snippets that are referenced
//   - The user's actual question/request
//   - Tone, personality, emotional content
//
// And to compress:
//   - Boilerplate, repeated patterns, verbose explanations
//   - Full file contents → skeleton (first/last N lines)
//   - Long prose → dense summary preserving all facts
//
// Falls back to heuristic prepareForStorage() if LLM is unreachable.

/**
 * LLM-powered storage compression. Sends the message to the local LLM
 * for intelligent analysis and compression.
 *
 * @param {string} text - The raw message content
 * @param {number} timeoutMs - Max time to wait for LLM (default 10000ms)
 * @returns {Promise<string>} Compressed content ready for storage
 */
async function prepareForStorageAsync(text, timeoutMs = 10000) {
    if (!text || typeof text !== 'string') return text || '';
    const len = text.length;

    // ── Small messages: don't bother the LLM ────────────────────────────
    if (len < 2000) return text;

    // ── LLM not enabled: fall back to heuristic ─────────────────────────
    if (!LLM_SUMMARIZE_ENABLED) return prepareForStorage(text);

    // ── Prepare the message for the LLM ─────────────────────────────────
    // For very large messages, send first 3000 + last 2000 chars as context
    // The LLM doesn't need to see every byte to know what to keep
    let contextForLLM = text;
    if (len > 8000) {
        contextForLLM = text.slice(0, 4000) +
            `\n\n... [${len - 8000} chars omitted from middle] ...\n\n` +
            text.slice(-4000);
    }

    const isFileDump = isFileReadDump(text);
    const { isCode, codeRatio } = detectCodeDensity(text);

    // ── Build the compression prompt ────────────────────────────────────
    let contentTypeHint = 'conversational prose';
    if (isFileDump) contentTypeHint = 'a file-read dump from a coding tool (contains <file> blocks with source code)';
    else if (isCode) contentTypeHint = 'source code or technical output';

    const prompt = `You are a context compression engine. Your job is to compress this message for long-term memory storage while preserving ALL important information.

MESSAGE TYPE: ${contentTypeHint}
ORIGINAL SIZE: ${len} chars
TARGET: 50-80% reduction (output should be ${Math.round(len * 0.35)}-${Math.round(len * 0.5)} chars)

RULES:
1. PRESERVE VERBATIM: file paths, function/class names, error messages, line numbers, code snippets that are referenced, the user's actual question/request
2. PRESERVE MEANING: decisions, conclusions, action items, key facts, emotional tone, personality
3. COMPRESS: boilerplate, repeated patterns, verbose explanations, full file contents → skeleton (first/last few lines with line count)
4. For file dumps: keep file paths + first ~10 significant lines + last ~3 lines per file + the user's question
5. For code: keep structure (function/class signatures) + key logic, strip implementation details
6. For prose: dense summary preserving ALL facts, decisions, and tone
7. NEVER invent information. If unsure, keep it.
8. Output ONLY the compressed text. No explanations, no markdown fences.

MESSAGE TO COMPRESS:
${contextForLLM}

COMPRESSED:`;


    try {
        const res = await fetch(`${LM_STUDIO_URL}/v1/chat/completions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model: SUMMARIZER_MODEL,
                messages: [
                    { role: 'system', content: 'You are a context compression engine. Output ONLY the compressed text. No explanations, no markdown fences, no meta-commentary. Preserve all important information in dense form.' },
                    { role: 'user', content: prompt }
                ],
                max_tokens: Math.max(200, Math.ceil(len / 8)), // ~2 chars/token, target ~25% of original
                temperature: 0.1,
                stream: false
            }),
            signal: (() => { const c = new AbortController(); setTimeout(() => c.abort(), timeoutMs); return c.signal; })()
        });

        if (!res.ok) {
            console.warn(`[StorageAsync] LLM returned ${res.status}, falling back to heuristic`);
            return prepareForStorage(text);
        }

        const data = await res.json();
        const raw = data.choices?.[0]?.message?.content;
        if (!raw || raw.trim().length < 10) {
            console.warn('[StorageAsync] LLM returned empty/short content, falling back to heuristic');
            return prepareForStorage(text);
        }

        const compressed = raw.trim();
        const reduction = ((1 - compressed.length / len) * 100).toFixed(0);
        console.log(`[StorageAsync] 🤖 LLM compressed: ${len} → ${compressed.length} chars (${reduction}% reduction)`);

        // Add hash for traceability
        const hash = xrlHash(text);
        return `${compressed}\n🔗 ${hash}`;
    } catch (err) {
        console.warn(`[StorageAsync] LLM call failed (${err.message}), falling back to heuristic`);
        return prepareForStorage(text);
    }
}

module.exports = { compress, compressAsync, xrlHash, extractTopic, estimateTokens, extractiveSummarize, generateHeadline, refineMessage, refineMessageAsync, analyzeMessage, executeRefinement, detectTone, generateToneHeadline, scoreImportance, determineStrategy, strategyCompressionRatio, prepareForStorage, prepareForStorageAsync, isFileReadDump, compressFileDump };
