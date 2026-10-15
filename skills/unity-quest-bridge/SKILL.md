---
name: unity-quest-bridge
description: Build & debug the FoveAI Quest 3 APK (client_quest, Unity 6000.4.9f1 on Linux) — Android WebView bridge that renders the Multigate web UI on a VR quad. Use for APK builds, WebViewPanel work, scene/asmdef wiring, or Quest deployment issues.
version: 1.0.0
author: FoveAI
metadata:
  tags: [unity, quest, apk, webview, android,XR, foveai]
  related_skills: [xrl-proxy]
---

# Unity ↔ Quest ↔ Web Bridge

## Topology (one sentence each)

- **Web:** `Frontend/multigate` (Vite, dev :5177) serves the UI; Quest loads it over LAN.
- **Bridge:** `client_quest/Assets/Scripts/UI/WebViewPanel.cs` — software-rendered
  Android WebView (`LAYER_TYPE_SOFTWARE`, drawn offscreen at x=-8192) → `draw()` →
  Bitmap → PNG → `Texture2D` on a quad; ray/pinch/touch dispatched via
  `MotionEvent.obtain`; thumbstick = `scrollBy`. Default URL `http://192.168.8.100:5177/chat`.
- **Unity side:** Unity 6000.4.9f1 @ `/opt/Unity/Unity-6000.4.9f1/Editor/Unity`;
  scene `FoveAI.unity`, asmdef `FoveAI.Runtime`; avatar scripts mirror the TS
  layer (`AvatarManager`/`MovementEngine`/`HapticWand`/`TposeWarningSystem` in C#).
- **Deploy:** `apk_server.py` serves `AliceVR.apk` (port 8888, Range support) for sideload.

## Build (Linux, headless-safe)

```bash
cd /home/lumba/FoveAI/client_quest && ./build_apk.sh [--fast|--cores=N|out.apk]
```

- Editor autodetect: `/opt/Unity/Unity-*/Editor/Unity` first, then `~/Unity/Hub/Editor/*`.
- **DISPLAY required** — Unity 6 aborts in `-batchmode` without X (this box: `:20`).
  If `xdpyinfo -display :20` fails, script's `DISPLAY=:0` default needs updating.
- SDK/NDK live inside the editor install (`Editor/Data/PlaybackEngines/android-sdk-ndk-tools/…`,
  NDK r27c, JDK 17.0.18, platforms 34–36). `PlaybackEngines/AndroidPlayer` only
  appears after Android-support.pkg; if missing, extract the xar manually:
  TOC zlib at heap-start+~2 bytes, `Payload` = gzip → cpio → extract (see git history).
- asmdef: new packages (e.g. `Unity.XR.Hands`) MUST be added to
  `FoveAI.Runtime.asmdef` references or scripts fail to compile.
- Build logs: `client_quest/build_linux*.log`; result → `AliceVR.apk` (~527M) or
  `build/outputs/apk/android/AliceVR.apk` (copied by script).

## Pitfalls (learned)

1. **Password gate eats WebView traffic** — `FoveAI_WEBUI_PASSWORD` returns the
   Xarel login HTML for anything outside the `/api/ /v1/ /xrlf/ /health` allowlist;
   inside the WebView this looks like a broken proxy. Test the cookie first.
2. WebView needs `setDomStorageEnabled(true)` + `setMediaPlaybackRequiresUserGesture(false)`
   for the multigate audio/vibration flows — already set; don't regress.
3. Non-Android builds render a placeholder quad only (all bridge code is
   `#if UNITY_ANDROID && !UNITY_EDITOR`) — editor-testing the UI is pointless; use a browser.
4. Hand-tracking rays need the tracking-space transform dance via controller
   anchor parent (same convention as XRRigFixer) — see `PollHandRay`.

## Commands

- `/quest build` → run build_apk.sh, tail log for `SUCCESS: APK built`
- `/quest serve` → `python3 apk_server.py` (port 8888)
- `/quest panel <url>` → tell WebViewPanel.Navigate(url) target convention:
  LAN multigate URL, never localhost.