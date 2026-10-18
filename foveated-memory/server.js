/**
 * ═══════════════════════════════════════════════════════
 * FOVEATED MEMORY PROXY — Main Server
 * ═══════════════════════════════════════════════════════
 *
 * OpenAI-compatible proxy server that gives any LLM infinite,
 * on-demand foveated memory using XRL Active Recall.
 *
 * Usage:
 *   node server.js [--config path/to/config.json]
 *   foveated-memory --upstream http://localhost:1234 --port 8400
 *
 * Point any OpenAI-compatible client at this server instead of
 * your LLM backend. Change one URL — every model gains memory.
 */

'use strict';

// ── Inline .env loader (no external dependency) ──────────────────────
// NSSM services don't auto-load .env files, so we do it manually.
// Loads ONLY the local .env in this directory — the xrlf-model proxy is
// fully self-contained and does NOT read from the parent XRLF .env.
(function loadEnv() {
    const fs = require('fs');
    const path = require('path');

    const localEnvPath = path.resolve(__dirname, '.env');
    try {
        const raw = fs.readFileSync(localEnvPath, 'utf8');
        for (const line of raw.split('\n')) {
            const trimmed = line.trim();
            if (!trimmed || trimmed.startsWith('#')) continue;
            const eqIdx = trimmed.indexOf('=');
            if (eqIdx === -1) continue;
            const key = trimmed.slice(0, eqIdx).trim();
            const val = trimmed.slice(eqIdx + 1).trim().replace(/^["']|["']$/g, '');
            if (!(key in process.env)) process.env[key] = val;
        }
        console.log('[XRLF] Loaded local .env configuration');
    } catch (e) { /* .env optional — silently ignore if missing */ }
})();

const express = require('express');
const http = require('http');
const fetch   = require('node-fetch');
const path    = require('path');
const fs      = require('fs');
const { execFile, spawn } = require('child_process');
const { v4: uuidv4 } = require('uuid');
const net     = require('net');


// ============================================================
// REACTOR MASTER KILL SWITCH (Step 1)
// ============================================================
// XRLF_REPO_ENABLED=false -> the repo becomes COLD:
//   - no global caps
//   - no context override
//   - no foveation override
//   - no memory override
//   - no routing override
//   - no interference with your proxy / assistants
//
// Individual override isolators (Step 2A) can be toggled on top:
//   XRLF_CONTEXT_OVERRIDE, XRLF_CAPABILITY_OVERRIDE,
//   XRLF_FOVEATION_OVERRIDE
// Each defaults to the opposite of XRLF_REPO_ENABLED (i.e. disabled
// when the repo is cold), so the master switch fully isolates the repo.
const REPO_ENABLED = (() => {
    const v = (process.env.XRLF_REPO_ENABLED || "false").toLowerCase().trim();
    return v === "true" || v === "1" || v === "on";
})();
const REPO_CONTEXT_OVERRIDE = (() => {
    const v = (process.env.XRLF_CONTEXT_OVERRIDE || (REPO_ENABLED ? "true" : "false")).toLowerCase().trim();
    return v === "true" || v === "1" || v === "on";
})();
const REPO_CAPABILITY_OVERRIDE = (() => {
    const v = (process.env.XRLF_CAPABILITY_OVERRIDE || (REPO_ENABLED ? "true" : "false")).toLowerCase().trim();
    return v === "true" || v === "1" || v === "on";
})();
const REPO_FOVEATION_OVERRIDE = (() => {
    const v = (process.env.XRLF_FOVEATION_OVERRIDE || (REPO_ENABLED ? "true" : "false")).toLowerCase().trim();
    return v === "true" || v === "1" || v === "on";
})();

// ── Proxy Mode ──────────────────────────────────────────────────────
// XRLF_PROXY_MODE: routing (default) | transparent (bypass all features)
// transparent mode: just passes through to upstream, no foveation, no HUD, no compression
const PROXY_MODE = (() => {
    const v = (process.env.XRLF_PROXY_MODE || "routing").toLowerCase().trim();
    return v === "transparent" ? "transparent" : "routing";
})();

if (PROXY_MODE === "transparent") {
    console.log("[ProxyMode] 🔄 TRANSPARENT MODE — bypassing all foveation features, direct passthrough only");
} else {
    console.log("[ProxyMode] 🔀 ROUTING MODE — foveation, HUD, and compression enabled");
}

if (!REPO_ENABLED) {
    console.log("[XRLF] REACTOR COLD - repo overrides DISABLED (XRLF_REPO_ENABLED=false)");
    console.log("[XRLF]    context_override=" + REPO_CONTEXT_OVERRIDE + " capability_override=" + REPO_CAPABILITY_OVERRIDE + " foveation_override=" + REPO_FOVEATION_OVERRIDE);
} else {
    console.log("[XRLF] REACTOR HOT - repo overrides enabled (XRLF_REPO_ENABLED=true)");
    console.log("[XRLF]    context_override=" + REPO_CONTEXT_OVERRIDE + " capability_override=" + REPO_CAPABILITY_OVERRIDE + " foveation_override=" + REPO_FOVEATION_OVERRIDE);
}


// ── Diagnostic Logger ──────────────────────────────────────────────────────
const DIAG_LOG_FILE = path.join(__dirname, 'proxy_diagnostics.log');
function logDiagnostic(stage, data) {
    const timestamp = new Date().toISOString();
    const entry = `[${timestamp}] [${stage}] ${JSON.stringify(data, null, 2)}\n---\n`;
    fs.appendFileSync(DIAG_LOG_FILE, entry, 'utf8');
}

// ── Platform Detection ──────────────────────────────────────────────────────
const IS_LINUX = process.platform === 'linux';
const IS_WIN = process.platform === 'win32';

const WT_EXE = process.env.WT_EXE_PATH || 'wt.exe';

// ── PowerShell Path Auto-Detection (Windows only) ───────────────────────────
function resolvePwshPath() {
    if (!IS_WIN) return 'bash'; // Linux doesn't need PowerShell
    const fs = require('fs');

    // 1. Explicit override via env var (if it exists on disk)
    if (process.env.PWSH_PATH && fs.existsSync(process.env.PWSH_PATH)) {
        return process.env.PWSH_PATH;
    }

    // 2. Common PowerShell 7 install locations
    const candidates = [
        'C:\\Program Files\\PowerShell\\7\\pwsh.exe',
        'C:\\Program Files (x86)\\PowerShell\\7\\pwsh.exe',
        process.env.LOCALAPPDATA ? `${process.env.LOCALAPPDATA}\\Microsoft\\WindowsApps\\pwsh.exe` : null,
        process.env.ProgramFiles ? `${process.env.ProgramFiles}\\PowerShell\\7\\pwsh.exe` : null,
        process.env['ProgramFiles(x86)'] ? `${process.env['ProgramFiles(x86)']}\\PowerShell\\7\\pwsh.exe` : null
    ].filter(Boolean);

    for (const candidate of candidates) {
        if (fs.existsSync(candidate)) {
            return candidate;
        }
    }

    // 3. Try `where pwsh` on PATH
    try {
        const { execSync } = require('child_process');
        const result = execSync('where pwsh', { encoding: 'utf8', windowsHide: true }).trim();
        if (result) return result.split(/\r?\n/)[0];
    } catch (_) { /* not on PATH */ }

    // 4. Fallback: built-in Windows PowerShell (always available)
    return 'powershell.exe';
}

const PWSH = resolvePwshPath();
console.log(`[PWSH] Using PowerShell: ${PWSH}`);

const { MemoryStore }        = require('./memory/store');
const { buildRingBlock }     = require('./core/ring-builder');
const { buildMembraneHUD }   = require('./core/membrane-bridge');
const { trackFile, getSessionDiagnostics, lintSession } = require('./core/linter-feedback');
const { patchMessages }      = require('./core/system-prompt-patch');
const { detectRecall, collectStream, collectJson, buildMemoryInjection }
                              = require('./core/recall-interceptor');
const { compressContext } = require('./core/context-compressor');
const { getAuthManager, FEATURE_CATALOG } = require('./core/auth-manager');
const { getSwarmRouter } = require('./core/swarm-router');
const { saveContinuity, loadContinuity, buildResumeContext, getHistory: getContinuityHistory, clearContinuity } = require('./core/memory-continuity');
const { checkQuality, quickCheck } = require('./core/quality-guard');
const { getBudget, getState: getHealerState, onSuccess, onFailure, applyBudget, injectWarning, resetBudget, setBudget, reconfigureForProvider } = require('./core/context-healer');
const { extractFromMessages, restoreToMessages, getStats: getPreserverStats, configure: configurePreserver } = require('./core/code-preserver');
const { saveShadowBlock, getShadowBlock, searchShadowBlocks, buildZoomInjection, getStats: getShadowStats } = require('./core/shadow-context');
const { detectSaccade, detectAccommodate, parseSaccadeTarget, parseAccommodate, validateSaccade, executeAccommodate, buildRestructuredFovea } = require('./core/saccade-engine');
const { handleTemporalZoom } = require('./core/temporal-zoom');
const { score: scoreImportance, refine: refineImportance, summarizeWithImportance } = require('./core/importance-scorer');
const { runAudit, tick: auditTick, startAutoAudit } = require('./core/memory-auditor');
const { classifyBatch, formatStats: formatRetinaStats, VALUE } = require('./core/retina');
const { applyProfile, saveActiveModel, loadActiveModel, listProfiles } = require('./core/model-profile-loader');
const residency = require('./core/residency');
const { 
    processButterflyEffect, 
    setEmotionalState, 
    getCurrentEmotion,
    updateProximity,
    getProximityState 
} = require('./core/emotional-resonance');

// ── XRLF Unified Compression Utilities (self-contained, no external deps) ────────
const RE_THINKING = /<thinking>.*?<\/thinking>/gsi;
function stripThinking(content) {
    if (typeof content !== 'string') return content;
    return content.replace(RE_THINKING, '[thought]').trim();
}

// ── Avatar-protocol tag stripping (client-facing output boundary) ─────────────
// XRLF persona emits machine directives inline: <emotion:…>, <movement:…>,
// <thought:…>, <micro:…>, <mode:…>, <recall:…> etc. These belong to the
// motor/XR/TTS layers — API consumers (IDE plugins, scripts) get them stripped.
// Callers that need the raw stream send `xrlf_raw: true` or X-FoveAI-Raw: 1.
// Upstream reasoning (reasoning_content) is surfaced in its own field instead
// of being inlined — thinking models stay supported without leaking into prose.
const PROTOCOL_TAGS = new Set([
    'think', 'thinking', 'thought', 'emotion', 'movement', 'micro', 'mode',
    'recall', 'zoom', 'saccade', 'accommodate', 'temporal_zoom',
    'action', 'motor', 'gaze', 'posture', 'prosody', 'sfx', 'sound', 'persona',
    'self', 'dev', 'audio', 'animation', 'request'
]);
const PROTOCOL_BLOCK_TAGS = new Set(['think', 'thinking', 'thought']); // paired <x>…</x>
// Chat-template tokens that must never reach clients — stripped in ANY form
// (<x>, </x>, <|x|>) since they carry no user-facing meaning.
const TEMPLATE_TOKENS = new Set([
    'start_of_turn', 'end_of_turn', 'im_start', 'im_end', 'turn',
    'response', 'eot', 'eos'
]);

// Stateful stripper — safe across arbitrary chunk boundaries (SSE deltas can
// split a tag mid-name). Unknown tags like <div> pass through untouched so
// code/HTML in replies is preserved. Stripped <thought:>/<think> content is
// captured into a reasoning buffer — thinking stays available to callers via
// reasoning_content, just out of `content`.
function createTagStripper() {
    let pending = '';       // chars that might be an incomplete tag
    let blockTag = null;    // name of the open <think>/<thinking>/<thought> block
    let blockBuf = '';      // in-progress text of the open block
    let inParenThought = false; // inside a (thought:…) paren marker
    const thoughtParts = [];// captured thought/reasoning fragments
    return {
        feed(chunk) {
            const s = pending + chunk;
            pending = '';
            let out = '', i = 0;
            while (i < s.length) {
                if (inParenThought) {
                    // Inside (thought:… — capture until the closing paren.
                    const close = s.indexOf(')', i);
                    if (close === -1) {
                        // hold a trailing '(' — could start a nested marker…
                        // parens inside thought text are rare; treat the whole
                        // remainder as thought and wait for the closer.
                        blockBuf += s.slice(i);
                        break;
                    }
                    blockBuf += s.slice(i, close);
                    // a chunk-split "(thought" + ":" leaves a leading colon
                    const parenThought = blockBuf.trim().replace(/^[:：\-–—]\s*/, '');
                    if (parenThought) thoughtParts.push(parenThought);
                    blockBuf = '';
                    inParenThought = false;
                    i = close + 1;
                    continue;
                }
                if (blockTag) {
                    const closer = '</' + blockTag;
                    const close = s.indexOf(closer, i);
                    if (close === -1) {
                        // possible partial closer at buffer end — hold the tail
                        const tailStart = Math.max(i, s.length - closer.length);
                        const tail = s.slice(tailStart);
                        const partial = tail.indexOf('</');
                        let hold = -1;
                        if (partial !== -1 && closer.startsWith(tail.slice(partial))) {
                            hold = partial;
                        }
                        // capture block content as reasoning, minus held tail
                        blockBuf += hold !== -1 ? s.slice(i, tailStart + hold) : s.slice(i);
                        if (hold !== -1) pending = tail.slice(hold);
                        break;
                    }
                    blockBuf += s.slice(i, close);
                    if (blockBuf.trim()) thoughtParts.push(blockBuf.trim());
                    blockBuf = '';
                    const gt = s.indexOf('>', close);
                    if (gt === -1) { pending = s.slice(close); break; }
                    i = gt + 1;
                    blockTag = null;
                    continue;
                }
                // Scan for the next marker start: '<' (tag) or '(' (paren
                // thought) — whichever comes first.
                const lt = s.indexOf('<', i);
                const po = s.indexOf('(', i);
                const next = lt === -1 ? po : (po === -1 ? lt : Math.min(lt, po));
                if (next === -1) { out += s.slice(i); break; }
                out += s.slice(i, next);

                if (s[next] === '(') {
                    const rest = s.slice(next);
                    const pm = rest.match(/^\(\s*(thought|think|thinking)\s*:?/i);
                    if (pm) {
                        inParenThought = true;
                        i = next + pm[0].length;
                        continue;
                    }
                    // Buffer ends in a possible marker prefix — hold it.
                    const head = rest.match(/^\(\s*([a-z]*)$/i);
                    if (head && (('thought'.startsWith(head[1].toLowerCase())) ||
                                 ('think'.startsWith(head[1].toLowerCase())) ||
                                 ('thinking'.startsWith(head[1].toLowerCase())))) {
                        pending = rest;
                        break;
                    }
                    out += '('; // ordinary paren — keep literally
                    i = next + 1;
                    continue;
                }

                const rest = s.slice(next);
                const m = rest.match(/^<(\/?)(\|?[a-zA-Z_]+\|?)([^>]*)>/);
                if (m) {
                    const name = m[2].replace(/\|/g, '').toLowerCase();
                    const isClose = m[1] === '/';
                    // Markers use the <name:value> form — require the colon so
                    // plain HTML/XML in code output (<audio controls>, <meta>)
                    // survives. Block tags and stray closers strip unconditionally.
                    // Template tokens (<start_of_turn>, <|im_end|>…) strip in
                    // every form — they are never user-facing content.
                    const isMarker = m[3].startsWith(':');
                    if (TEMPLATE_TOKENS.has(name) ||
                        (PROTOCOL_TAGS.has(name) && (isClose || isMarker || PROTOCOL_BLOCK_TAGS.has(name)))) {
                        if (!isClose && isMarker && (name === 'thought' || name === 'think' || name === 'thinking')) {
                            // <thought:the idea…> — capture the marker value
                            const v = m[3].slice(1).trim();
                            if (v) thoughtParts.push(v);
                        } else if (!isClose && !isMarker && PROTOCOL_BLOCK_TAGS.has(name)) {
                            blockTag = name; // <thought>/<think>/<thinking> — capture inner text until closer
                        }
                        // drop the tag itself
                    } else {
                        out += m[0]; // not a protocol tag — keep literally
                    }
                    i = lt + m[0].length;
                } else if (/^<\/?\|?[a-zA-Z_|]*(:[^>]*)?$/.test(rest)) {
                    pending = rest; // incomplete tag/marker ('<', '<em', '<micro:part'…) — wait for more
                    break;
                } else {
                    out += '<'; // '<' not starting a tag (math, generics, etc.)
                    i = lt + 1;
                }
            }
            return out;
        },
        flush() {
            // Commit any still-open thought block so its text isn't lost
            if (blockBuf.trim()) thoughtParts.push(blockBuf.trim());
            blockBuf = '';
            // Anything still pending is an unterminated tag fragment — drop it
            // only if it looks like a protocol tag; otherwise emit as text.
            const s = pending; pending = '';
            if (!blockTag && /^<\/?([a-zA-Z_]+)/.test(s)) {
                const name = (s.match(/^<\/?([a-zA-Z_]+)/) || [])[1];
                if (name && !PROTOCOL_TAGS.has(name.toLowerCase())) return s;
                return '';
            }
            return blockTag ? '' : s;
        },
        takeThoughts() {
            // strip stray tag fragments that leaked inside thought text
            // (e.g. a model-written '</thought' inside a (thought:…) paren)
            const t = thoughtParts.join(' ').replace(/<\/?[a-zA-Z_|][^>\s]*/g, '').replace(/\s{2,}/g, ' ').trim();
            thoughtParts.length = 0;
            return t;
        }
    };
}
function stripProtocolTags(text) {
    if (typeof text !== 'string' || !text.includes('<')) return text;
    const st = createTagStripper();
    return st.feed(text) + st.flush();
}

// ── Multimodal Content Passthrough ──────────────────────────────────────────
function extractTextFromContent(content) {
    if (typeof content === 'string') return content;
    if (!Array.isArray(content)) return '';
    return content
        .filter(p => p && p.type === 'text' && typeof p.text === 'string')
        .map(p => p.text)
        .join('\n');
}

function isMultimodalContent(content) {
    return Array.isArray(content) && content.some(p => p && p.type === 'image_url');
}

function hasMultimodalMessages(messages) {
    return messages.some(m => isMultimodalContent(m.content));
}

// Fast dedup of repeated file reads inside a single request window.
function dedupeFileReads(messages) {
    const seen = new Set();
    return messages.map(m => {
        if (m.role !== 'user') return m;
        const textContent = extractTextFromContent(m.content);
        if (!textContent) return m;
        // Ultra-safe regex: no overlapping character classes, zero backtracking
        const fpMatch = textContent.match(/([A-Za-z]:[\\/][^\s,\u201c\u201d"']+|[a-zA-Z0-9_/-]+\.(?:py|ts|js|json|md|xml|kt|html|css)\b)/);
        const rangeMatch = textContent.match(/start_line[:\s=]+(\d+)(?:.{0,100}?)end_line[:\s=]+(\d+)/is)
            || textContent.match(/[Ll]ines?\s+(\d+)\s*[-\u2013to]+\s*(\d+)/);
        if (!fpMatch || !rangeMatch) return m;
        const key = `${fpMatch[1]}:${rangeMatch[1]}:${rangeMatch[2]}`;
        if (seen.has(key)) {
            const clone = { ...m, content: `[re-read] ${fpMatch[1]}:${rangeMatch[1]}-${rangeMatch[2]} - already seen, skipped` };
            return clone;
        }
        seen.add(key);
        return m;
    });
}

// Hard upstream token cap (port of XRLF_CLOUD_MAX_TOKENS_CAP from 8103 proxy)
// If env cap is set explicitly, use it; otherwise derive from model context window.
const CLOUD_MAX_TOKENS_CAP = parseInt(process.env.XRLF_CLOUD_MAX_TOKENS_CAP || '0', 10);
const PRESERVE_LAST_TURNS  = parseInt(process.env.XRLF_CLOUD_PRESERVE_LAST  || '4', 10);

// ── Context Window Spoofing ────────────────────────────────────────────────
// Reports a large context window to clients (Papillon, Cline, VS Code Copilot)
// while the proxy operates at a much smaller real window via XRL checkpointing.
// Set XRLF_SPOOF_CONTEXT_WINDOW=128000 to tell clients they have 128K available.
// Set XRLF_SAFE_MODE=true to disable spoofing and report real context windows.
const SPOOF_CONTEXT_WINDOW = parseInt(process.env.XRLF_SPOOF_CONTEXT_WINDOW || '0', 10);
const SAFE_MODE = process.env.XRLF_SAFE_MODE === 'true' || process.env.XRLF_SAFE_MODE === '1';

function getCloudCapForModel(modelName) {
    if (CLOUD_MAX_TOKENS_CAP > 0) return CLOUD_MAX_TOKENS_CAP;
    // Prefer the actual runtime n_ctx (queried async, cached) over the heuristic
    if (_runtimeCtxCache > 0) {
        const ctx = _runtimeCtxCache;
        if (ctx >= 500000) return 32768;
        if (ctx >= 150000) return 16384;
        if (ctx >=  64000) return 12288;
        return Math.min(ctx, 8192);  // local runtime: cap at actual n_ctx
    }
    const ctx = detectContextWindow(modelName, 'cloud');
    if (ctx >= 500000) return 32768;   // 1M+ context window
    if (ctx >= 150000) return 16384;   // ~150K context window
    if (ctx >=  64000) return 12288;   // 64K-128K
    return 8192;                       // default
}

function enforceCloudBudget(messages, modelName = '') {
    if (COGNITIVE_MODE !== 'cloud') return messages;
    if (!REPO_ENABLED || !REPO_CONTEXT_OVERRIDE) return messages; // reactor cold: no global caps
    const cap = getCloudCapForModel(modelName);
    const budgetChars = cap * 3; // ~3 chars/token heuristic
    const totalChars  = messages.reduce((n, m) => n + (m.content?.length || 0), 0);
    if (totalChars <= budgetChars) return messages;

    const systemMsgs = messages.filter(m => m.role === 'system');
    const convoMsgs  = messages.filter(m => m.role !== 'system');
    const preserveFrom = Math.max(0, convoMsgs.length - PRESERVE_LAST_TURNS);
    const preservedConvo = convoMsgs.slice(preserveFrom);
    const systemChars = systemMsgs.reduce((n, m) => n + (m.content?.length || 0), 0);
    const budgetLeft  = budgetChars - systemChars;

    let trimmed = [...preservedConvo];
    while (trimmed.length > 0 && trimmed.reduce((n, m) => n + (m.content?.length || 0), 0) > budgetLeft) {
        trimmed.shift();
    }
    console.log(`[CloudBudget] trim ${totalChars} → ${systemChars + trimmed.reduce((n,m)=>n+(m.content?.length||0),0)} chars (cap ${cap} tok, preserve last ${PRESERVE_LAST_TURNS})`);
    return [...systemMsgs, ...trimmed];
}

// ── XRLF Native Skeletonizer (self-contained — no external CLI deps) ─────────────
// Extracts structural skeletons from source files natively in JS.
// Equivalent to TokenSlayer level 3: keeps imports, class/function signatures,
// strips bodies. Supports JS/TS/Python. Fallback: first N lines for other types.
function skeletonizeFile(filepath, level = 3) {
    try {
        if (!fs.existsSync(filepath)) return null;
        const src = fs.readFileSync(filepath, 'utf8');
        const ext = path.extname(filepath).toLowerCase();
        const lines = src.split('\n');
        if (level === 0) return src; // full file
        // Level 3 / deep: keep only imports and signatures
        const SIG_RE_JS = /^\s*(export\s+)?(async\s+)?function\s+\w+|^\s*(export\s+)?(class|const|let|var)\s+\w+|^\s*import\b|^\s*require\b|^\s*module\.exports/;
        const SIG_RE_PY = /^\s*(def |class |import |from |@)/;
        const isJs = ['.js', '.ts', '.jsx', '.tsx'].includes(ext);
        const isPy = ext === '.py';
        const sigRe = isJs ? SIG_RE_JS : (isPy ? SIG_RE_PY : null);
        if (!sigRe) return lines.slice(0, 80).join('\n') + '\n...(truncated)';
        const skeleton = lines.filter(l => sigRe.test(l) || l.trim() === '');
        return skeleton.join('\n') || src.slice(0, 2000);
    } catch (e) {
        console.warn('[XRLF-Skeletonizer] skeletonizeFile failed:', e.message);
        return null;
    }
}
function expandFileLine(filepath, lineNum, contextLines = 3) {
    try {
        if (!fs.existsSync(filepath)) return null;
        const lines = fs.readFileSync(filepath, 'utf8').split('\n');
        const start = Math.max(0, lineNum - contextLines - 1);
        const end   = Math.min(lines.length, lineNum + contextLines);
        return lines.slice(start, end).map((l, i) => `${start + i + 1}: ${l}`).join('\n');
    } catch (e) {
        return null;
    }
}

// XRL-style atomic cache (tiny in-memory registry for expansion requests)
const xrlCache = new Map();
const XRL_NAMESPACE = 'XRLF';
function generateXrl(filepath, line, content) {
    const hash = require('crypto').createHash('sha256').update(`${filepath}:${line}:${content}`).digest('hex').slice(0, 6);
    const uri = `xrl://${XRL_NAMESPACE}/${filepath}:${line}:${hash}`;
    xrlCache.set(uri, { filepath, line, content, created: new Date().toISOString() });
    return uri;
}
function parseXrl(uri) {
    const m = uri.match(/^xrl:\/\/([^/]+)\/(.+):(\d+):([a-f0-9]{6})$/);
    return m ? { namespace: m[1], filepath: m[2], line: parseInt(m[3], 10), hash: m[4] } : null;
}

// Model context-window detection (ported from 8103)
function detectContextWindow(modelName, mode = 'cloud') {
    const m = (modelName || '').toLowerCase();
    if (m.includes('gemini-1.5') || m.includes('1m') || m.includes('2m') || m.includes('500k')) return 2000000;
    if (m.includes('gemini') || m.includes('128k')) return 128000;
    if (m.includes('gpt-4') || m.includes('claude-3') || m.includes('200k')) return 200000;
    if (m.includes('32k') || m.includes('64k') || m.includes('mixtral') || m.includes('command-r')) return 128000;
    if (m.includes('8k') || m.includes('16k') || m.includes('llama3') || m.includes('llama-3')) return 8192;
    if (m.includes('0.5b') || m.includes('1b') || m.includes('micro') || m.includes('tiny')) return 4096;
    return mode === 'cloud' ? 32768 : 8192;
}

// ── Runtime Context Window Detection ────────────────────────────────────────
// Queries the XRLF runtime's /v1/context endpoint for the ACTUAL n_ctx (after
// safety-net cap). Falls back to detectContextWindow() heuristic if unreachable.
let _runtimeCtxCache = 0;
let _runtimeCtxCacheTime = 0;
const RUNTIME_CTX_TTL_MS = 30000; // re-query every 30s

async function getRuntimeContextWindow() {
    const now = Date.now();
    if (_runtimeCtxCache > 0 && (now - _runtimeCtxCacheTime) < RUNTIME_CTX_TTL_MS) {
        return _runtimeCtxCache;
    }
    try {
        const r = await fetch(`${XRLF_RUNTIME_URL}/v1/context`, { timeout: 2000 });
        if (r.ok) {
            const data = await r.json();
            if (data.context_window && data.context_window > 0) {
                _runtimeCtxCache = data.context_window;
                _runtimeCtxCacheTime = now;
                return _runtimeCtxCache;
            }
        }
    } catch (_) {}
    return 0; // unreachable — caller falls back to heuristic
}
function selectTier(ctx) {
    if (ctx >= 1000000) return 'micro';
    if (ctx >= 200000) return 'standard';
    if (ctx >= 32000)  return 'full';
    return 'standard';
}

// ── Config ─────────────────────────────────────────────────────────────────

function loadConfig(overrides = {}) {
    const defaultPath = path.join(__dirname, 'config', 'default.json');
    const defaults    = JSON.parse(fs.readFileSync(defaultPath, 'utf8'));

    // Check for a local config.json in cwd
    const localPath = path.join(process.cwd(), 'config.json');
    const local     = fs.existsSync(localPath)
        ? JSON.parse(fs.readFileSync(localPath, 'utf8'))
        : {};

    return { ...defaults, ...local, ...overrides };
}

const config = loadConfig();

// ── Conversation identity names (assistant + user) ─────────────────────────
// Assistant name is canonical in Backend/Cognition/jen_soul.json (soul.soul_name);
// falls back to config.identity_name. User name comes from config.user_name.
let ASSISTANT_NAME = config.identity_name || 'Jen';
const USER_NAME = config.user_name || 'You';
try {
    const soulPath = path.resolve(__dirname, '..', 'Backend', 'Cognition', 'jen_soul.json');
    if (fs.existsSync(soulPath)) {
        const soul = JSON.parse(fs.readFileSync(soulPath, 'utf8'));
        ASSISTANT_NAME = soul?.soul?.soul_name || soul?.profile?.nickname || ASSISTANT_NAME;
    }
} catch (_) {}

// ── XRLF Port Override ─────────────────────────────────────────────────────
// Default port for the new canonical XRLF proxy is 8400.
// Set XRLF_PROXY_PORT env var to override.
if (process.env.XRLF_PROXY_PORT) {
    config.proxy_port = parseInt(process.env.XRLF_PROXY_PORT, 10);
} else if (config.proxy_port === 8301) {
    config.proxy_port = 8400; // promote to new default
}
console.log(`[XRLF] Proxy port: ${config.proxy_port}`);

// ── Cloud-Aware Upstream Routing ─────────────────────────────────────────────
// When XRLF_COGNITIVE_MODE=cloud, override upstream to Ollama Cloud with API key.
// Compression checkpoints (context-compressor.js) stay local on LM Studio — hybrid routing.
const COGNITIVE_MODE = (process.env.XRLF_COGNITIVE_MODE || 'local').toLowerCase();
// Ollama Cloud upstream. Deliberately NOT aliased to XRLF_PROXY_TARGET: that
// key names the *global* upstream, which in local mode is the local XRLF
// runtime. Sharing it meant 'ollama/<id>' silently inherited the local runtime
// as its target. FOVEAI_OLLAMA_URL is the per-route override; XRLF_PROXY_TARGET
// is still honoured as a fallback so cloud-mode deployments keep working.
const OLLAMA_CLOUD_URL = (() => {
    const dedicated = process.env.FOVEAI_OLLAMA_URL;
    if (dedicated) return dedicated.replace(/\/+$/, '');
    const proxied = process.env.XRLF_PROXY_TARGET;
    if (proxied) {
        console.warn('[OLLAMA] no FOVEAI_OLLAMA_URL set — falling back to XRLF_PROXY_TARGET. ' +
            'Set FOVEAI_OLLAMA_URL=https://ollama.com/v1 so ollama/* cannot inherit the local runtime.');
        return proxied.replace(/\/+$/, '');
    }
    return 'https://ollama.com/v1';
})();
const OLLAMA_API_KEY = process.env.XRLF_PROXY_API_KEY || process.env.OLLAMA_API_KEY || '';

// ── NVIDIA NIM side-route ─────────────────────────────────────────────────────
// Models in XRLF_NVIDIA_MODELS are exposed in /v1/models as `nvidia/<id>` and
// routed per-request to integrate.api.nvidia.com — works alongside local XRLF
// models without flipping COGNITIVE_MODE.
const NVIDIA_BASE_URL = (process.env.FOVEAI_NVIDIA_URL || 'https://integrate.api.nvidia.com/v1/chat/completions')
    .replace(/\/chat\/completions\/?$/, '');   // ends with /v1
const NVIDIA_API_KEY  = process.env.FOVEAI_NVIDIA_API_KEY || '';
const NVIDIA_PREFIX   = 'nvidia/';
const NVIDIA_MODELS   = (process.env.XRLF_NVIDIA_MODELS ||
    'moonshotai/kimi-k3,deepseek-ai/deepseek-v4-flash-0731,nvidia/nemotron-3-super-120b-a12b')
    .split(',').map(s => s.trim()).filter(Boolean);
const isNvidiaModel   = (m) => typeof m === 'string' && m.startsWith(NVIDIA_PREFIX);

// Member-facing free cloud tier: 'nvidia-free' is the only cloud model ID
// testers see — the real backend model is server-side config, not disclosed.
const FREE_CLOUD_ID    = 'nvidia-free';
const FREE_CLOUD_MODEL = process.env.FOVEAI_CLOUD_FREE_MODEL || 'nvidia/nemotron-3-super-120b-a12b';
const isFreeCloudModel = (m) => m === FREE_CLOUD_ID;

// ── Ollama Cloud per-model side-route ────────────────────────────────────────
// Cloud mode makes Ollama the *global* upstream, so a request cannot choose a
// specific Ollama model while local models stay reachable. 'ollama/<id>' is the
// per-model equivalent of 'nvidia/<id>': it pins one turn to Ollama Cloud using
// the owner's key, leaving every other route untouched. Both surfaces benefit —
// Multigate's chat and the Quest/voice clients post to the same
// /v1/chat/completions. Unlike the NVIDIA route this is permissive: the id is
// passed through to Ollama, which validates it, so we never hard-code a model
// catalog that would rot. XRLF_OLLAMA_MODELS only seeds /v1/models discovery.
const OLLAMA_PREFIX   = 'ollama/';
const isOllamaModel   = (m) => typeof m === 'string' && m.startsWith(OLLAMA_PREFIX);
const OLLAMA_MODELS   = (process.env.XRLF_OLLAMA_MODELS || '')
    .split(',').map(s => s.trim()).filter(Boolean);

// ── Nova collegium side-route (:8416 bridge) ────────────────────────────────
// The tiny seed-memory swarm (Project XRL: kqatt pawn + k6 knight) runs as an
// OpenAI-compatible bridge on 127.0.0.1:8416. 'nova', 'nova-k1', 'nova-k8',
// 'nova-k32' pin one turn to the bridge, same mechanics as nvidia/*. No keys,
// no auth gates — purely local. /v1/models merges the bridge's live list.
const NOVA_URL = process.env.FOVEAI_NOVA_URL || 'http://127.0.0.1:8416';
const isNovaModel = (m) => typeof m === 'string' && /^(nova|nova-(k1|k8|k32))$/.test(m);

// Cloud providers reject the XRLF-specific fields the local runtime tolerates
// (HTTP 400 on strict schema validation). Applied to every cloud side-route.
function stripCloudParams(b) {
    delete b.session_id;
    delete b._tasks;
    delete b.tasks;
    delete b.persona;
    delete b.workspaceId;
    delete b.workspace_id;
    delete b.xrlf_headless;
    delete b.xrlf_thinking;
    return b;
}

// ── BYOK side-route ─────────────────────────────────────────────────────────
// Model name 'byok' or 'byok/<model>' routes through the caller's own stored
// cloud key (set on /user-settings.html). The full XRLF pipeline — memory,
// compression, persona — still applies; only the final upstream changes.
const BYOK_PROVIDER_URLS = {
    openai:     'https://api.openai.com/v1',
    nvidia:     'https://integrate.api.nvidia.com/v1',
    ollama:     'https://ollama.com/v1',
    openrouter: 'https://openrouter.ai/api/v1',
    gemini:     'https://generativelanguage.googleapis.com/v1beta/openai',
    opencode:   'https://opencode.ai/zen/v1',   // Zen: space-bunny-free, big-pickle (both free)
    lmstudio:   null, // requires user-supplied baseUrl
};
const isByokModel = (m) => typeof m === 'string' && /^byok(\/|$)/.test(m);

// Architecture brief injected as a system message on nvidia/* requests so the
// cloud model knows XRLF local models are the product and it is a dev helper.
const NVIDIA_CONTEXT_ENABLED = (process.env.XRLF_NVIDIA_CONTEXT || 'true').toLowerCase() !== 'false';
let _nvidiaContext = '';
if (NVIDIA_CONTEXT_ENABLED) {
    try {
        _nvidiaContext = fs.readFileSync(
            process.env.XRLF_NVIDIA_CONTEXT_FILE || path.resolve(__dirname, 'nvidia-context.md'), 'utf8'
        ).trim();
    } catch { /* brief optional */ }
}
function injectNvidiaContext(messages) {
    if (!_nvidiaContext || !Array.isArray(messages)) return messages;
    const out = messages.slice();
    if (out[0] && out[0].role === 'system') {
        out[0] = { ...out[0], content: `${out[0].content}\n\n${_nvidiaContext}` };
    } else {
        out.unshift({ role: 'system', content: _nvidiaContext });
    }
    return out;
}

if (NVIDIA_API_KEY) console.log(`[NVIDIA] side-route enabled: ${NVIDIA_MODELS.map(m => NVIDIA_PREFIX + m).join(', ')} (context=${_nvidiaContext ? 'on' : 'off'})`);
else console.warn('[NVIDIA] FOVEAI_NVIDIA_API_KEY not set — nvidia/* models will fail');

// ── Bearer-based collective memory / billing key ──────────────────────────────
// The client's Authorization token is used as the workspace/memory scope key.
// If the client omits a token, fall back to a default workspace so the proxy
// still functions, but we log a warning once.
const DEFAULT_FALLBACK_WORKSPACE = process.env.XRLF_DEFAULT_WORKSPACE || 'default';
let warnedMissingAuth = false;

// ── LM Studio Auto-Start (for local compression) ─────────────────────────────
// In cloud mode, chat completions go to Ollama Cloud, but compression checkpoints
// still use local LM Studio. If LM Studio is offline, auto-start it headlessly
// with the Qwen3.5-4B middleman model at 20% GPU offload.
const XRLF_RUNTIME_URL = process.env.XRLF_RUNTIME_URL || process.env.LOCAL_LLM_BASE || 'http://127.0.0.1:8402';
const MIDDLEMAN_MODEL = process.env.XRLF_MIDDLEMAN_MODEL || process.env.FoveAI_MIDDLEMAN_MODEL || process.env.LOCAL_LLM_MODEL || 'slim-summary-tiny-tool';
const MIDDLEMAN_GPU_OFFLOAD = process.env.XRLF_MIDDLEMAN_GPU_OFFLOAD || '0.2';
const MIDDLEMAN_CONTEXT_LENGTH = process.env.XRLF_MIDDLEMAN_CONTEXT_LENGTH || '8192';

// ── XRLF Config (xrlf_config.yaml) — summarizer & model registry ───────────────
// Loads the declarative config from xrlf_config.yaml so the summarizer settings
// (model, endpoint, max_tokens, temperature) are actually consumed by server.js
// instead of being documentation-only. Falls back to env / hardcoded defaults.
let XRLF_CONFIG = { summarizer: { enabled: false }, models: { primary: null, secondary: null } };
(function loadXrlfConfig() {
    try {
        const yamlLib = (() => { try { return require('yaml'); } catch { return require('js-yaml'); } })();
        const cfgPath = path.resolve(__dirname, '..', 'xrlf_config.yaml');
        if (!fs.existsSync(cfgPath)) {
            console.log('[XRLF-Config] xrlf_config.yaml not found — using env/defaults');
            return;
        }
        const raw = fs.readFileSync(cfgPath, 'utf8');
        // 'yaml' package uses .parse(), 'js-yaml' uses .load()
        XRLF_CONFIG = (yamlLib.parse ? yamlLib.parse(raw) : yamlLib.load(raw)) || {};
        console.log(`[XRLF-Config] Loaded xrlf_config.yaml (model=${XRLF_CONFIG.model || 'n/a'}, port=${XRLF_CONFIG.api?.port || 'n/a'})`);
    } catch (e) {
        console.warn(`[XRLF-Config] Could not parse xrlf_config.yaml: ${e.message}`);
    }
})();

// Summarizer settings — sourced from xrlf_config.yaml, overridable via env vars.
// The summarizer is the lightweight model used for foveated memory compression
// and session-title generation. It typically runs on the same llama_server
// endpoint as the local LLM backend (LM Studio, port 1234) but can be pointed elsewhere.
const SUMMARIZER_ENABLED  = (process.env.XRLF_SUMMARIZER_ENABLED || String(XRLF_CONFIG.summarizer?.enabled ?? true)).toLowerCase() === 'true';
const SUMMARIZER_MODEL     = process.env.XRLF_SUMMARIZER_MODEL    || XRLF_CONFIG.summarizer?.model    || MIDDLEMAN_MODEL;
const SUMMARIZER_ENDPOINT  = process.env.XRLF_SUMMARIZER_ENDPOINT  || XRLF_CONFIG.summarizer?.endpoint || `${XRLF_RUNTIME_URL}/v1`;
const SUMMARIZER_MAX_TOKENS= parseInt(process.env.XRLF_SUMMARIZER_MAX_TOKENS || String(XRLF_CONFIG.summarizer?.max_tokens || 512), 10);
const SUMMARIZER_TEMP      = parseFloat(process.env.XRLF_SUMMARIZER_TEMP      || String(XRLF_CONFIG.summarizer?.temperature ?? 0.3));
console.log(`[XRLF-Summarizer] enabled=${SUMMARIZER_ENABLED} model=${SUMMARIZER_MODEL} endpoint=${SUMMARIZER_ENDPOINT} max_tokens=${SUMMARIZER_MAX_TOKENS} temp=${SUMMARIZER_TEMP}`);

// ── Upstream Model Override ────────────────────────────────────────────────────
// The proxy receives `model: "auto"` from clients like Cline, which upstreams
// (LM Studio / Ollama Cloud) cannot resolve. Override with an explicit model name.
// Priority: XRLF_PROXY_MODEL env > MIDDLEMAN_MODEL (local) > hardcoded default.
// In cloud mode, the default is 'kimi-k2.7-code' (a confirmed available Ollama Cloud model).
// In local mode, the default is MIDDLEMAN_MODEL (the LM Studio loaded model).
const UPSTREAM_MODEL = process.env.XRLF_PROXY_MODEL || (COGNITIVE_MODE === 'cloud' ? (process.env.XRLF_MODEL_CLOUD_ID || 'kimi-k2.7-code') : (process.env.XRLF_MODEL_LOCAL_ID || process.env.LOCAL_LLM_MODEL || MIDDLEMAN_MODEL));

// ── Restore last active model profile from disk ───────────────────────────────
// Atomically snaps ALL settings back to where they were before the last restart.
(function restoreActiveProfile() {
    try {
        const saved = loadActiveModel();
        if (saved && saved.model) {
            const applied = applyProfile(saved.model, config);
            if (applied) {
                console.log(`[ModelProfile] 🔄 Restored '${saved.model}' from active-model.json (${saved.appliedAt})`);
            } else {
                console.warn(`[ModelProfile] ⚠️ '${saved.model}' has no profile — add it to memory_data/model-profiles.json`);
            }
        } else {
            const envModel = process.env.XRLF_MODEL_ID || process.env.XRLF_MODEL_CLOUD_ID || process.env.XRLF_MODEL_LOCAL_ID;
            if (envModel) {
                const applied = applyProfile(envModel, config);
                if (applied) console.log(`[ModelProfile] 🔍 Auto-applied profile for env model '${envModel}'`);
            }
        }
    } catch (e) {
        console.warn('[ModelProfile] Startup restore failed:', e.message);
    }
})();

let _lmStudioStarting = false;

async function ensureLMStudio() {
    // Quick health check — is LM Studio already running?
    try {
        const r = await fetch(`${XRLF_RUNTIME_URL}/v1/models`, { timeout: 2000 });
        if (r.ok) return true;
    } catch (_) {}

    // Prevent concurrent auto-start attempts
    if (_lmStudioStarting) return false;

    // Headless auto-start disabled to prevent background VRAM/RAM exhaustion
    if (process.env.FOVEAI_ALLOW_SPAWN_LMSTUDIO !== 'true') {
        console.warn('[AutoStart] LM Studio offline on ' + XRLF_RUNTIME_URL + ' (headless auto-spawning disabled)');
        return false;
    }

    _lmStudioStarting = true;

    try {
        console.log('[AutoStart] LM Studio offline — starting headlessly...');

        // Step 1: Start LM Studio server
        await new Promise((resolve, reject) => {
            execFile('lms', ['server', 'start'], { timeout: 30000, windowsHide: true }, (err, stdout, stderr) => {
                if (err) { console.warn('[AutoStart] lms server start failed:', err.message); reject(err); }
                else { console.log('[AutoStart] lms server started'); resolve(); }
            });
        });

        // Step 2: Wait for server to be ready (poll up to 20s)
        let ready = false;
        for (let i = 0; i < 10; i++) {
            await new Promise(r => setTimeout(r, 2000));
            try {
                const r = await fetch(`${XRLF_RUNTIME_URL}/v1/models`, { timeout: 2000 });
                if (r.ok) { ready = true; break; }
            } catch (_) {}
        }
        if (!ready) { console.warn('[AutoStart] LM Studio server did not become ready in 20s'); return false; }

        // Step 3: Unload any existing models to free VRAM
        await new Promise((resolve) => {
            execFile('lms', ['unload', '--all'], { timeout: 15000, windowsHide: true }, (err) => {
                if (err) console.warn('[AutoStart] lms unload failed (non-critical):', err.message);
                resolve(); // non-critical — load will replace anyway
            });
        });

        // Step 4: Load the middleman model with GPU offload
        await new Promise((resolve, reject) => {
            const args = ['load', MIDDLEMAN_MODEL, '--gpu', MIDDLEMAN_GPU_OFFLOAD, '--context-length', MIDDLEMAN_CONTEXT_LENGTH, '-y'];
            execFile('lms', args, { timeout: 120000, windowsHide: true }, (err, stdout, stderr) => {
                if (err) { console.warn('[AutoStart] lms load failed:', err.message); reject(err); }
                else { console.log(`[AutoStart] LM Studio loaded model: ${MIDDLEMAN_MODEL}`); resolve(); }
            });
        });

        return true;
    } catch (e) {
        console.warn('[AutoStart] LM Studio auto-start failed:', e.message);
        return false;
    } finally {
        _lmStudioStarting = false;
    }
}

if (COGNITIVE_MODE === 'cloud') {
    config.upstream_url = OLLAMA_CLOUD_URL.replace(/\/v1\/?$/, '');
    config._cloud_mode = true;
    config._api_key = OLLAMA_API_KEY;
} else {
    config._cloud_mode = false;
    config._api_key = '';
}

const app    = express();

const DEBUG_LOG_PATH = path.join(__dirname, 'debug.log');
const MAX_DEBUG_LOG_BYTES = 2 * 1024 * 1024; // 2 MB safety cap
let _logWriteInProgress = false;
let _logQueue = [];

function logDebug(msg) {
    _logQueue.push(msg);
    if (_logWriteInProgress) return;
    _flushLogQueue();
}

function _flushLogQueue() {
    if (_logQueue.length === 0) {
        _logWriteInProgress = false;
        return;
    }
    _logWriteInProgress = true;
    const chunk = _logQueue.join('');
    _logQueue = [];

    fs.stat(DEBUG_LOG_PATH, (err, stats) => {
        if (!err && stats.size > MAX_DEBUG_LOG_BYTES) {
            try {
                // Truncate to keep the last 512KB
                const fd = fs.openSync(DEBUG_LOG_PATH, 'r+');
                const keepBytes = 512 * 1024;
                const buffer = Buffer.alloc(keepBytes);
                fs.readSync(fd, buffer, 0, keepBytes, Math.max(0, stats.size - keepBytes));
                fs.closeSync(fd);
                fs.writeFileSync(DEBUG_LOG_PATH, buffer);
            } catch (_) {
                try { fs.writeFileSync(DEBUG_LOG_PATH, ''); } catch (_) {}
            }
        }

        fs.appendFile(DEBUG_LOG_PATH, chunk, () => {
            if (_logQueue.length > 0) {
                setImmediate(_flushLogQueue);
            } else {
                _logWriteInProgress = false;
            }
        });
    });
}

// Request logger (BEFORE body parsing!)
const SILENT_LOG_PATHS = new Set(['/health', '/api/status', '/v1/models', '/favicon.ico']);
app.use((req, res, next) => {
    if (req.method !== 'OPTIONS') {
        const urlPath = req.path || (req.url ? req.url.split('?')[0] : '');
        if (!SILENT_LOG_PATHS.has(urlPath)) {
            console.log(`[Proxy] ${req.method} ${req.url}`);
            logDebug(`[${new Date().toISOString()}] Socket Hit: ${req.method} ${req.url}\n`);
        }
    }
    next();
});

app.use(express.json({ limit: '50mb' }));

// Native CORS middleware
app.use((req, res, next) => {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
    if (req.method === 'OPTIONS') {
        return res.sendStatus(200);
    }
    next();
});

// ── Access telemetry ─────────────────────────────────────────────────────────
// Every API call lands in the buffered JSONL request log. Chat completions are
// skipped here — handleChatCompletion writes a richer record (model, route,
// latency, thought counts) instead of this generic one.
app.use((req, res, next) => {
    const urlPath = req.path || (req.url ? req.url.split('?')[0] : '');
    if (SILENT_LOG_PATHS.has(urlPath)
        || urlPath === '/v1/chat/completions' || urlPath === '/chat/completions') {
        return next();
    }
    const t0 = Date.now();
    let written = false;
    const writeEntry = (err) => {
        if (written) return;
        written = true;
        logRequest({
            route: 'api',
            endpoint: `${req.method} ${urlPath}`,
            status: res.statusCode,
            latency_ms: Date.now() - t0,
            user: req.userId || 'anonymous',
            error: err || (res.statusCode >= 400 ? `http_${res.statusCode}` : undefined),
        });
    };
    res.on('finish', () => writeEntry());
    res.on('close', () => { if (!res.writableFinished) writeEntry('client_disconnect'); });
    next();
});

// ── Dashboard static assets on port 8414 ─────────────────────────────────────
const DASHBOARD_PORT = parseInt(process.env.XRLF_DASHBOARD_PORT || '8414', 10);
const dashboardApp   = express();
dashboardApp.use(express.json());
const publicDir      = path.join(__dirname, 'public');
if (fs.existsSync(publicDir)) {
    dashboardApp.use('/', express.static(publicDir));
    dashboardApp.use('/memory', express.static(publicDir));
}
// Strip trailing slashes on .html files (browsers sometimes add them)
dashboardApp.use((req, res, next) => {
    // No-cache for HTML pages so code changes show up without hard refresh
    if (req.path.endsWith('.html') || req.path === '/' || req.path === '/launch') {
        res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
    }
    if (req.path.endsWith('.html/') || req.path.endsWith('.html//')) {
        return res.redirect(301, req.path.replace(/\/+$/, ''));
    }
    next();
});
dashboardApp.get(['/', '/memory'], (req, res) => {
    const launchPath = path.join(publicDir, 'launch.html');
    if (fs.existsSync(launchPath)) return res.sendFile(launchPath);
    const settingsPath = path.join(publicDir, 'settings.html');
    if (fs.existsSync(settingsPath)) return res.sendFile(settingsPath);
    const indexPath = path.join(publicDir, 'index.html');
    if (fs.existsSync(indexPath)) return res.sendFile(indexPath);
    res.status(404).json({ error: 'Dashboard not installed.' });
});
dashboardApp.get(['/launch', '/launch/'], (req, res) => {
    const launchPath = path.join(publicDir, 'launch.html');
    if (fs.existsSync(launchPath)) {
        res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
        return res.sendFile(launchPath);
    }
    res.redirect('/');
});

// ── Active IDE Detection & Dispatch Endpoints ─────────────────────────────────
const IDE_PROCESS_MAP = [
    { id: 'antigravity', name: 'Antigravity / AGY', exePatterns: ['antigravity', 'agy', 'gemini-cli', 'antigravity-ide'], scheme: 'lx://chat?q=' },
    { id: 'vscode', name: 'VS Code', exePatterns: ['code', 'code - insiders'], scheme: 'vscode://chat?q=' },
    { id: 'cursor', name: 'Cursor', exePatterns: ['cursor'], scheme: 'cursor://chat?q=' },
    { id: 'windsurf', name: 'Windsurf', exePatterns: ['windsurf'], scheme: 'windsurf://chat?q=' },
    { id: 'hermes', name: 'Hermes Agent', exePatterns: ['hermes'], scheme: 'hermes://chat?q=' },
    { id: 'cline', name: 'Cline Agent', exePatterns: ['cline'], scheme: 'cline://chat?q=' },
    { id: 'codex', name: 'Codex / Custom', exePatterns: ['codex'], scheme: 'codex://chat?q=' }
];

function detectActiveIDEs(callback) {
    if (process.platform !== 'win32') {
        const fallback = { id: 'vscode', name: 'VS Code', scheme: 'vscode://chat?q=' };
        return callback(null, { detected: [fallback], primary: fallback, foreground: 'vscode' });
    }
    const psCmd = `$code = @"\nusing System;\nusing System.Runtime.InteropServices;\npublic class Win32 {\n  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();\n  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);\n}\n"@\nAdd-Type -TypeDefinition $code -ErrorAction SilentlyContinue\n$hwnd = [Win32]::GetForegroundWindow()\n$pid = 0\n[Win32]::GetWindowThreadProcessId($hwnd, [ref]$pid)\n$fgName = ""\nif ($pid -gt 0) { $fgName = (Get-Process -Id $pid -ErrorAction SilentlyContinue).ProcessName }\n$procs = (Get-CimInstance Win32_Process | Select-Object -ExpandProperty Name) -join "\n"\nWrite-Output "FG:$fgName"\nWrite-Output "PROCS:"\nWrite-Output $procs`;

    execFile(PWSH, ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', psCmd], { windowsHide: true }, (err, stdout) => {
        if (err || !stdout) {
            const fallback = { id: 'antigravity', name: 'Antigravity / AGY', scheme: 'lx://chat?q=' };
            return callback(null, { detected: [fallback], primary: fallback, foreground: 'antigravity' });
        }
        const lines = stdout.split(/\r?\n/);
        let fgName = '';
        const procs = [];
        let inProcs = false;
        for (const line of lines) {
            if (line.startsWith('FG:')) {
                fgName = line.slice(3).trim().toLowerCase();
            } else if (line.startsWith('PROCS:')) {
                inProcs = true;
            } else if (inProcs && line.trim()) {
                procs.push(line.trim().toLowerCase());
            }
        }

        const detected = [];
        let fgTarget = null;

        for (const target of IDE_PROCESS_MAP) {
            const isRunning = target.exePatterns.some(pattern => procs.some(p => p.includes(pattern)));
            if (isRunning) {
                detected.push(target);
            }
            if (fgName && target.exePatterns.some(pattern => fgName.includes(pattern))) {
                fgTarget = target;
            }
        }

        if (detected.length === 0) {
            detected.push({ id: 'antigravity', name: 'Antigravity / AGY', scheme: 'lx://chat?q=' });
        }

        const primary = fgTarget || detected[0];
        callback(null, { detected, primary, foreground: fgName || primary.id });
    });
}

const handleIdeDetect = (req, res) => {
    detectActiveIDEs((err, data) => {
        if (err) return res.status(500).json({ error: err.message });
        res.json(data);
    });
};

const handleXRLFDispatch = async (req, res) => {
    const { prompt } = req.body || {};
    if (!prompt) return res.status(400).json({ error: 'prompt is required' });

    try {
        // Route directly through the main chat handler instead of looping back to the proxy port.
        const workspaceId = 'prompt_kiosk';
        const reqStore = getStore(workspaceId);
        const fakeReq = {
            body: {
                model: UPSTREAM_MODEL || 'foveated-proxy-auto',
                messages: [{ role: 'user', content: prompt }],
                stream: false
            },
            headers: { authorization: 'Bearer prompt_kiosk_agent' }
        };
        await handleChatCompletion(fakeReq, res, null, reqStore, workspaceId);
    } catch (err) {
        console.error('[XRLFDispatch] Error dispatching prompt to XRLF core:', err);
        if (!res.headersSent) res.status(500).json({ error: `Failed to dispatch prompt to FoveAI Agent: ${err.message}` });
    }
};

dashboardApp.get('/api/ide/detect', handleIdeDetect);
app.get('/api/ide/detect', handleIdeDetect);
dashboardApp.get('/api/status', (req, res) => res.json({ status: 'ok' }));
dashboardApp.post('/api/XRLF/dispatch', handleXRLFDispatch);
app.post('/api/XRLF/dispatch', handleXRLFDispatch);

// ── Model Profile Endpoints ───────────────────────────────────────────────────
// POST /v1/switch-model  { "model": "kimi-k2.7-code" }
// GET  /v1/profiles
app.post(['/v1/switch-model', '/api/switch-model', '/api/settings'], (req, res) => {
    if (!requireAdmin(req, res)) return;
    let { model, role, key, value } = req.body || {};
    if (!model && key === 'XRLF_MODEL_LOCAL_ID' && value) {
        model = value;
    }
    let targetModel = model;
    if (!targetModel && role) {
        const match = listProfiles().find(p => p.role === role);
        if (match) targetModel = match.id;
    }
    if (!targetModel) {
        return res.status(400).json({ error: 'model or role required', example: { model: 'kimi-k2.7-code' } });
    }
    const profile = applyProfile(targetModel, config);
    if (!profile) {
        return res.status(404).json({
            error: `No profile found for '${targetModel}'`,
            hint: 'Add it to memory_data/model-profiles.json',
            available: listProfiles().map(p => p.id)
        });
    }
    saveActiveModel(profile.id);
    return res.json({
        status: 'ok',
        applied: profile.id,
        label: profile.label,
        cognitive_mode: profile.cognitive_mode,
        upstream_url: profile.upstream_url,
        spoof_context_window: profile.spoof_context_window,
        proxy_aggression: profile.proxy_aggression,
        cloud_max_tokens_cap: profile.cloud_max_tokens_cap
    });
});

app.get(['/v1/profiles', '/api/profiles'], (req, res) => {
    const active = loadActiveModel();
    res.json({ active_model: active?.model || null, active_since: active?.appliedAt || null, profiles: listProfiles() });
});

// Context Healer endpoints on dashboard port too
dashboardApp.get('/api/context/health', (req, res) => res.json(getHealerState()));
dashboardApp.post('/api/context/reset', (req, res) => {
    const result = resetBudget();
    res.json({ status: 'reset', ...result, state: getHealerState() });
});
dashboardApp.post('/api/context/budget', (req, res) => {
    const { budget } = req.body || {};
    if (!budget || typeof budget !== 'number') {
        return res.status(400).json({ error: 'budget (number) required' });
    }
    const result = setBudget(budget);
    res.json({ status: 'set', ...result, state: getHealerState() });
});

// ── Code Preserver API ──────────────────────────────────────────────────
dashboardApp.get('/api/preserver/stats', (req, res) => {
    res.json(getPreserverStats());
});
dashboardApp.post('/api/preserver/rule', (req, res) => {
    const { name, enabled } = req.body || {};
    if (!name || typeof enabled !== 'boolean') {
        return res.status(400).json({ error: 'name (string) and enabled (boolean) required' });
    }
    const { setRuleEnabled } = require('./core/code-preserver');
    setRuleEnabled(name, enabled);
    res.json({ status: 'ok', rule: name, enabled, stats: getPreserverStats() });
});
dashboardApp.post('/api/preserver/configure', (req, res) => {
    const { rules } = req.body || {};
    if (!Array.isArray(rules)) {
        return res.status(400).json({ error: 'rules (array) required' });
    }
    configurePreserver(rules);
    res.json({ status: 'ok', stats: getPreserverStats() });
});

// ── Shadow Context API ──────────────────────────────────────────────────
dashboardApp.get('/api/shadow/stats', (req, res) => {
    const sessionId = req.query.session || config.workspace_id;
    res.json(getShadowStats(sessionId));
});
dashboardApp.get('/api/shadow/search', (req, res) => {
    const sessionId = req.query.session || config.workspace_id;
    const q = req.query.q || '';
    if (!q) return res.status(400).json({ error: 'q (search query) required' });
    res.json(searchShadowBlocks(sessionId, q, 10));
});
dashboardApp.get('/api/shadow/block/:hash', (req, res) => {
    const sessionId = req.query.session || config.workspace_id;
    const block = getShadowBlock(sessionId, req.params.hash);
    if (!block) return res.status(404).json({ error: 'block not found' });
    res.json(block);
});

// ── Retina API ──────────────────────────────────────────────────────────
dashboardApp.post('/api/retina/classify', (req, res) => {
    const { messages } = req.body || {};
    if (!Array.isArray(messages)) {
        return res.status(400).json({ error: 'messages (array) required' });
    }
    const classification = classifyBatch(messages);
    res.json({
        stats: formatRetinaStats(classification.stats),
        shadow: classification.shadow.length,
        checkpoint: classification.checkpoint.length,
        ephemeral: classification.ephemeral.length,
        discard: classification.discard.length
    });
});

// ── Emotional Resonance API ────────────────────────────────────────────────
dashboardApp.post('/api/emotion/butterfly', (req, res) => {
    const { errorType, errorMessage } = req.body || {};
    if (!errorType || !errorMessage) {
        return res.status(400).json({ error: 'errorType and errorMessage required' });
    }
    const effect = processButterflyEffect(errorType, errorMessage);
    res.json({ effect, currentEmotion: getCurrentEmotion() });
});

dashboardApp.post('/api/emotion/set', (req, res) => {
    const { emotion, trigger } = req.body || {};
    if (!emotion) {
        return res.status(400).json({ error: 'emotion required' });
    }
    const success = setEmotionalState(emotion, trigger || 'api');
    res.json({ success, currentEmotion: getCurrentEmotion() });
});

dashboardApp.get('/api/emotion/current', (req, res) => {
    res.json(getCurrentEmotion());
});

dashboardApp.post('/api/proximity/update', (req, res) => {
    const { nearby, distance } = req.body || {};
    if (typeof nearby !== 'boolean') {
        return res.status(400).json({ error: 'nearby (boolean) required' });
    }
    updateProximity(nearby, distance || 'unknown');
    res.json({ proximity: getProximityState(), currentEmotion: getCurrentEmotion() });
});

dashboardApp.get('/api/proximity/state', (req, res) => {
    res.json(getProximityState());
});

// ── Same-origin bridges (for Cloudflare-tunnel / LAN access) ────────────────
// A tunnel domain can only proxy ONE port per hostname, so panels served from
// :8414 must reach the runtime (:8402) and the proxy API (:8400) same-origin.
// /xrlf/* forwards to the runtime; everything else falls through to the full
// proxy app mounted below.
dashboardApp.use('/xrlf', async (req, res) => {
    try {
        const r = await withLocalUpstream(() => fetch(`http://127.0.0.1:8402${req.url}`, {
            method: req.method,
            headers: { 'Content-Type': 'application/json' },
            body: ['GET', 'HEAD'].includes(req.method) ? undefined : JSON.stringify(req.body || {}),
            signal: AbortSignal.timeout(120000),
        }));
        const text = await r.text();
        res.status(r.status).type(r.headers.get('content-type') || 'text/plain').send(text);
    } catch (e) {
        res.status(502).json({ error: `xrlf runtime unreachable: ${e.message}` });
    }
});

// Mount the proxy app LAST so dashboard routes/static win on conflicts — this
// exposes /api/env, /api/setting, /api/control, /api/subsystems, /health,
// /v1/* etc. on the dashboard port for any same-origin client.
dashboardApp.use(app);

// ── Express Error Handler (catch body-parser errors, return JSON not HTML) ──
app.use((err, req, res, next) => {
    if (err && (err.type === 'entity.parse.failed' || err.message?.includes('raw-body') || err.message?.includes('stream') || err.code === 'HPE_INVALID_CONSTANT')) {
        console.error('[Express] Body parse error:', err.message);
        // Butterfly Effect: Parse errors cause nervous system tingles
        processButterflyEffect('parse_error', err.message);
        return res.status(400).json({
            error: {
                message: `Request body parse error: ${err.message}`,
                type: 'invalid_request_error',
                code: err.code || 'body_parse_error'
            }
        });
    }
    next(err);
});

// ── Memory Store Manager ────────────────────────────────────────────────────

const stores = new Map();

function getStore(workspaceId) {
    if (!stores.has(workspaceId)) {
        console.log(`[Store] Initializing new memory workspace: ${workspaceId}`);
        stores.set(workspaceId, new MemoryStore(
            path.resolve(config.persist_path),
            workspaceId
        ));
    }
    return stores.get(workspaceId);
}

// Pre-initialize the default store
const defaultStore = getStore(config.workspace_id);

// Start the memory audit safety net
startAutoAudit(defaultStore);

console.log(`\n🧠 Foveated Memory Proxy`);
console.log(`   Default Workspace : ${config.workspace_id} (${config.workspace_mode})`);
console.log(`   Upstream  : ${config.upstream_url}`);
console.log(`   Port      : ${config.proxy_port}`);
console.log(`   Mode      : ${COGNITIVE_MODE.toUpperCase()}${COGNITIVE_MODE === 'cloud' ? ' (Ollama Cloud)' : ' (LM Studio)'}`);
console.log(`   Compress  : LOCAL (XRLF Runtime :${XRLF_RUNTIME_URL.split(':').pop()}) — zero cloud tokens for checkpoints`);
console.log(`   Healer    : Self-healing context guard (${getBudget()} chars, auto-shrink/restore)`);

// ── Session ID per connection ───────────────────────────────────────────────

// Simple: generate one session ID per server run.
// In a future phase: parse from request headers or JWT.
const SESSION_ID = uuidv4().slice(0, 8);

// ── Dynamic Resolution Scaling (Holonic 12-Tier System) ────────────────────────
function scaleConfigForModel(modelName, baseConfig) {
    const model = (modelName || '').toLowerCase();
    let multiplier = 1.0;
    let label = "16K (Neural Starlight)"; // Default middle tier

    if (!REPO_ENABLED || !REPO_FOVEATION_OVERRIDE) {
        // Reactor cold or foveation override disabled — no scaling
        return { scaledConfig: JSON.parse(JSON.stringify(baseConfig)), label: "Passthrough (Reactor Cold)" };
    }

    // ── Load Holonic Resolution Config ───────────────────────────────────────
    let holonicConfig = null;
    try {
        const holonicPath = path.join(__dirname, 'memory_data', 'holonic-resolution.json');
        if (fs.existsSync(holonicPath)) {
            const raw = fs.readFileSync(holonicPath, 'utf8');
            holonicConfig = JSON.parse(raw);
        }
    } catch (e) {
        console.warn(`[Holonic] Could not load holonic-resolution.json: ${e.message}`);
    }

    // ── Holonic Tier Detection ─────────────────────────────────────────────────
    if (holonicConfig && holonicConfig.resolution_tiers) {
        // Use sophisticated 12-tier holonic system
        if (model.includes('0.1b') || model.includes('0.5b') || model.includes('tiny') || model.includes('quantum')) {
            const tier = holonicConfig.resolution_tiers['2K'];
            multiplier = tier.multiplier;
            label = tier.label;
        } else if (model.includes('0.3b') || model.includes('1b') || model.includes('micro') || model.includes('synaptic')) {
            const tier = holonicConfig.resolution_tiers['4K'];
            multiplier = tier.multiplier;
            label = tier.label;
        } else if (model.includes('0.5b') || model.includes('3b') || model.includes('mini') || model.includes('photon')) {
            const tier = holonicConfig.resolution_tiers['8K'];
            multiplier = tier.multiplier;
            label = tier.label;
        } else if (model.includes('7b') || model.includes('8b') || model.includes('neural') || model.includes('starlight')) {
            const tier = holonicConfig.resolution_tiers['16K'];
            multiplier = tier.multiplier;
            label = tier.label;
        } else if (model.includes('14b') || model.includes('27b') || model.includes('nebula') || model.includes('32k')) {
            const tier = holonicConfig.resolution_tiers['32K'];
            multiplier = tier.multiplier;
            label = tier.label;
        } else if (model.includes('32b') || model.includes('70b') || model.includes('galaxy') || model.includes('64k')) {
            const tier = holonicConfig.resolution_tiers['64K'];
            multiplier = tier.multiplier;
            label = tier.label;
        } else if (model.includes('72b') || model.includes('405b') || model.includes('universe') || model.includes('90k')) {
            const tier = holonicConfig.resolution_tiers['90K'];
            multiplier = tier.multiplier;
            label = tier.label;
        } else if (model.includes('claude-3.5') || model.includes('gpt-4o') || model.includes('gemini-1.5-pro') || model.includes('128k')) {
            const tier = holonicConfig.resolution_tiers['128K'];
            multiplier = tier.multiplier;
            label = tier.label;
        } else if (model.includes('claude-3.5-opus') || model.includes('gpt-4-turbo') || model.includes('gemini-1.5-ultra') || model.includes('180k')) {
            const tier = holonicConfig.resolution_tiers['180K'];
            multiplier = tier.multiplier;
            label = tier.label;
        } else if (model.includes('claude-3-opus') || model.includes('gpt-4') || model.includes('gemini-ultra') || model.includes('256k')) {
            const tier = holonicConfig.resolution_tiers['256K'];
            multiplier = tier.multiplier;
            label = tier.label;
        } else if (model.includes('cloud') || model.includes('omniscient') || model.includes('512k')) {
            const tier = holonicConfig.resolution_tiers['512K'];
            multiplier = tier.multiplier;
            label = tier.label;
        } else if (model.includes('ultimate') || model.includes('transcendent') || model.includes('1000k')) {
            const tier = holonicConfig.resolution_tiers['1000K'];
            multiplier = tier.multiplier;
            label = tier.label;
        }
    } else {
        // Fallback to simplified 5-tier system (legacy compatibility)
        if (model.includes('gemini-1.5') || model.includes('1m') || model.includes('2m') || model.includes('500k')) {
            multiplier = 25.0;
            label = "1M+ (Panoramic Ultra-HD)";
        } else if (model.includes('gpt-4') || model.includes('claude-3') || model.includes('128k') || model.includes('200k')) {
            multiplier = 10.0;
            label = "128K (Macula High-Res)";
        } else if (model.includes('32k') || model.includes('64k') || model.includes('mixtral') || model.includes('command-r')) {
            multiplier = 4.0;
            label = "32K (Medium-Res)";
        } else if (model.includes('8k') || model.includes('16k') || model.includes('llama3') || model.includes('llama-3')) {
            multiplier = 2.0;
            label = "8K (Enhanced)";
        } else if (model.includes('0.5b') || model.includes('1b') || model.includes('micro') || model.includes('tiny') || model.includes('retina')) {
            multiplier = 0.32;
            label = "Micro (Dense Retina)";
        }
    }

    // ── Manual Foveation Level Override (XRLF_PROXY_AGGRESSION) ──────────────
    // If XRLF_PROXY_AGGRESSION is set to 1-5, override the auto-detected multiplier
    // STANDARDIZED SCALE: Higher number = MORE aggressive compression
    // Level 0=Auto (model-detected), 1=Minimal, 2=Light, 3=Moderate, 4=Aggressive, 5=Maximum, 6=Off
    const aggressionLevel = parseInt(process.env.XRLF_PROXY_AGGRESSION || '0', 10);
    const aggressionMap = { 1: 0.5, 2: 1.0, 3: 2.0, 4: 4.0, 5: 8.0, 6: 0.0 };
    const aggressionLabels = {
        1: "L1 Minimal (x0.5)",
        2: "L2 Light (x1.0)",
        3: "L3 Moderate (x2.0)",
        4: "L4 Aggressive (x4.0)",
        5: "L5 Maximum (x8.0)",
        6: "L6 Off (no compression)"
    };
    if (aggressionLevel >= 1 && aggressionLevel <= 5 && aggressionMap[aggressionLevel]) {
        multiplier = aggressionMap[aggressionLevel];
        label = aggressionLabels[aggressionLevel];
        console.log(`[Fovea] Manual override: XRLF_PROXY_AGGRESSION=${aggressionLevel} → multiplier=${multiplier} (${label})`);
    }

    // ── NVIDIA Cloud Supermemory ─────────────────────────────────────────────
    // nvidia/* cloud models get a dedicated large ring budget — the foveated
    // memory expands to XRLF_NVIDIA_MEMORY_CAP tokens (default 64K). This is
    // applied AFTER the aggression lever, which governs local XRLF models only.
    if (isNvidiaModel(model)) {
        const cap = parseInt(process.env.XRLF_NVIDIA_MEMORY_CAP || '65536', 10);
        const base = Math.max(1, baseConfig.ring_token_budget || 8192);
        multiplier = cap / base;
        label = `${Math.round(cap / 1024)}K (Cloud Supermemory)`;
        console.log(`[Fovea] NVIDIA supermemory: ${label} — ring budget ${cap} tokens`);
    }

    // ── Log Holonic Tier Activation ───────────────────────────────────────────
    if (label.includes('Retina') || label.includes('Photon') || label.includes('Starlight')) {
        console.log(`[Holonic] 🔬 ${label} activated — low-powered retina cell firing like photons`);
    } else if (label.includes('Nebula') || label.includes('Galaxy') || label.includes('Universe')) {
        console.log(`[Holonic] 🌌 ${label} activated — resonant memory processing`);
    } else if (label.includes('Multiverse') || label.includes('Singularity') || label.includes('Quantum')) {
        console.log(`[Holonic] ✨ ${label} activated — time-reversal photon routing enabled`);
    }

    // Deep copy base config
    const scaled = JSON.parse(JSON.stringify(baseConfig));
    scaled.ring_token_budget = Math.max(128, Math.floor(baseConfig.ring_token_budget * multiplier));

    // ── Cloud Fovea Budget Overrides ───────────────────────────────────────
    // Each fovea level can be overridden via .env (XRLF_FOVEA1_CLOUD_BUDGET, etc.)
    // Map multiplier → fovea level number for env var lookup
    const foveaLevelMap = { '0.32': 1, '1.0': 2, '2.0': 3, '4.0': 4, '10.0': 5, '25.0': 6 };
    const foveaLevel = foveaLevelMap[String(multiplier)];
    if (foveaLevel) {
        const envVarName = `XRLF_FOVEA${foveaLevel}_CLOUD_BUDGET`;
        const envBudgetOverride = parseInt(process.env[envVarName] || '0', 10);
        if (envBudgetOverride > 0) {
            scaled.ring_token_budget = envBudgetOverride;
        }
    }
    scaled.recall_max_results = Math.max(2, Math.floor(baseConfig.recall_max_results * multiplier));

    // Scale fovea messages (keep at least 2 for context)
    const fovMult = multiplier > 2 ? 2 : (multiplier < 1 ? 0.5 : 1.5);
    scaled.fovea_message_count = Math.max(2, Math.floor(baseConfig.fovea_message_count * fovMult));

    // Scale ring budgets proportionally
    for (const key in scaled.ring_budgets) {
        scaled.ring_budgets[key] = Math.max(10, Math.floor(baseConfig.ring_budgets[key] * multiplier));
    }

    return { scaledConfig: scaled, label };
}

// ── Local upstream serializer ────────────────────────────────────────────────
// llama.cpp's CUDA pool asserts (GGML_ASSERT ptr == pool_addr + pool_used →
// SIGABRT) when decodes overlap on a single context. Serialize every call to
// the LOCAL runtime so only one upstream request is in flight at a time; the
// slot is held until the response body is fully consumed (end/close/error).
// Cloud routes (nvidia/*, cloud mode) bypass the queue.
const { acquireLocalUpstream, withLocalUpstream } = require('./core/local-upstream-queue');
const { logRequest, bodySnippet, readRecent, summarize } = require('./core/request-log');

// ── Core request handler ────────────────────────────────────────────────────

async function handleChatCompletion(req, res, injectMessages = null, store, workspaceId) {
    logDebug(`\n[${new Date().toISOString()}] handleChatCompletion started\n`);
    residency.touchTurn(); // never let idle-unload cut a live turn
    // ── Per-request effective settings (workspace overlay > global env) ──
    // The ignition trackball dials are user-scoped (setting_overlays/<ws>.json);
    // member sessions must honor THEIR dials, not the process's boot-time env.
    let effMode = COGNITIVE_MODE;
    let effModel = null;
    try {
        const ov = readSettingsOverlay(workspaceId);
        if (ov.XRLF_COGNITIVE_MODE) effMode = String(ov.XRLF_COGNITIVE_MODE).toLowerCase();
        if (ov.XRLF_MODEL_LOCAL_ID) effModel = String(ov.XRLF_MODEL_LOCAL_ID);
    } catch (_) {}
    const isEffCloud = effMode === 'cloud';
    const body     = { ...req.body };
    const isStream = body.stream === true;

    // ── Request telemetry (beta observability) ─────────────────────────────
    // Buffered JSONL writes — never blocks the response. Privacy: message
    // bodies only when FOVEAI_LOG_BODIES=1 (and then truncated snippets).
    const _logStart = Date.now();
    const _log = req._log = {
        model: body.model || null,
        stream: isStream,
        prompt_chars: JSON.stringify(body.messages || []).length,
        prompt_snip: bodySnippet(
            extractTextFromContent(
                (body.messages || []).filter(m => m && m.role === 'user').pop()?.content)),
    };
    let _logWritten = false;
    const _writeLog = (forcedError) => {
        if (_logWritten) return;
        _logWritten = true;
        logRequest({
            route: _log.route || 'unknown',
            model: _log.model,
            stream: _log.stream,
            status: res.statusCode,
            latency_ms: Date.now() - _logStart,
            user: req.userId || 'anonymous',
            error: forcedError || _log.error
                || (res.statusCode >= 400 ? `http_${res.statusCode}` : undefined),
            workspace: workspaceId,
            prompt_chars: _log.prompt_chars,
            reply_chars: _log.reply_chars,
            reasoning_chars: _log.reasoning_chars,
            prompt_snip: _log.prompt_snip,
            reply_snip: _log.reply_snip,
        });
    };
    res.on('finish', () => _writeLog());
    // Client abort mid-stream never emits 'finish' — catch it via 'close'.
    res.on('close', () => { if (!res.writableFinished) _writeLog('client_disconnect'); });

    // Protocol consumers (Multigate TTS/motor/XR) opt into raw avatar tags;
    // everyone else gets them stripped at this API boundary.
    const wantRaw = body.xrlf_raw === true || req.headers?.['x-foveai-raw'] === '1';
    delete body.xrlf_raw; // strict upstreams (NVIDIA NIM) reject unknown fields

    // Headless callers (IDE plugins, API scripts) get a soul prompt without
    // avatar markup — nothing downstream consumes <emotion>/<movement> tags
    // there, so generating them is wasted tokens/latency. Thought monologue
    // stays (it feeds memory). Embodied clients opt out via xrlf_raw.
    if (!wantRaw) body.xrlf_headless = true;

    // X-Deep-Think (Multigate toggle) → xrlf_thinking. When explicitly 'false'
    // the soul prompt drops the [MONOLOGUE] block so no <thought:> channel is
    // prompted at all; unset/true keeps thoughts available at will. Body field
    // `xrlf_thinking` works for direct callers; header takes precedence.
    const deepThinkHeader = req.headers?.['x-deep-think'];
    if (deepThinkHeader === 'true' || deepThinkHeader === 'false') {
        body.xrlf_thinking = deepThinkHeader === 'true';
    }

    // ── Auto-apply model profile ───────────────────────────────────────────────
    // Snap ALL settings (URL, mode, ctx, aggression, token caps) into place
    // for the requested model. No manual env var sync ever needed again.
    if (body.model && !injectMessages) {
        const profile = applyProfile(body.model, config);
        if (!profile) {
            console.warn(`[ModelProfile] ⚠️ No profile for '${body.model}' — add to memory_data/model-profiles.json. Using current settings.`);
        } else {
            // Reconfigure context budget for the provider
            // XRLF local → 16K chars max, Cloud → 50K chars max
            reconfigureForProvider(profile.provider || (profile.cognitive_mode === 'cloud' ? 'cloud' : 'xrlf_proxy'));
        }
    }

    // Dynamically scale memory resolution based on the requested model
    const { scaledConfig, label } = scaleConfigForModel(body.model, config);
    logDebug(`[${new Date().toISOString()}] scaleConfigForModel finished. Model=${body.model}\n`);
    if (!injectMessages) {
        console.log(`[Memory Resolution] Model '${body.model || 'unknown'}' mapped to ${label}. Budget: ${scaledConfig.ring_token_budget} tokens`);
    }

    const activeSessionId = req.body?.session_id || req.headers['x-session-id'] || (workspaceId + '_' + SESSION_ID);

    // Persist incoming tasks if provided by the client
    if (body._tasks) {
        try {
            await store.saveTasks(activeSessionId, body._tasks);
        } catch (e) {
            console.warn('[Tasks] Failed to save tasks:', e.message);
        }
    }

    // Build the foveated ring block for this session
    let ringBlock = '';
    try {
        logDebug(`[${new Date().toISOString()}] before buildRingBlock\n`);
        ringBlock = (REPO_ENABLED && REPO_FOVEATION_OVERRIDE) ? await buildRingBlock(store, scaledConfig, activeSessionId) : '';
        logDebug(`[${new Date().toISOString()}] after buildRingBlock\n`);
    } catch (e) {
        console.warn('[Rings] Failed to build ring block:', e.message);
    }

    // Build the Agent HUD with task board, repo skeleton, and diagnostics
    let hudBlock = '';
    if (REPO_ENABLED && REPO_FOVEATION_OVERRIDE) {
        try {
            const tasks = await store.getTasks(activeSessionId);
            const pendingTasks = tasks.filter(t => !t.done).map(t => t.text);
            const clearedTasks = tasks.filter(t => t.done).map(t => t.text);
            
            // Get recent file diagnostics from linter module
            const recentFileDiagnostics = getSessionDiagnostics(activeSessionId);
            
            hudBlock = await buildMembraneHUD({
                redThread: body.messages?.[0]?.content?.slice(0, 200) || 'AI Pair Programming Session',
                turnCount: body.messages?.length || 0,
                clearedTasks,
                pendingTasks,
                recentFileDiagnostics,
                tokenBudget: scaledConfig.ring_token_budget || 8192,
                backendInfo: { model: body.model }
            });
            
            if (hudBlock) {
                console.log('[MembraneBridge] 🔌 HUD built with repo skeleton and diagnostics');
            }
        } catch (e) {
            console.warn('[MembraneBridge] Failed to build HUD:', e.message);
        }
    }

    // Prepend HUD to ring block for unified context injection
    if (hudBlock) {
        ringBlock = hudBlock + '\n\n' + (ringBlock || '');
    }

    // ── Juggle / Tandem mode ────────────────────────────────────────────────
    // model:'juggle'|'tandem' — or XRLF_COGNITIVE_MODE=juggle — routes the
    // prompt through Backend/Creativity/tandem.py (local routers + free NIM
    // juggle race + gemini plan/synth). Answer is relayed as one OpenAI-shaped
    // completion. The memory pipeline above stays untouched.
    const juggleRequested =
        body.model === 'juggle' || body.model === 'tandem' || body.model === 'legion'
        || effMode === 'juggle' || effMode === 'legion';
    if (juggleRequested && !injectMessages) {
        const convo = (body.messages || [])
            .filter(m => m && (m.role === 'user' || m.role === 'assistant' || m.role === 'system'))
            .map(m => ({
                role: m.role,
                content: typeof m.content === 'string'
                    ? m.content
                    : extractTextFromContent(m.content)
            }))
            .filter(m => typeof m.content === 'string' && m.content.length);
        const userText = convo.filter(m => m.role === 'user').pop()?.content;
        const prompt = typeof userText === 'string'
            ? userText : extractTextFromContent(userText);
        // History travels with the prompt — Jen must not answer blind.
        const historyJson = JSON.stringify(convo.slice(-12));
        if (prompt) {
            console.log(`[Juggle+Legion] ▶️ tandem+legion run for: ${prompt.slice(0, 80)}… (${convo.length} msgs of context)`);
            const pyBin = process.env.FOVEAI_VENV_PYTHON || '/home/lumba/FoveAI/.venv/bin/python';
            try {
                const { stdout, stderr } = await new Promise((resolve) => {
                    const { execFile } = require('child_process');
                    const child = execFile(pyBin,
                        ['-u', '/home/lumba/FoveAI/Backend/Creativity/tandem.py', '--legion', prompt, '--history', historyJson],
                        { timeout: 180000, maxBuffer: 4 * 1024 * 1024,   // ms, not python-seconds!
                          cwd: '/home/lumba/FoveAI/Backend/Creativity' },
                        (err, stdout, stderr) => resolve({ err, stdout, stderr }));
                    child.once('error', (e) => console.warn('[Juggle] child error event:', e.message));
                    child.once('exit', (code, signal) => console.warn('[Juggle] child exit:', code, signal));
                }).then(r => {
                    if (r.err) console.warn('[Juggle] tandem err:', (r.stderr || '').slice(0, 800),
                        '| code:', r.err.code, '| killed:', r.err.killed,
                        '| signal:', r.err.signal || '-',
                        '| msg:', (r.err.message || '').slice(0, 160));
                    return { stdout: r.stdout || '', stderr: r.stderr || '' };
                });
                let answer = (stdout || '').trim();
                // first-call-after-restart flake: juggler race cold → rc=2.
                // One retry usually lands (state warms on the first try).
                if (!answer) {
                    console.warn('[Juggle] empty answer — retrying once');
                    const { execFile: exec2 } = require('child_process');
                    const r2 = await new Promise((resolve) => {
                        exec2(pyBin,
                            ['-u', '/home/lumba/FoveAI/Backend/Creativity/tandem.py', '--legion', prompt, '--history', historyJson],
                            { timeout: 180000, maxBuffer: 4 * 1024 * 1024,
                              cwd: '/home/lumba/FoveAI/Backend/Creativity' },
                            (err, so, se) => resolve({ err, so, se }));
                    });
                    answer = (r2.so || '').trim();
                }
                // Junk guard: a bare route tag or near-empty leg output is a
                // router artefact, never Jen's answer — fall through instead.
                const junk = !answer
                    || answer.length < 2
                    || /^\s*<\/?[a-z_-]+:[^>]*>\s*$/i.test(answer)
                    || /^(route|tag|keep|compress)\s*[:=]/i.test(answer);
                if (junk) {
                    console.warn(`[Juggle] ⚠️ router artefact discarded (${JSON.stringify(answer.slice(0, 60))}) — falling back to upstream`);
                    baseMessages = processedMessages;
                } else {
                    console.log(`[Juggle] ✅ ${answer.length} chars ${stderr ? `| ${stderr.split('\n').pop()}` : ''}`);
                    _log.reply_chars = answer.length;
                    const now = Date.now() / 1000;
                    const shape = {
                        id: 'chatcmpl-juggle-' + now,
                        object: 'chat.completion',
                        created: Math.floor(now),
                        model: body.model || 'juggle',
                        choices: [{
                            index: 0,
                            message: { role: 'assistant', content: answer },
                            finish_reason: 'stop',
                        }],
                        usage: {
                            prompt_tokens: Math.ceil((JSON.stringify(body.messages) || '').length / 4),
                            completion_tokens: Math.ceil(answer.length / 4),
                            total_tokens: 0,
                        },
                    };
                    if (isStream) {
                        // one chunk containing the whole answer, then [DONE]
                        res.writeHead(200, {
                            'Content-Type': 'text/event-stream',
                            'Cache-Control': 'no-cache',
                            'Connection': 'keep-alive',
                        });
                        res.write(`data: ${JSON.stringify({ ...shape, choices: [{ index: 0, delta: { role: 'assistant', content: answer }, finish_reason: null }] })}\n\n`);
                        res.write('data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\n');
                        res.write('data: [DONE]\n\n');
                        res.end();
                    } else {
                    res.json(shape);
                    }
                }
                return; // juggle answered — skip the standard pipeline
            } catch (e) {
                console.error('[Juggle] tandem failed:', e.message, '— fall through to standard pipeline');
                // falls through to normal routing on failure
            }
        }
    }

    // ── XRL Context Compression ──────────────────────────────────────────
    // Compress old turns into XRL checkpoints before patching (transparent)
    // In cloud mode, ensure LM Studio is running for local compression checkpoints
    // Fire-and-forget: don't block the request stream waiting for LM Studio startup
    if (isEffCloud) {
        ensureLMStudio().catch(e => console.warn('[AutoStart] Background LM Studio check failed:', e.message));
    }

    const rawMessages   = injectMessages || body.messages || [];
    console.log(`[handleChatCompletion] ▶️ entry | inject=${!!injectMessages} | rawMessages=${rawMessages.length} | session=${activeSessionId}`);

    // ── Code Preservation: Extract protected structures BEFORE stripping ──
    // This ensures code fences, thinking blocks, JSON schemas, and tool
    // definitions survive the aggressive stripping/compression pipeline.
    const PRESERVE_CODE = REPO_ENABLED && REPO_CAPABILITY_OVERRIDE && process.env.XRLF_PRESERVE_CODE !== '0' && process.env.XRLF_PRESERVE_CODE !== 'false';
    let preservationStore = null;
    let preservedMessages = rawMessages;
    if (PRESERVE_CODE) {
        const result = extractFromMessages(rawMessages);
        preservationStore = result.store;
        console.log(`[CodePreserver] 🔒 Extracted ${preservationStore.size} protected blocks (${[...preservationStore.values()].reduce((n, e) => n + e.content.length, 0)} chars)`);
        preservedMessages = result.messages;
    }

    logDebug(`[${new Date().toISOString()}] before stripThinking and dedupeFileReads\n`);
    // XRLF-Skeletonizer pre-processing
    let processedMessages = preservedMessages.map(m => ({
        ...m,
        content: typeof m.content === 'string' ? stripThinking(m.content) : m.content
    }));
    processedMessages = dedupeFileReads(processedMessages);
    logDebug(`[${new Date().toISOString()}] after dedupeFileReads\n`);

    // ── Track files mentioned in messages for linter diagnostics ─────────────
    if (REPO_ENABLED && REPO_FOVEATION_OVERRIDE) {
        for (const msg of processedMessages) {
            if (typeof msg.content === 'string') {
                // Extract file paths from common patterns
                const filePatterns = [
                    /(?:created|modified|updated|edited|wrote|saved)\s+([^\s]+\.(?:py|js|ts|jsx|tsx|json|md))/gi,
                    /(?:file|path):\s*([^\s]+\.(?:py|js|ts|jsx|tsx))/gi,
                    /([a-zA-Z]:[\\\/][^\s]+\.(?:py|js|ts|jsx|tsx))/g // Windows paths
                ];
                
                for (const pattern of filePatterns) {
                    const matches = msg.content.match(pattern);
                    if (matches) {
                        for (const match of matches) {
                            // Extract the file path from the match
                            const filePath = match.replace(/^(?:created|modified|updated|edited|wrote|saved|file|path):\s*/i, '').trim();
                            trackFile(activeSessionId, filePath);
                        }
                    }
                }
            }
        }
        
        // Run linters on tracked files (async, non-blocking)
        lintSession(activeSessionId).catch(err => {
            console.warn('[LinterFeedback] Failed to lint session:', err.message);
        });
    }

    // Multimodal content detection
    if (hasMultimodalMessages(processedMessages)) {
        console.log('[Multimodal] 🖼️ Request contains image content — passthrough mode');
    }

    let baseMessages = processedMessages;
    const AUTO_CHECKPOINT = REPO_ENABLED && REPO_CONTEXT_OVERRIDE && process.env.XRLF_PROXY_AUTO_CHECKPOINT !== '0' && process.env.XRLF_PROXY_AUTO_CHECKPOINT !== 'false';
    const reqCompressLevel = req.headers['x-compression-level'] ? parseInt(req.headers['x-compression-level'], 10) : 3;

    // ── Shadow Context: Save full-fidelity blocks to disc BEFORE compression ──
    // The model can zoom back into these via <zoom: "hash"> at any time.
    // The retina classifier ensures only HIGH-value context gets shadow storage.
    // MEDIUM goes to XRL checkpoint, LOW stays ephemeral, ZERO is discarded.
    const SHADOW_ENABLED = REPO_ENABLED && REPO_FOVEATION_OVERRIDE && process.env.XRLF_SHADOW_CONTEXT !== '0' && process.env.XRLF_SHADOW_CONTEXT !== 'false';
    const RETINA_ENABLED = REPO_ENABLED && REPO_FOVEATION_OVERRIDE && process.env.XRLF_RETINA !== '0' && process.env.XRLF_RETINA !== 'false';
    let shadowRefs = [];
    let retinaStats = null;
    let retinaScoresByContent = new Map(); // Store content -> retina score mapping
    if (SHADOW_ENABLED) {
        try {
            const turnMsgs = processedMessages.filter(m => m.role !== 'system');

            if (RETINA_ENABLED) {
                // ── Retina: classify each message by value ──
                const classification = classifyBatch(turnMsgs);
                retinaStats = formatRetinaStats(classification.stats);
                console.log(`[Retina] 🧬 ${retinaStats.distribution.high} high | ${retinaStats.distribution.medium} med | ${retinaStats.distribution.low} low | ${retinaStats.distribution.zero} zero | ${retinaStats.savedPct}% chars saved by discarding zero-value`);

                // Store retina scores by content for later lookup in store()
                for (const msg of turnMsgs) {
                    if (msg._retina) {
                        retinaScoresByContent.set(msg.content, msg._retina.score);
                    }
                }

                // Only HIGH-value messages get shadow storage
                for (let i = 0; i < classification.shadow.length; i++) {
                    const msg = classification.shadow[i];
                    const ref = saveShadowBlock(activeSessionId, [msg], {
                        turnRange: [i + 1, i + 1],
                        value: VALUE.HIGH,
                        signals: msg._retina?.signals
                    });
                    if (ref) shadowRefs.push(ref);
                }
            } else {
                // Retina disabled — save all turn pairs (legacy behavior)
                for (let i = 0; i < turnMsgs.length; i += 2) {
                    const batch = turnMsgs.slice(i, i + 2);
                    if (batch.length > 0) {
                        const ref = saveShadowBlock(activeSessionId, batch, {
                            turnRange: [i + 1, i + batch.length]
                        });
                        if (ref) shadowRefs.push(ref);
                    }
                }
            }

            if (shadowRefs.length > 0) {
                console.log(`[ShadowContext] 💾 Saved ${shadowRefs.length} shadow blocks for session ${activeSessionId}`);
            }
        } catch (e) {
            console.warn('[ShadowContext] Save failed (non-critical):', e.message);
        }
    }

    if (AUTO_CHECKPOINT) {
        try {
            baseMessages = await compressContext(processedMessages, activeSessionId, reqCompressLevel);
        } catch (e) {
            console.warn('[Compress] compressContext failed, using raw messages:', e.message);
        }
    } else {
        console.log('[Compress] ⏭️ Auto-checkpointing disabled via .env');
    }

    // Final cloud budget safety trim (keeps last N turns protected)
    baseMessages = enforceCloudBudget(baseMessages, body.model || UPSTREAM_MODEL);

    // ── Smart Proxy Context Router ───────────────────────────────────────
    // The smart router's middleman (routing/compression) ALWAYS goes to local
    // LM Studio — never to the cloud. Cloud models handle chat only.
    // Skipped for xrlf_server (local ctx is already guarded by the compressor,
    // ContextHealer and runtime adapt_context), and OFF BY DEFAULT everywhere:
    // the dedicated middleman/router models are gone, so routing runs through
    // the main model and its keep-index decisions silently amputate context.
    // Opt back in explicitly with XRLF_SMART_PROXY=1 if ever needed.
    const isXrlfServer = (config._active_profile && config._active_profile.provider === 'xrlf_server')
        || (config.upstream_url || '').replace(/\/v1\/?$/, '') === XRLF_RUNTIME_URL.replace(/\/v1\/?$/, '');
    const SMART_PROXY_ENABLED = !isXrlfServer && REPO_ENABLED && REPO_CONTEXT_OVERRIDE
        && (process.env.XRLF_SMART_PROXY === '1' || process.env.XRLF_SMART_PROXY === 'true');
    if (SMART_PROXY_ENABLED) {
        try {
            const { smartRouteMessages } = require('./core/smart-router');
            const routerUpstream = `${XRLF_RUNTIME_URL}/v1`;  // always local for routing
            const middleman = (typeof MIDDLEMAN_MODEL !== 'undefined') ? MIDDLEMAN_MODEL : 'qwen2.5-0.5b-instruct';
            baseMessages = await smartRouteMessages(baseMessages, middleman, routerUpstream);
        } catch (e) {
            console.warn('[Smart Router] smartRouteMessages failed, using unrouted messages:', e.message);
        }
    }

    console.log(`[handleChatCompletion] 📦 baseMessages=${baseMessages.length} (raw=${rawMessages.length})`);

    logDebug(`[${new Date().toISOString()}] before patchMessages\n`);
    // Patch messages with ring block + ACTIVE RECALL instructions
    // Local XRLF (:8402) composes its own principia+membrane+soul system prompt
    // via _inject_system — so skip the proxy RING there (avoids double memory
    // injection), but still send the HUD (task board, repo skeleton, diagnostics),
    // compact persona, memory protocol and resume context: the runtime merges
    // them into its system message. Cloud/LLM-studio paths get the full ring.
    const nvidiaRequested = isNvidiaModel(body.model || '');
    const novaRequested = isNovaModel(body.model || '');
    const freeCloudRequested = isFreeCloudModel(body.model || '');
    const ollamaRequested = isOllamaModel(body.model || '');
    const byokRequested = isByokModel(body.model || '');
    const patchRing = isXrlfServer ? hudBlock : ringBlock;
    body.messages = (REPO_ENABLED && REPO_CAPABILITY_OVERRIDE) ? patchMessages(baseMessages, patchRing, scaledConfig, body) : baseMessages;
    logDebug(`[${new Date().toISOString()}] after patchMessages\n`);

    // ── Self-Healing Context Guard ────────────────────────────────────────
    // Auto-scaling context budget that shrinks on upstream failure and
    // gradually recovers. Replaces the old static CTX_MAX_CHARS truncation.
    // Agentic door: coding clients (opencode) speak the -agentic alias —
    // the ride expands to the engine's full capacity (64000 signs) and the
    // suffix is stripped before the engine sees the model name.
    const CTX_KEEP_LAST = parseInt(process.env.XRLF_CTX_KEEP_LAST || '6', 10);
    const isAgentic = !!(body.model && body.model.endsWith('-agentic'));
    if (isAgentic) {
        body.model = body.model.slice(0, body.model.length - '-agentic'.length);
    }
    const requestBudget = parseInt(req.headers['x-context-budget'] || '0', 10)
        || (isAgentic ? 64000 : 0);
    const budgetResult = (REPO_ENABLED && REPO_CONTEXT_OVERRIDE) ? applyBudget(body.messages, CTX_KEEP_LAST, requestBudget) : { messages: body.messages, truncated: false, originalChars: 0, finalChars: 0, warning: '' };
    const { messages: budgetedMessages, truncated, originalChars, finalChars, warning } = budgetResult;
    body.messages = budgetedMessages;

    // ── Code Preservation: Restore protected structures AFTER pipeline ──
    // Swap [PRESERVED:hash:type] tokens back to original code blocks.
    if (PRESERVE_CODE && preservationStore && preservationStore.size > 0) {
        body.messages = restoreToMessages(body.messages, preservationStore);
        console.log(`[CodePreserver] 🔓 Restored ${preservationStore.size} protected blocks into final messages`);
    }
    if (truncated) {
        console.warn(`[ContextHealer] ⚠️ Budget applied: ${originalChars} → ${finalChars} chars. Budget=${getBudget()}. Warning: ${warning}`);
    }

    // ── HARD CAP: Final safety net before sending upstream ───────────────
    // No matter what happened above (code restoration, ring injection, etc.),
    // the total chars sent upstream must NEVER exceed the planned budget.
    // This is the absolute last line of defense against flooding the model.
    {
        let finalTotalChars = 0;
        for (const m of body.messages) {
            finalTotalChars += typeof m.content === 'string' ? m.content.length : JSON.stringify(m.content || '').length;
        }
        const hardCap = getBudget();
        if (finalTotalChars > hardCap) {
            console.warn(`[HardCap] 🚫 Post-pipeline total ${finalTotalChars} > hard cap ${hardCap} — force truncating`);
            // Re-apply budget one more time on the final messages
            const hardCapResult = applyBudget(body.messages, CTX_KEEP_LAST, hardCap);
            body.messages = hardCapResult.messages;
            if (hardCapResult.truncated) {
                console.warn(`[HardCap] ✂️ Force-truncated ${finalTotalChars} → ${hardCapResult.finalChars} chars. NOTHING over ${hardCap} leaves this proxy.`);
            }
        }
    }

    // Preserve client's original stream preference
    body.stream = isStream;

    // ── Model Resolution ──────────────────────────────────────────────────────
    const originalModel = body.model || '';
    const isLocalLMStudio = config.upstream_url.includes('127.0.0.1') || config.upstream_url.includes('localhost');

    // In cloud mode, pass through the client's model name — don't override it.
    // Only override when: (a) local LM Studio needs a specific model, or (b) model is 'auto'/empty.
    // NVIDIA side-routes are exempt — the nvidia/<id> name selects the upstream below.
    // Cloud quota: nvidia/* models ride the owner's shared free-tier key, so
    // member access is feature-gated AND metered — per-user and pool-wide
    // daily caps keep beta usage from flagging or exhausting the key.
    // Legacy/local callers are exempt: the owner's own traffic is uncapped.
    if (nvidiaRequested || freeCloudRequested) {
        const mgr = getAuthManager(AUTH_DB_DIR);
        const na = resolveRequestAuth(req);
        if (!mgr.hasFeature({ role: na.role, features: na.features }, 'cloud')) {
            return res.status(403).json({ error: 'cloud models are not enabled for this account' });
        }
        if (!na.isLegacy) {
            const USER_CAP = parseInt(process.env.FOVEAI_CLOUD_DAILY_PER_USER || '50', 10);
            const GLOBAL_CAP = parseInt(process.env.FOVEAI_CLOUD_DAILY_GLOBAL || '400', 10);
            const used = mgr.usageToday(na.userId, 'cloud');
            const pool = mgr.usageToday('__global__', 'cloud');
            if (used >= USER_CAP || pool >= GLOBAL_CAP) {
                return res.status(429).json({ error: `daily cloud quota reached (${Math.min(used, USER_CAP)}/${USER_CAP} yours · ${pool}/${GLOBAL_CAP} pool) — local models stay unlimited` });
            }
            mgr.bumpUsage(na.userId, 'cloud');
            mgr.bumpUsage('__global__', 'cloud');
        }
    }

    // BYOK: resolve the caller's own cloud key before any model override —
    // 'byok' uses their stored default model, 'byok/<model>' overrides it.
    let byokCfg = null;
    if (byokRequested) {
        const mgr = getAuthManager(AUTH_DB_DIR);
        const byokAuth = resolveRequestAuth(req);
        if (!mgr.hasFeature({ role: byokAuth.role, features: byokAuth.features }, 'byok')) {
            return res.status(403).json({ error: 'byok feature not enabled for this account' });
        }
        byokCfg = req.userId && req.userId !== 'anonymous' ? mgr.getByok(req.userId) : null;
        if (!byokCfg) {
            return res.status(400).json({ error: 'no cloud key configured — add one under "Bring your own model" on /user-settings.html' });
        }
        body.model = String(body.model).replace(/^byok\/?/, '') || byokCfg.model;
        if (!body.model) {
            return res.status(400).json({ error: 'BYOK needs a model — set a default on your settings page or request byok/<model>' });
        }
        delete body.session_id; delete body._tasks; delete body.tasks;
        delete body.persona; delete body.workspaceId; delete body.workspace_id;
        delete body.xrlf_headless; delete body.xrlf_thinking;
        console.log(`[BYOK] user=${req.userId} provider=${byokCfg.provider} model=${body.model}`);
    }

    if (ollamaRequested) {
        if (!OLLAMA_API_KEY) {
            return res.status(400).json({ error: 'no Ollama Cloud key configured (OLLAMA_API_KEY / XRLF_PROXY_API_KEY)' });
        }
        const oMgr = getAuthManager(AUTH_DB_DIR);
        const oNa = resolveRequestAuth(req);
        if (!oMgr.hasFeature({ role: oNa.role, features: oNa.features }, 'cloud')) {
            return res.status(403).json({ error: 'cloud models are not enabled for this account' });
        }
    }

    const shouldOverride = !nvidiaRequested && !byokRequested && !freeCloudRequested &&
        !ollamaRequested && !novaRequested &&
        ((isLocalLMStudio && !isEffCloud) || originalModel === 'auto' || !originalModel);
    if (nvidiaRequested) {
        body.model = originalModel.slice(NVIDIA_PREFIX.length);
        body.messages = injectNvidiaContext(body.messages);
        // Strip custom client parameters that strict NVIDIA NIM schema validation rejects (HTTP 400)
        stripCloudParams(body);
        console.log(`[NVIDIA] Routing '${originalModel}' → NVIDIA NIM as '${body.model}'`);
    } else if (freeCloudRequested) {
        body.model = FREE_CLOUD_MODEL;
        body.messages = injectNvidiaContext(body.messages);
        stripCloudParams(body);
        console.log(`[NVIDIA] Routing '${FREE_CLOUD_ID}' → NVIDIA NIM as '${body.model}'`);
    } else if (ollamaRequested) {
        body.model = originalModel.slice(OLLAMA_PREFIX.length);
        if (!body.model) {
            return res.status(400).json({ error: 'Ollama Cloud needs a model — request ollama/<model>' });
        }
        stripCloudParams(body);
        console.log(`[OLLAMA] Routing '${originalModel}' → Ollama Cloud as '${body.model}'`);
    }
    if (nvidiaRequested || freeCloudRequested) {
        // NIM reasoning control + output cap. kimi-k3 defaults to
        // reasoning_effort=max which — combined with the 64K supermemory
        // ring — pushed every turn into the client-side timeout.
        const effort = (process.env.FOVEAI_NVIDIA_REASONING || 'low').toLowerCase().trim();
        body.reasoning_effort = { true: 'high', false: 'low', on: 'high', off: 'low' }[effort] || effort;
        if (!body.max_tokens) {
            body.max_tokens = parseInt(process.env.XRLF_NVIDIA_MAX_TOKENS || '2048', 10);
        }
    }
    const currentEnvModel = isEffCloud
        ? (process.env.XRLF_MODEL_CLOUD_ID || process.env.XRLF_PROXY_MODEL || UPSTREAM_MODEL).trim()
        : (process.env.XRLF_MODEL_LOCAL_ID || process.env.XRLF_PROXY_MODEL || UPSTREAM_MODEL).trim();
    if (shouldOverride) {
        body.model = currentEnvModel;
        console.log(`[Model] Resolved '${originalModel}' → '${body.model}' (Env target: ${currentEnvModel})`);
    } else {
        console.log(`[Model] Passthrough model: '${body.model}' (no override). Cognitive mode: ${COGNITIVE_MODE}`);
    }
    _log.route = nvidiaRequested ? 'nvidia' : freeCloudRequested ? 'nvidia-free'
        : ollamaRequested ? 'ollama'
        : novaRequested ? 'nova'
        : byokRequested ? 'byok' : (config._cloud_mode ? 'cloud' : 'local');
    _log.model = body.model;

    // ── Self-Healing Upstream Fetch (with retry loop) ────────────────────
    const MAX_CTX_RETRIES = parseInt(process.env.XRLF_CTX_MAX_RETRIES || '3', 10);
    let upstreamRes;
    let retryCount = 0;
    let lastErrorText = '';
    let lastErrorStatus = 0;

    while (retryCount <= MAX_CTX_RETRIES) {
        try {
            const upstreamHeaders = { 'Content-Type': 'application/json' };
            if (nvidiaRequested || freeCloudRequested) {
                upstreamHeaders['Authorization'] = `Bearer ${NVIDIA_API_KEY}`;
            } else if (byokRequested) {
                upstreamHeaders['Authorization'] = `Bearer ${byokCfg.apiKey}`;
            } else if (ollamaRequested) {
                upstreamHeaders['Authorization'] = `Bearer ${OLLAMA_API_KEY}`;
            } else if (config._cloud_mode && config._api_key) {
                upstreamHeaders['Authorization'] = `Bearer ${config._api_key}`;
            }

            // P2P Swarm Routing: Determine best available local node based on capability
            const swarmRouter = getSwarmRouter(path.resolve(__dirname, 'memory_data'));
            const requiredCapability = swarmRouter.detectCapability(body.messages);
            let targetUpstream = (nvidiaRequested || freeCloudRequested) ? NVIDIA_BASE_URL
                : ollamaRequested ? OLLAMA_CLOUD_URL
                : novaRequested ? NOVA_URL
                : byokRequested ? (byokCfg.baseUrl || BYOK_PROVIDER_URLS[byokCfg.provider])
                : config.upstream_url;

            if (byokRequested && !targetUpstream) {
                return res.status(400).json({ error: `BYOK provider '${byokCfg.provider}' needs a custom base URL — set one on your settings page` });
            }

            // Only use Swarm Router in local Cognitive Mode and when repo context override is enabled
            // Only use Swarm Router in local Cognitive Mode and when repo context override is enabled.
// ollama/* must be excluded like the other explicit side-routes: the swarm picks a
// LOCAL node, which silently replaced the Ollama Cloud upstream and sent the
// request to the local runtime — surfacing as a confusing context-overflow 500.
if (!nvidiaRequested && !freeCloudRequested && !byokRequested && !ollamaRequested && !novaRequested &&
        !isEffCloud && REPO_ENABLED && REPO_CONTEXT_OVERRIDE) {
                const bestNode = swarmRouter.route(requiredCapability);
                if (bestNode) {
                    targetUpstream = bestNode;
                    logDebug(`[SwarmRouter] Routing task (capability: ${requiredCapability}) to ${targetUpstream}`);
                }
            }

            // Ensure upstream URL doesn't have double /v1 if node already has it
            let fetchUrl = `${targetUpstream}/v1/chat/completions`;
            if (targetUpstream.endsWith('/v1')) fetchUrl = `${targetUpstream}/chat/completions`;

            logDebug(`[${new Date().toISOString()}] before fetch to ${fetchUrl} (attempt ${retryCount + 1}/${MAX_CTX_RETRIES + 1})\n`);
            // Serialize concurrent requests to the local runtime — overlapping
            // decode frees trip llama.cpp's CUDA pool assert → SIGABRT (see
            // runtime_stderr.log). Slot is released when the response body ends.
            const isLocalTarget = !nvidiaRequested && !freeCloudRequested && !byokRequested && !novaRequested && !(config._cloud_mode && config._api_key) && !isEffCloud;
            // ── Residency gate ──────────────────────────────────────────
            // A managed local port with no tier resident is not a failure —
            // it is Jen asleep. Wake her and tell the caller, don't 502.
            if (isLocalTarget) {
                residency.touchTurn();
                const managed = residency.managedTier(targetUpstream);
                if (managed) {
                    const cur = residency.resident();
                    const ready = cur && cur.tier === managed && (cur.state === 'present' || !cur.state);
                    if (!ready) {
                        residency.requestWake(managed);
                        return res.status(200).json({
                            id: `chatcmpl-${uuidv4().slice(0, 8)}`,
                            object: 'chat.completion',
                            model: body.model || 'foveated-proxy',
                            choices: [{ message: { role: 'assistant', content: residency.wakeNotice(managed) }, index: 0, finish_reason: 'waking' }],
                            usage: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 },
                            _residency: { waking: managed },
                        });
                    }
                }
            }
let releaseSlot = null;
            if (isLocalTarget) {
                releaseSlot = await acquireLocalUpstream();
            }
            try {
                upstreamRes = await fetch(fetchUrl, {
                    method: 'POST',
                    headers: upstreamHeaders,
                    body: JSON.stringify(body),
                    signal: AbortSignal.timeout(
                        parseInt(process.env.XRLF_UPSTREAM_TIMEOUT_MS || '300000', 10))
                });
            } catch (fetchErr) {
                if (releaseSlot) releaseSlot();
                throw fetchErr;
            }
            if (releaseSlot) {
                let released = false;
                const rel = () => { if (!released) { released = true; releaseSlot(); } };
                upstreamRes.body.once('end', rel);
                upstreamRes.body.once('close', rel);
                upstreamRes.body.once('error', rel);
                setTimeout(rel, 10 * 60 * 1000).unref();
            }
            logDebug(`[${new Date().toISOString()}] after fetch to upstream\n`);

            // Success — notify healer
            if (upstreamRes.ok) {
                onSuccess();
                break; // exit retry loop
            }

            // Non-OK response — collect error text
            lastErrorText = await upstreamRes.text();
            lastErrorStatus = upstreamRes.status;
            console.error(`[Proxy] Upstream returned ${upstreamRes.status}: ${lastErrorText.slice(0, 500)}`);

            // Diagnose: is this a context overflow?
            const { shrunk, shouldRetry, reason } = onFailure(upstreamRes.status, lastErrorText, '');

            if (shrunk && shouldRetry && retryCount < MAX_CTX_RETRIES) {
                // Re-apply budget with the new (smaller) limit
                const { messages: retryMessages, warning: retryWarning } = applyBudget(body.messages, CTX_KEEP_LAST, requestBudget);
                body.messages = retryMessages;
                retryCount++;
                console.log(`[ContextHealer] 🔄 Retry ${retryCount}/${MAX_CTX_RETRIES} with budget=${getBudget()} chars (reason: ${reason})`);
                continue; // retry
            }

            // Can't retry — return error as valid JSON with choices
            console.error(`[ContextHealer] ❌ Giving up after ${retryCount} retries. Budget=${getBudget()}.`);
            const isCtx = reason && reason.includes('context');
            const errorContent = isCtx
                ? `⚠️ Context overflow: The upstream model could not process this request even after auto-shrinking the context to ${getBudget()} chars. Please reduce the input size or increase XRLF_CANONICAL_CTX. (Upstream: ${upstreamRes.status})`
                : `⚠️ Upstream error ${upstreamRes.status}: ${(lastErrorText || reason || 'Unknown error').slice(0, 300)}`;
            return res.status(upstreamRes.status).json({
                id: `chatcmpl-${uuidv4().slice(0, 8)}`,
                object: 'chat.completion',
                model: body.model || 'foveated-proxy',
                choices: [{
                    message: {
                        role: 'assistant',
                        content: errorContent
                    },
                    index: 0,
                    finish_reason: 'error'
                }],
                usage: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 },
                _healer: { budget: getBudget(), retries: retryCount, reason }
            });

        } catch (err) {
            console.error('[Proxy] Upstream connection failed:', err.message);
            lastErrorText = err.message;
            lastErrorStatus = 0;

            const { shrunk, shouldRetry, reason } = onFailure(0, err.message, '');

            if (shrunk && shouldRetry && retryCount < MAX_CTX_RETRIES) {
                const { messages: retryMessages } = applyBudget(body.messages, CTX_KEEP_LAST, requestBudget);
                body.messages = retryMessages;
                retryCount++;
                console.log(`[ContextHealer] 🔄 Retry ${retryCount}/${MAX_CTX_RETRIES} after connection error (budget=${getBudget()})`);
                continue;
            }

            return res.status(502).json({
                id: `chatcmpl-${uuidv4().slice(0, 8)}`,
                object: 'chat.completion',
                model: body.model || 'foveated-proxy',
                choices: [{
                    message: {
                        role: 'assistant',
                        content: `⚠️ Upstream LLM unreachable: ${err.message}. Context budget auto-adjusted to ${getBudget()} chars.`
                    },
                    index: 0,
                    finish_reason: 'error'
                }],
                usage: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 },
                _healer: { budget: getBudget(), retries: retryCount, reason }
            });
        }
    }

    // ── Buffered-stream keep-alive ───────────────────────────────────────────
    // In buffered mode (FOVEA_PASSTHROUGH_MODE=false) we collect the whole
    // upstream reply before emitting, so the client would otherwise sit in
    // silence for the entire generation. Send an immediate role chunk plus
    // periodic comments so clients show life and idle timeouts don't fire.
    if (isStream && process.env.FOVEA_PASSTHROUGH_MODE === 'false' && !res.headersSent && !res._kaTimer) {
        res.setHeader('Content-Type', 'text/event-stream');
        res.setHeader('Cache-Control', 'no-cache');
        res.setHeader('Connection', 'keep-alive');
        res.setHeader('X-Accel-Buffering', 'no');
        if (typeof res.flushHeaders === 'function') res.flushHeaders();
        res.write(`data: ${JSON.stringify({ id: `chatcmpl-${uuidv4().slice(0, 8)}`, object: 'chat.completion.chunk', choices: [{ delta: { role: 'assistant' }, index: 0, finish_reason: null }] })}\n\n`);
        res._kaTimer = setInterval(() => {
            try { res.write(': keep-alive\n\n'); } catch (_) {}
        }, 1500);
        if (res._kaTimer.unref) res._kaTimer.unref();
        const stopKa = () => { if (res._kaTimer) { clearInterval(res._kaTimer); res._kaTimer = null; } };
        res.once('close', stopKa);
        res.once('finish', stopKa);
    }

    // ── Passthrough Mode (real-time streaming for IDE plugins — zero freezing) ──────────
    const PASSTHROUGH_MODE = process.env.FOVEA_PASSTHROUGH_MODE !== 'false';
    if (PASSTHROUGH_MODE && isStream) {
        res.setHeader('Content-Type', 'text/event-stream');
        res.setHeader('Cache-Control', 'no-cache');
        res.setHeader('Connection', 'keep-alive');

        let buffer = '';
        let firstChunkSent = false;
        const tagStripper = wantRaw ? null : createTagStripper();

        upstreamRes.body.on('data', (chunk) => {
            buffer += chunk.toString();
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (!line.startsWith('data:')) {
                    res.write(line + '\n');
                    continue;
                }
                const dataStr = line.slice(5).trim();
                if (dataStr === '[DONE]') {
                    if (tagStripper) {
                        const tail = tagStripper.flush();
                        const lastThoughts = tagStripper.takeThoughts();
                        if (lastThoughts) {
                            _log.reasoning_chars = (_log.reasoning_chars || 0) + lastThoughts.length;
                            res.write('data: ' + JSON.stringify({choices:[{delta:{reasoning_content:lastThoughts}}]}) + '\n\n');
                        }
                        if (tail) {
                            _log.reply_chars = (_log.reply_chars || 0) + tail.length;
                            res.write('data: ' + JSON.stringify({choices:[{delta:{content:tail}}]}) + '\n\n');
                        }
                    }
                    res.write('data: [DONE]\n\n');
                    continue;
                }
                try {
                    const parsed = JSON.parse(dataStr);
                    const delta = parsed?.choices?.[0]?.delta;

                    if (delta) {
                        if (!firstChunkSent) {
                            delta.role = 'assistant';
                            firstChunkSent = true;
                        }

                        // Reasoning stays in its own standard field (Ollama's
                        // `reasoning` is normalized to `reasoning_content`) —
                        // never inlined into content, so nothing leaks to strip.
                        if (delta.reasoning && !delta.reasoning_content) {
                            delta.reasoning_content = delta.reasoning;
                        }
                        delete delta.reasoning;

                        if (tagStripper && typeof delta.content === 'string') {
                            delta.content = tagStripper.feed(delta.content);
                            if (!delta.content) delete delta.content;
                            // Captured <thought:>/<think> text rides out as
                            // reasoning_content — thinking stays visible to
                            // clients without polluting `content`.
                            const newThoughts = tagStripper.takeThoughts();
                            if (newThoughts) {
                                _log.reasoning_chars = (_log.reasoning_chars || 0) + newThoughts.length;
                                res.write(`data: ${JSON.stringify({
                                    ...parsed,
                                    choices: [{ ...parsed.choices[0], delta: { reasoning_content: newThoughts } }]
                                })}\n\n`);
                            }
                        }
                        if (delta.content) _log.reply_chars = (_log.reply_chars || 0) + delta.content.length;
                        if (delta.reasoning_content) _log.reasoning_chars = (_log.reasoning_chars || 0) + delta.reasoning_content.length;
                        res.write(`data: ${JSON.stringify(parsed)}\n\n`);
                    } else {
                        res.write(line + '\n');
                    }
                } catch (e) {
                    res.write(line + '\n');
                }
            }
        });

        upstreamRes.body.on('end', () => {
            if (buffer) {
                res.write(buffer);
            }
            res.end();
        });
        upstreamRes.body.on('error', (e) => {
            console.error('[Passthrough] Stream error:', e);
            _log.error = `stream_error: ${e.message || e}`;
            res.end();
        });
        return;
    }

    // Collect the response watching for <recall:>, <zoom:>, <saccade:>, <accommodate:>, <temporal_zoom:> tokens
    let fullText, reasoningText, recallQuery, zoomQuery, saccadeQuery, accommodateQuery, temporalZoomQuery, rawJsonData;
    if (isStream) {
        const streamResult = await collectStream(upstreamRes);
        fullText = streamResult.fullText;
        reasoningText = streamResult.reasoningText;
        recallQuery = streamResult.recallQuery;
        zoomQuery = streamResult.zoomQuery;
        saccadeQuery = streamResult.saccadeQuery;
        accommodateQuery = streamResult.accommodateQuery;
        temporalZoomQuery = streamResult.temporalZoomQuery;
    } else {
        const jsonResult = await collectJson(upstreamRes);
        fullText = jsonResult.fullText;
        reasoningText = jsonResult.reasoningText;
        recallQuery = jsonResult.recallQuery;
        zoomQuery = jsonResult.zoomQuery;
        saccadeQuery = jsonResult.saccadeQuery;
        accommodateQuery = jsonResult.accommodateQuery;
        temporalZoomQuery = jsonResult.temporalZoomQuery;
        rawJsonData = jsonResult.data;
    }
    _log.reply_chars = (fullText || '').length;
    _log.reasoning_chars = (reasoningText || '').length;
    _log.reply_snip = bodySnippet(fullText);

    if (!fullText && !recallQuery && !zoomQuery && !saccadeQuery && !accommodateQuery && !temporalZoomQuery) {
        console.warn('[handleChatCompletion] ⚠️ collect stream/json returned empty fullText — upstream likely OOM/crashed');
        _log.error = 'empty_upstream_response';

        // Notify healer of empty response (likely context overflow)
        const { shrunk, reason } = onFailure(200, '', '');

        const healerState = getHealerState();
        const warningMsg = shrunk
            ? `⚠️ The upstream model returned an empty response (likely context overflow). Context budget auto-shrunk to ${healerState.currentBudget} chars. It will auto-restore after stable operation.`
            : `⚠️ The upstream model returned an empty response. This may be a context overflow. Current budget: ${healerState.currentBudget} chars.`;

        // Return a valid response instead of empty content that causes VS Code "no choices" error
        if (isStream) {
            if (res._kaTimer) { clearInterval(res._kaTimer); res._kaTimer = null; }
            if (!res.headersSent) {
                res.setHeader('Content-Type', 'text/event-stream');
                res.setHeader('Cache-Control', 'no-cache');
                res.setHeader('Connection', 'keep-alive');
            }
            const id = `chatcmpl-${uuidv4().slice(0, 8)}`;
            res.write(`data: ${JSON.stringify({id, object:'chat.completion.chunk', choices:[{delta:{role:'assistant',content: warningMsg}}]})}\n\n`);
            res.write(`data: ${JSON.stringify({id, object:'chat.completion.chunk', choices:[{delta:{},finish_reason:'stop'}]})}\n\n`);
            res.write('data: [DONE]\n\n');
            res.end();
        } else {
            res.json({
                id: `chatcmpl-${uuidv4().slice(0, 8)}`,
                object: 'chat.completion',
                model: body.model || 'foveated-proxy',
                choices: [{
                    message: { role: 'assistant', content: warningMsg },
                    index: 0,
                    finish_reason: 'stop'
                }],
                usage: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 },
                _healer: healerState
            });
        }
        return;
    }

    // ── Recall detected ─────────────────────────────────────────────────────
    if (recallQuery) {
        console.log(`\n🔍 [Recall] Query: "${recallQuery}" | baseMessages=${baseMessages.length} | fullText=${fullText.length} chars`);

        // Search memory store
        const results = await store.search(recallQuery, config.recall_max_results || 5);
        console.log(`   Found ${results.length} matching memories.`);

        // Build the injection block
        const memoryInjection = buildMemoryInjection(recallQuery, results);
        console.log(`   Injecting: ${memoryInjection.slice(0, 80)}…`);

        // Add to conversation: assistant partial thought + memory + continuation
        const continuationMessages = [
            ...baseMessages,
            { role: 'assistant', content: fullText },
            { role: 'system',    content: memoryInjection },
            { role: 'user',      content: config.continuation_prompt }
        ];

        // Recursively handle (the continuation will NOT have a recall)
        console.log(`[handleChatCompletion] 🔄 recursive recall | continuationMessages=${continuationMessages.length}`);
        return handleChatCompletion(req, res, continuationMessages, store, workspaceId);
    }

    // ── Zoom detected — model wants full-fidelity shadow context ──────────
    if (zoomQuery) {
        console.log(`\n🔍 [Zoom] Query: "${zoomQuery}" | session=${activeSessionId} | fullText=${fullText.length} chars`);

        let zoomInjection = null;

        // Check if it's a hash (10 hex chars) or a search phrase
        if (/^[a-f0-9]{10}$/.test(zoomQuery)) {
            // Direct hash lookup — fastest path
            const block = getShadowBlock(activeSessionId, zoomQuery);
            if (block) {
                zoomInjection = buildZoomInjection(block);
                console.log(`[Zoom] ✅ Direct hash hit: ${zoomQuery} (${block.charCount} chars restored)`);
            }
        } else {
            // Search phrase — find best matching shadow blocks
            const results = searchShadowBlocks(activeSessionId, zoomQuery, 3);
            if (results.length > 0) {
                // Inject the top match at full fidelity
                const block = getShadowBlock(activeSessionId, results[0].hash);
                if (block) {
                    zoomInjection = buildZoomInjection(block);
                    console.log(`[Zoom] ✅ Search hit: "${zoomQuery}" → ${results[0].hash} (score ${results[0].score}, ${block.charCount} chars)`);
                }
            }
        }

        if (!zoomInjection) {
            zoomInjection = {
                role: 'system',
                content: `[SHADOW ZOOM — no match for "${zoomQuery}"]. No shadow context found. Continue with current context.`
            };
            console.log(`[Zoom] ❌ No match for: "${zoomQuery}"`);
        }

        // Add to conversation: assistant partial thought + zoomed context + continuation
        const continuationMessages = [
            ...baseMessages,
            { role: 'assistant', content: fullText },
            zoomInjection,
            { role: 'user', content: '[SYSTEM: Shadow context restored at full fidelity. Please continue your response using this zoomed-in context.]' }
        ];

        console.log(`[handleChatCompletion] 🔄 recursive zoom | continuationMessages=${continuationMessages.length}`);
        return handleChatCompletion(req, res, continuationMessages, store, workspaceId);
    }

    // ── Saccade detected — model wants to move the fovea ─────────────────
    if (saccadeQuery) {
        console.log(`\n👁️ [Saccade] Target: "${saccadeQuery}" | session=${activeSessionId} | fullText=${fullText.length} chars`);

        const parsed = parseSaccadeTarget(saccadeQuery);
        const SACCADE_TOKEN_BUDGET = parseInt(process.env.XRLF_SACCADE_TOKEN_BUDGET || '2000', 10);
        const validation = validateSaccade(activeSessionId, parsed, baseMessages, SACCADE_TOKEN_BUDGET);

        if (!validation.valid) {
            console.warn(`[Saccade] ❌ Rejected: ${validation.reason}`);
            const rejectionMessages = [
                ...baseMessages,
                { role: 'assistant', content: fullText },
                { role: 'system', content: `[SACCADE REJECTED — ${validation.reason}]. The fovea stays at current position. Continue with available context or try a different target.]` },
                { role: 'user', content: '[SYSTEM: Saccade rejected. Please continue your response with the current context.]' }
            ];
            return handleChatCompletion(req, res, rejectionMessages, store, workspaceId);
        }

        // "newest" saccade = return to recent context (no blocks to inject)
        if (parsed.type === 'newest') {
            console.log(`[Saccade] ✅ Returning fovea to recent context`);
            const returnMessages = [
                ...baseMessages,
                { role: 'assistant', content: fullText },
                { role: 'system', content: `[SACCADE — fovea returned to recent context. Recent turns are now at full fidelity again.]` },
                { role: 'user', content: '[SYSTEM: Fovea returned to recent context. Please continue your response.]' }
            ];
            return handleChatCompletion(req, res, returnMessages, store, workspaceId);
        }

        // Valid saccade — restructure the fovea
        const saccadeBlocks = validation.blocks || (validation.block ? [validation.block] : []);
        if (saccadeBlocks.length === 0) {
            console.warn(`[Saccade] ❌ No blocks retrieved despite validation pass`);
            const noBlockMessages = [
                ...baseMessages,
                { role: 'assistant', content: fullText },
                { role: 'system', content: `[SACCADE — no shadow blocks found for "${saccadeQuery}"]. Continue with current context.]` },
                { role: 'user', content: '[SYSTEM: No shadow context found. Please continue.]' }
            ];
            return handleChatCompletion(req, res, noBlockMessages, store, workspaceId);
        }

        const restructuredMessages = buildRestructuredFovea(baseMessages, saccadeBlocks, validation.reason);
        console.log(`[Saccade] ✅ Fovea shifted: ${validation.reason} | restructuredMessages=${restructuredMessages.length}`);
        return handleChatCompletion(req, res, restructuredMessages, store, workspaceId);
    }

    // ── Accommodate detected — model wants to sharpen/blur a region ───────
    if (accommodateQuery) {
        console.log(`\n🔬 [Accommodate] Directive: "${accommodateQuery}" | session=${activeSessionId} | fullText=${fullText.length} chars`);

        const parsed = parseAccommodate(accommodateQuery);
        const ACCOMMODATE_TOKEN_BUDGET = parseInt(process.env.XRLF_SACCADE_TOKEN_BUDGET || '2000', 10);
        const result = executeAccommodate(activeSessionId, parsed, baseMessages, ACCOMMODATE_TOKEN_BUDGET);

        if (!result.valid || !result.injection) {
            console.warn(`[Accommodate] ❌ Rejected: ${result.reason}`);
            const rejectionMessages = [
                ...baseMessages,
                { role: 'assistant', content: fullText },
                { role: 'system', content: `[ACCOMMODATION REJECTED — ${result.reason}]. Continue with current context.]` },
                { role: 'user', content: '[SYSTEM: Accommodation rejected. Please continue your response.]' }
            ];
            return handleChatCompletion(req, res, rejectionMessages, store, workspaceId);
        }

        const continuationMessages = [
            ...baseMessages,
            { role: 'assistant', content: fullText },
            result.injection,
            { role: 'user', content: '[SYSTEM: Accommodation applied. Please continue your response with the adjusted context fidelity.]' }
        ];
        console.log(`[Accommodate] ✅ ${result.reason} | continuationMessages=${continuationMessages.length}`);
        return handleChatCompletion(req, res, continuationMessages, store, workspaceId);
    }

    // ── Temporal Zoom detected — model wants to zoom into a past time period ──
    if (temporalZoomQuery) {
        console.log(`\n📅 [TemporalZoom] Query: "${temporalZoomQuery}" | fullText=${fullText.length} chars`);

        const TEMPORAL_ZOOM_TOKEN_BUDGET = parseInt(process.env.XRLF_TEMPORAL_ZOOM_BUDGET || '1500', 10);
        const result = await handleTemporalZoom(store, temporalZoomQuery, TEMPORAL_ZOOM_TOKEN_BUDGET);

        console.log(`[TemporalZoom] ✅ ${result.stats.messagesFound} memories found | ${result.stats.tokensInjected} tokens injected | ${result.stats.parsed}`);

        const continuationMessages = [
            ...baseMessages,
            { role: 'assistant', content: fullText },
            result.injection,
            { role: 'user', content: '[SYSTEM: Temporal zoom applied. You now have a focused view of that time period. Use <recall: "phrase"> or <zoom: "hash"> to decompress specific memories within it. Please continue your response.]' }
        ];

        console.log(`[handleChatCompletion] 🔄 recursive temporal zoom | continuationMessages=${continuationMessages.length}`);
        return handleChatCompletion(req, res, continuationMessages, store, workspaceId);
    }

    // ── No recall/zoom/saccade/accommodate — store this turn and return ──

    // Store the last user message under the activeSessionId
    // ── 3-Tier Importance Scoring ────────────────────────────────────────
    // Tier 1: Heuristic scoring (instant, used for storage decision)
    // Tier 2: Async LLM refinement (fires after response, updates score)
    const lastUser = [...(baseMessages)].reverse().find(m => m.role === 'user');
    if (lastUser) {
        const userContent = typeof lastUser.content === 'string' ? lastUser.content : '';
        // Ping the soul layer (compagent :8405) — her autonomous loop's idle
        // detection and tick context need to see the user talking. The chat
        // path bypasses compagent entirely, so without this she's blind.
        // Fire-and-forget: soul layer may be down, chat must not care.
        // Skip [SYSTEM: pseudo-user continuations from recursive zoom/recall
        // turns — the real user message already pinged on the first pass.
        if (!userContent.startsWith('[SYSTEM:')) {
            try {
                fetch('http://127.0.0.1:8405/api/agent/activity', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: userContent.slice(0, 500), source: 'chat' })
                }).catch(() => {});
            } catch (_) {}
        }

        const heuristicScore = scoreImportance(userContent, 'user');
        const userMetadata = {
            importance: heuristicScore,
            topics: heuristicScore.categories
        };
        await store.store(activeSessionId, 'user', lastUser.content, new Date().toISOString(), req.userId, userMetadata);

        // Tier 2: Fire async LLM refinement (non-blocking, updates score after)
        if (process.env.XRLF_LLM_IMPORTANCE !== '0' && process.env.XRLF_LLM_IMPORTANCE !== 'false') {
            refineImportance(userContent, 'user', heuristicScore).then(refined => {
                if (refined) {
                    console.log(`[Importance] 🎯 Refined user msg: ${heuristicScore.overall}→${refined.overall} (${refined.strategy})`);
                    // Update the stored message with refined score
                    store.updateImportance(activeSessionId, userContent, refined).catch(() => {});
                }
            }).catch(() => {});
        }
    }

    // Store assistant response under the activeSessionId
    if (fullText) {
        const heuristicScore = scoreImportance(fullText, 'assistant');
        const assistantMetadata = {
            importance: heuristicScore,
            topics: heuristicScore.categories
        };
        await store.store(activeSessionId, 'assistant', fullText, new Date().toISOString(), 'assistant', assistantMetadata);

        // Tier 2: Fire async LLM refinement for assistant response too
        if (process.env.XRLF_LLM_IMPORTANCE !== '0' && process.env.XRLF_LLM_IMPORTANCE !== 'false') {
            refineImportance(fullText, 'assistant', heuristicScore).then(refined => {
                if (refined) {
                    console.log(`[Importance] 🎯 Refined assistant msg: ${heuristicScore.overall}→${refined.overall} (${refined.strategy})`);
                    store.updateImportance(activeSessionId, fullText, refined).catch(() => {});
                }
            }).catch(() => {});
        }

        // ── Memory Audit: tick the counter (triggers periodic re-scan) ──
        auditTick(store);

        // ── Memory Continuity: save ring state after each turn ──────────
        try {
            const continuityState = {
                sessionId: activeSessionId,
                workspaceId,
                model: body.model || 'foveated-proxy',
                lastUserMessage: lastUser ? (typeof lastUser.content === 'string' ? lastUser.content : extractTextFromContent(lastUser.content)) : '',
                lastAssistantMessage: fullText,
                timestamp: new Date().toISOString(),
                ringState: store.getRingState ? store.getRingState() : null,
                messageCount: store.getMessageCount ? await store.getMessageCount(activeSessionId) : 0
            };
            saveContinuity(continuityState);
        } catch (e) {
            console.warn('[Continuity] Failed to save continuity state:', e.message);
        }

        // ── Quality Guard: check response quality ──────────────────────
        const qualityResult = quickCheck(fullText);
        if (!qualityResult.passed) {
            console.warn(`[QualityGuard] ⚠️ Response flagged: score=${qualityResult.qualityScore} issues=${qualityResult.issues.join(',')}`);
        }

        // Fire-and-forget speech dispatch to TTS service (:8411) for 3D avatar audio sync
        const mouthUrl = process.env.TTS_URL || 'http://127.0.0.1:8411';
        try {
            const cleanSpeech = fullText.replace(/<think>[\s\S]*?<\/think>/gi, '').replace(/```[\s\S]*?```/g, '').replace(/[*_#`]/g, '').trim();
            if (cleanSpeech.length > 0 && cleanSpeech.length < 400) {
                fetch(`${mouthUrl}/say`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text: cleanSpeech, voice: process.env.XRLF_KOKORO_VOICE || 'af_heart' }),
                    signal: AbortSignal.timeout(4000)
                }).catch(() => {});
            }
        } catch (_) {}
    }

    // Client-facing content: strip avatar-protocol tags unless the caller opted
    // into raw (TTS/motor/XR consumers). Reasoning travels in its own field —
    // <thought:>/<think> content stripped here is captured into it.
    let clientText = fullText;
    if (!wantRaw) {
        const st = createTagStripper();
        // Strip leading whitespace/newlines left behind when a leading
        // <thought:…> tag is removed, so the reply doesn't start with blank lines.
        clientText = (st.feed(fullText) + st.flush()).replace(/^\s+/, '');
        const captured = st.takeThoughts();
        if (captured) {
            reasoningText = reasoningText ? reasoningText + '\n' + captured : captured;
        }
    }

    // Return to client in the requested format
    if (isStream) {
        if (res._kaTimer) { clearInterval(res._kaTimer); res._kaTimer = null; }
        // Re-emit as SSE
        if (!res.headersSent) {
            res.setHeader('Content-Type', 'text/event-stream');
            res.setHeader('Cache-Control', 'no-cache');
            res.setHeader('Connection', 'keep-alive');
        }

        const id = `chatcmpl-${uuidv4().slice(0, 8)}`;
        // Reasoning first, in the standard field — thinking-capable clients can render it
        if (reasoningText) {
            res.write(`data: ${JSON.stringify({
                id, object: 'chat.completion.chunk',
                choices: [{ delta: { reasoning_content: reasoningText }, index: 0, finish_reason: null }]
            })}\n\n`);
        }
        // Stream word-by-word for natural feel
        const words = clientText.split(' ');
        for (let i = 0; i < words.length; i++) {
            const token = (i === 0 ? '' : ' ') + words[i];
            const chunk = {
                id,
                object: 'chat.completion.chunk',
                choices: [{ delta: { content: token }, index: 0, finish_reason: null }]
            };
            res.write(`data: ${JSON.stringify(chunk)}\n\n`);
        }
        // Final chunk
        const finalChunk = {
            id, object: 'chat.completion.chunk',
            choices: [{ delta: {}, index: 0, finish_reason: 'stop' }]
        };
        res.write(`data: ${JSON.stringify(finalChunk)}\n\n`);
        res.write('data: [DONE]\n\n');
        res.end();
    } else {
        // Inject context warning if budget was shrunk
        const healerState = getHealerState();
        const responseContent = healerState.totalShrinks > 0 && healerState.currentBudget < healerState.maxBudget
            ? injectWarning(clientText, `Context budget currently at ${healerState.currentBudget}/${healerState.maxBudget} chars (auto-shrunk ${healerState.totalShrinks}x). Will auto-restore.`)
            : clientText;

        // Return as normal JSON response
        res.json({
            id: `chatcmpl-${uuidv4().slice(0, 8)}`,
            object: 'chat.completion',
            model: body.model || 'foveated-proxy',
            choices: [{
                message: {
                    role: 'assistant',
                    content: responseContent,
                    ...(reasoningText ? { reasoning_content: reasoningText } : {})
                },
                index: 0,
                finish_reason: 'stop'
            }],
            usage: {
                prompt_tokens: Math.ceil(JSON.stringify(body.messages).length / 4),
                completion_tokens: Math.ceil(fullText.length / 4),
                total_tokens: Math.ceil((JSON.stringify(body.messages).length + fullText.length) / 4)
            },
            _healer: healerState
        });
    }
}

