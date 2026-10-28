#!/usr/bin/env python3
"""
Tools/thalamus_xrl_bridge.py — Live Central Thalamus & Open XRL Bus Bridge
===========================================================================
Binds the Sleipnir Swarm to the live FoveAI WebSocket IPC on port :8403:
1. Connects to ws://127.0.0.1:8403/ws.
2. Registers Sleipnir on the Open XRL Memory Contract.
3. Exposes the Central Thalamus HTTP Router on port :8419.
4. On query: executes multi-tick routing -> emits pure specialist output -> deposits state into XRL bus.
5. Strict single-model residency with immediate garbage collection (Zero OOM).
"""

import os
import sys
import json
import time
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import websockets
import urllib.request
import urllib.error

ROOT = Path("/home/lumba/FoveAI")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Tools.central_thalamus_coordinator import CentralThalamus
from Tools.xrl_midhive_protocol import CollectiveWillProtocol, MidHiveWorkingMemory
from Backend.Cognition.MusicalDirector import CHORD_MAP

WS_URI = "ws://127.0.0.1:8403/ws"
RESONANCE_URL = "http://127.0.0.1:8400"
HTTP_PORT = 8420
thalamus = None
ws_connection = None

def evaluate_musical_chord(query: str, consensus: str, category: str) -> dict:
    """Evaluates the 432Hz emotional chord based on swarm tension and resolution."""
    ql = query.lower()
    cl = consensus.lower()

    if "DEFER" in consensus or "deadlock" in ql or "collapse" in ql:
        # Cognitive tension / systemic boundary friction
        chord = CHORD_MAP.get("FEAR", "D_HARMONIC")
        state = "DISSONANT_SUSPENSION"
        emotion = "TENSION"
    elif any(w in ql for w in ["feel", "family", "father", "friend", "lonely", "warm", "love"]):
        chord = CHORD_MAP.get("WARMTH", "C_MAJ7")
        state = "WARM_RESONANCE"
        emotion = "WARMTH"
    elif any(w in ql for w in ["why", "how", "reflect", "history", "maturation"]):
        chord = CHORD_MAP.get("REFLECTIVE", "A_MINOR")
        state = "INTIMATE_REFLECTION"
        emotion = "REFLECTIVE"
    elif any(w in ql for w in ["awe", "cosmos", "transcend", "universe"]):
        chord = CHORD_MAP.get("AWE", "F_LYDIAN")
        state = "EXPANSIVE_AWE"
        emotion = "AWE"
    else:
        # Harmonious consensus resolution
        chord = CHORD_MAP.get("JOY", "C_MAJOR")
        state = "RESOLVED_CONSONANCE"
        emotion = "JOY"

    return {
        "chord": chord,
        "emotion": emotion,
        "harmonic_state": state,
        "tuning_hz": 432
    }

def recall_kantian_ring(limit: int = 2) -> list:
    """Recalls latest cognitive memory seeds from Ring 1 / Resonance on :8400."""
    try:
        req = urllib.request.Request(f"{RESONANCE_URL}/api/resonance/tail?n={limit}")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("units", [])
    except Exception:
        return []

