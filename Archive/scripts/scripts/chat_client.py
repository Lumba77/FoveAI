#!/usr/bin/env python3
"""
scripts/chat_client.py — CLI Chat Client for 4-Way XR Conversation
===================================================================
Connects to the FoveAI chat relay (port 8407) and lets you send/receive
messages from the terminal. Messages also appear in the XR scene.

Usage:
  python scripts/chat_client.py --name user
  python scripts/chat_client.py --name devin
  python scripts/chat_client.py --name antigravity

Controls:
  Type a message and press Enter to send.
  Press Ctrl+C to quit.
"""

import argparse
import asyncio
import json
import os
import sys
from typing import Any

import websockets

# Color codes per speaker
COLORS: dict[str, str] = {
    "user": "\033[97m",  # white
    "jen": "\033[92m",  # green
    "devin": "\033[94m",  # blue
    "antigravity": "\033[93m",  # yellow/orange
}
RESET: str = "\033[0m"
DIM: str = "\033[90m"


async def chat_client(name: str, host: str, port: int) -> None:
    uri: str = f"ws://{host}:{port}/ws"
    print(f"{DIM}[Chat] Connecting to {uri} as '{name}'...{RESET}")

    try:
        async with websockets.connect(uri) as ws:
            print(
                f"{DIM}[Chat] Connected! Type a message and press Enter. Ctrl+C to quit.{RESET}"
            )
            print(f"{DIM}[Chat] ---{RESET}")

            # Task to read stdin and send messages
            async def send_loop() -> None:
                loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
                while True:
                    text: str = await loop.run_in_executor(None, input, "")
                    text = text.strip()
                    if not text:
                        continue
                    msg: dict[str, Any] = {
                        "type": "chat",
                        "from": name,
                        "text": text,
                    }
                    await ws.send(json.dumps(msg))

            # Task to receive messages and print them
            async def recv_loop() -> None:
                while True:
                    raw: str = await ws.recv()
                    try:
                        data: dict[str, Any] = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    if data.get("type") == "history":
                        for m in data.get("messages", []):
                            _print_message(m)
                        continue

                    if data.get("type") == "chat":
                        _print_message(data)

            await asyncio.gather(send_loop(), recv_loop())

    except KeyboardInterrupt:
        print(f"\n{DIM}[Chat] Disconnected.{RESET}")
    except ConnectionRefusedError:
        print(f"{DIM}[Chat] Could not connect to {uri}. Is the relay running?{RESET}")
        print(f"{DIM}[Chat] Start it with: python Backend/chat_relay_server.py{RESET}")
        sys.exit(1)


def _print_message(msg: dict[str, Any]) -> None:
    speaker: str = msg.get("from", "unknown")
    text: str = msg.get("text", "")
    timestamp: str = msg.get("time", "")
    color: str = COLORS.get(speaker, "\033[95m")
    # Short timestamp
    t: str = timestamp[11:19] if len(timestamp) >= 19 else timestamp
    print(f"{DIM}{t}{RESET} {color}{speaker:>12}{RESET}: {text}")


def main() -> int:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="FoveAI 4-Way Chat Client"
    )
    parser.add_argument(
        "--name",
        required=True,
        help="Your name in the chat (user, devin, antigravity, jen)",
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="Relay host (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("FOVEAI_BACKEND_PORT_CHAT", 8407)),
        help="Relay port",
    )
    args: argparse.Namespace = parser.parse_args()

    try:
        asyncio.run(chat_client(args.name, args.host, args.port))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
