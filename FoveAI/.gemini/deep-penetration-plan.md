# Plan: Deep Project Penetration & Stability Analysis

## Objective
Investigate the architectural "rot" causing the 440+ warnings and the duplicate "competing" avatars. Instead of applying quick fixes, we will map out why the systems are clashing (Multiplayer vs. Local) and why the VR tools are failing to initialize.

## Key Areas of Investigation
1. **The "Competing" Avatars**:
   - Trace why `SkeletonKey.gd` and `Lumax_Core.tscn` are both trying to own the "Jen" instance.
   - Investigate why `avatar_controller.gd` reports `Target Skeleton: MISSING`, leaving one Jen in a T-pose.
2. **The 440+ Warning Storm**:
   - **XRTools Autoload Failure**: Diagnose why `user_settings.gd` and `rumble_manager.gd` are throwing parse errors (Identifier 'XRTools' not declared). This likely breaks haptics and settings.
   - **OpenXR Path Conflicts**: Analyze why the Meta XR extension is reporting "Unsupported toplevel path" for eye tracking and trackers.
3. **The "Boutique/Street" Camera Mystery**:
   - Investigate the `screenshot_watcher.gd` and `MultiVisionHandler.gd` to see how POV captures are actually handled and why they might be failing to "load properly."

## Proposed Research Steps
1. **Node Tree Audit**: Run a script to dump the live Node Tree from the Quest to see exactly where the duplicate Jen is being parented.
2. **Dependency Mapping**: Verify the `addons/godot-xr-tools/` structure to see if a missing script or a broken `.gdignore` is causing the "XRTools not declared" error.
3. **Multiplayer vs. Local Logic**: Analyze `MultiplayerManager.gd` to ensure it isn't accidentally spawning a "local proxy" that mimics the real Jen.

## Verification & Breakthrough Documentation
- Create a "System Health Report" in `.gemini/health_report.md`.
- Document the "Milestone" state before attempting deep structural changes.
