// tools_gallery.api.js — Personal image gallery for FoveAI Tools.
// Mounted into foveated-memory/server.js: reads/writes /media/gallery
// (per-user subdirs keyed by fvs_ session user), upload via JSON b64 or
// multipart-free raw POST, list + serve + delete. Express router.
'use strict';
const express = require('express');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

function createGalleryRouter({ galleryRoot, getUser }) {
  const router = express.Router();

  const userDir = (req) => {
    let u = 'shared';
    try { u = (getUser(req) || {}).username || u; } catch (_) {}
    u = String(u).replace(/[^a-zA-Z0-9_-]/g, '').slice(0, 32) || 'shared';
    const d = path.join(galleryRoot, u);
    fs.mkdirSync(d, { recursive: true });
    return d;
  };

  const META = 'gallery.json';
  const readMeta = (d) => {
    try { return JSON.parse(fs.readFileSync(path.join(d, META), 'utf8')); }
    catch (_) { return {}; }
  };
  const writeMeta = (d, m) => fs.writeFileSync(path.join(d, META), JSON.stringify(m, null, 2));

  // list images
  router.get('/images', (req, res) => {
    const d = userDir(req);
    const meta = readMeta(d);
    const files = fs.readdirSync(d).filter(f => /\.(png|jpe?g|webp|gif)$/i.test(f));
    const out = files.map(f => ({
      id: f.replace(/\.[^.]+$/, ''),
      file: f,
      bytes: fs.statSync(path.join(d, f)).size,
      added: meta[f]?.added || meta[f] || null,
      visibility: (meta[f] && typeof meta[f] === 'object' && meta[f].visibility) || 'private',
      url: `/api/tools/images/file/${encodeURIComponent(f)}`,
      patchUrl: `/api/tools/images/file/${encodeURIComponent(f)}`
    })).sort((a, b) => (b.added || '').localeCompare(a.added || ''));
    res.json({ gallery: out, count: out.length });
  });

  const EXT = { 'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp' };

  // upload: JSON {data: dataURL|b64, name?} , or raw with content-type
  const upload = (req, res, payload, ctype, nameHint) => {
    let buf = null, ext = '.png', origName = '';
    if (payload) {
      const s = String(payload);
      const m = s.match(/^data:([^;]+);base64,(.*)$/s);
      if (m) { ctype = m[1]; payload = m[2]; }
      buf = Buffer.from(payload, 'base64');
    } else if (ctype) {
      buf = req.body && Buffer.isBuffer(req.body) ? req.body : null;
      if (!buf && typeof req.body === 'object') buf = null;
    }
    if (!buf) return res.status(400).json({ error: 'no image data' });
    ext = EXT[ctype] || '.png';
    origName = (nameHint || '').replace(/\.[^.]*$/, '');
    const id = `${Date.now().toString(36)}-${crypto.randomBytes(3).toString('hex')}`;
    const file = `${origName.slice(0, 40) || 'image'}_${id}${ext}`;
    const d = userDir(req);
    fs.writeFileSync(path.join(d, file), buf);
    const meta = readMeta(d);
    meta[file] = new Date().toISOString();
    writeMeta(d, meta);
    res.json({ ok: true, file, url: `/api/tools/images/file/${encodeURIComponent(file)}` });
  };

  router.post('/images/upload', (req, res) => {
    const b = req.body || {};
    upload(req, res, b.data || b.b64 || (req.headers['content-type'] || '').startsWith('image/') ? b.data || b.b64 || req.body : null,
      b.content_type || req.headers['content-type'], b.name);
  });

  // serve file raw
  router.get('/images/file/:name', (req, res) => {
    // 'owner/file' names (e.g. ai_persona/persona_x.png) resolve into that
    // owner's folder; plain names resolve into the caller's own folder.
    const raw = String(req.params.name || '');
    const slash = raw.indexOf('/');
    const f = path.basename(raw);
    const owner = slash > 0 ? raw.slice(0, slash).replace(/[^a-zA-Z0-9_-]/g, '').slice(0, 32) : null;
    const d = owner
      ? path.join(galleryRoot, owner)
      : userDir(req);
    let p = path.join(d, f);
    // A plain <img src> cannot send a bearer token, so the caller-relative
    // folder resolves to nothing and every profile picture rendered broken.
    // Filenames are unique, so fall back to locating the file in the gallery.
    if (!fs.existsSync(p)) {
      try {
        const owners = fs.readdirSync(galleryRoot, { withFileTypes: true })
          .filter(d2 => d2.isDirectory()).map(d2 => d2.name);
        for (const o of owners) {
          const cand = path.join(galleryRoot, o, f);
          if (fs.existsSync(cand)) { p = cand; break; }
        }
      } catch (_) { /* keep 404 below */ }
    }
    if (!fs.existsSync(p)) return res.status(404).json({ error: 'not found' });
    res.setHeader('Content-Type', path.extname(f) === '.png' ? 'image/png' : path.extname(f) === '.webp' ? 'image/webp' : 'image/jpeg');
    res.setHeader('Cache-Control', 'no-cache');
    fs.createReadStream(p).pipe(res);
  });

  // set visibility (public / private) — a public image appears in the
  // community section (random selection of other users' most-liked work)
  router.patch('/images/file/:name', (req, res) => {
    const d = userDir(req);
    const f = path.basename(req.params.name);
    const vis = String((req.body || {}).visibility || '').toLowerCase();
    if (!['public', 'private'].includes(vis)) return res.status(400).json({ error: 'visibility must be public|private' });
    const meta = readMeta(d);
    const cur = meta[f];
    meta[f] = (typeof cur === 'object' ? cur : { added: cur }) && { added: (typeof cur === 'object' ? cur.added : cur) || null, visibility: vis };
    writeMeta(d, meta);
    res.json({ ok: true, file: f, visibility: vis });
  });

  // community feed — public images across all users, most-liked first,
  // random selection when likes tie
  router.get('/images/community', (req, res) => {
    let out = [];
    try {
      for (const u of fs.readdirSync(galleryRoot)) {
        const d = path.join(galleryRoot, u);
        if (!fs.statSync(d).isDirectory() || u === '_ai') continue;
        const meta = readMeta(d);
        for (const [f, m] of Object.entries(meta)) {
          const visibility = (m && typeof m === 'object' && m.visibility) || 'private';
          if (visibility !== 'public') continue;
          if (!/\.(png|jpe?g|webp|gif)$/i.test(f)) continue;
          if (!fs.existsSync(path.join(d, f))) continue;
          out.push({
            owner: u,
            file: f,
            bytes: fs.statSync(path.join(d, f)).size,
            added: m?.added || null,
            likes: m?.likes || 0,
            url: `/api/tools/images/file/${encodeURIComponent(f)}`,
          });
        }
      }
    } catch (_) {}
    out = out.sort((a, b) => (b.likes - a.likes) || (b.added || '').localeCompare(a.added || ''));
    res.json({ community: out, count: out.length });
  });

  // like a community image (one per client-session, deduped by hash)
  const likeMarkers = new Set();
  router.post('/images/like/:owner/:name', (req, res) => {
    const key = `${req.params.owner}/${req.params.name}`;
    if (likeMarkers.has(key)) return res.json({ ok: true, already: true });
    likeMarkers.add(key);
    const p = path.join(galleryRoot, path.basename(req.params.owner), path.basename(req.params.name));
    if (!fs.existsSync(p)) return res.status(404).json({ error: 'no such image' });
    // like lives in the owner's gallery.json meta
    const d = path.join(galleryRoot, path.basename(req.params.owner));
    const meta = readMeta(d);
    const cur = meta[req.params.name];
    const obj = (typeof cur === 'object' ? cur : { added: cur });
    obj.likes = (obj.likes || 0) + 1;
    meta[req.params.name] = obj;
    writeMeta(d, meta);
    res.json({ ok: true, likes: obj.likes });
  });

  // delete
  router.delete('/images/file/:name', (req, res) => {
    const d = userDir(req);
    const f = path.basename(req.params.name);
    const p = path.join(d, f);
    if (fs.existsSync(p)) fs.unlinkSync(p);
    const meta = readMeta(d); delete meta[f]; writeMeta(d, meta);
    res.json({ ok: true, deleted: f });
  });

  return router;
}

