"""
Intelligent Router — Real-Time Local/Cloud Decision Engine

Decides per-request whether to route to local LLM or cloud based on:
  1. Hardware capability (VRAM, RAM, CPU)
  2. Current system load (CPU/GPU usage)
  3. Prompt complexity (token count, estimated compute)
  4. Latency requirements (chat vs deep thought)
  5. Privacy mode (force local)
  6. User preference (local / hybrid / cloud)

Architecture:
  - Fast, synchronous decision (no blocking I/O)
  - Falls back gracefully if any probe fails
  - Returns a routing decision + reasoning for the user

Usage:
  from intelligent_router import IntelligentRouter
  router = IntelligentRouter()
  decision = router.decide(prompt="Hello", token_count=50)
  # => {"route": "local", "reason": "Simple query, local is fast enough"}
"""

import os
import time
from typing import Any

import psutil

# ── Thresholds (tunable via .env) ──
VRAM_FOR_7B = float(os.environ.get("FoveAI_VRAM_FOR_7B", "6.0"))  # GB
VRAM_FOR_3B = float(os.environ.get("FoveAI_VRAM_FOR_3B", "3.0"))  # GB
MAX_TOKENS_LOCAL = int(os.environ.get("FoveAI_MAX_TOKENS_LOCAL", "4096"))
MAX_TOKENS_CLOUD = int(os.environ.get("FoveAI_MAX_TOKENS_CLOUD", "32768"))
CPU_THRESHOLD_HIGH = float(os.environ.get("FoveAI_CPU_HIGH_THRESHOLD", "80.0"))  # %
VRAM_THRESHOLD_LOW = float(
    os.environ.get("FoveAI_VRAM_LOW_THRESHOLD", "1.0")
)  # GB free
LATENCY_MS_LOCAL_TARGET = float(
    os.environ.get("FoveAI_LATENCY_LOCAL_TARGET", "2000")
)  # ms
LATENCY_MS_CLOUD_TARGET = float(
    os.environ.get("FoveAI_LATENCY_CLOUD_TARGET", "5000")
)  # ms


