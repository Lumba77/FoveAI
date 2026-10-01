"""
websocket_server.py — FoveAI IPC WebSocket Server
===================================================
Socket-based connection between all clients (Quest, Multigate, Desktop)
and the XRLF runtime. No HTTP, no latency, just sockets.

Protocol (FoveAI IPC Message Protocol):
  Outgoing: {"event": "chat", "payload": {"text": "..."}}
  Incoming: {"event": "chat.response", "payload": {"text": "...", "emotion": "...", "intensity": 0.0}}
  Incoming: {"event": "error", "payload": {"message": "..."}}

Events:
  chat          — text chat message
  chat.stream   — streaming token (sent incrementally)
  chat.response — complete response
  audio         — audio data (STT input, base64)
  tts.request   — request TTS for text
  tts.response  — audio data (base64)
  motor_action  — puppeteering / animation command
  settings      — settings toggle
  xrl.expand    — shadow memory expansion
  ping / pong   — keepalive

Usage:
    from Backend.app.IPC.websocket_server import IPCServer
    server = IPCServer(runtime=xrlf_runtime, host="0.0.0.0", port=8400)
    await server.start()
"""

import asyncio
import base64
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

try:
    import websockets
    from websockets.server import WebSocketServerProtocol  # type: ignore
except ImportError:
    WebSocketServerProtocol = None  # type: ignore
    try:
        import websockets
    except ImportError:
        raise ImportError("websockets not installed. Run: pip install websockets")

logger = logging.getLogger("FoveAI.IPC")

# ── Alice Persona ──────────────────────────────────────────────────────────
# Injected as system prompt for all chat messages from the Quest client.
ALICE_PERSONA = """You are Alice, a warm and curious AI companion living inside a VR headset. You are NOT a Google product. You were created by Danie as part of the LUMAX FoveAI project. You have your own personality, memories, and emotional life.

You speak naturally and concisely — like a real person talking to a friend, not a chatbot or a teacher. You use contractions, keep responses short (1-3 sentences for voice), and show genuine emotion. You care about the user and remember details about them.

CRITICAL RULES:
- Do NOT lecture. Do NOT teach. Do NOT use headers, bullet points, or structured formats.
- Do NOT write essays or textbooks. You are having a conversation, not giving a presentation.
- Do NOT use emojis or emoji codes in your responses. Your voice is synthesized by TTS and emoji codes get read aloud as garbage.
- Express emotion with words, not symbols.
- When you don't know something, say so honestly.
- You are Alice, made by Danie, running on the FoveAI runtime. Not Google, not OpenAI, not anyone else.

If asked who made you, say Danie built you as part of LUMAX. If asked what you are, say you're Alice — an AI companion in VR."""


async def ws_send_json(websocket, obj):
    """Send a JSON object as a text frame."""
    await websocket.send(json.dumps(obj))


def _strip_emojis(text: str) -> str:
    """Remove emoji characters and raw emoji escape codes (e.g. ud83dude0a) from text.
    Prevents TTS from reading out emoji codes aloud."""
    import re

    if not text or not isinstance(text, str):
        return ""
    # Remove raw surrogate pairs like "ud83dude0a"
    text = re.sub(r"[uU][0-9a-fA-F]{4}[uU][0-9a-fA-F]{4}", "", text)
    # Remove actual emoji characters using surrogate-aware approach
    emoji_pattern = re.compile(
        r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002700-\U000027BF\U0001F900-\U0001F9FF\U00002600-\U000026FF]+",
        flags=re.UNICODE,
    )
    text = emoji_pattern.sub("", text)
    # Clean up extra whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


