"""
SystemProbe — FoveAI Hardware Detection & Onboarding Flow

Auto-detects system capabilities, tests local LLM performance, and recommends
the best configuration (local / cloud / hybrid). Never leaves the user in the dark.

Architecture:
  - Phase 1: Detect GPU, VRAM, RAM, CPU
  - Phase 2: Test local LLM (Unsloth / LM Studio / Ollama)
  - Phase 3: Recommend mode based on hardware + test results
  - Phase 4: Auto-configure .env and start services
  - Phase 5: Return status report for the frontend onboarding panel

Usage:
  from system_probe import SystemProbe
  probe = SystemProbe()
  report = await probe.run_full_diagnostic()
"""

import os
import time
import json
import psutil
import asyncio
import subprocess
from typing import Dict, Any, Optional, List

# ── Constants ──
VRAM_THRESHOLD_LOCAL_7B = 6.0  # GB — need at least 6GB VRAM for a 7B model
VRAM_THRESHOLD_LOCAL_3B = 3.0  # GB — need at least 3GB VRAM for a 3B model
RAM_THRESHOLD_LOCAL = 8.0      # GB — need at least 8GB system RAM
CPU_CORES_THRESHOLD = 4        # Minimum CPU cores for local inference

LOCAL_LLM_PORTS = {
    "unsloth": 8888,
    "lmstudio": 7272,
    "ollama": 11434,
}

LOCAL_LLM_HEALTH_URLS = {
    "unsloth": "http://127.0.0.1:8888/v1/models",
    "lmstudio": "http://127.0.0.1:7272/v1/models",
    "ollama": "http://127.0.0.1:11434/api/tags",
}