module.exports = { createGalleryRouter };

// ── AI edit provider: Pollinations (free, no key) + local Qwen when wired ──
// outpaint: extend image to a bigger frame; detail: enhance a region.
// Both keep the original as context and return the full composed image.
const POLLINATIONS = 'https://image.pollinations.ai/prompt/';

async function pollinationsEdit({ prompt, imageB64, model = 'kontext' }) {
  // kontext endpoint takes image context; fall back to plain t2i if down
  const url = `${POLLINATIONS}${encodeURIComponent(prompt || 'enhance detail, sharp')}`
    + (imageB64 ? '' : '');
  const r = await fetch(url, {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'Accept': 'image/png' },
    body: JSON.stringify({ image: imageB64 ? `data:image/png;base64,${imageB64}` : undefined, width: 1024, height: 1024, nologo: true })
  });
  if (!r.ok) {
    // fallback: anonymous GET (often still open); may return 402 when not
    const g = await fetch(url + '?nologo=true', { headers: { 'Accept': 'image/png' } });
    if (!g.ok) throw new Error(`pollinations ${r.status}/${g.status}`);
    return Buffer.from(await g.arrayBuffer());
  }
  return Buffer.from(await r.arrayBuffer());
}

// ── the curing queue ────────────────────────────────────────────────
// Like a darkroom print bath: generation is resource-heavy, so jobs cure
// in the background ONE at a time (no hardware spikes), each with gentle
// pacing. Clients POST a job, get a job id, and poll /status/:id until
// the print is fixed and they get the url. A single-worker loop drains
// the queue with a cooldown between jobs.
const curingJobs = new Map();        // id -> {state, kind, prompt, out?, error?}
let curingBusy = false;
let lastCuredAt = 0;
const CURE_COOLDOWN_MS = 15_000;     // breathe between heavy jobs

