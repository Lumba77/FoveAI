# Plan: Home Regained - Stabilization & Recovery

## Objective
Fix the critical failures in Backend connectivity, STT, Double-Grip possession, and "Star Wars" Haptic Wands. We will decouple input systems from the avatar's animation state to ensure the project is controllable even during startup failures.

## Key Files & Context
- `Godot/Nexus/SkeletonKey.gd`: Root controller logic.
- `Godot/Mind/HapticWand.gd`: Haptic wand/morphing logic.
- `Godot/Soul/Synapse.gd`: Backend communication bridge.
- `Backend/Body/body_interface.py`: STT engine bridge.

## Implementation Steps

1. **Decouple Input (SkeletonKey.gd)**:
   - Move `_left_hand` and `_right_hand` assignment from `_setup_presence_cortex()` to `_ready()`.
   - Move Haptic Wand setup to `_ready()` so it doesn't wait for Jen to load.
   - This ensures you can move and use wands even if the avatar fails to load its skeleton.

2. **Fix STT/Backend Connectivity (Synapse.gd)**:
   - Restore the stable `server_ip` but add a `rotate_ip` feature that is only triggered manually or after a long timeout, preventing the startup crash.
   - Ensure the `LogMaster` is actually writing to a path that isn't blocked by Godot's sandbox.

3. **Fix "Star Wars" Haptics (HapticWand.gd)**:
   - Optimize the mesh generation (only update on shape-shift, not every frame).
   - Use `XRToolsRumbleManager` if available for better Quest haptics, falling back to `trigger_haptic_pulse`.

4. **Verify STT Bridge (body_interface.py)**:
   - Ensure the Faster-Whisper model is loading correctly on CPU to avoid the CUDA crash we saw earlier.

## Verification
- Launch on Quest.
- Test Double Grip: Can you steer the "Body" node?
- Test Haptic Wands: Do they morph (Whip/Club/Ball) and vibrate when touching things?
- Test STT: Hold B, speak, and see if text appears.
