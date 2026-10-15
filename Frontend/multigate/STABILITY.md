# Frontend Stability Contract — 2026-10-08

**Mission**: make Multigate boringly reliable. The user's real goal is vocal
face-to-face AI conversation in VR — this frontend is the door, not the house.

## Reference states ("screenshots of intent")

These two files are the FROZEN SPEC. Any change must keep them true:

- `reference/main-page.md`   — functional main chat page
- `reference/gate-page.md`   — functional start gate
- `reference/verification.md` — how every change is proven

## Non-negotiable rules

1. **Reference-first**: read the reference docs before touching code.
2. **Verify before claiming** — no "done" without the probe pass (see
   reference/verification.md). Never describe intent as a result.
3. **No new animation/interaction systems** on the main page without a
   device test plan. The vault is parked (`src/vault-parked/`).
4. **One change per commit**, verified, so rollback is always possible.
5. **Small surface**: prefer deleting/fixing over adding. New UI elements
   must state which reference behavior they serve.
6. When a session ends, update the STATUS table below — the next agent
   (or a week-away user) must know the exact state without archaeology.

## Work queue (checked off as completed+verified)

- [ ] Send-ball behavior = press to send, hold to talk. NOTHING else.
      No dragging, no mode hijack, no "image move" capture.
- [ ] Mode menu (text/voice/video) opens from the send area, selection
      sticks, indicator lives INSIDE the input area, not floating above.
- [ ] Composer always visible on 1080p/1440p/Quest viewport sizes.
- [ ] Chat round-trip: type → send → reply renders (real login).
- [ ] No console errors on gate + main page.
- [ ] ×2/×1.5 scale holds on all viewport tiers without layout breaks.
- [ ] AGENTS.md lessons updated with anything new learned.

## STATUS (update at end of every session)

| Area | State |
|---|---|
| Gate page | Simple gate live, logotype + cozy glass framing, verified |
| Vault | PARKED — src/vault-parked/; do not revive without canvas rebuild |
| Main chat | Composer: TXT→input / vocal→status chip; ball = mode regulator (press/hold/roll); PTT auto-sends transcription; wheel hijack removed twice — CHECK after any App.tsx revert |
| Portraits | Both 156×200 in the chat column (NOT viewport), clickable→upload (user & persona storages), user portrait flush to page bottom; listening glow while mic live |
| Bubbles | soft glass 22px radius, glued comic tails BOTH roles (assistant class mapped!), 92% width parity, first-name tags, thread lines portrait→bubble + timestamps at the elbow |
| Top bar | naked icons 44px, clock/context/metrics chips one rhythm, metrics hang left of AI portrait (margin-right clears) |
| Scale | ×1.45 uniform (App.css+ChatLayout rebuilt from HEAD ×1.45; App.tsx at HEAD + re-applied fixes) |
| STT | NEW: POST /stt on :8430 (PyAV decode→whisper), vite proxy /api/soul/stt exempted from fvs-gate; browser speech→bubble works server-side — needs one live mic test |
| Build | green via Node 24; vite dev serves no-cache headers now |
| Dev server | :5177 via systemd user unit `multigate-dev` (auto-restarts on boot) |
| STT | POST /stt on :8430 (PyAV→whisper) — needs live mic test |
| Chat | swarm ghost :8408 removed; /v1 verified end-to-end 2026-10-09 |
| Driver | nvidia 595.99.02 reinstalled (was kernel/userland mismatch) — REBOOT PENDING |
| Unity | headless fixes + AndroidPlayer il2cpp Release restored + Meta XR 205.0.0 + modules.vr + server_info discovery; NEXT: build 8 with --cores=10 after reboot |
| Image editor | 2026-10-15: desk decoupled (frame=viewport; image has own deskZoom/imgPan 5%..500%; pan tool+wheel+pinch; fit/fill/1:1/crop-to-frame chips). AI ops → LOCAL /api/dream :8412 — VERIFIED LIVE: paint txt2img 15.5s warm (14 steps @256), outpaint img2img 65s incl. pipe load, detail enhance ~1s. Engine select: SD1.5 default (always fits), Z-Turbo opt-in w/ 13G RAM preflight (trio = 12G — oomd kills mid-load when LLM resident; don't retry until card free). Dials button toggles sidebar. Diffusers 0.40 gotchas fixed in _load_zimage_pipe (GGUFQuantizationConfig + component instances). VERIFY in browser before claiming stable. |
