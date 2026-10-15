// Headless proof that the avatar performance math actually performs:
// mouth moves only while speaking, blinks happen, idle never freezes.
const test = require('node:test');
const assert = require('node:assert');
// multigate is an ESM package — import the module, don't require it
let P;
test('module loads', async () => {
  P = await import('../Frontend/multigate/src/avatar/performance.js');
  assert.ok(typeof P.visemeAt === 'function');
});

test('envelope: fast attack, slower release', () => {
  let e = 0;
  for (let i = 0; i < 30; i++) e = P.envelope(e, 1);
  assert.ok(e > 0.95, 'reaches ~1 while loud');
  for (let i = 0; i < 5; i++) e = P.envelope(e, 0);
  assert.ok(e > 0.3 && e < 0.95, 'decays gradually, not instantly: ' + e);
});

test('mouth stays shut in silence and opens when speaking', () => {
  let loud = 0, moving = 0;
  for (let t = 0; t < 4; t += 1 / 60) {
    const v = P.visemeAt(t, 0);
    if (v) moving++;
    loud = Math.max(loud, v ? v.value : 0);
  }
  assert.equal(moving, 0, 'no visemes while silent');
  assert.ok(loud === 0, 'no mouth value while silent');

  moving = 0; loud = 0; const used = new Set();
  for (let t = 0; t < 2; t += 1 / 60) {
    const v = P.visemeAt(t, 0.8);
    if (v) { moving++; loud = Math.max(loud, v.value); used.add(v.name); }
  }
  assert.ok(moving > 60, 'mouth moves while speaking: ' + moving);
  assert.ok(loud > 0.8, 'mouth opens wide when loud');
  assert.ok(used.size >= 3, 'varied visemes, not one shape: ' + [...used].join(','));
});

test('idle is alive but subtle; body speaks only when loud', () => {
  const heads = new Set(), shifts = new Set();
  for (let t = 0; t < 6; t += 0.05) {
    heads.add(P.headIdle(t).yaw.toFixed(4));
    shifts.add(P.weightShift(t).x.toFixed(4));
  }
  assert.ok(heads.size > 50, 'head never freezes');
  assert.ok(shifts.size > 50, 'weight shift never freezes');
  assert.equal(P.talkBody(1.0, 0).nod, 0, 'no nods in silence');
  let maxNod = 0, maxHand = 0;
  for (let t = 0; t < 3; t += 1 / 60) {
    const b = P.talkBody(t, 0.9);
    maxNod = Math.max(maxNod, Math.abs(b.nod));
    maxHand = Math.max(maxHand, b.hand);
  }
  assert.ok(maxNod > 0.02 && maxHand > 0.05, 'speaking produces body language');
});

test('blinks are occasional and fully close', () => {
  let events = 0, prev = 0, max = 0, closedFrames = 0;
  for (let t = 0; t < 12; t += 1 / 60) {
    const b = P.blinkAt(t);
    if (b > 0.5) closedFrames++;
    if (b > 0.5 && prev <= 0.5) events++;   // rising edge = one blink
    prev = b;
    max = Math.max(max, b);
  }
  assert.ok(max > 0.95, 'lids fully close at peak');
  assert.ok(events >= 2 && events <= 10, 'blinks occasionally (not frozen, not spam): ' + events);
  assert.ok(closedFrames < 12 * 60 * 0.2, 'eyes are open most of the time');
});

test('breathing oscillates', () => {
  const s = new Set();
  for (let t = 0; t < 8; t += 0.1) s.add(P.breathing(t).toFixed(3));
  assert.ok(s.size > 20);
});

test('avatar validator agrees with the rig we ship', async () => {
  const { execFileSync } = require('node:child_process');
  const good = 'Frontend/multigate/public/avatars/jen.vrm';
  const code = execFileSync('.venv/bin/python',
    ['Tools/check_avatar.py', good, '--json'], { encoding: 'utf8' });
  const info = JSON.parse(code);
  assert.equal(info.exit, 0, 'shipped rig passes its own validator');
  assert.ok(info.mouth_shapes.length >= 5, 'shipped rig can lip sync');
  assert.ok(info.humanoid_bones > 40, 'shipped rig is properly rigged');
});
