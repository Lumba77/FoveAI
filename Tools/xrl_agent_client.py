#!/usr/bin/env python3
"""xrl_agent_client.py — Open XRL memory-contract client for autonomous coders (Devin & Antigravity).

Performs the full admission handshake on the unified IPC socket and exposes
the memory ops as a CLI. Identity is the agent's own ed25519 key at
/agent/<model>/.ssh/id_ed25519 — lumba reads it via file ACL (setfacl),
the home dir itself stays private.

Lanes:
  deposit/recall — PRIVATE agent lane (grant + key verified, per-model units)
  telepathy      — COLLECTIVE long-form ledger (shared ring, broadcast to listeners)
  resonate       — COLLECTIVE state/feeling bus via :8400 HTTP ingest

Usage:
  xrl_agent_client.py [--agent antigravity|devin] deposit "summary text" [tag1 tag2 ...]
  xrl_agent_client.py [--agent antigravity|devin] recall [n]
  xrl_agent_client.py [--agent antigravity|devin] telepathy "long-form collective transmission"
  xrl_agent_client.py [--agent antigravity|devin] resonate "state note" [tag1 tag2 ...]
  xrl_agent_client.py [--agent antigravity|devin] ping
"""
import argparse
import asyncio
import base64
import json
import sys
import urllib.request
from pathlib import Path

import websockets
from cryptography.hazmat.primitives.serialization import load_ssh_private_key

WS_URL = "ws://127.0.0.1:8403/ws"
RESONANT_INGEST = "http://127.0.0.1:8400/api/resonance/ingest"


def get_agent_key_path(model: str) -> Path:
    return Path(f"/agent/{model}/.ssh/id_ed25519")


async def _session(model: str):
    key_path = get_agent_key_path(model)
    if not key_path.exists():
        raise SystemExit(f"Private key not accessible: {key_path}")
    key = load_ssh_private_key(key_path.read_bytes(), password=None)
    ws = await websockets.connect(WS_URL)
    await ws.send(json.dumps(
        {"event": "xrl.memory",
         "payload": {"op": "register", "model": model, "mode": "both"}}))
    ch = json.loads(await asyncio.wait_for(ws.recv(), 8))["payload"]
    sig = key.sign(ch["message"].encode())
    await ws.send(json.dumps(
        {"event": "xrl.memory",
         "payload": {"op": "verify", "model": model, "nonce": ch["nonce"],
                     "signature": base64.b64encode(sig).decode()}}))
    hello = json.loads(await asyncio.wait_for(ws.recv(), 8))
    if hello.get("event") != "xrl.memory.hello":
        raise SystemExit(f"admission failed: {hello}")
    return ws


async def _send_op(ws, payload, timeout=8):
    await ws.send(json.dumps({"event": "xrl.memory", "payload": payload}))
    try:
        return json.loads(await asyncio.wait_for(ws.recv(), timeout))
    except asyncio.TimeoutError:
        return {"event": "timeout"}


async def main():
    parser = argparse.ArgumentParser(description="Open XRL memory-contract client")
    parser.add_argument("--agent", "--model", default="devin", help="Agent identity (devin or antigravity)")
    parser.add_argument("cmd", nargs="?", default=None, help="Command: deposit | recall | telepathy | resonate | ping")
    parser.add_argument("args", nargs="*", help="Arguments for the command")

    parsed, unknown = parser.parse_known_args()

    # Allow positional or unknown args parsing cleanly
    cmd = parsed.cmd
    args = parsed.args + unknown
    model = parsed.agent.lower()

    if not cmd:
        parser.print_help()
        return

    if cmd == "resonate" and args:
        summary = args[0]
        tags = args[1:]
        body = json.dumps({"units": [{"model": model,
                                      "summary": summary,
                                      "tags": tags}]}).encode()
        req = urllib.request.Request(RESONANT_INGEST, data=body,
            headers={"Content-Type": "application/json"})
        print(urllib.request.urlopen(req, timeout=10).read().decode())
        return

    ws = await _session(model)
    try:
        if cmd == "deposit" and args:
            summary = args[0]
            tags = args[1:]
            print(await _send_op(ws, {"op": "deposit", "unit": {
                "summary": summary, "tags": tags}}))
        elif cmd == "recall":
            n = int(args[0]) if args else 5
            print(json.dumps(await _send_op(ws, {"op": "recall", "n": n}), indent=2))
        elif cmd == "telepathy" and args:
            text = args[0]
            tags = args[1:]
            await ws.send(json.dumps({"event": "xrl.telepathy", "payload": {
                "seq": 1, "blob": {"from": model, "text": text, "tags": tags}}}))
            print(json.loads(await asyncio.wait_for(ws.recv(), 8)))
        elif cmd == "ping":
            print(await _send_op(ws, {"op": "ping"}))
        else:
            parser.print_help()
    finally:
        await ws.close()


if __name__ == "__main__":
    asyncio.run(main())
