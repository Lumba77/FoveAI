"""
runtime/memory_planner.py — Dynamic VRAM/RAM Tiling Planner
=============================================================

Treats VRAM and RAM like a tiling window manager manages screen space.
Models are "windows" that get tiled into VRAM (fast) or RAM (warm) or
unloaded (cold), based on current workload, priority, and recency.

Architecture:
  ┌─────────────────────────────────────────────────────┐
  │  VRAM (8GB) — "Primary Monitor"                     │
  │  ┌─────────────┐ ┌──────────┐ ┌──────────────────┐  │
  │  │ Main Model  │ │ Vision   │ │ KV Cache         │  │
  │  │ (2.65GB)    │ │ MMPROJ   │ │ (1.75GB)         │  │
  │  │             │ │ (0.4GB)  │ │                  │  │
  │  └─────────────┘ └──────────┘ └──────────────────┘  │
  │  ┌──────────────────────────────────────────────┐   │
  │  │ Free space (dynamic)                         │   │
  │  └──────────────────────────────────────────────┘   │
  └─────────────────────────────────────────────────────┘
  ┌─────────────────────────────────────────────────────┐
  │  RAM (15GB) — "Secondary Monitor" (warm standby)    │
  │  ┌──────────┐ ┌──────────┐ ┌──────────────────────┐ │
  │  │ Router   │ │ Summariz │ │ Whisper STT          │ │
  │  │ (0.5B)   │ │ er(0.6B) │ │ (tiny, int8)         │ │
  │  └──────────┘ └──────────┘ └──────────────────────┘ │
  │  ┌──────────────────────────────────────────────┐   │
  │  │ Kokoro TTS  │ Main Model (offloaded weights)  │   │
  │  └──────────────────────────────────────────────┘   │
  └─────────────────────────────────────────────────────┘
  ┌─────────────────────────────────────────────────────┐
  │  Disk — "Minimized" (cold, fast reload)             │
  │  • Base models for fine-tuning                      │
  │  • Alternate model variants                         │
  └─────────────────────────────────────────────────────┘

Tiling decisions are made on every request:
  - Chat request → ensure main model is in VRAM
  - Vision request → ensure MMPROJ is in VRAM (evict KV cache if needed)
  - STT request → Whisper stays in RAM (no VRAM needed)
  - TTS request → Kokoro stays in RAM (no VRAM needed)
  - Idle (30s) → demote main model to RAM, free VRAM
  - Long generation → shrink KV cache to fit, or offload layers to RAM

The planner is adaptive — it learns from usage patterns:
  - If vision requests are frequent, keep MMPROJ resident
  - If idle periods are long, aggressively demote to save VRAM
  - If context is growing, predict KV cache pressure and pre-emptively cap
"""

import os
import time
import json
import threading
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


class MemoryTier(Enum):
    """Where a model currently lives."""
    VRAM = "vram"       # GPU memory — fastest inference
    RAM = "ram"         # System memory — warm standby, CPU inference
    DISK = "disk"       # Unloaded — cold, needs reload
    ACTIVE = "active"   # Currently being used (in VRAM + locked)


class ModelPriority(Enum):
    """Priority for VRAM tiling — higher wins."""
    CRITICAL = 100   # Main model during active generation
    HIGH = 80        # Vision MMPROJ during vision request
    NORMAL = 50      # Main model idle but recent
    LOW = 30         # Helper models (router, summarizer)
    BACKGROUND = 10  # Whisper, Kokoro (always RAM)


@dataclass
class ModelTile:
    """A model's memory footprint and current placement."""
    name: str
    size_vram_gb: float         # VRAM footprint when fully offloaded
    size_ram_gb: float          # RAM footprint (weights only, no GPU offload)
    kv_cache_gb: float = 0.0    # KV cache size (VRAM only)
    tier: MemoryTier = MemoryTier.DISK
    priority: ModelPriority = ModelPriority.NORMAL
    last_used: float = 0.0      # timestamp of last access
    use_count: int = 0          # how many times used
    gpu_layers: int = -1        # -1 = all, 0 = none (RAM only)
    can_partial_offload: bool = True  # can split between VRAM and RAM
    n_ctx: int = 4096           # context window (affects KV cache)
    locked: bool = False        # if True, can't be evicted

    @property
    def total_vram_gb(self) -> float:
        """Total VRAM usage including KV cache."""
        if self.tier == MemoryTier.DISK:
            return 0.0
        if self.tier == MemoryTier.RAM:
            return 0.0
        # VRAM or ACTIVE
        offload_ratio = 1.0 if self.gpu_layers == -1 else self.gpu_layers / max(1, self._total_layers)
        return self.size_vram_gb * offload_ratio + self.kv_cache_gb

    @property
    def total_ram_gb(self) -> float:
        """Total RAM usage."""
        if self.tier == MemoryTier.DISK:
            return 0.0
        if self.tier == MemoryTier.VRAM or self.tier == MemoryTier.ACTIVE:
            # Weights in VRAM, but llama.cpp keeps some overhead in RAM
            return self.size_ram_gb * 0.15  # ~15% RAM overhead
        # RAM tier — full weights in RAM
        return self.size_ram_gb

    def __post_init__(self):
        self._total_layers = 40  # default, updated from model


