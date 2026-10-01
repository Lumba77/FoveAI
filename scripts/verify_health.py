#!/usr/bin/env python3
"""
scripts/verify_health.py — FoveAI Service Health Verification
==============================================================
Checks all FoveAI biological-cycle service health endpoints.

Services:
  8400 — Sight Nerve (Vision Stream) + Foveated Memory Proxy
  8401 — Hearing Nerve (STT Stream)
  8402 — Contemplation / XRLF Runtime (main API, returns `loaded` boolean)
  8403 — Speech Nerve (WebSocket, TCP-only check)
  8404 — Body / Motor Cortex (Animation Stream)
  8405 — Subconscious IN (Director)
  8406 — Subconscious OUT (State)
  1234 — LM Studio (optional, external)
  5177 — Multigate (optional, frontend dev server)

Usage:
  python scripts/verify_health.py
  python scripts/verify_health.py --port 8402
  python scripts/verify_health.py --json
"""

import argparse
import json
import socket
import sys
import time
import urllib.error
import urllib.request
from typing import Any

# ── Service registry ──────────────────────────────────────────────────────────

SERVICES: list[dict[str, Any]] = [
    {
        "name": "Sight Nerve",
        "port": 8400,
        "path": "/health",
        "type": "http",
        "critical": True,
    },
    {
        "name": "Hearing Nerve",
        "port": 8401,
        "path": "/health",
        "type": "http",
        "critical": False,
    },
    {
        "name": "XRLF Runtime",
        "port": 8402,
        "path": "/health",
        "type": "http",
        "critical": True,
        "check_loaded": True,
    },
    {
        "name": "Speech (WebSocket)",
        "port": 8403,
        "path": "",
        "type": "tcp",
        "critical": False,
    },
    {
        "name": "Body / Motor Cortex",
        "port": 8404,
        "path": "/health",
        "type": "http",
        "critical": False,
    },
    {
        "name": "Subconscious IN",
        "port": 8405,
        "path": "/health",
        "type": "http",
        "critical": False,
    },
    {
        "name": "Subconscious OUT",
        "port": 8406,
        "path": "/health",
        "type": "http",
        "critical": False,
    },
    {
        "name": "Chat Relay",
        "port": 8407,
        "path": "/health",
        "type": "http",
        "critical": False,
    },
    {
        "name": "LM Studio",
        "port": 1234,
        "path": "/v1/models",
        "type": "http",
        "critical": False,
        "optional": True,
    },
    {
        "name": "Multigate",
        "port": 5177,
        "path": "/",
        "type": "http",
        "critical": False,
        "optional": True,
    },
]


def check_http(
    port: int, path: str, timeout: float = 3.0
) -> tuple[bool, str, dict[str, Any] | None]:
    """Check an HTTP health endpoint. Returns (ok, message, parsed_json)."""
    url: str = f"http://127.0.0.1:{port}{path}"
    try:
        req: urllib.request.Request = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body: str = resp.read().decode("utf-8", errors="replace")[:500]
            try:
                parsed: dict[str, Any] = json.loads(body)
                return True, f"HTTP {resp.status}", parsed
            except json.JSONDecodeError:
                return True, f"HTTP {resp.status} (non-JSON)", None
    except urllib.error.URLError as e:
        return False, f"Connection refused: {e.reason}", None
    except Exception as e:
        return False, f"Error: {e}", None


def check_tcp(port: int, timeout: float = 3.0) -> tuple[bool, str]:
    """Check if a TCP port is listening (for WebSocket-only services)."""
    try:
        sock: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result: int = sock.connect_ex(("127.0.0.1", port))
        sock.close()
        if result == 0:
            return True, "TCP port listening"
        return False, f"TCP connection failed (errno {result})"
    except Exception as e:
        return False, f"Error: {e}"


def verify_service(svc: dict[str, Any]) -> dict[str, Any]:
    """Run a health check on a single service and return a result dict."""
    name: str = svc["name"]
    port: int = svc["port"]
    svc_type: str = svc["type"]
    t0: float = time.perf_counter()

    if svc_type == "tcp":
        ok, msg = check_tcp(port)
        result: dict[str, Any] = {
            "name": name,
            "port": port,
            "type": "tcp",
            "ok": ok,
            "message": msg,
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
            "critical": svc.get("critical", False),
            "optional": svc.get("optional", False),
        }
    else:
        ok, msg, parsed = check_http(port, svc["path"])
        result = {
            "name": name,
            "port": port,
            "type": "http",
            "ok": ok,
            "message": msg,
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
            "critical": svc.get("critical", False),
            "optional": svc.get("optional", False),
        }
        # Check `loaded` field for XRLF Runtime
        if ok and svc.get("check_loaded") and parsed:
            result["loaded"] = parsed.get("loaded", False)
            if not parsed.get("loaded"):
                result["ok"] = False
                result["message"] += " (loaded=False)"

    return result


def print_report(results: list[dict[str, Any]]) -> bool:
    """Print a human-readable health report. Returns True if all critical services are healthy."""
    print("\n" + "=" * 60)
    print("  FoveAI Service Health Check")
    print("=" * 60)
    print(f"  {'Service':<26} {'Port':>6} {'Status':>8} {'Detail':<30}")
    print("  " + "-" * 56)

    all_critical_ok: bool = True
    for r in results:
        status: str = "ONLINE" if r["ok"] else "OFFLINE"
        marker: str = "OK" if r["ok"] else "FAIL"
        opt_tag: str = " (optional)" if r.get("optional") else ""
        crit_tag: str = " [CRITICAL]" if r.get("critical") and not r["ok"] else ""
        loaded_tag: str = ""
        if "loaded" in r:
            loaded_tag = f" loaded={r['loaded']}"

        print(
            f"  {r['name']:<26} {r['port']:>6} {marker:>8} {r['message'][:28]}{loaded_tag}{opt_tag}{crit_tag}"
        )

        if r.get("critical") and not r["ok"]:
            all_critical_ok = False

    print("  " + "-" * 56)
    if all_critical_ok:
        print("  All critical services are ONLINE")
    else:
        print("  Some critical services are OFFLINE")
    print("=" * 60)

    return all_critical_ok


def main() -> int:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="FoveAI Service Health Verification"
    )
    parser.add_argument(
        "--port", type=int, default=None, help="Check only a specific port"
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--timeout", type=float, default=3.0, help="HTTP timeout in seconds"
    )
    args: argparse.Namespace = parser.parse_args()

    services: list[dict[str, Any]] = SERVICES
    if args.port:
        services = [s for s in SERVICES if s["port"] == args.port]
        if not services:
            print(f"No service registered on port {args.port}")
            return 1

    results: list[dict[str, Any]] = []
    for svc in services:
        svc_copy: dict[str, Any] = svc.copy()
        if svc_copy["type"] == "http":
            svc_copy["path"] = svc_copy["path"]
        results.append(verify_service(svc_copy))

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        all_ok: bool = print_report(results)
        if not all_ok:
            print("\n  To start services:")
            print("    python Backend/interactive_cycle.py   # ports 8400-8406")
            print(
                "    python api/server.py --port 8402      # XRLF Runtime (if not using interactive_cycle)"
            )
            print("    node foveated-memory/server.js         # Foveated Memory Proxy")

    return (
        0
        if all(r["ok"] or r.get("optional") for r in results if r.get("critical"))
        else 1
    )


if __name__ == "__main__":
    sys.exit(main())