// ── API endpoints (Port 8400 Active Recall & Ingestion) ───────────────────────

// ── Theme manifest endpoints (Theme Machine in Multigate) ───────────────────
// The Multigate's ThemeMachineTab fetches /api/themes and POSTs
// /api/theme/set_active. These used to live in Backend/app/IPC/http_proxy.py
// (Python) which isn't the process actually listening on :8400 — so every
// fetch 404'd and opening the Theme Machine crashed on res.json().
// Manifest: Backend/themes/manifest.json (single source of truth).
const THEME_MANIFEST_CANDIDATES = [
    path.resolve(__dirname, 'themes', 'manifest.json'),
    path.resolve(__dirname, '..', 'Backend', 'themes', 'manifest.json'),
];
function readThemeManifest() {
    for (const p of THEME_MANIFEST_CANDIDATES) {
        try {
            if (fs.existsSync(p)) return JSON.parse(fs.readFileSync(p, 'utf8'));
        } catch (e) { console.warn('[themes] manifest read failed:', p, e.message); }
    }
    return { themes: [], default: 'foveai-celestial', error: 'Manifest not found' };
}
app.get(['/api/themes', '/themes'], (req, res) => {
    try {
        res.json(readThemeManifest());
    } catch (e) {
        res.status(500).json({ themes: [], error: 'Failed to load theme manifest', detail: String(e && e.message || e) });
    }
});
app.post('/api/theme/set_active', express.json({ limit: '2mb' }), (req, res) => {
    try {
        const theme = req.body || {};
        if (!theme.theme_name) {
            return res.status(400).json({ ok: false, error: 'theme_name required' });
        }
        // Persist the full theme blob under data/active_theme.json for restarts
        const activePath = path.resolve(__dirname, 'data', 'active_theme.json');
        try {
            fs.mkdirSync(path.dirname(activePath), { recursive: true });
            if (theme && theme.theme_name) {
                fs.writeFileSync(activePath, JSON.stringify(theme, null, 2));
            } else {
                fs.writeFileSync(activePath, JSON.stringify({ active: theme }, null, 2));
            }
        } catch (e) {
            console.warn('[themes] active-theme persist failed:', e.message);
        }
        // Conductor hand-off: the theme engine (:8415) is the end authority —
        // it does Unity SoftLayer injection + ecosystem broadcast + relay.
        // fire-and-forget: local persistence already succeeded.
        fetch('http://127.0.0.1:8415/api/theme/set_active', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(theme),
            signal: AbortSignal.timeout(8000),
        }).catch(e => console.warn('[themes] :8415 conductor hand-off failed:', e.message));
        res.json({ ok: true, active: theme.theme_name });
    } catch (e) {
        res.status(500).json({ ok: false, error: String(e && e.message || e) });
    }
});

