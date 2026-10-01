#!/usr/bin/env python3
"""
FoveAI SoftLayer Server — serves hot-reloadable JS modules to the Quest.

Watches the softlayer/ directory for .js file changes and pushes updates
to connected Quest clients via the existing WebSocket (:8403).

Also serves modules over HTTP for initial load:
  GET /softlayer/{name}.js  →  returns the JS module source

The Quest's SoftLayerEngine fetches modules on startup, then receives
hot-reload pushes via WS events:
  {"event": "softlayer.update", "payload": {"module": "hud_config", "source": "..."}}

Usage:
  python3 softlayer_server.py [--dir softlayer/] [--watch]

Or integrate into the existing XRLF server by importing SoftLayerWatcher.
"""

import asyncio
import json
import time
from collections.abc import Callable
from pathlib import Path

import watchdog.events
import watchdog.observers

# ── SoftLayer directory ─────────────────────────────────────────────────────

SOFTLAYER_DIR = Path(__file__).parent.parent / "softlayer"


class SoftLayerWatcher:
    """Watches the softlayer/ directory and pushes updates to WS clients."""

    def __init__(self, ws_broadcast: Callable, softlayer_dir: Path = SOFTLAYER_DIR):
        self.ws_broadcast = ws_broadcast
        self.softlayer_dir = softlayer_dir
        self.observer = None
        self._cache: dict[str, str] = {}

        # Ensure directory exists
        self.softlayer_dir.mkdir(parents=True, exist_ok=True)

    def start(self):
        """Start watching for file changes."""
        if not self.softlayer_dir.exists():
            print(f"[SoftLayer] Directory not found: {self.softlayer_dir}", flush=True)
            return

        # Load all modules into cache
        self._load_all()

        # Start file watcher
        handler = _SoftLayerHandler(self)
        self.observer = watchdog.observers.Observer()
        self.observer.schedule(handler, str(self.softlayer_dir), recursive=True)
        self.observer.start()
        print(f"[SoftLayer] Watching {self.softlayer_dir} for changes", flush=True)

    def stop(self):
        if self.observer:
            self.observer.stop()
            self.observer.join()

    def _load_all(self):
        """Load all .js files into cache."""
        for js_file in self.softlayer_dir.glob("*.js"):
            name = js_file.stem
            source = js_file.read_text(encoding="utf-8")
            self._cache[name] = source
            print(f"[SoftLayer] Cached: {name}.js ({len(source)} bytes)", flush=True)

    def get_module(self, name: str) -> str | None:
        """Get a module's source code by name."""
        if name in self._cache:
            return self._cache[name]

        # Try loading from disk
        js_file = self.softlayer_dir / f"{name}.js"
        if js_file.exists():
            source = js_file.read_text(encoding="utf-8")
            self._cache[name] = source
            return source
        return None

    def list_modules(self) -> list[str]:
        """List all available module names."""
        return list(self._cache.keys())

    async def on_file_changed(self, filepath: Path):
        """Called when a .js file changes — push update to WS clients."""
        name = filepath.stem
        try:
            source = filepath.read_text(encoding="utf-8")
            self._cache[name] = source
            print(
                f"[SoftLayer] Hot-reload: {name}.js ({len(source)} bytes)", flush=True
            )

            # Push to all WS clients
            msg = json.dumps(
                {
                    "event": "softlayer.update",
                    "payload": {
                        "module": name,
                        "source": source,
                    },
                }
            )
            await self.ws_broadcast(msg)
        except Exception as e:
            print(f"[SoftLayer] Reload error for {name}: {e}", flush=True)


class _SoftLayerHandler(watchdog.events.FileSystemEventHandler):
    """File system event handler for softlayer/ directory."""

    def __init__(self, watcher: SoftLayerWatcher):
        self.watcher = watcher
        self._debounce = 0.5
        self._last_event = 0.0

    def on_modified(self, event):
        if event.is_directory:
            return
        if not event.src_path.endswith(".js"):
            return

        # Debounce — editors often write multiple events
        now = time.time()
        if now - self._last_event < self._debounce:
            return
        self._last_event = now

        filepath = Path(event.src_path)
        # Run the async handler in the event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self.watcher.on_file_changed(filepath), loop
                )
        except Exception:
            pass


# ── HTTP serving (for initial module load) ──────────────────────────────────


def setup_softlayer_routes(app, watcher: SoftLayerWatcher):
    """Add softlayer routes to a FastAPI/Starlette app."""

    from fastapi import HTTPException
    from fastapi.responses import PlainTextResponse

    @app.get("/softlayer/{module_name}.js")
    async def get_softlayer_module(module_name: str):
        source = watcher.get_module(module_name)
        if source is None:
            raise HTTPException(
                status_code=404, detail=f"Module '{module_name}' not found"
            )
        return PlainTextResponse(source, media_type="application/javascript")

    @app.get("/softlayer")
    async def list_softlayer_modules():
        return {"modules": watcher.list_modules()}


# ── Standalone mode ─────────────────────────────────────────────────────────


async def standalone():
    """Run standalone with a simple HTTP server + file watcher."""
    import uvicorn
    from fastapi import FastAPI

    app = FastAPI()

    # Simple broadcast (just print in standalone mode)
    async def broadcast(msg):
        print(f"[SoftLayer] Would broadcast: {msg[:100]}...", flush=True)

    watcher = SoftLayerWatcher(broadcast)
    watcher.start()
    setup_softlayer_routes(app, watcher)

    config = uvicorn.Config(app, host="0.0.0.0", port=8402, log_level="warning")
    server = uvicorn.Server(config)

    print(
        f"""
  ╔══════════════════════════════════════════════════╗
  ║  FoveAI SoftLayer Server                         ║
  ╠══════════════════════════════════════════════════╣
  ║  Modules: {watcher.softlayer_dir!s:<40s} ║
  ║  HTTP: http://0.0.0.0:8402/softlayer/            ║
  ║  Watch: {"ON" if watcher.observer else "OFF":<44s} ║
  ╚══════════════════════════════════════════════════╝
    """,
        flush=True,
    )

    await server.serve()


if __name__ == "__main__":
    asyncio.run(standalone())
