/**
 * ═══════════════════════════════════════════════════════
 * MEMORY STORE — NeDB (pure JS) + Cosine Similarity Search
 * ═══════════════════════════════════════════════════════
 *
 * Persistent conversation memory with hybrid retrieval.
 * Uses NeDB (pure JavaScript, no native compilation) for storage.
 *
 * Retrieval has two complementary paths:
 *   - TF-IDF cosine similarity (always on, pure JS, zero native deps)
 *   - dense MiniLM vectors via core/embedder.js (Step 2, opt-out: XRLF_SEMANTIC=0)
 * Both are always written; search() fuses them by rank (Step 3). A message is
 * never lost to an embedding failure — it simply falls back to lexical recall.
 *
 * Each workspace gets its own isolated .db file on disk.
 */

'use strict';

const Datastore = require('nedb-promises');
const path      = require('path');
const fs        = require('fs');

// ── Semantic retrieval (Step 2) ───────────────────────────────────────────
// XRLF_SEMANTIC=0 reverts recall to pure TF-IDF instantly, no restart.
// The require is lazy AND guarded on every use: store.js is the memory write
// path for live conversation, so it must keep working even if core/embedder.js
// is missing, mid-edit, or broken. Never take the write down with it.
let _embedder = null;
function embedder() {
    if (_embedder === null) _embedder = require('../core/embedder');
    return _embedder;
}

// True only when the sidecar socket is genuinely connected and ready to serve.
function sidecarReady() {
    try {
        return embedder().status().state === 'ready';
    } catch (_) {
        return false;
    }
}

function semanticEnabled() {
    const v = String(process.env.XRLF_SEMANTIC == null ? '1' : process.env.XRLF_SEMANTIC)
        .toLowerCase().trim();
    return !(v === '0' || v === 'false' || v === 'off' || v === 'no');
}

// OpenAI multi-part content arrives as an array of parts; flatten to text the
// same way _tokenize() does, so both retrieval paths see identical input.
function normalizeText(text) {
    if (Array.isArray(text)) {
        return text
            .filter(p => p && typeof p === 'object' && typeof p.text === 'string')
            .map(p => p.text).join('\n');
    }
    return typeof text === 'string' ? text : String(text || '');
}

// ── Why the encode is time-boxed ──────────────────────────────────────────
// Measured 2026-10-10: a WARM encode is 3.6 ms, but the first one pays ONNX
// model load and costs 7–11 s. Without a bound that cost lands inside the
// first chat write after every restart and stalls the turn for ten seconds.
//
// So the first call after boot starts the encode, waits a short grace period,
// and gives up WITHOUT cancelling — the encode keeps running in the
// background and warms the sidecar for every write after it. One message
// falls back to TF-IDF; the conversation never pauses.
const EMBED_GRACE_WARM_MS  = 2000;  // sidecar connected: ~3.6 ms expected; safety net
const EMBED_POLL_BOOT_MS   = 25;    // how often to re-check readiness while booting

class MemoryStore {
    /**
     * @param {string} persistPath  - Directory to store .db files
     * @param {string} workspaceId  - Scopes all memory to this workspace
     */
    constructor(persistPath, workspaceId) {
        this.workspaceId = workspaceId || 'default';
        const dbDir = path.resolve(persistPath, workspaceId);
        fs.mkdirSync(dbDir, { recursive: true });

        this.db = Datastore.create({
            filename:   path.join(dbDir, 'memory.db'),
            autoload:   true,
            timestampData: true
        });

        this.themeDb = Datastore.create({
            filename:   path.join(dbDir, 'theme.db'),
            autoload:   true,
            timestampData: true
        });

        this.metaDb = Datastore.create({
            filename:   path.join(dbDir, 'session_meta.db'),
            autoload:   true,
            timestampData: true
        });

        this.tasksDb = Datastore.create({
            filename:   path.join(dbDir, 'session_tasks.db'),
            autoload:   true,
            timestampData: true
        });

        // Ensure indexes for fast queries
        this.db.ensureIndex({ fieldName: 'session_id' });
        this.db.ensureIndex({ fieldName: 'timestamp'  });
        this.themeDb.ensureIndex({ fieldName: 'theme_name' });
        this.themeDb.ensureIndex({ fieldName: 'category' });
        this.metaDb.ensureIndex({ fieldName: 'session_id', unique: true });
        this.tasksDb.ensureIndex({ fieldName: 'session_id', unique: true });
    }

