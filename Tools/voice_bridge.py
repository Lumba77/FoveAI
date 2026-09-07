#!/usr/bin/env python3
"""
FoveAI Voice Bridge — Talk to Devin/AI assistants with your voice on Linux.

Press Meta+H, speak, release — your speech is transcribed by Whisper
and typed directly into whatever window has focus (your terminal, chat,
browser, anything). No remote desktop needed.

Also supports webcam capture: press Meta+V to snap a photo and save it
so you can reference it, or Meta+C to copy a screenshot to clipboard.

Hotkeys:
  Meta+H (Super+H)  — Push to talk (hold & speak, release to type)
  Meta+J            — Toggle continuous VAD mode (hands-free)
  Meta+K            — Cancel current recording (discard)
  Meta+Q            — Quit

The transcribed text is typed via wtype (Wayland) or xdotool (X11).
On Wayland, if wtype fails, falls back to wl-copy (clipboard paste).

Requirements:
  sounddevice, pynput, numpy, faster-whisper (or use XRLF endpoint)
  System: wtype + wl-clipboard (Wayland) or xdotool + xclip (X11)
"""

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request

import numpy as np
import sounddevice as sd


# ── Device selection ─────────────────────────────────────────────────────────

def list_input_devices():
    """Print all available input devices and exit."""
    print("  Available audio input devices:\n")
    print(f"  {'IDX':>4}  {'NAME':<50}  {'CH':>3}")
    print(f"  {'---':>4}  {'-' * 50}  {'---':>3}")
    found = False
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0:
            found = True
            print(f"  {i:>4}  {dev['name']:<50.50}  {dev['max_input_channels']:>3}")
    if not found:
        print("  (no input devices found)")
    print("\n  Pass --device <IDX|name-substring> to select one.")
    sys.exit(0)


def resolve_device(device_arg):
    """Resolve a --device argument (index or name substring) to a device index.

    Returns None if device_arg is None (use default).
    Raises SystemExit on invalid selection.
    """
    if device_arg is None:
        return None

    # Try parsing as an integer index first
    try:
        idx = int(device_arg)
        try:
            dev = sd.query_devices(idx)
        except Exception:
            print(f"  [ERR] Device index {idx} not found.", flush=True)
            sys.exit(1)
        if dev["max_input_channels"] <= 0:
            print(f"  [ERR] Device {idx} ({dev['name']}) has no input channels.", flush=True)
            sys.exit(1)
        return idx
    except ValueError:
        pass

    # Match by name substring (case-insensitive)
    needle = device_arg.lower()
    matches = []
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0 and needle in dev["name"].lower():
            matches.append((i, dev["name"]))

    if not matches:
        print(f"  [ERR] No input device matching '{device_arg}'.", flush=True)
        print("  Use --list-devices to see available devices.", flush=True)
        sys.exit(1)
    if len(matches) > 1:
        print(f"  [ERR] Multiple input devices match '{device_arg}':", flush=True)
        for i, name in matches:
            print(f"    {i}: {name}", flush=True)
        print("  Specify a more precise name or use the index.", flush=True)
        sys.exit(1)

    idx, name = matches[0]
    print(f"  [MIC] Matched device: {idx}: {name}", flush=True)
    return idx


def device_name(device_index):
    """Return a human-readable name for a device index, or 'default'."""
    if device_index is None:
        return "default"
    try:
        return f"{device_index}: {sd.query_devices(device_index)['name']}"
    except Exception:
        return str(device_index)


# ── Config ──────────────────────────────────────────────────────────────────

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"
CHUNK_DURATION = 0.5
CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_DURATION)

# VAD
VAD_ENERGY_THRESHOLD = 300.0
VAD_SILENCE_FRAMES = 6   # ~3 seconds of silence to stop

# STT: use local faster-whisper or the XRLF endpoint
XRLF_STT_URL = "http://127.0.0.1:8403/ws"  # WS endpoint for STT
USE_LOCAL_WHISPER = True  # Use local faster-whisper if available
FALLBACK_TO_XRLF = True   # Fall back to XRLF WS endpoint if local fails

# ── State ───────────────────────────────────────────────────────────────────

class BridgeState:
    def __init__(self):
        self.recording = False
        self.continuous = False
        self.audio_buffer: list[np.ndarray] = []
        self.lock = threading.Lock()
        self.vad_silence_count = 0
        self.vad_was_speaking = False
        self.whisper_model = None
        self.transcribing = False

