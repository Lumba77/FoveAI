/**
 * lumax-solver.js — Repo Manager Edition v3
 *
 * 6-tier fallback: KB (instant) → 9B local → 12B local → Ollama Cloud (deepseek-v4) → Gemini Flash → Cloudflare (opt-in)
 * Repo-aware: reads git state, skeleton file tree, atomic multi-file patches.
 * Modes: interactive | --pipe | --watch | --serve (local saviour daemon) | --dry-run
 *
 * Usage:
 *   node lumax-solver.js [--repo <path>] [--test <cmd>] [--watch] [--commit] [--dry-run] [--pipe]
 *
 * Exit codes:  0=success  1=LLM failed  2=parse failure  3=user aborted  4=tests failed post-patch
 */

import fs from 'fs';
import os from 'os';
import path from 'path';
import { execSync, spawn } from 'child_process';
import readline from 'readline';
import { fileURLToPath } from 'url';

// ─── CLI Parsing ──────────────────────────────────────────────────────────────
const argv = process.argv.slice(2);
const flag  = (f) => argv.includes(f);
const flagVal = (f) => { const i = argv.indexOf(f); return i !== -1 ? argv[i + 1] : null; };

const PIPE_MODE    = flag('--pipe');
const WATCH_MODE   = flag('--watch');
const SERVE_MODE   = flag('--serve');
const SERVICE_MODE = flag('--service');  // OS service: HTTP + all guarded repos + log tailers
const DRY_RUN      = flag('--dry-run');
const AUTO_COMMIT  = flag('--commit');
const HELP_MODE    = flag('--help') || flag('-h');
const REPO_PATH    = path.resolve(flagVal('--repo') || process.cwd());
const TEST_CMD     = flagVal('--test');
const SERVE_PORT   = parseInt(process.env.LUMAX_SERVE_PORT || flagVal('--port') || '8113', 10);
const NON_INTERACTIVE = PIPE_MODE || WATCH_MODE || SERVE_MODE || SERVICE_MODE;

if (HELP_MODE) {
    console.log(`
🛸 Lumax Solver — Repo Manager Edition v3

Usage:
  node lumax-solver.js [options]

Options:
  --repo <path>   Target repository directory (default: current directory)
  --test <cmd>    Run this command after applying fixes to validate them
  --watch         Daemon mode: monitor repo, auto-fix errors with LLM
  --serve         Local Saviour: run as HTTP service (port 8113) — other services POST errors here
  --port <n>      Override serve port (default 8113)
  --commit        Auto git-commit if tests pass after fix
  --dry-run       Preview proposed changes without applying anything
  --pipe          Read error log from stdin (scripted/CI use)
  --help          Show this help

Local Saviour permission model:
  Auto-apply is OFF by default. Enable it once:
    node lumax-solver.js --serve --enable-auto-apply
  Or set in ~/.lumax/config.json:  { "autoApplyEnabled": true }

Environment variables:
  GEMINI_API_KEY      Google Gemini key
  GOOGLE_API_KEY      Alias for GEMINI_API_KEY
  OLLAMA_API_KEY      Ollama Cloud key
  LUMAX_WORKER_URL    Cloudflare Worker URL

Config file (~/.lumax/config.json):
  { "geminiApiKey": "...", "ollamaApiKey": "...", "workerUrl": "..." }

Exit codes:
  0  Success
  1  All LLM channels failed
  2  Unrecoverable JSON parse failure
  3  User aborted
  4  Tests failed after applying patch
`);
    process.exit(0);
}

// ─── Constants ────────────────────────────────────────────────────────────────
const CONFIG_PATH        = path.join(os.homedir(), '.lumax', 'config.json');
const WATCH_LOG          = path.join(REPO_PATH, '.lumax', 'solver-watch.log');
const BACKUP_DIR         = path.join(REPO_PATH, '.lumax', 'solver-backups');

// Gemini (cheap tier — Flash first, then 1.5 as fallback)
const GEMINI_BASE        = 'https://generativelanguage.googleapis.com/v1beta/models';
const GEMINI_FLASH       = 'gemini-2.0-flash';
const GEMINI_CHEAP       = 'gemini-1.5-flash';

// Ollama Cloud (primary cloud — DeepSeek V4 Pro)
const OLLAMA_CLOUD_URL   = 'https://api.ollama.com/v1/chat/completions';
const OLLAMA_CLOUD_MODEL = 'deepseek-v4-pro';

// Local models — 4B Fast Coder (Qwen): fast specialist | 12B Gemma: deep reasoning
const LOCAL_9B_PATH     = process.env.LUMAX_9B_MODEL ||
    loadConfig().model9bPath ||
    'C:\\Users\\danie\\.cache\\huggingface\\hub\\kaitchup\\Qwen3.5-4B-GGUF-MoQ\\MoQ-3.5.gguf';
const LOCAL_12B_PATH    = process.env.LUMAX_12B_MODEL ||
    loadConfig().model12bPath ||
    'C:\\Users\\danie\\.cache\\huggingface\\hub\\w-ahmad\\Gemma-4-12B-it-qat-GGUF-MoQ\\MoQ-3.5.gguf';
const LLAMA_PORT_9B     = 8765;  // 9B Coder — primary local
const LLAMA_PORT_12B    = 8766;  // 12B Gemma — deep reasoning

const IGNORE_DIRS = new Set(['node_modules', '.git', '.venv', '.svelte-kit', 'build', 'dist', '__pycache__', '.lumax']);

const SYSTEM_PROMPT =
    'You are Lumax Solver, an expert software repair agent. You receive a repo snapshot and an error log. ' +
    'Return ONLY a single raw JSON object (no markdown fences) with exactly these keys:\n' +
    '  "chatResponse": string — explain what is wrong and what you are doing\n' +
    '  "fileEdits": array of { "filePath": string, "content": string } — complete new file contents\n' +
    '  "commands": array of strings — shell commands to run after file edits\n' +
    'Paths in fileEdits must be relative to the repo root. Do not invent new paths.';

// ─── Config Helpers ───────────────────────────────────────────────────────────
function loadConfig() {
    if (fs.existsSync(CONFIG_PATH)) {
        try { return JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf-8')); } catch (_) {}
    }
    return {};
}

function saveConfig(updates) {
    try {
        fs.mkdirSync(path.dirname(CONFIG_PATH), { recursive: true });
        const cfg = Object.assign(loadConfig(), updates);
        fs.writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2), 'utf-8');
        console.log(`💾 Config saved to ${CONFIG_PATH}`);
    } catch (e) { console.warn(`⚠️ Could not save config: ${e.message}`); }
}

function loadGeminiKey() {
    if (process.env.GEMINI_API_KEY) return process.env.GEMINI_API_KEY.trim();
    if (process.env.GOOGLE_API_KEY)  return process.env.GOOGLE_API_KEY.trim();
    return loadConfig().geminiApiKey?.trim() || null;
}