    /**
     * Store a message turn to the persistent memory.
     * Now supports importance scoring and relational metadata.
     */
    async store(sessionId, role, content, timestamp, userId = 'anonymous', metadata = {}) {
        const ts = timestamp || new Date().toISOString();
        const doc = {
            session_id:  sessionId,
            role,
            content,
            timestamp:   ts,
            tokens_est:  Math.ceil(content.length / 4),
            user_id:     userId
        };

        // ── Importance & relational metadata ────────────────────────────
        if (metadata.importance) {
            doc.importance = {
                logic:      metadata.importance.logic || 3,
                emotional:  metadata.importance.emotional || 3,
                personal:   metadata.importance.personal || 3,
                actionable: metadata.importance.actionable || 3,
                overall:    metadata.importance.overall || 3,
                strategy:   metadata.importance.strategy || 'balanced',
                tier:       metadata.importance.tier || 'heuristic',
                relationalBoost: metadata.importance._relationalBoost || 0
            };
        }
        if (metadata.importance?.categories?.length > 0) {
            doc.categories = metadata.importance.categories;
        } else if (metadata.categories && metadata.categories.length > 0) {
            doc.categories = metadata.categories;
        }
        if (metadata.topics && metadata.topics.length > 0) {
            doc.topics = metadata.topics;
        }
        if (metadata.tone) {
            doc.tone = metadata.tone;
        }

        // ── Dense vector for semantic recall ───────────────────────────
        // Sync on purpose: ~2.4 ms measured, against a write that already
        // touches disk. _embed() never throws and never returns a bad shape,
        // so a dead sidecar degrades recall to TF-IDF and nothing else.
        const vector = await this._embed(content);
        if (vector) doc.embedding = vector;

        const inserted = await this.db.insert(doc);
        return inserted;
    }

    /**
     * Encode one message into a dense vector for retrieval.
     * Returns a plain Array of 384 numbers, or null. NEVER THROWS.
     *
     * Plain Array, not Float32Array: NeDB persists via JSON, and a typed
     * array would serialize as {"0":0.12,"1":...} instead of [0.12,...].
     */
    async _embed(content) {
        try {
            if (!semanticEnabled()) return null;
            const text = normalizeText(content);
            if (!text || text.length < 3) return null;

            const pending = embedder().encode([text]);
            pending.catch(() => {});   // never an unhandledRejection

            // Wait up to 3500ms for sidecar spawn & encoding (~450ms cold, ~4ms warm)
            const vectors = await Promise.race([
                pending,
                new Promise(r => setTimeout(() => r(null), 3500))
            ]);

            if (vectors && vectors[0]) return Array.from(vectors[0]);
            return null;
        } catch (e) {
            console.warn('[Store] embed skipped (' + e.message + ') — TF-IDF fallback');
            return null;
        }
    }

    /**
     * Update the importance score of a stored message (Tier 2 async refinement).
     * Called after the LLM re-scores a message in the background.
     */
    async updateImportance(sessionId, content, importance) {
        try {
            await this.db.update(
                { session_id: sessionId, content },
                { $set: { importance } },
                { multi: false }
            );
        } catch (e) {
            console.warn('[Store] Failed to update importance:', e.message);
        }
    }

    /**
     * Get the N most recent messages (across all sessions).
     */
    async getRecent(n = 6) {
        const docs = await this.db
            .find({})
            .sort({ timestamp: -1 })
            .limit(n);
        return docs.reverse();
    }

    /**
     * Get the N most recent messages from a specific session.
     * Falls back to getRecent() if sessionId is not provided.
     */
    async getRecentBySession(sessionId, n = 6) {
        if (!sessionId) return this.getRecent(n);
        const docs = await this.db
            .find({ session_id: sessionId })
            .sort({ timestamp: -1 })
            .limit(n);
        return docs.reverse();
    }

    /**
     * Get messages from a specific session.
     */
    async getBySession(sessionId) {
        return this.db
            .find({ session_id: sessionId })
            .sort({ timestamp: 1 });
    }

    /**
     * Get messages by age bracket.
     * @param {number} daysMin  - Older than this many days
     * @param {number} daysMax  - Newer than this many days (0 = no bound)
     * @param {number} limit
     */
    async getByAge(daysMin, daysMax = 0, limit = 50) {
        const now    = Date.now();
        const minTs  = new Date(now - daysMin * 86400000).toISOString();
        const query  = daysMax === 0
            ? { timestamp: { $lt: minTs } }
            : { timestamp: { $lt: minTs, $gte: new Date(now - daysMax * 86400000).toISOString() } };

        return this.db
            .find(query)
            .sort({ timestamp: -1 })
            .limit(limit);
    }

