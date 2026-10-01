# Add Theme Switcher to Audio UI Header

This plan adds a small interactive theme toggle to the header of the Studio FX rack directly inside the popup menu.

## Proposed Changes

### 1. Update `StudioMixerSection` Constructor
#### [MODIFY] applet.js
- Pass the main `applet` instance into `StudioMixerSection`.
- Add an interactive button/icon (e.g., a small palette icon or text button) to the `badgeRow` header.
- When clicked, this button will read the current `rackTheme` from `applet.settings`, cycle to the next available theme in `RACK_THEMES`, and call `applet.settings.setValue('rackTheme', nextTheme)`. 

### 2. Force Header Visibility
- Currently, the header (`badgeRow`) is only rendered if `RACK_LOGO_BADGE` is true or if the theme specifies `T.wm`. We will modify the logic to ensure the header is always rendered so the theme switcher is always accessible, or we will add a dedicated switcher row.

## User Review Required
> [!NOTE]
> Are you okay with adding a small "Theme" toggle button to the top left/right of the Studio FX section, and ensuring the header row is always visible across all themes to house it?
