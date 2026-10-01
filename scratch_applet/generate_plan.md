# Add Sleek AI Crystal Theme to Volume Applet

This plan outlines adding a new premium "Crystal Glass" theme to the Cinnamon audio applet using AI-generated glossy textures.

## Proposed Changes

### 1. Generate Glossy UI Textures
We will use the image generation tool to create three new assets:
- `rack-panel-crystal.png` - A high-gloss, premium translucent panel for the main UI.
- `rack-deep-crystal.png` - A darker, recessed glossy texture for the inner LCD screens.
- `rack-btn-crystal.png` - A sleek, glassy button texture.

### 2. Update `applet.js`
#### [MODIFY] applet.js
We will add a new `crystal` theme to `RACK_THEMES`:
```javascript
    "crystal": {
        tex: "crystal",
        cardBg: "rgba(10, 15, 25, 0.65)", cardBd: "rgba(255, 255, 255, 0.25)", btnBg: "rgba(255, 255, 255, 0.15)", ddBg: "rgba(5, 8, 15, 0.85)",
        val: "#00f0ff", valGlow: "rgba(0, 240, 255, 0.6)",
        acc: "#ff007f", accDim: "#b30059", dim: "#94a3b8", dim2: "#64748b",
        head: "#f8fafc", hint: "#cbd5e1", div: "rgba(255,255,255,0.2)", utilBd: "rgba(255,255,255,0.25)",
        inset: "inset 0 1px 5px rgba(0,0,0,0.8)", eqBar: "#00f0ff",
        wm: false,
        mc: { neutral: "#cbd5e1", low: "#ff007f", mid: "#00f0ff", high: "#7000ff" }
    }
```

### 3. Update `settings-schema.json`
#### [MODIFY] settings-schema.json
Add the new option to the `rackTheme` combobox:
```javascript
            "Crystal Glass — Sleek AI Theme": "crystal",
```

## User Review Required
> [!NOTE]
> Please review this new theme palette (cyan/magenta glowing text over glossy deep-blue/black glass) and approve if you are ready for me to generate the images and apply the changes!