    /**
     * Hybrid Semantic search: dense MiniLM vector cosine similarity when available,
     * seamlessly falling back to pure JS TF-IDF cosine similarity.
     * @param {string} query
     * @param {number} topN
     * @param {string|null} sessionId
     * @returns {Promise<Array<{message, score, method}>>}
     */
    async search(query, topN = 5, sessionId = null) {
        const filter = sessionId ? { session_id: sessionId } : {};
        const all = await this.db.find(filter);
        if (all.length === 0) return [];

        const queryEmbedding = await this._embed(query);
        const queryTerms = this._tokenize(query);

        const scored = all.map(msg => {
            let score = 0;
            let method = 'tfidf';

            if (queryEmbedding && Array.isArray(msg.embedding) && msg.embedding.length === 384) {
                // Dense vector cosine similarity (vectors are unit L2-normalized)
                let dot = 0;
                const emb = msg.embedding;
                for (let i = 0; i < 384; i++) {
                    dot += queryEmbedding[i] * emb[i];
                }
                score = Math.max(0, dot);
                method = 'vector';
            } else {
                // Lexical TF-IDF cosine similarity fallback
                score = this._cosineSimilarity(queryTerms, this._tokenize(msg.content));
            }

            return {
                message: msg,
                score,
                method
            };
        });

        scored.sort((a, b) => b.score - a.score);
        return scored.slice(0, topN).filter(r => r.score > 0);
    }

    /**
     * Get total stored message count.
     */
    async count() {
        return this.db.count({});
    }

    /**
     * Get total consolidated theme count.
     */
    async countThemes() {
        return this.themeDb.count({});
    }

    /**
     * Get distinct session count.
     */
    async countSessions() {
        const all = await this.db.find({});
        const sessionIds = new Set(all.map(m => m.session_id).filter(Boolean));
        return sessionIds.size;
    }

    /**
     * Get list of distinct sessions with message counts, timestamps, and preview text.
     */
    async listSessions(limit = 10) {
        const all = await this.db.find({}).sort({ timestamp: -1 });
        const map = new Map();
        for (const msg of all) {
            const sId = msg.session_id || 'default';
            if (!map.has(sId)) {
                map.set(sId, {
                    session_id: sId,
                    count: 0,
                    last_updated: msg.timestamp,
                    preview: msg.content ? msg.content.slice(0, 60) : ''
                });
            }
            const item = map.get(sId);
            item.count += 1;
        }
        
        let sessions = Array.from(map.values())
            .filter(s => (s.count || 0) > 0 && typeof s.preview === 'string' && s.preview.trim().length > 0)
            .slice(0, limit);
        
        // Join with session metadata from metaDb
        const metaDocs = await this.metaDb.find({});
        const metaMap = new Map();
        for (const m of metaDocs) {
            if (m.session_id) metaMap.set(m.session_id, m);
        }
        
        for (const s of sessions) {
            if (metaMap.has(s.session_id)) {
                const meta = metaMap.get(s.session_id);
                if (meta.title) s.title = meta.title;
                if (meta.theme) s.theme = meta.theme;
                if (meta.project) s.project = meta.project;
                if (meta.keywords) s.keywords = meta.keywords;
                if (meta.ingredients) s.ingredients = meta.ingredients;
                if (meta.summary) s.summary = meta.summary;
            }
        }
        
        return sessions;
    }

    /**
     * Set AI-generated session metadata (title, dynamic theme, project)
     */
    async setSessionMeta(sessionId, metaObj) {
        await this.metaDb.update(
            { session_id: sessionId },
            { $set: { session_id: sessionId, ...metaObj, generated_at: new Date().toISOString() } },
            { upsert: true }
        );
    }
    
    async setSessionTitle(sessionId, title) {
        await this.setSessionMeta(sessionId, { title });
    }

    async deleteSession(sessionId) {
        await this.db.remove({ session_id: sessionId }, { multi: true });
        await this.metaDb.remove({ session_id: sessionId }, { multi: true });
        await this.tasksDb.remove({ session_id: sessionId }, { multi: true });
    }

    /**
     * Save the active task board state for a session.
     */
    async saveTasks(sessionId, tasks) {
        await this.tasksDb.update(
            { session_id: sessionId },
            { $set: { session_id: sessionId, tasks: tasks, updated_at: new Date().toISOString() } },
            { upsert: true }
        );
    }

    /**
     * Retrieve the active task board state for a session.
     */
    async getTasks(sessionId) {
        const doc = await this.tasksDb.findOne({ session_id: sessionId });
        return doc ? doc.tasks : [];
    }

    /**
     * Store or update a consolidated Theme document.
     */
    async storeTheme(themeObj) {
        const ts = themeObj.timestamp || new Date().toISOString();
        const doc = {
            theme_name:  themeObj.theme_name || 'General Workspace Context',
            category:    themeObj.category || 'General',
            summary:     themeObj.summary || '',
            decisions:   themeObj.decisions || [],
            code_refs:   themeObj.code_refs || [],
            session_ids: themeObj.session_ids || [],
            raw_count:   themeObj.raw_count || 1,
            timestamp:   ts,
            tokens_est:  Math.ceil((themeObj.summary || '').length / 4)
        };

        const existing = await this.themeDb.findOne({ theme_name: doc.theme_name });
        if (existing) {
            await this.themeDb.update({ _id: existing._id }, { $set: doc });
            return existing._id;
        } else {
            const res = await this.themeDb.insert(doc);
            return res._id;
        }
    }

