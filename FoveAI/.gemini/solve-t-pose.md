# Plan: Resolve T-Pose and Steering Issues

## Objective
Restore Jen's physical agency by removing the conflicting `AnimationTree` suppression logic and fixing the interaction transforms.

## Key Files & Context
- `Godot/scripts/avatar_controller.gd`: Contains the core animation playback logic. Currently, `play_animation` tries to activate the `AnimationTree`, but the `_process` function forcefully deactivates it on the same frame, causing an animation deadlock (T-pose).
- `Godot/Nexus/SkeletonKey.gd`: Contains an overly aggressive "Nuclear Suppression" loop that targets all `AnimationMixer` nodes. In modern Godot, `AnimationPlayer` inherits from `AnimationMixer`, meaning this loop could be accidentally suppressing the primary animation player as well. It also contains the `_steer_avatar` logic which may be using deprecated or incorrect XR input mappings.
- `Godot/Mind/TactileInput_v2.gd`: The Vision Cockpit layout is mostly fixed, but the specific node names for the previews (`UserPOV` and `JenPOV` in `WebUI.gd`) need to be synced correctly so the textures apply.

## Implementation Steps
1. **Cleanse `avatar_controller.gd`**:
   - Remove the `_animation_tree.active = false` suppression from `_process`.
   - Remove the `AnimationTree` fallback branch from `play_animation`. We will strictly enforce `AnimationPlayer.play()` to ensure robust, direct bone manipulation.
2. **Cleanse `SkeletonKey.gd`**:
   - Remove the "Nuclear Suppression" loop from `_process` to stop it from fighting the `AnimationPlayer`.
   - Audit and correct the `_steer_avatar` function to ensure it properly translates the Quest 3 thumbstick vectors (`primary_2d_axis`) into global space movement.
3. **Restore Vision Previews**:
   - Ensure `WebUI.gd` properly targets the new `_user_preview` and `_jen_preview` texture rects created in `TactileInput_v2.gd` to restore the vision stream.

## Verification & Testing
- The avatar should smoothly transition into the `idle` animation on boot, rather than remaining stuck in a T-pose.
- Pushing the left thumbstick forward while holding both grips should move the avatar in world space and trigger the `walk` animation.
- The 60x60 preview boxes in the UI should display the live camera feeds.