# Tests (manual + smoke)

This folder contains local smoke checks used while developing.

## Recommended "run all tests" flow

From repo root:

```powershell
.\scripts\run_all_tests.ps1
```

Default: **`tests/smoke_ops_imagine_tts.py`** only — ops auth → IMAGINE `/api/dream` → Chatterbox TTS → Piper fallback (matches the current stack).

Optional legacy bundle (older **STT → soul → MOUTH/TTS** pipeline; originally written when Turbo on `:8005` was the default; it still works and picks Turbo vs Chatterbox based on mouth backend):

```powershell
.\scripts\run_all_tests.ps1 -LegacySmoke
```

## Individual runs

```bash
python tests/smoke_ops_imagine_tts.py
python tests/smoke_stt_thinking_tts.py
python tests/test_stt_backend.py
```
