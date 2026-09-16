#!/usr/bin/env python3
"""
FoveAI Desktop Talk — Talk to Alice from your desk, and let her see through your webcam.

Records audio from the default microphone, sends it to the XRLF WebSocket
(:8403) for Whisper transcription → Alice chat → Kokoro TTS, and plays
the response back through your speakers.

Also captures webcam frames and sends them as vision.frame events so
Alice can see what's in front of your camera.

Hotkeys:
  Meta+H (Super+H)  — Push to talk (hold and speak, release to send)
  Meta+J            — Toggle continuous mode (auto-VAD, hands-free)
  Meta+V            — Capture webcam frame → Alice sees (vision)
  Meta+B            — Toggle continuous vision (1 frame every 10s)
  Meta+K            — Stop playback / interrupt Alice
  Meta+Q            — Quit

Requirements:
  sounddevice, pynput, websockets, numpy, cv2 (opencv)
"""

import argparse
import asyncio
import base64
import json
import struct
import sys
import threading
import time
import wave
import io
from pathlib import Path

import cv2
import numpy as np
import sounddevice as sd
import websockets


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

WS_URL = "ws://127.0.0.1:8403/ws"
SAMPLE_RATE = 16000      # Whisper expects 16kHz
CHANNELS = 1
DTYPE = "int16"
CHUNK_DURATION = 0.5     # seconds per chunk
CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_DURATION)

# VAD thresholds for continuous mode
VAD_ENERGY_THRESHOLD = 500.0
VAD_SILENCE_FRAMES = 8   # ~4 seconds of silence to stop

# TTS playback
TTS_SAMPLE_RATE = 24000  # Kokoro outputs 24kHz

# Vision config
WEBCAM_INDEX = 0  # Default camera (0=desk, 1=kitchen, 2=living, 3=garage, 4=garden)
VISION_FRAME_INTERVAL = 10.0  # seconds between auto-vision frames
VISION_JPEG_QUALITY = 70
VISION_FRAME_WIDTH = 640
VISION_FRAME_HEIGHT = 360

# ── State ───────────────────────────────────────────────────────────────────

class TalkState:
    def __init__(self):
        self.recording = False
        self.continuous = False
        self.audio_buffer: list[np.ndarray] = []
        self.ws = None
        self.connected = False
        self.speaking = False
        self.tts_audio = bytearray()
        self.lock = threading.Lock()
        self.loop = None
        self.vad_silence_count = 0
        self.vad_was_speaking = False
        # Vision
        self.cap = None
        self.continuous_vision = False
        self.last_vision_frame = 0.0

state = TalkState()

# ── Audio recording ─────────────────────────────────────────────────────────

def audio_callback(indata: np.ndarray, frames: int, time_info, status):
    """Called by sounddevice for each audio chunk."""
    if state.recording or state.continuous:
        with state.lock:
            state.audio_buffer.append(indata.copy())

            # In continuous mode, check VAD
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
                            print("  [VAD] Silence — sending...", flush=True)
                            # Trigger send in the event loop
                            if state.loop:
                                asyncio.run_coroutine_threadsafe(send_and_transcribe(), state.loop)

def start_recording():
    """Start capturing audio."""
    with state.lock:
        state.audio_buffer = []
        state.recording = True
    print("  [MIC] ● Recording... (release Meta+H to send)", flush=True)

def stop_recording_and_send():
    """Stop capturing and send audio to Whisper via WebSocket."""
    with state.lock:
        state.recording = False
        if not state.audio_buffer:
            return
        audio_data = np.concatenate(state.audio_buffer, axis=0).flatten()
        state.audio_buffer = []

    duration = len(audio_data) / SAMPLE_RATE
    print(f"  [MIC] ■ Captured {duration:.1f}s — sending to Alice...", flush=True)

    if state.loop:
        asyncio.run_coroutine_threadsafe(
            send_audio_for_transcription(audio_data), state.loop
        )

# ── WebSocket communication ─────────────────────────────────────────────────