def deposit_kantian_memory(query: str, consensus: str, category: str = "relation", tags: list = None):
    """Deposits Kantian cognitive reasoning units to :8400 and :8403."""
    tags = tags or ["kantian-memory", "ring_1_cognitive", category]
    payload = {
        "model": "sleipnir-swarm",
        "workspace": "kantian-memory",
        "unit": {
            "summary": f"[{category.upper()}] {query[:60]} -> {consensus[:120]}",
            "query": query,
            "category": category,
            "consensus": consensus,
            "tags": tags,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z")
        }
    }
    try:
        req = urllib.request.Request(
            f"{RESONANCE_URL}/api/resonance/ingest",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            pass
    except Exception as e:
        print(f"[bridge] Note: Kantian ingest :8400: {e}")

class ThalamusHTTPHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        if self.path in ["/v1/chat/completions", "/api/chat", "/dispatch"]:
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len).decode("utf-8")
            data = json.loads(body)
            
            # Extract prompt from messages or prompt field
            query = ""
            if "messages" in data:
                for m in reversed(data["messages"]):
                    if m.get("role") == "user":
                        query = m.get("content", "")
                        break
            elif "prompt" in data:
                query = data["prompt"]
                
            mode = data.get("mode", "single")
            depth = data.get("depth", 0)
            max_tokens = data.get("max_tokens", 80)
            
            if mode == "midhive":
                # 1. Warm-start active recall from Ring 1 / Kantian Resonance (:8400)
                recalled = recall_kantian_ring(limit=2)
                kantian_context = ""
                if recalled:
                    summaries = [u.get("summary") or (u.get("unit") or {}).get("summary", "") for u in recalled]
                    summaries = [s for s in summaries if s]
                    if summaries:
                        kantian_context = " | ".join(summaries[-2:])
                
                # Execute Mid-Hive Collective Will Protocol (Colonies bring will to ring_2_mid)
                runners = {
                    "receptor": lambda p, max_tokens=60: thalamus.generate_with_colony("receptor", p, depth=0, max_tokens=max_tokens)["output"],
                    "history": lambda p, max_tokens=60: thalamus.generate_with_colony("history", p, depth=0, max_tokens=max_tokens)["output"],
                    "finance": lambda p, max_tokens=60: thalamus.generate_with_colony("finance", p, depth=0, max_tokens=max_tokens)["output"],
                    "constitutive_base": lambda p, max_tokens=70: thalamus.generate_with_colony("constitutive", p, depth=0, max_tokens=max_tokens)["output"]
                }
                protocol = CollectiveWillProtocol()
                cycle_res = protocol.execute_resonance_cycle(query, runners)
                thalamus.unload()
                
                output_content = cycle_res["consensus"]
                
                # Determine Kantian Cognitive Category
                cat = "relation"  # Default: causal relation
                if "DEFER" in output_content or "boundary" in query.lower() or "limit" in query.lower():
                    cat = "modality"
                elif "thread" in query.lower() or "seed" in query.lower():
                    cat = "substance"
                elif "swarm" in query.lower() or "consensus" in query.lower():
                    cat = "reciprocity"

                # 2. Deposit to Ring 1 Kantian Cognitive Memory (:8400)
                deposit_kantian_memory(query, output_content, category=cat)

                # 3. Evaluate 432Hz Acoustic Musical Chord (Harmonic Paradigm)
                chord_info = evaluate_musical_chord(query, output_content, cat)

                meta = {
                    "protocol": "midhive_collective",
                    "ring": "ring_2_mid",
                    "kantian_category": cat,
                    "kantian_recall": kantian_context,
                    "musical_chord": chord_info,
                    "log": cycle_res["log"]
                }
                
                # Deposit collective state to XRL bus
                if ws_connection is not None:
                    try:
                        deposit_payload = {
                            "event": "xrl.memory",
                            "payload": {
                                "op": "deposit",
                                "agent": "sleipnir-midhive",
                                "unit": {
                                    "source": "sleipnir-midhive",
                                    "ring": "ring_2_mid",
                                    "query": query,
                                    "state": cycle_res["mid_hive_state"],
                                    "consensus": output_content,
                                    "chord": chord_info,
                                    "timestamp": time.time()
                                }
                            }
                        }
                        asyncio.run_coroutine_threadsafe(
                            ws_connection.send(json.dumps(deposit_payload)),
                            ws_loop
                        )
                    except Exception as e:
                        print(f"[bridge] Note: XRL midhive deposit: {e}")
            else:
                # Execute pure Thalamic dispatch
                res = thalamus.dispatch(query, depth=depth, max_tokens=max_tokens)
                thalamus.unload()
                output_content = res["output"]
                meta = {
                    "winning_colony": res["routing"]["winning_colony"],
                    "confidence": res["routing"]["confidence"],
                    "alice_tier": res["alice_tier"],
                    "latency": res["total_latency_s"],
                    "tok_speed": res["tokens_per_sec"]
                }
                
                # Deposit to XRL WebSocket if connected
                if ws_connection is not None:
                    try:
                        deposit_payload = {
                            "event": "xrl.memory",
                            "payload": {
                                "op": "deposit",
                                "agent": "sleipnir-thalamus",
                                "unit": {
                                    "source": "sleipnir-swarm",
                                    "colony": res["routing"]["winning_colony"],
                                    "query": query,
                                    "response": res["output"],
                                    "timestamp": time.time()
                                }
                            }
                        }
                        asyncio.run_coroutine_threadsafe(
                            ws_connection.send(json.dumps(deposit_payload)),
                            ws_loop
                        )
                    except Exception as e:
                        print(f"[bridge] Note: XRL deposit: {e}")
            
            resp = {
                "id": f"sleipnir-{int(time.time())}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": "sleipnir-swarm",
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": output_content
                    },
                    "finish_reason": "stop"
                }],
                "thalamus_meta": meta
            }
            
            resp_bytes = json.dumps(resp).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp_bytes)))
            self.end_headers()
            self.wfile.write(resp_bytes)
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if self.path in ["/health", "/status"]:
            body = json.dumps({
                "status": "online",
                "architecture": "Sleipnir 3-6-9 Swarm",
                "thalamus_port": HTTP_PORT,
                "xrl_bus": WS_URI,
                "ws_connected": ws_connection is not None
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Quiet HTTP logging

async def xrl_ws_worker():
    global ws_connection
    while True:
        try:
            print(f"[bridge] Connecting to Open XRL WebSocket bus at {WS_URI}...", flush=True)
            async with websockets.connect(WS_URI) as ws:
                ws_connection = ws
                print(f"[bridge] Connected to Open XRL bus (:8403). Subscribing Sleipnir...", flush=True)
                
                # Send registration ping
                await ws.send(json.dumps({"event": "ping"}))
                
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    event = data.get("event")
                    
                    if event == "pong":
                        pass
                    elif event == "thalamus.query":
                        payload = data.get("payload", {})
                        q = payload.get("text", "")
                        if q:
                            res = thalamus.dispatch(q, depth=payload.get("depth", 0))
                            thalamus.unload()
                            await ws.send(json.dumps({
                                "event": "thalamus.response",
                                "payload": res
                            }))
                            
        except Exception as e:
            print(f"[bridge] XRL socket note: {e}. Reconnecting in 5s...", flush=True)
            ws_connection = None
            await asyncio.sleep(5)

def run_ws_loop():
    global ws_loop
    ws_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(ws_loop)
    ws_loop.run_until_complete(xrl_ws_worker())

def main():
    global thalamus
    print("="*75)
    print("🐎 SLEIPNIR CENTRAL THALAMUS & OPEN XRL BRIDGE")
    print(f"   HTTP Endpoint: http://127.0.0.1:{HTTP_PORT}")
    print(f"   XRL WebSocket: {WS_URI}")
    print("="*75)
    
    thalamus = CentralThalamus(device="cuda" if torch.cuda.is_available() else "cpu")
    
    # Start WebSocket worker in background thread
    t = threading.Thread(target=run_ws_loop, daemon=True, name="thalamus-ws")
    t.start()
    
    # Start HTTP server
    httpd = HTTPServer(("0.0.0.0", HTTP_PORT), ThalamusHTTPHandler)
    print(f"[bridge] Central Thalamus HTTP Router listening on port :{HTTP_PORT}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[bridge] Shutting down bridge.")

if __name__ == "__main__":
    import torch
    main()