function loadOllamaKey() {
    if (process.env.OLLAMA_API_KEY) return process.env.OLLAMA_API_KEY.trim();
    return loadConfig().ollamaApiKey?.trim() || null;
}

function loadWorkerUrl() {
    if (process.env.LUMAX_WORKER_URL) return process.env.LUMAX_WORKER_URL.trim().replace(/\/$/, '');
    return loadConfig().workerUrl?.trim().replace(/\/$/, '') || null;
}

// ─── Prompt Helper ────────────────────────────────────────────────────────────
function makePrompt() {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    const ask = (q) => new Promise((res) => rl.question(q, res));
    return { rl, ask };
}

// ─── Git Helpers ──────────────────────────────────────────────────────────────
function runGit(args, cwd = REPO_PATH) {
    try {
        return execSync(`git ${args}`, { cwd, encoding: 'utf-8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
    } catch (_) { return null; }
}

function isGitRepo(dir) {
    return fs.existsSync(path.join(dir, '.git'));
}

// ─── Repo Context Engine ──────────────────────────────────────────────────────
function extractSkeleton(filePath) {
    // Lightweight signature extractor — signatures + imports, no bodies
    // Keeps file content token-efficient for LLM context
    try {
        const ext  = path.extname(filePath).toLowerCase();
        const text = fs.readFileSync(filePath, 'utf-8');
        const lines = text.split('\n');
        const KEEP = /^(import|from|export|def |class |async def |function |const |let |var |interface |type |@)/;
        const skeleton = lines
            .filter(l => KEEP.test(l.trim()) || l.trim().startsWith('//') || l.trim().startsWith('#'))
            .slice(0, 60)  // cap at 60 signature lines per file
            .join('\n');
        return skeleton || '(binary or empty)';
    } catch (_) { return '(unreadable)'; }
}

function walkTree(dir, depth = 0, maxDepth = 4) {
    if (depth > maxDepth) return [];
    const entries = [];
    try {
        const items = fs.readdirSync(dir, { withFileTypes: true });
        for (const item of items) {
            if (IGNORE_DIRS.has(item.name)) continue;
            const full = path.join(dir, item.name);
            const rel  = path.relative(REPO_PATH, full);
            if (item.isDirectory()) {
                entries.push({ type: 'dir', path: rel });
                entries.push(...walkTree(full, depth + 1, maxDepth));
            } else {
                entries.push({ type: 'file', path: rel });
            }
        }
    } catch (_) {}
    return entries;
}

function buildRepoContext(errorLog) {
    console.log(`\n📂 Building repo context for: ${REPO_PATH}`);
    const tree = walkTree(REPO_PATH);
    const fileList = tree.filter(e => e.type === 'file').map(e => e.path);

    // Extract skeletons only for files likely relevant to the error
    const errorWords = new Set(
        (errorLog || '').split(/\W+/).filter(w => w.length > 3)
    );
    const relevantFiles = fileList.filter(f => {
        const base = path.basename(f, path.extname(f)).toLowerCase();
        return [...errorWords].some(w => base.includes(w.toLowerCase())) || fileList.length < 20;
    }).slice(0, 15);  // max 15 skeletons to keep token count sane

    const skeletons = {};
    for (const f of relevantFiles) {
        skeletons[f] = extractSkeleton(path.join(REPO_PATH, f));
    }

    const git = isGitRepo(REPO_PATH) ? {
        branch:  runGit('branch --show-current'),
        status:  runGit('status --short'),
        commits: runGit('log --oneline -8'),
    } : null;

    // Read package.json / pyproject.toml for project type
    const meta = {};
    for (const mf of ['package.json', 'pyproject.toml', 'requirements.txt', 'Cargo.toml']) {
        const mp = path.join(REPO_PATH, mf);
        if (fs.existsSync(mp)) {
            try { meta[mf] = fs.readFileSync(mp, 'utf-8').slice(0, 800); } catch (_) {}
        }
    }

    console.log(`  📁 ${fileList.length} files found | 🧬 ${relevantFiles.length} skeletons extracted`);
    if (git) console.log(`  🌿 Branch: ${git.branch} | Changes: ${(git.status || 'clean').split('\n').length}`);

    return { fileList, skeletons, git, meta };
}

// ─── Fetch with Retry ─────────────────────────────────────────────────────────
async function fetchWithRetry(url, options, retries = 2, timeoutMs = 25000) {
    for (let attempt = 1; attempt <= retries; attempt++) {
        try {
            const resp = await fetch(url, { ...options, signal: AbortSignal.timeout(timeoutMs) });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            return resp;
        } catch (err) {
            if (attempt === retries) throw err;
            const wait = attempt * 1500;
            console.log(`  ↩ Retry ${attempt}/${retries - 1} in ${wait}ms… (${err.message})`);
            await new Promise(r => setTimeout(r, wait));
        }
    }
}

// ─── Safe JSON Extraction ─────────────────────────────────────────────────────
function safeParseJSON(raw) {
    let text = raw.replace(/```json|```/gi, '').trim();
    try { return JSON.parse(text); } catch (_) {}
    const match = text.match(/\{[\s\S]*\}/);
    if (match) { try { return JSON.parse(match[0]); } catch (_) {} }
    const idx = text.indexOf('{');
    if (idx > 0) { try { return JSON.parse(text.slice(idx)); } catch (_) {} }
    return null;
}

// ─── Crash Dump ───────────────────────────────────────────────────────────────
function writeCrashDump(errorLog, lastError) {
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    const p = path.join(REPO_PATH, `lumax-solver-FAILED-${stamp}.json`);
    try { fs.writeFileSync(p, JSON.stringify({ timestamp: stamp, errorLog, lastError }, null, 2)); console.error(`📁 Crash dump: ${p}`); }
    catch (_) {}
}

// ─── Path Guard ───────────────────────────────────────────────────────────────
function isSafePath(filePath) {
    const abs = path.resolve(REPO_PATH, filePath);
    return abs.startsWith(REPO_PATH + path.sep) || abs === REPO_PATH;
}

// ─── Atomic Patch Engine ──────────────────────────────────────────────────────
function showDiffPreview(fileEdits) {
    console.log('\n📋 Proposed changes:');
    for (const edit of fileEdits) {
        const abs = path.resolve(REPO_PATH, edit.filePath);
        const exists = fs.existsSync(abs);
        const oldLines = exists ? fs.readFileSync(abs, 'utf-8').split('\n').length : 0;
        const newLines = (edit.content || '').split('\n').length;
        const delta = newLines - oldLines;
        const sign = delta >= 0 ? `+${delta}` : `${delta}`;
        console.log(`  ${exists ? '📝' : '🆕'} ${edit.filePath}  (${sign} lines)`);
    }
}

function applyPatchesAtomic(fileEdits) {
    // 1. Backup originals
    const backups = [];
    fs.mkdirSync(BACKUP_DIR, { recursive: true });
    const stamp = Date.now();

    for (const edit of fileEdits) {
        if (!isSafePath(edit.filePath)) {
            console.warn(`⛔ [GUARD] Rejected unsafe path: ${edit.filePath}`);
            continue;
        }
        const abs = path.resolve(REPO_PATH, edit.filePath);
        if (fs.existsSync(abs)) {
            const bak = path.join(BACKUP_DIR, `${stamp}-${edit.filePath.replace(/[/\\]/g, '_')}`);
            fs.cpSync(abs, bak);
            backups.push({ abs, bak });
        }
    }

    // 2. Apply all
    const applied = [];
    try {
        for (const edit of fileEdits) {
            if (!isSafePath(edit.filePath)) continue;
            const abs = path.resolve(REPO_PATH, edit.filePath);
            fs.mkdirSync(path.dirname(abs), { recursive: true });
            fs.writeFileSync(abs, edit.content, 'utf-8');
            applied.push(edit.filePath);
            console.log(`  ✍️  Patched: ${edit.filePath}`);
        }
        return { applied, backups };
    } catch (err) {
        // 3. Rollback on partial failure
        console.error(`\n💥 Patch write failed: ${err.message}. Rolling back...`);
        for (const { abs, bak } of backups) {
            try { fs.cpSync(bak, abs); console.log(`  ⏪ Restored: ${abs}`); } catch (_) {}
        }
        throw err;
    }
}

function rollbackPatches(backups) {
    for (const { abs, bak } of backups) {
        try { fs.cpSync(bak, abs); console.log(`  ⏪ Rolled back: ${path.relative(REPO_PATH, abs)}`); } catch (_) {}
    }
}

function runTestCmd(cmd) {
    console.log(`\n🧪 Running: ${cmd}`);
    try {
        execSync(cmd, { cwd: REPO_PATH, stdio: 'inherit' });
        console.log('  ✅ Tests passed.');
        return true;
    } catch (_) {
        console.error('  ❌ Tests failed.');
        return false;
    }
}

function gitCommit(message, files) {
    try {
        for (const f of files) execSync(`git add "${f}"`, { cwd: REPO_PATH });
        execSync(`git commit -m "${message}"`, { cwd: REPO_PATH, stdio: 'inherit' });
        console.log(`  ✅ Committed: ${message}`);
    } catch (e) {
        console.warn(`  ⚠️ Git commit failed: ${e.message}`);
    }
}

// ─── LLM Tier 4: Gemini API (cheap tier) ──────────────────────────────────────
async function tryGemini(apiKey, context, terminalLog) {
    for (const model of [GEMINI_FLASH, GEMINI_CHEAP]) {
        console.log(`\n✨ [Tier 4] Gemini — ${model}...`);
        try {
            const url = `${GEMINI_BASE}/${model}:generateContent?key=${apiKey}`;
            const resp = await fetchWithRetry(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    systemInstruction: { parts: [{ text: SYSTEM_PROMPT }] },
                    contents: [{
                        role: 'user',
                        parts: [{ text: buildLLMPayload(context, terminalLog) }],
                    }],
                    generationConfig: { temperature: 0.1, responseMimeType: 'application/json' },
                }),
            }, 2, 35000);
            const result = await resp.json();
            if (result.error) {
                const msg = result.error.message || '';
                if (model === GEMINI_FLASH && (msg.includes('not found') || msg.includes('quota') || msg.includes('PERMISSION_DENIED'))) {
                    console.log(`  ⚡ Flash quota/unavailable — trying 1.5...`); continue;
                }
                throw new Error(`Gemini API: ${msg}`);
            }
            const text = result?.candidates?.[0]?.content?.parts?.[0]?.text;
            if (!text) throw new Error('Empty Gemini response');
            const parsed = safeParseJSON(text);
            if (parsed) { console.log(`  ✅ Gemini (${model}) answered.`); return parsed; }
            throw new Error('Gemini JSON parse failed');
        } catch (err) {
            if (model === GEMINI_FLASH) throw err;
            console.log(`  ⚠️ ${model}: ${err.message} — downgrading...`);
        }
    }
}