async def connect_ws():
    """Connect to the XRLF WebSocket server."""
    try:
        state.ws = await websockets.connect(WS_URL, max_size=10_000_000)
        state.connected = True
        print(f"  [WS] Connected to {WS_URL}", flush=True)
        return True
    except Exception as e:
        print(f"  [WS] Connection failed: {e}", flush=True)
        state.connected = False
        return False

async def send_audio_for_transcription(audio: np.ndarray):
    """Send raw PCM audio to the WS server for Whisper transcription."""
    if not state.connected or state.ws is None:
        print("  [WS] Not connected, reconnecting...", flush=True)
        if not await connect_ws():
            return

    try:
        # Send start_recording signal
        await state.ws.send(json.dumps({"type": "start_recording"}))

        # Send raw 16-bit PCM bytes
        pcm_bytes = audio.astype(np.int16).tobytes()
        await state.ws.send(pcm_bytes)

        # Send stop_recording signal
        await state.ws.send(json.dumps({"type": "stop_recording"}))

        print("  [WS] Audio sent — waiting for Alice...", flush=True)

        # Listen for response
        await listen_for_response()

    except Exception as e:
        print(f"  [WS] Send error: {e}", flush=True)
        state.connected = False

async def send_and_transcribe():
    """Wrapper for VAD-triggered send."""
    with state.lock:
        if not state.audio_buffer:
            return
        audio_data = np.concatenate(state.audio_buffer, axis=0).flatten()
        state.audio_buffer = []

    duration = len(audio_data) / SAMPLE_RATE
    if duration < 0.3:
        return  # Too short, ignore

    print(f"  [VAD] Sending {duration:.1f}s to Alice...", flush=True)
    await send_audio_for_transcription(audio_data)

async def listen_for_response():
    """Listen for chat response + TTS audio from the WebSocket."""
    state.tts_audio = bytearray()
    state.speaking = False

    try:
        async for raw in state.ws:
            if isinstance(raw, bytes):
                # TTS audio chunk
                state.tts_audio.extend(raw)
                if not state.speaking:
                    state.speaking = True
                    print("  [TTS] ♪ Alice is speaking...", flush=True)

            elif isinstance(raw, str):
                msg = json.loads(raw)

                # Chat text response
                if msg.get("event") == "chat.response" or msg.get("type") == "chat.response":
                    text = msg.get("payload", {}).get("text", "") or msg.get("text", "")
                    if text:
                        print(f"\n  Alice: {text}\n", flush=True)

                # TTS end signal
                elif msg.get("type") == "end":
                    if state.tts_audio:
                        play_tts_audio(bytes(state.tts_audio))
                        state.tts_audio = bytearray()
                    state.speaking = False
                    break

                # TTS ready/config
                elif msg.get("type") == "ready":
                    continue

                # Error
                elif msg.get("type") == "error":
                    print(f"  [ERR] {msg.get('message', 'unknown')}", flush=True)
                    break

                # STT transcription result
                elif msg.get("event") == "stt.result" or msg.get("type") == "stt.result":
                    text = msg.get("payload", {}).get("text", "") or msg.get("text", "")
                    if text:
                        print(f"  [STT] You said: \"{text}\"", flush=True)

                # Streaming token
                elif msg.get("event") == "chat.token" or msg.get("type") == "chat.token":
                    token = msg.get("payload", {}).get("text", "") or msg.get("text", "")
                    print(token, end="", flush=True)

    except websockets.exceptions.ConnectionClosed:
        print("  [WS] Connection closed", flush=True)
        state.connected = False

def play_tts_audio(pcm_bytes: bytes):
    """Play TTS audio through the default output device."""
    try:
        samples = np.frombuffer(pcm_bytes, dtype=np.int16)
        if len(samples) == 0:
            return
        # Kokoro outputs 24kHz 16-bit mono
        sd.play(samples, TTS_SAMPLE_RATE, device=sd.default.device[1])
        print(f"  [TTS] Playing {len(samples)/TTS_SAMPLE_RATE:.1f}s audio", flush=True)
    except Exception as e:
        print(f"  [TTS] Playback error: {e}", flush=True)

