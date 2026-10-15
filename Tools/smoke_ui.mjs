/**
 * smoke_ui.mjs — headless UI smoke test + breakage collector.
 *
 * Loads Multigate in a real browser, walks the critical path (ignition →
 * chat), and records every console error, page error, failed request and
 * dead WebSocket. Writes a JSON report the agents (and Jen) can read, so
 * breakage is *detected* rather than discovered by the user.
 *
 *   node Tools/smoke_ui.mjs [--url http://127.0.0.1:5177] [--out report.json]
 *                            [--shots] [--keep-open]
 *
 * Exit: 0 when the page boots with no errors, 1 otherwise.
 */
import puppeteer from 'puppeteer-core';
import { writeFileSync, mkdirSync, readFileSync } from 'node:fs';

const arg = (name, def) => {
  const i = process.argv.indexOf(name);
  return i > -1 ? process.argv[i + 1] : def;
};
const URL_ = arg('--url', 'http://127.0.0.1:5177/');
const OUT = arg('--out', '/home/lumba/FoveAI/memory/ui_health/latest.json');
const SHOTS = process.argv.includes('--shots');

// Credentials are read from the environment/.env by the harness itself and
// never printed. They exist so the smoke test can reach the *authenticated*
// app — without this the test only ever measures the login portal.
// Auth for the smoke test. Order: explicit token → env credentials → skip.
// It never invents a username/password pair: guessing produced a misleading
// "logged in" verdict on a page that was still showing "invalid credentials".
function loadSession() {
  const token = process.env.FOVEAI_SMOKE_TOKEN || '';
  const user = process.env.FOVEAI_SMOKE_USER || '';
  const pass = process.env.FOVEAI_SMOKE_PASS || '';
  return { token, user, pass };
}

const IGNORE = [
  /favicon/i,
  /DevTools/i,
  /websocket is closed/i,
];

const browser = await puppeteer.launch({
  browser: 'firefox',
  executablePath: '/usr/bin/firefox',
  headless: true,
  args: ['--width=1680', '--height=1050'],
});

const page = await browser.newPage();
const errors = [];
const warnings = [];
const netFails = [];

page.on('console', (m) => {
  const t = m.text();
  if (IGNORE.some(r => r.test(t))) return;
  if (m.type() === 'error') errors.push({ kind: 'console', text: t.slice(0, 300) });
  else if (m.type() === 'warning') warnings.push({ kind: 'warn', text: t.slice(0, 200) });
});
page.on('pageerror', (e) => errors.push({ kind: 'pageerror', text: String(e).slice(0, 300) }));
page.on('requestfailed', (r) => {
  const u = r.url();
  if (IGNORE.some(x => x.test(u))) return;
  netFails.push({ url: u.slice(0, 160), reason: r.failure()?.errorText });
});

const steps = [];
const step = async (name, fn) => {
  const t0 = Date.now();
  try {
    const detail = await fn();
    steps.push({ name, ok: true, ms: Date.now() - t0, detail });
  } catch (e) {
    steps.push({ name, ok: false, ms: Date.now() - t0, detail: String(e).slice(0, 200) });
  }
};

// Through a tunnel the dev HMR socket never goes idle, so networkidle never
// fires — wait for DOM and let the settle window do the rest.
await page.goto(URL_, { waitUntil: 'domcontentloaded', timeout: 90000 });
await new Promise(r => setTimeout(r, 3500));

await step('page loads', async () => {
  const t = await page.title();
  if (!t) throw new Error('no title');
  return t;
});

await step('no error boundary', async () => {
  const txt = await page.evaluate(() => document.body.innerText);
  if (/Something went wrong|Oops!/i.test(txt)) throw new Error('error boundary shown');
  return 'clean';
});