// ── Resonant-memory influx (:8400) — the gravity lane ──────────────────────
// Naturally accumulated memory material lands here — batched, patient, no
// latency SLA (that traffic rides :8403 xrl.memory / :8402 compute instead).
// The store: data/resonance.jsonl (append-only), tail endpoint for recall.
const RESONANCE_FILE = path.join(__dirname, 'data', 'resonance.jsonl');
let RESONANCE_OVERFLOW = null;   // set when default lane is blocked

// Theme soundscape proxy — rendered OGG loops live on the theme engine :8415
// Image-drop generation — multipart → theme engine :8415 (the council pipeline)
app.post('/api/theme/generate', (req, res) => {
    const http2 = require('http');
    const up = http2.request({
        host: '127.0.0.1', port: 8415, path: '/api/theme/generate',
        method: 'POST',
        headers: {
            'Content-Type': req.headers['content-type'] || 'multipart/form-data',
            'Transfer-Encoding': 'chunked',
        },
    }, (ur) => {
        res.status(ur.statusCode || 500);
        res.setHeader('Content-Type', ur.headers['content-type'] || 'text/plain');
        ur.pipe(res);   // the engine's terminal stream flows to the UI live
    });
    up.on('error', (e) => {
        console.error('[themes] generate pipe error:', e.message);
        if (!res.headersSent) res.status(502).json({ error: `theme engine unreachable: ${e.message}` });
    });
    req.pipe(up);
});