def stop_playback():
    """Stop TTS playback."""
    sd.stop()
    state.speaking = False
    print("  [TTS] ■ Stopped", flush=True)

# ── Vision (webcam → Alice) ─────────────────────────────────────────────────

def init_webcam():
    """Initialize the webcam for vision capture."""
    state.cap = cv2.VideoCapture(WEBCAM_INDEX)
    state.cap.set(cv2.CAP_PROP_FRAME_WIDTH, VISION_FRAME_WIDTH)
    state.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, VISION_FRAME_HEIGHT)
    if state.cap.isOpened():
        print(f"  [CAM] Webcam {WEBCAM_INDEX} ready ({VISION_FRAME_WIDTH}x{VISION_FRAME_HEIGHT})", flush=True)
    else:
        print(f"  [CAM] No webcam available — vision disabled", flush=True)
        state.cap = None

def capture_webcam_frame() -> str | None:
    """Capture a single frame from the webcam, return as base64 JPEG."""
    if state.cap is None or not state.cap.isOpened():
        return None
    ret, frame = state.cap.read()
    if not ret:
        return None
    _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, VISION_JPEG_QUALITY])
    return base64.b64encode(buf.tobytes()).decode()

async def send_vision_frame():
    """Capture a webcam frame and send it to Alice as a vision.frame event."""
    if not state.connected or state.ws is None:
        print("  [WS] Not connected, reconnecting...", flush=True)
        if not await connect_ws():
            return

    b64 = capture_webcam_frame()
    if b64 is None:
        print("  [CAM] No frame captured", flush=True)
        return

    msg = {
        "event": "vision.frame",
        "payload": {
            "image_base64": b64,
            "perspective": "desk",
            "direction": "webcam",
        },
    }
    await state.ws.send(json.dumps(msg))
    print(f"  [VISION] Frame sent to Alice ({len(b64)} bytes) — she's looking...", flush=True)

    # Listen for response
    await listen_for_response()

def maybe_send_auto_vision():
    """In continuous vision mode, send a frame every VISION_FRAME_INTERVAL seconds."""
    if not state.continuous_vision:
        return
    now = time.time()
    if now - state.last_vision_frame >= VISION_FRAME_INTERVAL:
        state.last_vision_frame = now
        if state.loop:
            asyncio.run_coroutine_threadsafe(send_vision_frame(), state.loop)

# ── Hotkey handler ──────────────────────────────────────────────────────────

def on_hotkey_press(key):
    """Handle hotkey presses."""
    pass  # We use combo detection

