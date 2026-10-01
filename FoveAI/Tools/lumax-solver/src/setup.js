/**
 * foveai-solver setup wizard
 *
 * Run: foveai-solver setup  (or: node src/setup.js)
 *
 * Guides the user through:
 *   1. API key configuration (Gemini, Ollama Cloud, Cloudflare Worker URL)
 *   2. Guarded repository registration
 *   3. Log file path registration
 *   4. Local guardian service installation (opt-in)
 */

import fs from 'fs';
import os from 'os';
import path from 'path';
import { execSync } from 'child_process';
import readline from 'readline';

const CONFIG_PATH = path.join(os.homedir(), '.foveai', 'config.json');
const SVC_INSTALL = new URL('./service-install.js', import.meta.url).pathname.replace(/^\/([A-Z]:)/, '$1');

// ─── Helpers ──────────────────────────────────────────────────────────────────
function loadConfig() {
    if (fs.existsSync(CONFIG_PATH)) {
        try { return JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf-8')); } catch (_) {}
    }
    return {};
}

function saveConfig(updates) {
    fs.mkdirSync(path.dirname(CONFIG_PATH), { recursive: true });
    const cfg = Object.assign(loadConfig(), updates);
    fs.writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2), 'utf-8');
    return cfg;
}

function rl() {
    const iface = readline.createInterface({ input: process.stdin, output: process.stdout });
    const ask   = (q) => new Promise(res => iface.question(q, res));
    const close = () => iface.close();
    return { ask, close };
}

function green(s)  { return `\x1b[32m${s}\x1b[0m`; }
function cyan(s)   { return `\x1b[36m${s}\x1b[0m`; }
function yellow(s) { return `\x1b[33m${s}\x1b[0m`; }
function bold(s)   { return `\x1b[1m${s}\x1b[0m`; }
function dim(s)    { return `\x1b[2m${s}\x1b[0m`; }

async function verifyGeminiKey(key) {
    try {
        const resp = await fetch(
            `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${key}`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    contents: [{ role: 'user', parts: [{ text: 'Reply with just: ok' }] }],
                    generationConfig: { maxOutputTokens: 4 }
                }),
                signal: AbortSignal.timeout(8000),
            }
        );
        const data = await resp.json();
        return !data.error;
    } catch (_) { return false; }
}

async function verifyWorkerUrl(url) {
    try {
        const resp = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ terminalLog: btoa('test'), currentDirFiles: [] }),
            signal: AbortSignal.timeout(8000),
        });
        return resp.status < 500;
    } catch (_) { return false; }
}

