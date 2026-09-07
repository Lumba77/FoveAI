/**
 * foveai-solver knowledge base
 *
 * A local JSON store of confirmed problem → solution pairs.
 * Checked BEFORE calling any LLM — zero latency, zero API cost for known problems.
 *
 * Location: ~/.foveai/solutions.json
 *
 * Exports:
 *   lookup(errorText)             → Solution | null
 *   learn(problem, actionPlan)    → Solution  (adds to KB)
 *   fromLastFix(errorText, plan)  → Solution  (converts LLM fix to KB entry)
 *   remove(id)                    → bool
 *   stats()                       → { total, bySource, topPatterns }
 *   list()                        → Solution[]
 */

import fs from 'fs';
import os from 'os';
import path from 'path';
import crypto from 'crypto';

const KB_PATH = path.join(os.homedir(), '.foveai', 'solutions.json');
const CONFIDENCE_THRESHOLD = 0.80;   // min match score to apply without asking
const MAX_PATTERN_LEN      = 300;    // truncate stored patterns for KB size control

// ─── Types (JSDoc) ────────────────────────────────────────────────────────────
/**
 * @typedef {Object} Solution
 * @property {string}   id
 * @property {string}   pattern        — substring/regex that triggered this
 * @property {string}   description    — human-readable summary of the fix
 * @property {Array}    fileEdits      — [{filePath, content}]
 * @property {string[]} commands       — shell commands to run
 * @property {string}   source         — 'user' | 'llm' | 'auto'
 * @property {number}   successCount
 * @property {number}   failCount
 * @property {string}   createdAt
 * @property {string}   lastUsed
 * @property {string[]} tags           — e.g. ['python', 'import', 'venv']
 */

// ─── IO ───────────────────────────────────────────────────────────────────────
function loadKB() {
    try {
        if (fs.existsSync(KB_PATH)) {
            const raw = fs.readFileSync(KB_PATH, 'utf-8');
            const data = JSON.parse(raw);
            return Array.isArray(data.solutions) ? data : { solutions: [], version: 1 };
        }
    } catch (_) {}
    return { solutions: [], version: 1 };
}

function saveKB(data) {
    try {
        fs.mkdirSync(path.dirname(KB_PATH), { recursive: true });
        fs.writeFileSync(KB_PATH, JSON.stringify(data, null, 2), 'utf-8');
    } catch (e) {
        console.warn(`⚠️ [KB] Could not save: ${e.message}`);
    }
}

// ─── Matching Engine ──────────────────────────────────────────────────────────
/**
 * Score how well a solution's pattern matches the given error text.
 * Returns 0.0–1.0.
 */
function scoreMatch(pattern, errorText) {
    if (!pattern || !errorText) return 0;

    const err = errorText.toLowerCase();
    const pat = pattern.toLowerCase();

    // Exact substring — highest confidence
    if (err.includes(pat)) return 1.0;

    // Try as regex
    try {
        const rx = new RegExp(pattern, 'i');
        if (rx.test(errorText)) return 0.95;
    } catch (_) {}

    // Token overlap score
    const patTokens  = new Set(pat.split(/\W+/).filter(t => t.length > 3));
    const errTokens  = new Set(err.split(/\W+/).filter(t => t.length > 3));
    if (patTokens.size === 0) return 0;
    let hits = 0;
    for (const t of patTokens) if (errTokens.has(t)) hits++;
    return hits / patTokens.size;
}

// ─── Public API ───────────────────────────────────────────────────────────────

/**
 * Look up a solution for the given error text.
 * Returns the best match above CONFIDENCE_THRESHOLD, or null.
 */
export function lookup(errorText) {
    const data = loadKB();
    let best = null;
    let bestScore = 0;

    for (const sol of data.solutions) {
        const score = scoreMatch(sol.pattern, errorText);
        if (score > bestScore && score >= CONFIDENCE_THRESHOLD) {
            bestScore = score;
            best = { ...sol, _matchScore: score };
        }
    }

    if (best) {
        // Record usage
        const data2 = loadKB();
        const entry = data2.solutions.find(s => s.id === best.id);
        if (entry) {
            entry.lastUsed = new Date().toISOString();
            entry.successCount++;
            saveKB(data2);
        }
        console.log(`\n💡 [KB] Known solution found (score: ${(bestScore * 100).toFixed(0)}%)`);
        console.log(`   Pattern: ${best.pattern.slice(0, 80)}`);
        console.log(`   Fix: ${best.description}`);
    }

    return best;
}

/**
 * Convert a successful LLM fix into a KB entry.
 * Call this after a fix passes tests and is confirmed by the user.
 */
export function fromLastFix(errorText, actionPlan, source = 'llm') {
    const pattern = errorText.slice(0, MAX_PATTERN_LEN).trim();
    const entry = {
        id:           crypto.randomUUID(),
        pattern,
        description:  actionPlan.chatResponse?.slice(0, 200) || 'Auto-captured fix',
        fileEdits:    (actionPlan.fileEdits || []).map(e => ({
            filePath: e.filePath,
            // Store only the first 2KB of content — enough for small fixes
            content:  e.content?.slice(0, 2048) || '',
            truncated: (e.content?.length || 0) > 2048,
        })),
        commands:     actionPlan.commands || [],
        source,
        successCount: 1,
        failCount:    0,
        createdAt:    new Date().toISOString(),
        lastUsed:     new Date().toISOString(),
        tags:         extractTags(errorText, actionPlan),
    };
    return learn(entry);
}