def setup_hotkeys():
    """Set up global hotkeys using pynput."""
    from pynput import keyboard

    current_keys = set()

    def on_press(key):
        current_keys.add(key)

        # Meta+H — Push to talk
        if keyboard.Key.cmd in current_keys or keyboard.Key.cmd_l in current_keys:
            if key == keyboard.KeyCode.from_char('h') or key == keyboard.KeyCode.from_char('H'):
                if not state.recording and not state.continuous:
                    start_recording()

        # Meta+J — Toggle continuous mode
        if keyboard.Key.cmd in current_keys or keyboard.Key.cmd_l in current_keys:
            if key == keyboard.KeyCode.from_char('j') or key == keyboard.KeyCode.from_char('J'):
                state.continuous = not state.continuous
                if state.continuous:
                    print("\n  [MODE] ●● Continuous VAD mode ON — just talk\n", flush=True)
                else:
                    print("\n  [MODE] ○○ Continuous mode OFF\n", flush=True)

        # Meta+K — Stop playback
        if keyboard.Key.cmd in current_keys or keyboard.Key.cmd_l in current_keys:
            if key == keyboard.KeyCode.from_char('k') or key == keyboard.KeyCode.from_char('K'):
                stop_playback()

        # Meta+V — Capture webcam frame → Alice sees
        if keyboard.Key.cmd in current_keys or keyboard.Key.cmd_l in current_keys:
            if key == keyboard.KeyCode.from_char('v') or key == keyboard.KeyCode.from_char('V'):
                print("\n  [VISION] ● Capturing webcam frame for Alice...", flush=True)
                if state.loop:
                    asyncio.run_coroutine_threadsafe(send_vision_frame(), state.loop)

        # Meta+B — Toggle continuous vision
        if keyboard.Key.cmd in current_keys or keyboard.Key.cmd_l in current_keys:
            if key == keyboard.KeyCode.from_char('b') or key == keyboard.KeyCode.from_char('B'):
                state.continuous_vision = not state.continuous_vision
                if state.continuous_vision:
                    print(f"\n  [VISION] ●● Continuous vision ON — Alice sees every {VISION_FRAME_INTERVAL}s\n", flush=True)
                else:
                    print("\n  [VISION] ○○ Continuous vision OFF\n", flush=True)

        # Meta+1..5 — Switch webcam for vision
        if keyboard.Key.cmd in current_keys or keyboard.Key.cmd_l in current_keys:
            if hasattr(key, 'char') and key.char and key.char in '12345':
                cam_id = int(key.char) - 1
                global WEBCAM_INDEX
                WEBCAM_INDEX = cam_id
                if state.cap:
                    state.cap.release()
                init_webcam()
                print(f"\n  [CAM] Switched to camera {cam_id}\n", flush=True)

        # Meta+Q — Quit
        if keyboard.Key.cmd in current_keys or keyboard.Key.cmd_l in current_keys:
            if key == keyboard.KeyCode.from_char('q') or key == keyboard.KeyCode.from_char('Q'):
                print("\n  [EXIT] Quitting FoveAI Desktop Talk...", flush=True)
                sd.stop()
                if state.ws:
                    asyncio.run_coroutine_threadsafe(state.ws.close(), state.loop)
                # Stop the listener
                return False

    def on_release(key):
        current_keys.discard(key)

        # Release Meta+H — stop and send
        if key == keyboard.KeyCode.from_char('h') or key == keyboard.KeyCode.from_char('H'):
            if state.recording:
                stop_recording_and_send()

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()
    return listener

# ── Main ────────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="FoveAI Desktop Talk — talk & see Alice")
    parser.add_argument("--device", type=str, default=None,
                        help="Audio input device: index (e.g. 3) or name substring (e.g. 'AUSDOM'). "
                             "Use --list-devices to see options. Default: system default input.")
    parser.add_argument("--list-devices", action="store_true",
                        help="List available audio input devices and exit.")
    args = parser.parse_args()

    if args.list_devices:
        list_input_devices()

    # Resolve microphone device
    device_index = resolve_device(args.device)

    print("""
  ╔══════════════════════════════════════════════════╗
  ║     FoveAI Desktop Talk — Talk & See Alice        ║
  ╠══════════════════════════════════════════════════╣
  ║  Meta+H  — Push to talk (hold & speak)          ║
  ║  Meta+J  — Toggle continuous VAD mode           ║
  ║  Meta+V  — Capture webcam → Alice sees          ║
  ║  Meta+B  — Toggle continuous vision (10s)       ║
  ║  Meta+1-5— Switch camera (desk/kitchen/etc)     ║
  ║  Meta+K  — Stop Alice's playback                ║
  ║  Meta+Q  — Quit                                  ║
  ╚══════════════════════════════════════════════════╝
    """, flush=True)

    state.loop = asyncio.get_event_loop()

    # Connect to WebSocket
    await connect_ws()

    # Initialize webcam for vision
    init_webcam()

    # Start audio recording stream
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

    # Start hotkey listener
    listener = setup_hotkeys()

    # Keep running
    try:
        while True:
            maybe_send_auto_vision()
            await asyncio.sleep(0.1)
    except asyncio.CancelledError:
        pass
    finally:
        stream.stop()
        stream.close()
        sd.stop()
        if state.cap:
            state.cap.release()
        if state.ws:
            await state.ws.close()
        listener.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n  [EXIT] Bye!", flush=True)
