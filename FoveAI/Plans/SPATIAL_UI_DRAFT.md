# Spatial UI Draft: LUMAX Dashboard 3D WebGL Port

## 1. CSS & Layout Analysis (`Dashboard.ts`)

### Chat History Container (`#chat-history`)
- **Layout**: `display: flex`, `flex-direction: column`, `flex: 1`
- **Spacing**: `gap: 12px`, `padding-right: 10px`
- **Background**: Transparent, but inherits a radial gradient from `.dashboard-content`: `radial-gradient(circle at 50% 0%, rgba(0, 243, 255, 0.05) 0%, transparent 70%)`
- **Dimensions**: Takes available height minus footer.

### Input Wrapper (`.input-wrapper`)
- **Layout**: `display: flex`, `flex-direction: row`
- **Spacing**: `gap: 10px`, `padding: 5px`
- **Background**: `rgba(255, 255, 255, 0.03)`
- **Border**: `1px solid rgba(0, 243, 255, 0.2)`, `border-radius: 4px`

### Text Input (`#chat-input`)
- **Layout**: `flex: 1`
- **Background**: `transparent`
- **Typography**: `'Inter', sans-serif`, `0.85rem` size, `#ffffff` color

### Send Button (`.btn-send`)
- **Layout**: Fixed width padding `padding: 0 15px`
- **Background**: `var(--neon-blue)` -> `#00f3ff`
- **Typography**: `'Orbitron', sans-serif`, `0.6rem` size, `#000000` color, `font-weight: 700`
- **Border**: `none`, `border-radius: 3px`

---

## 2. `three-mesh-ui` Architectural Proposal

To map this into a 3D WebGL UI using `three-mesh-ui`, we construct a hierarchical tree of `Block` components. Since WebGL requires absolute units (usually meters), we will map CSS pixels/rems to World Units (WU), assuming `1 WU = 1 meter`. A reasonable scale factor is `1px ≈ 0.001 WU`.

### Hierarchical Tree Structure

```javascript
import * as ThreeMeshUI from 'three-mesh-ui';

// 1. Root Container (Dashboard)
const rootContainer = new ThreeMeshUI.Block({
    height: 0.9,     // ~900px
    width: 0.5,      // ~500px
    padding: 0.02,   // ~20px
    justifyContent: 'space-between',
    flexDirection: 'column',
    fontFamily: './assets/fonts/Inter-Regular-msdf.json',
    fontTexture: './assets/fonts/Inter-Regular.png',
});

// 2. Chat History Scroll Area
const chatHistoryBlock = new ThreeMeshUI.Block({
    height: 0.75,
    width: '100%',
    padding: 0.01,
    margin: 0.01,
    backgroundOpacity: 0.05,
    backgroundColor: new THREE.Color(0x00f3ff), // Matches the subtle glow
    justifyContent: 'end',
    flexDirection: 'column',
    interline: 0.012 // corresponds to gap: 12px
});
// Note: To support scrolling, nest content in a parent block that applies y-axis position translation based on scroll events.

// 3. Input Wrapper (Footer)
const inputWrapperBlock = new ThreeMeshUI.Block({
    height: 0.06,
    width: '100%',
    padding: 0.005,  // 5px padding
    margin: 0.01,
    justifyContent: 'space-between',
    contentDirection: 'row',
    backgroundColor: new THREE.Color(0xffffff),
    backgroundOpacity: 0.03,
    borderColor: new THREE.Color(0x00f3ff),
    borderOpacity: 0.2,
    borderWidth: 0.001,
    borderRadius: 0.004 // 4px border-radius
});

// 4. Text Input Field (Placeholder)
const chatInputBlock = new ThreeMeshUI.Block({
    width: 0.35, // flex: 1 mapping
    height: 0.04,
    padding: 0.008, // 8px
    backgroundOpacity: 0,
    fontColor: new THREE.Color(0xffffff),
    fontSize: 0.02 // 0.85rem approx
});

// 5. Send Button
const sendButtonBlock = new ThreeMeshUI.Block({
    width: 0.08,
    height: 0.04,
    padding: 0.015, // 15px
    backgroundColor: new THREE.Color(0x00f3ff), // --neon-blue
    backgroundOpacity: 1.0,
    borderRadius: 0.003, // 3px
    fontFamily: './assets/fonts/Orbitron-Bold-msdf.json', // Requires Orbitron MSDF font
    fontTexture: './assets/fonts/Orbitron-Bold.png',
});

const sendButtonText = new ThreeMeshUI.Text({
    content: 'SEND',
    fontSize: 0.015, // 0.6rem
    fontColor: new THREE.Color(0x000000)
});

// Assembly
sendButtonBlock.add(sendButtonText);
inputWrapperBlock.add(chatInputBlock, sendButtonBlock);
rootContainer.add(chatHistoryBlock, inputWrapperBlock);
```

### Mathematical Mapping & Constants

- **Base Conversion**: 1 CSS Pixel = `0.001` World Units (WU)
- **REM Conversion**: 1 rem = 16px = `0.016` WU
- **Spacing**: `gap: 12px` -> `0.012` WU
- **Border Radius**: `4px` -> `0.004` WU
- **Colors**:
  - `var(--neon-blue)`: `#00f3ff` -> `0x00f3ff`
  - `.input-wrapper` background: `rgba(255,255,255,0.03)` -> `0xffffff`, opacity `0.03`
  - `.input-wrapper` border: `rgba(0,243,255,0.2)` -> `0x00f3ff`, opacity `0.2`
