'use strict';
/**
 * _xrlf_env_fix.cjs — Decontaminate root .env + report state.
 *
 * Goals (surgical, XRLF-process-only):
 *   1) Ensure root `c:/Users/danie/program/LUMAX/.env` does NOT contain
 *      XRLF_REPO_ENABLED=true (so it never leaks into the main Node proxy
 *      at 8200 or the swarm router).
 *   2) Report the current state of both .env files to a report file so the
 *      agent can read it reliably (the terminal mangles one-liner output).
 *
 * Usage:  node _xrlf_env_fix.cjs
 * Report: c:/Users/danie/program/LUMAX/_xrlf_env_report.txt
 */

const fs = require('fs');
const path = require('path');

const ROOT = 'c:/Users/danie/program/LUMAX';
const ROOT_ENV = path.join(ROOT, '.env');
const DEV_ENV = path.join(ROOT, 'Tools', 'XRLF 1.0 dev', '.env');
const REPORT = path.join(ROOT, '_xrlf_env_report.txt');

const report = [];
function log(msg) {
  report.push(msg);
}

function readEnv(p) {
  try {
    return fs.readFileSync(p, 'utf8');
  } catch (e) {
    return null;
  }
}

// ── 1) Decontaminate root .env ──────────────────────────────────────────
let rootChanged = false;
const rootRaw = readEnv(ROOT_ENV);
if (rootRaw === null) {
  log('ROOT_ENV: missing (nothing to do)');
} else {
  const lines = rootRaw.split(/\r?\n/);
  const before = lines.length;
  const filtered = lines.filter((l) => {
    const t = l.trim();
    // Remove any XRLF_REPO_ENABLED / override / context override lines from root.
    return !/^XRLF_REPO_ENABLED\s*=/i.test(t)
      && !/^XRLF_CAPABILITY_OVERRIDE\s*=/i.test(t)
      && !/^XRLF_FOVEATION_OVERRIDE\s*=/i.test(t)
      && !/^XRLF_CONTEXT_OVERRIDE\s*=/i.test(t);
  });
  if (filtered.length !== before) {
    fs.writeFileSync(ROOT_ENV, filtered.join('\r\n'), 'utf8');
    const removed = before - filtered.length;
    log(`ROOT_ENV: removed ${removed} XRLF override line(s) from root .env`);
    rootChanged = true;
  } else {
    log('ROOT_ENV: already clean (no XRLF_REPO/OVERRIDE/CONTEXT lines)');
  }
}

// ── 2) Report dev .env state ─────────────────────────────────────────────
const devRaw = readEnv(DEV_ENV);
if (devRaw === null) {
  log('DEV_ENV: missing');
} else {
  const devLines = devRaw.split(/\r?\n/).filter((l) => /XRLF|OVERRIDE|CONTEXT/i.test(l));
  log('DEV_ENV XRLF lines:');
  devLines.forEach((l) => log('  ' + l));
}

// ── 3) Verify xrlf-spawner.js has child-scoped flags ───────────────────
const spawner = readEnv(path.join(ROOT, 'Tools', 'foveated-memory', 'core', 'xrlf-spawner.js'));
if (spawner === null) {
  log('SPAWNER: missing');
} else {
  const ok = spawner.includes('XRLF_REPO_ENABLED:') && spawner.includes('XRLF_CONTEXT_OVERRIDE: \'false\'');
  log('SPAWNER child-scoped XRLF flags: ' + (ok ? 'OK' : 'MISSING/UNEXPECTED'));
}

// ── 4) Verify run_xrlf.py has the .env loader ──────────────────────────
const launcher = readEnv(path.join(ROOT, 'Tools', 'XRLF 1.0 dev', 'run_xrlf.py'));
if (launcher === null) {
  log('LAUNCHER: missing');
} else {
  const ok = launcher.includes('_load_local_env') && launcher.includes('def _load_local_env');
  log('LAUNCHER run_xrlf.py .env loader: ' + (ok ? 'OK' : 'MISSING/UNEXPECTED'));
}

log('ROOT_CHANGED=' + String(rootChanged));
fs.writeFileSync(REPORT, report.join('\n'), 'utf8');
console.log('report written to ' + REPORT);