class SystemProbe:
    """Probes system hardware, tests LLM backends, and recommends configuration."""

    def __init__(self):
        self.report: Dict[str, Any] = {
            "hardware": {},
            "llm_backends": {},
            "recommendation": {},
            "status": "scanning",
            "message": "Probing system capabilities...",
            "steps": [],
        }

    # ── Phase 1: Hardware Detection ──

    def _detect_cpu(self) -> Dict[str, Any]:
        """Detect CPU capabilities."""
        cpu_info = {
            "cores": psutil.cpu_count(logical=False) or psutil.cpu_count(),
            "logical_cores": psutil.cpu_count(),
            "usage_percent": psutil.cpu_percent(interval=0.5),
            "architecture": "x86_64",
            "sufficient": False,
        }
        cpu_info["sufficient"] = cpu_info["cores"] >= CPU_CORES_THRESHOLD
        return cpu_info

    def _detect_ram(self) -> Dict[str, Any]:
        """Detect system RAM."""
        mem = psutil.virtual_memory()
        ram_info = {
            "total_gb": round(mem.total / 1e9, 1),
            "available_gb": round(mem.available / 1e9, 1),
            "usage_percent": mem.percent,
            "sufficient": (mem.total / 1e9) >= RAM_THRESHOLD_LOCAL,
        }
        return ram_info

    def _detect_gpu(self) -> Dict[str, Any]:
        """Detect GPU capabilities using multiple methods."""
        gpu_info = {
            "available": False,
            "name": "Not detected",
            "vram_gb": 0.0,
            "vram_free_gb": 0.0,
            "cuda_available": False,
            "cuda_version": "",
            "driver_version": "",
            "sufficient_for_7b": False,
            "sufficient_for_3b": False,
        }

        # Method 1: NVIDIA SMI (most reliable on Windows)
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total,memory.free,driver_version",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split(", ")
                if len(parts) >= 3:
                    gpu_info["available"] = True
                    gpu_info["name"] = parts[0]
                    gpu_info["vram_gb"] = round(float(parts[1]) / 1024, 1) if parts[1] else 0.0
                    gpu_info["vram_free_gb"] = round(float(parts[2]) / 1024, 1) if parts[2] else 0.0
                    gpu_info["driver_version"] = parts[3] if len(parts) > 3 else ""
                    gpu_info["sufficient_for_7b"] = gpu_info["vram_gb"] >= VRAM_THRESHOLD_LOCAL_7B
                    gpu_info["sufficient_for_3b"] = gpu_info["vram_gb"] >= VRAM_THRESHOLD_LOCAL_3B
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, IndexError):
            pass

        # Method 2: PyTorch CUDA detection
        if not gpu_info["available"]:
            try:
                import torch
                if torch.cuda.is_available():
                    gpu_info["available"] = True
                    gpu_info["name"] = torch.cuda.get_device_name(0)
                    gpu_info["vram_gb"] = round(torch.cuda.get_device_properties(0).total_memory / 1e9, 1)
                    gpu_info["cuda_available"] = True
                    gpu_info["cuda_version"] = torch.version.cuda or ""
                    gpu_info["sufficient_for_7b"] = gpu_info["vram_gb"] >= VRAM_THRESHOLD_LOCAL_7B
                    gpu_info["sufficient_for_3b"] = gpu_info["vram_gb"] >= VRAM_THRESHOLD_LOCAL_3B
            except ImportError:
                pass

        # Method 3: Windows WMIC (fallback)
        if not gpu_info["available"]:
            try:
                result = subprocess.run(
                    ["wmic", "path", "win32_VideoController", "get", "name,adapterram"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0 and result.stdout.strip():
                    lines = [l.strip() for l in result.stdout.split("\n") if l.strip()]
                    if len(lines) > 1:
                        # Parse WMIC output (tab-separated)
                        for line in lines[1:]:
                            parts = line.split()
                            if len(parts) >= 1:
                                gpu_info["available"] = True
                                gpu_info["name"] = " ".join(parts[:-1]) if len(parts) > 1 else parts[0]
                                if len(parts) > 1 and parts[-1].isdigit():
                                    vram_bytes = int(parts[-1])
                                    gpu_info["vram_gb"] = round(vram_bytes / 1e9, 1)
                                    gpu_info["sufficient_for_7b"] = gpu_info["vram_gb"] >= VRAM_THRESHOLD_LOCAL_7B
                                    gpu_info["sufficient_for_3b"] = gpu_info["vram_gb"] >= VRAM_THRESHOLD_LOCAL_3B
                                break
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

        return gpu_info

    def _detect_disk(self) -> Dict[str, Any]:
        """Detect disk space."""
        disk = psutil.disk_usage('/')
        return {
            "total_gb": round(disk.total / 1e9, 1),
            "free_gb": round(disk.free / 1e9, 1),
            "sufficient": disk.free / 1e9 > 10.0,  # Need at least 10GB free
        }

    # ── Phase 2: LLM Backend Detection ──

    async def _check_llm_backend(self, name: str, port: int, health_url: str) -> Dict[str, Any]:
        """Check if an LLM backend is running and responsive."""
        import httpx
        result = {
            "name": name,
            "port": port,
            "running": False,
            "models": [],
            "latency_ms": 0,
            "error": None,
        }

        try:
            start = time.time()
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(health_url)
                latency = (time.time() - start) * 1000
                result["latency_ms"] = round(latency, 1)

                if resp.status_code == 200:
                    result["running"] = True
                    data = resp.json()
                    # Parse models from various API formats
                    if "data" in data:
                        result["models"] = [m.get("id", str(m)) for m in data["data"]]
                    elif "models" in data:
                        result["models"] = [m.get("name", str(m)) for m in data["models"]]
        except Exception as e:
            result["error"] = str(e)

        return result

    async def _detect_llm_backends(self) -> Dict[str, Any]:
        """Detect all available LLM backends."""
        backends = {}
        tasks = []
        for name, port in LOCAL_LLM_PORTS.items():
            tasks.append(self._check_llm_backend(name, port, LOCAL_LLM_HEALTH_URLS[name]))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, name in enumerate(LOCAL_LLM_PORTS.keys()):
            if isinstance(results[i], Exception):
                backends[name] = {
                    "name": name,
                    "port": LOCAL_LLM_PORTS[name],
                    "running": False,
                    "models": [],
                    "latency_ms": 0,
                    "error": str(results[i]),
                }
            else:
                backends[name] = results[i]

        return backends

    # ── Phase 3: Recommendation Engine ──

    def _recommend_mode(self, hardware: Dict[str, Any], llm_backends: Dict[str, Any]) -> Dict[str, Any]:
        """Recommend the best configuration based on hardware and LLM availability."""
        gpu = hardware.get("gpu", {})
        ram = hardware.get("ram", {})
        cpu = hardware.get("cpu", {})

        # Check if any LLM is already running
        any_llm_running = any(b.get("running") for b in llm_backends.values())

        recommendation = {
            "mode": "cloud",  # Default: cloud (safest)
            "provider": "openai",
            "model": "gpt-4o-mini",
            "local_model": "",
            "can_run_local": False,
            "can_run_hybrid": False,
            "reasoning": [],
            "steps": [],
        }

        # Check if we can run local models
        can_run_3b = gpu.get("sufficient_for_3b", False) and ram.get("sufficient", False)
        can_run_7b = gpu.get("sufficient_for_7b", False) and ram.get("sufficient", False)

        if any_llm_running:
            # An LLM is already running — use it
            for name, backend in llm_backends.items():
                if backend.get("running"):
                    recommendation["mode"] = "local"
                    recommendation["provider"] = name
                    recommendation["local_model"] = backend.get("models", [None])[0] or "default"
                    recommendation["can_run_local"] = True
                    recommendation["reasoning"].append(
                        f"{backend['name']} detected on port {backend['port']} with {len(backend.get('models', []))} model(s)"
                    )
                    break
        elif can_run_7b:
            recommendation["mode"] = "hybrid"
            recommendation["provider"] = "unsloth"
            recommendation["local_model"] = "7B GGUF"
            recommendation["can_run_local"] = True
            recommendation["can_run_hybrid"] = True
            recommendation["reasoning"].append(
                f"GPU {gpu['name']} with {gpu['vram_gb']}GB VRAM can run 7B models locally"
            )
            recommendation["reasoning"].append(
                "Hybrid mode: small local model for quick responses, cloud for complex reasoning"
            )
        elif can_run_3b:
            recommendation["mode"] = "hybrid"
            recommendation["provider"] = "unsloth"
            recommendation["local_model"] = "3B GGUF"
            recommendation["can_run_local"] = True
            recommendation["can_run_hybrid"] = True
            recommendation["reasoning"].append(
                f"GPU {gpu['name']} with {gpu['vram_gb']}GB VRAM can run 3B models locally"
            )
            recommendation["reasoning"].append(
                "3B model for quick chat, cloud for complex tasks"
            )
        elif gpu.get("available", False):
            recommendation["mode"] = "cloud"
            recommendation["reasoning"].append(
                f"GPU {gpu['name']} with {gpu['vram_gb']}GB VRAM is below the 3B model threshold ({VRAM_THRESHOLD_LOCAL_3B}GB)"
            )
            recommendation["reasoning"].append(
                "Cloud mode recommended — your GPU can still accelerate other tasks (STT, TTS, embeddings)"
            )
        else:
            recommendation["mode"] = "cloud"
            recommendation["reasoning"].append(
                "No compatible GPU detected — cloud mode recommended for best experience"
            )

        # Add steps for the user
        if recommendation["mode"] == "cloud":
            recommendation["steps"].append("Configure cloud API keys in Settings > API Keys")
            recommendation["steps"].append("Select your preferred cloud provider (OpenAI, Anthropic, etc.)")
        elif recommendation["mode"] == "hybrid":
            recommendation["steps"].append("Download a small local model (3B-7B GGUF) for quick responses")
            recommendation["steps"].append("Configure cloud API keys for complex reasoning tasks")
            recommendation["steps"].append("The system will automatically route between local and cloud")
        elif recommendation["mode"] == "local":
            recommendation["steps"].append("Your local LLM is ready to use")
            recommendation["steps"].append("Configure additional models in Model Hub")

        return recommendation

    # ── Phase 4: Auto-Configure ──

    def _auto_configure(self, recommendation: Dict[str, Any]) -> Dict[str, Any]:
        """Auto-configure .env based on recommendation."""
        config_changes = {}
        mode = recommendation.get("mode", "cloud")

        if mode == "local":
            config_changes["FoveAI_CHAT_PROVIDER"] = recommendation.get("provider", "unsloth")
            config_changes["FoveAI_COGNITIVE_MODE"] = "local"
        elif mode == "hybrid":
            config_changes["FoveAI_CHAT_PROVIDER"] = recommendation.get("provider", "unsloth")
            config_changes["FoveAI_COGNITIVE_MODE"] = "hybrid"
            config_changes["FoveAI_CLOUD_SPLICE_PERCENT"] = "20"
        else:  # cloud
            config_changes["FoveAI_CHAT_PROVIDER"] = "ollama_cloud"
            config_changes["FoveAI_COGNITIVE_MODE"] = "cloud"

        # Persist to .env
        env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                for k, v in config_changes.items():
                    found = False
                    for i, line in enumerate(lines):
                        if line.startswith(f"{k}="):
                            lines[i] = f"{k}={v}\n"
                            found = True
                            break
                    if not found:
                        lines.append(f"{k}={v}\n")

                with open(env_path, "w", encoding="utf-8") as f:
                    f.writelines(lines)

                config_changes["_persisted"] = True
            except Exception as e:
                config_changes["_persist_error"] = str(e)

        return config_changes

    # ── Main Diagnostic Flow ──

    async def run_full_diagnostic(self) -> Dict[str, Any]:
        """Run the full system diagnostic and return a comprehensive report."""
        self.report["status"] = "scanning"
        self.report["message"] = "Detecting hardware capabilities..."
        self.report["steps"].append({"phase": "hardware", "status": "running", "message": "Detecting CPU, RAM, GPU..."})

        # Phase 1: Hardware
        self.report["hardware"] = {
            "cpu": self._detect_cpu(),
            "ram": self._detect_ram(),
            "gpu": self._detect_gpu(),
            "disk": self._detect_disk(),
        }
        self.report["steps"].append({"phase": "hardware", "status": "done", "message": "Hardware detection complete"})

        # Phase 2: LLM Backends
        self.report["message"] = "Scanning for LLM backends..."
        self.report["steps"].append({"phase": "llm", "status": "running", "message": "Checking Unsloth, LM Studio, Ollama..."})
        self.report["llm_backends"] = await self._detect_llm_backends()
        self.report["steps"].append({"phase": "llm", "status": "done", "message": "LLM backend scan complete"})

        # Phase 3: Recommendation
        self.report["message"] = "Analyzing results and generating recommendation..."
        self.report["steps"].append({"phase": "recommend", "status": "running", "message": "Generating configuration recommendation..."})
        self.report["recommendation"] = self._recommend_mode(self.report["hardware"], self.report["llm_backends"])
        self.report["steps"].append({"phase": "recommend", "status": "done", "message": "Recommendation ready"})

        # Phase 4: Auto-Configure
        self.report["message"] = "Applying recommended configuration..."
        self.report["steps"].append({"phase": "config", "status": "running", "message": "Writing configuration..."})
        self.report["config_applied"] = self._auto_configure(self.report["recommendation"])
        self.report["steps"].append({"phase": "config", "status": "done", "message": "Configuration applied"})

        # Final status
        self.report["status"] = "ready"
        self.report["message"] = self._build_summary_message()

        return self.report

    def _build_summary_message(self) -> str:
        """Build a human-readable summary message."""
        mode = self.report.get("recommendation", {}).get("mode", "cloud")
        gpu = self.report.get("hardware", {}).get("gpu", {})
        ram = self.report.get("hardware", {}).get("ram", {})

        gpu_str = f"{gpu.get('name', 'Unknown')} ({gpu.get('vram_gb', 0)}GB VRAM)" if gpu.get("available") else "No GPU detected"
        ram_str = f"{ram.get('total_gb', 0)}GB RAM"

        if mode == "local":
            return f"✅ Local mode ready — {gpu_str}, {ram_str}. Using your local LLM."
        elif mode == "hybrid":
            return f"🔀 Hybrid mode configured — {gpu_str}, {ram_str}. Small local model + cloud for complex tasks."
        else:
            return f"☁️ Cloud mode recommended — {gpu_str}, {ram_str}. Configure API keys for best experience."


# ── Convenience function for soul_core.py ──

async def run_system_probe() -> Dict[str, Any]:
    """Run a full system probe and return the report."""
    probe = SystemProbe()
    return await probe.run_full_diagnostic()


def get_system_summary() -> Dict[str, Any]:
    """Get a quick system summary without running the full probe."""
    probe = SystemProbe()
    return {
        "hardware": {
            "cpu": probe._detect_cpu(),
            "ram": probe._detect_ram(),
            "gpu": probe._detect_gpu(),
            "disk": probe._detect_disk(),
        },
        "status": "summary",
        "message": "Quick system summary (run full probe for LLM backend detection)",
    }