// ─── LLM Tier 3: Ollama Cloud (DeepSeek V4 Pro) ───────────────────────────────
async function tryOllamaCloud(ollamaKey, context, terminalLog) {
    console.log(`\n🧠 [Tier 3] Ollama Cloud — ${OLLAMA_CLOUD_MODEL}...`);
    const resp = await fetchWithRetry(OLLAMA_CLOUD_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${ollamaKey}` },
        body: JSON.stringify({
            model: OLLAMA_CLOUD_MODEL,
            messages: [
                { role: 'system', content: SYSTEM_PROMPT },
                { role: 'user',   content: buildLLMPayload(context, terminalLog) },
            ],
            temperature: 0.1,
            stream: false,
        }),
    }, 2, 25000);
    const result = await resp.json();
    const parsed = safeParseJSON(result.choices[0].message.content);
    if (parsed) { console.log('  ✅ Ollama Cloud answered.'); return parsed; }
    throw new Error('Ollama Cloud JSON parse failed');
}

// ─── LLM Local GGUF Factory ────────────────────────────────────────────────
// One factory serves both the 9B coder and 12B Gemma — same protocol, different ports.
const _llamaProcs = {};  // { port: ChildProcess }

function findLlamaBinary() {
    const candidates = [
        'llama-server', 'llama-server.exe',
        'C:\\llama.cpp\\llama-server.exe',
        path.join(os.homedir(), 'llama.cpp', 'llama-server.exe'),
    ];
    for (const b of candidates) {
        try { execSync(`"${b}" --version`, { stdio: 'ignore' }); return b; } catch (_) {}
    }
    return null;
}

async function ensureLlamaServer(modelPath, port, label) {
    const healthUrl = `http://127.0.0.1:${port}/health`;
    const chatUrl   = `http://127.0.0.1:${port}/v1/chat/completions`;

    // Already running?
    try {
        const probe = await fetch(healthUrl, { signal: AbortSignal.timeout(1200) });
        if (probe.ok) { console.log(`  🟢 ${label} server already running on :${port}`); return chatUrl; }
    } catch (_) {}

    // Auto-spawning disabled to prevent choking the PC with background servers
    if (process.env.LUMAX_ALLOW_SPAWN_LLAMA !== 'true') {
        throw new Error(`${label} server on :${port} is offline (auto-spawning disabled to protect PC memory)`);
    }

    // File check
    if (!fs.existsSync(modelPath)) throw new Error(`Model not found: ${modelPath}`);

    // Binary
    const binary = findLlamaBinary();
    if (!binary) throw new Error('llama-server not found in PATH or C:\\llama.cpp\\');

    // GPU layer heuristic based on model size
    const sizeGB = fs.statSync(modelPath).size / (1024 ** 3);
    const gpuLayers = sizeGB < 4 ? 35 : sizeGB < 6 ? 28 : 20;  // fewer layers offloaded for larger models

    console.log(`  🚀 Spawning llama-server [${label}] on :${port} (${sizeGB.toFixed(1)}GB, ${gpuLayers} GPU layers)...`);
    _llamaProcs[port] = spawn(binary, [
        '--model',       modelPath,
        '--port',        String(port),
        '--ctx-size',    '4096',
        '--n-gpu-layers', String(gpuLayers),
        '--no-mmap',
    ], { stdio: 'ignore', detached: false });

    // Wait up to 60s for ready
    for (let i = 0; i < 60; i++) {
        await new Promise(r => setTimeout(r, 1000));
        try {
            const probe = await fetch(healthUrl, { signal: AbortSignal.timeout(800) });
            if (probe.ok) { console.log(`  ✅ ${label} ready.`); return chatUrl; }
        } catch (_) {}
    }
    throw new Error(`${label} server failed to start within 60s`);
}

async function queryLocalModel(chatUrl, context, terminalLog, label, timeoutMs = 90000) {
    const resp = await fetchWithRetry(chatUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            model: 'local',
            messages: [
                { role: 'system', content: SYSTEM_PROMPT },
                { role: 'user',   content: buildLLMPayload(context, terminalLog) },
            ],
            temperature: 0.1,
        }),
    }, 1, timeoutMs);
    const result = await resp.json();
    const parsed = safeParseJSON(result?.choices?.[0]?.message?.content || '');
    if (parsed) { console.log(`  ✅ ${label} answered.`); return parsed; }
    throw new Error(`${label} JSON parse failed`);
}

