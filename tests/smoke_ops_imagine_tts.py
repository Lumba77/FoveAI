"""
Smoke test: ops auth -> imagine (/api/dream) + mouth TTS (chatterbox primary, piper fallback).

Run from repo root with stack up:
  python tests/smoke_ops_imagine_tts.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

BASE = "http://127.0.0.1"
OPS = f"{BASE}:8080"
MOUTH = f"{BASE}:8002"


def _load_env_value(key: str) -> str:
    val = os.getenv(key, "").strip()
    if val:
        return val
    env_path = Path(".env")
    if not env_path.exists():
        return ""
    for raw in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == key:
            return v.strip().strip('"').strip("'")
    return ""


def _json_request(
    opener: urllib.request.OpenerDirector,
    method: str,
    url: str,
    payload: dict | None = None,
    timeout: float = 60.0,
) -> tuple[int, dict]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with opener.open(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        parsed = json.loads(body) if body else {}
        return resp.status, parsed


def _json_request_raw(
    method: str,
    url: str,
    payload: dict | None = None,
    timeout: float = 120.0,
) -> tuple[int, bytes]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read()


def main() -> int:
    dream_timeout = float(os.getenv("FoveAI_SMOKE_DREAM_TIMEOUT_SEC", "420"))
    print("--- Ops auth session ---")
    password = _load_env_value("FoveAI_WEBUI_PASSWORD")
    if not password:
        print("FAIL missing FoveAI_WEBUI_PASSWORD in env/.env")
        return 1

    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    try:
        st, out = _json_request(
            opener,
            "POST",
            f"{OPS}/api/auth/login",
            {"password": password},
            timeout=20.0,
        )
        if st != 200 or not out.get("ok"):
            print(f"FAIL login status={st} body={out}")
            return 1
        st, auth = _json_request(opener, "GET", f"{OPS}/api/auth/status", timeout=20.0)
        if st != 200 or not auth.get("authenticated"):
            print(f"FAIL auth status={st} body={auth}")
            return 1
        print("OK auth session established")
    except urllib.error.URLError as e:
        print(f"FAIL auth request: {e}")
        return 1

    print("--- Ensure chatterbox backend on mouth ---")
    try:
        st, current = _json_request(opener, "GET", f"{OPS}/api/tts/backend", timeout=20.0)
        print(f"current backend: {current}")
        st, switched = _json_request(
            opener,
            "PUT",
            f"{OPS}/api/tts/backend",
            {"backend": "chatterbox"},
            timeout=20.0,
        )
        if st != 200 or switched.get("backend") != "chatterbox":
            print(f"FAIL could not set chatterbox backend: status={st} body={switched}")
            return 1
        print("OK backend=chatterbox")
    except urllib.error.URLError as e:
        print(f"FAIL backend set: {e}")
        return 1

    print("--- IMAGINE smoke via ops /api/dream ---")
    dream_payload = {
        "prompt": "foveai smoke e2e",
        "model_type": "turbo",
        "num_inference_steps": 2,
        "width": 256,
        "height": 256,
    }
    try:
        st, dream = _json_request(
            opener,
            "POST",
            f"{OPS}/api/dream",
            dream_payload,
            timeout=dream_timeout,
        )
        b64 = str(dream.get("image_b64", ""))
        if st != 200 or dream.get("status") != "success" or len(b64) < 1000:
            print(f"FAIL dream status={st} keys={list(dream.keys())} detail={dream.get('detail')}")
            return 1
        print(f"OK dream image_b64 length={len(b64)}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        print(f"FAIL dream HTTP {e.code}: {detail[:500]}")
        return 1
    except urllib.error.URLError as e:
        print(f"FAIL dream request: {e}")
        return 1

    print("--- TTS primary (chatterbox expected) ---")
    try:
        st, audio = _json_request_raw(
            "POST",
            f"{MOUTH}/tts",
            {
                "text": "Jen smoke check. Emotional voice path online.",
                "voice": "Emily.wav",
                "engine": "TURBO",
            },
            timeout=180.0,
        )
        if st != 200 or len(audio) < 1000:
            print(f"FAIL chatterbox primary status={st} bytes={len(audio)}")
            return 1
        print(f"OK chatterbox primary bytes={len(audio)}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        print(f"FAIL chatterbox primary HTTP {e.code}: {detail[:400]}")
        return 1
    except urllib.error.URLError as e:
        print(f"FAIL chatterbox primary request: {e}")
        return 1

    print("--- TTS fallback (force chatterbox miss -> piper) ---")
    try:
        st, audio = _json_request_raw(
            "POST",
            f"{MOUTH}/tts",
            {
                "text": "Jen smoke fallback. Piper should catch this path.",
                "voice": "__missing_voice__.wav",
                "engine": "TURBO",
            },
            timeout=180.0,
        )
        if st != 200 or len(audio) < 1000:
            print(f"FAIL piper fallback status={st} bytes={len(audio)}")
            return 1
        # Piper path may return raw PCM with media_type=audio/wav (no RIFF header),
        # so only require a healthy non-trivial audio payload.
        if audio.startswith(b"{") and b"status" in audio[:120]:
            print("FAIL fallback returned JSON-like payload instead of audio bytes")
            return 1
        print(f"OK piper fallback bytes={len(audio)}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        print(f"FAIL piper fallback HTTP {e.code}: {detail[:400]}")
        return 1
    except urllib.error.URLError as e:
        print(f"FAIL piper fallback request: {e}")
        return 1

    print("--- Pipeline OK: auth -> imagine -> chatterbox -> piper fallback ---")
    return 0


if __name__ == "__main__":
    sys.exit(main())