// ─── Main wizard ──────────────────────────────────────────────────────────────
async function setup() {
    const { ask, close } = rl();
    const cfg = loadConfig();

    console.log(`
${bold(cyan('🛸  Lumax Solver — Setup Wizard'))}
${dim('Configure your AI keys, guarded repos, and optional local guardian service.')}
${dim('Config will be saved to: ' + CONFIG_PATH)}
`);

    // ── Step 1: Gemini API Key ──────────────────────────────────────────────
    console.log(bold('Step 1/4 — Gemini API Key') + dim('  (primary AI brain)'));
    if (cfg.geminiApiKey) {
        console.log(`  ${green('✅')} Key already configured: ${cfg.geminiApiKey.slice(0, 10)}…`);
        const overwrite = await ask('  Replace it? (y/N): ');
        if (overwrite.trim().toLowerCase() !== 'y') {
            console.log(`  ${dim('Keeping existing key.')}\n`);
        } else {
            cfg.geminiApiKey = null;
        }
    }

    if (!cfg.geminiApiKey) {
        console.log(`  ${dim('Get a free key at: https://aistudio.google.com/app/apikey')}`);
        const key = await ask('  Paste Gemini API key (blank to skip): ');
        if (key.trim()) {
            process.stdout.write('  Verifying… ');
            const valid = await verifyGeminiKey(key.trim());
            if (valid) {
                console.log(green('✅ Valid'));
                cfg.geminiApiKey = key.trim();
            } else {
                console.log(yellow('⚠️  Could not verify (saved anyway — check later)'));
                cfg.geminiApiKey = key.trim();
            }
        } else {
            console.log(`  ${dim('Skipped — Gemini tier will be disabled.')}`);
        }
    }
    console.log();

    // ── Step 2: Ollama Cloud Key ────────────────────────────────────────────
    console.log(bold('Step 2/4 — Ollama Cloud Key') + dim('  (secondary AI tier)'));
    if (cfg.ollamaApiKey) {
        console.log(`  ${green('✅')} Key already configured: ${cfg.ollamaApiKey.slice(0, 10)}…`);
        const overwrite = await ask('  Replace it? (y/N): ');
        if (overwrite.trim().toLowerCase() !== 'y') {
            console.log(`  ${dim('Keeping existing key.')}\n`);
        } else { cfg.ollamaApiKey = null; }
    }
    if (!cfg.ollamaApiKey) {
        console.log(`  ${dim('Get a key at: https://ollama.com/settings/keys')}`);
        const key = await ask('  Paste Ollama Cloud key (blank to skip): ');
        if (key.trim()) { cfg.ollamaApiKey = key.trim(); console.log(`  ${green('✅')} Saved.`); }
        else console.log(`  ${dim('Skipped.')}`);
    }
    console.log();

    // ── Step 2b: Cloudflare Worker URL ─────────────────────────────────────
    console.log(bold('  Cloudflare Worker URL') + dim('  (your existing tunnel — final fallback tier)'));
    if (cfg.workerUrl) {
        console.log(`  ${green('✅')} URL: ${cfg.workerUrl}`);
        const overwrite = await ask('  Replace it? (y/N): ');
        if (overwrite.trim().toLowerCase() === 'y') cfg.workerUrl = null;
    }
    if (!cfg.workerUrl) {
        const url = await ask('  Paste your Cloudflare Worker URL (blank to skip): ');
        if (url.trim()) {
            const u = url.trim().replace(/\/$/, '');
            process.stdout.write('  Checking reachability… ');
            const ok = await verifyWorkerUrl(u);
            console.log(ok ? green('✅ Reachable') : yellow('⚠️  Unreachable (saved anyway)'));
            cfg.workerUrl = u;
        }
    }
    console.log();

    // ── Step 3: Guarded Repositories ───────────────────────────────────────
    console.log(bold('Step 3/4 — Guarded Repositories'));
    console.log(`  ${dim('The solver will watch these repos and auto-fix errors when found.')}`);
    cfg.guardedRepos = cfg.guardedRepos || [];

    if (cfg.guardedRepos.length) {
        console.log(`  Currently guarded (${cfg.guardedRepos.length}):`);
        cfg.guardedRepos.forEach((r, i) => {
            console.log(`    ${i + 1}. ${r.path}${r.testCmd ? dim(' → ' + r.testCmd) : ''}`);
        });
    }

    let addMore = true;
    while (addMore) {
        const repoPath = await ask('  Add repo path (blank to finish): ');
        if (!repoPath.trim()) { addMore = false; break; }
        const absPath = path.resolve(repoPath.trim());
        if (!fs.existsSync(absPath)) {
            console.log(`  ${yellow('⚠️  Path not found — skipping.')}`);
            continue;
        }
        const testCmd = await ask(`  Test command for ${path.basename(absPath)} (blank to skip): `);
        const autoCommit = (await ask('  Auto-commit fixes if tests pass? (y/N): ')).trim().toLowerCase() === 'y';
        cfg.guardedRepos.push({
            path: absPath,
            testCmd: testCmd.trim() || null,
            autoCommit,
        });
        console.log(`  ${green('✅')} Added: ${absPath}`);
    }
    console.log();

    // ── Step 3b: Log File Tailing ───────────────────────────────────────────
    console.log(bold('  Log File Monitoring'));
    console.log(`  ${dim('The guardian will tail these log files and send errors to the solver.')}`);
    cfg.watchedLogs = cfg.watchedLogs || [];

    let addLog = true;
    while (addLog) {
        const logPath = await ask('  Add log file path (blank to finish): ');
        if (!logPath.trim()) { addLog = false; break; }
        const absPath = path.resolve(logPath.trim());
        cfg.watchedLogs.push(absPath);
        console.log(`  ${green('✅')} Added: ${absPath}`);
    }
    console.log();

    // ── Step 4: Permission model ────────────────────────────────────────────
    console.log(bold('Step 4/4 — Auto-Apply Permission'));
    console.log(`  ${dim('When the solver finds a fix, should it apply it automatically?')}`);
    console.log(`  ${dim('You can change this at any time in ~/.foveai/config.json')}`);
    if (cfg.autoApplyEnabled === undefined) {
        const allow = await ask('  Enable auto-apply? (y/N): ');
        cfg.autoApplyEnabled = allow.trim().toLowerCase() === 'y';
    } else {
        console.log(`  ${dim('Currently: ' + (cfg.autoApplyEnabled ? 'ENABLED' : 'DISABLED'))}`);
        const change = await ask('  Change it? (y/N): ');
        if (change.trim().toLowerCase() === 'y') {
            const allow = await ask('  Enable auto-apply? (y/N): ');
            cfg.autoApplyEnabled = allow.trim().toLowerCase() === 'y';
        }
    }
    console.log(`  ${cfg.autoApplyEnabled ? green('✅ Auto-apply ENABLED') : yellow('⚠️  Auto-apply DISABLED — solver will suggest only')}`);
    console.log();

    // ── Save config ─────────────────────────────────────────────────────────
    saveConfig(cfg);
    console.log(`${green('✅')} Config saved to ${CONFIG_PATH}\n`);

    // ── Step 5 (opt-in): Install as system service ──────────────────────────
    console.log(bold('Optional — Install as System Service'));
    console.log(`  ${dim('Run the solver as a background service that starts at login.')}`);
    console.log(`  ${dim('It will guard your repos, tail logs, and listen on port 8113.')}`);
    const installService = await ask('  Install local guardian service now? (y/N): ');

    if (installService.trim().toLowerCase() === 'y') {
        close();
        try {
            const { install } = await import('./service-install.js');
            await install();
        } catch (e) {
            console.error(`\n${yellow('⚠️  Service install failed:')} ${e.message}`);
            console.error(`  You can install it later with: ${cyan('foveai-solver service install')}`);
        }
    } else {
        close();
        console.log(`\n${dim('Skipped. Run anytime with:')} ${cyan('foveai-solver service install')}`);
    }

    console.log(`
${bold(green('🎉 Setup complete!'))}

Quick start:
  ${cyan('foveai-solver')}                    — interactive: paste any error
  ${cyan('foveai-solver serve')}              — local guardian (HTTP on :8113)
  ${cyan('foveai-solver --watch')}            — watch current directory
  ${cyan('foveai-solver service install')}    — install background service
  ${cyan('foveai-solver service status')}     — check service health
`);
}

setup().catch(err => { console.error('💥 Setup failed:', err.message); process.exit(1); });
