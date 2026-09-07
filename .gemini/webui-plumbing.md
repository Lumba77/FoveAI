# Plan: Plumb WebUI and Implement Final Steps

## Objective
Correctly identify the active WebUI (`index.html` rendered in a `WebView`), and connect its buttons to Godot functions to implement the pending features from the "MIGRATION" tab.

## Key Files
- `Godot/Mind/Web/index.html`: The user-facing UI with placeholder buttons.
- `Godot/Nexus/SkeletonKey.gd`: The master script that will handle signals from the UI.
- `Godot/Mind/Lumax_Display.tscn`: A broken scene that needs to be fixed.
- `Godot/Mind/keyboard_test_screen.gd`: A missing script that needs to be created.

## Implementation Steps

### 1. Fix the Broken Keyboard Demo Scene
- **Create Placeholder Script:** Create a new GDScript file at `Godot/Mind/keyboard_test_screen.gd`. This script will extend `Panel` and have a basic `_ready` function to show it has loaded.
- **Update Scene Reference:** Modify `Godot/Mind/Lumax_Display.tscn` to change the `ext_resource` path for its script from the non-existent `res://scenes/baseline/keyboard_test_screen.gd` to the new `res://Mind/keyboard_test_screen.gd`.

### 2. Implement JavaScript-to-Godot Bridge
- **Update HTML Buttons:** In `Godot/Mind/Web/index.html`, modify the `onclick` attributes for the `RESTORE_UTILITIES` buttons. Instead of `alert()`, they will use `JavaScriptBridge.emit_signal('web_button_pressed', 'unique_button_id')` to send a signal to Godot.
- **Create Godot Signal Handler:** In `Godot/Nexus/SkeletonKey.gd`, add a `_ready` function check for the `JavaScriptBridge` singleton. If it exists, connect its `web_button_pressed` signal to a new handler function, `_on_web_button_pressed`.

### 3. Plumb the Button Functionality
- **Implement Handler Logic:** The new `_on_web_button_pressed(button_id: String)` function in `SkeletonKey.gd` will use a `match` statement on the `button_id`.
- **Implement Keyboard Demo:** For the `launch_keyboard` ID, it will call a new function `show_keyboard_demo()`. This function will load and instance the now-fixed `Godot/Mind/Lumax_Display.tscn` and position it in the world.
- **Implement Integrity Check:** For the `integrity_check` ID, it will call a placeholder function `_run_integrity_check()` that shows a user notification.
- **Implement Stubs:** For all other button IDs, it will show a "not yet plumbed" user notification.

## Verification
1.  Push all four modified files (`index.html`, `SkeletonKey.gd`, `Lumax_Display.tscn`, and the new `keyboard_test_screen.gd`) to the Quest.
2.  Launch the application in VR.
3.  Open the WebUI.
4.  Navigate to the "MIGRATION" tab.
5.  Press the "LAUNCH KEYBOARD_DEMO" button and verify a 2D panel appears in the 3D space.
6.  Press the "INTEGRITY_CHECK" button and verify a notification appears on the user's arm HUD.