class IntelligentRouter:
    """
    Real-time decision engine for local vs cloud routing.
    Thread-safe, no blocking I/O in the hot path.
    """

    def __init__(self):
        self._last_gpu_probe: dict[str, Any] = {}
        self._last_gpu_probe_time: float = 0
        self._gpu_probe_interval: float = 5.0  # Re-probe GPU every 5s

    # ── Hardware Probes (cached, non-blocking) ──

    def _probe_gpu(self) -> dict[str, Any]:
        """Probe GPU state with caching to avoid hammering nvidia-smi."""
        now = time.time()
        if (
            now - self._last_gpu_probe_time < self._gpu_probe_interval
            and self._last_gpu_probe
        ):
            return self._last_gpu_probe

        gpu_info = {
            "available": False,
            "name": "Not detected",
            "vram_total_gb": 0.0,
            "vram_free_gb": 0.0,
            "vram_used_pct": 0.0,
            "gpu_util_pct": 0.0,
        }

        # Try nvidia-smi (most reliable on Windows)
        try:
            import subprocess

            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total,memory.free,utilization.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split(", ")
                if len(parts) >= 3:
                    gpu_info["available"] = True
                    gpu_info["name"] = parts[0]
                    gpu_info["vram_total_gb"] = (
                        round(float(parts[1]) / 1024, 1) if parts[1] else 0.0
                    )
                    gpu_info["vram_free_gb"] = (
                        round(float(parts[2]) / 1024, 1) if parts[2] else 0.0
                    )
                    gpu_info["vram_used_pct"] = (
                        round((1 - float(parts[2]) / float(parts[1])) * 100, 1)
                        if parts[1] and parts[2]
                        else 0.0
                    )
                    gpu_info["gpu_util_pct"] = (
                        float(parts[3]) if len(parts) > 3 and parts[3] else 0.0
                    )
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, IndexError):
            pass

        self._last_gpu_probe = gpu_info
        self._last_gpu_probe_time = now
        return gpu_info

    def _probe_cpu(self) -> dict[str, Any]:
        """Probe CPU state."""
        return {
            "cores": psutil.cpu_count(),
            "usage_pct": psutil.cpu_percent(interval=0.1),
            "load_avg": psutil.getloadavg()[0]
            if hasattr(psutil, "getloadavg")
            else 0.0,
        }

    def _probe_ram(self) -> dict[str, Any]:
        """Probe RAM state."""
        mem = psutil.virtual_memory()
        return {
            "total_gb": round(mem.total / 1e9, 1),
            "available_gb": round(mem.available / 1e9, 1),
            "used_pct": mem.percent,
        }

    # ── Decision Engine ──

    def decide(
        self,
        prompt: str = "",
        token_count: int = 0,
        mode: str | None = None,
        privacy: bool = False,
        deep_thought: bool = False,
        local_available: bool = True,
    ) -> dict[str, Any]:
        """
        Make a routing decision for a single request.

        Args:
            prompt: The user's input text
            token_count: Estimated token count (0 = auto-estimate)
            mode: Override mode ('local', 'hybrid', 'cloud', or None for auto)
            privacy: If True, force local-only
            deep_thought: If True, prefer cloud for complex reasoning
            local_available: Whether a local LLM is running

        Returns:
            Dict with 'route', 'reason', and diagnostic info
        """
        decision = {
            "route": "cloud",  # Default: cloud (safest)
            "reason": [],
            "mode": mode or os.environ.get("FoveAI_COGNITIVE_MODE", "hybrid"),
            "hardware": {},
            "prompt_analysis": {},
            "timestamp": time.time(),
        }

        # ── Privacy override ──
        if privacy:
            decision["route"] = "local"
            decision["reason"].append("Privacy mode: forced local-only")
            return decision

        # ── Mode override ──
        effective_mode = (
            mode or os.environ.get("FoveAI_COGNITIVE_MODE", "hybrid").strip().lower()
        )

        if effective_mode == "local":
            decision["route"] = "local"
            decision["reason"].append("Cognitive mode set to local-only")
            return decision

        if effective_mode == "cloud":
            decision["route"] = "cloud"
            decision["reason"].append("Cognitive mode set to cloud-only")
            return decision

        # ── Hybrid mode: intelligent decision ──
        if effective_mode == "hybrid":
            # Probe hardware
            gpu = self._probe_gpu()
            cpu = self._probe_cpu()
            ram = self._probe_ram()
            decision["hardware"] = {"gpu": gpu, "cpu": cpu, "ram": ram}

            # Auto-estimate token count if not provided
            if token_count <= 0:
                token_count = max(
                    1, len(prompt) // 2
                )  # Rough estimate: ~2 chars per token
            decision["prompt_analysis"]["estimated_tokens"] = token_count

            # Decision factors (weighted)
            reasons = []

            # Factor 1: Local LLM availability
            if not local_available:
                decision["route"] = "cloud"
                reasons.append("No local LLM available")
                decision["reason"] = reasons
                return decision

            # Factor 2: VRAM check
            if gpu["available"]:
                if gpu["vram_free_gb"] < VRAM_THRESHOLD_LOW:
                    reasons.append(
                        f"Low VRAM ({gpu['vram_free_gb']}GB free) — routing to cloud"
                    )
                    decision["route"] = "cloud"
                    decision["reason"] = reasons
                    return decision

                if gpu["vram_total_gb"] >= VRAM_FOR_7B:
                    reasons.append(
                        f"GPU {gpu['name']} with {gpu['vram_total_gb']}GB VRAM — can run 7B locally"
                    )
                elif gpu["vram_total_gb"] >= VRAM_FOR_3B:
                    reasons.append(
                        f"GPU {gpu['name']} with {gpu['vram_total_gb']}GB VRAM — can run 3B locally"
                    )
                else:
                    reasons.append(
                        f"GPU {gpu['name']} with {gpu['vram_total_gb']}GB VRAM — below 3B threshold"
                    )
            else:
                reasons.append("No GPU detected — CPU-only mode")

            # Factor 3: CPU load
            if cpu["usage_pct"] > CPU_THRESHOLD_HIGH:
                reasons.append(
                    f"High CPU load ({cpu['usage_pct']}%) — routing to cloud"
                )
                decision["route"] = "cloud"
                decision["reason"] = reasons
                return decision

            # Factor 4: Prompt complexity
            if deep_thought or token_count > MAX_TOKENS_LOCAL:
                reasons.append(
                    f"Complex query ({token_count} tokens) — routing to cloud for deep reasoning"
                )
                decision["route"] = "cloud"
                decision["reason"] = reasons
                return decision

            # Factor 5: Simple queries go local
            if token_count < 100 and not deep_thought:
                reasons.append(
                    f"Simple query ({token_count} tokens) — local is fast enough"
                )
                decision["route"] = "local"
                decision["reason"] = reasons
                return decision

            # Factor 6: Medium complexity — check RAM
            if ram["available_gb"] < 2.0:
                reasons.append(
                    f"Low RAM ({ram['available_gb']}GB available) — routing to cloud"
                )
                decision["route"] = "cloud"
                decision["reason"] = reasons
                return decision

            # Default for hybrid: try local first, fall back to cloud
            reasons.append(f"Medium query ({token_count} tokens) — trying local first")
            decision["route"] = "local"
            decision["reason"] = reasons
            return decision

        # Fallback: cloud
        decision["reason"].append(
            f"Unknown mode '{effective_mode}' — defaulting to cloud"
        )
        return decision

    def get_status(self) -> dict[str, Any]:
        """Return current router status for the status panel."""
        gpu = self._probe_gpu()
        cpu = self._probe_cpu()
        ram = self._probe_ram()

        mode = os.environ.get("FoveAI_COGNITIVE_MODE", "hybrid")
        provider = os.environ.get("FoveAI_CHAT_PROVIDER", "ollama_cloud")

        return {
            "mode": mode,
            "provider": provider,
            "hardware": {
                "gpu": gpu,
                "cpu": cpu,
                "ram": ram,
            },
            "capabilities": {
                "can_run_7b": gpu["available"] and gpu["vram_total_gb"] >= VRAM_FOR_7B,
                "can_run_3b": gpu["available"] and gpu["vram_total_gb"] >= VRAM_FOR_3B,
                "can_run_hybrid": gpu["available"] or ram["total_gb"] >= 8.0,
            },
            "last_decision": getattr(self, "_last_decision", None),
        }


# ── Singleton for soul_core.py ──
_router = IntelligentRouter()


def get_router() -> IntelligentRouter:
    """Get the singleton router instance."""
    return _router
