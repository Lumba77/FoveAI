"""FoveAI virtual gamepad service — the body's actuator channel.

Serves the virtual controller on the hands/motor port (8410). The single
source of truth for the driver is ``gamepad_driver.VirtualGamepad``; this
module only adds transport. (The old ``Backend/foveai_gamepad_linux.py``
was a verbatim copy of the driver on retired port 8005 and is redundant.)

Protocol, deliberately permissive — the previous client nested everything
under ``state`` while the driver read top-level keys, which silently
zeroed every axis and button. Both shapes are accepted now:

    {"buttons":[0|1 x16], "leftStick":{"x":-1..1,"y":-1..1}, ...}
    {"type":"gamepad", "state":{ ...same fields... }}

Buttons follow the driver mapping:
    0 A   1 B   2 X   3 Y   4 LB  5 RB  6-7 triggers (ABS)
    8 SELECT  9 START  10 LStick  11 RStick  12-15 dpad Up Down Left Right

Run ``--selftest`` to create the pad, print the node, and exit.
"""

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from Backend.app.IPC.gamepad_driver import VirtualGamepad  # noqa: E402

PORT = int(os.environ.get("FOVEAI_GAMEPAD_PORT", "8410"))
HOST = os.environ.get("FOVEAI_GAMEPAD_HOST", "127.0.0.1")
LOG = logging.getLogger("foveai.gamepad")


def _stick(value, x: float = 0.0, y: float = 0.0):
    """Normalise a stick to ``[x, y]``.

    The driver indexes ``ls[0]``/``ls[1]``, so a dict raises KeyError inside
    the driver's bare ``except`` and the pad dies with only a log line. Accept
    ``[x, y]`` or ``{x, y}`` and clamp, so a malformed frame cannot silently
    stop the controller.
    """
    if isinstance(value, dict):
        value = [value.get("x", x), value.get("y", y)]
    elif isinstance(value, (list, tuple)) and len(value) >= 2:
        value = [value[0], value[1]]
    else:
        value = [x, y]
    try:
        return [max(-1.0, min(1.0, float(value[0]))), max(-1.0, min(1.0, float(value[1])))]
    except (TypeError, ValueError):
        return [x, y]


def _flatten(payload: dict) -> dict:
    """Accept both the flat shape and the nested ``state`` shape."""
    if not isinstance(payload, dict):
        return {}
    inner = payload.get("state")
    if isinstance(inner, dict):
        merged = dict(payload)
        merged.pop("state", None)
        merged.update(inner)
        return merged
    return payload


class GamepadService:
    def __init__(self) -> None:
        self.pad = VirtualGamepad()
        if getattr(self.pad, "ui", None) is None:
            LOG.error("virtual gamepad unavailable (evdev missing or /dev/uinput denied)")
        else:
            LOG.info("virtual gamepad created: %s", getattr(self.pad, "device_path", "/dev/uinput"))

    async def handle(self, websocket) -> None:
        peer = getattr(websocket, "remote_address", None)
        LOG.info("controller client connected: %s", peer)
        try:
            async for raw in websocket:
                try:
                    msg = json.loads(raw)
                except (ValueError, TypeError):
                    LOG.warning("dropping non-JSON frame (%d bytes)", len(raw or b""))
                    continue
                data = _flatten(msg)
                data["leftStick"] = _stick(data.get("leftStick"), 0.0, 0.0)
                data["rightStick"] = _stick(data.get("rightStick"), 0.0, 0.0)
                self.pad.handle_payload(data)
        except Exception as exc:  # a dead socket must never take the pad down
            LOG.warning("controller link ended (%s): %s", peer, exc)
        finally:
            LOG.info("controller client disconnected: %s", peer)

    async def run(self) -> None:
        import websockets

        stop = asyncio.get_running_loop().create_future()

        def _shutdown(*_):
            stop.done() or stop.set_result(None)

        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, _shutdown)

        async with websockets.serve(self.handle, HOST, PORT):
            LOG.info("gamepad WS listening on ws://%s:%d/controller", HOST, PORT)
            await stop
        LOG.info("gamepad service stopped")


def selftest() -> int:
    pad = VirtualGamepad()
    if getattr(pad, "ui", None) is None:
        print("FAIL: no virtual device (evdev missing or /dev/uinput not writable)")
        return 1
    node = getattr(pad, "device_path", "/dev/uinput")
    print(f"OK: virtual gamepad active at {node}")
    pad.ui.syn() if hasattr(pad.ui, "syn") else None
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="FoveAI virtual gamepad service")
    ap.add_argument("--selftest", action="store_true", help="create the pad, report, exit")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.selftest:
        return selftest()
    try:
        asyncio.run(GamepadService().run())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