// Tier 1 — 4B Fast Coder: fast, coding-specialized (first LLM attempt)
async function tryLocal9B(context, terminalLog) {
    const label = `4B Qwen Coder (${path.basename(LOCAL_9B_PATH)})`;
    console.log(`\n⚡ [Tier 1] ${label}...`);
    const chatUrl = await ensureLlamaServer(LOCAL_9B_PATH, LLAMA_PORT_9B, '4B Qwen');
    return queryLocalModel(chatUrl, context, terminalLog, label, 60000);
}

// Tier 2 — 12B Gemma: deep reasoning / planning mode for complex problems
async function tryLocal12B(context, terminalLog) {
    const label = `12B Gemma (${path.basename(LOCAL_12B_PATH)})`;
    console.log(`\n🧠 [Tier 2] ${label} (deep analysis)...`);
    const chatUrl = await ensureLlamaServer(LOCAL_12B_PATH, LLAMA_PORT_12B, '12B Gemma');
    return queryLocalModel(chatUrl, context, terminalLog, label, 120000);
}

// ─── LLM Tier 5: Cloudflare Worker (pay-as-you-go, opt-in) ────────────────────
async function tryCloudflare(workerUrl, context, terminalLog) {
    console.log(`\n☁️  [Tier 5] Cloudflare Worker (opt-in)...`);
    const resp = await fetchWithRetry(`${workerUrl}/api/solve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            systemPrompt: SYSTEM_PROMPT,
            payload: buildLLMPayload(context, terminalLog),
        }),
    }, 2, 20000);
    const result = await resp.json();
    const parsed = safeParseJSON(result?.response || result?.text || '');
    if (parsed) { console.log('  ✅ Cloudflare Worker answered.'); return parsed; }
    throw new Error('Cloudflare Worker JSON parse failed');
}

// ─── LLM Payload Builder ──────────────────────────────────────────────────────
function buildLLMPayload(context, terminalLog) {
    const parts = [];
    parts.push(`## Repo: ${REPO_PATH}`);
    if (context.git) {
        parts.push(`## Git Branch: ${context.git.branch}`);
        parts.push(`## Git Status:\n${context.git.status || '(clean)'}`);
        parts.push(`## Recent Commits:\n${context.git.commits || '(none)'}`);
    }
    if (Object.keys(context.meta).length) {
        for (const [k, v] of Object.entries(context.meta)) {
            parts.push(`## ${k}:\n${v}`);
        }
    }
    parts.push(`## File Tree (${context.fileList.length} files):\n${context.fileList.join('\n')}`);
    if (Object.keys(context.skeletons).length) {
        parts.push('## Relevant File Skeletons:');
        for (const [f, skel] of Object.entries(context.skeletons)) {
            parts.push(`### ${f}\n${skel}`);
        }
    }
    parts.push(`## Error Log:\n${terminalLog}`);
    return parts.join('\n\n');
}

// ─── Librarian Bridge ──────────────────────────────────────────────────────────
// Queries the TerminalLibrarian (Python) for relevant shell history, error patterns,
// and past fix suggestions. Returns enriched context string or empty string.
function queryLibrarian(errorLog) {
    const libPath = path.join(path.dirname(SOLVER_JS_PATH), '..', '..', 'Forge', 'terminal_librarian.py');
    if (!fs.existsSync(libPath)) {
        console.log('  📚 Librarian not found — skipping local knowledge query.');
        return '';
    }
    try {
        const query = errorLog.slice(0, 300).replace(/"/g, '\\"').replace(/\n/g, ' ');
        const result = execSync(
            `python -c "from terminal_librarian import TerminalLibrarian; lib = TerminalLibrarian(); print(lib.ask('${query}'))"`,
            { cwd: path.dirname(libPath), encoding: 'utf-8', timeout: 8000, stdio: ['ignore', 'pipe', 'ignore'] }
        ).trim();
        if (result && result !== '[]' && result !== 'None') {
            console.log(`  📚 Librarian found ${result.split('{').length - 1} relevant history entries.`);
            return `\n## Local Knowledge (TerminalLibrarian):\n${result}`;
        }
    } catch (_) { /* librarian unavailable — silent skip */ }
    return '';
}

// ─── Knowledge Base Bridge ─────────────────────────────────────────────────────
// Imports the local knowledge-base.js module for solution lookups.
// Falls back gracefully if the module isn't available.
let kbModule = null;
function getKB() {
    if (kbModule !== null) return kbModule;
    const kbPath = path.join(path.dirname(SOLVER_JS_PATH), 'src', 'knowledge-base.js');
    try {
        if (fs.existsSync(kbPath)) {
            // Dynamic import of the ES module
            kbModule = { path: kbPath, available: true };
            return kbModule;
        }
    } catch (_) {}
    kbModule = { available: false };
    return kbModule;
}

function queryKB(errorLog) {
    const kb = getKB();
    if (!kb.available) return null;
    try {
        // Use execSync to call the knowledge-base CLI
        const escaped = errorLog.slice(0, 500).replace(/"/g, '\\"').replace(/\n/g, ' ');
        const result = execSync(
            `node "${kb.path}" lookup "${escaped}"`,
            { encoding: 'utf-8', timeout: 3000, stdio: ['ignore', 'pipe', 'ignore'] }
        ).trim();
        if (result && result !== 'null') {
            const parsed = JSON.parse(result);
            if (parsed && parsed.fileEdits) {
                console.log(`  📚 [KB] Hit! Matched solution "${parsed.description || parsed.id}" (confidence: ${parsed._score || 'N/A'})`);
                return parsed;
            }
        }
    } catch (_) { /* KB lookup failed — silent skip */ }
    return null;
}

function feedKB(errorLog, actionPlan, source = 'llm') {
    const kb = getKB();
    if (!kb.available) return;
    try {
        const escaped = errorLog.slice(0, 500).replace(/"/g, '\\"').replace(/\n/g, ' ');
        const planStr = JSON.stringify({ chatResponse: actionPlan.chatResponse, fileEdits: actionPlan.fileEdits, commands: actionPlan.commands }).replace(/"/g, '\\"');
        execSync(
            `node "${kb.path}" learn "${escaped}" "${planStr}" "${source}"`,
            { timeout: 3000, stdio: 'ignore' }
        );
        console.log('  📚 [KB] Solution stored for future reference.');
    } catch (_) { /* silent */ }
}

// ─── Core Solve + Apply ────────────────────────────────────────────────────────
async function solveAndApply(context, terminalLog, { geminiKey, ollamaKey, workerUrl, autoApply = false }) {
    let actionPlan = null;
    let lastError  = '';

    // Tier 0: Knowledge Base (instant, free — past solutions)
    actionPlan = queryKB(terminalLog);
    if (actionPlan) {
        console.log('  ⚡ [Tier 0] Knowledge Base hit — skipping LLM calls.');
    }

    // Enrich context with librarian knowledge
    const librarianContext = queryLibrarian(terminalLog);
    const enrichedLog = terminalLog + librarianContext;

    // Tier 1: Local 9B Coder (fast, free — first attempt)
    if (!actionPlan) {
        try { actionPlan = await tryLocal9B(context, enrichedLog); }
        catch (e) { lastError = e.message; console.log(`  ❌ Tier 1 (9B Coder): ${e.message}`); }
    }
    // Tier 2: Local 12B Gemma (deep reasoning / planning mode)
    if (!actionPlan) {
        try { actionPlan = await tryLocal12B(context, enrichedLog); }
        catch (e) { lastError = e.message; console.log(`  ❌ Tier 2 (12B Gemma): ${e.message}`); }
    }
    // Tier 3: Ollama Cloud (DeepSeek V4 Pro — paid cloud)
    if (!actionPlan && ollamaKey) {
        try { actionPlan = await tryOllamaCloud(ollamaKey, context, enrichedLog); }
        catch (e) { lastError = e.message; console.log(`  ❌ Tier 3 (Ollama Cloud): ${e.message}`); }
    }
    // Tier 4: Gemini Flash → 1.5 (cheap/free tier)
    if (!actionPlan && geminiKey) {
        try { actionPlan = await tryGemini(geminiKey, context, enrichedLog); }
        catch (e) { lastError = e.message; console.log(`  ❌ Tier 4 (Gemini): ${e.message}`); }
    }
    // Tier 5: Cloudflare Worker (pay-as-you-go, opt-in)
    if (!actionPlan && workerUrl) {
        try { actionPlan = await tryCloudflare(workerUrl, context, enrichedLog); }
        catch (e) { lastError = e.message; console.log(`  ❌ Tier 5 (Cloudflare): ${e.message}`); }
    }

    if (!actionPlan) {
        console.error('\n💥 All LLM channels failed.'); writeCrashDump(terminalLog, lastError); process.exit(1);
    }
    if (typeof actionPlan.chatResponse !== 'string') {
        console.error('\n💥 LLM response malformed.'); writeCrashDump(terminalLog, JSON.stringify(actionPlan).slice(0, 300)); process.exit(2);
    }

    // Print response
    console.log(`\n🤖 Lumax Solver:\n${'─'.repeat(55)}\n${actionPlan.chatResponse}\n${'─'.repeat(55)}\n`);

    // Diff preview
    const edits = (actionPlan.fileEdits || []).filter(e => isSafePath(e.filePath));
    if (edits.length) showDiffPreview(edits);

    if (DRY_RUN) { console.log('\n🔍 [DRY RUN] No files written.'); return { success: true }; }

    // Confirm
    let apply = autoApply;
    if (!autoApply) {
        const { rl, ask } = makePrompt();
        const ans = await ask('👉 Apply? (y/n/preview): ');
        rl.close();
        if (ans.trim().toLowerCase() === 'n') { console.log('\n🚫 Aborted.'); process.exit(3); }
        apply = true;
    }

    // Apply patches atomically
    let backups = [];
    if (edits.length) {
        const result = applyPatchesAtomic(edits);
        backups = result.backups;
    }

    // Run commands
    if (Array.isArray(actionPlan.commands)) {
        for (const cmd of actionPlan.commands) {
            console.log(`⚙️ ${cmd}`);
            try { execSync(cmd, { stdio: 'inherit', cwd: REPO_PATH }); }
            catch (e) { console.error(`❌ Command failed: ${cmd}`); }
        }
    }

    // Post-patch test
    if (TEST_CMD) {
        const passed = runTestCmd(TEST_CMD);
        if (!passed) {
            console.error('\n⏪ Tests failed — rolling back all patches...');
            rollbackPatches(backups);
            process.exit(4);
        }
        // Auto-commit on success
        if (AUTO_COMMIT && isGitRepo(REPO_PATH)) {
            gitCommit(`fix: ${actionPlan.chatResponse.slice(0, 72)} [lumax-solver]`, edits.map(e => e.filePath));
        }
    }

    // Feed successful fix back to knowledge base for future instant recall
    if (actionPlan.chatResponse && edits.length > 0) {
        feedKB(terminalLog, actionPlan, autoApply ? 'auto' : 'llm');
    }

    console.log(`\n✅ Done — ${edits.length} file(s) patched.`);
    return { success: true };
}

// ─── Watch Mode ───────────────────────────────────────────────────────────────
async function watchMode(keys) {
    console.log(`\n👁️ [WATCH MODE] Monitoring ${REPO_PATH}`);
    if (TEST_CMD) console.log(`   Test cmd: ${TEST_CMD}`);
    fs.mkdirSync(path.dirname(WATCH_LOG), { recursive: true });

    const mtimes = new Map();
    const CODE_EXT = new Set(['.py', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.rs', '.go']);

    function logEvent(entry) {
        fs.appendFileSync(WATCH_LOG, JSON.stringify({ ts: Date.now(), ...entry }) + '\n');
    }

    function scanChanges() {
        const changed = [];
        for (const entry of walkTree(REPO_PATH)) {
            if (entry.type !== 'file') continue;
            if (!CODE_EXT.has(path.extname(entry.path).toLowerCase())) continue;
            const abs = path.join(REPO_PATH, entry.path);
            try {
                const mtime = fs.statSync(abs).mtimeMs;
                if (mtimes.has(entry.path) && mtime > mtimes.get(entry.path)) changed.push(entry.path);
                mtimes.set(entry.path, mtime);
            } catch (_) {}
        }
        return changed;
    }

    // Initial scan
    scanChanges();
    console.log(`   Watching ${mtimes.size} files. Ctrl+C to stop.\n`);

    while (true) {
        await new Promise(r => setTimeout(r, 2500));
        const changed = scanChanges();
        if (!changed.length) continue;

        console.log(`\n🔔 [WATCH] ${changed.length} file(s) changed: ${changed.join(', ')}`);
        logEvent({ event: 'change', files: changed });

        if (!TEST_CMD) {
            console.log('  ℹ️ No --test command set — change detected but no action taken.');
            continue;
        }

        const passed = runTestCmd(TEST_CMD);
        if (passed) {
            console.log('  ✅ All good — no LLM needed.');
            logEvent({ event: 'ok', files: changed });
            continue;
        }

        // Capture test output as the "error log"
        let testOutput = '';
        try { execSync(TEST_CMD, { cwd: REPO_PATH, encoding: 'utf-8' }); }
        catch (e) { testOutput = (e.stdout || '') + '\n' + (e.stderr || ''); }

        console.log('  🤖 Tests broke — invoking LLM solver...');
        logEvent({ event: 'llm_invoked', files: changed });

        const context = buildRepoContext(testOutput);
        await solveAndApply(context, testOutput, { ...keys, autoApply: true });
        logEvent({ event: 'llm_applied' });
    }
}

// ─── Local Saviour: HTTP Serve Mode ──────────────────────────────────────────
// Any service can POST to /solve or /repair. Auto-apply is gated behind explicit
// user opt-in (autoApplyEnabled in config). Nothing is applied without permission.
async function startServeMode(keys) {
    const http = await import('http');

    // Permission check
    const cfg = loadConfig();
    let autoApplyEnabled = cfg.autoApplyEnabled === true || flag('--enable-auto-apply');

    if (flag('--enable-auto-apply')) {
        saveConfig({ autoApplyEnabled: true });
        console.log('✅ [PERMISSION] Auto-apply ENABLED and saved to config.');
        autoApplyEnabled = true;
    }

    // Ring buffer for solve history (last 50 events)
    const history = [];
    function logHistory(entry) {
        history.push({ ts: new Date().toISOString(), ...entry });
        if (history.length > 50) history.shift();
    }

    async function handleRequest(req, res) {
        const url = new URL(req.url, `http://localhost:${SERVE_PORT}`);
        const route = `${req.method} ${url.pathname}`;

        // ── GET /health ──
        if (route === 'GET /health') {
            res.writeHead(200, { 'Content-Type': 'application/json' });
            return res.end(JSON.stringify({
                status: 'ok', service: 'lumax-solver',
                version: 'v3', port: SERVE_PORT,
                autoApplyEnabled, solves: history.length,
            }));
        }

        // ── GET /status ──
        if (route === 'GET /status') {
            res.writeHead(200, { 'Content-Type': 'application/json' });
            return res.end(JSON.stringify({ autoApplyEnabled, history }));
        }

        // ── POST /solve  (analysis only — never applies) ──
        // ── POST /solve/apply  (applies if autoApplyEnabled) ──
        // ── POST /repair  (watchdog compat — applies if autoApplyEnabled) ──
        if (['POST /solve', 'POST /solve/apply', 'POST /repair'].includes(route)) {
            let body = '';
            for await (const chunk of req) body += chunk;
            let payload;
            try { payload = JSON.parse(body); }
            catch (_) { res.writeHead(400); return res.end(JSON.stringify({ error: 'Invalid JSON body' })); }

            const errorLog = payload.error || payload.terminalLog ||
                (payload.terminalLog ? Buffer.from(payload.terminalLog, 'base64').toString('utf-8') : '') ||
                payload.log || '';

            const repoPath  = payload.repo ? path.resolve(payload.repo) : REPO_PATH;
            const shouldApply = (route !== 'POST /solve') && autoApplyEnabled;

            // Classify errors: only fatal / crashes / security exploits are Emergency
            const isEmergency = /fatal|security|panic|crash|exception|segfault|nullpointer|unhandledrejection|breach|exploit|compromised|leak/i.test(errorLog);
            const isAutoApplyAllowed = shouldApply && (isEmergency || payload.force);

            if (!errorLog) {
                res.writeHead(400);
                return res.end(JSON.stringify({ error: 'No error log provided. Send { "error": "..." }' }));
            }

            console.log(`\n⚡ [SERVE] Incoming solve request from ${req.socket.remoteAddress}`);
            console.log(`   Route: ${route} | Auto-apply: ${isAutoApplyAllowed} (emergency: ${isEmergency}) | Repo: ${repoPath}`);
            console.log(`   Error preview: ${errorLog.slice(0, 120).replace(/\n/g, ' ')}…`);

            logHistory({ event: 'received', route, autoApply: isAutoApplyAllowed, preview: errorLog.slice(0, 80) });

            // Build context relative to the requested repo
            const savedRepo = REPO_PATH;  // note: REPO_PATH is a const; context uses its own path
            const context = buildRepoContext(errorLog);

            let result;
            try {
                // Run solve (always in dry-run for /solve, real apply for /solve/apply & /repair)
                const actionPlan = await (async () => {
                    let plan = null;
                    let lastErr = '';
                    // Tier 1: Local 4B Fast Coder
                    try { plan = await tryLocal9B(context, errorLog); } catch (e) { lastErr = e.message; }
                    // Tier 2: Local 12B
                    if (!plan) {
                        try { plan = await tryLocal12B(context, errorLog); } catch (e) { lastErr = e.message; }
                    }
                    // Tier 3: Ollama Cloud
                    if (!plan && keys.ollamaKey) {
                        try { plan = await tryOllamaCloud(keys.ollamaKey, context, errorLog); } catch (e) { lastErr = e.message; }
                    }
                    // Tier 4: Gemini
                    if (!plan && keys.geminiKey) {
                        try { plan = await tryGemini(keys.geminiKey, context, errorLog); } catch (e) { lastErr = e.message; }
                    }
                    // Tier 5: Cloudflare
                    if (!plan && keys.workerUrl) {
                        try { plan = await tryCloudflare(keys.workerUrl, context, errorLog); } catch (e) { lastErr = e.message; }
                    }
                    if (!plan) throw new Error(`All channels failed. Last: ${lastErr}`);
                    return plan;
                })();

                if (isAutoApplyAllowed && Array.isArray(actionPlan.fileEdits) && actionPlan.fileEdits.length) {
                    const { applied } = applyPatchesAtomic(actionPlan.fileEdits);
                    if (Array.isArray(actionPlan.commands)) {
                        for (const cmd of actionPlan.commands) {
                            try { execSync(cmd, { stdio: 'inherit', cwd: REPO_PATH }); }
                            catch (e) { console.error(`❌ Cmd failed: ${cmd}`); }
                        }
                    }
                    logHistory({ event: 'applied', files: applied });
                    console.log(`  ✅ Applied ${applied.length} patch(es).`);
                    result = { status: 'applied', chatResponse: actionPlan.chatResponse, applied };
                } else {
                    // It was a post-session fix proposal or solve analysis
                    let proposalFile = null;
                    if (shouldApply && Array.isArray(actionPlan.fileEdits) && actionPlan.fileEdits.length) {
                        try {
                            const proposalsDir = path.join(REPO_PATH, '.lumax', 'proposals');
                            fs.mkdirSync(proposalsDir, { recursive: true });
                            proposalFile = path.join(proposalsDir, `proposal_${Date.now()}.json`);
                            fs.writeFileSync(proposalFile, JSON.stringify(actionPlan, null, 2), 'utf-8');
                            console.log(`  💾 Proposed post-session patch saved: ${proposalFile}`);
                        } catch (e) { console.warn(`  ⚠️ Failed to save proposal: ${e.message}`); }
                    }

                    logHistory({ event: 'analyzed', autoApplyDisabled: !isAutoApplyAllowed });
                    result = {
                        status: proposalFile ? 'proposed' : (shouldApply ? 'no_edits' : 'analyzed_only'),
                        chatResponse: actionPlan.chatResponse,
                        fileEdits: actionPlan.fileEdits,
                        commands: actionPlan.commands,
                        proposalFile: proposalFile,
                        note: isAutoApplyAllowed ? undefined : (proposalFile ? 'Patch saved as post-session proposal because it is not categorized as an emergency.' : 'Auto-apply is disabled.'),
                    };
                }
            } catch (err) {
                logHistory({ event: 'error', message: err.message });
                console.error(`  💥 Solve failed: ${err.message}`);
                res.writeHead(500);
                return res.end(JSON.stringify({ error: err.message }));
            }

            res.writeHead(200, { 'Content-Type': 'application/json' });
            return res.end(JSON.stringify(result));
        }

        // ── 404 ──
        res.writeHead(404);
        res.end(JSON.stringify({ error: 'Unknown route', available: ['GET /health', 'GET /status', 'POST /solve', 'POST /solve/apply', 'POST /repair'] }));
    }

    const server = http.default.createServer((req, res) => {
        handleRequest(req, res).catch(err => {
            console.error('💥 Handler error:', err);
            try { res.writeHead(500); res.end(JSON.stringify({ error: 'Internal server error' })); } catch (_) {}
        });
    });

    server.listen(SERVE_PORT, '127.0.0.1', () => {
        console.log(`\n🛡️  Local Saviour armed and listening on http://127.0.0.1:${SERVE_PORT}`);
        console.log(`   Auto-apply: ${autoApplyEnabled ? '✅ ENABLED' : '❌ DISABLED (analysis only)'}`);
        if (!autoApplyEnabled) {
            console.log(`   To enable:  node lumax-solver.js --serve --enable-auto-apply`);
            console.log(`   Or set in config: { "autoApplyEnabled": true }`);
        }
        console.log(`\n   Endpoints:`);
        console.log(`     GET  /health         — ping`);
        console.log(`     GET  /status         — solve history`);
        console.log(`     POST /solve          — analyze error (never applies)`);
        console.log(`     POST /solve/apply    — analyze + apply (if permitted)`);
        console.log(`     POST /repair         — watchdog compat endpoint`);
        console.log(`\n   Waiting for incoming errors…\n`);
    });

    // Graceful shutdown
    process.on('SIGINT', () => { console.log('\n🛑 Local Saviour shutting down.'); server.close(); process.exit(0); });
    process.on('SIGTERM', () => { server.close(); process.exit(0); });

    // Keep alive
    await new Promise(() => {});
}

// ─── Service Mode: HTTP + Guarded Repos + Log Tailers ─────────────────────────
// This is the mode the OS service (systemd/launchd/Task Scheduler) runs.
// It orchestrates everything simultaneously.
async function startServiceMode(keys) {
    const cfg = loadConfig();
    const guardedRepos = cfg.guardedRepos || [];
    const watchedLogs  = cfg.watchedLogs  || [];

    console.log(`\n🛡️  Lumax Solver — Guardian Service starting...`);
    console.log(`   Port:          ${SERVE_PORT}`);
    console.log(`   Guarded repos: ${guardedRepos.length}`);
    console.log(`   Log watchers:  ${watchedLogs.length}`);
    console.log(`   Auto-apply:    ${cfg.autoApplyEnabled ? '✅ ENABLED' : '❌ DISABLED'}\n`);

    // 1. HTTP guardian (accepts incoming POSTs from any service)
    const servePromise = startServeMode(keys);

    // Give the HTTP server 2s to bind before spawning watchers that will POST to it
    await new Promise(r => setTimeout(r, 2000));

    // 2. Repo watchers — one per guarded repo
    const watchPromises = guardedRepos.map(async (repo) => {
        if (!fs.existsSync(repo.path)) {
            console.warn(`⚠️ [SERVICE] Guarded repo not found, skipping: ${repo.path}`);
            return;
        }
        console.log(`👁️  Watching repo: ${repo.path}${repo.testCmd ? ' [' + repo.testCmd + ']' : ''}`);
        // We re-use watchMode but need to override REPO_PATH and TEST_CMD per-repo.
        // Since those are module-level consts we launch a child process instead.
        const { spawn: sp } = await import('child_process');
        const child = sp(process.execPath, [
            SOLVER_JS_PATH,
            '--watch',
            '--repo', repo.path,
            ...(repo.testCmd ? ['--test', repo.testCmd] : []),
            ...(repo.autoCommit ? ['--commit'] : []),
        ], { stdio: 'inherit', env: process.env });
        child.on('exit', (code) => {
            if (code !== 0) console.error(`⚠️ [SERVICE] Repo watcher exited (${repo.path}) code ${code}`);
        });
    });

    // 3. Log file tailers — poll each log file for new error lines
    const tailerPromises = watchedLogs.map(async (logPath) => {
        if (!fs.existsSync(logPath)) {
            console.warn(`⚠️ [SERVICE] Log file not found, will retry when it appears: ${logPath}`);
        }
        console.log(`📜 Tailing log: ${logPath}`);
        let lastSize = 0;
        const ERROR_PAT = /error|exception|traceback|fatal|failed|panic|crash/i;
        let pendingLines = [];
        let debounceTimer = null;

        async function flushToSolver(lines) {
            const blob = lines.join('\n');
            try {
                await fetch(`http://127.0.0.1:${SERVE_PORT}/solve/apply`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ error: blob, source: logPath }),
                    signal: AbortSignal.timeout(5000),
                });
            } catch (_) { /* solver not ready yet — skip */ }
        }

        // Poll every 3 seconds
        while (true) {
            await new Promise(r => setTimeout(r, 3000));
            try {
                if (!fs.existsSync(logPath)) continue;
                const stat = fs.statSync(logPath);
                if (stat.size <= lastSize) continue;
                const fd = fs.openSync(logPath, 'r');
                const buf = Buffer.alloc(stat.size - lastSize);
                fs.readSync(fd, buf, 0, buf.length, lastSize);
                fs.closeSync(fd);
                lastSize = stat.size;
                const newText = buf.toString('utf-8');
                const errorLines = newText.split('\n').filter(l => ERROR_PAT.test(l));
                if (errorLines.length) {
                    pendingLines.push(...errorLines);
                    clearTimeout(debounceTimer);
                    debounceTimer = setTimeout(() => {
                        const batch = [...pendingLines];
                        pendingLines = [];
                        flushToSolver(batch);
                    }, 2000);  // batch errors within 2s window
                }
            } catch (_) {}
        }
    });

    await Promise.all([servePromise, ...watchPromises, ...tailerPromises]);
}

// Self-path for spawning child processes
const SOLVER_JS_PATH = fileURLToPath(import.meta.url);

// ─── GPU Memory Cleanup ───────────────────────────────────────────────────────
function killExistingLLMProcesses() {
    // Free GPU VRAM by killing any running LLM servers before we spawn our own.
    // Targets: llama-server, LM Studio, ollama (local), koboldcpp
    const patterns = [
        'llama-server', 'llama-server.exe',
        'LM Studio.exe', 'LM_Studio.exe',
        'ollama.exe', 'ollama',
        'koboldcpp.exe', 'koboldcpp',
    ];
    let killed = 0;
    for (const name of patterns) {
        try {
            const result = execSync(`taskkill /F /IM "${name}" 2>nul`, { stdio: 'pipe' });
            if (result.toString().includes('SUCCESS')) {
                console.log(`  🧹 Killed: ${name}`);
                killed++;
            }
        } catch (_) { /* not running — fine */ }
    }
    if (killed > 0) {
        console.log(`  🧹 Freed GPU memory — ${killed} LLM process(es) terminated.\n`);
        // Give Windows a moment to actually release VRAM
        try {
            execSync('timeout.exe /t 2 /nobreak', { stdio: 'ignore' });
        } catch (_) {
            try { execSync('ping 127.0.0.1 -n 3', { stdio: 'ignore' }); } catch (__) {}
        }
    }
}

// ─── Main ─────────────────────────────────────────────────────────────────────
async function run() {
    console.log(`\n🛸 ─── Lumax Solver — Repo Manager Edition v3 ─── 🛸`);
    console.log(`   Repo: ${REPO_PATH}${TEST_CMD ? ` | Test: ${TEST_CMD}` : ''}${WATCH_MODE ? ' | WATCH' : ''}${DRY_RUN ? ' | DRY RUN' : ''}\n`);

    // Free GPU memory before spawning local models
    if ((WATCH_MODE || SERVE_MODE || SERVICE_MODE) && !process.env.LUMAX_LAUNCHER) {
        killExistingLLMProcesses();
    }

    // Load credentials
    let geminiKey = loadGeminiKey();
    let ollamaKey = loadOllamaKey();
    let workerUrl = loadWorkerUrl();

    if (!NON_INTERACTIVE) {
        const { rl, ask } = makePrompt();

        if (!geminiKey) {
            console.log('🔑 No Gemini key. Get one free: https://aistudio.google.com/app/apikey');
            const v = await ask('🔑 Gemini API key (blank to skip): ');
            geminiKey = v.trim() || null;
            if (geminiKey) saveConfig({ geminiApiKey: geminiKey });
        } else {
            console.log(`✨ Gemini: ${geminiKey.slice(0, 8)}…`);
        }

        if (!ollamaKey) {
            const v = await ask('🦙 Ollama Cloud key (blank to skip): ');
            ollamaKey = v.trim() || null;
            if (ollamaKey) saveConfig({ ollamaApiKey: ollamaKey });
        } else {
            console.log(`🦙 Ollama Cloud: ${ollamaKey.slice(0, 8)}…`);
        }

        if (!workerUrl) {
            const v = await ask('☁️ Cloudflare Worker URL (blank to skip): ');
            workerUrl = v.trim().replace(/\/$/, '') || null;
            if (workerUrl) saveConfig({ workerUrl });
        } else {
            console.log(`☁️ Cloudflare: ${workerUrl}`);
        }

        rl.close();
    }

    const keys = { geminiKey, ollamaKey, workerUrl };

    // ── OS Service mode (HTTP + all repo watchers + log tailers) ──
    if (SERVICE_MODE) {
        await startServiceMode(keys);
        return;
    }

    // ── Local Saviour serve mode ──
    if (SERVE_MODE) {
        await startServeMode(keys);
        return;
    }

    // ── Watch mode ──
    if (WATCH_MODE) {
        await watchMode(keys);
        return;
    }

    // ── Pipe mode ──
    if (PIPE_MODE) {
        console.log('📥 [PIPE] Reading error from stdin...');
        const chunks = [];
        for await (const chunk of process.stdin) chunks.push(chunk);
        const terminalLog = Buffer.concat(chunks).toString('utf-8').trim();
        if (!terminalLog) { console.error('❌ Empty stdin.'); process.exit(3); }
        const context = buildRepoContext(terminalLog);
        await solveAndApply(context, terminalLog, { ...keys, autoApply: true });
        return;
    }

    // ── Interactive mode ──
    const { rl, ask } = makePrompt();
    console.log('\n⚠️ Paste your error log below. Press ENTER on a blank line when done:');
    const errorLines = [];
    for await (const line of rl) {
        if (line.trim() === '') break;
        errorLines.push(line);
    }
    rl.close();
    const terminalLog = errorLines.join('\n');
    if (!terminalLog) { console.log('❌ No error provided. Exiting.'); process.exit(3); }

    const context = buildRepoContext(terminalLog);
    await solveAndApply(context, terminalLog, keys);
}

run().catch(err => { console.error('💥 Fatal:', err); process.exit(1); });
