# Deploy & Service Upgrade Plan

## Part A: Fix `deploy` — Base64 Encoding + Bug Fix

### Current Issues
1. **Indentation bug** (lines 446-450): The `with open(...)` block is at the same indentation as the `for` loop, so only the last module gets written
2. **Raw string fragility**: `r'''...'''` breaks on backslashes/quotes in TypeScript code
3. **Unused import**: `base64` imported but never used
4. **No error handling**: No try/except around file writes
5. **No verification**: Unlike `gen_ts`, no post-write size check
6. **Double backslash**: `Frontend\\XR_Vessel` has escaped backslash

### Solution
Convert all 4 TypeScript modules to base64-encoded strings (matching `gen_ts` pattern), fix the loop indentation, add error handling and verification.

### New `deploy` structure:
```python
"""Deploy WebSearch.ts, CommsBridge.ts, VoiceClone.ts, GameController.ts"""
import os, base64

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    'Frontend', 'XR_Vessel', 'src', 'senses')

modules_b64 = {
    "WebSearch.ts": "BASE64_ENCODED_CONTENT_HERE",
    "CommsBridge.ts": "BASE64_ENCODED_CONTENT_HERE",
    "VoiceClone.ts": "BASE64_ENCODED_CONTENT_HERE",
    "GameController.ts": "BASE64_ENCODED_CONTENT_HERE",
}

os.makedirs(BASE, exist_ok=True)

for fn, b64_content in modules_b64.items():
    fp = os.path.join(BASE, fn)
    try:
        content = base64.b64decode(b64_content)
        with open(fp, 'wb') as f:
            f.write(content)
        size = os.path.getsize(fp)
        print(f'  ✓ {fn}: {size} bytes')
    except Exception as e:
        print(f'  ✗ {fn}: FAILED — {e}')

print(f'\nAll {len(modules_b64)} modules deployed.')
```

### Base64 Encoding
Each TypeScript module's content will be base64-encoded (UTF-8). The encoding will be done by reading the existing raw strings from the current `deploy` file, extracting the TypeScript content, and encoding it.

---

## Part B: Upgrade `LumaxService.ps1` — Diamond Concordia Services

### Current Legacy Services (lines 153-172)
| Service | Path | Port | Status |
|---------|------|------|--------|
| SOUL | `backend\Cognition\compagent.py` | 8000 | Keep (fix case) |
| EARS | `Frontend\Physical_Interface\body_interface:app` | 8001 | 🔴 Remove |
| MEMORY | `backend\Memory\memory_service:app` | 8002 | 🔴 Remove |
| MOUTH | `Frontend\Physical_Interface\turbochat_server:app` | 8004 | 🔴 Remove |
| OLLAMA | `backend\Cognition\ollama_serv.py` | 11434 | 🔴 Remove |
| WEBUI | `Frontend\Web_Vessel\web_app.py` | 8080 | 🔴 Remove |
| SENTRY | `Mind\librarian_daemon.py` | — | 🔴 Remove |
| CREATIVE | `backend\Creativity\creative_service:app` | 8003 | 🔴 Remove |
| CODER | `backend\Cognition\soul_coder_api:app` | 11435 | 🔴 Remove |

### New Diamond Concordia Services
| Service | Path | Port | Profiles |
|---------|------|------|----------|
| SOVEREIGN | `Backend\Cognition\compagent.py` | 8000 | AWAKE, LIVE, CODE, CREATIVE |
| XR_API | `Frontend\XR_Vessel\xr_app.py` | 8080 | AWAKE, LIVE, CODE, CREATIVE |
| MOTOR | `Backend\Cognition\motor_daemon.py` | 8110 | AWAKE, LIVE, CODE, CREATIVE |
| TOKENSLAYER | `Forge\scratch\TokenSlayer\standalone\tokenslayer.js` | 8103 | AWAKE, LIVE, CODE, CREATIVE, SLEEP |
| STARDUST | `Backend\Memory\stardust_encoder.py` | 8109 | AWAKE, LIVE, CODE, CREATIVE, SLEEP |
| VITE_DEV | (Node process) | 5176 | AWAKE, LIVE, CODE, CREATIVE |

### State Profiles (preserved from legacy)
- **AWAKE**: Full interaction mode — all services active
- **SLEEP**: Minimal services — TokenSlayer + Stardust for background processing
- **LIVE**: XR-focused — Sovereign + XR_API + MOTOR + VITE_DEV
- **CODE**: Development mode — Sovereign + TokenSlayer + Stardust
- **CREATIVE**: Generation mode — Sovereign + Stardust

### Changes to `$Services` hash:
```powershell
$Services = @{
    "SOVEREIGN"   = @{ Path="Backend\Cognition"; Port=8000; Profiles=@('AWAKE','LIVE','CODE','CREATIVE') }
    "XR_API"      = @{ Path="Frontend\XR_Vessel"; Port=8080; Profiles=@('AWAKE','LIVE','CODE','CREATIVE') }
    "MOTOR"       = @{ Path="Backend\Cognition"; Port=8110; Profiles=@('AWAKE','LIVE','CODE','CREATIVE') }
    "TOKENSLAYER" = @{ Path="Forge\scratch\TokenSlayer\standalone"; Port=8103; Profiles=@('AWAKE','LIVE','CODE','CREATIVE','SLEEP') }
    "STARDUST"    = @{ Path="Backend\Memory"; Port=8109; Profiles=@('AWAKE','LIVE','CODE','CREATIVE','SLEEP') }
    "VITE_DEV"    = @{ Path="Frontend\XR_Vessel"; Port=5176; Profiles=@('AWAKE','LIVE','CODE','CREATIVE') }
}
$Services["SOVEREIGN"].Cmd = "compagent.py"
$Services["XR_API"].Cmd = "xr_app.py"
$Services["MOTOR"].Cmd = "motor_daemon.py"
$Services["TOKENSLAYER"].Cmd = "tokenslayer.js"  # Node process
$Services["STARDUST"].Cmd = "-m uvicorn stardust_encoder:app --host 0.0.0.0 --port 8109"
$Services["VITE_DEV"].Cmd = "vite"  # npm run dev
```

### Changes to `LumaxGuardian.ps1`:
- Update port check list (line 78): `@(8000, 8080, 8110, 8103, 8109, 5176)`
- Update zombie process detection patterns to match new service names

### Preserved Features (NOT changed):
- State cycling (AWAKE/SLEEP/CREATIVE/LIVE/CODE)
- Wake ritual via `/compagent`
- VAD bridge
- GPU arbitration
- Crash reporting
- Tray watchdog
- Backup system
- Singleton lock

---

## Part C: Temperature Banner

The "1.0 temperature" line in `Start_Concordia.PS1` (line 14) is philosophical flavor text — part of the Dead Sure Coding identity. It stays as-is. No changes needed.

---

## Implementation Order
1. Fix `deploy` (base64 encode + indentation fix)
2. Update `LumaxService.ps1` service definitions
3. Update `LumaxGuardian.ps1` port checks