/**
 * Manually add a solution entry to the KB.
 */
export function learn(entry) {
    const data = loadKB();

    // Deduplicate by pattern similarity
    const existing = data.solutions.find(s => scoreMatch(s.pattern, entry.pattern) > 0.90);
    if (existing) {
        existing.successCount++;
        existing.lastUsed = new Date().toISOString();
        // Merge commands if new ones added
        for (const cmd of (entry.commands || [])) {
            if (!existing.commands.includes(cmd)) existing.commands.push(cmd);
        }
        saveKB(data);
        console.log(`📚 [KB] Updated existing entry (id: ${existing.id})`);
        return existing;
    }

    data.solutions.push(entry);
    saveKB(data);
    console.log(`📚 [KB] Learned new solution (id: ${entry.id}) — KB now has ${data.solutions.length} entries`);
    return entry;
}

/**
 * Mark a KB entry as having failed (reduces its confidence over time).
 */
export function markFailed(id) {
    const data = loadKB();
    const entry = data.solutions.find(s => s.id === id);
    if (entry) {
        entry.failCount = (entry.failCount || 0) + 1;
        // Auto-remove if failure rate > 50% and > 3 uses
        const total = entry.successCount + entry.failCount;
        if (total >= 4 && entry.failCount / total > 0.5) {
            data.solutions = data.solutions.filter(s => s.id !== id);
            console.log(`🗑️ [KB] Auto-removed unreliable entry (id: ${id})`);
        }
        saveKB(data);
    }
}

/**
 * Remove a solution by ID.
 */
export function remove(id) {
    const data = loadKB();
    const before = data.solutions.length;
    data.solutions = data.solutions.filter(s => s.id !== id);
    saveKB(data);
    return data.solutions.length < before;
}

/**
 * KB statistics.
 */
export function stats() {
    const data = loadKB();
    const sols  = data.solutions;
    const bySource = {};
    for (const s of sols) bySource[s.source] = (bySource[s.source] || 0) + 1;
    const top = [...sols]
        .sort((a, b) => b.successCount - a.successCount)
        .slice(0, 5)
        .map(s => ({ pattern: s.pattern.slice(0, 60), hits: s.successCount, source: s.source }));
    return { total: sols.length, bySource, topPatterns: top, path: KB_PATH };
}

/**
 * List all solutions (for `foveai-solver kb list`).
 */
export function list() {
    return loadKB().solutions;
}

// ─── Tag Extraction ───────────────────────────────────────────────────────────
const TAG_PATTERNS = [
    [/python|\.py|pip|venv|import|module/i, 'python'],
    [/node|npm|yarn|\.js|\.ts|require/i,    'node'],
    [/rust|cargo|\.rs/i,                     'rust'],
    [/go |golang|\.go/i,                     'go'],
    [/docker|container/i,                    'docker'],
    [/port|eaddrinuse|address already/i,     'network'],
    [/permission|eacces|access denied/i,     'permissions'],
    [/module not found|cannot find/i,        'missing-dep'],
    [/syntax error|unexpected token/i,       'syntax'],
    [/soul|stardust|tokenslayer|foveai/i,     'foveai'],
];

function extractTags(errorText, actionPlan) {
    const text = `${errorText} ${actionPlan?.chatResponse || ''}`.toLowerCase();
    return TAG_PATTERNS.filter(([rx]) => rx.test(text)).map(([, tag]) => tag);
}

// ─── CLI direct invocation ────────────────────────────────────────────────────
// node src/knowledge-base.js stats
// node src/knowledge-base.js list
// node src/knowledge-base.js remove <id>
const [,, cmd, arg] = process.argv;
if (cmd === 'stats') {
    const s = stats();
    console.log(`\n📚 Lumax Solver Knowledge Base`);
    console.log(`   Path:    ${s.path}`);
    console.log(`   Total:   ${s.total} solutions`);
    console.log(`   Sources: ${JSON.stringify(s.bySource)}`);
    if (s.topPatterns.length) {
        console.log(`\n   Top patterns:`);
        s.topPatterns.forEach((p, i) => console.log(`     ${i+1}. [${p.hits}x] ${p.pattern}`));
    }
} else if (cmd === 'list') {
    list().forEach(s => {
        console.log(`\n[${s.id.slice(0,8)}] ${s.pattern.slice(0,80)}`);
        console.log(`  Source: ${s.source} | Hits: ${s.successCount} | Tags: ${s.tags?.join(', ')}`);
    });
} else if (cmd === 'remove' && arg) {
    const ok = remove(arg);
    console.log(ok ? `✅ Removed ${arg}` : `❌ Not found: ${arg}`);
}
