#!/usr/bin/env python3
"""
Tools/test_agent_handshake.py — Verify Open XRL Key-Based Identity & Challenge Handshake
======================================================================================
Tests:
  1. Negative test: Trying to register as 'jen' without signing -> challenge issued, unauthorized ops blocked.
  2. Negative test: Forged signature -> rejected.
  3. Positive test: Legitimate signature using ~/.ssh/id_ed25519 -> accepted: true, verified: true.
  4. Memory ops: Deposit and recall succeed once verified.
  5. Backwards compatibility: Un-enrolled model name auto-admitted as unverified.
"""

import asyncio
import base64
import json
import os
import subprocess
import sys
import websockets

WS_URL = "ws://127.0.0.1:8403/ws"


def sign_as_agent(agent_name: str, message: bytes) -> str:
    """Sign a message using the agent's private key via sudo -u <agent>."""
    py_code = f"""
import base64
from cryptography.hazmat.primitives.serialization import load_ssh_private_key
key_path = "/agent/{agent_name}/.ssh/id_ed25519"
with open(key_path, "rb") as f:
    priv = load_ssh_private_key(f.read(), password=None)
sig = priv.sign({repr(message)})
print(base64.b64encode(sig).decode())
"""
    cmd = ["sudo", "-S", "-u", agent_name, "python3", "-c", py_code]
    p = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Use standard host sudo if needed
    out, err = p.communicate(b"1im6a1UM6a*\n")
    if p.returncode != 0:
        raise RuntimeError(f"Signing failed ({p.returncode}): {err.decode()}")
    return out.decode().strip()


async def run_tests():
    print("=" * 60)
    print("Open XRL Handshake & Admitted Access Verification")
    print("=" * 60)

    # ---------------------------------------------------------
    # 1. Backwards Compatibility Test (Guest / Un-enrolled Model)
    # ---------------------------------------------------------
    print("\n[Test 1] Testing legacy/un-enrolled model registration...")
    async with websockets.connect(WS_URL) as ws:
        await ws.send(json.dumps({
            "event": "xrl.memory",
            "payload": {"op": "register", "model": "test-guest-model", "mode": "both"}
        }))
        resp = json.loads(await ws.recv())
        assert resp["event"] == "xrl.memory.hello", f"Unexpected response: {resp}"
        assert resp["payload"]["you"]["model"] == "test-guest-model"
        assert resp["payload"]["you"]["accepted"] is True
        assert resp["payload"]["you"]["verified"] is False
        print("  ✓ Un-enrolled model admitted as verified=False (backwards compatible)")

    # ---------------------------------------------------------
    # 2. Enrolled Agent Challenge Test (Jen)
    # ---------------------------------------------------------
    print("\n[Test 2] Testing enrolled agent challenge issuance...")
    async with websockets.connect(WS_URL) as ws:
        await ws.send(json.dumps({
            "event": "xrl.memory",
            "payload": {"op": "register", "model": "jen", "mode": "both"}
        }))
        challenge_resp = json.loads(await ws.recv())
        assert challenge_resp["event"] == "xrl.memory.challenge", f"Expected challenge, got {challenge_resp}"
        nonce = challenge_resp["payload"]["nonce"]
        msg = challenge_resp["payload"]["message"]
        print(f"  ✓ Server issued nonce: {nonce[:16]}... for agent jen")

        # ---------------------------------------------------------
        # 3. Negative Test: Premature ops blocked before verification
        # ---------------------------------------------------------
        print("\n[Test 3] Testing premature op rejection before challenge verification...")
        await ws.send(json.dumps({
            "event": "xrl.memory",
            "payload": {"op": "deposit", "unit": {"concept": "leak_test"}}
        }))
        err_resp = json.loads(await ws.recv())
        assert err_resp["event"] == "error", f"Expected error, got {err_resp}"
        assert "admission required" in err_resp["payload"]["message"]
        print("  ✓ Premature deposit blocked while challenge is pending")

        # ---------------------------------------------------------
        # 4. Negative Test: Forged signature rejected
        # ---------------------------------------------------------
        print("\n[Test 4] Testing forged signature rejection...")
        fake_sig = base64.b64encode(b"\x00" * 64).decode()
        await ws.send(json.dumps({
            "event": "xrl.memory",
            "payload": {
                "op": "verify",
                "model": "jen",
                "nonce": nonce,
                "signature": fake_sig
            }
        }))
        fake_err = json.loads(await ws.recv())
        assert fake_err["event"] == "error"
        assert "verification failed" in fake_err["payload"]["message"]
        print("  ✓ Forged signature successfully rejected")

    # ---------------------------------------------------------
    # 5. Positive Test: Legitimate Ed25519 signature handshake
    # ---------------------------------------------------------
    print("\n[Test 5] Testing legitimate Ed25519 signature handshake...")
    async with websockets.connect(WS_URL) as ws:
        await ws.send(json.dumps({
            "event": "xrl.memory",
            "payload": {"op": "register", "model": "jen", "mode": "both"}
        }))
        ch = json.loads(await ws.recv())
        nonce = ch["payload"]["nonce"]
        challenge_msg = ch["payload"]["message"].encode("utf-8")

        # Sign using jen's isolated key
        signature = sign_as_agent("jen", challenge_msg)
        print(f"  ✓ Signed challenge using /agent/jen/.ssh/id_ed25519")

        # Submit verification
        await ws.send(json.dumps({
            "event": "xrl.memory",
            "payload": {
                "op": "verify",
                "model": "jen",
                "nonce": nonce,
                "signature": signature
            }
        }))

        hello = json.loads(await ws.recv())
        assert hello["event"] == "xrl.memory.hello", f"Expected hello, got {hello}"
        assert hello["payload"]["you"]["model"] == "jen"
        assert hello["payload"]["you"]["accepted"] is True
        assert hello["payload"]["you"]["verified"] is True
        print("  ✓ Server accepted handshake: model=jen, accepted=True, verified=True")

        # ---------------------------------------------------------
        # 6. Admitted Memory Ops Test (Deposit + Recall)
        # ---------------------------------------------------------
        print("\n[Test 6] Testing admitted memory operations (deposit & recall)...")
        test_unit = {
            "title": "Open XRL Phase 2 Test",
            "content": "Admitted access verified via Ed25519 signature contract.",
            "type": "epistemic"
        }
        await ws.send(json.dumps({
            "event": "xrl.memory",
            "payload": {"op": "deposit", "unit": test_unit}
        }))
        ack = json.loads(await ws.recv())
        assert ack["event"] == "xrl.memory.ack" and ack["payload"]["stored"] is True
        print("  ✓ Deposit accepted and stored in resonant buffer")

        await ws.send(json.dumps({
            "event": "xrl.memory",
            "payload": {"op": "recall", "n": 1}
        }))
        recall = json.loads(await ws.recv())
        assert recall["event"] == "xrl.memory.recall"
        units = recall["payload"]["units"]
        assert len(units) > 0 and units[-1]["unit"]["title"] == "Open XRL Phase 2 Test"
        print("  ✓ Recalled deposit successfully from memory bus")

    print("\n" + "=" * 60)
    print("ALL OPEN XRL PHASE 2 SECURITY & HANDSHAKE TESTS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_tests())
