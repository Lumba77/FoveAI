'use strict';

/**
 * xrlf-spawner.js — XRLF Auto-Spin-Up Manager
 *
 * The XRLF model is a proprietary single-file LLM format (`.xrlf`) that
 * cannot be served by LM Studio. It runs its own FastAPI + llama.cpp runtime
 * (the "XRLF server") on port 8300.
 *
 * This module lets the main foveated proxy (port 8400) natively support the
 * XRLF format by:
 *   1. Detecting when a request targets the XRLF model.
 *   2. Ensuring the XRLF server is running (spawn it if not).
 *   3. Waiting until its /health endpoint responds.
 *   4. Routing the request to it.
 *
 * The XRLF runtime lives in the dev working directory:
 *   <repo>/Tools/XRLF 1.0 dev
 * which contains its own `.venv` with llama_cpp, fastapi, uvicorn.
 *
 * No external dependencies — uses Node's built-in child_process + fetch.
 */

const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

// ── Config (overridable via env) ────────────────────────────────────────────

// Absolute path to the XRLF dev working directory.
// The XRLF runtime lives in FoveAI at the repo root.
const DEV_DIR = process.env.XRLF_DEV_DIR
  || (fs.existsSync(path.resolve(__dirname, '..', '..', '..', 'FoveAI', 'run_xrlf.py')) 
      ? path.resolve(__dirname, '..', '..', '..', 'FoveAI') 
      : path.resolve(__dirname, '..', '..', '..', 'Tools', 'XRLF 1.0 dev'));

// Model identifier used by the proxy side (providers.json maps this to 8300).
const XRLF_MODEL_IDS = [
  'xrlf-qwen4b-concise',
  'xrlf-qwen4b',
  'xrlf',
  'qwen4b-concise-v1.0',
  'lumax-plumax-omni-router',
];

// The .xrlf bundle to launch (relative to DEV_DIR).
const XRLF_MODEL_FILE = process.env.XRLF_MODEL_FILE || 'no2-lumax-plumax-omni-router.xrlf';

// Speculative Decoding (Draft Model) for 10x inference speed on Omni models.
// Uses one of your ultra-compact (e.g., 50MB-100MB) summarizer models to draft tokens for the main model.
// They are incredibly fast at spitting out large masses of tokens, making them perfect draft engines!
const XRLF_DRAFT_MODEL_FILE = process.env.XRLF_DRAFT_MODEL_FILE || 'lumax-summarizer-draft.gguf';

// Port the XRLF API server listens on.
const XRLF_PORT = parseInt(process.env.XRLF_PORT || '8402', 10);

// Health-check retry budget.
const XRLF_START_TIMEOUT_MS = parseInt(process.env.XRLF_START_TIMEOUT_MS || '180000', 10);
const XRLF_HEALTH_INTERVAL_MS = parseInt(process.env.XRLF_HEALTH_INTERVAL_MS || '2000', 10);

// ── Runtime state ───────────────────────────────────────────────────────────

let _child = null;
let _starting = false;
let _lastSpawnError = null;

function devPython() {
  // Prefer the venv python, fall back to system python.
  const candidates = [
    path.join(DEV_DIR, '.venv', 'Scripts', 'python.exe'),
    path.join(DEV_DIR, 'venv', 'Scripts', 'python.exe'),
    'python',
  ];
  for (const c of candidates) {
    if (c === 'python') return c;
    if (fs.existsSync(c)) return c;
  }
  return 'python';
}

function isXrlModel(modelName) {
  const m = (modelName || '').toLowerCase();
  return XRLF_MODEL_IDS.some(id => m.includes(id.toLowerCase()));
}

function devDirReady() {
  try {
    const launcher = path.join(DEV_DIR, 'run_xrlf.py');
    const model = path.join(DEV_DIR, XRLF_MODEL_FILE);
    return fs.existsSync(launcher) && fs.existsSync(model);
  } catch (e) {
    return false;
  }
}

async function healthOk() {
  try {
    const res = await fetch(`http://127.0.0.1:${XRLF_PORT}/health`, {
      signal: (() => { const c = new AbortController(); setTimeout(() => c.abort(), 3000); return c.signal; })(),
    });
    if (!res.ok) return false;
    const data = await res.json();
    return data && data.status === 'ok' && data.loaded === true;
  } catch (e) {
    return false;
  }
}

