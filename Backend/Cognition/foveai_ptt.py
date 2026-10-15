#!/usr/bin/env python3
"""foveai_ptt.py — Global Push-To-Talk for FoveAI (Vocal mode everywhere).

Hold LEFT CTRL (configurable) in any app → talk → release:
    mic → :8401 STT (faster-whisper WS) → text
    text → :8400 /v1/chat/completions (juggle/local/cloud — current MODE)
    answer → :8411 Kokoro /say (spoken out loud, speakers)
    transcript + answer → desktop notification (dunst) + agent memory

Standard vocal mode for the whole desktop — not tied to any one app.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path

DISPLAY = os.environ.get("DISPLAY", ":0")
os.environ.setdefault("DISPLAY", DISPLAY)

STT_URL = os.environ.get("FOVEAI_PTT_STT", "ws://127.0.0.1:8401")
BACKEND = os.environ.get("FOVEAI_PTT_BACKEND", "http://127.0.0.1:8400")
TTS_URL = os.environ.get("FOVEAI_PTT_TTS", "http://127.0.0.1:8411/say")
AUTH_TOKEN = os.environ.get("FOVEAI_PTT_TOKEN", "prompt_kiosk_agent")
JUGGLE_MODEL = os.environ.get("FOVEAI_PTT_MODEL", "juggle")
KEY_HOLD = "ctrl_l"          # pynput KeyCode/Key name for push-to-talk
# Capture: Chrome Remote Desktop hijacks the default PulseAudio socket with a
# private server that only has a monitor source — recording "pulse" there yields
# pure silence, which is why PTT never heard anything. Talk to the real session
# socket and name the live mic explicitly.
REC_SOCK = os.environ.get("FOVEAI_PTT_PULSE", f"unix:/run/user/{os.getuid()}/pulse/native")
REC_DEV = os.environ.get(
    "FOVEAI_PTT_REC_DEV",
    "alsa_input.usb-HD_Web_Camera_HD_Web_Camera_Ucamera001-02.mono-fallback")
TMP_WAV = Path("/tmp/foveai_ptt_turn.wav")
TMP_WEBM = Path("/tmp/foveai_ptt_turn.webm")

# Rolling voice conversation — Jen must remember what was just said.
HISTORY_TURNS = int(os.environ.get("FOVEAI_PTT_HISTORY", "8"))
_history: list[dict] = []


def notify(body: str, title: str = "FoveAI Voice") -> None:
    try:
        subprocess.Popen(
            ["notify-send", "-a", "FoveAI", title, body],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env={**os.environ, "DISPLAY": DISPLAY})
    except Exception:
        pass


def speak(text: str) -> None:
    """Kokoro mouth :8411 — spoken out loud on the speakers."""
    import urllib.request
    body = json.dumps({"text": text[:400]}).encode()
    try:
        req = urllib.request.Request(TTS_URL, data=body,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=60).read()
    except Exception as e:
        notify(f"TTS miss: {e}", "FoveAI Voice")


def ask_jen(prompt: str) -> str:
    """One chat completion through the foveated proxy (current MODE dials).

    Carries the rolling voice conversation so Jen stays in context instead of
    answering every turn blind. HISTORY_TURNS pairs are kept; the oldest
    user turn is summarised away by the proxy's own compaction.
    """
    import urllib.request
    _history.append({"role": "user", "content": prompt})
    messages = list(_history)
    body = json.dumps({
        "model": JUGGLE_MODEL,
        "messages": messages,
        "stream": False,
    }).encode()
    req = urllib.request.Request(
        f"{BACKEND}/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {AUTH_TOKEN}"})
    try:
        with urllib.request.urlopen(req, timeout=170) as r:
            d = json.load(r)
            reply = (d["choices"][0]["message"].get("content") or "").strip()
            _history.append({"role": "assistant", "content": reply})
            del _history[:-2 * HISTORY_TURNS]
            return reply
    except Exception as e:
        _history.pop()  # don't bank a failed turn
        return f"(backend miss: {e})"


_mic_cache: tuple[float, str] = (0.0, "")


def pick_live_mic(probe: bool = False) -> str:
    """Best capture device on the REAL session socket.

    Chrome Remote Desktop's private server hides every microphone, so we ask
    the session's own PipeWire. With probe=True each candidate is sampled and
    the first one carrying actual signal wins — which also picks up the Quest
    mic whenever Horizon is running.
    """
    global _mic_cache
    import time as _t
    if not probe and _mic_cache[1] and _t.time() - _mic_cache[0] < 60:
        return _mic_cache[1]
    env = {**os.environ, "PULSE_SERVER": REC_SOCK}
    try:
        out = subprocess.run(["pactl", "list", "short", "sources"], capture_output=True,
                             text=True, timeout=5, env=env).stdout
    except Exception:
        return REC_DEV
    names = [ln.split("\t")[1] for ln in out.splitlines()[1:]
             if len(ln.split("\t")) > 1 and ln.split("\t")[1].startswith("alsa_input")]
    if not names:
        return REC_DEV
    if not probe:
        _mic_cache = (_t.time(), REC_DEV if REC_DEV in names else names[0])
        return _mic_cache[1]
    for name in names:
        probe_wav = TMP_WAV.with_name("micprobe.wav")
        try:
            subprocess.run(["parecord", f"--device={name}", "--format=s16le",
                            "--rate=16000", "--channels=1", "--file-format=wav",
                            str(probe_wav)], capture_output=True, timeout=4, env=env)
            raw = probe_wav.read_bytes()
            import array
            a = array.array("h"); a.frombytes(raw[44:])
            if a and max(abs(x) for x in a) > 150:
                _mic_cache = (_t.time(), name)
                return name
        except Exception:
            continue
    _mic_cache = (_t.time(), REC_DEV)
    return REC_DEV


def _arecord(seconds_hint: float | None, stop_event: threading.Event) -> float:
    """parecord → wav from the live mic; stops when stop_event set."""
    env = {**os.environ, "PULSE_SERVER": REC_SOCK}
    dev = pick_live_mic()
    cmd = ["parecord", f"--device={dev}", "--format=s16le", "--rate=16000",
           "--channels=1", "--file-format=wav", str(TMP_WAV)]
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         env=env)
    t0 = time.time()
    while p.poll() is None and not stop_event.is_set():
        time.sleep(0.05)
    if p.poll() is None:
        p.terminate()
        try:
            p.wait(timeout=2)
        except subprocess.TimeoutExpired:
            p.kill()
    dur = time.time() - t0

    # Dead mic (CRD socket, unplugged interface, muted device) — try another.
    raw = TMP_WAV.read_bytes()
    import array
    a = array.array("h"); a.frombytes(raw[44:] if raw[:4] == b"RIFF" else raw)
    if (not a or max(abs(x) for x in a) < 120) and dev != REC_DEV:
        alt = pick_live_mic(probe=True)
        if alt != dev:
            stop_rec = threading.Event()
            return _arecord(seconds_hint, stop_rec)
    return dur


def wav_to_stt() -> str:
    """wav PCM → :8401 native WS protocol (raw chunks, silence finalize,
    final transcript from the `transcription`/`text` message)."""
    import websockets  # system or venv
    try:
        import numpy  # optional: only present in the venv interpreter
    except Exception:
        pass

    async def run() -> str:
        frames = open(TMP_WAV, "rb").read()
        # strip 44-byte canonical WAV header
        pcm = frames[44:]
        chunk = 3200  # 200ms @16kHz/16bit
        async with websockets.connect(f"{STT_URL}/ws") as ws:
            await asyncio.wait_for(ws.recv(), 3)  # ready handshake
            for i in range(0, len(pcm), chunk):
                await ws.send(pcm[i:i+chunk])
                await asyncio.sleep(0.02)
            # force finalize ({"type":"stop"} → server transcribes buffer)
            await ws.send(json.dumps({"type": "stop"}))
            deadline = time.time() + 40   # whisper on a busy GPU can take ~10-15s
            while time.time() < deadline:
                try:
                    msg = await asyncio.wait_for(ws.recv(), 20)
                    d = json.loads(msg) if isinstance(msg, str) else {}
                    t = d.get("type", "")
                    if t in ("transcription", "final", "text"):
                        return d.get("text") or d.get("transcription") or ""
                except asyncio.TimeoutError:
                    break
        return ""

    try:
        return asyncio.run(run())
    except Exception as e:
        notify(f"STT miss: {e}")
        return ""


# ── push-to-talk loop ───────────────────────────────────────────────────
def ptt_loop() -> None:
    from pynput import keyboard
    hold_key = getattr(keyboard.Key, KEY_HOLD, keyboard.Key.ctrl_l)
    pressed = threading.Event()
    stop_rec = threading.Event()

    def on_press(key):
        if key == hold_key and not pressed.is_set():
            pressed.set()
            stop_rec.clear()

    def on_release(key):
        if key == hold_key and pressed.is_set():
            stop_rec.set()
            pressed.clear()
            threading.Thread(target=_turn, args=(stop_rec,),
                             daemon=True).start()
        if key == keyboard.Key.esc:
            return False  # stop listener → quit

    def _turn(stop_ev: threading.Event) -> None:
        # record while key still held (stop_ev set on release)
        dur = _arecord(None, stop_ev)
        if dur < 0.6:
            return  # accidental tap
        try:
            text = wav_to_stt()
        except Exception:
            text = ""
        if not text.strip():
            notify("didn't catch that", "FoveAI Voice")
            return
        threading.Thread(target=_answer, args=(text,), daemon=True).start()

    def _answer(text: str) -> None:
        notify(f"👤 {text[:160]}", "FoveAI Voice — you said")
        ans = ask_jen(text)
        threading.Thread(target=speak, args=(ans,), daemon=True).start()
        notify(ans[:220] or "…", "FoveAI Voice — Jen")

    with keyboard.Listener(on_press=on_press, on_release=on_release) as lst:
        notify(f"vocal mode ON — hold LEFT CTRL to talk · ESC to quit",
               "FoveAI Voice")
        lst.join()


if __name__ == "__main__":
    threading.Thread(target=ptt_loop, daemon=True).start()
    print("[ptt] foveai_ptt alive — hold L-CTRL to talk, ESC in focus to quit")
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    while True:
        time.sleep(60)