# Theme Selector Submenu Plan

Since embedding a custom button directly into the `PopupBaseMenuItem` header is interfering with Cinnamon's window manager grab (causing the freeze), we will remove the custom button and use Cinnamon's native `PopupSubMenuMenuItem`.

## Proposed Changes

### 1. Remove Custom Button
- Remove the "🎨 Theme" `St.Button` from the `StudioMixerSection` header in `applet.js`.

### 2. Add Native Theme Submenu
- In `Applet._init`, right above where `StudioMixerSection` is added, we will add a native `PopupMenu.PopupSubMenuMenuItem("🎨 Studio FX Theme")`.
- We will loop through the available themes in `RACK_THEMES` and add a `PopupMenu.PopupMenuItem` for each theme.
- When clicked, these standard menu items will naturally and safely close the menu (without breaking Cinnamon's grab) and update the `rackTheme` setting.
- The `rackTheme` setting bind will continue to execute a clean `ReloadExtension` in the background.

## User Review Required
> [!NOTE]
> Are you okay with having a standard drop-down submenu called "🎨 Studio FX Theme" located just above the mixer interface, rather than a button stuck inside the header?
