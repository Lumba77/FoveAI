# Plan: Stabilize Avatar & UI

## Objective
Fix the duplicate avatar spawning, reign in the wild autonomous animations, and correct the UI rendering (transparent background with shaded keyboard).

## Key Files & Context
- `Godot/Nexus/SkeletonKey.gd`
- `Godot/Mind/Lumax_Display.tscn`
- `Godot/Nexus/Lumax_Core.tscn`

## Implementation Steps
1. **Fix Duplicate Avatar**: 
   - `SkeletonKey.gd` `_setup_ambience()` was creating a *second* instance of `Lumax_Jen.tscn`. 
   - We updated it to first check for the existing `Avatar` node (already in `Lumax_Core.tscn`) and use it instead. This eliminates the T-posed duplicate facing away.
2. **Reign in Wild Animations**:
   - `_scan_for_animations()` was pulling *every* animation (jumping, climbing, dancing) into the `_idle_anims` pool.
   - We added a string filter to only append animations containing "idle", "stand", or "breathe".
3. **Fix Transparent UI**:
   - The UI `Viewport` was inheriting a `transparent_bg` setting which breaks the alpha sorting on Quest, making the UI look transparent while the keyboard gets shaded by environment lights.
   - We explicitly set `transparent_bg = false` in `Lumax_Display.tscn`.
4. **Deploy to Quest**:
   - Push the updated `SkeletonKey.gd` and `Lumax_Display.tscn` to the Quest using `adb push`.

## Verification
- Launch the app on Quest.
- Verify only one Jen exists, facing the user.
- Verify she stays in subtle idle animations rather than performing acrobatics.
- Verify the WebUI has a solid background and doesn't ghost against the background.
