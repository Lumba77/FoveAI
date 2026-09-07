# LUMAX Matchbox // WebXR Vessel

High-performance, sovereign Mixed Reality interface for LUMAX.

## 🧩 Matchbox Sovereign Architecture
The Matchbox is a browser-native "brain" and "body" that runs directly in your headset or browser via WebGPU.

- **Local Brain:** Llama-3.2-1B-Instruct running via `webllm`.
- **Local Memory:** Persistent interaction history stored in `Dexie.js` (IndexedDB).
- **Visual Dissolution:** Custom NoiseShader for real-time avatar "melting" into the environment.
- **Privacy Veil:** All heretical and personal dialogue stays in the browser's local memory.

## 🚀 Quick Start (Sovereign Flow)

1.  **Install dependencies:**
    ```bash
    npm install
    ```

2.  **Start dev server:**
    ```bash
    npm run dev
    ```

3.  **Launch Secure Tunnel (Recommended):**
    To enable WebXR and WebGPU on your Quest or remote devices without certificate errors:
    ```bash
    cloudflared tunnel --url http://localhost:5176
    ```

4.  **Access:**
    - Open the `trycloudflare.com` URL on your device.
    - Click **START DESKTOP** (PC) or **START AR** (Quest).
    - Watch the Dashboard log for the **Neural Link** initialization (0% - 100%).

## Project Structure
- `src/main.ts`: Entry point and sovereign hub rewiring.
- `src/network/LocalBrain.ts`: WebLLM initialization and local inference.
- `src/network/LocalMemory.ts`: Dexie.js database for sovereign persistence.
- `src/avatar/AvatarManager.ts`: VRM handling + Visual Melting Shader.
- `src/components/Dashboard.ts`: "LUMAX Lite" aesthetic MR console.
- `public/avatar.vrm`: The active avatar model.
