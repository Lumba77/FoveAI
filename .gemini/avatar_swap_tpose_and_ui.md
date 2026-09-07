# Objective
Fix the T-pose issue occurring when swapping to secondary avatars and raise the UI height by 0.5 meters as requested.

# Key Files & Context
- `Godot/scripts/avatar_controller.gd`: Handles avatar skeletal mapping and animation sanitization. Currently, `force_resanitize_animations` performs a new search for the skeleton, accidentally grabbing secondary skeletons (like hair or tails) instead of the authoritative body skeleton, leading to invalid animation paths and the T-pose.
- `Godot/Nexus/SkeletonKey.gd`: Controls UI manifestation and positioning in the `_toggle_ui()` function.

# Implementation Steps

1. **Fix Skeleton Selection in Avatar Controller:**
   - In `Godot/scripts/avatar_controller.gd`, update `force_resanitize_animations()` to use the already validated `_skeleton` variable rather than performing a fresh `find_child` search.
   - Example change:
     ```gdscript
     func force_resanitize_animations() -> void:
         if not _body_animation_player or not avatar_node: return
         var skel = _skeleton # Use authoritative skeleton
         if not skel: return
     ```

2. **Adjust UI Position and Distance:**
   - In `Godot/Nexus/SkeletonKey.gd`, within the `_toggle_ui()` function, locate the UI positioning logic.
   - Pull the UI closer: Change `forward * 1.5` to `forward * 0.8`.
   - Raise the UI height: Change the Y-offset from `- 0.2` to `+ 0.1` (raising it by ~0.3 meters relative to previous, or whichever fits 0.5m higher if it was too low).
   - Example change:
     ```gdscript
     # POSITION UI: Pulled closer and raised
     var ui_pos = xr_cam.global_position + (forward * 0.8)
     ui_pos.y = xr_cam.global_position.y + 0.1
     ```

3. **Fix Jen's Floor Level:**
   - In `Godot/Nexus/SkeletonKey.gd`, inside `_toggle_ui()`, she is placed at `xr_cam.global_position.y - 1.6`. Since her Y position might end up below the actual floor, change it to respect the existing floor level or a safer offset like `0.0` (origin floor).
   - Example change:
     ```gdscript
     # POSITION JEN: Keep her on the actual floor level instead of guessing from the camera
     jen_pos.y = 0.0 # Standard Godot floor, or jen_body.global_position.y to preserve her existing floor level
     ```

4. **Fix Single-Grip UI Manipulation:**
   - In `Godot/Nexus/SkeletonKey.gd`, inside `_try_grab_object()`, the `ray` variable sometimes resolves to the `FunctionPointer` root node instead of the actual `RayCast3D` component, which doesn't have an `is_colliding` method. This breaks the ability to grab the UI.
   - Example change:
     ```gdscript
     func _try_grab_object(hand: XRController3D):
         var ray = hand.find_child("RayCast*", true, false)
         if ray and ray.has_method("is_colliding") and ray.is_colliding():
             var col = ray.get_collider()
             # (Rest of the grab logic...)
     ```

5. **Deploy Changes:**
   - Execute `.\push_all.ps1` to push the updated scripts to the Quest device via ADB.

# Verification & Testing
- Switch avatars via the WebUI and verify the new avatar assumes an active idle pose instead of a T-pose.
- Toggle the UI (Left Menu button) and verify the cockpit is spawned 0.5 meters higher than its previous position, improving visibility.