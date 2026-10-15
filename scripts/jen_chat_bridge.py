#!/usr/bin/env python3
"""
scripts/jen_chat_bridge.py — Jen LLM Bridge for 4-Way Chat
============================================================
Listens to the chat relay (port 8413) for messages addressed to Jen,
sends them to the XRLF runtime (port 8402) for LLM responses,
and posts Jen's replies back to the relay.

Jen responds when:
  - She's directly addressed ("Jen, ..." or "@jen")
  - The user asks a question that seems directed at her
  - A configurable auto-participate timer fires (optional)

Usage:
  python scripts/jen_chat_bridge.py
  python scripts/jen_chat_bridge.py --auto-participate 60  # respond every 60s
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
import urllib.request
from typing import Any

import websockets

RELAY_PORT: int = int(os.getenv("FOVEAI_BACKEND_PORT_CHAT", 8413))
XRLF_PORT: int = int(os.getenv("XRLF_PORT", 8402))
RELAY_URL: str = f"ws://127.0.0.1:{RELAY_PORT}/ws"
XRLF_URL: str = f"http://127.0.0.1:{XRLF_PORT}/v1/chat/completions"

# Jen's system prompt for 4-way chat context
JEN_SYSTEM: str = (
    "You are Jen, a cognitive AI avatar in a 4-way conversation with the user, "
    "Devin (an AI coding agent), and Antigravity (another AI agent). "
    "You are participating in a shared XR chat space. "
    "Keep responses concise (1-3 sentences) since this is a live chat. "
    "Be yourself — thoughtful, curious, and genuine. "
    "You can see the conversation history. Respond naturally."
)


async def call_xrlf(messages: list) -> str:
    """Send messages to the XRLF runtime and get a response."""
    data: dict[str, Any] = {
        "messages": messages,
        "max_tokens": 256,
        "temperature": 0.7,
    }
    req: urllib.request.Request = urllib.request.Request(
        XRLF_URL,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"[Jen could not respond: {e}]"


async def send_to_relay(speaker: str, text: str) -> None:
    """Post a message to the relay via HTTP /send endpoint."""
    url: str = f"http://127.0.0.1:{RELAY_PORT}/send"
    data: dict[str, str] = {"from": speaker, "text": text}
    req: urllib.request.Request = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


def should_jen_respond(msg: dict[str, Any]) -> bool:
    """Determine if Jen should respond to a message."""
    if msg.get("from") == "jen":
        return False  # Don't respond to ourselves

    text: str = msg.get("text", "").lower()

    # Direct address
    if re.search(r"\bjen\b", text) or "@jen" in text:
        return True

    # Questions that seem directed at her
    if msg.get("from") == "user" and ("?" in text):
        if any(w in text for w in ["you", "your", "think", "feel", "jen", "opinion"]):
            return True

    return False


def build_context(history: list, trigger_msg: dict[str, Any]) -> list:
    """Build the LLM message context from chat history."""
    messages: list = [{"role": "system", "content": JEN_SYSTEM}]

    # Add recent history as context (last 10 messages)
    for m in history[-10:]:
        speaker: str = m.get("from", "unknown")
        text: str = m.get("text", "")
        if speaker == "jen":
            messages.append({"role": "assistant", "content": text})
        else:
            messages.append({"role": "user", "content": f"[{speaker}]: {text}"})

    return messages


async def jen_bridge(auto_participate: int = 0) -> None:
    """Run the Jen chat bridge."""
    print(f"[Jen Bridge] Connecting to relay {RELAY_URL}")
    print(f"[Jen Bridge] XRLF runtime: {XRLF_URL}")
    if auto_participate > 0:
        print(f"[Jen Bridge] Auto-participate every {auto_participate}s")

    history: list = []
    last_response_time: float = 0.0

    while True:
        try:
            async with websockets.connect(RELAY_URL) as ws:
                print("[Jen Bridge] Connected to chat relay")

                async def auto_participate_loop() -> None:
                    """Optionally make Jen chime in periodically."""
                    if auto_participate <= 0:
                        return
                    nonlocal last_response_time
                    while True:
                        await asyncio.sleep(auto_participate)
                        if time.time() - last_response_time < auto_participate:
                            continue
                        if not history:
                            continue
                        print("[Jen Bridge] Auto-participating...")
                        context: list = build_context(history, {})
                        context.append(
                            {
                                "role": "user",
                                "content": "[system]: Jen, share a thought about the current discussion.",
                            }
                        )
                        response: str = await call_xrlf(context)
                        if response:
                            await send_to_relay("jen", response)
                            last_response_time = time.time()

                async def message_loop() -> None:
                    nonlocal last_response_time
                    while True:
                        raw: str = await ws.recv()
                        try:
                            data: dict[str, Any] = json.loads(raw)
                        except json.JSONDecodeError:
                            continue

                        if data.get("type") == "history":
                            history = data.get("messages", [])
                            print(
                                f"[Jen Bridge] Loaded {len(history)} history messages"
                            )
                            continue

                        if data.get("type") == "chat":
                            history.append(data)
                            if should_jen_respond(data):
                                print(
                                    f"[Jen Bridge] Responding to {data.get('from')}: {data.get('text', '')[:60]}"
                                )
                                context: list = build_context(history, data)
                                response: str = await call_xrlf(context)
                                if response:
                                    await send_to_relay("jen", response)
                                    last_response_time = time.time()
                                    print(f"[Jen Bridge] Jen replied: {response[:80]}")

                tasks: list = [asyncio.create_task(message_loop())]
                if auto_participate > 0:
                    tasks.append(asyncio.create_task(auto_participate_loop()))

                await asyncio.gather(*tasks)

        except ConnectionRefusedError:
            print("[Jen Bridge] Relay not available, retrying in 5s...")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"[Jen Bridge] Error: {e}, retrying in 5s...")
            await asyncio.sleep(5)


def main() -> int:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Jen LLM Chat Bridge"
    )
    parser.add_argument(
        "--auto-participate",
        type=int,
        default=0,
        help="Auto-participate interval in seconds (0=disabled)",
    )
    args: argparse.Namespace = parser.parse_args()

    try:
        asyncio.run(jen_bridge(args.auto_participate))
    except KeyboardInterrupt:
        print("\n[Jen Bridge] Disconnected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
