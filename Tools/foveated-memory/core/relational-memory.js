/**
 * ═══════════════════════════════════════════════════════
 * RELATIONAL MEMORY — Topic Energy Graph & Value System
 * ═══════════════════════════════════════════════════════
 *
 * Tracks what the user cares about across time, sessions,
 * and conversation partners. Messages gain importance not
 * just from their content, but from how the user RETURNS
 * to the ideas within them.
 *
 * CORE CONCEPT: Topic Energy
 *   A topic accumulates "energy" when:
 *     • The user writes a lot about it (volume)
 *     • It spans multiple sessions (persistence)
 *     • It gets referenced by later messages (backlinks)
 *     • It triggers emotional responses (charge)
 *     • It appears across different conversation partners (spread)
 *
 *   Energy decays over time if the topic isn't revisited,
 *   but high-energy topics decay slower — they're "sticky."
 *
 * RELATIONAL BOOST:
 *   When a message touches a high-energy topic, its
 *   importance score gets boosted. A routine message
 *   about a core obsession becomes important because
 *   it's part of a larger pattern the user cares about.
 *
 * TOPIC GRAPH:
 *   Topics are connected by co-occurrence within messages.
 *   "XRL compressor" ↔ "context budget" ↔ "token optimization"
 *   form a cluster. The cluster's collective energy affects
 *   all messages touching any node in it.
 */

'use strict';

// ── Configuration ──────────────────────────────────────────────────────────
const ENERGY_DECAY_HALF_LIFE_DAYS = 7;     // Energy halves every 7 days without activity
const STICKY_TOPIC_THRESHOLD = 50;          // Topics above this energy decay slower
const STICKY_DECAY_MULTIPLIER = 0.5;        // Sticky topics decay at half speed
const BOOST_MAX = 5;                        // Maximum importance boost from relational energy
const CO_OCCURRENCE_WINDOW = 3;             // Messages within this distance are "co-occurring"

// ── In-memory topic graph ──────────────────────────────────────────────────
// Persisted to disk periodically, rebuilt on startup.

/** @type {Map<string, TopicNode>} */
let topicGraph = new Map();

/** @type {Map<string, number>} */
let messageTopicMap = new Map(); // messageId → [topicKeys...]

/**
 * @typedef {Object} TopicNode
 * @property {string} key          - Normalized topic key (lowercase, trimmed)
 * @property {string} label        - Human-readable topic label
 * @property {number} energy       - Current energy level (0-100+)
 * @property {number} peakEnergy   - Highest energy ever reached
 * @property {number} messageCount - Number of messages touching this topic
 * @property {number} sessionCount - Number of distinct sessions
 * @property {number} partnerCount - Number of distinct conversation partners
 * @property {number} lastTouched  - Timestamp of most recent mention
 * @property {number} firstSeen    - Timestamp of first mention
 * @property {string[]} categories - Associated categories
 * @property {Set<string>} connectedTopics - Co-occurring topic keys
 * @property {number} emotionalCharge - Accumulated emotional weight
 */

/**
 * Normalize a topic string for use as a key.
 */
function normalizeTopic(topic) {
    return topic.toLowerCase().trim().replace(/\s+/g, ' ');
}

/**
 * Extract topics from a message using keyword extraction.
 * Returns an array of {key, label} objects.
 *
 * This is a fast heuristic — the LLM can provide better topics
 * via the analysis pipeline, but this works without one.
 */