state = BridgeState()

# ── Whisper (local) ─────────────────────────────────────────────────────────

def load_local_whisper():
    """Load faster-whisper model (CPU, int8)."""
    try:
        from faster_whisper import WhisperModel
        cache_dirs = [
            os.getenv("HF_HUB_CACHE", ""),
            os.getenv("HF_HOME", ""),
            os.path.expanduser("~/.cache/huggingface/hub"),
        ]
        model_path = None
        for cache_dir in cache_dirs:
            if not cache_dir or not os.path.isdir(cache_dir):
                continue
            for candidate_name in ["faster-whisper-tiny", "faster-whisper-base.en"]:
                candidate = os.path.join(cache_dir, f"models--Systran--{candidate_name}")
                if os.path.isdir(candidate):
                    snapshots = os.path.join(candidate, "snapshots")
                    if os.path.isdir(snapshots):
                        for snap in os.listdir(snapshots):
                            snap_path = os.path.join(snapshots, snap)
                            if os.path.isdir(snap_path):
                                model_path = snap_path
                                break
                if model_path:
                    break
            if model_path:
                break

        if not model_path:
            print("  [Whisper] No cached model found, using 'tiny' (will download)", flush=True)
            model_path = "tiny"

        model = WhisperModel(model_path, device="cpu", compute_type="int8")
        print(f"  [Whisper] Local model loaded: {model_path}", flush=True)
        return model
    except Exception as e:
        print(f"  [Whisper] Local load failed: {e}", flush=True)
        return None

def transcribe_local(audio: np.ndarray) -> str:
    """Transcribe audio using local faster-whisper."""
    if state.whisper_model is None:
        return ""
    # faster-whisper expects float32 normalized
    samples = audio.astype(np.float32) / 32768.0
    segments, _ = state.whisper_model.transcribe(
        samples,
        language="en",
        beam_size=1,
        vad_filter=True,
        condition_on_previous_text=False,
    )
    text = " ".join(seg.text.strip() for seg in segments).strip()
    return text

# ── XRLF WS STT fallback ────────────────────────────────────────────────────

async def transcribe_via_xrlf(audio: np.ndarray) -> str:
    """Send audio to XRLF WebSocket for Whisper transcription."""
    import websockets
    try:
        async with websockets.connect(XRLF_STT_URL, max_size=10_000_000) as ws:
            await ws.send(json.dumps({"type": "start_recording"}))
            await ws.send(audio.astype(np.int16).tobytes())
            await ws.send(json.dumps({"type": "stop_recording"}))

            # Wait for transcription response
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=30)
                if isinstance(raw, str):
                    msg = json.loads(raw)
                    if msg.get("event") == "stt.result" or msg.get("type") == "stt.result":
                        return msg.get("payload", {}).get("text", "") or msg.get("text", "")
                    elif msg.get("event") == "chat.response":
                        # The WS auto-triggers chat — we just want the transcription
                        # but the handler sends audio to chat. Extract the user text.
                        return ""
                    elif msg.get("type") == "error":
                        print(f"  [XRLF STT] Error: {msg.get('message')}", flush=True)
                        return ""
    except Exception as e:
        print(f"  [XRLF STT] Failed: {e}", flush=True)
        return ""

# ── Type text into focused window ───────────────────────────────────────────

def type_text(text: str):
    """Type text into the currently focused window."""
    if not text:
        return

    session_type = os.environ.get("XDG_SESSION_TYPE", "x11")

    if session_type == "wayland":
        # Try wtype first
        if shutil.which("wtype"):
            try:
                subprocess.run(["wtype", text], check=True, timeout=5)
                print(f"  [TYPE] Typed via wtype: \"{text[:60]}...\"" if len(text) > 60 else f"  [TYPE] Typed via wtype: \"{text}\"", flush=True)
                return
            except Exception as e:
                print(f"  [TYPE] wtype failed: {e}, trying clipboard...", flush=True)

        # Fallback: wl-copy + wtype paste key
        if shutil.which("wl-copy") and shutil.which("wtype"):
            try:
                subprocess.run(["wl-copy", text], check=True, timeout=3)
                time.sleep(0.1)
                # Simulate Ctrl+V
                subprocess.run(["wtype", "-M", "ctrl", "v", "-m", "ctrl"], check=True, timeout=3)
                print(f"  [TYPE] Pasted via clipboard: \"{text[:60]}...\"" if len(text) > 60 else f"  [TYPE] Pasted: \"{text}\"", flush=True)
                return
            except Exception as e:
                print(f"  [TYPE] Clipboard paste failed: {e}", flush=True)

        # Last resort: just print to stdout
        print(f"\n  [VOICE] Transcribed (copy manually): {text}\n", flush=True)

    else:
        # X11: use xdotool
        if shutil.which("xdotool"):
            try:
                subprocess.run(["xdotool", "type", "--delay", "10", text], check=True, timeout=10)
                print(f"  [TYPE] Typed via xdotool: \"{text[:60]}...\"" if len(text) > 60 else f"  [TYPE] Typed: \"{text}\"", flush=True)
                return
            except Exception as e:
                print(f"  [TYPE] xdotool failed: {e}", flush=True)

        print(f"\n  [VOICE] Transcribed (copy manually): {text}\n", flush=True)