// Theme soundscape proxy — rendered OGG loops live on the theme engine :8415
// Image-drop generation — multipart → theme engine :8415 (the council pipeline)
app.post('/api/theme/generate', (req, res) => {
    const chunks = [];
    req.on('data', c => chunks.push(c));
    req.on('end', async () => {
        try {
            const upstream = await fetch('http://127.0.0.1:8415/api/theme/generate', {
                method: 'POST',
                headers: { 'Content-Type': req.headers['content-type'] || 'multipart/form-data' },
                body: Buffer.concat(chunks),
                signal: AbortSignal.timeout(600000),
            });
            res.status(upstream.status);
            res.setHeader('Content-Type', upstream.headers.get('content-type') || 'text/plain');
            // stream the engine's terminal output through to the UI
            const reader = upstream.body.getReader();
            const pump = () => reader.read().then(({ done, value }) => {
                if (done) { res.end(); return; }
                res.write(Buffer.from(value));
                return pump();
            });
            await pump();
        } catch (e) {
            res.status(502).json({ error: `theme engine unreachable: ${e.message}` });
        }
    });
});

// Theme soundscape proxy — rendered OGG loops live on the theme engine :8415
app.get('/api/theme/sound/:fname', (req, res) => {
    (async () => {
        try {
            const upstream = await fetch(`http://127.0.0.1:8415/theme/audio/${encodeURIComponent(req.params.fname)}`);
            if (!upstream.ok) { res.status(upstream.status).end(); return; }
            res.type('audio/ogg').set('Cache-Control', 'no-cache');
            const buf = Buffer.from(await upstream.arrayBuffer());
            res.send(buf);
        } catch (e) {
            res.status(502).end();
        }
    })();
});

// ── FUI theme render endpoint (the authoritative -fui engine) ───────────────
// POST /api/theme/fui {variant: signum|whisper|screamer|daylight, image_url?}
// Shells to runtime/fui_colors.py --render: writes the variant stylesheet +
// palette artifacts into every frontend public dir, refreshes the theme
// manifest (fui family), and live-applies via /api/theme/set_active.
const FUI_VARIANTS = ['signum', 'whisper', 'screamer', 'daylight'];
app.post('/api/theme/fui', express.json({ limit: '2mb' }), (req, res) => {
    const variant = FUI_VARIANTS.includes(req.body?.variant) ? req.body.variant : 'signum';
    const bgImage = typeof req.body?.image_url === 'string' && req.body.image_url.startsWith('http')
        ? req.body.image_url : null;
    const args = [path.resolve(__dirname, '..', 'runtime', 'fui_colors.py'), '--render', variant];
    if (bgImage) args.push('--bg-image', bgImage);
    const py = fs.existsSync(path.resolve(__dirname, '..', '.venv', 'bin', 'python'))
        ? path.resolve(__dirname, '..', '.venv', 'bin', 'python') : 'python3';
    execFile(py, args, { timeout: 30000, cwd: path.resolve(__dirname, '..') },
        (err, stdout) => {
            if (err) {
                console.error('[fui] render failed:', err.message);
                return res.status(500).json({ ok: false, error: String(err.message).slice(0, 200) });
            }
            const written = String(stdout).trim().split('\n')
                .filter(l => l.includes('→')).map(l => l.split('→')[1].trim());
            res.json({ ok: true, variant, applied: true, written });
        });
});

// Telepathy overflow: when the WS lane backs up, HTTP POST here instead
app.post(['/api/resonance/ingest', '/api/resonance/telepathy'], (req, res) => {
    try {
        const body = Array.isArray(req.body) ? req.body : (req.body?.units || (req.body ? [req.body] : []));
        if (!body.length) return res.status(400).json({ error: 'empty influx' });
        const lines = body.map(u => JSON.stringify({ ...u, ingested: new Date().toISOString(), lane: req.path.endsWith('telepathy') ? 'telepathy' : 'resonance' })).join('\n') + '\n';
        try { fs.mkdirSync(path.dirname(RESONANCE_FILE), { recursive: true }); } catch (_) {}
        fs.appendFileSync(RESONANCE_FILE, lines);
        res.json({ ok: true, ingested: body.length, lane: req.path.endsWith('telepathy') ? 'telepathy' : 'resonance' });
    } catch (e) {
        res.status(500).json({ error: String(e && e.message || e) });
    }
});

// Tail recall for models hooking in over HTTP (contrast with ws xrl.memory recall)
app.get('/api/resonance/tail', (req, res) => {
    const n = Math.min(500, Math.max(1, parseInt(req.query.n || '50', 10)));
    let lines = [];
    try {
        lines = fs.readFileSync(RESONANCE_FILE, 'utf8').trim().split('\n').filter(Boolean).slice(-n);
    } catch (_) {}
    res.json({ units: lines.map(l => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean) });
});

app.get('/api/resonance/depth', (_req, res) => {
    let count = 0;
    try { count = fs.readFileSync(RESONANCE_FILE, 'utf8').split('\n').filter(Boolean).length; } catch (_) {}
    res.json({ depth: count, overflowRegistered: !!RESONANCE_OVERFLOW });
});

// ── Live Nervous System Synapses & Rings Telemetry ───────────────────────
app.get('/api/synapses', async (_req, res) => {
    const net = require('net');
    const probe = (port) => new Promise(resolve => {
        const s = new net.Socket();
        s.setTimeout(250);
        s.once('connect', () => { s.destroy(); resolve(true); });
        s.once('timeout', () => { s.destroy(); resolve(false); });
        s.once('error', () => { s.destroy(); resolve(false); });
        s.connect(port, '127.0.0.1');
    });

    const synapses = [
        { id: 'gateway', name: 'Gateway Proxy', port: 8400, role: 'Active Recall & Compressor', layer: 'core' },
        { id: 'hearing', name: 'STT Whisper', port: 8401, role: 'Senses · Hearing', layer: 'senses' },
        { id: 'vision', name: 'XRLF Vision', port: 8402, role: 'Senses · Vision Runtime', layer: 'senses' },
        { id: 'memory_bus', name: 'Memory Bus', port: 8403, role: 'Unified WebSocket IPC', layer: 'senses' },
        { id: 'soul', name: 'Soul DNA', port: 8405, role: 'Mind · Persona Authority', layer: 'mind' },
        { id: 'tier_a', name: 'Mind Tier A', port: 8407, role: 'Gemma-4-E2B Background Model', layer: 'mind' },
        { id: 'tier_b', name: 'Mind Tier B', port: 8408, role: 'Qwen3.5-9B Flagship MoQ', layer: 'mind' },
        { id: 'body', name: 'Act Body', port: 8410, role: 'Gamepad & Input Relay', layer: 'act' },
        { id: 'voice', name: 'Act Voice', port: 8411, role: 'Kokoro TTS Speech', layer: 'act' },
        { id: 'create', name: 'Act Create', port: 8412, role: 'Dreamscape Creative Engine', layer: 'act' },
        { id: 'relay', name: 'Chat Relay', port: 8413, role: 'Multi-Way Chat Relay', layer: 'serve' },
        { id: 'dashboard', name: 'Dashboard', port: 8414, role: 'Foveated Memory WebUI', layer: 'serve' },
        { id: 'theme', name: 'Theme Engine', port: 8415, role: 'Dynamic UI Theme API', layer: 'serve' },
        { id: 'multigate', name: 'Multigate UI', port: 5177, role: 'Frontend Spatial WebUI', layer: 'frontend' }
    ];

    const results = await Promise.all(synapses.map(async s => ({
        ...s,
        alive: await probe(s.port)
    })));

    const rings = [
        { ring: 0, name: 'Fovea', budget: 600, compression: '0–35%', scope: 'Last 4–6 messages (High Res)' },
        { ring: 1, name: 'Parafovea', budget: 200, compression: '~65%', scope: 'Last 24 hours (Themes)' },
        { ring: 2, name: 'Near Periphery', budget: 300, compression: '~85%', scope: '1–7 days (Headlines)' },
        { ring: 3, name: 'Mid Periphery', budget: 300, compression: '~93%', scope: '7–30 days (Topics & Hashes)' },
        { ring: 4, name: 'Far Periphery', budget: 300, compression: '~97%', scope: '30–365 days (Summaries)' },
        { ring: 5, name: 'Outer Horizon', budget: 200, compression: '~99%', scope: '1yr+ Deep Past (Atomic Hashes)' }
    ];

    res.json({
        ok: true,
        timestamp: new Date().toISOString(),
        synapses: results,
        rings: rings,
        healer: getHealerState()
    });
});

// ── Context Healer Health & Control API ────────────────────────────────────
app.get('/_health/context', (req, res) => {
    res.json(getHealerState());
});
// Alias for settings diagnostics panel
app.get('/api/healer-state', (req, res) => {
    res.json(getHealerState());
});

