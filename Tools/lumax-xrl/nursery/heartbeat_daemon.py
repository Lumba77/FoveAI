import os
import time
import json
import logging
import asyncio
import httpx
from typing import Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("foveai.heartbeat")

# Ring Nodes ports map
SWARM_RING = {
    8105: "CODER",
    8106: "UI",
    8107: "VOICE",
    8108: "MEMORY",
    8109: "STATE",
    8110: "PLANNER"
}

STARDUST_ENDPOINT = "http://127.0.0.1:8109/update_resonance"
SOVEREIGN_ENDPOINT = "http://127.0.0.1:8000/api/telemetry/heartbeat"

class HeartbeatDaemon:
    def __init__(self, check_interval_seconds: float = 5.0):
        self.check_interval = check_interval_seconds
        self.client = httpx.AsyncClient(timeout=2.0)
        self.resonance_history: List[float] = []

    async def measure_node_latency(self, port: int) -> Optional[float]:
        """Measure roundtrip latency of a single node's health/status API."""
        url = f"http://127.0.0.1:{port}/health" if port != 8109 else "http://127.0.0.1:8109/health"
        if port == 8105: # Forge Nursery status
            url = "http://127.0.0.1:8105/api/status"
        
        # Fallback endpoints depending on service type
        try:
            start = time.perf_counter()
            response = await self.client.get(url)
            if response.status_code == 200:
                return time.perf_counter() - start
        except Exception:
            # Fallback to standard status endpoint for typical llama-server configurations
            try:
                start = time.perf_counter()
                response = await self.client.get(f"http://127.0.0.1:{port}/slots")
                if response.status_code == 200:
                    return time.perf_counter() - start
            except Exception:
                pass
        return None

    async def fetch_speculative_acceptance(self, port: int) -> Optional[float]:
        """Fetch speculative draft model token acceptance rate from llama-server metrics."""
        try:
            response = await self.client.get(f"http://127.0.0.1:{port}/metrics")
            if response.status_code == 200:
                # Simple prometheus metric parsing for draft model acceptance rate:
                # e.g., "llamacpp:speculative_acceptance_rate 0.85" or similar patterns
                for line in response.text.split("\n"):
                    if "speculative_acceptance_rate" in line or "speculative_tokens_accepted" in line:
                        parts = line.strip().split()
                        if len(parts) >= 2:
                            return float(parts[1])
        except Exception:
            pass
        return None

    async def run_loop(self):
        logger.info("🛸 Heartbeat Daemon initiated. Measuring the temporal continuum pulse...")
        while True:
            try:
                latencies = {}
                acceptance_rates = {}
                active_nodes = 0

                for port, name in SWARM_RING.items():
                    latency = await self.measure_node_latency(port)
                    if latency is not None:
                        latencies[name] = latency
                        active_nodes += 1
                        
                        # Fetch speculative stats for active inference endpoints
                        acc = await self.fetch_speculative_acceptance(port)
                        if acc is not None:
                            acceptance_rates[name] = acc

                # If we have loop entries, calculate structural resonance
                if active_nodes > 0:
                    avg_latency = sum(latencies.values()) / len(latencies)
                    # Perfect resonance is low latency + high speculative acceptance rate (MTP alignment)
                    avg_acceptance = sum(acceptance_rates.values()) / len(acceptance_rates) if acceptance_rates else 0.75
                    
                    # Core Resonance Metric: high acceptance rate + small loop transit latency
                    # Warped scaling: higher is better (max target ~1.0)
                    resonance = (avg_acceptance) / (1.0 + avg_latency)
                    resonance = min(max(resonance, 0.0), 1.0)
                    
                    logger.info(f"✨ [TEMPORAL HEARTBEAT] Active Nodes: {active_nodes}/6 | Avg Latency: {avg_latency:.4f}s | Speculative Hit Rate: {avg_acceptance:.2%}")
                    logger.info(f"🌀 [INDRA'S NET RESONANCE] {resonance:.4f} Pulse Frequency")

                    # Pipe resonance metric to Stardust and Sovereign Core
                    await self._send_telemetry(resonance, latencies, acceptance_rates)
                else:
                    logger.warning("⚠️ Swarm Ring disconnected. Temporal pulse resting at 0.0.")

            except Exception as e:
                logger.error(f"Error in telemetry loop: {e}")

            await asyncio.sleep(self.check_interval)

    async def _send_telemetry(self, resonance: float, latencies: Dict[str, float], acceptance: Dict[str, float]):
        payload = {
            "resonance": resonance,
            "timestamp": time.time(),
            "latencies": latencies,
            "acceptance_rates": acceptance
        }
        # Update Stardust vector warping threshold
        try:
            await self.client.post(STARDUST_ENDPOINT, json=payload)
        except Exception:
            pass

        # Update Sovereign Core main agent dashboard info
        try:
            await self.client.post(SOVEREIGN_ENDPOINT, json=payload)
        except Exception:
            pass

    async def shutdown(self):
        await self.client.aclose()

if __name__ == "__main__":
    daemon = HeartbeatDaemon()
    try:
        asyncio.run(daemon.run_loop())
    except KeyboardInterrupt:
        logger.info("Heartbeat grounded safely.")
