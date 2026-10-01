# LUMAX Chrome Extension — Setup Guide

## What This Does
A Chrome Extension that lets you control LUMAX from the browser:
- Start/stop services (Soul, Memory, Creative, TTS, WebUI)
- Detect and launch LLM backends (llama-cpp, LM Studio, Ollama, vLLM)
- Run dev commands (npm build, git pull)
- All without opening a terminal

## Setup Steps (in order!)

### Step 1: Get the latest code
```powershell
cd C:\Users\lumba\Program\LUMAX
git pull
```

### Step 2: Make sure the unified venv exists
The Chrome Extension and WebUI server both need the unified Python venv (FastAPI, httpx, etc.).
```powershell
# Check if it exists:
dir .venv\Scripts\python.exe

# If missing, create it:
python -m venv .venv
.venv\Scripts\pip install fastapi uvicorn httpx python-dotenv
```

> **No need to manually activate it** — `lumax_host.bat` and `Start_LUMAX.ps1` find it automatically.

### Step 3: Build the XR Vessel (Web UI)
```powershell
cd Frontend\XR_Vessel
npm install   # Only needed first time or when package.json changes
npm run build
```

### Step 4: Load the Chrome Extension
1. Open Chrome → go to `chrome://extensions/`
2. Enable **Developer mode** (top right toggle)
3. Click **Load unpacked**
4. Select the folder: `C:\Users\lumba\Program\LUMAX\frontend\ChromeExtension`
5. **Copy the Extension ID** — it looks like `abcdefghijklmnopqrstuvwxyz123456`
   (You'll see it under the extension name after loading)

### Step 5: Register the native messaging host
```powershell
# Replace YOUR_EXTENSION_ID with the ID from Step 3
$env:LUMAX_EXT_ID = "YOUR_EXTENSION_ID"
powershell -ExecutionPolicy Bypass -File Frontend\ChromeExtension\native\install_host.ps1
```

After running this, you'll see:
```
[OK] Manifest updated with absolute path: ...\lumax_host.bat
[OK] Registry key created: HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.lumax.lumax_host
[OK] Native messaging host registered!
```

### Step 6: Reload the extension
Go back to `chrome://extensions/` and click the **↻ Reload** button on the LUMAX extension.

### Step 7: Try it!
1. Click the LUMAX icon in your Chrome toolbar
2. Click **🔍 Detect Installed** to scan for LLM backends
3. Click **▶ START LUMAX** to boot all services
4. Click **⟳ Refresh Status** to see what's running

## Troubleshooting

### "Native host error" in popup
- Make sure you ran `install_host.ps1` with the correct extension ID
- Check that Python is in your PATH: `python --version`
- Reload the extension after running install

### Fonts look weird
- The popup needs internet to load Google Fonts (Orbitron, Share Tech Mono)
- If offline, it falls back to Segoe UI — still readable

### Extension ID changes after reload
- If you loaded the extension as "unpacked", the ID is stable as long as you
  don't delete and re-add it. Just reload (↻), don't remove and re-load.

### npm build button doesn't work
- The native host runs `npm run build` in `frontend/XR_Vessel`
- Make sure you've done `npm install` at least once in that directory