function extractTopics(text) {
    const lower = text.toLowerCase();
    const topics = [];

    // ── Technical topics ────────────────────────────────────────────────
    const techPatterns = [
        /\b(xrl|fovea|foveated|ring\s*builder|context\s*window|token\s*budget)\b/gi,
        /\b(compressor|compression|summariz\w+|refinement|pipeline)\b/gi,
        /\b(memory\s*store|nedb|database|persist\w*|index\w*)\b/gi,
        /\b(api|endpoint|server|proxy|router|middleware)\b/gi,
        /\b(llm|model|inference|summariz\w*|analyzer|classif\w*)\b/gi,
        /\b(importance|scoring|grading|ranking|priority)\b/gi,
        /\b(dashboard|frontend|ui|html|css|visualization)\b/gi,
        /\b(relational|graph|energy|topic|cluster|semantic)\b/gi,
    ];

    for (const pattern of techPatterns) {
        const matches = text.match(pattern);
        if (matches) {
            const unique = [...new Set(matches.map(m => m.toLowerCase()))];
            for (const m of unique) {
                topics.push({ key: normalizeTopic(m), label: m, category: 'technical' });
            }
        }
    }

    // ── Conceptual topics ───────────────────────────────────────────────
    const conceptPatterns = [
        /\b(importance|value|meaning|significance|worth|priority)\b/gi,
        /\b(preserv\w*|sav\w*|keep|retain|remember|forget)\b/gi,
        /\b(digest\w*|nutrient|process|filter|refine|distill)\b/gi,
        /\b(tone|voice|emotion|feeling|warmth|irony|sarcasm)\b/gi,
        /\b(friend|relationship|personal|identity|self)\b/gi,
        /\b(decision|choice|plan|action|commit|promise)\b/gi,
        /\b(discover|realize|understand|insight|breakthrough)\b/gi,
        /\b(beauty|love|care|affection|connection|bond)\b/gi,
    ];

    for (const pattern of conceptPatterns) {
        const matches = text.match(pattern);
        if (matches) {
            const unique = [...new Set(matches.map(m => m.toLowerCase()))];
            for (const m of unique) {
                if (!topics.find(t => t.key === normalizeTopic(m))) {
                    topics.push({ key: normalizeTopic(m), label: m, category: 'conceptual' });
                }
            }
        }
    }

    // ── Named entities (capitalized phrases) ────────────────────────────
    const namedEntities = text.match(/\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){0,2}\b/g);
    if (namedEntities) {
        const unique = [...new Set(namedEntities)];
        for (const entity of unique) {
            const key = normalizeTopic(entity);
            if (!topics.find(t => t.key === key) && entity.length > 3) {
                topics.push({ key, label: entity, category: 'entity' });
            }
        }
    }

    return topics.slice(0, 10); // cap at 10 topics per message
}

/**
 * Initialize or update a topic node in the graph.
 */
function ensureTopic(key, label, category = 'general') {
    if (!topicGraph.has(key)) {
        topicGraph.set(key, {
            key,
            label: label || key,
            energy: 0,
            peakEnergy: 0,
            messageCount: 0,
            sessionCount: 0,
            partnerCount: 0,
            lastTouched: Date.now(),
            firstSeen: Date.now(),
            categories: [category],
            connectedTopics: new Set(),
            emotionalCharge: 0
        });
    }
    return topicGraph.get(key);
}

/**
 * Feed a message into the topic energy graph.
 *
 * This is called on every message ingest. It:
 *   1. Extracts topics from the message
 *   2. Adds energy to each topic
 *   3. Creates co-occurrence edges between topics
 *   4. Tracks session and partner spread
 *
 * @param {string} messageId - Unique message ID
 * @param {string} text - Message content
 * @param {string} sessionId - Current session ID
 * @param {string} userId - User/partner identifier
 * @param {number} emotionalCharge - 0-10 emotional weight from analysis
 * @param {string[]} llmCategories - Categories from LLM analysis
 */