# ── Audio recording ─────────────────────────────────────────────────────────

def audio_callback(indata: np.ndarray, frames: int, time_info, status):
    """Called by sounddevice for each audio chunk."""
    if state.recording or state.continuous:
        with state.lock:
            state.audio_buffer.append(indata.copy())

            # VAD for continuous mode
            if state.continuous and not state.recording:
                energy = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2)))
                if energy > VAD_ENERGY_THRESHOLD:
                    state.vad_silence_count = 0
                    if not state.vad_was_speaking:
                        state.vad_was_speaking = True
                        print("  [VAD] Speech detected — recording...", flush=True)
                else:
                    if state.vad_was_speaking:
                        state.vad_silence_count += 1
                        if state.vad_silence_count >= VAD_SILENCE_FRAMES:
                            state.vad_was_speaking = False
                            state.vad_silence_count = 0
                            print("  [VAD] Silence — transcribing...", flush=True)
                            # Trigger transcription
                            threading.Thread(target=stop_and_transcribe, daemon=True).start()

def start_recording():
    """Start capturing audio."""
    with state.lock:
        state.audio_buffer = []
        state.recording = True
    print("  [MIC] ● Recording... (release Meta+H to transcribe)", flush=True)

def stop_and_transcribe():
    """Stop recording and transcribe."""
    with state.lock:
        state.recording = False
        if not state.audio_buffer:
            return
        audio_data = np.concatenate(state.audio_buffer, axis=0).flatten()
        state.audio_buffer = []

    duration = len(audio_data) / SAMPLE_RATE
    if duration < 0.3:
        print("  [MIC] Too short, discarded", flush=True)
        return

    print(f"  [MIC] ■ Captured {duration:.1f}s — transcribing...", flush=True)
    state.transcribing = True

    # Try local Whisper first
    text = ""
    if USE_LOCAL_WHISPER and state.whisper_model:
        try:
            text = transcribe_local(audio_data)
        except Exception as e:
            print(f"  [STT] Local error: {e}", flush=True)

    # Fallback to XRLF endpoint
    if not text and FALLBACK_TO_XRLF:
        try:
            loop = asyncio.new_event_loop()
            text = loop.run_until_complete(transcribe_via_xrlf(audio_data))
            loop.close()
        except Exception as e:
            print(f"  [STT] XRLF fallback error: {e}", flush=True)

    state.transcribing = False

    if text:
        # Clean up transcription
        text = text.strip()
        if text:
            print(f"  [STT] \"{text}\"", flush=True)
            type_text(text)
    else:
        print("  [STT] No speech detected", flush=True)

def cancel_recording():
    """Discard current recording."""
    with state.lock:
        state.recording = False
        state.audio_buffer = []
    print("  [MIC] ✕ Cancelled", flush=True)

# ── Hotkeys ─────────────────────────────────────────────────────────────────

