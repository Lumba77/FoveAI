"""
The Forge CLI Bridge — Async subprocess manager for Cline CLI 3.

Spawns Cline CLI 3 as a managed async subprocess, reads its --json stream
line-by-line, parses structured JSON events, and fans them out to all
registered subscribers (WebSocket, file watcher, context vault, MCP memory).

Architecture:
    cline_bridge.py
    ├── spawn()          → asyncio.create_subprocess_exec
    ├── _read_stream()   → stdout line reader + JSON parser
    ├── _route_event()   → fan-out to subscribers
    └── subscribers      → list of async callbacks

Event types parsed from Cline --json stream:
    - tool_call       → {type, tool, args, timestamp}
    - tool_result     → {type, tool, result, duration_ms}
    - thought         → {type, content, timestamp}
    - response        → {type, content, model, tokens}
    - file_edit       → {type, path, diff, timestamp}
    - session_start   → {type, session_id, model, timestamp}
    - session_end     → {type, session_id, reason, duration_s}
    - error           → {type, message, code, timestamp}
"""

import asyncio
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Awaitable, Dict, Any, List

logger = logging.getLogger("forge.cline_bridge")

# ── Event Types ──────────────────────────────────────────────────────────
EVENT_TOOL_CALL = "tool_call"
EVENT_TOOL_RESULT = "tool_result"
EVENT_THOUGHT = "thought"
EVENT_RESPONSE = "response"
EVENT_FILE_EDIT = "file_edit"
EVENT_SESSION_START = "session_start"
EVENT_SESSION_END = "session_end"
EVENT_ERROR = "error"
EVENT_SYSTEM = "system"

# ── Subscriber callback type ─────────────────────────────────────────────
Subscriber = Callable[[Dict[str, Any]], Awaitable[None]]