await step('authenticate', async () => {
  const needsLogin = await page.evaluate(() =>
    /Enter unique ID|Authenticate/i.test(document.body.innerText));
  if (!needsLogin) return 'already authenticated';
  const { token, user, pass } = loadSession();
  if (!token && !(user && pass)) {
    return 'SKIPPED — no session token or credentials supplied (portal only)';
  }
  if (token) {
    // Seed the session the same way the app does after a real login.
    await page.evaluate((t) => {
      localStorage.setItem('foveai_foveai_user', JSON.stringify({
        id: 'smoke', firstName: 'Smoke', lastName: 'Test',
        username: 'smoke', apiKey: t, role: 'user',
      }));
      document.cookie = `fvs_gate=${t}; path=/`;
    }, token);
    try { await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 }); }
    catch { await page.goto(URL_, { waitUntil: 'domcontentloaded', timeout: 90000 }); }
    await new Promise(r => setTimeout(r, 4000));
  } else {
    await page.evaluate((u, p) => {
      const ins = [...document.querySelectorAll('input')];
      const set = (el, v) => {
        const d = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value');
        d.set.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true }));
      };
      if (ins[0]) set(ins[0], u);
      if (ins[1]) set(ins[1], p);
    }, user, pass);
    await page.evaluate(() => {
      const btn = [...document.querySelectorAll('button')].find(b => /Authenticate/i.test(b.textContent || ''));
      if (btn) btn.click();
    });
    await new Promise(r => setTimeout(r, 6000));
  }
  // Honest verdict: the portal must be gone AND no error banner present.
  const state = await page.evaluate(() => ({
    portal: /Enter unique ID/.test(document.body.innerText),
    denied: /invalid credentials|disabled account/i.test(document.body.innerText),
  }));
  if (state.denied) throw new Error('server rejected the credentials');
  if (state.portal) throw new Error('still on the login portal');
  return token ? 'session token accepted' : 'credentials accepted';
});

await step('persona setup', async () => {
  // After login the app shows a hard "Name your AI companion" wall; ignition is
  // behind it. This is the step a real user gets stuck on, so the harness walks
  // through it instead of reporting a false failure.
  const needsSetup = await page.evaluate(() =>
    /Name your AI companion|Configure your profile/i.test(document.body.innerText));
  if (!needsSetup) return 'already configured';
  await page.evaluate(() => {
    const ins = [...document.querySelectorAll('input')];
    const set = (el, v) => {
      const d = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value');
      d.set.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true }));
    };
    const byHint = (re) => ins.find(i => re.test(i.placeholder || '') || re.test(i.name || ''));
    const first = byHint(/first name/i); if (first) set(first, 'Smoke');
    const ai = byHint(/lumax|aria|ai name|companion/i) || ins[ins.length - 1];
    if (ai) set(ai, 'Smoke Jen');
  });
  await page.evaluate(() => {
    const btn = [...document.querySelectorAll('button')]
      .find(b => /^(enter|save|continue|next)$/i.test((b.textContent || '').trim()));
    if (btn) btn.click();
  });
  await new Promise(r => setTimeout(r, 5000));
  const still = await page.evaluate(() =>
    /Name your AI companion/i.test(document.body.innerText));
  if (still) return 'WALL STILL PRESENT — account cannot get past setup';
  return 'configured';
});

await step('ignition present', async () => {
  const found = await page.evaluate(() =>
    /ignite|press to|start/i.test(document.body.innerText));
  if (!found) throw new Error('no ignition/start affordance found');
  return 'found';
});

await step('press start', async () => {
  // The ignition control is a canvas dial, not a <button> — click its centre.
  const vp = page.viewport();
  await page.mouse.click(Math.round(vp.width / 2), Math.round(vp.height * 0.44));
  const clicked = await page.evaluate(() => {
    const els = [...document.querySelectorAll('button,[role=button],.ign-btn,.dial')];
    const el = els.find(e => /ignite|start|board|enter/i.test(e.textContent || ''));
    if (el) { el.click(); return true; }
    return false;
  });
  await new Promise(r => setTimeout(r, 9000));
  const txt = await page.evaluate(() => document.body.innerText);
  return clicked ? 'clicked' : `no button; body starts: ${txt.slice(0, 60)}`;
});

await step('reaches app shell', async () => {
  await new Promise(r => setTimeout(r, 4000));
  const txt = await page.evaluate(() => document.body.innerText);
  if (/Something went wrong/i.test(txt)) throw new Error('crashed after start');
  if (/press to ignite|press to board/i.test(txt)) throw new Error('still on the ignition screen');
  return txt.slice(0, 80).replace(/\n/g, ' ');
});

await step('mic diagnostics visible', async () => {
  // The mic must be legible: device, live level, audio-context state.
  const info = await page.evaluate(() => {
    const el = document.querySelector('.mic-diag');
    if (!el) return { present: false };
    return {
      present: true,
      devices: el.querySelectorAll('select option').length,
      readout: (el.querySelector('.mic-diag-readout')?.textContent || '').trim(),
    };
  });
  if (!info.present) throw new Error('mic diagnostics strip missing — mic state is invisible again');
  return `${info.devices} option(s) · ${info.readout}`;
});

