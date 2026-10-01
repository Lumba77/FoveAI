# LUMAX Handoff - August 17, 2026

## Session Summary (latest at top)

---

### Session 3 — Avatar, STT Regression, Backend Startup

#### 1. AvatarIKController.cs — REWRITTEN
- Replaced UnityEngine.Animations.Rigging (fragile, silently fails on Quest)
- Now uses built-in OnAnimatorIK() — works on ANY Humanoid rig, no packages needed
- SetLookAtPosition(Camera.main) = gaze always follows user when backend is idle
- LateUpdate() procedural breathing via spine bone micro-bob (breathAmplitude=0.005)
- Backend motor.ik_target events still override gaze when AI is active

#### 2. Quest3STTClient.cs — REGRESSION FIXED
- Critical bug: previous fix wrote async void Start() + yield return = INVALID C#
  Silently crashed on device, mic never started
- Fix: Start() calls StartCoroutine(InitRoutine()) - proper IEnumerator chain:
  load config -> request mic permission -> connect -> (server sends ready) -> mic starts
- OnEnable() restored with _initialized guard for scene reload

#### 3. NetworkDiscoveryManager.cs — NEW
- Path: Assets/Scripts/IPC/NetworkDiscoveryManager.cs
- TCP-probes backend port 8400 on startup
- If unreachable: shows amber in-VR overlay "Backend not detected, start on PC"
- Sends UDP broadcast on port 9999 -> wake_listener.py on PC starts all services
- Retries every 5s, hides overlay when backend comes online

#### 4. wake_listener.py — NEW
- Path: Backend/wake_listener.py
- Listens on UDP 9999 for Quest wake broadcast
- Starts: main.py (8400), stt_whisper_server.py (8402), tts_stream_server.py (8403)
- Each service opens its own console window (visible for debugging)
- Run once on PC: & C:\Users\danie\program\LUMAX\.venv\Scripts\python.exe C:\Users\danie\program\LUMAX\FoveAI\Backend\wake_listener.py

---

### Session 2 — STT/TTS Port Fix + TerminalIDE

#### STT/TTS Backend Port Fixes
- stt_whisper_server.py: 8011->8402, added ready handshake, /ws path
- tts_stream_server.py: 8012->8403, SAMPLE_RATE 22050->24000, added /ws path
- Quest3STTClient.cs: Android mic permission request added (was completely missing)

#### TerminalIDE Glassboard
- Floor-anchored (pivot=bottom-centre), 2m x 3m at scale 0.001
- fontSize 32 = 32mm chars at 2-3m (CanvasScaler ConstantPixelSize fixes override)
- Layout: Left=code, Right-top=FileManager, Right-bottom=Status
- "REQUEST EDIT MODE" button at bottom

---

## IMPORTANT: Rebuild Required
A fresh APK build is needed to pick up all changes.

## NetworkDiscoveryManager — Add to Scene
This script needs to be added as a component to a GameObject in the main scene.
AutoSceneBuilder.cs may need to be updated to spawn it on startup. Or manually drag
it onto an empty GameObject named "NetworkManager" in the scene.

## Test Checklist
1. Start wake_listener.py on PC
2. Install fresh APK on Quest
3. Launch APK - should see amber "Backend not detected" overlay
4. wake_listener.py auto-starts all 3 services
5. Overlay disappears after ~5s when backend comes online
6. Mic permission dialog appears on first launch
7. Speak -> Alicechan responds with voice
8. Alicechan looks at you with head tracking

## Next Steps
1. Wire NetworkDiscoveryManager into AutoSceneBuilder or add to scene manually
2. Test avatar gaze (OnAnimatorIK needs avatar to be Humanoid rig type in Animator settings)
3. If avatar still frozen: check Animator component has "Avatar" set + Humanoid rig type
4. Edit Mode button in TerminalIDE: wire OVR virtual keyboard