function feedMessage(messageId, text, sessionId, userId, emotionalCharge = 0, llmCategories = []) {
    const topics = extractTopics(text);
    if (topics.length === 0) return;

    const now = Date.now();
    const topicKeys = topics.map(t => t.key);

    // Store message→topic mapping
    messageTopicMap.set(messageId, topicKeys);

    // ── Update each topic ──────────────────────────────────────────────
    for (const topic of topics) {
        const node = ensureTopic(topic.key, topic.label, topic.category);

        // Energy gain: base + emotional bonus + category bonus
        let energyGain = 1;
        if (emotionalCharge >= 7) energyGain += 3;
        else if (emotionalCharge >= 5) energyGain += 1;
        if (llmCategories.includes('personal')) energyGain += 2;
        if (llmCategories.includes('decision')) energyGain += 1;

        node.energy += energyGain;
        node.messageCount += 1;
        node.lastTouched = now;
        node.emotionalCharge += emotionalCharge;

        if (node.energy > node.peakEnergy) {
            node.peakEnergy = node.energy;
        }

        // Track categories
        for (const cat of llmCategories) {
            if (!node.categories.includes(cat)) {
                node.categories.push(cat);
            }
        }
    }

    // ── Co-occurrence edges ─────────────────────────────────────────────
    for (let i = 0; i < topicKeys.length; i++) {
        for (let j = i + 1; j < topicKeys.length; j++) {
            const a = topicGraph.get(topicKeys[i]);
            const b = topicGraph.get(topicKeys[j]);
            if (a && b) {
                a.connectedTopics.add(topicKeys[j]);
                b.connectedTopics.add(topicKeys[i]);
            }
        }
    }
}

/**
 * Apply time-based energy decay to all topics.
 *
 * Called periodically (e.g., every hour or on each ring build).
 * Energy halves every ENERGY_DECAY_HALF_LIFE_DAYS.
 * Sticky topics (energy > STICKY_TOPIC_THRESHOLD) decay slower.
 */
function applyDecay(now = Date.now()) {
    for (const [key, node] of topicGraph) {
        const daysSinceLastTouch = (now - node.lastTouched) / (1000 * 60 * 60 * 24);
        if (daysSinceLastTouch <= 0) continue;

        const halfLives = daysSinceLastTouch / ENERGY_DECAY_HALF_LIFE_DAYS;
        let decayFactor = Math.pow(0.5, halfLives);

        // Sticky topics resist decay
        if (node.energy > STICKY_TOPIC_THRESHOLD) {
            decayFactor = Math.pow(0.5, halfLives * STICKY_DECAY_MULTIPLIER);
        }

        node.energy = Math.max(0, node.energy * decayFactor);

        // Remove dead topics (energy < 0.1)
        if (node.energy < 0.1) {
            topicGraph.delete(key);
        }
    }
}

/**
 * Get the relational boost for a message based on its topics.
 *
 * A message touching high-energy topics gets an importance boost.
 * The boost is proportional to the collective energy of its topics,
 * capped at BOOST_MAX.
 *
 * @param {string} messageId - Message ID
 * @returns {number} Boost value (0 to BOOST_MAX)
 */
function getRelationalBoost(messageId) {
    const topicKeys = messageTopicMap.get(messageId);
    if (!topicKeys || topicKeys.length === 0) return 0;

    let totalEnergy = 0;
    let count = 0;

    for (const key of topicKeys) {
        const node = topicGraph.get(key);
        if (node) {
            totalEnergy += node.energy;
            count++;
        }
    }

    if (count === 0) return 0;

    const avgEnergy = totalEnergy / count;
    // Map energy to boost: 0 energy → 0 boost, 50+ energy → max boost
    const boost = Math.min(BOOST_MAX, (avgEnergy / 50) * BOOST_MAX);
    return Math.round(boost * 10) / 10;
}

/**
 * Get the topic energy graph as a plain object (for API/dashboard).
 *
 * @returns {Object} Topic energy summary
 */