def setup_hotkeys():
    """Set up global hotkeys."""
    from pynput import keyboard

    current_keys = set()

    def on_press(key):
        current_keys.add(key)

        is_meta = (keyboard.Key.cmd in current_keys or
                   keyboard.Key.cmd_l in current_keys or
                   keyboard.Key.cmd_r in current_keys)

        if not is_meta:
            return

        key_char = None
        if hasattr(key, 'char') and key.char:
            key_char = key.char.lower()

        # Meta+H — Push to talk
        if key_char == 'h':
            if not state.recording and not state.continuous and not state.transcribing:
                start_recording()

        # Meta+J — Toggle continuous VAD
        elif key_char == 'j':
            state.continuous = not state.continuous
            if state.continuous:
                print("\n  [MODE] ●● Continuous VAD ON — just talk\n", flush=True)
            else:
                print("\n  [MODE] ○○ Continuous mode OFF\n", flush=True)

        # Meta+K — Cancel recording
        elif key_char == 'k':
            cancel_recording()

        # Meta+Q — Quit
        elif key_char == 'q':
            print("\n  [EXIT] Quitting Voice Bridge...", flush=True)
            return False

    def on_release(key):
        current_keys.discard(key)

        # Release Meta+H — stop and transcribe
        if hasattr(key, 'char') and key.char and key.char.lower() == 'h':
            if state.recording:
                stop_and_transcribe()

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()
    return listener

# ── Main ────────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="FoveAI Voice Bridge — talk to your AI")
    parser.add_argument("--no-local-whisper", action="store_true", help="Use XRLF endpoint only")
    parser.add_argument("--no-xrlf-fallback", action="store_true", help="Local Whisper only")
    parser.add_argument("--device", type=str, default=None,
                        help="Audio input device: index (e.g. 3) or name substring (e.g. 'AUSDOM'). "
                             "Use --list-devices to see options. Default: system default input.")
    parser.add_argument("--list-devices", action="store_true",
                        help="List available audio input devices and exit.")
    args = parser.parse_args()

    if args.list_devices:
        list_input_devices()

    global USE_LOCAL_WHISPER, FALLBACK_TO_XRLF
    if args.no_local_whisper:
        USE_LOCAL_WHISPER = False
    if args.no_xrlf_fallback:
        FALLBACK_TO_XRLF = False

    # Resolve microphone device
    device_index = resolve_device(args.device)

    session_type = os.environ.get("XDG_SESSION_TYPE", "x11")
    print(f"""
  ╔══════════════════════════════════════════════════╗
  ║  FoveAI Voice Bridge — Talk to Your AI           ║
  ╠══════════════════════════════════════════════════╣
  ║  Meta+H  — Push to talk (hold & speak)          ║
  ║  Meta+J  — Toggle continuous VAD mode           ║
  ║  Meta+K  — Cancel recording                     ║
  ║  Meta+Q  — Quit                                  ║
  ╠══════════════════════════════════════════════════╣
  ║  Session: {session_type:<39s} ║
  ║  STT: {'local Whisper' if USE_LOCAL_WHISPER else 'XRLF endpoint':<42s} ║
  ║  Fallback: {'XRLF WS' if FALLBACK_TO_XRLF else 'none':<41s} ║
  ╚══════════════════════════════════════════════════╝
    """, flush=True)

    # Check typing tools
    if session_type == "wayland":
        has_wtype = shutil.which("wtype") is not None
        has_wlcopy = shutil.which("wl-copy") is not None
        if not has_wtype:
            print("  [WARN] wtype not found — install with: sudo dnf install wtype", flush=True)
        if not has_wlcopy:
            print("  [WARN] wl-copy not found — install with: sudo dnf install wl-clipboard", flush=True)
        if not has_wtype and not has_wlcopy:
            print("  [WARN] No typing method available — text will print to stdout only", flush=True)
    else:
        if not shutil.which("xdotool"):
            print("  [WARN] xdotool not found — install with: sudo dnf install xdotool", flush=True)

    # Load Whisper
    if USE_LOCAL_WHISPER:
        print("  [STT] Loading local Whisper...", flush=True)
        state.whisper_model = load_local_whisper()
        if state.whisper_model is None:
            if FALLBACK_TO_XRLF:
                print("  [STT] Falling back to XRLF endpoint", flush=True)
            else:
                print("  [STT] No STT available — exiting", flush=True)
                return

    # Start audio stream
    stream = sd.InputStream(
        device=device_index,
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype=DTYPE,
        blocksize=CHUNK_SAMPLES,
        callback=audio_callback,
    )
    stream.start()
    print(f"  [MIC] Listening on {device_name(device_index)} ({SAMPLE_RATE}Hz)", flush=True)
    print("  [READY] Press Meta+H and talk!\n", flush=True)

    # Start hotkeys
    listener = setup_hotkeys()

    # Keep running
    try:
        while True:
            await asyncio.sleep(0.1)
    except asyncio.CancelledError:
        pass
    finally:
        stream.stop()
        stream.close()
        listener.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n  [EXIT] Bye!", flush=True)