class ClineBridge:
    """
    Async bridge to Cline CLI 3 subprocess.

    Usage:
        bridge = ClineBridge(workspace="C:\\Users\\lumba\\Program\\FoveAI")
        bridge.subscribe(my_websocket_handler)
        bridge.subscribe(my_memory_handler)
        await bridge.spawn(model="deepseek-v4-pro")
        # ... agent runs ...
        await bridge.stop()
    """

    def __init__(
        self,
        workspace: str = None,
        cline_command: str = "cline",
        max_buffer_lines: int = 1000,
    ):
        self.workspace = Path(workspace or os.getcwd()).resolve()
        self.cline_command = cline_command
        self.max_buffer_lines = max_buffer_lines

        # Runtime state
        self.process: Optional[asyncio.subprocess.Process] = None
        self._session_id: Optional[str] = None
        self._model: Optional[str] = None
        self._started_at: Optional[float] = None
        self._running: bool = False
        self._subscribers: List[Subscriber] = []
        self._event_buffer: List[Dict[str, Any]] = []
        self._read_task: Optional[asyncio.Task] = None
        self._stderr_task: Optional[asyncio.Task] = None

    # ── Subscriber Management ────────────────────────────────────────────

    def subscribe(self, callback: Subscriber) -> None:
        """Register an async callback to receive all parsed events."""
        if callback not in self._subscribers:
            self._subscribers.append(callback)
            logger.debug(f"Subscriber added: {callback.__name__ if hasattr(callback, '__name__') else callback}")

    def unsubscribe(self, callback: Subscriber) -> None:
        """Remove a previously registered subscriber."""
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    # ── Process Lifecycle ─────────────────────────────────────────────────

    async def spawn(
        self,
        model: str = "deepseek-v4-pro",
        prompt: Optional[str] = None,
        extra_args: Optional[List[str]] = None,
    ) -> str:
        """
        Spawn Cline CLI 3 as an async subprocess.

        Args:
            model: The model to use (e.g., deepseek-v4-pro, glm-5.1-cloud)
            prompt: Optional initial prompt to send
            extra_args: Additional CLI arguments

        Returns:
            session_id: Unique session identifier

        Raises:
            RuntimeError: If process fails to start
        """
        if self._running:
            logger.warning("Bridge already running — stopping existing process first")
            await self.stop()

        self._session_id = f"forge_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.getpid()}"
        self._model = model
        self._started_at = time.time()

        # Build command
        cmd = [
            self.cline_command,
            "--json",              # Structured JSON output
            "--model", model,
            "--workspace", str(self.workspace),
        ]

        if prompt:
            cmd.extend(["--prompt", prompt])

        if extra_args:
            cmd.extend(extra_args)

        logger.info(f"Spawning Cline CLI 3: {' '.join(cmd)}")
        logger.info(f"Session: {self._session_id} | Model: {model} | Workspace: {self.workspace}")

        try:
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.workspace),
                env={**os.environ, "FORGE_SESSION_ID": self._session_id},
            )
        except FileNotFoundError:
            raise RuntimeError(
                f"Cline CLI not found: '{self.cline_command}'. "
                f"Ensure Cline CLI 3 is installed and in PATH."
            )
        except Exception as e:
            raise RuntimeError(f"Failed to spawn Cline CLI: {e}")

        self._running = True

        # Emit session_start event
        await self._emit({
            "type": EVENT_SESSION_START,
            "session_id": self._session_id,
            "model": model,
            "workspace": str(self.workspace),
            "timestamp": datetime.now().isoformat(),
        })

        # Start stream readers
        self._read_task = asyncio.create_task(self._read_stdout())
        self._stderr_task = asyncio.create_task(self._read_stderr())

        return self._session_id

    async def stop(self, reason: str = "user_requested") -> None:
        """
        Gracefully stop the Cline subprocess.

        Args:
            reason: Why the session is ending
        """
        if not self._running or self.process is None:
            return

        logger.info(f"Stopping Cline bridge: {reason}")
        duration_s = time.time() - (self._started_at or time.time())

        # Cancel reader tasks
        for task in [self._read_task, self._stderr_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Terminate process gracefully
        try:
            if sys.platform == "win32":
                self.process.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                self.process.terminate()

            try:
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("Process did not exit gracefully, killing")
                self.process.kill()
                await self.process.wait()
        except ProcessLookupError:
            pass  # Already exited

        # Emit session_end event
        await self._emit({
            "type": EVENT_SESSION_END,
            "session_id": self._session_id,
            "reason": reason,
            "duration_s": round(duration_s, 1),
            "timestamp": datetime.now().isoformat(),
        })

        self._running = False
        self.process = None
        self._read_task = None
        self._stderr_task = None
        logger.info(f"Cline bridge stopped (duration: {duration_s:.1f}s)")

    async def send_prompt(self, text: str) -> None:
        """
        Send a user prompt to the running Cline process via stdin.

        Args:
            text: The prompt text to send
        """
        if not self._running or self.process is None or self.process.stdin is None:
            raise RuntimeError("Cline bridge is not running")

        # Cline CLI reads prompts from stdin
        # We send the prompt followed by a newline
        prompt_json = json.dumps({"type": "user_prompt", "content": text}) + "\n"
        self.process.stdin.write(prompt_json.encode("utf-8"))
        await self.process.stdin.drain()

        logger.debug(f"Prompt sent: {text[:100]}...")

    # ── Stream Readers ────────────────────────────────────────────────────

    async def _read_stdout(self) -> None:
        """Read and parse JSON lines from Cline stdout."""
        if self.process is None or self.process.stdout is None:
            return

        buffer = ""
        while self._running:
            try:
                line_bytes = await self.process.stdout.readline()
                if not line_bytes:
                    # Process stdout closed
                    logger.info("Cline stdout closed")
                    break

                line = line_bytes.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                # Try to parse as JSON
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    # Might be partial JSON or plain text — buffer it
                    buffer += line
                    try:
                        event = json.loads(buffer)
                        buffer = ""
                    except json.JSONDecodeError:
                        # Still incomplete, keep buffering
                        if len(buffer) > 100_000:
                            logger.warning("Buffer overflow, discarding")
                            buffer = ""
                        continue

                # Normalize event
                if not isinstance(event, dict):
                    event = {"type": EVENT_SYSTEM, "content": str(event), "raw": line}

                if "type" not in event:
                    event["type"] = EVENT_SYSTEM

                event.setdefault("session_id", self._session_id)
                event.setdefault("timestamp", datetime.now().isoformat())

                await self._route_event(event)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error reading stdout: {e}")
                await self._emit({
                    "type": EVENT_ERROR,
                    "message": f"Stdout read error: {e}",
                    "code": "stdout_read_error",
                    "session_id": self._session_id,
                    "timestamp": datetime.now().isoformat(),
                })

    async def _read_stderr(self) -> None:
        """Read stderr for error logging."""
        if self.process is None or self.process.stderr is None:
            return

        while self._running:
            try:
                line_bytes = await self.process.stderr.readline()
                if not line_bytes:
                    break

                line = line_bytes.decode("utf-8", errors="replace").strip()
                if line:
                    logger.warning(f"Cline stderr: {line}")
                    await self._emit({
                        "type": EVENT_SYSTEM,
                        "stream": "stderr",
                        "content": line,
                        "session_id": self._session_id,
                        "timestamp": datetime.now().isoformat(),
                    })

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error reading stderr: {e}")

    # ── Event Routing ─────────────────────────────────────────────────────

    async def _route_event(self, event: Dict[str, Any]) -> None:
        """
        Route a parsed event to all subscribers.

        Also maintains the internal event buffer for replay.
        """
        # Add to buffer (with cap)
        self._event_buffer.append(event)
        if len(self._event_buffer) > self.max_buffer_lines:
            self._event_buffer = self._event_buffer[-self.max_buffer_lines:]

        # Fan out to all subscribers
        for subscriber in self._subscribers:
            try:
                await subscriber(event)
            except Exception as e:
                logger.error(f"Subscriber error: {e}")

    async def _emit(self, event: Dict[str, Any]) -> None:
        """Emit an internally-generated event (not from Cline stdout)."""
        await self._route_event(event)

    # ── Public Properties ─────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def session_id(self) -> Optional[str]:
        return self._session_id

    @property
    def model(self) -> Optional[str]:
        return self._model

    @property
    def uptime_s(self) -> float:
        if self._started_at is None:
            return 0.0
        return time.time() - self._started_at

    def get_recent_events(self, count: int = 50) -> List[Dict[str, Any]]:
        """Return the most recent events from the buffer."""
        return self._event_buffer[-count:]

    def get_event_summary(self) -> Dict[str, int]:
        """Return counts of each event type in the buffer."""
        counts: Dict[str, int] = {}
        for event in self._event_buffer:
            t = event.get("type", "unknown")
            counts[t] = counts.get(t, 0) + 1
        return counts