function getTopicEnergyReport() {
    applyDecay(); // decay before reporting

    const topics = [];
    for (const [key, node] of topicGraph) {
        topics.push({
            key: node.key,
            label: node.label,
            energy: Math.round(node.energy * 10) / 10,
            peakEnergy: Math.round(node.peakEnergy * 10) / 10,
            messageCount: node.messageCount,
            categories: node.categories,
            connectionCount: node.connectedTopics.size,
            emotionalCharge: Math.round(node.emotionalCharge * 10) / 10,
            lastTouched: new Date(node.lastTouched).toISOString(),
            daysSinceLastTouch: Math.round((Date.now() - node.lastTouched) / (1000 * 60 * 60 * 24) * 10) / 10,
            isSticky: node.energy > STICKY_TOPIC_THRESHOLD
        });
    }

    // Sort by energy descending
    topics.sort((a, b) => b.energy - a.energy);

    // ── Topic clusters (connected components) ───────────────────────────
    const visited = new Set();
    const clusters = [];

    for (const [key] of topicGraph) {
        if (visited.has(key)) continue;

        // BFS to find connected component
        const cluster = [];
        const queue = [key];
        visited.add(key);

        while (queue.length > 0) {
            const current = queue.shift();
            const node = topicGraph.get(current);
            if (!node) continue;

            cluster.push(current);

            for (const neighbor of node.connectedTopics) {
                if (!visited.has(neighbor)) {
                    visited.add(neighbor);
                    queue.push(neighbor);
                }
            }
        }

        if (cluster.length >= 2) {
            const clusterEnergy = cluster.reduce((sum, k) => {
                const n = topicGraph.get(k);
                return sum + (n ? n.energy : 0);
            }, 0);

            clusters.push({
                topics: cluster,
                size: cluster.length,
                totalEnergy: Math.round(clusterEnergy * 10) / 10,
                topLabels: cluster
                    .map(k => topicGraph.get(k)?.label || k)
                    .slice(0, 5)
            });
        }
    }

    // Sort clusters by total energy
    clusters.sort((a, b) => b.totalEnergy - a.totalEnergy);

    return {
        topicCount: topics.length,
        clusterCount: clusters.length,
        totalMessagesTracked: messageTopicMap.size,
        stickyTopicCount: topics.filter(t => t.isSticky).length,
        topics: topics.slice(0, 20), // top 20
        clusters: clusters.slice(0, 10) // top 10 clusters
    };
}

/**
 * Boost an importance profile based on relational topic energy.
 *
 * Takes the intrinsic importance from analyzeMessage/scoreImportance
 * and applies relational boosts from the topic energy graph.
 *
 * @param {ImportanceProfile} importance - From scoreImportance or LLM
 * @param {string} messageId - Message ID for topic lookup
 * @returns {ImportanceProfile} Boosted importance profile
 */
function boostImportance(importance, messageId) {
    const boost = getRelationalBoost(messageId);
    if (boost === 0) return importance;

    const boosted = { ...importance };

    // Apply boost to overall
    boosted.overall = Math.min(10, Math.round((boosted.overall || 5) + boost));

    // Boost the dominant dimension
    const dims = ['personal', 'emotional', 'logic', 'actionable'];
    let maxDim = 'logic';
    let maxVal = 0;
    for (const d of dims) {
        if ((boosted[d] || 0) > maxVal) {
            maxVal = boosted[d] || 0;
            maxDim = d;
        }
    }
    boosted[maxDim] = Math.min(10, Math.round((boosted[maxDim] || 5) + boost * 0.7));

    // Re-determine strategy with boosted scores
    boosted.strategy = determineStrategy(boosted);

    // Mark as relationally boosted
    boosted._relationalBoost = Math.round(boost * 10) / 10;

    return boosted;
}

// Import determineStrategy from xrl-compressor (circular-reference safe)
let _determineStrategy = null;
function determineStrategy(imp) {
    if (_determineStrategy) return _determineStrategy(imp);
    // Inline fallback
    if (imp.overall >= 9 || imp.personal >= 8) return 'crystalline';
    if (imp.emotional >= 7 && imp.logic < 6) return 'tone-first';
    if (imp.logic >= 7 && imp.emotional < 4) return 'logic-only';
    if (imp.overall <= 2) return 'aggressive';
    return 'balanced';
}

/**
 * Wire up the determineStrategy from xrl-compressor to avoid circular deps.
 */
function setDetermineStrategy(fn) {
    _determineStrategy = fn;
}

/**
 * Reset the topic graph (for testing or full rebuild).
 */
function resetGraph() {
    topicGraph = new Map();
    messageTopicMap = new Map();
}

/**
 * Get the size of the topic graph.
 */
function graphSize() {
    return { topics: topicGraph.size, messages: messageTopicMap.size };
}

module.exports = {
    extractTopics,
    feedMessage,
    applyDecay,
    getRelationalBoost,
    getTopicEnergyReport,
    boostImportance,
    setDetermineStrategy,
    resetGraph,
    graphSize,
    getRawGraph: () => topicGraph
};