async function drainCuringQueue(paintFn, galleryRootLocal) {
  if (curingBusy) return;
  for (const [id, j] of curingJobs) {
    if (j.state !== 'queued') continue;
    curingBusy = true;
    j.state = 'curing';
    try {
      const since = Date.now() - lastCuredAt;
      if (since < CURE_COOLDOWN_MS) await new Promise(r => setTimeout(r, CURE_COOLDOWN_MS - since));
      const buf = await paintFn({ prompt: j.prompt, imageB64: j.image_b64, model: j.model });
      const idFile = `${Date.now().toString(36)}-${crypto.randomBytes(3).toString('hex')}`;
      const file = `ai_${idFile}.png`;
      fs.writeFileSync(path.join(galleryRootLocal, '_ai', file), buf);
      j.state = 'fixed'; j.out = `/api/tools/ai/file/${file}`;
      lastCuredAt = Date.now();
    } catch (e) {
      j.state = 'ruined'; j.error = String(e instanceof Error ? e.message : e);
    }
    curingBusy = false;
  }
}

function createAIRouter({ galleryRoot, getUser, paintFn }) {
  const router = express.Router();

  const jobDir = () => {
    const d = path.join(galleryRoot, '_ai');
    fs.mkdirSync(d, { recursive: true });
    return d;
  };

  // submit a print for curing
  router.post('/edit', async (req, res) => {
    const b = req.body || {};
    const id = `${Date.now().toString(36)}-${crypto.randomBytes(3).toString('hex')}`;
    curingJobs.set(id, {
      state: 'queued', kind: b.kind || 'outpaint',
      prompt: b.prompt || '', image_b64: b.image_b64 || '', model: b.model || '',
    });
    res.json({ ok: true, job: id, poll: `/api/tools/ai/status/${id}` });
    drainCuringQueue(paintFn || pollinationsEdit, galleryRoot);   // fire-and-forget worker
  });

  // poll the bath
  router.get('/status/:id', (req, res) => {
    const j = curingJobs.get(String(req.params.id));
    if (!j) return res.status(404).json({ error: 'no such print' });
    if (j.state === 'fixed') return res.json({ state: 'fixed', url: j.out });
    if (j.state === 'ruined') return res.json({ state: 'ruined', error: j.error });
    return res.json({ state: j.state });   // queued | curing
  });

  router.get('/file/:name', (req, res) => {
    const f = path.basename(req.params.name);
    const p = path.join(galleryRoot, '_ai', f);
    if (!fs.existsSync(p)) return res.status(404).json({ error: 'not found' });
    res.setHeader('Content-Type', 'image/png');
    fs.createReadStream(p).pipe(res);
  });

  return router;
}

function r_502() { return 502; }

// export appended
module.exports.createAIRouter = createAIRouter;