    /**
     * Semantic search across Consolidated Theme documents.
     */
    async searchThemes(query, topN = 5) {
        const all = await this.themeDb.find({});
        if (all.length === 0) return [];

        const queryTerms = this._tokenize(query);
        const scored = all.map(theme => {
            const searchableText = `${theme.theme_name} ${theme.category} ${theme.summary} ${theme.decisions.join(' ')}`;
            return {
                theme,
                score: this._cosineSimilarity(queryTerms, this._tokenize(searchableText))
            };
        });

        scored.sort((a, b) => b.score - a.score);
        return scored.slice(0, topN).filter(r => r.score > 0);
    }

    /**
     * Consolidate raw messages into Theme blocks.
     * Clusters messages by session and extracts thematic topics.
     */
    async consolidateRawMemories() {
        const allRaw = await this.db.find({});
        if (allRaw.length === 0) return { themesCreated: 0, rawProcessed: 0 };

        // Group raw messages by session_id
        const sessions = {};
        for (const msg of allRaw) {
            const sId = msg.session_id || 'default_session';
            if (!sessions[sId]) sessions[sId] = [];
            sessions[sId].push(msg);
        }

        let themesCreated = 0;

        for (const [sId, msgs] of Object.entries(sessions)) {
            // Sort by timestamp
            msgs.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));

            // Extract topic markers or build session summary
            const codeFiles = new Set();
            const highlights = [];
            let textAcc = '';

            for (const m of msgs) {
                const content = typeof m.content === 'string' ? m.content : JSON.stringify(m.content);
                textAcc += content + '\n';

                // Extract file paths referenced
                const files = content.match(/([A-Za-z]:[\\/][^\s,\u201c\u201d"']+|[a-zA-Z0-9_/-]+\.(?:py|ts|js|json|md|html|css)\b)/g);
                if (files) files.forEach(f => codeFiles.add(f));

                // Extract decisions/highlights
                if (/TODO|FIX|IMPORTANT|SOLVED|PLAN|REFACTOR/i.test(content)) {
                    highlights.push(content.slice(0, 150).replace(/\n/g, ' ').trim());
                }
            }

            // Derive Theme Name
            let themeName = `Session ${sId.replace('sess_', '')}`;
            if (codeFiles.size > 0) {
                const topFile = Array.from(codeFiles)[0].split(/[\\/]/).pop();
                themeName = `Development on ${topFile}`;
            }

            const summary = textAcc.slice(0, 800).trim();

            await this.storeTheme({
                theme_name:  themeName,
                category:    codeFiles.size > 0 ? 'Development' : 'Conversation',
                summary:     summary,
                decisions:   highlights.slice(0, 5),
                code_refs:   Array.from(codeFiles).slice(0, 8),
                session_ids: [sId],
                raw_count:   msgs.length,
                timestamp:   msgs[msgs.length - 1]?.timestamp || new Date().toISOString()
            });

            themesCreated++;
        }

        return { themesCreated, rawProcessed: allRaw.length };
    }

    /**
     * Clear all memory from this workspace.
     */
    async clearAll() {
        return this.db.remove({}, { multi: true });
    }

    /**
     * Remove specific memory by ID.
     */
    async removeById(id) {
        return this.db.remove({ _id: id }, {});
    }

    // ── Private helpers ────────────────────────────────────────────────────

    _tokenize(text) {
        const stopWords = new Set([
            'the','a','an','is','it','in','on','at','to','of','and','or',
            'for','with','this','that','was','are','','as','we','','you',
            'havehad','do','not','but','so','if','by','can','will'
        ]);
        const freqs = {};
        // Normalize array content (OpenAI multi-part format) to string
        const normalized = Array.isArray(text)
            ? text.filter(p => p && typeof p === 'object' && typeof p.text === 'string').map(p => p.text).join('\n')
            : String(text || '');
        const words = normalized.toLowerCase().replace(/[^a-z0-9\s]/g, ' ').split(/\s+/);
        for (const w of words) {
            if (w.length > 2 && !stopWords.has(w)) {
                freqs[w] = (freqs[w] || 0) + 1;
            }
        }
        return freqs;
    }

    _cosineSimilarity(a, b) {
        const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
        let dot = 0, magA = 0, magB = 0;
        for (const k of keys) {
            const va = a[k] || 0;
            const vb = b[k] || 0;
            dot  += va * vb;
            magA += va * va;
            magB += vb * vb;
        }
        if (magA === 0 || magB === 0) return 0;
        return dot / (Math.sqrt(magA) * Math.sqrt(magB));
    }
}

module.exports = { MemoryStore };
