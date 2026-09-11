# FoveAI — Development Context

Latest developments and session log.

## 2026-09-11 — XR Locomotion, Sociable Alice, and Passthrough Fix

### Environment recovery (Linux reinstall)
- Rebuilt Python 3.12 venv with `uv` (system Python 3.14 too new for pinned wheels)
- Installed Unity 6000.4.9f1 + Android Build Support
- Activated Unity Personal licensing
- Built and verified Quest APK (519 MB, IL2CPP arm64)

### XR Thumbstick Locomotion (new Input System)
- Added `Assets/Scripts/XR/XRThumbstickLocomotion.cs`
- Uses `InputAction` with `<XRController>{LeftHand}/thumbstick` and `<OpenXRController>` bindings
- Left thumbstick = smooth move (head-gaze relative, 1.5 m/s)
- Right thumbstick = snap turn (30° increments, 0.25s cooldown)
- Auto-wired to `XR_CameraRig` by `AutoWireExperiences.cs`
- Player can now walk beyond physical room space; room-scale tracking unaffected

### Alice sociability improvements
- Default mode: `Follow` (was `FreeRoam`) — Alice stays near you
- Default mood: `Clingy` (was `Curious`) — comes to you more often
- Clinginess: 0.8 (was 0.4)
- Curiosity: 0.5 (was 0.7) — less wandering off
- Follow distance: 1.2m (was 1.5m) — stands closer
- Position: in **front** of player (was behind) — walks to where you're facing
- Head tracking: looks at user 70% of time (was 50%)
- Decision interval: 6s (was 8s) — more responsive

### Passthrough fix
- Main Camera clear flags: Skybox → SolidColor (transparent black) in scene
- `XRRigFixer.Awake()` now fixes ALL cameras before first render
- AndroidManifest: added `com.oculus.vr.capability.group = mhmr` (Mixed Reality mode)

### Infrastructure
- Installed and configured xrdp (port 3389) for remote desktop access
- Firewall: ports 1025-65535 TCP+UDP open (covers all FoveAI services)
- HTTP server on port 8888 for APK sideloading to Quest (no USB cable needed)
- Installed EDuke32 (Flatpak) + Duke Nukem 3D shareware for a visiting friend

### Build commands
- APK: `bash client_quest/build_apk.sh --cores=8`
- Tests: `.venv/bin/python -B -m unittest discover -s tests -p 'test_api_health.py' -v`
- HTTP sideload: `cd client_quest && python3 -m http.server 8888 --bind 0.0.0.0`