app.post('/_health/context/reset', (req, res) => {
    const result = resetBudget();
    res.json({ status: 'reset', ...result, state: getHealerState() });
});

app.post('/_health/context/budget', (req, res) => {
    const { budget } = req.body || {};
    if (!budget || typeof budget !== 'number') {
        return res.status(400).json({ error: 'budget (number) required' });
    }
    const result = setBudget(budget);
    res.json({ status: 'set', ...result, state: getHealerState() });
});

// ── Settings Redirect on Port 8400 ──────────────────────────────────────────
app.get(['/settings', '/settings.html'], (_req, res) => {
    res.redirect(`http://${PROXY_HOST || '127.0.0.1'}:${DASHBOARD_PORT}/settings.html`);
});

// ── Soul DNA & Persona Bridge ───────────────────────────────────────────
app.get('/api/soul/soul_dna', async (_req, res) => {
    try {
        const resp = await fetch('http://127.0.0.1:8405/api/soul/soul_dna', { timeout: 1500 });
        if (resp.ok) {
            const data = await resp.json();
            return res.json(data);
        }
    } catch (_) {}
    try {
        const soulPath = path.resolve(__dirname, '..', 'Backend', 'Cognition', 'jen_soul.json');
        if (fs.existsSync(soulPath)) {
            const raw = fs.readFileSync(soulPath, 'utf8');
            return res.json({ dna: JSON.parse(raw) });
        }
    } catch (err) {
        return res.status(500).json({ error: 'Failed to read soul DNA: ' + err.message });
    }
    res.status(404).json({ error: 'Soul DNA not found' });
});

app.post(['/api/soul/update_soul', '/update_soul'], async (req, res) => {
    let forwarded = false;
    let forwardData = null;
    try {
        const resp = await fetch('http://127.0.0.1:8405/api/soul/update_soul', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(req.body),
            timeout: 2000
        });
        if (resp.ok) {
            forwardData = await resp.json();
            forwarded = true;
        }
    } catch (_) {}

    try {
        const soulPath = path.resolve(__dirname, '..', 'Backend', 'Cognition', 'jen_soul.json');
        let current = {};
        if (fs.existsSync(soulPath)) {
            current = JSON.parse(fs.readFileSync(soulPath, 'utf8'));
        }
        Object.assign(current, req.body);
        fs.writeFileSync(soulPath, JSON.stringify(current, null, 2), 'utf8');

        // Also sync lever to jen_mind.json if present
        if (req.body.agent_person_balance !== undefined) {
            const mindPath = path.resolve(__dirname, '..', 'Backend', 'Cognition', 'jen_mind.json');
            if (fs.existsSync(mindPath)) {
                try {
                    const mind = JSON.parse(fs.readFileSync(mindPath, 'utf8'));
                    mind.lever = parseFloat(req.body.agent_person_balance);
                    mind.updated = Date.now() / 1000;
                    fs.writeFileSync(mindPath, JSON.stringify(mind, null, 2), 'utf8');
                } catch (_) {}
            }
        }

        return res.json(forwardData || { status: 'success', dna: current });
    } catch (err) {
        if (forwarded) return res.json(forwardData);
        return res.status(500).json({ error: 'Failed to write soul DNA: ' + err.message });
    }
});

// ── Unified Voice API (STT + TTS) ──────────────────────────────────────────
// The proxy is the single endpoint for all modalities.
// Strategy: try the XRLF model first (when it supports audio natively),
// fall back to dedicated voice services on the 840x port series.
//
// XRLF_URL = native model API (STT/TTS/vision on :8402)
// TTS_URL  = TTS service (Kokoro on :8411)
// STT_URL  = STT service (Whisper on :8401 — the HEARING lane)
const TTS_URL = process.env.TTS_URL || 'http://127.0.0.1:8411';
const STT_URL = process.env.STT_URL || 'http://127.0.0.1:8401';
const XRLF_URL = process.env.XRLF_URL || 'http://127.0.0.1:8402';

// ── STT: POST /api/soul/stt ─────────────────────────────────────────────────
// Accepts audio_base64, returns transcribed text.
// Tries XRLF model native STT first, falls back to Soul/Whisper.
app.post('/api/soul/stt', requireFeature('voice'), async (req, res) => {
    const { audio_base64, format, filename } = req.body || {};
    if (!audio_base64) {
        return res.status(400).json({ error: 'audio_base64 required' });
    }

    // TODO: When XRLF model supports native STT, try :8402 first:
    // POST /v1/audio/transcriptions with the audio data.
    // For now, go straight to fallback.

    // Try native model STT first (POST /v1/audio/transcriptions on :8402)
    try {
        const r = await fetch(`${XRLF_URL}/v1/audio/transcriptions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ audio_base64, format: format || 'audio/webm', filename: filename || 'recording.webm' }),
            signal: AbortSignal.timeout(15000)
        });
        if (r.ok) {
            const data = await r.json();
            if (typeof data.text === 'string') {
                console.log(`[Voice/STT] ✅ Native model transcribed: "${data.text.slice(0, 80)}"`);
                return res.json(data);
            }
        }
        console.warn(`[Voice/STT] Native model STT returned ${r.status}`);
    } catch (e) {
        console.warn(`[Voice/STT] Native STT unavailable: ${e.message}`);
    }

    // Fallback: STT service (Whisper) on :8409
    try {
        const r = await fetch(`${STT_URL}/api/soul/stt`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ audio_base64, format: format || 'audio/webm', filename: filename || 'recording.webm' }),
            signal: AbortSignal.timeout(15000)
        });
        if (r.ok) {
            const data = await r.json();
            console.log(`[Voice/STT] ✅ Whisper transcribed: "${(data.text || '').slice(0, 80)}"`);
            return res.json(data);
        }
        console.warn(`[Voice/STT] STT service returned ${r.status}`);
    } catch (e) {
        console.warn(`[Voice/STT] Whisper STT (:8409) unavailable: ${e.message}`);
    }

    // Last resort: return empty so the frontend doesn't hang
    console.error('[Voice/STT] ❌ All STT backends failed');
    res.status(503).json({ error: 'STT unavailable — no Whisper service running', text: '' });
});

// ── TTS: POST /api/tts ──────────────────────────────────────────────────────
// Accepts text, returns audio or dispatches to TTS engine.
// Tries XRLF model native TTS first, falls back to the TTS service (Kokoro on :8411).
app.post('/api/tts', requireFeature('voice'), async (req, res) => {
    const { text, voice } = req.body || {};
    if (!text) {
        return res.status(400).json({ error: 'text required' });
    }
    const cleanText = text.replace(/<think>[\s\S]*?<\/think>/gi, '').replace(/```[\s\S]*?```/g, '').replace(/[*_#`]/g, '').trim();
    if (!cleanText || cleanText.length === 0) {
        return res.json({ status: 'empty', audio: null });
    }

    // TODO: When XRLF model supports native TTS, try :8402 first:
    // POST /v1/audio/speech with the text.
    // For now, go straight to fallback.

    // Try native model TTS first (POST /v1/audio/speech on :8402)
    try {
        const r = await fetch(`${XRLF_URL}/v1/audio/speech`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: cleanText, voice: voice || 'default' }),
            signal: AbortSignal.timeout(10000)
        });
        if (r.ok) {
            const contentType = r.headers.get('content-type') || '';
            if (contentType.includes('audio')) {
                const audioBuf = Buffer.from(await r.arrayBuffer());
                res.setHeader('Content-Type', contentType);
                console.log(`[Voice/TTS] ✅ Native model spoke: "${cleanText.slice(0, 60)}"`);
                return res.send(audioBuf);
            }
        }
        console.warn(`[Voice/TTS] Native model TTS returned ${r.status}`);
    } catch (e) {
        console.warn(`[Voice/TTS] Native TTS unavailable: ${e.message}`);
    }

    // Fallback 1: TTS service (Kokoro) on :8411
    try {
        const r = await fetch(`${TTS_URL}/tts`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: cleanText, voice: voice || process.env.XRLF_KOKORO_VOICE || 'af_heart' }),
            signal: AbortSignal.timeout(8000)
        });
        if (r.ok) {
            console.log(`[Voice/TTS] ✅ Kokoro spoke: "${cleanText.slice(0, 60)}"`);
            // Pass through audio response if Kokoro returns audio, or just acknowledge
            const contentType = r.headers.get('content-type') || '';
            if (contentType.includes('audio')) {
                const audioBuf = Buffer.from(await r.arrayBuffer());
                res.setHeader('Content-Type', contentType);
                return res.send(audioBuf);
            }
            return res.json({ status: 'ok', engine: 'kokoro', text: cleanText });
        }
        console.warn(`[Voice/TTS] TTS service returned ${r.status}`);
    } catch (e) {
        console.warn(`[Voice/TTS] TTS service (:8411) unavailable: ${e.message}`);
    }

    // Fallback 2: TTS service /say alias on :8411
    try {
        const r = await fetch(`${TTS_URL}/say`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: cleanText }),
            signal: AbortSignal.timeout(5000)
        });
        if (r.ok) {
            console.log(`[Voice/TTS] ✅ TTS /say spoke: "${cleanText.slice(0, 60)}"`);
            const contentType = r.headers.get('content-type') || '';
            if (contentType.includes('audio')) {
                const audioBuf = Buffer.from(await r.arrayBuffer());
                res.setHeader('Content-Type', contentType);
                return res.send(audioBuf);
            }
            return res.json({ status: 'ok', engine: 'kokoro', text: cleanText });
        }
    } catch (e) {
        console.warn(`[Voice/TTS] TTS /say unavailable: ${e.message}`);
    }

    // Last resort: no audio, but don't crash the frontend
    console.error('[Voice/TTS] ❌ All TTS backends failed');
    res.status(503).json({ error: 'TTS unavailable — no TTS service running', text: cleanText });
});

// ── TTS voices: GET /api/tts/voices ─────────────────────────────────────────
// Passthrough to the TTS service's /voices endpoint (Kokoro on :8411).
app.get('/api/tts/voices', async (req, res) => {
    try {
        const r = await fetch(`${TTS_URL}/voices`, { signal: AbortSignal.timeout(4000) });
        if (r.ok) {
            const data = await r.json();
            return res.json(data);
        }
        console.warn(`[Voice/TTS] /voices returned ${r.status}`);
    } catch (e) {
        console.warn(`[Voice/TTS] /voices unavailable: ${e.message}`);
    }
    res.status(503).json({ error: 'TTS voices unavailable', voices: [] });
});

// ── Voice pipeline status ───────────────────────────────────────────────────
app.get('/api/voice/status', async (req, res) => {
    const status = { stt: 'offline', tts: 'offline', model_native: false };
    // Check XRLF runtime native capabilities first
    try {
        const r = await fetch(`${XRLF_URL}/v1/capabilities`, { signal: AbortSignal.timeout(2000) });
        if (r.ok) {
            const caps = await r.json();
            if (caps.tts) { status.tts = 'native'; status.model_native = true; }
            if (caps.audio_stt) { status.stt = 'native'; status.model_native = true; }
        }
    } catch {}
    // Check Whisper STT service (fallback, :8409) — WebSocket-only, so probe TCP
    if (status.stt === 'offline') {
        try {
            const sttPort = parseInt(new URL(STT_URL).port || '8401', 10);
            await new Promise((resolve, reject) => {
                const sock = require('net').connect({ host: '127.0.0.1', port: sttPort, timeout: 1500 });
                sock.on('connect', () => { sock.end(); resolve(); });
                sock.on('error', reject); sock.on('timeout', () => { sock.destroy(); reject(new Error('timeout')); });
            });
            status.stt = 'whisper';
        } catch {}
    }
    // Check Kokoro TTS service (fallback, :8411)
    if (status.tts === 'offline') {
        try {
            const r = await fetch(`${TTS_URL}/health`, { signal: AbortSignal.timeout(2000) });
            if (r.ok) status.tts = 'kokoro';
        } catch {}
    }
    res.json(status);
});

// ── PipeWire Audio FX (EQ + mic FX) ─────────────────────────────────────────
// The Multigate "Audio FX" surface. Everything here drives the audio-variator-eq
// CLIs, which modulate PipeWire DSP nodes live — so the contract is strict:
//   • preset names are USER INPUT → allowlist regex AND existence check before
//     anything is executed (a 400 never reaches the CLI);
//   • execFile with an ARGS ARRAY + explicit cwd, never a shell string, so a
//     name can never become syntax;
//   • every exec is bounded by a timeout (execFile's timeout is MILLISECONDS)
//     and a failure is a 500 with a useful message — a request never hangs;
//   • the GET is strictly read-only (`--json` / `--presets-json` only): reading
//     state must never move a dial.
const os = require('os');
const AUDIO_FX_DIR = path.resolve(__dirname, '..', 'Tools', 'audio-variator-eq');
const AUDIO_FX_SET_EQ = path.join(AUDIO_FX_DIR, 'set-eq');
const AUDIO_FX_SET_MIC_FX = path.join(AUDIO_FX_DIR, 'set-mic-fx');
const AUDIO_FX_PRESETS_FILE = path.join(os.homedir(), '.config', 'pipewire', 'eq-presets.json');
const AUDIO_FX_EXEC_MS = 8000;        // execFile timeout — MILLISECONDS
const AUDIO_FX_MAX_BUFFER = 8 * 1024 * 1024;   // --presets-json is the fat one
// Letters, digits, space, underscore, dash. Nothing else: no quotes, no
// metacharacters, no path separators, no NUL — belt on top of the args array.
const AUDIO_FX_NAME_RE = /^[A-Za-z0-9 _-]{1,64}$/;

// Read-only exec wrapper. Never throws an exec error into the request.
function audioFxRun(tool, args) {
    return new Promise((resolve, reject) => {
        execFile(tool, args, {
            cwd: AUDIO_FX_DIR,
            timeout: AUDIO_FX_EXEC_MS,
            maxBuffer: AUDIO_FX_MAX_BUFFER,
            windowsHide: true,
        }, (err, stdout) => {
            if (err) return reject(new Error(String(err.message || err).slice(0, 200)));
            resolve(String(stdout));
        });
    });
}

/**
 * Every preset name the CLI would accept: the factory scenes it ships, plus
 * the user scenes in ~/.config/pipewire/eq-presets.json. The allowlist regex
 * alone is not enough — a name can be well-formed and still resolve to
 * nothing, and that must be a 400 rather than a shell round-trip.
 */
async function audioFxKnownPresets() {
    const known = new Map();
    let cli = {};
    try {
        cli = JSON.parse(await audioFxRun(AUDIO_FX_SET_EQ, ['--presets-json']));
    } catch (e) {
        console.warn('[audio-fx] preset listing unavailable:', e.message);
    }
    for (const [name, scene] of Object.entries(cli.scenes || {})) {
        known.set(name, (scene && scene.cat) || null);
    }
    let file = null;
    try { file = JSON.parse(fs.readFileSync(AUDIO_FX_PRESETS_FILE, 'utf8')); } catch { file = null; }
    for (const [name, scene] of Object.entries((file && file.scenes) || {})) {
        known.set(name, (scene && scene.cat) || null);
    }
    return known;
}

// GET /api/audio-fx/state — read-only snapshot: EQ + mic FX + preset list.
app.get('/api/audio-fx/state', async (req, res) => {
    try {
        const [eqRaw, micRaw, presetsRaw] = await Promise.all([
            audioFxRun(AUDIO_FX_SET_EQ, ['--json']),
            audioFxRun(AUDIO_FX_SET_MIC_FX, ['--json']),
            audioFxRun(AUDIO_FX_SET_EQ, ['--presets-json']),
        ]);
        const known = new Map();
        for (const [name, scene] of Object.entries(JSON.parse(presetsRaw).scenes || {})) {
            known.set(name, (scene && scene.cat) || null);
        }
        let file = null;
        try { file = JSON.parse(fs.readFileSync(AUDIO_FX_PRESETS_FILE, 'utf8')); } catch { file = null; }
        for (const [name, scene] of Object.entries((file && file.scenes) || {})) {
            known.set(name, (scene && scene.cat) || null);
        }
        res.json({
            ok: true,
            output: JSON.parse(eqRaw),            // set-eq --json
            input: JSON.parse(micRaw),            // set-mic-fx --json
            presets: [...known.entries()]
                .map(([name, cat]) => ({ name, cat }))
                .sort((a, b) => a.name.localeCompare(b.name)),
        });
    } catch (e) {
        console.warn('[audio-fx] state read failed:', e.message);
        res.status(500).json({ ok: false, error: `audio FX unavailable: ${e.message}` });
    }
});

// POST /api/audio-fx/preset {preset} — apply a scene preset by name.
app.post('/api/audio-fx/preset', async (req, res) => {
    const auth = resolveRequestAuth(req);
    if (auth.rejected) return res.status(401).json({ error: 'invalid or expired session' });
    const name = String((req.body && (req.body.preset || req.body.name)) || '');
    if (!AUDIO_FX_NAME_RE.test(name)) {
        return res.status(400).json({ error: 'preset name must be 1-64 characters of [A-Za-z0-9 _-]' });
    }
    try {
        const known = await audioFxKnownPresets();
        if (!known.has(name)) {
            return res.status(400).json({ error: `unknown preset: ${name}` });
        }
        const log = await audioFxRun(AUDIO_FX_SET_EQ, ['--preset', name]);
        const output = JSON.parse(await audioFxRun(AUDIO_FX_SET_EQ, ['--json']));
        res.json({ ok: true, applied: name, output, log: log.trim().slice(-400) });
    } catch (e) {
        console.warn(`[audio-fx] preset "${name}" failed:`, e.message);
        res.status(500).json({ error: `could not apply preset "${name}": ${e.message}` });
    }
});

// POST /api/audio-fx/bypass {bypass} — master FX bypass on/off (boolean).
app.post('/api/audio-fx/bypass', async (req, res) => {
    const auth = resolveRequestAuth(req);
    if (auth.rejected) return res.status(401).json({ error: 'invalid or expired session' });
    const want = !!(req.body && req.body.bypass);
    try {
        await audioFxRun(AUDIO_FX_SET_EQ, ['--bypass', want ? 'on' : 'off']);
        const output = JSON.parse(await audioFxRun(AUDIO_FX_SET_EQ, ['--json']));
        res.json({ ok: true, bypass: !!output.bypass, output });
    } catch (e) {
        console.warn('[audio-fx] bypass failed:', e.message);
        res.status(500).json({ error: `could not set bypass: ${e.message}` });
    }
});