/**
 * Ensure the XRLF server is running on port 8300.
 * - If already healthy, returns immediately.
 * - Otherwise spawns the runtime from the dev directory and waits for /health.
 */
async function ensureXrlRunning() {
  // Already running and healthy?
  if (await healthOk()) {
    console.log('[XRLF] Server already healthy on :' + XRLF_PORT);
    return { ok: true, spawned: false };
  }

  // If a spawn is in flight, wait for it.
  if (_starting && _child) {
    return await waitForHealth();
  }

  if (!devDirReady()) {
    const err = `XRLF dev dir not ready: ${DEV_DIR} (missing run_xrlf.py or ${XRLF_MODEL_FILE})`;
    console.error('[XRLF] ' + err);
    _lastSpawnError = err;
    return { ok: false, spawned: false, error: err };
  }

  _starting = true;
  const py = devPython();
  const args = [
    'run_xrlf.py',
    '--model', XRLF_MODEL_FILE,
    '--port', String(XRLF_PORT),
  ];

  // If a draft model is specified and exists, inject the speculative decoding arguments
  const draftPath = path.join(DEV_DIR, XRLF_DRAFT_MODEL_FILE);
  if (XRLF_DRAFT_MODEL_FILE && fs.existsSync(draftPath)) {
    args.push('--draft', XRLF_DRAFT_MODEL_FILE);
  }

  let logFd;
  try {
    const logPath = path.join(DEV_DIR, 'xrlf-proxy.log');
    logFd = fs.openSync(logPath, 'a');
  } catch (e) {
    console.warn('[XRLF] Could not open log file, using ignore stdio:', e.message);
    logFd = 'ignore';
  }

  console.log(`[XRLF] Spawning XRLF server: ${py} ${args.join(' ')} (cwd=${DEV_DIR})`);
  _child = spawn(py, args, {
    cwd: DEV_DIR,
    windowsHide: true,
    detached: false,
    stdio: ['ignore', logFd, logFd],
    env: {
      ...process.env,
      XRLF_PORT: String(XRLF_PORT),
      // ── Reactor HOT (scoped to the XRLF child ONLY) ─────────────────
      // These flags are read exclusively inside xrlf_runtime.py. Setting
      // them here (in the child's env block) means ONLY the XRLF process
      // receives them — they cannot leak into the main proxy (8200), the
      // swarm router, or LM Studio. XRLF_CONTEXT_OVERRIDE stays false to
      // avoid the historical context-shrink behavior.
      XRLF_REPO_ENABLED: 'true',
      XRLF_CAPABILITY_OVERRIDE: 'true',
      XRLF_FOVEATION_OVERRIDE: 'true',
      XRLF_CONTEXT_OVERRIDE: 'false',
    },
  });

  _child.on('error', (err) => {
    console.error('[XRLF] Spawn error:', err.message);
    _lastSpawnError = err.message;
    _starting = false;
  });

  _child.on('exit', (code, signal) => {
    console.log(`[XRLF] Server exited (code=${code}, signal=${signal})`);
    _child = null;
    _starting = false;
    try { fs.closeSync(logFd); } catch (e) {}
  });

  const result = await waitForHealth();
  _starting = false;
  return result;
}

async function waitForHealth() {
  const deadline = Date.now() + XRLF_START_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (await healthOk()) {
      console.log(`[XRLF] Server healthy on :${XRLF_PORT}`);
      return { ok: true, spawned: true };
    }
    await new Promise(r => setTimeout(r, XRLF_HEALTH_INTERVAL_MS));
  }
  const err = `XRLF server did not become healthy within ${XRLF_START_TIMEOUT_MS}ms`;
  console.error('[XRLF] ' + err);
  _lastSpawnError = err;
  return { ok: false, spawned: true, error: err };
}

function getStatus() {
  return {
    devDir: DEV_DIR,
    modelFile: XRLF_MODEL_FILE,
    port: XRLF_PORT,
    running: !!_child,
    starting: _starting,
    lastError: _lastSpawnError,
    devDirReady: devDirReady(),
  };
}

module.exports = {
  isXrlModel,
  ensureXrlRunning,
  getStatus,
  XRLF_PORT,
  XRLF_MODEL_IDS,
};