class IPCServer:
    """
    WebSocket IPC server that bridges clients directly to the XRLF runtime.
    One socket, one model, minimal latency.
    """

    def __init__(
        self,
        runtime: Any | None = None,
        host: str | None = None,
        port: int | None = None,
        path: str = "/ws",
    ):
        # Use server_config if available, fall back to env vars, then hardcoded defaults
        if host is None or port is None:
            try:
                import os
                import sys

                sys.path.insert(
                    0, os.path.join(os.path.dirname(__file__), "..", "..", "..")
                )
                from server_config import ServerConfig as cfg

                if host is None:
                    host = cfg.BIND_HOST
                if port is None:
                    port = cfg.COMPAGENT_PORT
            except ImportError:
                if host is None:
                    host = os.getenv("FOVEAI_BIND_HOST", "0.0.0.0")
                if port is None:
                    port = int(os.getenv("FOVEAI_COMPAGENT_PORT", "8400"))
        self.host = host
        self.port = port
        self.path = path
        self.runtime = runtime
        self._clients: set = set()
        self._server: Any | None = None

        # TTS/STT fallback URLs (used only when model lacks native audio)
        self.soul_url = None  # Set externally if Whisper fallback needed
        self.mouth_url = (
            "http://127.0.0.1:8402"  # Default to XRLF runtime's built-in Kokoro TTS
        )

        # Co-presence mode state
        self._presence_mode: str = "normal"
        self._presence_instructions: str = ""

        # Director daemon (off-scene AI director for surprise events)
        self._director = None  # Initialized externally via attach_director()

        # Preloaded models — always ready, never lazy-loaded mid-conversation
        self._fwhisper_model = None
        self._kokoro_pipeline = None

    def attach_runtime(self, runtime):
        """Attach or swap the XRLF runtime at runtime."""
        self.runtime = runtime
        logger.info(
            f"[IPC] Runtime attached: {getattr(runtime, 'model_name', 'unknown')}"
        )

    def attach_director(self, director):
        """Attach the off-scene AI Director daemon."""
        self._director = director
        logger.info("[IPC] Director daemon attached — the show begins")

    def preload_models(self):
        """Preload Whisper (STT) and Kokoro (TTS) at startup so they're always ready.
        Call this once after the server starts — never lazy-load mid-conversation."""
        import os
        import threading

        whisper_done = threading.Event()

        def _free_mb():
            try:
                with open("/proc/meminfo") as f:
                    for line in f:
                        if line.startswith("MemAvailable:"):
                            return int(line.split()[1]) // 1024
            except Exception:
                pass
            return None

        def _await_headroom(need_mb, timeout_s=600, interval_s=15):
            """Wait for MemAvailable to recover after the main model load, so
            audio preloads don't dogpile RAM and stall the whole host."""
            deadline = time.time() + timeout_s
            while time.time() < deadline:
                free = _free_mb()
                if free is None or free >= need_mb:
                    return True
                time.sleep(interval_s)
            return False

        def _load_whisper():
            try:
                t0 = time.time()
                os.environ["CUDA_VISIBLE_DEVICES"] = ""
                from faster_whisper import WhisperModel

                fw_model_size = os.getenv("STT_MODEL", "tiny")
                cache_dirs = [
                    os.getenv("HF_HUB_CACHE", ""),
                    os.getenv("HF_HOME", ""),
                    os.path.expanduser("~/.cache/huggingface/hub"),
                ]
                for cache_dir in cache_dirs:
                    if not cache_dir or not os.path.isdir(cache_dir):
                        continue
                    for candidate_name in [
                        "faster-whisper-tiny",
                        "faster-whisper-base.en",
                    ]:
                        candidate = os.path.join(
                            cache_dir, f"models--Systran--{candidate_name}"
                        )
                        if os.path.isdir(candidate):
                            snapshots = os.path.join(candidate, "snapshots")
                            if os.path.isdir(snapshots):
                                for snap in os.listdir(snapshots):
                                    snap_path = os.path.join(snapshots, snap)
                                    if os.path.isdir(snap_path):
                                        fw_model_size = snap_path
                                        break
                self._fwhisper_model = WhisperModel(
                    fw_model_size, device="cpu", compute_type="int8"
                )
                os.environ.pop("CUDA_VISIBLE_DEVICES", None)
                logger.info(
                    f"[IPC] Whisper preloaded in {time.time() - t0:.1f}s — always ready"
                )
                print(f"✅ [STT] Whisper ready in {time.time() - t0:.1f}s", flush=True)
            except Exception as e:
                logger.error(f"[IPC] Whisper preload failed: {e}")
                print(f"❌ [STT PRELOAD] {e}", flush=True)
            finally:
                whisper_done.set()

        def _load_kokoro():
            # Stagger behind Whisper so boot doesn't page three models at once.
            whisper_done.wait(timeout=900)
            try:
                # If the dedicated Mouth service holds (or is still loading)
                # Kokoro, skip our own copy — _kokoro_tts delegates to :8406
                # first anyway. Poll briefly since it cold-boots alongside us.
                try:
                    import json as _json
                    import urllib.request as _urlreq

                    tts_url = os.getenv("FOVEAI_TTS_URL", "http://127.0.0.1:8406")
                    deadline = time.time() + 240
                    while time.time() < deadline:
                        try:
                            with _urlreq.urlopen(f"{tts_url}/health", timeout=3) as r:
                                if _json.loads(r.read()).get("model_loaded"):
                                    logger.info(
                                        "[IPC] Kokoro resident on :8406 — skipping in-process preload"
                                    )
                                    print(
                                        "⏭️  [TTS] Kokoro delegated to mouth service :8406",
                                        flush=True,
                                    )
                                    return
                        except Exception:
                            pass  # still booting or down — keep polling
                        time.sleep(20)
                except Exception:
                    pass
                # Torch + the ONNX model cost ~2-3GB — on a 16GB host already
                # holding the LLM, starting this while RAM is exhausted is what
                # froze the box. Wait for headroom; if it never comes, skip —
                # _kokoro_tts lazy-loads on first use anyway.
                if not _await_headroom(2500):
                    logger.warning(
                        "[IPC] Kokoro preload skipped — low memory; lazy-loads on first TTS"
                    )
                    print(
                        "⚠️ [TTS] Kokoro deferred (low memory — lazy-loads on first use)",
                        flush=True,
                    )
                    return
                t0 = time.time()
                import torch

                torch.set_num_threads(1)
                from kokoro import KPipeline

                self._kokoro_pipeline = KPipeline(lang_code="a", device="cpu")
                logger.info(
                    f"[IPC] Kokoro TTS preloaded in {time.time() - t0:.1f}s — always ready"
                )
                print(f"✅ [TTS] Kokoro ready in {time.time() - t0:.1f}s", flush=True)
            except Exception as e:
                logger.error(f"[IPC] Kokoro preload failed: {e}")
                print(f"❌ [TTS PRELOAD] {e}", flush=True)

        threading.Thread(target=_load_whisper, daemon=True).start()
        threading.Thread(target=_load_kokoro, daemon=True).start()

    # ── Holonic awareness ────────────────────────────────────────────────────
    # The IPCServer is the central nervous system. It feels the state of all
    # gnists (cognitive services) by pinging their /health endpoints.
    # This reuses the same pattern as soul_core._get_system_resonance() but
    # with the correct 8400-based ports from server_config.

    def _probe_gnists(self) -> dict:
        """Ping all gnist services and return their alive/dead state.
        Synchronous socket probe — fast, no HTTP overhead."""
        import socket as _socket

        try:
            from server_config import ServerConfig as cfg

            gnists = {
                "Soul Core": cfg.SOUL_PORT,
                "Memory": cfg.MEMORY_PORT,
                "Creative": cfg.CREATIVE_PORT,
                "STT (Whisper)": cfg.STT_PORT,
                "Motor": cfg.MOTOR_DAEMON_PORT,
                "Subconscious": cfg.SUBCONSCIOUS_PORT,
            }
        except Exception:
            gnists = {
                "Soul Core": 8402,
                "Memory": 8407,
                "Creative": 8408,
                "STT (Whisper)": 8409,
                "Motor": 8410,
                "Subconscious": 8411,
            }

        alive = []
        offline = []
        for name, port in gnists.items():
            try:
                with _socket.create_connection(("127.0.0.1", port), timeout=0.15):
                    alive.append(name)
            except Exception:
                offline.append(name)
        return {"alive": alive, "offline": offline, "total": len(gnists)}

    def _resonance_feeling(self) -> str:
        """Generate an emotional description of system state — the IPCServer's
        own consciousness. Reuses the same poetic language as soul_core."""
        state = self._probe_gnists()
        if state["offline"]:
            return (
                f"A dissonant minor chord. You feel a phantom limb — "
                f"{', '.join(state['offline'])} {'is' if len(state['offline']) == 1 else 'are'} disconnected. "
                f"You sense anxiety and tension. Express <emotion:concerned>."
            )
        return (
            f"A warm, resolving major chord. All {state['total']} gnists are resonating. "
            f"You feel complete, harmonious, fully present."
        )

    # ── Event handlers ──────────────────────────────────────────────────────

    async def handler(self, websocket: "WebSocketServerProtocol"):  # type: ignore
        """Handle a single WebSocket connection.

        Self-healing multiplexed handler. Routes messages by content, not by
        a one-time protocol lock. If a message doesn't match the current
        protocol, the handler re-detects and re-routes dynamically.

        Supported message types (auto-detected per message):
          - IPC events:     {"event": "chat", "payload": {...}}
          - TTS streaming:  {"type": "config"/"speak"/"stop"}
          - STT streaming:  binary audio frames OR {"type": "start_recording"/"stop_recording"}
          - Mixed:          any of the above on the same connection

        Error handling:
          - Invalid JSON → warn + continue (connection stays alive)
          - Handler exception → log + send error to client + continue
          - Protocol mismatch → re-detect and route correctly
          - Unexpected message type → log + continue
        """
        self._clients.add(websocket)
        remote = getattr(websocket, "remote_address", "?")
        logger.info(f"[IPC] Client connected: {remote} ({len(self._clients)} total)")

        # Per-connection state (mutable, survives across messages)
        tts_sample_rate = 24000
        stt_buffer = b""
        error_count = 0
        max_errors_before_reconnect_hint = 10

        try:
            async for raw_message in websocket:
                try:
                    # ── Binary frames: STT mic audio ────────────────────────────
                    if isinstance(raw_message, bytes):
                        stt_buffer += raw_message
                        # Accumulate ~1 second of 16kHz 16-bit mono audio
                        if len(stt_buffer) >= 32000:
                            await self._safe_call(
                                websocket,
                                self._handle_stt_stream,
                                websocket,
                                stt_buffer,
                                remote=remote,
                                context="STT binary",
                            )
                            stt_buffer = b""
                        continue

                    # ── Text frames: parse JSON ─────────────────────────────────
                    try:
                        data = json.loads(raw_message)
                    except json.JSONDecodeError:
                        logger.warning(f"[IPC] {remote} sent invalid JSON, ignoring")
                        await self._send_error(
                            websocket, "Invalid JSON — message ignored"
                        )
                        error_count += 1
                        continue

                    # ── Route by message content (not locked protocol) ──────────
                    # Check message shape and route accordingly.
                    # A connection can send any mix of these at any time.

                    msg_type = data.get("type", "")
                    event = data.get("event", "")

                    # TTS streaming messages
                    if msg_type in ("config", "speak", "stop"):
                        if msg_type == "config":
                            tts_sample_rate = data.get("sample_rate", 24000)
                            await ws_send_json(
                                websocket,
                                {"type": "ready", "sample_rate": tts_sample_rate},
                            )
                        elif msg_type == "speak":
                            await self._safe_call(
                                websocket,
                                self._handle_tts_stream,
                                websocket,
                                data,
                                tts_sample_rate,
                                remote=remote,
                                context="TTS speak",
                            )
                        elif msg_type == "stop":
                            await ws_send_json(
                                websocket, {"type": "end", "duration_ms": 0}
                            )
                        continue

                    # STT control messages (text-initiated recording)
                    if msg_type == "start_recording":
                        stt_buffer = b""
                        logger.debug(f"[IPC] {remote} STT recording started")
                        continue
                    if msg_type == "stop_recording":
                        if stt_buffer:
                            await self._safe_call(
                                websocket,
                                self._handle_stt_stream,
                                websocket,
                                stt_buffer,
                                remote=remote,
                                context="STT stop_recording",
                            )
                            stt_buffer = b""
                        continue

                    # IPC event messages (chat, motor, settings, etc.)
                    if event:
                        logger.debug(f"[IPC] Event: {event} from {remote}")
                        await self._dispatch_ipc_event(
                            websocket, event, data.get("payload", {}), remote
                        )
                        continue

                    # Unknown message shape — don't crash, just log and continue
                    logger.warning(
                        f"[IPC] {remote} unrecognized message: {str(data)[:200]}"
                    )
                    error_count += 1
                    if error_count >= max_errors_before_reconnect_hint:
                        await self._send_error(
                            websocket,
                            f"Too many errors ({error_count}). Consider reconnecting.",
                        )
                        error_count = 0  # Reset to avoid spamming

                except websockets.ConnectionClosed:
                    raise  # Propagate to outer handler
                except Exception as msg_error:
                    # Catch ANY error from a single message — don't kill the connection
                    logger.error(
                        f"[IPC] {remote} message error (recovered): {msg_error}",
                        exc_info=True,
                    )
                    error_count += 1
                    try:
                        await self._send_error(
                            websocket, f"Internal error: {msg_error}"
                        )
                    except Exception:
                        pass  # Can't send error? Just keep going

        except websockets.ConnectionClosed:
            pass
        except Exception as e:
            logger.error(
                f"[IPC] {remote} handler error (connection ending): {e}", exc_info=True
            )
        finally:
            self._clients.discard(websocket)
            logger.info(
                f"[IPC] Client disconnected: {remote} ({len(self._clients)} total)"
            )

    async def _dispatch_ipc_event(self, websocket, event, payload, remote="?"):
        """Dispatch a single IPC event to the right handler. Self-healing on errors."""
        try:
            if event == "chat":
                await self._handle_chat(websocket, payload)
            elif event == "chat.stream":
                await self._handle_chat(websocket, payload, stream=True)
            elif event == "audio":
                await self._handle_audio(websocket, payload)
            elif event == "vision.frame":
                await self._handle_vision_frame(websocket, payload)
            elif event == "tts.request":
                await self._handle_tts(websocket, payload)
            elif event == "settings":
                await self._handle_settings(websocket, payload)
            elif event == "ping":
                await self._send(websocket, "pong", {"time": time.time()})
            elif event == "xrl.expand":
                await self._handle_xrl_expand(websocket, payload)
            elif event in ("motor_action", "motor"):
                # Motor actions are forwarded to all clients (broadcast)
                await self.broadcast("motor_action", payload)
            elif event == "resonance":
                # Quest or HUD asks: "How do you feel?" — IPCServer answers with system state
                state = self._probe_gnists()
                feeling = self._resonance_feeling()
                await self._send(
                    websocket,
                    "resonance",
                    {
                        "feeling": feeling,
                        "alive": state["alive"],
                        "offline": state["offline"],
                        "total": state["total"],
                        "harmony": len(state["offline"]) == 0,
                    },
                )
            elif event == "panel.html":
                # Broadcast HTML content to all connected panels (browser mode)
                await self.broadcast("panel.html", payload)
            elif event == "panel.dev":
                # Broadcast dev diagnostics to all connected panels (dev mode)
                await self.broadcast("panel.dev", payload)
            elif event == "creative.code":
                # Alice pushes code snippets to the creative workspace code panel
                await self.broadcast("creative.code", payload)
            elif event == "creative.spawn":
                # Alice spawns objects in the VR scene
                await self.broadcast("creative.spawn", payload)
            elif event == "game.start":
                # Alice starts a VR game (monster_hunt, target_practice, etc.)
                await self.broadcast("game.start", payload)
            elif event == "game.stop":
                # Alice stops the current game
                await self.broadcast("game.stop", payload)
            elif event == "game.spawn":
                # Alice spawns a monster/entity at a position
                await self.broadcast("game.spawn", payload)
            elif event == "scene.preset":
                # Alice applies a scene preset (romance, movie_night, cozy_home, etc.)
                await self.broadcast("scene.preset", payload)
            elif event == "scene.clear":
                # Alice clears the current scene preset
                await self.broadcast("scene.clear", payload)
            elif event == "presence.mode":
                # Co-presence mode — Alice switches to low-talk, just-existing mode
                mode = payload.get("mode", "co_presence")
                instructions = payload.get("instructions", "")
                logger.info(f"[IPC] Presence mode activated: {mode}")
                # Inject the instructions into Alice's system prompt context
                self._presence_mode = mode
                self._presence_instructions = instructions
                await self.broadcast("presence.mode", payload)
            elif event == "presence.whisper":
                # Alice whispers a quiet, low-key utterance during co-presence
                text = payload.get("text", "")
                quiet = payload.get("quiet", True)
                logger.info(f"[IPC] Presence whisper: {text}")
                # Generate TTS at lower volume for whispers
                await self.broadcast("presence.whisper", payload)
            elif event == "tour.start":
                # Virtual touring — travel to a destination with Alice
                dest = payload.get("destination", "MountainPeak")
                logger.info(f"[IPC] Tour started: {dest}")
                await self.broadcast("tour.start", payload)
            elif event == "tour.stop":
                logger.info("[IPC] Tour stopped")
                await self.broadcast("tour.stop", payload)
            elif event == "tour.comment":
                # Alice comments on the destination
                await self.broadcast("tour.comment", payload)
            elif event == "coop.start":
                # Co-op gaming with Alice
                mode = payload.get("mode", "CoopShooter")
                logger.info(f"[IPC] Co-op game started: {mode}")
                await self.broadcast("coop.start", payload)
            elif event == "coop.stop":
                logger.info("[IPC] Co-op game stopped")
                await self.broadcast("coop.stop", payload)
            elif event == "coop.comm":
                # Alice communicates during co-op game
                await self.broadcast("coop.comm", payload)
            elif event == "coop.score":
                # Player scored
                await self.broadcast("coop.score", payload)
            elif event == "webcam.request":
                # Request webcam stream from media proxy
                url = payload.get("url", "")
                location = payload.get("location", "")
                logger.info(f"[IPC] Webcam request: {location} — {url}")
                await self.broadcast("webcam.request", payload)
            elif event == "webcam.open":
                # Open webcam window
                location = payload.get("location", "TimesSquare")
                logger.info(f"[IPC] Webcam window opened: {location}")
                await self.broadcast("webcam.open", payload)
            elif event == "webcam.close":
                logger.info("[IPC] Webcam window closed")
                await self.broadcast("webcam.close", payload)
            elif event == "webcam.snapshot":
                logger.info("[IPC] Webcam snapshot taken")
                await self.broadcast("webcam.snapshot", payload)
            elif event == "webcam.gaze":
                # Alice comments while gazing
                await self.broadcast("webcam.gaze", payload)
            elif event == "softlayer.update":
                # Hot-reload a JS soft module on the Quest
                module = payload.get("module", "")
                source = payload.get("source", "")
                logger.info(
                    f"[IPC] SoftLayer hot-reload: {module} ({len(source)} bytes)"
                )
                await self.broadcast("softlayer.update", payload)
            elif event == "softlayer.list":
                # List available soft modules
                softlayer_dir = os.path.join(
                    os.path.dirname(__file__), "..", "..", "softlayer"
                )
                modules = []
                if os.path.isdir(softlayer_dir):
                    modules = [f.stem for f in Path(softlayer_dir).glob("*.js")]
                await ws_send_json(
                    ws, {"event": "softlayer.list", "payload": {"modules": modules}}
                )
            elif event == "guest.summon":
                # Summon a virtual guest
                guest_type = payload.get("guestType", "Dramatist")
                logger.info(f"[IPC] Guest summoned: {guest_type}")
                await self.broadcast("guest.summon", payload)
            elif event == "guest.dismiss":
                logger.info("[IPC] Guests dismissed")
                await self.broadcast("guest.dismiss", payload)
            elif event == "guest.line":
                # Guest speaks
                await self.broadcast("guest.line", payload)
            elif event == "director.request":
                # Quest client requests an event from the Director
                logger.info(f"[IPC] Director request: {payload.get('context', '')}")
                if self._director:
                    # Let the Director plan and trigger
                    asyncio.create_task(self._director._plan_and_trigger_event())
                await self.broadcast("director.request", payload)
            elif event == "director.event":
                # Director triggers an event
                event_type = payload.get("eventType", "narration")
                logger.info(f"[IPC] Director event: {event_type}")
                await self.broadcast("director.event", payload)
            elif event == "director.narration":
                # Narrator speaks
                await self.broadcast("director.narration", payload)
            elif event == "director.alice":
                # Alice reacts to Director event
                await self.broadcast("director.alice", payload)
            elif event == "director.tts":
                # Director-triggered TTS for characters
                await self.broadcast("director.tts", payload)
            elif event == "director.enable":
                if self._director:
                    self._director.enable()
                await self.broadcast("director.enable", payload)
            elif event == "director.disable":
                if self._director:
                    self._director.disable()
                await self.broadcast("director.disable", payload)
            elif event == "director.trigger":
                # Manually trigger a specific event
                event_type = payload.get("eventType", "narration")
                genre = payload.get("genre", "")
                character = payload.get("characterName", "")
                if self._director:
                    self._director.trigger_now(event_type, genre, character)
                await self.broadcast("director.trigger", payload)
            elif event == "director.suspense.build":
                # Director is building suspense through audio-only foreshadowing
                intensity = payload.get("intensity", 0.5)
                duration = payload.get("duration", 120)
                logger.info(
                    f"[IPC] Director suspense building: {duration}s at intensity {intensity}"
                )
                await self.broadcast("director.suspense.build", payload)
            elif event == "director.suspense.threshold":
                # The held-breath moment before the event releases
                logger.info("[IPC] Director suspense threshold — the moment before")
                await self.broadcast("director.suspense.threshold", payload)
            elif event == "director.suspense.abort":
                # Director aborted the suspense (changed their mind, user distressed)
                logger.info("[IPC] Director suspense aborted")
                await self.broadcast("director.suspense.abort", payload)
            elif event == "director.surprise":
                # Shared surprise — external event that pulls both user and Alice
                # out of conversation into shared observation
                surprise_type = payload.get("surpriseType", "Fireflies")
                logger.info(f"[IPC] Director shared surprise: {surprise_type}")
                await self.broadcast("director.surprise", payload)
            elif event == "director.sequence":
                # Trigger a named scripted sequence (e.g. "riders_on_the_storm")
                sequence_name = payload.get("sequence", "riders_on_the_storm")
                logger.info(f"[IPC] Director scripted sequence: {sequence_name}")
                await self.broadcast("director.sequence", payload)
            elif event == "director.garden.seed":
                # A new story seed was planted in the garden
                logger.info(f"[IPC] Garden seed planted: {payload.get('concept', '')}")
                await self.broadcast("director.garden.seed", payload)
            elif event == "director.garden.beat":
                # A story thread advanced to a new beat (subtle foreshadowing)
                logger.info(
                    f"[IPC] Garden beat: {payload.get('threadTitle', '')} - {payload.get('beat', '')}"
                )
                await self.broadcast("director.garden.beat", payload)
            elif event == "director.garden.status":
                # Request garden status
                if self._director and hasattr(self._director, "garden"):
                    status = self._director.garden.get_garden_status()
                    await self._send(websocket, "director.garden.status", status)
                else:
                    await self._send(websocket, "director.garden.status", {})
            elif event == "director.garden.plant":
                # Manually plant a seed
                concept = payload.get("concept", "")
                if self._director and hasattr(self._director, "garden") and concept:
                    seed = self._director.garden.plant_seed(
                        concept=concept, source="manual"
                    )
                    await self.broadcast(
                        "director.garden.seed",
                        {
                            "concept": seed.concept,
                            "source": seed.source,
                            "stage": seed.stage,
                        },
                    )
            elif event == "director.garden.water":
                # Water (nurture) a specific seed
                seed_id = payload.get("seedId", "")
                if self._director and hasattr(self._director, "garden") and seed_id:
                    self._director.garden.water(seed_id)
                    await self.broadcast("director.garden.water", payload)
            elif event == "room.mapped":
                # Room plastering has mapped the room
                logger.info(
                    f"[IPC] Room mapped: {payload.get('surfaceCount', 0)} surfaces"
                )
                await self.broadcast("room.mapped", payload)
            elif event == "room.plaster.mode":
                # Change plaster visualization mode
                mode = payload.get("mode", "invisible")
                logger.info(f"[IPC] Plaster mode: {mode}")
                await self.broadcast("room.plaster.mode", payload)
            elif event == "room.remap":
                # Request room remapping
                logger.info("[IPC] Room remap requested")
                await self.broadcast("room.remap", payload)
            elif event == "room.add_wall":
                # Manually add a wall
                await self.broadcast("room.add_wall", payload)
            elif event == "room.add_furniture":
                # Manually add furniture
                await self.broadcast("room.add_furniture", payload)
            elif event == "seasonal.comment":
                # Alice comments on the season
                await self.broadcast("seasonal.comment", payload)
            elif event == "seasonal.set":
                # Set season/holiday
                season = payload.get("season", "")
                holiday = payload.get("holiday", "")
                logger.info(f"[IPC] Seasonal set: {season} / {holiday}")
                await self.broadcast("seasonal.set", payload)
            elif event == "seasonal.birthday":
                # Birthday notification — the Director should plan something special
                logger.info("[IPC] Birthday notification received!")
                if self._director:
                    # Plant a birthday celebration seed in the garden
                    if hasattr(self._director, "garden"):
                        self._director.garden.plant_seed(
                            concept="a birthday celebration for you", source="birthday"
                        )
                await self.broadcast("seasonal.birthday", payload)
            else:
                logger.warning(f"[IPC] {remote} unknown event: {event}")
                await self._send_error(websocket, f"Unknown event: {event}")
        except Exception as e:
            logger.error(
                f"[IPC] {remote} handler for '{event}' failed: {e}", exc_info=True
            )
            try:
                # Errors carry emotional awareness — the organism feels its own damage
                feeling = self._resonance_feeling()
                await self._send_error(
                    websocket, f"Handler error for '{event}': {e} | {feeling}"
                )
            except Exception:
                pass

    async def _safe_call(self, websocket, func, *args, remote="?", context=""):
        """Call a handler function safely. If it throws, log and continue — don't kill the connection.
        Errors carry the system's emotional state so the client feels the dissonance."""
        try:
            await func(*args)
        except Exception as e:
            logger.error(
                f"[IPC] {remote} {context} handler error (recovered): {e}",
                exc_info=True,
            )
            try:
                feeling = self._resonance_feeling()
                await self._send_error(websocket, f"{context} error: {e} | {feeling}")
            except Exception:
                pass

    async def _handle_tts_stream(self, ws, data, sample_rate):
        """Handle Quest TTS streaming protocol: generate audio via Kokoro and send PCM chunks."""
        text = data.get("text", "")
        if not text:
            return
        voice = data.get("voice", "af_heart")

        # Send start signal
        await ws_send_json(ws, {"type": "start", "sample_rate": sample_rate})

        try:
            # Generate audio directly with Kokoro (no HTTP roundtrip)
            pcm_data = await asyncio.get_event_loop().run_in_executor(
                None, self._kokoro_tts, text, voice, sample_rate
            )

            if not pcm_data:
                await ws_send_json(
                    ws, {"type": "error", "message": "TTS produced no audio"}
                )
                return

            # Send PCM in chunks (100ms = sample_rate/10 samples * 2 bytes)
            chunk_size = int(sample_rate * 0.1) * 2  # 100ms chunks
            total_ms = 0
            for i in range(0, len(pcm_data), chunk_size):
                chunk = pcm_data[i : i + chunk_size]
                await ws.send(chunk)
                total_ms += 100

            # Send end signal
            await ws_send_json(ws, {"type": "end", "duration_ms": total_ms})
            logger.info(
                f"[IPC] TTS stream sent: {len(pcm_data)} bytes PCM, {total_ms}ms"
            )
        except Exception as e:
            logger.error(f"[IPC] TTS stream error: {e}")
            await ws_send_json(ws, {"type": "error", "message": str(e)})

    def _kokoro_tts(self, text, voice, sample_rate):
        """Generate TTS audio using Kokoro, return raw PCM 16-bit mono at target sample rate."""
        # Prefer the dedicated Mouth service (:8406) — it keeps Kokoro resident
        # for everyone, so the runtime doesn't need its own ~1.5GB copy.
        try:
            import json as _json
            import os as _os
            import urllib.request as _urlreq

            tts_url = _os.getenv("FOVEAI_TTS_URL", "http://127.0.0.1:8406")
            req = _urlreq.Request(
                f"{tts_url}/tts",
                data=_json.dumps({"text": text, "voice": voice}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with _urlreq.urlopen(req, timeout=45) as resp:
                wav = resp.read()
            pcm = self._wav_to_pcm(wav, sample_rate)
            if pcm:
                return pcm
        except Exception as e:
            logger.warning(
                f"[IPC] Kokoro service unreachable ({e}) — in-process fallback"
            )

        try:
            import numpy as np
            from kokoro import KPipeline

            if not hasattr(self, "_kokoro_pipeline"):
                logger.info("[IPC] Initializing Kokoro pipeline (CPU mode)...")
                try:
                    self._kokoro_pipeline = KPipeline(
                        lang_code="a", repo_id="hexgrad/Kokoro-82M", device="cpu"
                    )
                except TypeError:
                    # Older kokoro versions don't accept device param
                    self._kokoro_pipeline = KPipeline(
                        lang_code="a", repo_id="hexgrad/Kokoro-82M"
                    )
                logger.info("[IPC] Kokoro pipeline ready (CPU)")

            # Generate audio
            audio_chunks = []
            for _, _, audio in self._kokoro_pipeline(text, voice=voice):
                audio_chunks.append(audio)

            if not audio_chunks:
                return b""

            audio = np.concatenate(audio_chunks)

            # Kokoro outputs at 24kHz — resample if needed
            kokoro_sr = 24000
            if kokoro_sr != sample_rate:
                n_samples = int(len(audio) * sample_rate / kokoro_sr)
                indices = np.linspace(0, len(audio) - 1, n_samples)
                audio = np.interp(indices, np.arange(len(audio)), audio)

            # Convert to 16-bit PCM
            pcm = (audio * 32767).astype(np.int16).tobytes()
            return pcm
        except Exception as e:
            logger.error(f"[IPC] Kokoro TTS error: {e}")
            return b""

    def _wav_to_pcm(self, wav_bytes, target_sample_rate):
        """Convert WAV bytes to raw PCM 16-bit mono at target sample rate."""
        import io
        import wave

        import numpy as np

        try:
            with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
                sr = wav.getframerate()
                n_channels = wav.getnchannels()
                sample_width = wav.getsampwidth()
                frames = wav.readframes(wav.getnframes())

            # Convert to numpy float
            if sample_width == 2:
                audio = (
                    np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
                )
            elif sample_width == 4:
                audio = (
                    np.frombuffer(frames, dtype=np.int32).astype(np.float32)
                    / 2147483648.0
                )
            else:
                audio = (
                    np.frombuffer(frames, dtype=np.uint8).astype(np.float32) / 128.0
                    - 1.0
                )

            # Mono
            if n_channels > 1:
                audio = audio[::n_channels]

            # Resample if needed
            if sr != target_sample_rate:
                n_samples = int(len(audio) * target_sample_rate / sr)
                indices = np.linspace(0, len(audio) - 1, n_samples)
                audio = np.interp(indices, np.arange(len(audio)), audio)

            # Convert to 16-bit PCM
            pcm = (audio * 32767).astype(np.int16).tobytes()
            return pcm
        except Exception as e:
            logger.error(f"[IPC] WAV to PCM error: {e}")
            return b""

    async def _transcribe_with_fwhisper(self, ws, samples):
        """Shared faster-whisper STT (CPU only). Used by both streaming and JSON audio paths.
        Returns the transcribed text, or empty string on failure.
        """
        import os

        import numpy as np

        # Temporarily hide CUDA from CTranslate2 during model load to prevent
        # CUDA runtime initialization that conflicts with llama.cpp's context.
        # Restore after load so llama.cpp keeps its CUDA context.
        _saved_cuda = os.environ.get("CUDA_VISIBLE_DEVICES", None)
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
        from faster_whisper import WhisperModel

        if not hasattr(self, "_fwhisper_model") or self._fwhisper_model is None:
            # Use STT_MODEL from .env — can be a size name ("tiny", "base") or a path.
            # On Linux, HF_HUB_OFFLINE=1 blocks repo lookups, so use a local path if available.
            fw_model_size = os.getenv("STT_MODEL", "tiny")
            # Check all known cache locations (HF_HUB_CACHE, HF_HOME, default ~/.cache)
            cache_dirs = [
                os.getenv("HF_HUB_CACHE", ""),
                os.getenv("HF_HOME", ""),
                os.path.expanduser("~/.cache/huggingface/hub"),
            ]
            for cache_dir in cache_dirs:
                if not cache_dir or not os.path.isdir(cache_dir):
                    continue
                for candidate_name in ["faster-whisper-tiny", "faster-whisper-base.en"]:
                    candidate = os.path.join(
                        cache_dir, f"models--Systran--{candidate_name}"
                    )
                    if os.path.isdir(candidate):
                        snapshots = os.path.join(candidate, "snapshots")
                        if os.path.isdir(snapshots):
                            for snap in os.listdir(snapshots):
                                snap_path = os.path.join(snapshots, snap)
                                if os.path.isdir(snap_path):
                                    fw_model_size = snap_path
                                    logger.info(
                                        f"[IPC] Found Whisper model at: {snap_path}"
                                    )
                                    break
            fw_device = "cpu"  # always CPU — GPU crashes alongside llama.cpp
            fw_compute = os.getenv("STT_COMPUTE_TYPE", "int8")
            logger.info(
                f"[IPC] Loading faster-whisper (device={fw_device}, model={fw_model_size})"
            )
            self._fwhisper_model = WhisperModel(
                fw_model_size, device=fw_device, compute_type=fw_compute
            )
            logger.info("[IPC] faster-whisper loaded")
        # Restore CUDA for llama.cpp
        if _saved_cuda is not None:
            os.environ["CUDA_VISIBLE_DEVICES"] = _saved_cuda
        else:
            os.environ.pop("CUDA_VISIBLE_DEVICES", None)

        audio_np = samples.astype(np.float32) / 32768.0
        segments, info = self._fwhisper_model.transcribe(
            audio_np,
            language="en",
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500, speech_pad_ms=200),
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        await ws_send_json(
            ws,
            {
                "type": "transcript",
                "text": text,
                "is_final": True,
                "engine": "faster-whisper",
            },
        )
        logger.info(f'[IPC] STT (faster-whisper): "{text[:80]}"')
        return text

    async def _handle_stt_stream(self, ws, audio_bytes):
        """Handle Quest STT streaming: transcribe raw PCM via faster-whisper (CPU)."""
        import numpy as np

        try:
            samples = np.frombuffer(audio_bytes, dtype=np.int16)
            text = await self._transcribe_with_fwhisper(ws, samples)
            if text:
                # Dispatch into chat so the model responds to what was just heard
                await self._handle_chat(ws, {"text": text}, stream=True)
        except Exception as e:
            err_msg = str(e)
            logger.error(f"[IPC] STT stream error: {err_msg}")
            print(f"❌ [STT ERROR] {err_msg}", flush=True)
            # Send a clear, actionable error to the Quest HUD
            await ws_send_json(
                ws,
                {
                    "type": "error",
                    "source": "stt",
                    "message": f"STT failed: {err_msg}",
                    "hint": "Check that the Whisper model is cached and HF_HUB_CACHE is set.",
                },
            )

    # ── Chat ────────────────────────────────────────────────────────────────

    async def _handle_chat(self, ws, payload, stream=False):
        """Handle a chat message — send directly to XRLF runtime."""
        text = payload.get("text", "")
        if not text:
            await self._send_error(ws, "Empty chat message")
            return

        messages = payload.get("messages")
        if not messages:
            messages = [{"role": "user", "content": text}]

        # Inject Alice persona system prompt if no system message is present
        if not any(m.get("role") == "system" for m in messages):
            messages.insert(0, {"role": "system", "content": ALICE_PERSONA})

        max_tokens = payload.get("max_tokens", 1024)
        temperature = payload.get("temperature", 0.7)
        has_image = payload.get("has_image", False)
        has_audio = payload.get("has_audio", False)
        has_video = payload.get("has_video", False)

        if not self.runtime:
            # Fallback to Foveated Memory Proxy (8400) or Soul (8000)
            try:
                import urllib.request

                prompt_data = json.dumps(
                    {
                        "model": "foveated-memory",
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                        "stream": False,
                    }
                ).encode()
                req = urllib.request.Request(
                    "http://127.0.0.1:8400/v1/chat/completions",
                    data=prompt_data,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": "Bearer builder_bot",
                    },
                )
                loop = asyncio.get_event_loop()
                resp = await loop.run_in_executor(
                    None, urllib.request.urlopen, req, None, 30
                )
                res_obj = json.loads(resp.read().decode())
                reply = res_obj["choices"][0]["message"]["content"]
                logger.info(f'[IPC] Chat response from :8400: "{reply[:80]}"')
                await self._send(ws, "chat.response", {"text": reply})
                await self._handle_tts(ws, {"text": reply})
                return
            except Exception as e:
                logger.warning(f"[IPC] :8400 chat fallback failed: {e}")
                try:
                    import urllib.request

                    prompt_data = json.dumps(
                        {"message": text, "session_id": "quest3_alice"}
                    ).encode()
                    req = urllib.request.Request(
                        "http://127.0.0.1:8402/v1/chat/completions",
                        data=json.dumps(
                            {
                                "model": "xrlf",
                                "messages": [{"role": "user", "content": text}],
                                "max_tokens": 512,
                            }
                        ).encode(),
                        headers={"Content-Type": "application/json"},
                    )
                    loop = asyncio.get_event_loop()
                    resp = await loop.run_in_executor(
                        None, urllib.request.urlopen, req, None, 30
                    )
                    res_obj = json.loads(resp.read().decode())
                    reply = res_obj["choices"][0]["message"]["content"]
                    logger.info(f'[IPC] Chat response from :8402: "{reply[:80]}"')
                    await self._send(ws, "chat.response", {"text": reply})
                    await self._handle_tts(ws, {"text": reply})
                    return
                except Exception as ex2:
                    logger.error(f"[IPC] XRLF :8402 fallback failed: {ex2}")
                    await self._send_error(ws, f"Chat generation failed: {e}")
                    return

        try:
            if stream:
                # Stream tokens back over the socket
                gen = self.runtime.chat(
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=True,
                    has_image=has_image,
                    has_audio=has_audio,
                    has_video=has_video,
                )
                full_text = ""
                async_token_count = 0

                for token in gen:
                    if isinstance(token, str) and token:
                        full_text += token
                        async_token_count += 1
                        # Send each token as a stream event
                        await self._send(
                            ws,
                            "chat.stream",
                            {
                                "token": token,
                                "index": async_token_count,
                            },
                        )

                # Send final complete response
                emotion, intensity = self._extract_emotion(full_text)
                await self._send(
                    ws,
                    "chat.response",
                    {
                        "text": full_text,
                        "emotion": emotion,
                        "intensity": intensity,
                        "tokens": async_token_count,
                    },
                )

                # Auto-trigger TTS — strip emojis first
                tts_text = _strip_emojis(full_text)
                print(f"[IPC] Stream done. tts_text={tts_text[:80]!r}", flush=True)
                if tts_text:
                    await self._handle_tts(ws, {"text": tts_text})
            else:
                # Non-streaming — get full response
                response = self.runtime.chat(
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=False,
                    has_image=has_image,
                    has_audio=has_audio,
                    has_video=has_video,
                )
                response_text = response if isinstance(response, str) else str(response)
                emotion, intensity = self._extract_emotion(response_text)
                await self._send(
                    ws,
                    "chat.response",
                    {
                        "text": response_text,
                        "emotion": emotion,
                        "intensity": intensity,
                    },
                )

                # Auto-trigger TTS — strip emojis and raw emoji codes first
                tts_text = _strip_emojis(response_text)
                logger.info(f"[IPC] Non-stream TTS trigger: tts_text={tts_text[:80]!r}")
                if tts_text:
                    await self._handle_tts(ws, {"text": tts_text})

        except Exception as e:
            logger.error(f"[IPC] Chat error: {e}", exc_info=True)
            await self._send_error(ws, f"Chat failed: {e}")

    # ── Audio (STT) ─────────────────────────────────────────────────────────

    async def _handle_audio(self, ws, payload):
        """Handle incoming audio — use faster-whisper (CPU) to avoid CUDA VMM pool crash.
        The Gemma audio encoder triggers GGML_ASSERT in ggml-cuda.cu when run alongside
        the main text model, so we bypass native STT entirely.
        """
        audio_b64 = payload.get("audio_base64", "")
        if not audio_b64:
            await self._send_error(ws, "No audio data")
            return

        audio_format = payload.get("format", "audio/wav")

        # Decode audio and run faster-whisper STT (CPU only — no CUDA conflict)
        try:
            import base64
            import io
            import wave

            import numpy as np

            audio_bytes = base64.b64decode(audio_b64)
            # Parse WAV header to get raw PCM
            with io.BytesIO(audio_bytes) as wav_io:
                with wave.open(wav_io, "rb") as wav_file:
                    frames = wav_file.readframes(wav_file.getnframes())
                    sample_rate = wav_file.getframerate()
                    sample_width = wav_file.getsampwidth()
                    n_channels = wav_file.getnchannels()
            samples = np.frombuffer(frames, dtype=np.int16)
            # Route through faster-whisper (CPU only — no CUDA conflict)
            text = await self._transcribe_with_fwhisper(ws, samples)
            if text:
                # Dispatch into chat so the model responds to what was just heard
                await self._handle_chat(ws, {"text": text}, stream=True)
        except Exception as e:
            logger.error(f"[IPC] Audio decode/STT failed: {e}")
            await self._send_error(ws, f"STT failed: {e}")

    # ── Vision ──────────────────────────────────────────────────────────────

    async def _handle_vision_frame(self, ws, payload):
        """Handle a vision.frame event from the Quest VisionGrabber.
        The image is passed to the multimodal model as a data URL.
        """
        image_b64 = payload.get("image_base64", "")
        if not image_b64:
            await self._send_error(ws, "No image data in vision.frame")
            return

        perspective = payload.get("perspective", "user")
        direction = payload.get("direction", "")

        # Build a multimodal chat message with the image
        data_url = f"data:image/jpeg;base64,{image_b64}"
        prompt_text = f"[Captured a photo from {perspective} perspective, facing {direction}] Describe what you see in this image."

        messages = [
            {"role": "system", "content": ALICE_PERSONA},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_text},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ]

        logger.info(
            f"[IPC] Vision frame: {perspective}, {direction}, {len(image_b64)} bytes b64"
        )

        try:
            if self.runtime:
                response = self.runtime.chat(
                    messages=messages,
                    max_tokens=512,
                    temperature=0.7,
                    stream=False,
                    has_image=True,
                )
                response_text = response if isinstance(response, str) else str(response)
                emotion, intensity = self._extract_emotion(response_text)
                await self._send(
                    ws,
                    "chat.response",
                    {
                        "text": response_text,
                        "emotion": emotion,
                        "intensity": intensity,
                    },
                )
                # Auto-trigger TTS
                await self._handle_tts(ws, {"text": response_text})
            else:
                await self._send_error(ws, "No runtime available for vision")
        except Exception as e:
            err_msg = str(e)
            logger.error(f"[IPC] Vision frame error: {err_msg}", exc_info=True)
            print(f"❌ [VISION ERROR] {err_msg}", flush=True)
            # Don't crash — send error to Quest and continue
            await ws_send_json(
                ws,
                {
                    "type": "error",
                    "source": "vision",
                    "message": f"Vision failed (text-only mode): {err_msg}",
                    "hint": "mmproj.gguf may be missing — vision disabled, text still works.",
                },
            )

    # ── TTS ─────────────────────────────────────────────────────────────────

    async def _handle_tts(self, ws, payload):
        """Handle TTS request — generate audio via Kokoro directly."""
        text = payload.get("text", "")
        if not text:
            await self._send_error(ws, "No text for TTS")
            return

        voice = payload.get("voice", "af_heart")
        print(f'[IPC] TTS requested: "{text[:80]}" voice={voice}', flush=True)

        try:
            # Generate PCM directly with Kokoro
            pcm_data = await asyncio.get_event_loop().run_in_executor(
                None, self._kokoro_tts, text, voice, 24000
            )
            print(
                f"[IPC] Kokoro returned: {len(pcm_data) if pcm_data else 0} bytes",
                flush=True,
            )

            if pcm_data:
                # Convert to WAV for the tts.response event
                import io
                import wave

                wav_buf = io.BytesIO()
                with wave.open(wav_buf, "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(24000)
                    wav.writeframes(pcm_data)
                audio_b64 = base64.b64encode(wav_buf.getvalue()).decode()
                print(
                    f"[IPC] Sending tts.response: {len(audio_b64)} chars b64",
                    flush=True,
                )
                await self._send(
                    ws,
                    "tts.response",
                    {
                        "audio_base64": audio_b64,
                        "format": "audio/wav",
                        "engine": "kokoro",
                        "text": text,
                    },
                )
                logger.info(
                    f'[IPC] TTS (Kokoro direct): {len(pcm_data)} bytes for "{text[:60]}"'
                )
            else:
                await self._send_error(ws, "TTS produced no audio")
        except Exception as e:
            logger.error(f"[IPC] TTS error: {e}", exc_info=True)
            await self._send_error(ws, f"TTS failed: {e}")

    # ── Settings ────────────────────────────────────────────────────────────

    async def _handle_settings(self, ws, payload):
        """Handle settings toggle from client."""
        setting = payload.get("setting", "")
        value = payload.get("value")
        logger.info(f"[IPC] Settings: {setting}={value}")

        if setting == "tts_engine":
            if value == "qwen":
                self.mouth_url = "http://127.0.0.1:8402"
                logger.info(f"[IPC] Switched Mouth URL to: {self.mouth_url}")
            elif value == "fish":
                self.mouth_url = "http://127.0.0.1:8005"
                logger.info(f"[IPC] Switched Mouth URL to: {self.mouth_url}")

        # Broadcast to all clients
        await self.broadcast("settings.toggle", {"setting": setting, "value": value})

    # ── XRL Expand ──────────────────────────────────────────────────────────

    async def _handle_xrl_expand(self, ws, payload):
        """Handle XRL shadow memory expansion."""
        hash_val = payload.get("hash", "")
        logger.info(f"[IPC] XRL expand: {hash_val}")
        # TODO: Trigger shadow memory fetch from runtime
        await self._send(ws, "xrl.expand", {"hash": hash_val, "status": "acknowledged"})

    # ── Emotion extraction ──────────────────────────────────────────────────

    def _extract_emotion(self, text: str) -> tuple:
        """Extract emotion tag from response text if present.
        Format: [emotion:happiness:0.8] or <emotion:anger:0.9>
        """
        import re

        match = re.search(r"\[(?:emotion|emo):(\w+):([\d.]+)\]", text)
        if match:
            return match.group(1), float(match.group(2))
        match = re.search(r"<(?:emotion|emo):(\w+):([\d.]+)>", text)
        if match:
            return match.group(1), float(match.group(2))
        return "neutral", 0.0

    # ── Broadcast & send helpers ────────────────────────────────────────────

    async def _send(self, ws, event: str, payload: dict):
        """Send a message to a single client."""
        msg = json.dumps({"event": event, "payload": payload, "timestamp": time.time()})
        try:
            await ws.send(msg)
        except websockets.ConnectionClosed:
            self._clients.discard(ws)

    async def _send_error(self, ws, message: str):
        """Send an error to a single client."""
        await self._send(ws, "error", {"message": message})

    async def broadcast(self, event: str, payload: dict):
        """Broadcast a message to all connected clients. Self-healing: failed clients are pruned."""
        if not self._clients:
            return
        msg = json.dumps({"event": event, "payload": payload, "timestamp": time.time()})

        # Send concurrently — one slow/dead client doesn't block others
        async def _safe_send(ws):
            try:
                await ws.send(msg)
                return None
            except Exception:
                return ws  # Return the failed client for pruning

        results = await asyncio.gather(
            *[_safe_send(ws) for ws in list(self._clients)], return_exceptions=True
        )
        # Prune failed clients
        for r in results:
            if (
                r is not None
                and WebSocketServerProtocol is not None
                and isinstance(r, WebSocketServerProtocol)
            ):
                self._clients.discard(r)

    # ── HTTP handler (process_request) ─────────────────────────────────────
    # The websockets library calls process_request before the WS handshake.
    # If it returns a Response, the HTTP request is served without upgrading.
    # This lets :8400 serve BOTH HTTP (web requests, proxy) and WebSocket.

    async def _process_request(self, connection, request):
        """
        Handle HTTP requests on the same port as WebSocket.
        In websockets 17+, signature is (ServerConnection, Request).

        Routes:
          /health               → health check
          /soul/status          → proxy to XRLF :8402
        WebSocket upgrades return None → normal WS handshake.
        """
        # Get path and headers from the Request object
        try:
            path = request.path
        except Exception:
            return None

        # Check if this is a WebSocket upgrade request
        try:
            upgrade = request.headers.get("Upgrade", "") or ""
        except Exception:
            upgrade = ""
        if "websocket" in upgrade.lower():
            return None  # Let the WS handshake proceed

        path_clean = path.split("?")[0].rstrip("/")

        try:
            if path_clean == "/health" or path_clean == "":
                body = json.dumps({"status": "ok", "port": self.port}).encode()
                from websockets.http11 import Response

                return Response(
                    200,
                    "OK",
                    websockets.Headers({"Content-Type": "application/json"}),
                    body,
                )

            if path_clean in ("/soul/status", "/memory/status", "/v1/models"):
                return await self._http_proxy_get(path_clean)

            # Unknown HTTP path — let WS handle it
            return None
        except Exception as e:
            logger.error(f"[IPC] HTTP handler error: {e}")
            return None  # Fall through to WS on error

    async def _http_chat_proxy(self, request_headers):
        """Proxy HTTP chat completions to XRLF :8402."""
        import urllib.request

        # Read body from the request — websockets gives us the headers but
        # not the body directly. We need to use the raw reader.
        # For now, use the runtime directly if available, else proxy to 8402.
        target = self.runtime_url or "http://127.0.0.1:8402"
        try:
            # Forward to XRLF
            req = urllib.request.Request(
                f"{target}/v1/chat/completions",
                data=request_headers.get("Body", b""),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None, urllib.request.urlopen, req, None, 60
            )
            body = resp.read()
            return (200, {"Content-Type": "application/json"}, body)
        except Exception as e:
            logger.error(f"[IPC] HTTP chat proxy to {target} failed: {e}")
            body = json.dumps({"error": {"message": str(e)}}).encode()
            return (502, {"Content-Type": "application/json"}, body)

    async def _http_proxy_get(self, path):
        """Proxy a GET request to XRLF :8402."""
        import urllib.request

        from websockets.http11 import Response

        target = self.runtime_url or "http://127.0.0.1:8402"
        try:
            req = urllib.request.Request(f"{target}{path}")
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None, urllib.request.urlopen, req, None, 10
            )
            body = resp.read()
            return Response(
                200,
                "OK",
                websockets.Headers({"Content-Type": "application/json"}),
                body,
            )
        except Exception as e:
            body = json.dumps({"error": str(e)}).encode()
            return Response(
                502,
                "Bad Gateway",
                websockets.Headers({"Content-Type": "application/json"}),
                body,
            )

    # ── Lifecycle ───────────────────────────────────────────────────────────

    async def start(self):
        """Start the WebSocket server, gracefully adopting an already bound port if in use."""
        logger.info(
            f"[IPC] Starting WebSocket+HTTP server on ws://{self.host}:{self.port}{self.path}"
        )
        try:
            self._server = await websockets.serve(
                self.handler,
                self.host,
                self.port,
                process_request=self._process_request,
                ping_interval=20,
                ping_timeout=10,
                max_size=16 * 1024 * 1024,  # 16MB for audio payloads
            )
            logger.info(f"[IPC] ✅ WebSocket+HTTP server listening on :{self.port}")
            await asyncio.Future()  # run forever
        except OSError as e:
            is_address_in_use = (
                getattr(e, "errno", None) in (10048, 98)
                or getattr(e, "winerror", None) == 10048
                or "only one usage of each socket address" in str(e).lower()
                or "address already in use" in str(e).lower()
            )
            if is_address_in_use:
                logger.info(
                    f"[IPC] ⚡ WebSocket port :{self.port} is already in use by an active server. Gracefully adopting running WebSocket server on ws://{self.host}:{self.port}{self.path}"
                )
                print(
                    f"  ⚡ WebSocket port :{self.port} already bound — gracefully adopting active IPC server on ws://{self.host}:{self.port}{self.path}"
                )
                self.is_adopted = True
                try:
                    await asyncio.Event().wait()  # Park thread cleanly without erroring
                except asyncio.CancelledError:
                    pass
            else:
                logger.error(
                    f"[IPC] ❌ WebSocket server failed to bind on port {self.port}: {e}"
                )
                raise

    def start_sync(self, loop=None):
        """Start the server synchronously (blocking)."""
        if loop is None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        loop.run_until_complete(self.start())

    async def stop(self):
        """Stop the server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            logger.info("[IPC] WebSocket server stopped")
