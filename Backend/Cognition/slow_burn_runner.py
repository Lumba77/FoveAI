#!/usr/bin/env python3
"""
foveai_embers: periodic POST to soul /internal/slow_burn/tick (no GPU).
"""
import logging
import os
import sys
import time

import httpx

logging.basicConfig(level=os.getenv("LOG_LEVEL", "WARNING"))
log = logging.getLogger("foveai_embers")

SOUL_URL = os.getenv("SOUL_URL", "http://foveai_soul:8402").rstrip("/")
INTERVAL = int(os.getenv("FoveAI_EMBERS_TICK_SEC", "300"))
SECRET = os.getenv("FoveAI_INTERNAL_SECRET", "").strip()
TIMEOUT = float(os.getenv("FoveAI_EMBERS_HTTP_TIMEOUT", "180"))


def main() -> None:
    print(
        f"[foveai_embers] SOUL_URL={SOUL_URL} interval={INTERVAL}s — further output: warnings/errors only",
        flush=True,
    )
    headers = {}
    if SECRET:
        headers["X-FoveAI-INTERNAL-KEY"] = SECRET

    while True:
        time.sleep(INTERVAL)
        try:
            with httpx.Client(timeout=TIMEOUT) as client:
                r = client.post(
                    f"{SOUL_URL}/internal/slow_burn/tick",
                    json={"force": False},
                    headers=headers,
                )
            try:
                body = r.json()
            except Exception:
                body = {"raw": r.text[:500]}
            if r.status_code >= 400:
                log.warning("tick HTTP %s: %s", r.status_code, body)
            else:
                log.debug("tick HTTP %s", r.status_code)
        except Exception as e:
            log.warning("tick failed: %s", e)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