class MemoryPlanner:
    """
    Dynamic VRAM/RAM tiling planner.

    Watches workload and retiles models between VRAM, RAM, and disk
    based on priority, recency, and available memory.

    Like a window manager:
      - Promote: RAM → VRAM (when needed and space available)
      - Demote:  VRAM → RAM (when idle or space needed for higher priority)
      - Evict:   VRAM → Disk (when RAM is also full)
      - Retile:  Adjust GPU layers / KV cache to fit
    """

    def __init__(
        self,
        vram_total_gb: float = 8.0,
        vram_usable_gb: float = 6.5,
        vram_reserve_gb: float = 1.5,
        ram_total_gb: float = 15.0,
        ram_usable_gb: float = 10.0,
        idle_demote_seconds: float = 30.0,
        verbose: bool = True,
    ):
        self.vram_total_gb = vram_total_gb
        self.vram_usable_gb = vram_usable_gb
        self.vram_reserve_gb = vram_reserve_gb
        self.ram_total_gb = ram_total_gb
        self.ram_usable_gb = ram_usable_gb
        self.idle_demote_seconds = idle_demote_seconds
        self.verbose = verbose

        self._tiles: Dict[str, ModelTile] = {}
        self._lock = threading.RLock()
        self._planner_thread: Optional[threading.Thread] = None
        self._running = False
        self._last_workload: str = "idle"
        self._workload_history: List[Tuple[float, str]] = []

        # Adaptive learning
        self._vision_frequency = 0.0    # rolling average of vision requests
        self._chat_frequency = 0.0      # rolling average of chat requests
        self._idle_frequency = 1.0      # rolling average of idle time

        # Callbacks for actual model operations
        self._on_promote: Optional[callable] = None      # (name) → load to VRAM
        self._on_demote: Optional[callable] = None       # (name) → offload to RAM
        self._on_evict: Optional[callable] = None        # (name) → unload completely
        self._on_retile: Optional[callable] = None       # (name, gpu_layers, n_ctx) → adjust

    # ── Registration ──────────────────────────────────────────────────────

    def register_model(
        self,
        name: str,
        size_vram_gb: float,
        size_ram_gb: float,
        kv_cache_gb: float = 0.0,
        priority: ModelPriority = ModelPriority.NORMAL,
        can_partial_offload: bool = True,
        n_ctx: int = 4096,
    ) -> ModelTile:
        """Register a model with the planner."""
        with self._lock:
            tile = ModelTile(
                name=name,
                size_vram_gb=size_vram_gb,
                size_ram_gb=size_ram_gb,
                kv_cache_gb=kv_cache_gb,
                priority=priority,
                can_partial_offload=can_partial_offload,
                n_ctx=n_ctx,
                tier=MemoryTier.DISK,
            )
            self._tiles[name] = tile
            if self.verbose:
                print(f"  [Planner] Registered: {name} "
                      f"(VRAM={size_vram_gb}GB, RAM={size_ram_gb}GB, KV={kv_cache_gb}GB)", flush=True)
            return tile

    def set_callbacks(
        self,
        on_promote: callable = None,
        on_demote: callable = None,
        on_evict: callable = None,
        on_retile: callable = None,
    ):
        """Set callbacks for model memory operations."""
        self._on_promote = on_promote
        self._on_demote = on_demote
        self._on_evict = on_evict
        self._on_retile = on_retile

    # ── Workload tracking ─────────────────────────────────────────────────

    def signal_workload(self, workload_type: str, model_name: str = None):
        """
        Signal current workload to the planner.

        Types: "chat", "vision", "stt", "tts", "idle", "code", "creative"
        """
        now = time.time()
        with self._lock:
            self._last_workload = workload_type
            self._workload_history.append((now, workload_type))
            # Keep last 100 entries
            if len(self._workload_history) > 100:
                self._workload_history = self._workload_history[-100:]

            # Update rolling frequencies (exponential moving average)
            alpha = 0.1
            if workload_type == "vision":
                self._vision_frequency = (1 - alpha) * self._vision_frequency + alpha
                self._chat_frequency = (1 - alpha) * self._chat_frequency
                self._idle_frequency = (1 - alpha) * self._idle_frequency
            elif workload_type == "chat":
                self._chat_frequency = (1 - alpha) * self._chat_frequency + alpha
                self._vision_frequency = (1 - alpha) * self._vision_frequency
                self._idle_frequency = (1 - alpha) * self._idle_frequency
            elif workload_type == "idle":
                self._idle_frequency = (1 - alpha) * self._idle_frequency + alpha
                self._chat_frequency = (1 - alpha) * self._chat_frequency
                self._vision_frequency = (1 - alpha) * self._vision_frequency

            # Mark model as used
            if model_name and model_name in self._tiles:
                self._tiles[model_name].last_used = now
                self._tiles[model_name].use_count += 1

            # Adjust priorities based on workload
            self._adjust_priorities(workload_type)

    def _adjust_priorities(self, workload: str):
        """Dynamically adjust model priorities based on current workload."""
        with self._lock:
            if workload == "chat":
                if "main" in self._tiles:
                    self._tiles["main"].priority = ModelPriority.CRITICAL
                if "vision" in self._tiles and self._vision_frequency < 0.2:
                    self._tiles["vision"].priority = ModelPriority.LOW

            elif workload == "vision":
                if "vision" in self._tiles:
                    self._tiles["vision"].priority = ModelPriority.HIGH
                if "main" in self._tiles:
                    # Main model still needed for vision processing
                    self._tiles["main"].priority = ModelPriority.CRITICAL

            elif workload == "idle":
                if "main" in self._tiles:
                    self._tiles["main"].priority = ModelPriority.NORMAL
                if "vision" in self._tiles:
                    self._tiles["vision"].priority = ModelPriority.LOW

    # ── Tiling logic ──────────────────────────────────────────────────────

    def plan(self) -> Dict[str, Any]:
        """
        Run the tiling planner — decide what goes where.

        Returns a plan dict with actions to execute.
        """
        with self._lock:
            now = time.time()
            actions: List[Dict[str, Any]] = []

            # 1. Check for idle models that should be demoted
            for name, tile in self._tiles.items():
                if tile.locked:
                    continue
                if tile.tier in (MemoryTier.VRAM, MemoryTier.ACTIVE):
                    idle_time = now - tile.last_used
                    if idle_time > self.idle_demote_seconds and tile.priority.value < ModelPriority.CRITICAL.value:
                        actions.append({
                            "action": "demote",
                            "model": name,
                            "reason": f"idle {idle_time:.0f}s",
                            "from": tile.tier.value,
                            "to": MemoryTier.RAM.value,
                        })

            # 2. Calculate current VRAM usage
            vram_used = sum(t.total_vram_gb for t in self._tiles.values()
                           if t.tier in (MemoryTier.VRAM, MemoryTier.ACTIVE))
            ram_used = sum(t.total_ram_gb for t in self._tiles.values()
                          if t.tier != MemoryTier.DISK)

            # 3. Check if we need to make room (VRAM pressure)
            if vram_used > self.vram_usable_gb:
                # Find lowest-priority VRAM models to evict/demote
                vram_models = [(name, t) for name, t in self._tiles.items()
                              if t.tier in (MemoryTier.VRAM, MemoryTier.ACTIVE) and not t.locked]
                vram_models.sort(key=lambda x: x[1].priority.value)

                for name, tile in vram_models:
                    if vram_used <= self.vram_usable_gb:
                        break
                    if tile.can_partial_offload:
                        # Try partial offload first (retile with fewer GPU layers)
                        new_layers = max(0, tile.gpu_layers - 10)
                        if new_layers > 0:
                            actions.append({
                                "action": "retile",
                                "model": name,
                                "reason": f"VRAM pressure ({vram_used:.1f}GB > {self.vram_usable_gb}GB)",
                                "gpu_layers": new_layers,
                                "n_ctx": tile.n_ctx,
                            })
                            # Estimate savings
                            vram_used -= tile.size_vram_gb * (10 / max(1, tile._total_layers))
                    else:
                        # Full demote
                        actions.append({
                            "action": "demote",
                            "model": name,
                            "reason": f"VRAM pressure ({vram_used:.1f}GB > {self.vram_usable_gb}GB)",
                            "from": tile.tier.value,
                            "to": MemoryTier.RAM.value,
                        })
                        vram_used -= tile.total_vram_gb

            # 4. Check if we should promote models from RAM to VRAM
            # (when there's free VRAM and a model is needed)
            free_vram = self.vram_usable_gb - vram_used
            if free_vram > 0.5:  # at least 500MB free
                ram_models = [(name, t) for name, t in self._tiles.items()
                             if t.tier == MemoryTier.RAM and not t.locked]
                ram_models.sort(key=lambda x: x[1].priority.value, reverse=True)

                for name, tile in ram_models:
                    if free_vram < tile.size_vram_gb:
                        continue
                    if tile.priority.value >= ModelPriority.HIGH.value:
                        actions.append({
                            "action": "promote",
                            "model": name,
                            "reason": f"high priority + free VRAM ({free_vram:.1f}GB)",
                            "from": MemoryTier.RAM.value,
                            "to": MemoryTier.VRAM.value,
                        })
                        free_vram -= tile.size_vram_gb

            # 5. Check RAM pressure — evict to disk if RAM is full
            if ram_used > self.ram_usable_gb:
                ram_models = [(name, t) for name, t in self._tiles.items()
                             if t.tier == MemoryTier.RAM and not t.locked]
                ram_models.sort(key=lambda x: x[1].priority.value)

                for name, tile in ram_models:
                    if ram_used <= self.ram_usable_gb:
                        break
                    if tile.priority.value < ModelPriority.NORMAL.value:
                        actions.append({
                            "action": "evict",
                            "model": name,
                            "reason": f"RAM pressure ({ram_used:.1f}GB > {self.ram_usable_gb}GB)",
                            "from": MemoryTier.RAM.value,
                            "to": MemoryTier.DISK.value,
                        })
                        ram_used -= tile.total_ram_gb

            # 6. Adaptive KV cache resizing
            for name, tile in self._tiles.items():
                if tile.tier in (MemoryTier.VRAM, MemoryTier.ACTIVE) and tile.kv_cache_gb > 0.5:
                    # If VRAM is tight, suggest smaller context
                    if vram_used > self.vram_usable_gb * 0.85:
                        new_ctx = max(1024, tile.n_ctx // 2)
                        if new_ctx != tile.n_ctx:
                            actions.append({
                                "action": "retile",
                                "model": name,
                                "reason": "KV cache pressure — halving context",
                                "gpu_layers": tile.gpu_layers,
                                "n_ctx": new_ctx,
                            })

            plan = {
                "timestamp": now,
                "workload": self._last_workload,
                "vram_used_gb": round(vram_used, 2),
                "vram_free_gb": round(self.vram_usable_gb - vram_used, 2),
                "ram_used_gb": round(ram_used, 2),
                "ram_free_gb": round(self.ram_usable_gb - ram_used, 2),
                "actions": actions,
                "frequencies": {
                    "chat": round(self._chat_frequency, 2),
                    "vision": round(self._vision_frequency, 2),
                    "idle": round(self._idle_frequency, 2),
                },
                "tiles": {
                    name: {
                        "tier": t.tier.value,
                        "priority": t.priority.name,
                        "vram_gb": round(t.total_vram_gb, 2),
                        "ram_gb": round(t.total_ram_gb, 2),
                        "gpu_layers": t.gpu_layers,
                        "n_ctx": t.n_ctx,
                        "last_used_ago_s": round(now - t.last_used, 0) if t.last_used else None,
                        "use_count": t.use_count,
                        "locked": t.locked,
                    }
                    for name, t in self._tiles.items()
                },
            }

            return plan

    def execute_plan(self, plan: Dict[str, Any]) -> List[str]:
        """Execute the plan's actions via callbacks."""
        results = []
        for action in plan.get("actions", []):
            try:
                model = action["model"]
                act = action["action"]

                if act == "promote" and self._on_promote:
                    self._on_promote(model)
                    self._tiles[model].tier = MemoryTier.VRAM
                    self._tiles[model].gpu_layers = -1
                    results.append(f"↑ Promoted {model} → VRAM")

                elif act == "demote" and self._on_demote:
                    self._on_demote(model)
                    self._tiles[model].tier = MemoryTier.RAM
                    self._tiles[model].gpu_layers = 0
                    results.append(f"↓ Demoted {model} → RAM")

                elif act == "evict" and self._on_evict:
                    self._on_evict(model)
                    self._tiles[model].tier = MemoryTier.DISK
                    self._tiles[model].gpu_layers = 0
                    results.append(f"✕ Evicted {model} → Disk")

                elif act == "retile" and self._on_retile:
                    self._on_retile(model, action.get("gpu_layers", -1), action.get("n_ctx", 4096))
                    self._tiles[model].gpu_layers = action.get("gpu_layers", -1)
                    self._tiles[model].n_ctx = action.get("n_ctx", 4096)
                    results.append(f"↔ Retiled {model} (layers={action.get('gpu_layers')}, ctx={action.get('n_ctx')})")

            except Exception as e:
                results.append(f"⚠ {action.get('action')} {action.get('model')} failed: {e}")

        return results

    # ── Background planner thread ─────────────────────────────────────────

    def start(self, interval: float = 5.0):
        """Start the background planner thread."""
        if self._running:
            return
        self._running = True
        self._planner_thread = threading.Thread(target=self._planner_loop, args=(interval,), daemon=True)
        self._planner_thread.start()
        if self.verbose:
            print(f"  [Planner] Started — interval={interval}s, "
                  f"VRAM budget={self.vram_usable_gb}GB, RAM budget={self.ram_usable_gb}GB", flush=True)

    def stop(self):
        """Stop the background planner."""
        self._running = False
        if self._planner_thread:
            self._planner_thread.join(timeout=5)

    def _planner_loop(self, interval: float):
        """Background loop — plan and execute periodically."""
        while self._running:
            try:
                # Auto-detect idle
                now = time.time()
                recent_activity = any(
                    now - ts < self.idle_demote_seconds
                    for ts, _ in self._workload_history[-10:]
                )
                if not recent_activity:
                    self.signal_workload("idle")

                plan = self.plan()
                results = self.execute_plan(plan)

                if results and self.verbose:
                    for r in results:
                        print(f"  [Planner] {r}", flush=True)

            except Exception as e:
                if self.verbose:
                    print(f"  [Planner] Error: {e}", flush=True)

            time.sleep(interval)

    # ── Querying ──────────────────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """Get current memory tiling status."""
        with self._lock:
            return self.plan()

    def get_model_tier(self, name: str) -> MemoryTier:
        """Get the current tier of a model."""
        with self._lock:
            if name in self._tiles:
                return self._tiles[name].tier
            return MemoryTier.DISK

    def lock_model(self, name: str):
        """Lock a model in its current tier (can't be evicted)."""
        with self._lock:
            if name in self._tiles:
                self._tiles[name].locked = True

    def unlock_model(self, name: str):
        """Unlock a model."""
        with self._lock:
            if name in self._tiles:
                self._tiles[name].locked = False

    # ── GPU sensing ───────────────────────────────────────────────────────

    @staticmethod
    def sense_vram() -> Dict[str, float]:
        """Sense actual VRAM usage from nvidia-smi."""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total,memory.used,memory.free",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split(", ")
                return {
                    "total_gb": float(parts[0]) / 1024,
                    "used_gb": float(parts[1]) / 1024,
                    "free_gb": float(parts[2]) / 1024,
                }
        except Exception:
            pass
        return {"total_gb": 8.0, "used_gb": 0.0, "free_gb": 8.0}

    @staticmethod
    def sense_ram() -> Dict[str, float]:
        """Sense actual RAM usage."""
        try:
            with open("/proc/meminfo") as f:
                lines = f.readlines()
            info = {}
            for line in lines:
                parts = line.split()
                if parts[0] in ("MemTotal:", "MemAvailable:", "MemFree:", "SwapTotal:", "SwapFree:"):
                    info[parts[0].rstrip(":")] = int(parts[1]) / (1024 * 1024)  # to GB
            return {
                "total_gb": info.get("MemTotal", 15.0),
                "used_gb": info.get("MemTotal", 15.0) - info.get("MemAvailable", 0),
                "free_gb": info.get("MemAvailable", 0),
                "swap_total_gb": info.get("SwapTotal", 0),
                "swap_used_gb": info.get("SwapTotal", 0) - info.get("SwapFree", 0),
            }
        except Exception:
            return {"total_gb": 15.0, "used_gb": 0.0, "free_gb": 15.0}