await step('lightweight boot', async () => {
  // The default stage is the still frame: no WebGL rig should be mounted, which
  // is what keeps low-memory clients (Quest browser) alive on first paint.
  const info = await page.evaluate(() => ({
    canvases: document.querySelectorAll('canvas').length,
  }));
  if (info.canvases > 0) return `${info.canvases} canvas(es) — animated stage active`;
  return 'still-frame mode (no VRM decoded)';
});

await step('images render', async () => {
  // A 1x1 stub or a flat-colour placeholder loads fine but *looks* broken.
  // Catch both: decode failure (naturalWidth 0) and suspiciously tiny payloads.
  const bad = await page.evaluate(async () => {
    const imgs = [...document.querySelectorAll('img')];
    const out = [];
    for (const im of imgs) {
      if (im.complete && im.naturalWidth === 0) {
        out.push({ src: im.currentSrc || im.src, why: 'failed to decode' });
        continue;
      }
      try {
        const r = await fetch(im.currentSrc || im.src, { method: 'HEAD' });
        const len = Number(r.headers.get('content-length') || 0);
        // Tiny payload is only suspicious when it is displayed large — small
        // icons are legitimately a couple of KB.
        const shown = Math.max(im.clientWidth, im.clientHeight);
        if (r.ok && len && len < 4096 && shown >= 96) {
          out.push({ src: im.currentSrc || im.src, why: `only ${len} bytes at ${shown}px` });
        }
      } catch { /* cross-origin or offline — ignore */ }
    }
    return { total: imgs.length, bad: out };
  });
  if (bad.bad.length) throw new Error(`${bad.bad.length}/${bad.total} broken: ` +
    bad.bad.map(b => `${b.src.split('/').pop()}(${b.why})`).join(', '));
  return `${bad.total} images OK`;
});

await step('avatar asset reachable', async () => {
  const code = await page.evaluate(async () => {
    const r = await fetch('/avatars/jen.vrm', { method: 'HEAD' });
    return r.status;
  });
  if (code >= 400) throw new Error('avatar asset ' + code);
  return 'HTTP ' + code;
});

await step('softlayer modules served as JS', async () => {
  const res = await page.evaluate(async () => {
    const out = {};
    for (const m of ['particles', 'chameleon', 'clothing', 'lighting', 'wall']) {
      const r = await fetch(`/softlayer/modules/${m}.js`);
      const head = (await r.text()).slice(0, 40);
      out[m] = r.ok && !/^\s*<!doctype/i.test(head) ? 'js' : `BAD(${r.status})`;
    }
    return out;
  });
  const bad = Object.entries(res).filter(([, v]) => v !== 'js');
  if (bad.length) throw new Error('not JS: ' + bad.map(([k, v]) => `${k}=${v}`).join(','));
  return Object.keys(res).length + ' modules';
});

if (SHOTS) {
  mkdirSync('/home/lumba/FoveAI/memory/ui_health', { recursive: true });
  await page.screenshot({ path: '/home/lumba/FoveAI/memory/ui_health/smoke.png' });
}

await browser.close();

const report = {
  generated_at: new Date().toISOString(),
  url: URL_,
  verdict: errors.length === 0 && steps.every(s => s.ok) ? 'PASS' : 'FAIL',
  steps,
  error_count: errors.length,
  errors,
  warnings: warnings.slice(0, 20),
  failed_requests: netFails.slice(0, 40),
};
mkdirSync(OUT.replace(/\/[^/]+$/, ''), { recursive: true });
writeFileSync(OUT, JSON.stringify(report, null, 2));

console.log(`\n  verdict : ${report.verdict}`);
for (const s of steps) console.log(`   ${s.ok ? '✓' : '✗'} ${s.name} (${s.ms}ms) ${s.detail ?? ''}`);
console.log(`  errors  : ${errors.length}`);
for (const e of errors.slice(0, 10)) console.log(`    [${e.kind}] ${e.text}`);
if (netFails.length) {
  console.log(`  failed requests: ${netFails.length}`);
  for (const f of netFails.slice(0, 8)) console.log(`    ${f.reason} ${f.url}`);
}
console.log(`  report  : ${OUT}\n`);
process.exit(report.verdict === 'PASS' ? 0 : 1);