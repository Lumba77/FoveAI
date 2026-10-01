# FoveAI Session Handoff — 2026-09-05

## What's Running
- **Backend**: `python -m app.main` from `FoveAI\Backend\` — WebSocket on :8400, Media proxy on :8402, AI Director daemon active
- **Story Garden**: persisted at `FoveAI\data\story_garden.json` — 2 seeds loaded (including birthday seed for Feb 17)
- **Birthday**: set to February 17 (month=2, day=17) — Alice counts down 7 days before, decorates on the day

## Completed This Session (17/17 items)
1. HUD + chat + browser + settings + creative suite
2. VR Game Engine (monster hunt, target practice, companions, tower defense)
3. Scene Preset Manager (7 presets)
4. Game & Scene Controller panel
5. Backend WebSocket events for games/scenes
6. Memory dashboard
7. Ambient Corner HUD
8. Co-Presence Mode
9. Virtual Guest System (7 personalities)
10. Virtual Touring (10 destinations)
11. Co-Op Gaming with Alice (6 modes)
12. Webcam Window Gazing (10 locations)
13. Seasonal Theming (4 seasons + 6 holidays + birthday)
14. Director Engine (narrative events, suspense builder, shared surprises, scripted sequences)
15. Avatar Free Movement (8 modes, 8 moods, POI navigation)
16. Story Garden (slow-cooking narrative — seeds grow over days into full events)
17. Room Plastering (spatial mapping, 5 visualization modes)

## Key Files
### Unity C# (Experiences) — `client_quest\Assets\Scripts\Experiences\`
- `DirectorEngine.cs` (144 KB) — the big one
- `AvatarFreeMovement.cs` (38 KB)
- `SeasonalTheming.cs` (34 KB) — now includes birthday
- `VirtualTouring.cs` (32 KB)
- `CoOpGamingWithAlice.cs` (30 KB)
- `RoomPlastering.cs` (29 KB)
- `WebcamWindowGazing.cs` (23 KB)

### Unity IPC — `client_quest\Assets\Scripts\IPC\`
- `FoveAIWebSocketClient.cs` (44 KB) — routes 15+ event types

### Backend Python — `Backend\app\IPC\`
- `director_daemon.py` (63 KB) — Director + Story Garden
- `websocket_server.py` (59 KB) — all event routing
- `main.py` — entry point, starts Director daemon

## Next Steps
- Open Unity project, wire up script references in Inspector
- Build to Quest headset
- Test WebSocket events from Unity
- The garden is already growing — check `director.garden.status` via WebSocket
- Consider: expanded peaceful coexistence, more scripted sequences, more seed templates

## WebSocket Quick Reference
- `director.enable` / `director.disable`
- `director.trigger` {eventType, genre, character}
- `director.surprise` {surpriseType}
- `director.sequence` {sequence: "riders_on_the_storm"}
- `director.garden.status` / `director.garden.plant` {concept} / `director.garden.water` {seedId}
- `seasonal.set` {season, holiday}
- `room.plaster.mode` {mode: invisible|ghost|solid|wireframe|xray}
- `room.remap`