// ── Memory Continuity API ──────────────────────────────────────────────────
app.get('/v1/memory/continuity', (req, res) => {
    try {
        const snapshot = loadContinuity();
        res.json({ snapshot, resumeContext: snapshot ? buildResumeContext(snapshot) : null });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

app.post('/v1/memory/continuity', (req, res) => {
    try {
        const state = req.body;
        saveContinuity(state);
        res.json({ status: 'saved', timestamp: new Date().toISOString() });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

app.get('/v1/memory/continuity/history', (req, res) => {
    try {
        const limit = parseInt(req.query.limit) || 50;
        const history = getContinuityHistory(limit);
        res.json({ history, count: history.length });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

app.delete('/v1/memory/continuity', (req, res) => {
    try {
        clearContinuity();
        res.json({ status: 'cleared' });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

// ── Semantic Memory Search API ──────────────────────────────────────────────
function cosineSimilarity(a, b) {
    if (!a || !b || a.length !== b.length) return 0;
    let dot = 0, normA = 0, normB = 0;
    for (let i = 0; i < a.length; i++) {
        dot += a[i] * b[i];
        normA += a[i] * a[i];
        normB += b[i] * b[i];
    }
    const denom = Math.sqrt(normA) * Math.sqrt(normB);
    return denom === 0 ? 0 : dot / denom;
}

app.post('/v1/memory/search', async (req, res) => {
    try {
        const _authz = resolveRequestAuth(req);
        const workspaceId = _authz.workspaceId || config.workspace_id || 'default';
        const { query, limit = 10, sessionId } = req.body || {};
        if (!query) return res.status(400).json({ error: 'query required' });

        const store = getStore(workspaceId);
        const results = await store.search(query, limit, sessionId);
        const mode = (results.length > 0 && results[0].method === 'vector') ? 'minilm-vector' : 'tfidf';

        res.json({ results, count: results.length, mode, workspace: workspaceId });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

// Store a single message turn (used by the foveated-memory MCP server so
// external IDEs write through the same getStore(workspace) path as chat).
app.post('/v1/memory/store', async (req, res) => {
    try {
        const _authz = resolveRequestAuth(req);
        if (_authz.rejected) return res.status(401).json({ error: 'invalid or expired session' });
        const workspaceId = _authz.workspaceId;
        const { role, content, session } = req.body || {};
        if (!role || !content) return res.status(400).json({ error: 'role and content required' });
        const s = getStore(workspaceId);
        const sessionId = session || new Date().toISOString().slice(0, 10);
        await s.store(sessionId, role, content, new Date().toISOString());
        const total = await s.count();
        res.json({ saved: true, workspace: workspaceId, session: sessionId, total_messages: total });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

// ── XRLF Format Inspector ──────────────────────────────────────────────────
app.get('/api/xrlf/inspect', (req, res) => {
    res.json({
        capabilities: {
            compression: true,
            rings: ['Fovea (0)', 'Parafovea (1)', 'Near Periphery (2)', 'Mid Periphery (3)', 'Far Periphery (4)', 'Outer Periphery (5)'],
            checkpointing: true,
            recall: true,
            continuity: true,
            qualityGuard: true,
            multimodal: true,
            semanticSearch: true
        },
        version: '3.0.0',
        service: 'FoveatedMemory XRLF Proxy'
    });
});

app.post('/api/xrlf/inspect', async (req, res) => {
    try {
        const { sessionId } = req.body;
        const store = getStore(config.workspace_id);
        const ringState = store.getRingState ? store.getRingState() : null;
        const messageCount = sessionId ? (store.getMessageCount ? await store.getMessageCount(sessionId) : 0) : 0;
        const continuity = loadContinuity();

        res.json({
            ringState,
            messageCount,
            sessionId: sessionId || 'default',
            continuity: continuity ? {
                lastSessionId: continuity.sessionId,
                lastTimestamp: continuity.timestamp,
                messageCount: continuity.messageCount
            } : null,
            timestamp: new Date().toISOString()
        });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

// ── Quality Check API ──────────────────────────────────────────────────────
app.post('/api/quality/check', (req, res) => {
    try {
        const { text, options } = req.body;
        if (!text) return res.status(400).json({ error: 'text required' });
        const result = checkQuality(text, options || {});
        res.json(result);
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

// XRLF-Skeletonizer tier-info
app.get('/api/tier-info', (req, res) => {
    const model = req.query.model || 'default';
    const mode  = req.query.mode  || COGNITIVE_MODE;
    const ctx   = detectContextWindow(model, mode);
    res.json({
        model,
        mode,
        context_window: ctx,
        recommended_tier: selectTier(ctx),
        service: 'XRLF/FoveatedMemory Unified Proxy v3',
        proxy_port: config.proxy_port,
        upstream: config.upstream_url
    });
});

// Skeletonize a file (XRLF-Skeletonizer native)
app.post('/api/skeletonize', (req, res) => {
    const { filepath, level = 3 } = req.body || {};
    if (!filepath) return res.status(400).json({ error: 'filepath required' });
    const candidates = [
        filepath,
        path.resolve(filepath),
        path.resolve(__dirname, '..', '..', filepath),
        path.resolve(__dirname, '..', '..', '..', filepath)
    ];
    const resolved = candidates.find(p => fs.existsSync(p));
    if (!resolved) return res.status(404).json({ error: `File '${filepath}' not found` });
    const skeleton = skeletonizeFile(resolved, level);
    if (!skeleton) return res.status(500).json({ error: 'Skeletonization failed' });
    res.json({ filepath, level, skeleton, source_hint: filepath });
});

// Expand file:line
app.get('/api/expand/:filepath(*)', (req, res) => {
    const filepath = req.params.filepath;
    const line = parseInt(req.query.line || '1', 10);
    const contextLines = parseInt(req.query.context || '3', 10);
    const candidates = [
        filepath,
        path.resolve(filepath),
        path.resolve(__dirname, '..', '..', filepath),
        path.resolve(__dirname, '..', '..', '..', filepath)
    ];
    const resolved = candidates.find(p => fs.existsSync(p));
    if (!resolved) return res.status(404).json({ error: 'File not found' });
    const expanded = expandFileLine(resolved, line, contextLines);
    if (!expanded) return res.status(500).json({ error: 'Expansion failed' });
    res.json({ filepath, line, context: contextLines, expanded });
});

// Expand hash or file:line via POST
app.post('/api/expand', (req, res) => {
    const { hash_id, filepath, line, context_lines = 3 } = req.body || {};
    if (hash_id) {
        for (const [uri, entry] of xrlCache.entries()) {
            if (uri.endsWith(`:${hash_id}`)) {
                return res.json({ hash_id, uri, expanded: entry.content });
            }
        }
        return res.status(404).json({ error: 'Hash not found in runtime cache' });
    }
    if (filepath && line != null) {
        const expanded = expandFileLine(filepath, line, context_lines);
        if (!expanded) return res.status(404).json({ error: 'File/line not found' });
        return res.json({ filepath, line, context: context_lines, expanded });
    }
    return res.status(400).json({ error: 'Provide hash_id or filepath+line' });
});

// XRL protocol stubs
app.post('/api/xrl/expand', (req, res) => {
    const { uris = [] } = req.body || {};
    const out = {};
    for (const uri of uris) {
        const parsed = parseXrl(uri);
        if (!parsed) { out[uri] = { error: 'Invalid XRL' }; continue; }
        const expanded = expandFileLine(parsed.filepath, parsed.line, 3);
        out[uri] = expanded ? { ...parsed, expanded } : { error: 'File not found' };
    }
    res.json({ expanded: out });
});

app.post('/api/xrl/resolve', (req, res) => {
    const { uri } = req.body || {};
    const parsed = parseXrl(uri);
    res.json({ uri, parsed, cached: xrlCache.has(uri) });
});

app.get('/api/xrl/status', (req, res) => {
    res.json({ namespace: XRL_NAMESPACE, cache_size: xrlCache.size, version: '3.0' });
});

app.post('/api/xrl/prune', (req, res) => {
    const maxAgeDays = parseInt(req.body?.max_age_days || '7', 10);
    const cutoff = Date.now() - maxAgeDays * 24 * 60 * 60 * 1000;
    let pruned = 0;
    for (const [uri, entry] of xrlCache.entries()) {
        if (new Date(entry.created).getTime() < cutoff) {
            xrlCache.delete(uri);
            pruned++;
        }
    }
    res.json({ pruned, remaining: xrlCache.size });
});

// Semantic summary (best-effort local middleman, or extractive fallback)
app.post('/api/semantic-summary', async (req, res) => {
    const { filepath, content } = req.body || {};
    if (!filepath && !content) return res.status(400).json({ error: 'filepath or content required' });
    let text = content;
    if (!text && filepath) {
        const candidates = [
            filepath,
            path.resolve(filepath),
            path.resolve(__dirname, '..', '..', filepath),
            path.resolve(__dirname, '..', '..', '..', filepath)
        ];
        const resolved = candidates.find(p => fs.existsSync(p));
        if (!resolved) return res.status(404).json({ error: 'File not found' });
        text = fs.readFileSync(resolved, 'utf8');
    }
    try {
        // Use config-driven summarizer settings from xrlf_config.yaml (or env overrides).
        // Falls back gracefully if the summarizer endpoint is unavailable.
        if (!SUMMARIZER_ENABLED) throw new Error('summarizer disabled in config');
        const summaryEndpoint = SUMMARIZER_ENDPOINT.replace(/\/v1\/?$/, '') + '/v1/chat/completions';
        const r = await withLocalUpstream(() => fetch(summaryEndpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model: SUMMARIZER_MODEL,
                messages: [
                    { role: 'system', content: 'Summarize the following file in one concise sentence.' },
                    { role: 'user', content: text.slice(0, 4000) }
                ],
                max_tokens: Math.min(SUMMARIZER_MAX_TOKENS, 150), temperature: Math.min(SUMMARIZER_TEMP, 0.1), stream: false
            })
        }));
        if (r.ok) {
            const data = await r.json();
            return res.json({ filepath, summary: data.choices?.[0]?.message?.content || 'No summary' });
        }
    } catch (e) { /* fallthrough */ }
    // Extractive fallback
    const firstLine = text.split('\n').find(l => l.trim()) || 'No content';
    res.json({ filepath, summary: `One-line extractive summary: ${firstLine.slice(0, 200)}`, fallback: true });
});

// ── Routes ──────────────────────────────────────────────────────────────────

// ── Gemini Interceptor ──────────────────────────────────────────────────────
app.post('/v1beta/models/:apiAction', async (req, res) => {
    try {
        const apiAction = req.params.apiAction;
        logDebug(`\n[${new Date().toISOString()}] Gemini Interceptor started for ${apiAction}\n`);

        let workspaceId = config.workspace_id;
        const auth = req.headers.authorization;
        if (auth && auth.startsWith('Bearer ')) {
            const token = auth.substring(7).trim();
            if (token && token !== 'lm-studio') workspaceId = token.replace(/[^a-zA-Z0-9_-]/g, '_');
        }
        const reqStore = getStore(workspaceId);

        const body = { ...req.body };

        // Fast token-minimization on the contents array
        if (body.contents && Array.isArray(body.contents)) {
            let pseudoMessages = [];
            for (let i = 0; i < body.contents.length; i++) {
                const c = body.contents[i];
                if (!c.parts || !Array.isArray(c.parts)) continue;
                for (let j = 0; j < c.parts.length; j++) {
                    const part = c.parts[j];
                    if (part.text && typeof part.text === 'string') {
                        pseudoMessages.push({
                            role: c.role || 'user',
                            content: part.text,
                            _geminiRef: { contentIndex: i, partIndex: j }
                        });
                    }
                }
            }

            // Apply token slayers
            pseudoMessages = pseudoMessages.map(m => ({
                ...m,
                content: stripThinking(m.content)
            }));
            pseudoMessages = dedupeFileReads(pseudoMessages);

            // XRL Checkpointing
            const AUTO_CHECKPOINT = process.env.XRLF_PROXY_AUTO_CHECKPOINT !== '0' && process.env.XRLF_PROXY_AUTO_CHECKPOINT !== 'false';
            if (AUTO_CHECKPOINT) {
                try {
                    pseudoMessages = await compressContext(pseudoMessages, workspaceId);
                } catch (e) {
                    console.warn('[Gemini] compressContext failed:', e.message);
                }
            }

            // Re-map to payload
            for (const pm of pseudoMessages) {
                if (pm._geminiRef) {
                    body.contents[pm._geminiRef.contentIndex].parts[pm._geminiRef.partIndex].text = pm.content;
                }
            }

            // Memory Rings
            if (body.contents.length > 0) {
                // Extract base model from apiAction (e.g. gemini-1.5-pro:generateContent -> gemini-1.5-pro)
                const modelId = apiAction.split(':')[0] || 'gemini-1.5-pro';
                const { scaledConfig } = scaleConfigForModel(modelId, config);
                const ringBlock = await buildRingBlock(reqStore, scaledConfig, workspaceId);
                if (ringBlock) {
                    const firstUser = body.contents.find(c => c.role === 'user' || c.role === 'model');
                    if (firstUser && firstUser.parts) {
                        firstUser.parts.unshift({ text: ringBlock + '\n\n' });
                    }
                }
            }
        }

        // System instruction strip
        if (body.systemInstruction && body.systemInstruction.parts) {
            for (let part of body.systemInstruction.parts) {
                if (part.text) part.text = stripThinking(part.text);
            }
        }

        // Forward to Google
        const apiKey = req.query.key || '';
        let upstreamUrl = `https://generativelanguage.googleapis.com/v1beta/models/${apiAction}`;
        if (apiKey) upstreamUrl += `?key=${apiKey}`;

        logDebug(`[${new Date().toISOString()}] before fetch to Gemini API\n`);

        const fwdHeaders = { 'Content-Type': 'application/json' };
        if (req.headers['x-goog-api-key']) fwdHeaders['x-goog-api-key'] = req.headers['x-goog-api-key'];
        if (req.headers['x-goog-api-client']) fwdHeaders['x-goog-api-client'] = req.headers['x-goog-api-client'];

        const upstreamRes = await fetch(upstreamUrl, {
            method: 'POST',
            headers: fwdHeaders,
            body: JSON.stringify(body)
        });

        // Stream response back transparently
        res.status(upstreamRes.status);
        upstreamRes.headers.forEach((val, key) => {
            if (!['content-encoding', 'content-length', 'transfer-encoding'].includes(key.toLowerCase())) {
                res.setHeader(key, val);
            }
        });
        upstreamRes.body.pipe(res);

        upstreamRes.body.on('error', (err) => {
            console.error('[Gemini Interceptor] Stream error:', err);
        });
    } catch (err) {
        console.error(`[Gemini Interceptor] Unhandled error:`, err);
        if (!res.headersSent) res.status(500).json({ error: err.message });
    }
});

app.post(['/v1/chat/completions', '/chat/completions'], (req, res) => {
    // ── Transparent Mode: Direct Passthrough ─────────────────────────────
    // In transparent mode, bypass ALL foveation features and just pass through
    // to the upstream server. This is for direct llama server access.
    if (PROXY_MODE === "transparent") {
        const upstreamUrl = config.upstream_url || `${XRLF_RUNTIME_URL}/v1`;
        const baseUrl = upstreamUrl.replace(/\/v1\/?$/, '');
        
        console.log(`[TransparentMode] 🔄 Passthrough to ${upstreamUrl}`);
        
        // Forward the request directly to upstream
        const isLocalTarget = !(config._cloud_mode && config._api_key);
        let releaseSlot = null;
        const slotTicket = isLocalTarget
            ? acquireLocalUpstream().then(rel => { releaseSlot = rel; })
            : Promise.resolve();
        slotTicket.then(() => fetch(`${baseUrl}/v1/chat/completions`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': req.headers.authorization || ''
            },
            body: JSON.stringify(req.body)
        }))
        .then(response => {
            if (releaseSlot) {
                let released = false;
                const rel = () => { if (!released) { released = true; releaseSlot(); } };
                response.body.once('end', rel);
                response.body.once('close', rel);
                response.body.once('error', rel);
                setTimeout(rel, 10 * 60 * 1000).unref();
            }
            // Forward all headers from upstream
            response.headers.forEach((value, key) => {
                if (key.toLowerCase() !== 'transfer-encoding') {
                    res.setHeader(key, value);
                }
            });
            res.status(response.status);
            return response.body.pipe(res);
        })
        .catch(err => {
            if (releaseSlot) releaseSlot();
            console.error('[TransparentMode] Passthrough error:', err);
            if (!res.headersSent) {
                res.status(500).json({ error: 'Transparent mode passthrough failed', details: err.message });
            }
        });
        return;
    }

    // Multi-user auth: session tokens, API tokens, and legacy workspace-name
    // bearers all resolve through the same path so memory scoping is consistent
    // across every endpoint.
    const _authz = resolveRequestAuth(req);
    const _loopbackChat = ['127.0.0.1', '::1', '::ffff:127.0.0.1'].includes(req.socket.remoteAddress || '');
    if (_authz.rejected) return res.status(401).json({ error: 'invalid or expired session' });
    // Loopback chat clients (opencode, console, local tooling) ride the local
    // admin fallback — the proxy already reserves anonymous for loopback trust;
    // remote anonymous stays refused.
    if (_authz.userId === 'anonymous' && !_loopbackChat) {
        return res.status(401).json({ error: 'authentication required' });
    }
    if (!_authz._mgr.hasFeature({ role: _authz.role, features: _authz.features }, 'chat')) {
        return res.status(403).json({ error: 'chat feature not enabled for this account' });
    }
    const workspaceId = _authz.workspaceId;
    const userId = _authz.userId;
    req.userId = userId;
    req.authFeatures = _authz.features;

    if (!req.headers.authorization && COGNITIVE_MODE === 'cloud' && !warnedMissingAuth) {
        console.warn(`[Auth] No client Bearer token; using collective workspace "${workspaceId}" based on proxy API key.`);
        warnedMissingAuth = true;
    }

    const reqStore = getStore(workspaceId);

    handleChatCompletion(req, res, null, reqStore, workspaceId).catch(err => {
        console.error(`[Server] Unhandled error in workspace ${workspaceId}:`, err);
        if (!res.headersSent) res.status(500).json({ error: err.message });
    });
});

// Passthrough: models list — forwards to upstream (LM Studio or Ollama Cloud)
app.get(['/v1/models', '/models'], async (req, res) => {
    try {
        const modelsHeaders = {};
        if (config._cloud_mode && config._api_key) {
            modelsHeaders['Authorization'] = `Bearer ${config._api_key}`;
        }
        let data;
        try {
            const baseUrl = config.upstream_url.replace(/\/v1\/?$/, '');
            const r = await fetch(`${baseUrl}/v1/models`, {
                headers: modelsHeaders,
                signal: AbortSignal.timeout(3000)
            });
            if (r.ok) {
                data = await r.json();
            }
        } catch (upstreamErr) {
            console.warn(`[Fovea] /v1/models upstream fetch failed: ${upstreamErr.message}`);
        }

        // If upstream gave us nothing usable, return the configured default model so clients can select it
        if (!data || !data.data || data.data.length === 0) {
            // Build a sensible fallback from env config
            const fallbackModels = [];
            if (UPSTREAM_MODEL) fallbackModels.push({ id: UPSTREAM_MODEL, object: 'model', created: Math.floor(Date.now()/1000), owned_by: COGNITIVE_MODE === 'cloud' ? 'ollama-cloud' : 'lmstudio' });
            // Always expose a proxy-managed "auto" entry
            // fallbackModels.push({ id: 'foveated-proxy-auto', object: 'model', created: Math.floor(Date.now()/1000), owned_by: 'foveated-proxy' });
            data = {
                object: 'list',
                data: fallbackModels
            };
            console.log(`[Fovea] /v1/models returning fallback: ${fallbackModels.map(m=>m.id).join(', ')}`);
        }

        // ── Inject model profiles (primary + secondary) from model-profiles.json ──
        // This ensures clients (Cline, LM Studio, etc.) can see and select between
        // all configured models, including the secondary FoveAI Omni Router instance.
        try {
            const profiles = listProfiles();
            if (profiles && profiles.length > 0 && data && Array.isArray(data.data)) {
                const existingIds = new Set(data.data.map(m => m.id));
                for (const p of profiles) {
                    if (p.role === 'dormant') continue;  // skip dormant models
                    if (!existingIds.has(p.id)) {
                        const owner = p.provider === 'ollama_cloud' ? 'ollama-cloud'
                                    : (p.provider === 'llama_server' || p.provider === 'xrlf_server') ? 'xrlf-runtime'
                                    : 'lmstudio';
                        data.data.push({
                            id:       p.id,
                            object:   'model',
                            created:  Math.floor(Date.now() / 1000),
                            owned_by:  owner
                        });
                        // Also register aliases as model IDs so clients that use
                        // an alias can resolve it without a 404.
                        for (const alias of (p.aliases || [])) {
                            if (!existingIds.has(alias)) {
                                existingIds.add(alias);
                                data.data.push({
                                    id:      alias,
                                    object:  'model',
                                    created: Math.floor(Date.now() / 1000),
                                    owned_by: owner
                                });
                            }
                        }
                    }
                }
                console.log(`[Fovea] /v1/models enriched with profiles: ${profiles.filter(p => p.role !== 'dormant').map(p => p.id).join(', ')}`);
            }
        } catch (profileErr) {
            console.warn(`[Fovea] /v1/models profile injection failed: ${profileErr.message}`);
        }

        // ── Nova collegium models (side-route to :8416 bridge) ─────────────
        // Merge the bridge's live list so the swarm shows up in every client's
        // picker as soon as it is awake, and vanishes when it is not.
        try {
            data = data || { object: 'list', data: [] };
            if (!Array.isArray(data.data)) data.data = [];
            const nr = await fetch(`${NOVA_URL}/v1/models`, { signal: AbortSignal.timeout(1500) });
            if (nr.ok) {
                const nj = await nr.json();
                const haveNova = new Set(data.data.map(m => m.id));
                for (const m of (nj.data || [])) {
                    if (!haveNova.has(m.id)) {
                        data.data.push({ id: m.id, object: 'model', created: Math.floor(Date.now() / 1000), owned_by: 'nova-collegium' });
                    }
                }
            }
        } catch (novaErr) {
            console.warn(`[Fovea] /v1/models nova merge skipped: ${novaErr.message}`);
        }

        // ── Cloud models ────────────────────────────────────────────────────
        // Members see exactly one friendly entry ('nvidia-free' → curated
        // backend model, name undisclosed). Admins/legacy get the full
        // nvidia/* side-route catalog.
        if (data && Array.isArray(data.data)) {
            const na = resolveRequestAuth(req);
            const mgr = getAuthManager(AUTH_DB_DIR);
            const cloudOk = !na.rejected &&
                mgr.hasFeature({ role: na.role, features: na.features }, 'cloud');
            const ids = new Set(data.data.map(m => m.id));
            if (cloudOk) {
                // The NIM catalog is listed for every cloud-enabled caller, not
                // just admins: the models are NVIDIA's free tier, the route is
                // server-side and already cost-free to us, and hiding the list
                // behind an admin check meant members only ever saw the single
                // opaque 'nvidia-free' alias with no way to tell what they are
                // actually talking to.
                for (const m of NVIDIA_MODELS) {
                    const nid = NVIDIA_PREFIX + m;
                    if (!ids.has(nid)) {
                        data.data.push({ id: nid, object: 'model', created: Math.floor(Date.now() / 1000), owned_by: 'nvidia-nim' });
                    }
                }
                if (!ids.has(FREE_CLOUD_ID)) {
                    data.data.push({ id: FREE_CLOUD_ID, object: 'model', created: Math.floor(Date.now() / 1000), owned_by: 'foveai-cloud' });
                }
                // Ollama Cloud: routed per-model as 'ollama/<id>'. The list is
                // seeded by XRLF_OLLAMA_MODELS only — routing itself is
                // permissive, so an unlisted id still resolves server-side.
                if (OLLAMA_API_KEY) {
                    for (const m of OLLAMA_MODELS) {
                        const oid = OLLAMA_PREFIX + m;
                        if (!ids.has(oid)) {
                            data.data.push({ id: oid, object: 'model', created: Math.floor(Date.now() / 1000), owned_by: 'ollama-cloud' });
                        }
                    }
                }
            }
        }

        // ── BYOK: callers with a stored cloud key see their own route ────────
        if (data && Array.isArray(data.data)) {
            try {
                const ba = resolveRequestAuth(req);
                if (!ba.rejected && ba.userId && ba.userId !== 'anonymous' && !ba.isLegacy) {
                    const bk = getAuthManager(AUTH_DB_DIR).getByokPublic(ba.userId);
                    if (bk) {
                        for (const bid of (bk.model ? ['byok', `byok/${bk.model}`] : ['byok'])) {
                            if (!data.data.find(m => m.id === bid)) {
                                data.data.push({ id: bid, object: 'model', created: Math.floor(Date.now() / 1000), owned_by: `byok-${bk.provider}` });
                            }
                        }
                    }
                }
            } catch (_) { /* byok listing is opportunistic */ }
        }

        // Always inject foveated-proxy-auto into the real model list
        if (data && data.data && !data.data.find(m => m.id === 'foveated-proxy-auto')) {
            // data.data.unshift({ id: 'foveated-proxy-auto', object: 'model', created: Math.floor(Date.now()/1000), owned_by: 'foveated-proxy' });
        }
        // Dedupe by id — upstream lists (ollama cloud returns devin-opus/
        // devin-sonnet-4 twice) leak duplicates into pickers that key on id.
        if (data && Array.isArray(data.data)) {
            const seen = new Set();
            data.data = data.data.filter(m => m && m.id && !seen.has(m.id) && seen.add(m.id));
        }
        res.json(data);
    } catch (err) {
        console.error(`[Fovea] /v1/models handler failed:`, err.message);
        res.status(500).json({ error: { message: err.message, type: 'internal_error' } });
    }
});

// Extensions like Papillion often do a GET /v1/models/model_name to verify it exists
app.get(['/v1/models/:model', '/models/:model'], async (req, res) => {
    // Just mock a success response to keep the extension happy
    const modelData = {
        id: req.params.model,
        object: "model",
        created: Math.floor(Date.now() / 1000),
        owned_by: "foveated-proxy"
    };
    // Inject spoofed context_window when active — fools Papillon/Cline/VS Code into thinking they have 128K
    // SAFE_MODE overrides: reports real context window instead of spoofed value
    if (SPOOF_CONTEXT_WINDOW > 0 && !SAFE_MODE) {
        modelData.context_window = SPOOF_CONTEXT_WINDOW;
        modelData.max_context_length = SPOOF_CONTEXT_WINDOW;
        console.log(`[Spoof] /v1/models/${req.params.model} → context_window=${SPOOF_CONTEXT_WINDOW}`);
    }
    res.json(modelData);
});

// Health check
app.get('/health', async (req, res) => {
    try {
        const _authz = resolveRequestAuth(req);
        if (_authz.rejected) return res.status(401).json({ error: 'invalid or expired session' });
        const workspaceId = _authz.workspaceId;
        const s = getStore(workspaceId);
        const storedCount = await s.count();
        res.json({
            status: 'ONLINE',
            service: 'XRLF/FoveatedMemory Unified Proxy v3',
            workspace: workspaceId,
            upstream: config.upstream_url,
            mode: COGNITIVE_MODE,
            cloud_cap: CLOUD_MAX_TOKENS_CAP > 0 ? CLOUD_MAX_TOKENS_CAP : 'auto',
            preserve_last: PRESERVE_LAST_TURNS,
            stored_messages: storedCount,
            session: SESSION_ID,
            xrl_cache_size: xrlCache.size
        });
    } catch (err) {
        res.status(500).json({ status: 'ERROR', error: err.message });
    }
});

// ── Debug: GET /memory/rings — show the current foveated ring block ──────────
app.get('/memory/rings', async (req, res) => {
    try {
        const _authz = resolveRequestAuth(req);
        if (_authz.rejected) return res.status(401).json({ error: 'invalid or expired session' });
        const workspaceId = _authz.workspaceId;
        const s = getStore(workspaceId);
        const scaledConfig = { ...config, ring_budgets: undefined }; // use defaults
        const ringBlock = await buildRingBlock(s, scaledConfig, SESSION_ID);
        const storedCount = await s.count();
        res.json({
            stored_messages: storedCount,
            session: SESSION_ID,
            ring_block: ringBlock,
            ring_tokens_est: Math.ceil(ringBlock.length / 4),
        });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// Memory audit — run a safety scan for misclassified messages
app.get('/api/audit', async (req, res) => {
    try {
        const _authz = resolveRequestAuth(req);
        if (_authz.rejected) return res.status(401).json({ error: 'invalid or expired session' });
        const workspaceId = _authz.workspaceId;
        const s = getStore(workspaceId);
        const dryRun = req.query.dryRun !== 'false'; // default to dry run
        const limit = parseInt(req.query.limit || '200', 10);
        const report = await runAudit(s, { limit, dryRun });
        res.json(report);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// Memory stats
app.get('/memory/stats', async (req, res) => {
    try {
        const _authz = resolveRequestAuth(req);
        if (_authz.rejected) return res.status(401).json({ error: 'invalid or expired session' });
        const workspaceId = _authz.workspaceId;
        const s = getStore(workspaceId);
        const storedCount = await s.count();
        res.json({
            workspace_id: workspaceId,
            stored_messages: storedCount,
            session_id: SESSION_ID
        });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// ── /api/status endpoint (consumed by Jenna VSCode extension) ─────────────────

app.get('/api/status', async (req, res) => {
    try {
        const _authz = resolveRequestAuth(req);
        if (_authz.rejected) return res.status(401).json({ error: 'invalid or expired session' });
        const workspaceId = _authz.workspaceId;
        const s = getStore(workspaceId);
        const totalRaw = await s.count();
        let totalThemes = await s.countThemes();
        const totalSessions = await s.countSessions();

        // Auto-consolidate raw memories into themes if themes aren't generated yet
        if (totalThemes === 0 && totalRaw > 0) {
            try {
                const resConsol = await s.consolidateRawMemories();
                totalThemes = resConsol.themesCreated;
            } catch (_) {}
        }

        let vramStatus = null;
        try {
            const lockFile = path.resolve(__dirname, '..', '.model_locks', 'main_model.lock');
            if (fs.existsSync(lockFile)) {
                vramStatus = JSON.parse(fs.readFileSync(lockFile, 'utf8'));
            }
        } catch (_) {}

        // Live runtime readiness — merged here so browser ignition probes don't
        // need a session cookie against the shielded /xrlf surface.
        // Probe the REAL health endpoint: upstream_url ends in /v1, and
        // llama-server serves /health (not /v1/health) — the old probe always
        // failed, so ignition sat on "checking the model" for two minutes.
        let runtimeHealth = null;
        try {
            const healthBase = String(config.upstream_url || '').replace(/\/v1\/?$/, '');
            const hr = await fetch(`${healthBase}/health`, { signal: AbortSignal.timeout(2500) });
            if (hr.ok) {
                const body = await hr.json().catch(() => ({}));
                // llama.cpp answers {"status":"ok"}; XRLF answers loaded/load_state
                const ready = body.loaded === true
                    || body.load_state === 'ready'
                    || String(body.status || '').toLowerCase() === 'ok';
                runtimeHealth = {
                    ...body,
                    loaded: ready,
                    load_state: body.load_state || (ready ? 'ready' : 'loading'),
                };
            }
        } catch (_) {}

        res.json({
            status: 'ONLINE',
            workspace_id: workspaceId,
            compression_level: parseInt(process.env.XRLF_PROXY_AGGRESSION || '3', 10),
            active_blocks: 0,
            total_memories: totalRaw,
            total_themes: totalThemes,
            total_sessions: totalSessions,
            model: config.model || 'auto',
            assistant_name: ASSISTANT_NAME,
            user_name: USER_NAME,
            upstream: config.upstream_url,
            session: SESSION_ID,
            vram_status: vramStatus,
            is_hybrid: vramStatus?.is_hybrid || false,
            status_text: vramStatus?.status_text || "",
            loaded: runtimeHealth?.loaded === true,
            load_state: runtimeHealth?.load_state || (runtimeHealth ? 'unknown' : 'unreachable'),
            load_error: runtimeHealth?.load_error || null
        });
    } catch (err) {
        res.status(500).json({ status: 'ERROR', error: err.message });
    }
});

// ── /api/residency/status endpoint (Tier A / Tier B live probe) ─────────────
app.get('/api/residency/status', async (req, res) => {
    const checkPort = (port) => new Promise(resolve => {
        const s = new net.Socket();
        s.setTimeout(250);
        s.on('connect', () => { s.destroy(); resolve(true); });
        s.on('error', () => { s.destroy(); resolve(false); });
        s.on('timeout', () => { s.destroy(); resolve(false); });
        s.connect(port, '127.0.0.1');
    });

    let tier = 'idle';
    let label = 'Idle (VRAM released)';
    let port = null;

    if (await checkPort(8408)) {
        tier = 'B';
        label = 'Tier B (9B on VRAM :8408)';
        port = 8408;
    } else if (await checkPort(8407)) {
        tier = 'A';
        label = 'Tier A (4B Light :8407)';
        port = 8407;
    }

    res.json({ tier, label, port });
});

// ── /api/sessions endpoint (returns list of available sessions across all stores) ────────────────
app.get('/api/sessions', async (req, res) => {
    try {
        const _authz = resolveRequestAuth(req);
        if (_authz.rejected) return res.status(401).json({ error: 'invalid or expired session' });
        const workspaceId = _authz.workspaceId;

        let subdirs = [];
        try {
            const memoryDataDir = path.join(__dirname, 'memory_data');
            subdirs = fs.readdirSync(memoryDataDir).filter(name => {
                try { return fs.statSync(path.join(memoryDataDir, name)).isDirectory() && name !== 'checkpoints'; }
                catch { return false; }
            });
        } catch (_) {}

        const priorityDirs = Array.from(new Set(['XRLF', 'default', 'jen', workspaceId, ...subdirs]));
        const sessionMap = new Map();

        for (const dbName of priorityDirs) {
            try {
                const storeInst = getStore(dbName);
                const sList = await storeInst.listSessions(50);
                for (const s of sList) {
                    const sid = s.session_id || s.id;
                    if (sid && (!sessionMap.has(sid) || (s.last_updated || '') > (sessionMap.get(sid).last_updated || ''))) {
                        sessionMap.set(sid, s);
                    }
                }
            } catch (_) {}
        }

        const sessions = Array.from(sessionMap.values())
            .sort((a, b) => (b.last_updated || '').localeCompare(a.last_updated || ''))
            .slice(0, 50);

        res.json({ status: 'OK', workspace_id: workspaceId, sessions });
    } catch (err) {
        res.status(500).json({ status: 'ERROR', error: err.message });
    }
});

// ── /api/session/messages endpoint (returns history for specific session) ──────
app.get('/api/session/messages', async (req, res) => {
    try {
        const _authz = resolveRequestAuth(req);
        if (_authz.rejected) return res.status(401).json({ error: 'invalid or expired session' });
        const workspaceId = _authz.workspaceId;
        const sessionId = req.query.session_id || SESSION_ID;
        const s = getStore(workspaceId);
        const msgs = await s.getBySession(sessionId);
        res.json({ status: 'OK', session_id: sessionId, messages: msgs });
    } catch (err) {
        res.status(500).json({ status: 'ERROR', error: err.message });
    }
});

// ── /api/session/rename endpoint — manual title edit from the chat divider ────
app.post('/api/session/rename', async (req, res) => {
    try {
        const _authz = resolveRequestAuth(req);
        if (_authz.rejected) return res.status(401).json({ error: 'invalid or expired session' });
        const workspaceId = _authz.workspaceId;
        const { session_id, title } = req.body || {};
        if (!session_id || !title) throw new Error("Missing session_id or title");
        const s = getStore(workspaceId);
        await s.setSessionMeta(session_id, { title: String(title).slice(0, 120) });
        res.json({ status: 'OK', session_id, title });
    } catch (err) {
        res.status(500).json({ status: 'ERROR', error: err.message });
    }
});

// ── /api/session/generate-title endpoint ───────────────────────────────────────
app.post('/api/session/generate-title', async (req, res) => {
    try {
        const _authz = resolveRequestAuth(req);
        if (_authz.rejected) return res.status(401).json({ error: 'invalid or expired session' });
        const workspaceId = _authz.workspaceId;
        const sessionId = req.body.session_id;
        if (!sessionId) throw new Error("Missing session_id");

        let s = getStore(workspaceId);
        let msgs = await s.getBySession(sessionId);
        if (msgs.length === 0) {
            for (const fallbackId of ['default', 'XRLF']) {
                const fallbackStore = getStore(fallbackId);
                const fallbackMsgs = await fallbackStore.getBySession(sessionId);
                if (fallbackMsgs.length > 0) {
                    s = fallbackStore;
                    msgs = fallbackMsgs;
                    break;
                }
            }
        }
        if (msgs.length === 0) return res.json({ status: 'OK', title: 'Empty Session' });

        // Grab up to last 6 messages for context
        const recentMsgs = msgs.slice(-6).map(m => m.role + ': ' + (typeof m.content === 'string' ? m.content.slice(0, 300) : '')).join('\n');

        const prompt = `Analyze this chat snippet and return metadata in EXACT FORMAT.
CRITICAL RULES:
1. Do NOT output any thinking blocks, reasoning, or conversational filler.
2. Output ONLY the 5 metadata lines.
3. Keep titles human-readable and professional.

TITLE: <3-6 word descriptive summary title>
THEME: <Code|Architecture|UI|General>
PROJECT: <Project or workspace name, e.g. XRLF, Jenna, Extension, or General>
KEYWORDS_ROW1: <3-4 key topic tags, e.g. #WebXR #FoveatedMemory #VSCode>
KEYWORDS_ROW2: <3-4 key issue/action tags, e.g. #FixSessionTitles #KeywordRows #UIEnhancement>

Snippet:
${recentMsgs}`;

        const r = await withLocalUpstream(() => fetch(`${XRLF_RUNTIME_URL}/v1/chat/completions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model: SUMMARIZER_MODEL || MIDDLEMAN_MODEL,
                messages: [{ role: 'user', content: prompt }],
                temperature: 0.2,
                max_tokens: 120,
                // Bare utility call — no soul injection, no memory persistence,
                // so title generation never pollutes the session or persona state
                xrlf_utility: true,
                xrlf_headless: true,
                xrlf_thinking: false
            })
        }));

        if (!r.ok) throw new Error("LLM request failed");
        const data = await r.json();
        let raw = data.choices?.[0]?.message?.content || '';
        raw = raw.replace(/<think>[\s\S]*?<\/think>/gi, '').trim();

        let title = (raw.match(/TITLE:\s*([^\n]+)/i)?.[1] || raw.split('\n')[0] || '').replace(/^["'\s]+|["'\s]+$/g, '').trim();
        title = title.replace(/[◆◇■□●○★☆▲▼#*_`]/g, '').trim();
        title = title.replace(/^(the|a|an)\s+/i, '');
        if (!title || title.length <= 3 || /^(the|a|an|untitled|session)$/i.test(title)) {
          title = 'Untitled Session';
        }
        let theme = (raw.match(/THEME:\s*([^\n]+)/i)?.[1] || 'General').trim();
        let project = (raw.match(/PROJECT:\s*([^\n]+)/i)?.[1] || workspaceId || 'XRLF').trim();

        let kw1 = (raw.match(/KEYWORDS_ROW1:\s*([^\n]+)/i)?.[1] || '').trim();
        let kw2 = (raw.match(/KEYWORDS_ROW2:\s*([^\n]+)/i)?.[1] || '').trim();

        let keywords = [kw1, kw2].filter(Boolean).join('\n');
        if (!keywords) {
          keywords = '#Session #Context';
        }

        if (!title || title.length < 3) title = 'Untitled Session';

        await s.setSessionMeta(sessionId, { title, theme, project, keywords, keywords_row1: kw1, keywords_row2: kw2 });
        res.json({ status: 'OK', session_id: sessionId, title, theme, project, keywords, keywords_row1: kw1, keywords_row2: kw2 });
    } catch (err) {
        logError(`[generate-title] failed: ${err.message}`);
        res.status(500).json({ status: 'ERROR', error: err.message });
    }
});

// ── /api/session/purge-and-retitle endpoint (Batch process legacy imported sessions) ─────────────
app.post('/api/session/purge-and-retitle', async (req, res) => {
    try {
        const _authz = resolveRequestAuth(req);
        if (_authz.rejected) return res.status(401).json({ error: 'invalid or expired session' });
        const workspaceId = _authz.workspaceId;
        const s = getStore(workspaceId);
        const sessions = await s.getRecentSessions();
        let purged = 0;
        let retitled = 0;

        for (const sess of sessions) {
            const sid = sess.session_id || sess.id;
            if (!sid) continue;
            const msgs = await s.getBySession(sid);

            // Purge 1 or 2 turn sessions (stubs with no real work)
            if (msgs.length <= 2) {
                await s.deleteSession(sid).catch(() => {});
                purged++;
                continue;
            }

            // Force full retitle & keyword generation for all active sessions using last 10 messages
            const recentMsgs = msgs.slice(-10).map(m => m.role + ': ' + (typeof m.content === 'string' ? m.content.slice(0, 400) : '')).join('\n');
            const prompt = `Analyze this chat snippet (last 10 turns of session) and return metadata in EXACT FORMAT:
TITLE: <3-6 word clear, descriptive summary title of what was accomplished or discussed>
THEME: <Code|Architecture|UI|General>
PROJECT: <Project or workspace name, e.g. XRLF, Jenna, Extension, or General>
KEYWORDS_ROW1: <3-4 key topic tags, e.g. #WebXR #FoveatedMemory #VSCode>
KEYWORDS_ROW2: <3-4 key issue/action tags, e.g. #FixSessionTitles #KeywordRows #UIEnhancement>

Snippet:
${recentMsgs}`;
            try {
                const r = await withLocalUpstream(() => fetch(`${XRLF_RUNTIME_URL}/v1/chat/completions`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        model: SUMMARIZER_MODEL || MIDDLEMAN_MODEL,
                        messages: [{ role: 'user', content: prompt }],
                        temperature: 0.2,
                        max_tokens: 140,
                        xrlf_utility: true,
                        xrlf_headless: true,
                        xrlf_thinking: false
                    })
                }));
                if (r.ok) {
                    const data = await r.json();
                    let raw = data.choices?.[0]?.message?.content || '';
                    raw = raw.replace(/<think>[\s\S]*?<\/think>/gi, '').trim();

                    let title = (raw.match(/TITLE:\s*([^\n]+)/i)?.[1] || raw.split('\n')[0] || '').replace(/^["'\s]+|["'\s]+$/g, '').trim();
                    title = title.replace(/[◆◇■□●○★☆▲▼#*_`]/g, '').trim().replace(/^(the|a|an)\s+/i, '');
                    if (!title || title.length <= 3) title = 'Untitled Session';
                    let theme = (raw.match(/THEME:\s*([^\n]+)/i)?.[1] || 'General').trim();
                    let project = (raw.match(/PROJECT:\s*([^\n]+)/i)?.[1] || workspaceId || 'XRLF').trim();
                    let kw1 = (raw.match(/KEYWORDS_ROW1:\s*([^\n]+)/i)?.[1] || '').trim();
                    let kw2 = (raw.match(/KEYWORDS_ROW2:\s*([^\n]+)/i)?.[1] || '').trim();
                    let keywords = [kw1, kw2].filter(Boolean).join('\n');

                    await s.setSessionMeta(sid, { title, theme, project, keywords, keywords_row1: kw1, keywords_row2: kw2 });
                    retitled++;
                }
            } catch (_) {}
        }
        res.json({ status: 'OK', purged, retitled, total: sessions.length });
    } catch (err) {
        logError(`[purge-and-retitle] failed: ${err.message}`);
        res.status(500).json({ status: 'ERROR', error: err.message });
    }
});

// ── /api/session/ingredients endpoint (Full session deep index & ingredients list) ─────────────
app.post('/api/session/ingredients', async (req, res) => {
    try {
        const _authz = resolveRequestAuth(req);
        if (_authz.rejected) return res.status(401).json({ error: 'invalid or expired session' });
        const workspaceId = _authz.workspaceId;
        const { session_id } = req.body;
        if (!session_id) return res.status(400).json({ error: 'session_id required' });

        let s = getStore(workspaceId);
        let msgs = await s.getBySession(session_id);
        if (msgs.length === 0) {
            for (const fallbackId of ['default', 'XRLF']) {
                const fallbackStore = getStore(fallbackId);
                const fallbackMsgs = await fallbackStore.getBySession(session_id);
                if (fallbackMsgs.length > 0) {
                    s = fallbackStore;
                    msgs = fallbackMsgs;
                    break;
                }
            }
        }
        if (msgs.length === 0) return res.json({ status: 'OK', ingredients: '' });

        let sampleMsgs = msgs;
        if (msgs.length > 12) {
            sampleMsgs = [...msgs.slice(0, 4), ...msgs.slice(Math.floor(msgs.length/2) - 2, Math.floor(msgs.length/2) + 2), ...msgs.slice(-4)];
        }
        const fullSnippet = sampleMsgs.map(m => m.role + ': ' + (typeof m.content === 'string' ? m.content.slice(0, 250) : '')).join('\n');

        const prompt = `Analyze this full session snippet and extract a detailed Ingredients Index:
SUMMARY: <2-sentence summary of what was accomplished>
TOPICS: <comma-separated key technical topics>
INGREDIENTS: <bullet points of files, APIs, components, or functions touched>

Snippet:
${fullSnippet}`;

        const r = await withLocalUpstream(() => fetch(`${XRLF_RUNTIME_URL}/v1/chat/completions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model: SUMMARIZER_MODEL || MIDDLEMAN_MODEL,
                messages: [{ role: 'user', content: prompt }],
                temperature: 0.2,
                max_tokens: 150,
                xrlf_utility: true,
                xrlf_headless: true,
                xrlf_thinking: false
            })
        }));

        if (!r.ok) throw new Error("LLM request failed");
        const data = await r.json();
        let raw = data.choices?.[0]?.message?.content || '';
        raw = raw.replace(/<think>[\s\S]*?<\/think>/gi, '').trim();

        let summary = (raw.match(/SUMMARY:\s*([^\n]+)/i)?.[1] || '').trim();
        let topics = (raw.match(/TOPICS:\s*([^\n]+)/i)?.[1] || '').trim();
        let ingredientsRaw = (raw.match(/INGREDIENTS:\s*([\s\S]+)/i)?.[1] || raw).trim();

        await s.setSessionMeta(session_id, { summary, topics, ingredients: ingredientsRaw });
        res.json({ status: 'OK', session_id, summary, topics, ingredients: ingredientsRaw });
    } catch (err) {
        logError(`[ingredients] failed: ${err.message}`);
        res.status(500).json({ status: 'ERROR', error: err.message });
    }
});

// ── /api/consolidate endpoint (trigger theme consolidation) ───────────────────
app.post('/api/consolidate', async (req, res) => {
    try {
        const _authz = resolveRequestAuth(req);
        if (_authz.rejected) return res.status(401).json({ error: 'invalid or expired session' });
        const workspaceId = _authz.workspaceId;
        const s = getStore(workspaceId);
        const result = await s.consolidateRawMemories();
        res.json({ status: 'OK', ...result });
    } catch (err) {
        res.status(500).json({ status: 'ERROR', error: err.message });
    }
});

// ═══ Settings / Control Panel API (user-initiated only; no watchdog loops) ═══

const envFilePath = path.resolve(__dirname, '..', '.env');

function readEnv() {
    if (!fs.existsSync(envFilePath)) return '';
    return fs.readFileSync(envFilePath, 'utf8');
}

function writeEnv(content) {
    fs.writeFileSync(envFilePath, content, 'utf8');
}

function setEnvVar(key, value) {
    const lines = readEnv().split(/\r?\n/);
    const replacement = `${key}=${value}`;
    let found = false;
    const out = lines.map(line => {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith('#')) return line;
        const eq = trimmed.indexOf('=');
        if (eq === -1) return line;
        const k = trimmed.slice(0, eq).trim();
        if (k !== key) return line;
        found = true;
        // Preserve any inline comment
        const commentMatch = line.match(/\s+#.*$/);
        const comment = commentMatch ? commentMatch[0] : '';
        return `${key}=${value}${comment}`;
    });
    if (!found) out.push(replacement);
    writeEnv(out.join('\n'));
}

function applyFrontendPreset(ui) {
    const uiNorm = String(ui).toLowerCase().trim();
    if (!['xr_vessel', '3d_avatar', 'multigate'].includes(uiNorm)) return;

    // Multigate (web mode) → :5177 (standard spatial UI port)
    // XR Vessel (XR mode)   → :5176 (Vite default for XR)
    const portMap = { multigate: '5177', xr_vessel: '5176', '3d_avatar': '8080' };
    const targetPort = portMap[uiNorm] || '5177';
    const targetProtocol = 'http';

    setEnvVar('XRLF_FRONTEND_UI', uiNorm);
    setEnvVar('VITE_URL', `${targetProtocol}://127.0.0.1:${targetPort}`);

    // Update Cloudflare tunnel config if it exists
    const tunnelConfigPath = path.resolve(__dirname, '..', '..', 'config.yml');
    try {
        let raw = fs.readFileSync(tunnelConfigPath, 'utf8');
        raw = raw.replace(
            /hostname:\s*XRLF\.1um6a\.se\r?\n\s*service:\s*http[s]*:\/\/[^\r\n]+(?:\r?\n\s*noTLSVerify:\s*true)?/,
            `hostname: XRLF.1um6a.se\n    service: http://127.0.0.1:${targetPort}`
        );
        fs.writeFileSync(tunnelConfigPath, raw, 'utf8');
        console.log(`[Setting] Tunnel config updated → ${targetProtocol}://127.0.0.1:${targetPort}`);
    } catch (e) {
        console.warn('[Setting] Tunnel config update skipped:', e.message);
    }

    // Auto-start Vite dev server (Multigate is the default; XR Vessel is on-demand)
    if (uiNorm === 'multigate') {
        startViteServer('multigate');
    }

    // Touch .env so Sleipnir's watchdog redeploys the frontend node
    try {
        const envPath = path.resolve(__dirname, '..', '.env');
        const now = new Date();
        fs.utimesSync(envPath, now, now);
    } catch (e) {
        console.warn('[Setting] .env touch failed:', e.message);
    }
}

function startViteServer(frontend) {
    const frontendDir = frontend === 'multigate'
        ? path.resolve(__dirname, '..', 'Frontend', 'multigate')
        : path.resolve(__dirname, '..', 'Frontend', 'XR_Vessel');
    if (!fs.existsSync(frontendDir)) {
        console.warn(`[Vite] Frontend dir not found: ${frontendDir}`);
        return;
    }
    // Multigate → :5177, XR Vessel → :5176
    const port = frontend === 'multigate' ? 5177 : 5176;
    const http = require('http');
    const probe = http.get(`http://127.0.0.1:${port}`, () => {
        console.log(`[Vite] Already running on :${port} — skipping start`);
    });
    probe.on('error', () => {
        console.log(`[Vite] Starting ${frontend} Vite dev server on :${port}…`);
        if (IS_LINUX) {
            const child = spawn('npm', ['run', 'dev'], {
                cwd: frontendDir, detached: true, stdio: 'ignore'
            });
            child.unref();
            console.log(`[Vite] ✅ ${frontend} dev server launched on :${port} (pid ${child.pid})`);
            return;
        }
        execFile('C:\\Windows\\System32\\cmd.exe',
            ['/c', 'start', '/min', '', 'npm', 'run', 'dev'],
            { cwd: frontendDir, windowsHide: true, detached: true },
            (err) => {
                if (err) console.warn(`[Vite] Failed to start: ${err.message}`);
                else console.log(`[Vite] ✅ ${frontend} dev server launched on :${port}`);
            }
        );
    });
    probe.setTimeout(2000, () => { probe.destroy(); });
}

function runPwsh(command, callback) {
    if (IS_LINUX) {
        // On Linux, run as bash command instead of PowerShell
        execFile('bash', ['-c', command], {
            cwd: path.resolve(__dirname, '..', '..')
        }, (err, stdout, stderr) => {
            if (callback) callback(err, stdout, stderr);
        });
        return;
    }
    execFile(PWSH, ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', command], {
        cwd: path.resolve(__dirname, '..', '..'),
        windowsHide: true
    }, (err, stdout, stderr) => {
        if (callback) callback(err, stdout, stderr);
    });
}

app.use(express.json());

// ── Account auth — sessions, users, feature gates ──────────────────────────
// Every endpoint resolves the Bearer credential through resolveRequestAuth so
// a session token, an API token, or a legacy workspace-name token all land on
// the same memory scope. A rejected (expired/unknown) session returns 401;
// no Authorization header keeps the historical open-local behavior.
const AUTH_DB_DIR = path.resolve(__dirname, 'memory_data');

function resolveRequestAuth(req) {
    const authManager = getAuthManager(AUTH_DB_DIR);
    const auth = req.headers.authorization;
    if (auth && auth.startsWith('Bearer ')) {
        const token = auth.substring(7).trim();
        const resolved = authManager.resolveToken(token);
        if (!resolved) return { rejected: true };
        return {
            workspaceId: resolved.teamId,
            userId: resolved.userId,
            role: resolved.role || 'member',
            features: resolved.features || [],
            isLegacy: !!resolved.isLegacy,
            _mgr: authManager,
        };
    }
    if (COGNITIVE_MODE === 'cloud') {
        const collectiveKey = OLLAMA_API_KEY
            ? `key_${OLLAMA_API_KEY.slice(0, 16)}`
            : DEFAULT_FALLBACK_WORKSPACE;
        return { workspaceId: collectiveKey, userId: 'anonymous', role: 'admin', features: [], isLegacy: true, _mgr: authManager };
    }
    return { workspaceId: config.workspace_id, userId: 'anonymous', role: 'admin', features: [], isLegacy: true, _mgr: authManager };
}

// Feature gate middleware factory — account sessions need the named feature;
// legacy bearers resolve to admin and pass through. Anonymous (no Bearer at
// all) is refused: /api is reachable through the public tunnel gate-free, so
// no-header cannot be allowed to ride the admin fallback.
function requireFeature(feature) {
    return (req, res, next) => {
        const a = resolveRequestAuth(req);
        if (a.rejected) return res.status(401).json({ error: 'invalid or expired session' });
        if (a.userId === 'anonymous') return res.status(401).json({ error: 'authentication required' });
        if (!a._mgr.hasFeature({ role: a.role, features: a.features }, feature)) {
            return res.status(403).json({ error: `'${feature}' feature not enabled for this account` });
        }
        next();
    };
}

// Session-authenticated admin: a real fvs_ login, not a legacy bearer and
// never anonymous. Account administration is reserved for this tier.
function isSessionAdmin(a, mgr) {
    return !a.rejected && !a.isLegacy && a.userId && a.userId !== 'anonymous'
        && mgr.hasFeature({ role: a.role, features: a.features }, 'users_admin');
}

// ── Per-user settings overlay (member self-service) ──────────────────────
// Admin keys stay admin-only (requireAdmin). The ignition trackball traits
// (XRLF_*/FOVEA_*) are user-scoped: member writes land in the workspace
// overlay file instead of the global env — that's WHY the dial "just won't
// change": member POSTs were silently 403'd by admin gating.
const SETTINGS_OVERLAYS_DIR = path.join(path.resolve(__dirname, '..'), 'foveated-memory', 'data', 'setting_overlays');
function settingsOverlayPath(workspaceId) {
    const ws = String(workspaceId || 'default').replace(/[^a-zA-Z0-9_-]/g, '').slice(0, 32) || 'default';
    return path.join(SETTINGS_OVERLAYS_DIR, `${ws}.json`);
}
function readSettingsOverlay(workspaceId) {
    try { return JSON.parse(fs.readFileSync(settingsOverlayPath(workspaceId), 'utf8')); }
    catch (_) { return {}; }
}
function writeSettingsOverlay(workspaceId, obj) {
    try {
        fs.mkdirSync(SETTINGS_OVERLAYS_DIR, { recursive: true });
        fs.writeFileSync(settingsOverlayPath(workspaceId), JSON.stringify(obj, null, 2));
        return true;
    } catch (e) { console.warn('[Setting] overlay write failed:', e.message); return false; }
}
// Ignition/self-service settings — these keys a member may set for their own session
const USER_SETTING_KEYS = new Set([
    'XRLF_COGNITIVE_MODE', 'XRLF_MODEL_THINKING', 'XRLF_PROXY_AGGRESSION',
    'XRLF_CLOUD_PRESERVE_LAST', 'FOVEA_COMPRESS_EVERY', 'XRLF_CLOUD_MAX_TOKENS_CAP',
    'XRLF_SPOOF_CONTEXT_WINDOW', 'XRLF_VOICE_ENABLED', 'XRLF_MIC_ENABLED',
    'XRLF_MODEL_LOCAL_ID',
]);
function requireAdminOrUserKey(req, res, key) {
    // Admin passes; member passes ONLY for user-overlay keys (writes overlay)
    const a = resolveRequestAuth(req);
    if (a.rejected) { res.status(401).json({ error: 'invalid or expired session' }); return null; }
    if (a.userId === 'anonymous') { res.status(401).json({ error: 'authentication required' }); return null; }
    if (a._mgr.hasFeature({ role: a.role, features: a.features }, 'settings_admin')) return { admin: true, ...a };
    if (USER_SETTING_KEYS.has(key)) return { admin: false, ...a };
    res.status(403).json({ error: 'admin role required for core settings' });
    return null;
}
function requireAdmin(req, res) {
    const a = resolveRequestAuth(req);
    if (a.rejected) { res.status(401).json({ error: 'invalid or expired session' }); return null; }
    // Anonymous (no Authorization header at all) never gets admin powers —
    // the tunnel is public-facing, so "present on the LAN" is not a credential.
    if (a.userId === 'anonymous') { res.status(401).json({ error: 'authentication required' }); return null; }
    if (!a._mgr.hasFeature({ role: a.role, features: a.features }, 'settings_admin')) {
        res.status(403).json({ error: 'admin role required' });
        return null;
    }
    return a;
}

app.get('/api/auth/features', (req, res) => {
    res.json({ features: FEATURE_CATALOG });
});

// ── Beta observability (admin-only) ─────────────────────────────────────────
// Structured request telemetry written by handleChatCompletion → core/request-log.
// Aggregate stats for the admin console; raw tail for debugging a tester report.
app.get('/api/admin/usage', (req, res) => {
    const a = requireAdmin(req, res);
    if (!a) return;
    const hours = Math.min(720, Math.max(1, parseInt(req.query.hours || '24', 10) || 24));
    res.json(summarize(hours));
});

app.get('/api/admin/request-log', (req, res) => {
    const a = requireAdmin(req, res);
    if (!a) return;
    const tail = Math.min(2000, Math.max(1, parseInt(req.query.tail || '200', 10) || 200));
    res.json({ entries: readRecent(tail) });
});

app.post('/api/auth/login', (req, res) => {
    const { username, password } = req.body || {};
    if (!username || !password) return res.status(400).json({ error: 'username and password required' });
    const mgr = getAuthManager(AUTH_DB_DIR);
    const result = mgr.login(username, password);
    if (!result) return res.status(401).json({ error: 'invalid credentials or disabled account' });
    res.json(result);
});

app.post('/api/auth/challenge', (req, res) => {
    const { username } = req.body || {};
    if (!username) return res.status(400).json({ error: 'username required' });
    try {
        const mgr = getAuthManager(AUTH_DB_DIR);
        const challenge = mgr.createChallenge(username);
        res.json({ ok: true, username, nonce: challenge.nonce, expires: challenge.expires });
    } catch (e) {
        res.status(400).json({ error: String(e.message || e) });
    }
});

app.post('/api/auth/login-signature', (req, res) => {
    const { username, nonce, signature } = req.body || {};
    if (!username || !nonce || !signature) {
        return res.status(400).json({ error: 'username, nonce, and signature required' });
    }
    const mgr = getAuthManager(AUTH_DB_DIR);
    const result = mgr.loginWithSignature(username, nonce, signature);
    if (!result) return res.status(401).json({ error: 'invalid signature or expired challenge' });
    res.json(result);
});

// Profile persistence — the setup answers ride the account so the user is
// greeted on return, never re-quizzed (firstName/lastName/aiName).
app.get('/api/auth/profile', (req, res) => {
    const a = resolveRequestAuth(req);
    if (!a) return res.status(401).json({ error: 'unauthorized' });
    const mgr = getAuthManager(AUTH_DB_DIR);
    res.json(mgr.publicUser(a.userId) || { error: 'no such user' });
});
app.put('/api/auth/profile', (req, res) => {
    const a = resolveRequestAuth(req);
    if (!a) return res.status(401).json({ error: 'unauthorized' });
    try {
        const mgr = getAuthManager(AUTH_DB_DIR);
        const patch = {};
        for (const k of ['firstName', 'lastName', 'aiName']) {
            if (typeof req.body?.[k] === 'string') patch[k] = req.body[k];
        }
        res.json({ success: true, user: mgr.updateUser(a.userId, patch) });
    } catch (e) {
        res.status(400).json({ error: String(e.message || e) });
    }
});

app.post('/api/auth/logout', (req, res) => {
    const auth = req.headers.authorization;
    const token = auth && auth.startsWith('Bearer ') ? auth.substring(7).trim() : null;
    res.json({ ok: token ? getAuthManager(AUTH_DB_DIR).logout(token) : false });
});

app.get('/api/auth/me', (req, res) => {
    const a = resolveRequestAuth(req);
    if (a.rejected) return res.status(401).json({ error: 'invalid or expired session' });
    const mgr = getAuthManager(AUTH_DB_DIR);
    res.json({
        userId: a.userId,
        role: a.role,
        workspaceId: a.workspaceId,
        features: a.features,
        legacy: a.isLegacy,
        account: a.userId ? mgr.publicUser(a.userId) : null,
        usage: {
            cloud: {
                used: mgr.usageToday(a.userId, 'cloud'),
                cap: parseInt(process.env.FOVEAI_CLOUD_DAILY_PER_USER || '50', 10),
            },
        },
    });
});

// Bootstrap: registration is open while zero accounts exist. Afterwards it
// requires an admin session token — OR a valid beta invite code
// (FOVEAI_BETA_CODE in .env). Invite signups always land as members;
// role/features are never taken from the request body on this path.
app.post('/api/auth/register', (req, res) => {
    const mgr = getAuthManager(AUTH_DB_DIR);
    const { username, password, displayName, inviteCode } = req.body || {};
    let viaInvite = false;
    if (mgr.userCount() > 0) {
        const a = resolveRequestAuth(req);
        if (!isSessionAdmin(a, mgr)) {
            const code = (process.env.FOVEAI_BETA_CODE || '').toUpperCase();
            // Case-forgiving compare — mobile keyboards mangle case; the
            // code convention is uppercase letters anyway.
            if (!code || String(inviteCode || '').trim().toUpperCase() !== code) {
                return res.status(403).json({ error: code ? 'invalid beta invite code' : 'registration is closed — an admin must create accounts' });
            }
            viaInvite = true;
        }
    }
    try {
        const user = mgr.createUser(username, password, viaInvite ? { displayName } : { displayName, role: req.body.role, features: req.body.features });
        res.status(201).json({ ok: true, user });
    } catch (e) {
        res.status(400).json({ error: e.message });
    }
});

app.get('/api/auth/users', (req, res) => {
    const mgr = getAuthManager(AUTH_DB_DIR);
    const a = resolveRequestAuth(req);
    if (a.rejected) return res.status(401).json({ error: 'invalid or expired session' });
    if (!isSessionAdmin(a, mgr)) {
        // non-admin sees only their own account
        const self = a.userId && a.userId !== 'anonymous' ? mgr.publicUser(a.userId) : null;
        return res.json({ users: self ? [self] : [] });
    }
    res.json({ users: mgr.listUsers() });
});

app.post('/api/auth/users', (req, res) => {
    const mgr = getAuthManager(AUTH_DB_DIR);
    const a = resolveRequestAuth(req);
    if (a.rejected) return res.status(401).json({ error: 'invalid or expired session' });
    if (!isSessionAdmin(a, mgr)) {
        return res.status(403).json({ error: 'admin role required' });
    }
    const { username, password, displayName, role, features } = req.body || {};
    try {
        const user = mgr.createUser(username, password, { displayName, role, features });
        res.status(201).json({ ok: true, user });
    } catch (e) {
        res.status(400).json({ error: e.message });
    }
});


// ── Image sanity: a stub that *looks* like an upload must be rejected ────
// A canvas snapshot of an empty frame, a 1x1 pixel or a flat colour swatch all
// decode fine and sail past a byte-count check, then render as a broken image.
// This reads real dimensions from the file header and rejects anything too
// small, too thin, or too flat for its pixel count.
function inspectImage(buf, mime) {
    let width = 0, height = 0;
    try {
        if (mime === 'image/png' && buf.length > 24 && buf.readUInt32BE(0) === 0x89504e47) {
            width = buf.readUInt32BE(16); height = buf.readUInt32BE(20);
        } else if (mime === 'image/jpeg') {
            for (let i = 2; i < buf.length - 9;) {
                if (buf[i] !== 0xFF) { i++; continue; }
                const marker = buf[i + 1];
                const len = buf.readUInt16BE(i + 2);
                // SOF0..SOF15 (excluding DHT/DAC/RST) carry the frame size
                if (marker >= 0xC0 && marker <= 0xCF && ![0xC4, 0xC8, 0xCC].includes(marker)) {
                    height = buf.readUInt16BE(i + 5); width = buf.readUInt16BE(i + 7); break;
                }
                i += 2 + len;
            }
        } else if (mime === 'image/webp' && buf.length > 30) {
            const tag = buf.toString('ascii', 12, 16);
            if (tag === 'VP8 ') { width = buf.readUInt16LE(26) & 0x3FFF; height = buf.readUInt16LE(28) & 0x3FFF; }
            else if (tag === 'VP8L') {
                const b = buf.readUInt32LE(21);
                width = (b & 0x3FFF) + 1; height = ((b >> 14) & 0x3FFF) + 1;
            } else if (tag === 'VP8X') {
                width = (buf.readUIntLE(24, 3) & 0xFFFFFF) + 1;
                height = (buf.readUIntLE(27, 3) & 0xFFFFFF) + 1;
            }
        }
    } catch (_) { /* unparseable → treated as invalid below */ }
    const pixels = width * height;
    // Flat images compress absurdly well: real photos/portraits carry far more
    // data than their pixel count. 1/60 bytes-per-pixel is a very low bar.
    const bytesPerPixel = pixels ? buf.length / pixels : 0;
    return { width, height, pixels, bytesPerPixel,
             valid: width >= 64 && height >= 64 && bytesPerPixel >= 1 / 60 };
}

// ── Profile picture ────────────────────────────────────────────────────────
// Uploads land in the user's gallery collection (media/gallery/<user>/) as
// new files — never replacing previously uploaded pictures. One extra
// pointer (profile_picture in auth.json) says which image is current.
const PROFILE_PICTURE_META = 'profile_pictures.json';
app.post('/api/profile/picture', (req, res) => {
    const a = resolveRequestAuth(req);
    if (a.rejected || !a.userId || a.userId === 'anonymous') return res.status(401).json({ error: 'invalid or expired session' });
    const b = req.body || {};
    const dataUrl = String(b.data || '');
    const m = dataUrl.match(/^data:(image\/(png|jpe?g|webp));base64,(.*)$/s);
    if (!m) return res.status(400).json({ error: 'data must be a base64 image dataURL (png/jpg/webp)' });
    const ext = m[1] === 'image/png' ? '.png' : m[1] === 'image/webp' ? '.webp' : '.jpg';
    let buf;
    try { buf = Buffer.from(m[3], 'base64'); } catch (_) { return res.status(400).json({ error: 'bad base64' }); }
    if (!buf || buf.length < 100) return res.status(400).json({ error: 'image too small' });
    if (buf.length > 6 * 1024 * 1024) return res.status(413).json({ error: 'image over 6 MB' });
    const probe = inspectImage(buf, m[1]);
    if (!probe.valid) {
        return res.status(400).json({
            error: probe.width && probe.height
                ? `image rejected: ${probe.width}x${probe.height} is too small or blank (no real picture data)`
                : 'image rejected: could not read image dimensions — the file is not a usable picture',
            width: probe.width, height: probe.height, bytes: buf.length,
        });
    }

    const user = String(a.userId).replace(/[^a-zA-Z0-9_-]/g, '').slice(0, 32) || 'shared';
    const dir = path.join(path.resolve(__dirname, '..'), 'media', 'gallery', user);
    try { fs.mkdirSync(dir, { recursive: true }); } catch (_) {}

    // COLLECT, not replace: each upload becomes a new timestamped file.
    const crypto = require('crypto');
    const id = `${Date.now().toString(36)}-${crypto.randomBytes(3).toString('hex')}`;
    const file = `profile_${id}${ext}`;
    fs.writeFileSync(path.join(dir, file), buf);

    // gallery meta (so it shows up in the user's gallery listing)
    let meta = {};
    try { meta = JSON.parse(fs.readFileSync(path.join(dir, 'gallery.json'), 'utf8')); } catch (_) {}
    meta[file] = new Date().toISOString();
    try { fs.writeFileSync(path.join(dir, 'gallery.json'), JSON.stringify(meta, null, 2)); } catch (_) {}

    // profile_pictures.json — the collection index + which is current
    let pp = { pictures: [], current: null };
    const ppPath = path.join(dir, PROFILE_PICTURE_META);
    try { pp = JSON.parse(fs.readFileSync(ppPath, 'utf8')); } catch (_) {}
    pp.pictures = Array.isArray(pp.pictures) ? pp.pictures : [];
    pp.pictures.push({ file, added: new Date().toISOString(), bytes: buf.length });
    if (!pp.current) pp.current = file;
    // setting a picture explicitly makes it current
    if (b.makeCurrent !== false) pp.current = file;
    try { fs.writeFileSync(ppPath, JSON.stringify(pp, null, 2)); } catch (_) {}

    // Point the account at it (served via the gallery file route)
    const mgr = getAuthManager(AUTH_DB_DIR);
    try {
        mgr.updateUser(user, { profilePicture: `/api/tools/images/file/${encodeURIComponent(file)}` });
    } catch (_) {}

    res.json({ ok: true, file, url: `/api/tools/images/file/${encodeURIComponent(file)}`, total: pp.pictures.length });
});

// ── AI persona portrait (shared across members — one Jen, one face) ───────
const PERSONA_DIR = path.join(path.resolve(__dirname, '..'), 'media', 'gallery', 'ai_persona');
// Select which collected picture is the CURRENT portrait
app.post('/api/profile/picture/select', (req, res) => {
    const a = resolveRequestAuth(req);
    if (a.rejected || !a.userId || a.userId === 'anonymous') return res.status(401).json({ error: 'invalid or expired session' });
    const user = String(a.userId).replace(/[^a-zA-Z0-9_-]/g, '').slice(0, 32) || 'shared';
    const file = path.basename(String((req.body || {}).file || ''));
    const dir = path.join(path.resolve(__dirname, '..'), 'media', 'gallery', user);
    if (!file || !fs.existsSync(path.join(dir, file))) return res.status(404).json({ error: 'picture not in collection' });
    const ppPath = path.join(dir, PROFILE_PICTURE_META);
    let pp = { pictures: [], current: null };
    try { pp = JSON.parse(fs.readFileSync(ppPath, 'utf8')); } catch (_) {}
    pp.current = file;
    if (!Array.isArray(pp.pictures)) pp.pictures = [];
    if (!pp.pictures.some(p => (p.file || p) === file)) pp.pictures.push({ file, added: new Date().toISOString() });
    fs.writeFileSync(ppPath, JSON.stringify(pp, null, 2));
    try {
        getAuthManager(AUTH_DB_DIR).updateUser(user, {
            profilePicture: `/api/tools/images/file/${encodeURIComponent(file)}`,
        });
    } catch (_) {}
    res.json({ ok: true, current: file });
});

app.get('/api/profile/persona_picture/file/:name', (req, res) => {
    const f = path.basename(req.params.name);
    const p = path.join(PERSONA_DIR, f);
    if (!fs.existsSync(p)) return res.status(404).json({ error: 'not found' });
    res.setHeader('Content-Type', path.extname(f) === '.png' ? 'image/png' : path.extname(f) === '.webp' ? 'image/webp' : 'image/jpeg');
    res.setHeader('Cache-Control', 'no-cache');
    fs.createReadStream(p).pipe(res);
});
app.get('/api/profile/persona_picture', (req, res) => {
    let pp = { pictures: [], current: null };
    try { pp = JSON.parse(fs.readFileSync(path.join(PERSONA_DIR, 'profile_pictures.json'), 'utf8')); } catch (_) {}
    // fall back to the shipped still
    if (!pp.current) return res.json({ current: null, url: '/avatars/jen_still.png', total: 0 });
    res.json({ current: pp.current, url: `/api/profile/persona_picture/file/${encodeURIComponent(pp.current)}`, total: pp.pictures.length });
});
app.post('/api/profile/persona_picture', (req, res) => {
    const a = resolveRequestAuth(req);
    if (a.rejected || (a.userId === 'anonymous' && COGNITIVE_MODE !== 'cloud')) {
        return res.status(401).json({ error: 'invalid or expired session' });
    }
    const b = req.body || {};
    const dataUrl = String(b.data || '');
    const m = dataUrl.match(/^data:(image\/(png|jpe?g|webp));base64,(.*)$/s);
    if (!m) return res.status(400).json({ error: 'data must be a base64 image dataURL (png/jpg/webp)' });
    const ext = m[1] === 'image/png' ? '.png' : m[1] === 'image/webp' ? '.webp' : '.jpg';
    let buf;
    try { buf = Buffer.from(m[3], 'base64'); } catch (_) { return res.status(400).json({ error: 'bad base64' }); }
    if (!buf || buf.length < 100) return res.status(400).json({ error: 'image too small' });
    if (buf.length > 6 * 1024 * 1024) return res.status(413).json({ error: 'image over 6 MB' });
    // Same guard as the user portrait: a blank canvas snapshot is not a picture.
    const probe = inspectImage(buf, m[1]);
    if (!probe.valid) {
        return res.status(400).json({
            error: probe.width && probe.height
                ? `image rejected: ${probe.width}x${probe.height} is too small or blank (no real picture data)`
                : 'image rejected: could not read image dimensions — the file is not a usable picture',
            width: probe.width, height: probe.height, bytes: buf.length,
        });
    }
    const crypto = require('crypto');
    fs.mkdirSync(PERSONA_DIR, { recursive: true });
    const file = `persona_${Date.now().toString(36)}-${crypto.randomBytes(3).toString('hex')}${ext}`;
    fs.writeFileSync(path.join(PERSONA_DIR, file), buf);
    // gallery meta for the ai_persona owner so it appears in gallery listings
    let meta = {};
    try { meta = JSON.parse(fs.readFileSync(path.join(PERSONA_DIR, 'gallery.json'), 'utf8')); } catch (_) {}
    meta[file] = new Date().toISOString();
    fs.writeFileSync(path.join(PERSONA_DIR, 'gallery.json'), JSON.stringify(meta, null, 2));
    let pp = { pictures: [], current: null };
    try { pp = JSON.parse(fs.readFileSync(path.join(PERSONA_DIR, 'profile_pictures.json'), 'utf8')); } catch (_) {}
    pp.pictures = Array.isArray(pp.pictures) ? pp.pictures : [];
    pp.pictures.push({ file, added: new Date().toISOString(), bytes: buf.length });
    pp.current = file;
    fs.writeFileSync(path.join(PERSONA_DIR, 'profile_pictures.json'), JSON.stringify(pp, null, 2));
    res.json({ ok: true, file, url: `/api/profile/persona_picture/file/${encodeURIComponent(file)}`, total: pp.pictures.length });
});

// Current profile picture (for the avatar window) — falls back to default
app.get('/api/profile/picture', (req, res) => {
    const a = resolveRequestAuth(req);
    if (a.rejected || !a.userId || a.userId === 'anonymous') return res.status(401).json({ error: 'invalid or expired session' });
    const user = String(a.userId).replace(/[^a-zA-Z0-9_-]/g, '').slice(0, 32) || 'shared';
    const dir = path.join(path.resolve(__dirname, '..'), 'media', 'gallery', user);
    let pp = null;
    try { pp = JSON.parse(fs.readFileSync(path.join(dir, PROFILE_PICTURE_META), 'utf8')); } catch (_) {}
    const mgr = getAuthManager(AUTH_DB_DIR);
    const current = pp?.current || (mgr.publicUser(user)?.profilePicture || '').split('/').pop();
    if (!current) return res.json({ current: null, url: null, total: 0 });
    res.json({ current, url: `/api/tools/images/file/${encodeURIComponent(current)}`, total: pp?.pictures?.length || 0 });
});

app.patch('/api/auth/users/:name', (req, res) => {
    const mgr = getAuthManager(AUTH_DB_DIR);
    const a = resolveRequestAuth(req);
    if (a.rejected) return res.status(401).json({ error: 'invalid or expired session' });
    const target = String(req.params.name || '').toLowerCase();
    const isSelf = a.userId === target;
    const isAdmin = isSessionAdmin(a, mgr);
    if (!isAdmin && !isSelf) return res.status(403).json({ error: 'admin role required' });
    // self-service users may only change displayName/password
    const patch = isAdmin ? (req.body || {}) : { displayName: req.body?.displayName, password: req.body?.password };
    try {
        res.json({ ok: true, user: mgr.updateUser(target, patch) });
    } catch (e) {
        res.status(400).json({ error: e.message });
    }
});

app.delete('/api/auth/users/:name', (req, res) => {
    const mgr = getAuthManager(AUTH_DB_DIR);
    const a = resolveRequestAuth(req);
    if (a.rejected) return res.status(401).json({ error: 'invalid or expired session' });
    if (!isSessionAdmin(a, mgr)) {
        return res.status(403).json({ error: 'admin role required' });
    }
    const target = String(req.params.name || '').toLowerCase();
    if (target === a.userId) return res.status(400).json({ error: 'cannot delete your own account' });
    res.json({ ok: mgr.deleteUser(target) });
});

// ── Feedback + targeted questions ──────────────────────────────────────────
const { getFeedbackStore } = require('./core/feedback');

// User: submit feedback or answer a question. Requires an authenticated
// identity — anonymous posts would be an unmoderated spam channel.
app.post('/api/feedback', (req, res) => {
    const a = resolveRequestAuth(req);
    if (a.rejected) return res.status(401).json({ error: 'invalid or expired session' });
    if (a.userId === 'anonymous') return res.status(401).json({ error: 'authentication required' });
    const { text, questionId } = req.body || {};
    if (!text || !String(text).trim()) return res.status(400).json({ error: 'text required' });
    const fb = getFeedbackStore(AUTH_DB_DIR);
    const r = fb.addResponse(a.userId, String(text).trim(), questionId || null);
    res.status(201).json({ ok: true, id: r.id });
});

// User: questions targeted at them (targets 'all' or their username).
app.get('/api/feedback/questions', (req, res) => {
    const a = resolveRequestAuth(req);
    if (a.rejected) return res.status(401).json({ error: 'invalid or expired session' });
    const fb = getFeedbackStore(AUTH_DB_DIR);
    res.json({ questions: fb.questionsFor(a.userId) });
});

// Admin: create a question for all or selected users.
app.post('/api/feedback/questions', (req, res) => {
    const a = requireAdmin(req, res);
    if (!a) return;
    const { text, targets } = req.body || {};
    if (!text || !String(text).trim()) return res.status(400).json({ error: 'text required' });
    const fb = getFeedbackStore(AUTH_DB_DIR);
    res.status(201).json({ ok: true, question: fb.addQuestion(String(text).trim(), targets, a.userId) });
});

app.get('/api/feedback/questions/all', (req, res) => {
    if (!requireAdmin(req, res)) return;
    const fb = getFeedbackStore(AUTH_DB_DIR);
    res.json({ questions: [...fb.data.questions].reverse() });
});

app.delete('/api/feedback/questions/:id', (req, res) => {
    if (!requireAdmin(req, res)) return;
    const fb = getFeedbackStore(AUTH_DB_DIR);
    res.json({ ok: fb.deleteQuestion(req.params.id) });
});

// Admin: response inbox.
app.get('/api/feedback/responses', (req, res) => {
    if (!requireAdmin(req, res)) return;
    const fb = getFeedbackStore(AUTH_DB_DIR);
    res.json({ responses: fb.listResponses() });
});

app.post('/api/feedback/responses/:id/read', (req, res) => {
    if (!requireAdmin(req, res)) return;
    const fb = getFeedbackStore(AUTH_DB_DIR);
    res.json({ ok: fb.markRead(req.params.id) });
});

// ── BYOK: user-managed cloud keys ──────────────────────────────────────────
// Session-auth only (no anonymous, no legacy bearers — keys belong to people).
function requireSession(req, res) {
    const a = resolveRequestAuth(req);
    if (a.rejected || a.isLegacy || !a.userId || a.userId === 'anonymous') {
        res.status(401).json({ error: 'a signed-in account is required' });
        return null;
    }
    return a;
}

app.get('/api/byok', (req, res) => {
    const a = requireSession(req, res);
    if (!a) return;
    const mgr = getAuthManager(AUTH_DB_DIR);
    res.json({ byok: mgr.getByokPublic(a.userId), providers: Object.keys(BYOK_PROVIDER_URLS) });
});

app.put('/api/byok', (req, res) => {
    const a = requireSession(req, res);
    if (!a) return;
    const mgr = getAuthManager(AUTH_DB_DIR);
    if (!mgr.hasFeature({ role: a.role, features: a.features }, 'byok')) {
        return res.status(403).json({ error: 'byok feature not enabled for this account' });
    }
    const { provider, apiKey, baseUrl, model } = req.body || {};
    if (provider && provider !== 'custom' && !(provider in BYOK_PROVIDER_URLS)) {
        return res.status(400).json({ error: `unknown provider — use one of: ${[...Object.keys(BYOK_PROVIDER_URLS), 'custom'].join(', ')}` });
    }
    try {
        res.json({ ok: true, byok: mgr.setByok(a.userId, { provider, apiKey, baseUrl, model }) });
    } catch (e) {
        res.status(400).json({ error: e.message });
    }
});

app.delete('/api/byok', (req, res) => {
    const a = requireSession(req, res);
    if (!a) return;
    const mgr = getAuthManager(AUTH_DB_DIR);
    res.json({ ok: mgr.deleteByok(a.userId) });
});

// GET /api/setting?key=X — read the LIVE effective value (process.env is the
// running source of truth shared with Commando/Commander writes via POST below).
app.get('/api/setting', (req, res) => {
    const key = String(req.query.key || '');
    if (!key) return res.status(400).json({ error: 'missing key' });
    // Per-user overlay wins for authenticated members; global env otherwise
    const a = resolveRequestAuth(req);
    if (!a.rejected && a.userId !== 'anonymous' && USER_SETTING_KEYS.has(key)) {
        const ov = readSettingsOverlay(a.workspaceId);
        if (ov[key] !== undefined) return res.json({ key, value: ov[key], scope: 'workspace' });
    }
    res.json({ key, value: process.env[key] ?? null, scope: 'global' });
});

app.post('/api/setting', (req, res) => {
    const { key, val } = req.body || {};
    if (!key) return res.status(400).json({ error: 'missing key' });
    // Admin-only for core keys; members write their workspace overlay for
    // the ignition trait keys (trackball dials — self-service).
    const gate = requireAdminOrUserKey(req, res, key);
    if (!gate) return;
    if (!gate.admin) {
        const ov = readSettingsOverlay(gate.workspaceId);
        ov[key] = String(val);
        writeSettingsOverlay(gate.workspaceId, ov);
        // MEMBER writes must NOT rewire the GLOBAL upstream — their
        // effective mode is honored per-request in handleChatCompletion
        // (effMode). (This block previously live-switched config globally,
        // clobbering default.json's upstream on every dial turn.)
        return res.json({ ok: true, key, value: String(val), scope: 'workspace' });
    }
    setEnvVar(key, String(val));
    process.env[key] = String(val);

    // Auto-load new model in LM Studio if key is XRLF_MODEL_LOCAL_ID
    if (key === 'XRLF_MODEL_LOCAL_ID') {
        const modelId = String(val).trim();
        console.log(`[Setting] Switching active local model to ${modelId}...`);
        execFile('lms', ['load', modelId, '--identifier', modelId, '-y'], { timeout: 90000, windowsHide: true }, (err) => {
            if (err) console.warn(`[Setting] Failed to auto-load ${modelId}:`, err.message);
            else console.log(`[Setting] ✅ Successfully loaded ${modelId} in LM Studio.`);
        });
    }

    // Frontend preset: apply atomically (also updates tunnel + VITE_URL + starts Vite)
    if (key === 'XRLF_FRONTEND_UI_PRESET' && ['xr_vessel', '3d_avatar', 'multigate'].includes(String(val))) {
        applyFrontendPreset(String(val));
    }

    // ── Live upstream routing update ──────────────────────────────────
    // When cognitive mode or base URL changes, update the running proxy config
    // so it routes to the correct upstream without needing a restart.
    if (key === 'XRLF_COGNITIVE_MODE' || key === 'XRLF_LOCAL_BASE_URL' || key === 'XRLF_LLM_PROVIDER' || key === 'XRLF_CHAT_PROVIDER') {
        const newMode = (process.env.XRLF_COGNITIVE_MODE || 'local').toLowerCase();
        const newBaseUrl = process.env.XRLF_LOCAL_BASE_URL || '';
        const provider = process.env.XRLF_LLM_PROVIDER || 'xrlf_proxy';

        if (newMode === 'cloud') {
            const cloudUrl = process.env.XRLF_PROXY_TARGET || 'https://ollama.com/v1';
            config.upstream_url = cloudUrl.replace(/\/v1\/?$/, '');
            config._cloud_mode = true;
            config._api_key = process.env.XRLF_PROXY_API_KEY || process.env.OLLAMA_API_KEY || '';
            console.log(`[Setting] Live switch → CLOUD mode, upstream: ${config.upstream_url}`);
        } else {
            // Local mode — route to the correct local server based on provider
            if (provider === 'lmstudio') {
                config.upstream_url = (process.env.XRLF_RUNTIME_URL || 'http://127.0.0.1:8402').replace(/\/v1\/?$/, '');
            } else {
                // xrlf_proxy → XRLF runtime on :8402
                config.upstream_url = (newBaseUrl || 'http://127.0.0.1:8402/v1').replace(/\/v1\/?$/, '');
            }
            config._cloud_mode = false;
            config._api_key = '';
            console.log(`[Setting] Live switch → LOCAL mode (${provider}), upstream: ${config.upstream_url}`);
        }
    }

    res.json({ ok: true, [key]: val });
});

// ── Server info for LAN clients (2026-10-09) ─────────────────────────────
// The ONE truth for "where is the server": live LAN IP + ports, so no client
// ever hardcodes an address. Unity's ConfigLoader calls this at boot via the
// tunnel origin (xarel.net) and switches to the LAN IP for low-latency links.
app.get('/api/server_info', (req, res) => {
    const os = require('os');
    const nets = os.networkInterfaces();
    let lan = null;
    for (const name of Object.keys(nets)) {
        for (const net of nets[name] || []) {
            if (net.family === 'IPv4' && !net.internal) { lan = net.address; break; }
        }
        if (lan) break;
    }
    res.json({
        lan_ip: lan,
        hostname: os.hostname(),
        ws_port: parseInt(process.env.FOVEAI_WS_PORT || '8400', 10),
        soul_port: 8405,
        stt_ws_port: parseInt(process.env.STT_PORT || '8401', 10),
        web_port: parseInt(process.env.VITE_PORT || '5177', 10),
        tunnel: process.env.FOVEAI_TUNNEL_URL || 'https://xarel.net',
    });
});

app.get('/api/env', (req, res) => {
    const envPath = path.resolve(__dirname, '..', '.env');
    const out = {};
    try {
        const raw = fs.readFileSync(envPath, 'utf8');
        for (const line of raw.split(/\r?\n/)) {
            const trimmed = line.trim();
            if (!trimmed || trimmed.startsWith('#') || !trimmed.includes('=')) continue;
            const eq = trimmed.indexOf('=');
            const k = trimmed.slice(0, eq).trim();
            let v = trimmed.slice(eq + 1).trim();
            if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) {
                v = v.slice(1, -1);
            }
            // Mask secrets — the panel only needs presence, not values,
            // and this endpoint is reachable over LAN/tunnel.
            out[k] = /KEY|TOKEN|SECRET|PASS|CREDENTIAL/i.test(k) && v ? '***' : v;
        }
    } catch (e) {
        return res.status(500).json({ error: e.message });
    }
    res.json(out);
});

app.post('/api/toggle', (req, res) => {
    const { name, value } = req.body || {};
    if (!name) return res.status(400).json({ error: 'missing name' });
    const envName = name === 'voice' ? 'XRLF_VOICE_ENABLED' : name === 'mic' ? 'XRLF_MIC_ENABLED' : name;
    setEnvVar(envName, value ? 'true' : 'false');
    res.json({ ok: true, [envName]: value ? 'true' : 'false' });
});

// Server-side subsystem probe — checks run on THIS host (127.0.0.1), so remote
// panels (Quest, LAN browsers) see the PC's true service states instead of
// probing their own localhost.
app.get('/api/subsystems', async (req, res) => {
    const net = require('net');
    const tcpCheck = (port, timeout = 800) => new Promise(resolve => {
        const sock = new net.Socket();
        let done = false;
        const finish = ok => { if (!done) { done = true; try { sock.destroy(); } catch (_) {} resolve(ok); } };
        sock.setTimeout(timeout);
        sock.once('connect', () => finish(true));
        sock.once('timeout', () => finish(false));
        sock.once('error', () => finish(false));
        try { sock.connect(port, '127.0.0.1'); } catch (_) { finish(false); }
    });
    const httpCheck = async (port, p, timeout = 1500) => {
        try {
            const r = await fetch(`http://127.0.0.1:${port}${p}`, { signal: AbortSignal.timeout(timeout) });
            let body = null;
            try { body = await r.json(); } catch (_) {}
            return { ok: r.ok || r.status === 302, status: r.status, body };
        } catch (_) { return { ok: false, status: 0, body: null }; }
    };
    const checks = [
        { group: 'stack',   name: 'Proxy',            port: 8400, http: '/health' },
        { group: 'stack',   name: 'Dashboard',        port: 8414, http: '/api/status' },
        { group: 'stack',   name: 'XRLF Runtime',     port: 8402, http: '/health' },
        { group: 'stack',   name: 'WS IPC',           port: 8403 },
        { group: 'stack',   name: 'Soul / Compagent', port: 8405, http: '/health' },
        { group: 'stack',   name: 'TTS (Kokoro)',     port: 8411, http: '/health' },
        { group: 'stack',   name: 'Chat Relay',       port: 8413, http: '/health' },
        { group: 'stack',   name: 'Creative / Dream', port: 8412, http: '/health' },
        { group: 'stack',   name: 'STT (Whisper)',    port: 8401 },
        { group: 'stack',   name: 'Body / Motor',     port: 8410, http: '/health' },
        { group: 'stack',   name: 'Subconscious',     port: 8409, http: '/health' },
        { group: 'stack',   name: 'LM Studio',        port: 1234, http: '/v1/models' },
        { group: 'web',     name: 'XR Vessel',        port: 5176, http: '/' },
        { group: 'web',     name: 'FoveAI Web',       port: 5177, http: '/' },
        { group: 'remote',  name: 'noVNC Desktop',    port: 6080 },
        { group: 'remote',  name: 'Remote Web (Guac)',port: 6081 },
        { group: 'remote',  name: 'guacd',            port: 4822 },
        { group: 'remote',  name: 'xrdp',             port: 3389 },
        { group: 'remote',  name: 'Sunshine',         port: 47990 },
        { group: 'machine', name: 'Netdata',          port: 19999, http: '/' },
    ];
    const results = await Promise.all(checks.map(async c => {
        const out = { name: c.name, port: c.port, group: c.group };
        if (!(await tcpCheck(c.port))) { out.state = 'offline'; return out; }
        if (!c.http) { out.state = 'listening'; return out; }
        const h = await httpCheck(c.port, c.http);
        out.state = h.ok ? 'online' : 'dormant';
        out.http_status = h.status;
        if (c.port === 8402 && h.body) {
            out.model = h.body.model;
            out.loaded = h.body.loaded;
            out.load_state = h.body.load_state;
            out.load_error = h.body.load_error;
        }
        return out;
    }));
    res.json({ host: '127.0.0.1', checks: results });
});

app.post('/api/route', (req, res) => {
    const { mode } = req.body || {};
    if (!['cloud', 'local'].includes(mode)) return res.status(400).json({ error: 'mode must be cloud or local' });

    // Atomic .env update for route switch (do not restart proxy from inside itself)
    if (mode === 'local') {
        setEnvVar('XRLF_COGNITIVE_MODE', 'local');
        setEnvVar('XRLF_CHAT_PROVIDER', 'lm_studio');
        setEnvVar('XRLF_LOCAL_BASE_URL', 'http://127.0.0.1:1234/v1');
        setEnvVar('XRLF_RUNTIME_URL', 'http://127.0.0.1:8402');
        setEnvVar('LOCAL_LLM_BASE', 'http://127.0.0.1:1234');
        process.env.XRLF_COGNITIVE_MODE = 'local';
        process.env.XRLF_CHAT_PROVIDER = 'lm_studio';
        process.env.XRLF_LOCAL_BASE_URL = 'http://127.0.0.1:1234/v1';
        process.env.XRLF_RUNTIME_URL = 'http://127.0.0.1:8402';
        process.env.LOCAL_LLM_BASE = 'http://127.0.0.1:1234';
    } else {
        setEnvVar('XRLF_COGNITIVE_MODE', 'cloud');
        setEnvVar('XRLF_CHAT_PROVIDER', 'ollama_cloud');
        process.env.XRLF_COGNITIVE_MODE = 'cloud';
        process.env.XRLF_CHAT_PROVIDER = 'ollama_cloud';
    }

    res.json({ ok: true, mode });
});

app.post('/api/fovea', (req, res) => {
    let { level } = req.body || {};
    if (typeof level === 'string') level = parseInt(level, 10);
    if (typeof level !== 'number' || isNaN(level) || level < 0 || level > 5) return res.status(400).json({ error: 'level must be 0-5 (0=auto, 1=minimal, 5=maximum)' });

    setEnvVar('XRLF_PROXY_AGGRESSION', String(level));
    process.env.XRLF_PROXY_AGGRESSION = String(level);
    res.json({ ok: true, level });
});

app.post('/api/cap', (req, res) => {
    const { cap } = req.body || {};
    if (typeof cap !== 'number' || cap < 0) return res.status(400).json({ error: 'cap must be >= 0' });
    setEnvVar('XRLF_CLOUD_MAX_TOKENS_CAP', String(cap));
    res.json({ ok: true, cap });
});

app.post('/api/preserve', (req, res) => {
    const { preserve } = req.body || {};
    if (typeof preserve !== 'number' || preserve < 0 || preserve > 100) return res.status(400).json({ error: 'preserve must be 0-100' });
    setEnvVar('XRLF_CLOUD_PRESERVE_LAST', String(preserve));
    process.env.XRLF_CLOUD_PRESERVE_LAST = String(preserve);
    res.json({ ok: true, preserve });
});

app.post('/api/control', (req, res) => {
    const { action } = req.body || {};
    const allowed = ['start-stack', 'stop-stack', 'open-tray', 'open-terminal', 'open-debug-terminal', 'show-meter', 'unload-lm', 'restart-local', 'open-quick-controls', 'open-corner-companion', 'open-topbar', 'restart-proxy', 'test-news-impulse', 'start-vite', 'start-xrlf-runtime', 'start-xrlf', 'stop-xrlf', 'launch-xr', 'check-xr', 'load-tier-a', 'load-tier-b', 'unload-residency'];
    if (!allowed.includes(action)) return res.status(400).json({ error: 'unknown action' });

    const repoRoot = path.resolve(__dirname, '..', '..');
    const foveaiDir = path.resolve(__dirname, '..');  // FoveAI/ directory (parent of foveated-memory)
    const venvPython = IS_LINUX
        ? path.join(foveaiDir, '.venv', 'bin', 'python')
        : path.join(foveaiDir, '.venv', 'Scripts', 'python.exe');
    const sendOk = () => res.json({ ok: true, action });
    const sendErr = (err) => res.status(500).json({ error: err?.message || String(err) });

    // ── XRLF runtime lifecycle (Linux) ──────────────────────────────
    // The runtime is owned by foveai-xrlf.service (systemd --user,
    // Restart=always). ALL start/stop/restart goes through systemctl so
    // cgroup tracking applies. Previously we pkill'd + detached-spawned
    // run_xrlf.py ourselves — that produced un-tracked processes that
    // fought the VRAM guardrail and left zombie runtimes with no model.
    const xrlfCtl = (verb, done) => {
        // Kill un-tracked strays first (their cgroup isn't the unit's, so
        // systemctl can't see them), then hand lifecycle to systemd.
        execFile('pkill', ['-f', 'run_xrlf.py'], () => {
            execFile('systemctl', ['--user', verb, 'foveai-xrlf'], (err) => done(err || null));
        });
    };

    // Cold-start with a non-default model: systemd loads the unit's default,
    // then we hot-swap via /load once /health reports loaded.
    const xrlfDeferredHotSwap = (model, port = 8402) => {
        const base = p => String(p).split(/[\\/]/).pop().replace(/\.xrlf$/i, '');
        const defaultModel = process.env.XRLF_MODEL_LOCAL_ID || 'gemma-4-e2b-multimodal-v1.0.xrlf';
        if (base(model) === base(defaultModel)) return;  // unit already loads this
        const resolved = String(model).includes('/') ? model : `xrl_encoded/${model}`;
        let tries = 0;
        const iv = setInterval(() => {
            if (++tries > 90) { clearInterval(iv); return; }
            fetch(`http://127.0.0.1:${port}/health`, { timeout: 3000 })
                .then(r => r.json())
                .then(h => {
                    if (h.loaded) {
                        clearInterval(iv);
                        console.log(`[xrlf] Cold-start swap → ${resolved}`);
                        fetch(`http://127.0.0.1:${port}/load`, {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({model: resolved}),
                            timeout: 120000,
                        }).catch(e => console.warn('[xrlf] deferred swap failed:', e.message));
                    } else if (h.load_state === 'error') {
                        clearInterval(iv);
                        console.warn(`[xrlf] load_state=error before swap: ${h.load_error}`);
                    }
                })
                .catch(() => {});
        }, 4000);
    };

    switch (action) {
        case 'start-stack':
            if (IS_LINUX) {
                const child = spawn('bash', [path.join(foveaiDir, 'sleipnir_launcher.sh')], {
                    cwd: foveaiDir,
                    detached: true,
                    stdio: 'ignore'
                });
                child.on('error', (err) => { if (!res.headersSent) sendErr(err); });
                child.unref();
                sendOk();
            } else {
                execFile('C:\\Windows\\System32\\cmd.exe', ['/c', 'start', '/min', '', 'node', 'sleipnir_launcher.js'], {
                    cwd: repoRoot,
                    windowsHide: true,
                    detached: true
                }, (err) => err ? sendErr(err) : sendOk());
            }
            break;
        case 'stop-stack':
            if (IS_LINUX) {
                execFile('bash', [path.join(foveaiDir, 'sleipnir_launcher.sh'), '--stop'], { cwd: foveaiDir }, (err) => err ? sendErr(err) : sendOk());
            } else {
                runPwsh(`Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*sleipnir_launcher.js*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }`, (err) => err ? sendErr(err) : sendOk());
            }
            break;
        case 'open-tray':
            // Taskbar lives in FoveAI/ — not FoveAI root
            if (IS_LINUX) {
                execFile(venvPython, [path.join(foveaiDir, 'FoveAI_Taskbar_Linux.py')], { cwd: foveaiDir, detached: true, stdio: 'ignore' }, (err) => err ? sendErr(err) : sendOk());
            } else {
                execFile('C:\\Windows\\System32\\cmd.exe', ['/c', 'start', '', path.join(foveaiDir, 'FoveAI_Taskbar.pyw')], { windowsHide: true }, (err) => err ? sendErr(err) : sendOk());
            }
            break;
        case 'open-terminal':
            if (IS_LINUX) {
                execFile('xdg-terminal-exec', ['-d', repoRoot], (err) => {
                    if (err) execFile('gnome-terminal', ['--working-directory', repoRoot], (e2) => e2 ? sendErr(e2) : sendOk());
                    else sendOk();
                });
            } else {
                execFile(WT_EXE, ['new-tab', '--profile', 'XRLF Super Memory', '-d', repoRoot], { windowsHide: true }, (err) => err ? sendErr(err) : sendOk());
            }
            break;
        case 'open-debug-terminal':
            if (IS_LINUX) {
                execFile('xdg-terminal-exec', ['-d', repoRoot, '--title', 'XRLF Debug'], (err) => {
                    if (err) execFile('gnome-terminal', ['--working-directory', repoRoot, '--title', 'XRLF Debug'], (e2) => e2 ? sendErr(e2) : sendOk());
                    else sendOk();
                });
            } else {
                execFile(WT_EXE, ['new-tab', '--profile', 'XRLF Super Memory', '-d', repoRoot, '--title', 'XRLF Debug'], { windowsHide: true }, (err) => err ? sendErr(err) : sendOk());
            }
            break;
        case 'show-meter':
            if (IS_LINUX) {
                execFile(venvPython, [path.join(foveaiDir, 'health_monitor.py'), '--watch'], { cwd: foveaiDir, detached: true, stdio: 'ignore' }, (err) => err ? sendErr(err) : sendOk());
            } else {
                runPwsh('Import-Module XRLFMemory; Show-MemoryMeter', (err) => err ? sendErr(err) : sendOk());
            }
            break;
        case 'unload-lm':
            if (IS_LINUX) {
                // Unload XRLF model via POST to the runtime on :8402
                fetch('http://127.0.0.1:8402/unload', { method: 'POST', timeout: 5000 })
                    .then(() => sendOk())
                    .catch(e => sendErr(e));
            } else {
                fetch('http://127.0.0.1:1234/v1/models', { timeout: 5000 })
                    .then(r => r.json())
                    .then(data => Promise.all((data.data || []).map(m =>
                        fetch(`http://127.0.0.1:1234/v1/models/${m.id}/unload`, { method: 'POST', timeout: 5000 })
                    )))
                    .then(() => sendOk())
                    .catch(e => sendErr(e));
            }
            break;
        case 'restart-local':
            if (IS_LINUX) {
                // systemd owns the runtime — restart the unit (kills cgroup,
                // respawns with Restart=always). pkill inside xrlfCtl sweeps
                // any un-tracked strays first.
                xrlfCtl('restart', (err) => err ? sendErr(err) : sendOk());
            } else {
                runPwsh('Restart-Service -Name "LMStudio*" -Force -ErrorAction SilentlyContinue', (err) => err ? sendErr(err) : sendOk());
            }
            break;
        case 'load-tier-a':
            if (IS_LINUX) {
                execFile(venvPython, ['-m', 'runtime.residency', 'load', 'A'], { cwd: foveaiDir }, (err) => err ? sendErr(err) : sendOk());
            } else {
                sendOk();
            }
            break;
        case 'load-tier-b':
            if (IS_LINUX) {
                execFile(venvPython, ['-m', 'runtime.residency', 'load', 'B'], { cwd: foveaiDir }, (err) => err ? sendErr(err) : sendOk());
            } else {
                sendOk();
            }
            break;
        case 'unload-residency':
            if (IS_LINUX) {
                execFile(venvPython, ['-m', 'runtime.residency', 'unload'], { cwd: foveaiDir }, (err) => err ? sendErr(err) : sendOk());
            } else {
                sendOk();
            }
            break;
        case 'open-quick-controls':
        case 'open-corner-companion':
            // Corner Companion = always-on-top mini chat window in bottom-right corner
            {
                const companionPy = path.join(foveaiDir, 'Tools', 'foveai_corner_companion', 'foveai_corner_companion.py');
                if (IS_LINUX) {
                    execFile(venvPython, [companionPy], { cwd: foveaiDir, detached: true, stdio: 'ignore' }, (err) => err ? sendErr(err) : sendOk());
                } else {
                    execFile('C:\\Windows\\System32\\cmd.exe', ['/c', 'start', '', venvPython, companionPy], { windowsHide: true }, (err) => err ? sendErr(err) : sendOk());
                }
            }
            break;
        case 'open-topbar':
            // TopBar = full-width bar across top of screen with avatar, volume, menus
            {
                const topBarExe = path.join(foveaiDir, 'Tools', 'foveai_top_bar', 'dist', 'LumaxTopBar.exe');
                const topBarPy = path.join(foveaiDir, 'Tools', 'foveai_top_bar', 'foveai_top_bar.py');
                if (IS_LINUX) {
                    execFile(venvPython, [topBarPy], { cwd: foveaiDir, detached: true, stdio: 'ignore' }, (err) => err ? sendErr(err) : sendOk());
                } else if (fs.existsSync(topBarExe)) {
                    execFile(topBarExe, [], { windowsHide: true, detached: true }, (err) => err ? sendErr(err) : sendOk());
                } else {
                    execFile('C:\\Windows\\System32\\cmd.exe', ['/c', 'start', '', venvPython, topBarPy], { windowsHide: true }, (err) => err ? sendErr(err) : sendOk());
                }
            }
            break;
        case 'restart-proxy':
            sendOk();
            setTimeout(() => {
                // Under systemd (INVOCATION_ID set) Restart=always brings us
                // back. Launched manually (nohup/double-click) nothing would —
                // so respawn ourselves first, then exit.
                if (!process.env.INVOCATION_ID) {
                    try {
                        const child = spawn(process.execPath, [__filename], {
                            cwd: __dirname, detached: true, stdio: 'ignore', env: process.env,
                        });
                        child.unref();
                    } catch (e) {
                        console.error('[restart-proxy] self-respawn failed:', e.message);
                    }
                }
                process.exit(0);
            }, 500);
            break;
        case 'test-news-impulse':
            if (IS_LINUX) {
                execFile(venvPython, [path.join(repoRoot, 'Backend', 'Cognition', 'SituationalAwarenessDaemon.py'), '--test-run'], { cwd: repoRoot }, (err) => err ? sendErr(err) : sendOk());
            } else {
                execFile('C:\\Windows\\System32\\cmd.exe', ['/c', 'python', path.join(repoRoot, 'Backend', 'Cognition', 'SituationalAwarenessDaemon.py'), '--test-run'], { windowsHide: true }, (err) => err ? sendErr(err) : sendOk());
            }
            break;
        case 'start-vite':
            startViteServer('multigate');
            sendOk();
            break;
        case 'start-xrlf-runtime': {
            // Start XRLF runtime with the configured model using venv Python.
            const xrlfRuntimeModel = (process.env.XRLF_MODEL_LOCAL_ID || (IS_LINUX ? 'gemma-4-e2b-multimodal-v1.0.xrlf' : 'foveai-omni-router-v2.xrlf'));
            // On Linux, run_xrlf.py expects the full path relative to FoveAI dir
            const xrlfModelPath = IS_LINUX ? `xrl_encoded/${xrlfRuntimeModel}` : xrlfRuntimeModel;
            const xrlfRuntimePort = 8402;
            const xrlfRuntimeWs = 8403;
            if (IS_LINUX) {
                // systemd owns the runtime — restart is idempotent whether the
                // unit is up or dead, and gives us cgroup-clean teardown.
                xrlfCtl('restart', (err) => {
                    if (err) return sendErr(err);
                    xrlfDeferredHotSwap(xrlfModelPath, xrlfRuntimePort);
                    sendOk(); // frontend polls /health
                });
            } else {
                execFile('C:\\Windows\\System32\\cmd.exe',
                    ['/c', 'start', '/min', '', venvPython, 'run_xrlf.py', '--model', xrlfRuntimeModel, '--port', String(xrlfRuntimePort), '--ws-port', String(xrlfRuntimeWs)],
                    { cwd: foveaiDir, windowsHide: true, detached: true },
                    (err) => err ? sendErr(err) : sendOk()
                );
            }
            break;
        }
        case 'start-xrlf': {
            // Start XRLF runtime with a specific model.
            // If the runtime is already alive on :8402, hot-swap via /load (no process restart,
            // no port conflict). Only kill+restart if the runtime is down or /load fails.
            const xrlfModel = req.body.model || (IS_LINUX ? 'qwopus3.5-9b-coder-mtp-moq.xrlf' : 'foveai-omni-router-v2.xrlf');
            const xrlfPort = req.body.port || 8402;
            const xrlfWsPort = req.body.ws_port || 8403;

            // Step 1: Check if runtime is already alive — hot-swap instead of kill+restart
            fetch(`http://127.0.0.1:${xrlfPort}/health`, { timeout: 3000 })
                .then(hr => hr.json())
                .then(h => {
                    console.log(`[start-xrlf] Runtime alive (model=${h.model}). Hot-swapping to ${xrlfModel}…`);
                    return fetch(`http://127.0.0.1:${xrlfPort}/load`, {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({model: xrlfModel}),
                        timeout: 120000,
                    });
                })
                .then(r => {
                    console.log(`[start-xrlf] Hot-swap response: ${r.status}`);
                    sendOk();
                })
                .catch(err => {
                    // Runtime is down — restart the systemd unit (clean cgroup
                    // teardown + auto-respawn), then deferred hot-swap if the
                    // requested model isn't the unit default.
                    console.log(`[start-xrlf] Runtime not responding (${err.message}). Full restart…`);
                    if (IS_LINUX) {
                        xrlfCtl('restart', (ctlErr) => {
                            if (ctlErr) return sendErr(ctlErr);
                            sendOk();
                            xrlfDeferredHotSwap(xrlfModel, xrlfPort);
                        });
                    } else {
                        runPwsh(`taskkill /F /T /IM python.exe /FI "WINDOWTITLE eq run_xrlf*" 2>$null; Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*run_xrlf.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }`, () => {
                            const portCheckCmd = `for ($i=0; $i -lt 15; $i++) { $c1 = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -eq ${xrlfPort} }; $c2 = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -eq ${xrlfWsPort} }; if (-not $c1 -and -not $c2) { Write-Output 'PORTS_FREE'; break }; Start-Sleep -Seconds 1 }`;
                            runPwsh(portCheckCmd, () => {
                                setTimeout(() => {
                                    sendOk();
                                    execFile('C:\\Windows\\System32\\cmd.exe',
                                        ['/c', 'start', '/min', '', venvPython, 'run_xrlf.py', '--model', xrlfModel, '--port', String(xrlfPort), '--ws-port', String(xrlfWsPort)],
                                        { cwd: foveaiDir, windowsHide: true, detached: true }
                                    );
                                }, 3000);
                            });
                        });
                    }
                });
            break;
        }
        case 'stop-xrlf': {
            // Kill all XRLF runtime processes — frees VRAM
            // Respond immediately; the frontend polls the health endpoint to confirm
            if (IS_LINUX) {
                // Stop the unit AND sweep strays — systemctl stop alone can't
                // see manually-spawned run_xrlf processes.
                execFile('systemctl', ['--user', 'stop', 'foveai-xrlf'], () => {
                    execFile('pkill', ['-f', 'run_xrlf.py'], (err) => {
                        if (err) console.warn('[stop-xrlf] Kill command error:', err.message);
                    });
                });
            } else {
                runPwsh(`Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*run_xrlf.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }`, (err) => {
                    if (err) console.warn('[stop-xrlf] Kill command error:', err.message);
                });
            }
            sendOk();
            break;
        }
        case 'launch-xr':
            // XR Vessel runs on :5176 — separate port from Multigate (:5177)
            startViteServer('xr_vessel');
            setEnvVar('XRLF_FRONTEND_UI', 'xr_vessel');
            sendOk();
            break;
        case 'check-xr':
            // Check if XR Vessel is available on disk
            const xrDir = path.resolve(__dirname, '..', 'Frontend', 'XR_Vessel');
            const xrAvailable = fs.existsSync(path.join(xrDir, 'package.json'));
            res.json({ ok: true, xrAvailable, xrDir });
            break;
    }
});

// ── Process-level crash protection ──────────────────────────────────────────
// Prevents NSSM watchdog restart loops: log errors but keep the process alive.

process.on('uncaughtException', (err) => {
    console.error(`[Fovea] uncaughtException (suppressed):`, err.message);
    console.error(err.stack || err);
});

process.on('unhandledRejection', (reason, promise) => {
    console.error(`[Fovea] unhandledRejection (suppressed):`, reason);
});

// ── Tools: personal image gallery ──────────────────────────────────────────
// Mounted just before server start. Gallery files live under
// /media/gallery/<user>/ in the FoveAI repo; user is taken from the fvs_
// session when present, else a shared folder. Auth: same session check the
// other /api surfaces use (open to authenticated sessions, blocked otherwise
// via the standard route wrapper ordering).
const { createGalleryRouter, createAIRouter } = require('./tools_gallery.api.js');
app.use('/api/tools', createGalleryRouter({
    galleryRoot: path.join(path.resolve(__dirname, '..'), 'media', 'gallery'),
    getUser: (req) => {
        const a = resolveRequestAuth(req);
        return (a && !a.rejected && a.userId !== 'anonymous') ? { username: a.userId } : null;
    }
}));

app.use('/api/tools/ai', createAIRouter({
    galleryRoot: path.join(path.resolve(__dirname, '..'), 'media', 'gallery')
}));

// ── Start ───────────────────────────────────────────────────────────────────

const _server = http.createServer(app);
_server.on('connect', (req, clientSocket, head) => {
    logDebug(`\n[${new Date().toISOString()}] Caught HTTP CONNECT request for ${req.url}! Express ignored this, causing a hang.\n`);
    clientSocket.write('HTTP/1.1 400 Bad Request\r\n\r\nTransparent proxy does not support CONNECT tunnels.');
    clientSocket.end();
});

const PROXY_HOST = process.env.FOVEAI_PROXY_HOST || '0.0.0.0';
_server.listen(config.proxy_port, PROXY_HOST, () => {
    console.log(`✅ Foveated Memory Proxy listening on http://${PROXY_HOST}:${config.proxy_port}`);
    console.log(`   → Point your client at: http://localhost:${config.proxy_port}/v1/chat/completions\n`);

    // ── Memory Continuity: restore previous session state ──────────────
    try {
        const snapshot = loadContinuity();
        if (snapshot && snapshot.sessionId) {
            console.log(`[Continuity] 🔄 Previous session found: ${snapshot.sessionId}`);
            console.log(`[Continuity]    Last activity: ${snapshot.timestamp}`);
            console.log(`[Continuity]    Messages: ${snapshot.messageCount || 'unknown'}`);
            console.log(`[Continuity]    Model: ${snapshot.model || 'unknown'}`);
        } else {
            console.log('[Continuity] ℹ️ No previous session state found — fresh start');
        }
    } catch (e) {
        console.warn('[Continuity] Failed to load continuity state:', e.message);
    }

    // --- Optional Public Tunnel ---
    if (process.env.XRLF_ENABLE_TUNNEL === 'true' || config.enable_public_tunnel === true) {
        console.log(`\n[Tunnel] Starting public localtunnel on port ${config.proxy_port}...`);
        const { spawn } = require('child_process');
        const tunnelCmd = `npx -y localtunnel --port ${config.proxy_port}`;
        const tunnel = spawn(tunnelCmd, { shell: true });

        tunnel.stdout.on('data', data => {
            const out = data.toString().trim();
            if (out) console.log(`[Tunnel] ${out}`);
        });
        tunnel.stderr.on('data', data => {
            const err = data.toString().trim();
            if (err) console.error(`[Tunnel Error] ${err}`);
        });
    }

    // Log upstream status
    console.log(`[Startup] Upstream LLM endpoint target: ${config.upstream_url}`);

    // Query runtime's actual n_ctx (after safety-net cap) for accurate injection planning
    getRuntimeContextWindow().then(ctx => {
        if (ctx > 0) console.log(`[Startup] Runtime context window: ${ctx} tokens (safety-net aware)`);
        else console.log(`[Startup] Runtime context window: unreachable — using heuristic fallback`);
    });
    // Refresh every 30s to catch runtime restarts or model swaps
    setInterval(() => { getRuntimeContextWindow(); }, RUNTIME_CTX_TTL_MS);
});

const _dashboardServer = dashboardApp.listen(DASHBOARD_PORT, PROXY_HOST, () => {
    console.log(`🖥️  Foveated Memory Dashboard on http://${PROXY_HOST}:${DASHBOARD_PORT}/memory`);
});

// Allow immediate restart after a crash/kill by reusing the port during TIME_WAIT.
_server.on('connection', (socket) => { /* no-op for typing */ });
_server.on('listening', () => {
    if (_server.address()) {
        _server.setMaxListeners(0);
    }
});

// Handle EADDRINUSE gracefully — exit 0 so NSSM watchdog can cleanly restart
_server.on('error', (err) => {
    if (err.code === 'EADDRINUSE') {
        console.error(`[Fovea] Port ${config.proxy_port} already in use — exiting gracefully for watchdog restart.`);
        process.exit(0);
    } else {
        console.error(`[Fovea] Server error:`, err);
    }
});

// ── Ecological Context Background Worker (Cron Sweeper) ─────────────────────
// Circuit breaker: tracks consecutive failures to avoid hammering a dead endpoint
let _ecoWorkerConsecutiveFailures = 0;
const _ECO_WORKER_MAX_FAILURES = 3;  // skip sweep after this many consecutive connection failures

async function runEcologicalContextWorker() {
    try {
        if (!SUMMARIZER_ENABLED) return;

        // Circuit breaker: if the summarizer has been unreachable for several sweeps, back off
        if (_ecoWorkerConsecutiveFailures >= _ECO_WORKER_MAX_FAILURES) {
            // Try a lightweight pre-flight ping to see if the endpoint is back
            const titleEndpoint = SUMMARIZER_ENDPOINT.replace(/\/v1\/?$/, '') + '/v1/chat/completions';
            try {
                const ping = await fetch(titleEndpoint.replace('/chat/completions', ''), {
                    method: 'GET',
                    signal: AbortSignal.timeout(3000)
                });
                // Endpoint is responsive again — reset circuit breaker
                _ecoWorkerConsecutiveFailures = 0;
                console.log(`[EcologicalWorker] Summarizer endpoint back online — resuming sweeps`);
            } catch (_) {
                // Still dead — skip this sweep entirely (log once, not per-session)
                console.log(`[EcologicalWorker] Summarizer still unreachable (${_ecoWorkerConsecutiveFailures} consecutive failures) — skipping sweep`);
                return;
            }
        }

        const memoryDataDir = path.join(__dirname, 'memory_data');
        let subdirs = [];
        try {
            subdirs = fs.readdirSync(memoryDataDir).filter(name => {
                try { return fs.statSync(path.join(memoryDataDir, name)).isDirectory() && name !== 'checkpoints'; }
                catch { return false; }
            });
        } catch (_) {}

        const workspaceIds = Array.from(new Set(['XRLF', 'default', config.workspace_id, ...subdirs]));
        let connectionFailed = false;  // trip on first connection error to abort sweep

        for (const wsId of workspaceIds) {
            if (connectionFailed) break;
            const s = getStore(wsId);
            const sessions = await s.listSessions(100);
            for (const sess of sessions) {
                if (connectionFailed) break;
                const sId = sess.session_id;
                const turnCount = sess.count || sess.turn_count || 0;
                const cleanT = (sess.title || '').replace(/^["'\s]+|["'\s]+$/g, '').trim();

                // 1. Delete useless stub/junk sessions (<= 2 turns)
                if (turnCount <= 2) {
                    console.log(`[EcologicalWorker] Pruning 1-2 turn stub session: ${sId}`);
                    await s.deleteSession(sId);
                    continue;
                }

                // 2. Refresh condition: missing/bad title, missing keywords, OR topic drift (every 12 turns since last title refresh)
                const isBadTitle = !cleanT || cleanT.length <= 4 || /^(the|a|an|in|on|untitled|session|session #\w+)$/i.test(cleanT) || cleanT.endsWith('...') || cleanT.toLowerCase().startsWith('the ');
                const lastTitledTurn = sess.last_titled_turn || 0;
                const turnsSinceLastTitle = turnCount - lastTitledTurn;
                const isDrifted = turnsSinceLastTitle >= 12;

                if (!isBadTitle && sess.keywords && !isDrifted) continue;

                try {
                    let msgs = await s.getBySession(sId);
                    if (msgs.length > 0) {
                        const recentMsgs = msgs.slice(-10).map(m => m.role + ': ' + (typeof m.content === 'string' ? m.content.slice(0, 300) : '')).join('\n');
                        const prompt = `Analyze this chat snippet (last 10 turns of session) and return metadata in EXACT FORMAT:
TITLE: <3-6 word clear, descriptive summary title of what was accomplished or discussed>
THEME: <Code|Architecture|UI|General>
PROJECT: <Project or workspace name, e.g. XRLF, Jenna, Extension, or General>
KEYWORDS_ROW1: <3-4 key topic tags, e.g. #WebXR #FoveatedMemory #VSCode>
KEYWORDS_ROW2: <3-4 key issue/action tags, e.g. #FixSessionTitles #KeywordRows #UIEnhancement>

Snippet:
${recentMsgs}`;
                        const titleEndpoint = SUMMARIZER_ENDPOINT.replace(/\/v1\/?$/, '') + '/v1/chat/completions';
                        const r = await withLocalUpstream(() => fetch(titleEndpoint, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            signal: AbortSignal.timeout(15000),  // 15s timeout per request
                            body: JSON.stringify({
                                model: SUMMARIZER_MODEL,
                                messages: [{ role: 'user', content: prompt }],
                                temperature: Math.max(SUMMARIZER_TEMP, 0.2),
                                max_tokens: Math.min(SUMMARIZER_MAX_TOKENS, 140),
                                // Bare utility call — no soul injection, no memory
                                // persistence; sweep titling must not pollute
                                // session history or persona state
                                xrlf_utility: true,
                                xrlf_headless: true,
                                xrlf_thinking: false
                            })
                        }));
                        if (r.ok) {
                            _ecoWorkerConsecutiveFailures = 0;  // reset on success
                            const data = await r.json();
                            let raw = data.choices?.[0]?.message?.content || '';
                            raw = raw.replace(/<think>[\s\S]*?<\/think>/gi, '').trim();

                            let title = (raw.match(/TITLE:\s*([^\n]+)/i)?.[1] || raw.split('\n')[0] || '').replace(/^["'\s]+|["'\s]+$/g, '').trim();
                            title = title.replace(/[◆◇■□●○★☆▲▼#*_`]/g, '').trim().replace(/^(the|a|an)\s+/i, '');
                            if (!title || title.length <= 3) title = 'Untitled Session';
                            let theme = (raw.match(/THEME:\s*([^\n]+)/i)?.[1] || 'General').trim();
                            let project = (raw.match(/PROJECT:\s*([^\n]+)/i)?.[1] || wsId || 'XRLF').trim();
                            let kw1 = (raw.match(/KEYWORDS_ROW1:\s*([^\n]+)/i)?.[1] || '').trim();
                            let kw2 = (raw.match(/KEYWORDS_ROW2:\s*([^\n]+)/i)?.[1] || '').trim();
                            let keywords = [kw1, kw2].filter(Boolean).join('\n');

                            await s.setSessionMeta(sId, {
                                title,
                                keywords,
                                keywords_row1: kw1,
                                keywords_row2: kw2,
                                theme,
                                project,
                                last_titled_turn: turnCount
                            });
                            console.log(`[EcologicalWorker] ${isDrifted ? 'Drift refreshed' : 'Retitled'} ${sId} @ turn ${turnCount} -> "${title}"`);
                        }
                    }
                    // Gentle throttle delay (1.5 seconds) between background generations to prevent GPU/CPU spikes
                    await new Promise(r => setTimeout(r, 1500));
                } catch (e) {
                    // Connection-level failures (ECONNREFUSED, timeout, fetch failed) → trip circuit breaker, abort sweep
                    const errStr = `${e.message || ''} ${e.cause?.message || ''} ${e.cause?.code || ''}`;
                    const isConnectionError = /ECONNREFUSED|ENOTFOUND|ETIMEDOUT|abort|timeout|fetch failed/i.test(errStr);
                    if (isConnectionError) {
                        _ecoWorkerConsecutiveFailures++;
                        console.warn(`[EcologicalWorker] Summarizer unreachable — aborting sweep (failure #${_ecoWorkerConsecutiveFailures}): ${e.message}`);
                        connectionFailed = true;
                    } else {
                        console.warn(`[EcologicalWorker] Title generation failed for ${sId}: ${e.message}`);
                    }
                }
            }
        }
    } catch (e) {
        console.warn(`[EcologicalWorker] Sweeper error: ${e.message}`);
    }
}

// Start ecological context sweeper (runs 5s after start, then every 3 minutes)
setTimeout(runEcologicalContextWorker, 5000);
setInterval(runEcologicalContextWorker, 180000);


// ── Workspace file API ──────────────────────────────────────────────────────
// Powers the Multigate Vibe IDE tab (and any agent tool surface). Every path
// resolves inside FILES_ROOT — the repo root by default — or is refused;
// symlinks are realpath-checked so nothing escapes the workspace. Gated by
// the 'tools' feature, the same tier the jenna-vscode extension uses.
const FILES_ROOT = fs.realpathSync(process.env.FOVEAI_FILES_ROOT || path.resolve(__dirname, '..'));
const FILES_MAX_READ = 4 * 1024 * 1024;    // 4MB read cap
const FILES_MAX_WRITE = 8 * 1024 * 1024;   // 8MB write cap

// Resolves rel against FILES_ROOT and verifies the real path stays inside.
// For existing paths, realpath the target itself; for new paths (write/mkdir),
// walk up to the nearest existing ancestor and realpath that. Returns the
// absolute path or null when the request escapes the root.
async function resolveWorkspacePath(rel) {
    if (typeof rel !== 'string') return null;
    const abs = path.resolve(FILES_ROOT, rel.replace(/^[/\\]+/, ''));
    if (abs !== FILES_ROOT && !abs.startsWith(FILES_ROOT + path.sep)) return null;
    try {
        const real = await fs.promises.realpath(abs);
        return (real === FILES_ROOT || real.startsWith(FILES_ROOT + path.sep)) ? abs : null;
    } catch {
        let cur = path.dirname(abs);
        while (cur.startsWith(FILES_ROOT)) {
            try {
                const real = await fs.promises.realpath(cur);
                return (real === FILES_ROOT || real.startsWith(FILES_ROOT + path.sep)) ? abs : null;
            } catch { cur = path.dirname(cur); }
        }
        return null;
    }
}

// GET /api/files/tree?path=<rel> — one directory level: dirs first, then files.
app.get('/api/files/tree', requireFeature('tools'), async (req, res) => {
    const abs = await resolveWorkspacePath(req.query.path || '');
    if (!abs) return res.status(403).json({ error: 'path outside workspace' });
    try {
        const entries = await fs.promises.readdir(abs, { withFileTypes: true });
        const out = [];
        for (const e of entries) {
            if (e.name === '.git' || e.name === 'node_modules' || e.name === '__pycache__') continue;
            try {
                const st = await fs.promises.stat(path.join(abs, e.name));
                out.push({
                    name: e.name,
                    type: e.isDirectory() ? 'dir' : 'file',
                    size: e.isDirectory() ? null : st.size,
                    mtime: st.mtime.toISOString(),
                });
            } catch { /* vanished between readdir/stat — skip */ }
        }
        out.sort((a, b) => (a.type === b.type ? a.name.localeCompare(b.name) : a.type === 'dir' ? -1 : 1));
        res.json({ root: FILES_ROOT, path: path.relative(FILES_ROOT, abs) || '.', entries: out });
    } catch (e) {
        res.status(e.code === 'ENOTDIR' || e.code === 'ENOENT' ? 404 : 500).json({ error: e.message });
    }
});

// GET /api/files/read?path=<rel> — utf8 text file, 4MB cap, binary refused.
app.get('/api/files/read', requireFeature('tools'), async (req, res) => {
    const abs = await resolveWorkspacePath(req.query.path);
    if (!abs) return res.status(403).json({ error: 'path outside workspace' });
    try {
        const st = await fs.promises.stat(abs);
        if (st.isDirectory()) return res.status(400).json({ error: 'path is a directory' });
        if (st.size > FILES_MAX_READ) return res.status(413).json({ error: `file too large (${st.size} bytes, cap ${FILES_MAX_READ})` });
        const buf = await fs.promises.readFile(abs);
        if (buf.subarray(0, 8192).includes(0)) return res.status(415).json({ error: 'binary file — not editable as text' });
        res.json({ path: path.relative(FILES_ROOT, abs), content: buf.toString('utf8'), size: st.size, mtime: st.mtime.toISOString() });
    } catch (e) {
        res.status(e.code === 'ENOENT' ? 404 : 500).json({ error: e.message });
    }
});

// POST /api/files/write {path, content} — creates parent dirs, utf8 overwrite.
app.post('/api/files/write', requireFeature('tools'), async (req, res) => {
    const { path: rel, content } = req.body || {};
    const abs = await resolveWorkspacePath(rel);
    if (!abs) return res.status(403).json({ error: 'path outside workspace' });
    if (typeof content !== 'string') return res.status(400).json({ error: 'content must be a string' });
    const bytes = Buffer.byteLength(content, 'utf8');
    if (bytes > FILES_MAX_WRITE) return res.status(413).json({ error: `content too large (${bytes} bytes, cap ${FILES_MAX_WRITE})` });
    try {
        await fs.promises.mkdir(path.dirname(abs), { recursive: true });
        await fs.promises.writeFile(abs, content, 'utf8');
        const st = await fs.promises.stat(abs);
        res.json({ ok: true, path: path.relative(FILES_ROOT, abs), size: st.size, mtime: st.mtime.toISOString() });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

// POST /api/files/mkdir {path} — recursive directory create.
app.post('/api/files/mkdir', requireFeature('tools'), async (req, res) => {
    const abs = await resolveWorkspacePath(req.body?.path);
    if (!abs) return res.status(403).json({ error: 'path outside workspace' });
    try {
        await fs.promises.mkdir(abs, { recursive: true });
        res.json({ ok: true, path: path.relative(FILES_ROOT, abs) });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

// ── Creative Engine pass-through (:8412) ──────────────────────────────────
// /api/dream (+ catalog, preheat, upscale) belong to foveai-creative.
// The image editor posts from any Multigate surface; same-origin proxy.
const CREATIVE_URL = process.env.FOVEAI_CREATIVE_URL || 'http://127.0.0.1:8412';
const creativeProxy = async (req, res) => {
    const target = CREATIVE_URL + req.url;
    try {
        const upstream = await fetch(target, {
            method: req.method,
            headers: { 'Content-Type': 'application/json' },
            body: ['GET', 'HEAD'].includes(req.method) ? undefined : JSON.stringify(req.body || {}),
            signal: AbortSignal.timeout(600000),
        });
        const buf = Buffer.from(await upstream.arrayBuffer());
        res.status(upstream.status).type(upstream.headers.get('content-type') || 'application/json').send(buf);
    } catch (e) {
        res.status(502).json({ error: `creative engine unreachable: ${e.message}` });
    }
};
app.all('/api/dream*', creativeProxy);          // /api/dream, /api/dream/catalog
app.post('/api/preheat', creativeProxy);
app.post('/api/upscale/display', creativeProxy);

// ── Transformative State Drive (TSD) · Photonic Znake & 1,000-Pentahedron Legion ──
app.get('/tsd', (req, res) => {
    res.sendFile(path.join(__dirname, 'public', 'tsd_blaster.html'));
});

app.all('/api/tsd/:action', (req, res) => {
    const action = req.params.action;
    const repoRoot = path.resolve(__dirname, '..');
    const pyBin = path.join(repoRoot, '.venv', 'bin', 'python');
    const prompt = (req.body && req.body.prompt) || (req.query && req.query.prompt) || 'Verify 1,000 Virtual Pentahedrons on TSD';

    let pyCode = '';
    if (action === 'status') {
        pyCode = 'import json; from runtime.xrl_swarm import get_tsd_motherboard; mb=get_tsd_motherboard(); print(json.dumps({"status":"ok","telemetry":mb.telemetry(),"biosphere":mb.biosphere_scale_hierarchy()}))';
    } else if (action === 'seek-and-destroy') {
        pyCode = 'import json; from runtime.xrl_swarm import get_tsd_motherboard; mb=get_tsd_motherboard(); r=mb.seek_and_destroy_tasks(); r.pop("lightshow",None); r["telemetry"]=mb.telemetry(); print(json.dumps(r))';
    } else if (action === 'dream-2036') {
        pyCode = 'import json; from runtime.xrl_swarm import get_tsd_motherboard; mb=get_tsd_motherboard(); print(json.dumps(mb.dream_cycle_evolution()))';
    } else if (action === 'legion') {
        pyCode = 'import json, sys; from runtime.xrl_swarm import get_tsd_motherboard; mb=get_tsd_motherboard(); r=mb.legion_countermodel(sys.argv[1]); r["telemetry"]=mb.telemetry(); print(json.dumps(r))';
    } else if (action === 'rejuvenate') {
        pyCode = 'import json; from runtime.repo_youth_engine import RepoYouthEngine; print(json.dumps(RepoYouthEngine().rejuvenate()))';
    } else if (action === 'benchmark') {
        pyCode = 'import json; from runtime.benchmark_tsd_legion import run_comprehensive_benchmark; print(json.dumps(run_comprehensive_benchmark()))';
    } else {
        return res.status(404).json({ error: `Unknown TSD action: ${action}` });
    }

    execFile(
        pyBin,
        ['-c', pyCode, prompt],
        { cwd: repoRoot, env: { ...process.env, PYTHONPATH: repoRoot }, timeout: 30000 },
        (err, stdout, stderr) => {
            if (err) {
                return res.status(500).json({ error: err.message, stderr: stderr ? stderr.slice(0, 500) : '' });
            }
            try {
                const lines = stdout.trim().split('\n');
                const jsonLine = lines[lines.length - 1];
                res.json(JSON.parse(jsonLine));
            } catch (parseErr) {
                res.json({ raw_output: stdout, stderr });
            }
        }
    );
});

