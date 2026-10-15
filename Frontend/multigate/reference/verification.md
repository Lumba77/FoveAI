# Verification protocol (mandatory — updated 2026-10-08)

NEVER claim a change works without running this. Tools live in
`Tools/pw-verify/` (scripts) + playwright node_modules in `/tmp/opencode`
(recreate: `cd /tmp/opencode && npm i playwright --no-save`).
Run everything with `export PATH="$HOME/.local/node24/bin:$PATH"`.

## Login helper (all probes start here)
```js
await page.goto('http://localhost:5177/');
await page.fill('#username', 'ignite');
await page.fill('input[type="password"]', '1um6a1UM6a');
await page.click('button[type="submit"], .auth-form button');
// gate: click the ENTER button
```

## Probe set
1. **Render**: screenshot at 1600×900 AND 1920×1080; read them.
2. **Geometry** (for circles/positioning): measure with
   `getBoundingClientRect()` relative to the expected center; assert 0±3px.
   Use `offsetWidth/offsetHeight` (transform-immune) for sizes.
3. **Stability**: 3 screenshots 700ms apart, same state → pixel-diff <3%
   (PIL: `sum(histogram()[16:]) / (w*h)`).
4. **Interaction**: click the thing being changed; assert the observable
   effect (armed class, select value, message appears).
5. **Console**: zero errors (page.on('console')).

## Known traps (do not re-learn these)
- Backticks inside CSS comments terminate the <style> template literal.
- CSS individual transform properties (`rotate:`) + separate `transform:`
  compose in surprising order — animate the whole transform instead.
- Negative animation durations = invalid → element loses animation AND its
  centering transform (the displaced-ring bug).
- `getBoundingClientRect` includes ancestor scale; `offsetWidth` doesn't.
- Old duplicated CSS rules can survive edits — grep for duplicates after
  every stylesheet change (`grep -c '\.selector {'`).
- Quest WebView latches :hover and caches builds hard — long-press refresh
  or private window; bump BUILD markers.
- Vite dev server serves stale modules after many HMR edits — restart with
  --force when probe results contradict source truth.
- Recovery: last-good CSS is always extractable from dist/assets/index-*.js
  (find the template literal containing '.ign-screen {').

## Machine verification loop (for autonomous sessions)
For each work-queue item in STABILITY.md: implement → build → run probes →
if green, mark done in STABILITY.md; if red, fix before moving on.
Never batch unverified changes.
