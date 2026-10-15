"""
runtime/vram_guard.py — FoveAI VRAM & Model Concurrency Guardrail
==================================================================
Strict governor for hardware with 8GB VRAM:
  1. Concurrency Cap: Allows at most ONE Main Model and ONE Helper Model.
     Prevents runaway processes from spinning up multiple heavy LLMs simultaneously.
  2. 8GB VRAM Governor: Detects model size. Prevents blind -1 layer offload on
     oversized models (e.g., 16GB models) which would otherwise overflow VRAM,
     spill into system RAM, and make the PC sluggish.
  3. Automatic Eviction: Cleanly unloads/signals prior model instances before
     loading a new candidate.
"""

import getpass
import json
import os
import time
from pathlib import Path
from typing import Any

LOCK_DIR = Path(
    os.environ.get("FOVEAI_LOCK_DIR", Path(__file__).parent.parent / ".model_locks")
)
MAX_VRAM_GB = float(os.environ.get("FOVEAI_MAX_VRAM_GB", "8.0"))
USABLE_VRAM_GB = float(
    os.environ.get("FOVEAI_USABLE_VRAM_GB", "6.5")
)  # Reserve 1.5GB for OS & WebXR display

# ── Lane sensing ──────────────────────────────────────────────────────────
# The governor used to ask one question: "how much is free?" A machine can be
# drowning with plenty free, and a machine can be idle with none. These let it
# ask the two questions that actually predict how the box FEELS, so a slowdown
# can be explained in numbers instead of guessed at.
#
# Linux Pressure Stall Information (PSI) is the honest instrument here: it is
# the kernel's own measure of how much wall-clock time tasks spent stalled. It is
# what "the disk is slow" actually is, measured rather than inferred.
LANE_IO_STALL_WARN = float(os.environ.get("FOVEAI_LANE_IO_STALL_WARN", "15"))
LANE_IO_STALL_BLOCK = float(os.environ.get("FOVEAI_LANE_IO_STALL_BLOCK", "35"))
LANE_HEADROOM_GB = float(os.environ.get("FOVEAI_LANE_HEADROOM_GB", "2.0"))
LANE_FOREIGN_VRAM_GB = float(os.environ.get("FOVEAI_LANE_FOREIGN_VRAM_GB", "0.5"))
# Below this footprint we stay quiet. Small work never needs announcing.
LANE_ANNOUNCE_MIN_GB = float(os.environ.get("FOVEAI_LANE_ANNOUNCE_MIN_GB", "4.0"))
# Human idle past this and we may take the lane without asking.
LANE_HUMAN_IDLE_GRACE_S = float(os.environ.get("FOVEAI_LANE_HUMAN_IDLE_S", "900"))

# ── Gaming / Exclusive Model Guardrail ────────────────────────────────────
# Blocks a model load when the GPU is already owned by a game or an active
# streaming session, so we do not spill into system RAM (which is what causes
# the freezes).
#
# HOW A GAME IS ACTUALLY DETECTED (2026-10-11):
#   The trigger is MEASURED VRAM held by a foreign GPU process, not a listening
#   port. Two reasons:
#     • xrdp (3389) and sunshine (47989/47984) keep their ports LISTENing even
#       when idle — blocking on the port alone would refuse every load on a box
#       that merely has remote access enabled.
#     • A game is a *graphics* (G) process. `nvidia-smi --query-compute-apps`
#       only lists compute (C) processes, so a running game is invisible there.
#       We parse the full nvidia-smi table (C and G) to see it.
#   A game always holds gigabytes of VRAM; that is the honest, measurable line.
#
# GAMING_PORTS is kept as a reference map of ports -> human name, used to label
# a hog when its process name matches a known service.
GAMING_PORTS = {
    # XRDP remote desktop — full GPU passthrough typically claimed
    "xrdp_3389": {"port": 3389, "name": "xrdp (Remote Desktop)", "proc": "xrdp"},
    # Sunshine game streaming — aggressive GPU capture
    "sunshine_47989": {"port": 47989, "name": "sunshine (Game Streaming)", "proc": "sunshine"},
    "sunshine_47984": {"port": 47984, "name": "sunshine (Game Streaming alt)", "proc": "sunshine"},
    # Extra llama-servers — compete for n-gpu-layers / VRAM
    "llama_8408": {"port": 8408, "name": "llama-server (9B MoQ)", "proc": "llama-server"},
    "llama_8612": {"port": 8612, "name": "llama-server (Core Router)", "proc": "llama-server"},
    "llama_8616": {"port": 8616, "name": "llama-server (Draft Router)", "proc": "llama-server"},
    # XRLF — also owns the weights; explicit blocking
    "xrlf_8402": {"port": 8402, "name": "XRLF Runtime (:8402)", "proc": "xrlf"},
}

# A foreign (non-FoveAI) GPU process holding at least this much VRAM counts as
# a game / heavy GPU session. Below it (Xorg compositor, a browser, the Unity
# editor) we stay out of the way — small work never needs blocking.
GAMING_VRAM_GB = float(os.environ.get("FOVEAI_GAMING_VRAM_GB", "1.5"))

# Escape hatch: FOVEAI_ALLOW_GAMING_OVERLOAD=1 skips the gate and loads anyway
# (the model will clamp/spill as best it can). For "I know, load it now".
GAMING_OVERLOAD_OVERRIDE = os.environ.get("FOVEAI_ALLOW_GAMING_OVERLOAD", "0") == "1"

# Decisions are also written here, in prose, so an explanation survives even
# when nothing is listening on the IPC port.
LANE_LOG = LOCK_DIR / "lane.log"

# Exit/decision codes, explained for humans. No opaque failures: every refusal
# a human can trigger carries a sentence saying what happened and what to do.
LANE_EXPLAIN = {
    "clear": "Lane is free — nothing else is competing for it.",
    "busy": "Lane is busy — measured pressure, but the work fits. Proceeding "
            "with your awareness.",
    "blocked_io": "Disk is saturated — tasks are spending real time stalled on "
                  "I/O. Starting now would slow everything else down.",
    "blocked_vram": "Not enough video memory left — another program is holding "
                    "the GPU, and this model would spill into system RAM "
                    "(which is the resource that causes freezes).",
    "blocked_ram": "Not enough system memory free — this model would push the "
                   "desktop into swap, which is what causes the long freezes.",
    "human_away": "Nobody at the keyboard — taking the lane without asking.",
    "never_preempt": "Yield only happens between batches, never mid-task.",
}

ROLE_MAIN = "main"
ROLE_HELPER = "helper"

# GGUF value-type enum -> struct format / byte size.
_GGUF_STRUCT = {0: "B", 1: "b", 2: "H", 3: "h", 4: "I", 5: "i",
                6: "f", 7: "?", 10: "Q", 11: "q", 12: "d"}
_GGUF_SIZE = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}


def read_gguf_scalars(model_path: str, max_pairs: int = 256) -> dict | None:
    """Read GGUF header scalar/string KV pairs — fast.

    `GGUFReader` parses the ENTIRE metadata and takes ~1 minute on a big model
    (measured 71 s on a 2.8 GB gguf), which is unacceptable for a service
    launcher. Everything we need (architecture, block_count, attention/SSM
    dims) lives in the first handful of KV pairs, before the huge tokenizer
    arrays. So we walk the KV section only, skipping arrays by size/seek, and
    stop once the namespace reaches `tokenizer.*`. Returns {key: value} for
    scalars/strings, or None if the file is not a readable GGUF.
    """
    import struct

    try:
        out: dict = {}
        with open(model_path, "rb") as f:
            if f.read(4) != b"GGUF":
                return None
            struct.unpack("<I", f.read(4))  # version
            f.read(8)  # tensor_count
            kv_count = struct.unpack("<Q", f.read(8))[0]
            for _ in range(min(kv_count, max_pairs)):
                klen = struct.unpack("<Q", f.read(8))[0]
                key = f.read(klen).decode("utf-8", "replace")
                vtype = struct.unpack("<I", f.read(4))[0]
                if vtype == 9:  # array — skip without materialising
                    etype = struct.unpack("<I", f.read(4))[0]
                    count = struct.unpack("<Q", f.read(8))[0]
                    if etype == 8:  # array of strings
                        for _2 in range(count):
                            f.seek(struct.unpack("<Q", f.read(8))[0], 1)
                    elif etype == 9:  # nested array — stop, we're past the header
                        return out
                    else:
                        f.seek(count * _GGUF_SIZE.get(etype, 1), 1)
                    continue
                if vtype == 8:  # string
                    sl = struct.unpack("<Q", f.read(8))[0]
                    out[key] = f.read(sl).decode("utf-8", "replace")
                else:
                    fmt = _GGUF_STRUCT.get(vtype)
                    if fmt is None:
                        return out
                    out[key] = struct.unpack("<" + fmt, f.read(_GGUF_SIZE[vtype]))[0]
                if key.startswith("tokenizer.") and any(
                    k.endswith(".block_count") for k in out
                ):
                    break
        return out
    except Exception:
        return None


class VRAMGuardrail:
    """Singleton VRAM and model concurrency controller."""

    def __init__(self, lock_dir: Path = LOCK_DIR):
        self.lock_dir = lock_dir
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        self._cleanup_stale_notices()

    def _cleanup_stale_notices(self):
        """Remove eviction notices addressed to dead PIDs — they accumulate
        across restarts and can unload a reused PID's model by accident."""
        try:
            for f in self.lock_dir.glob("evict_*.json"):
                try:
                    pid = int(f.stem.split("_", 1)[1])
                except (ValueError, IndexError):
                    f.unlink(missing_ok=True)
                    continue
                if not self._pid_exists(pid):
                    f.unlink(missing_ok=True)
        except Exception:
            pass

    @staticmethod
    def _friendly_model_name(model_path: str) -> str:
        """Extracted artifacts are all named 'core.gguf' inside
        '<model>.xrlf.cache/' — use the parent dir so logs/notices show the
        real model name instead of a meaningless 'core.gguf'."""
        name = Path(model_path).name
        if name == "core.gguf":
            parent = Path(model_path).parent.name
            if parent.endswith(".xrlf.cache"):
                return parent[: -len(".cache")]
            return parent or name
        return name

    def _lock_file(self, role: str) -> Path:
        return self.lock_dir / f"{role}_model.lock"

    def is_active(self, role: str) -> dict[str, Any] | None:
        """Check if a model for the given role is currently registered and active."""
        lf = self._lock_file(role)
        if not lf.exists():
            return None
        try:
            with open(lf, "r", encoding="utf-8") as f:
                data = json.load(f)
            pid = data.get("pid")
            # Check if process is still alive on Windows
            if pid and self._pid_exists(pid):
                return data
            else:
                # Stale lock
                lf.unlink(missing_ok=True)
                return None
        except Exception:
            return None

    def _pid_exists(self, pid: int) -> bool:
        """Check if a PID is a running process on Windows."""
        if os.name == "nt":
            import ctypes

            kernel32 = ctypes.windll.kernel32
            SYNCHRONIZE = 0x00100000
            STILL_ACTIVE = 259
            process = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
            if process == 0:
                return False
            # Check exit code — zombie/reused PIDs return non-STILL_ACTIVE
            exit_code = ctypes.wintypes.DWORD()
            kernel32.GetExitCodeProcess(process, ctypes.byref(exit_code))
            kernel32.CloseHandle(process)
            return exit_code.value == STILL_ACTIVE
        else:
            try:
                os.kill(pid, 0)
                return True
            except ProcessLookupError:
                return False
            except OSError:
                return False

    def get_realtime_free_vram_gb(self) -> float:
        """
        Query real-time physical free VRAM.
        On Linux: uses nvidia-smi CLI.
        On Windows: uses nvml.dll directly.
        Returns free VRAM in GB, or fallback to USABLE_VRAM_GB if unavailable.
        """
        # ── Linux: nvidia-smi ──
        if os.name != "nt":
            try:
                import subprocess as _sp

                out = _sp.check_output(
                    [
                        "nvidia-smi",
                        "--query-gpu=memory.free",
                        "--format=csv,noheader,nounits",
                    ],
                    timeout=5,
                    text=True,
                ).strip()
                # May return multiple lines for multi-GPU; take the first
                free_mib = float(out.splitlines()[0].strip())
                return float(free_mib / 1024.0)
            except Exception:
                return USABLE_VRAM_GB

        # ── Windows: NVML DLL ──
        try:
            import ctypes

            nvml = ctypes.CDLL("nvml.dll")
            nvml.nvmlInit_v2()
            h = ctypes.c_void_p()
            nvml.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(h))

            class Mem(ctypes.Structure):
                _fields_ = [
                    ("total", ctypes.c_ulonglong),
                    ("free", ctypes.c_ulonglong),
                    ("used", ctypes.c_ulonglong),
                ]

            m = Mem()
            nvml.nvmlDeviceGetMemoryInfo(h, ctypes.byref(m))
            free_gb = m.free / (1024**3)
            nvml.nvmlShutdown()
            return float(free_gb)
        except Exception:
            return USABLE_VRAM_GB

    def _kv_per_token_bytes(self, model_path: str) -> float | None:
        """Read the GGUF metadata and compute exact KV bytes/token.

        Dense models keep KV on every layer; hybrid SSM archs (e.g. qwen35)
        only on every `full_attention_interval`-th layer, plus a small fixed
        SSM state. Returns None when metadata can't be read.
        """
        md = read_gguf_scalars(model_path)
        if not md:
            return None
        arch = md.get("general.architecture")
        if not arch:
            return None
        blocks = md.get(f"{arch}.block_count")
        if not blocks:
            return None
        blocks = int(blocks)
        interval = int(md.get(f"{arch}.full_attention_interval") or 0)
        attn_layers = max(1, blocks // interval) if interval > 0 else blocks

        kv_heads = int(md.get(f"{arch}.attention.head_count_kv") or 1)
        key_len = int(
            md.get(f"{arch}.attention.key_length")
            or md.get(f"{arch}.embedding_length")
            or 0
        )
        val_len = int(md.get(f"{arch}.attention.value_length") or key_len)
        if not key_len:
            return None

        # f16 K+V per token across KV-keeping layers
        kv_bytes = attn_layers * (key_len + val_len) * kv_heads * 2

        # Hybrid SSM state: recurrent layers carry a fixed per-sequence
        # state (~inner_size * state_size * 2B each). Model as a flat
        # per-token allowance; it over-reserves slightly, safely.
        ssm_state = md.get(f"{arch}.ssm.state_size")
        ssm_inner = md.get(f"{arch}.ssm.inner_size")
        if ssm_state and ssm_inner:
            ssm_layers = blocks - attn_layers
            ssm_bytes = (
                float(ssm_layers) * float(ssm_state) * float(ssm_inner) * 2.0
            )
            # Fixed state, not per-token: amortize over ctx in caller via
            # a pseudo per-token bump of ~10% of KV.
            kv_bytes += ssm_bytes / max(1.0, 8192.0)

        return float(kv_bytes)

    def model_layer_count(self, model_path: str) -> int | None:
        """Real transformer block count from GGUF metadata.

        Lets a launcher clamp to the model's actual depth instead of guessing
        (or passing a meaningless `-ngl 999`). Returns None if unreadable.
        """
        md = read_gguf_scalars(model_path)
        if not md:
            return None
        arch = md.get("general.architecture")
        if not arch:
            return None
        blocks = md.get(f"{arch}.block_count")
        return int(blocks) if blocks else None

    def estimate_kv_cache_gb(
        self, n_ctx: int, total_layers: int = 33, model_path: str = None
    ) -> float:
        """
        Estimate VRAM consumed by the KV cache during inference.
        Uses exact GGUF metadata when available (handles hybrid SSM archs);
        falls back to a conservative ~0.35 GB per 1024 tokens heuristic.
        """
        if model_path:
            per_token = self._kv_per_token_bytes(model_path)
            if per_token:
                return round(n_ctx * per_token / (1024**3), 2)
        ctx_k = max(1, n_ctx) / 1024.0
        # Scale with layers relative to standard 32-layer model
        layer_scale = max(0.8, total_layers / 32.0)
        return round(ctx_k * 0.35 * layer_scale, 2)

    def acquire_slot(
        self,
        role: str,
        model_path: str,
        requested_layers: int = -1,
        total_model_layers: int = 33,
        n_ctx: int = 4096,
    ) -> tuple[bool, int, str]:
        """
        Acquire execution slot for a model role.
        Implements Preemptive Hot-Swap (Latest-Wins) + Real-time VRAM Governor:
          - Measures real physical free VRAM via NVML.
          - Accounts for model weights + KV Cache + 1.8GB safety reserve (OS/display/CUDA).
          - Clamps GPU layers safely to avoid PCIe WDDM thrashing and PC crashes.
          - Flags partial/hybrid offloads so GUIs can announce expected higher latency.
        Returns: (success, safe_gpu_layers, message)
        """
        active = self.is_active(role)
        current_pid = os.getpid()
        requested_model_name = self._friendly_model_name(model_path)

        # ── Gaming gate: never drag the main model into a GPU a game owns. ──
        # Runs BEFORE any eviction so we refuse without disturbing anyone.
        # Helper/aux models run on CPU regardless, so they are not gated.
        if role == ROLE_MAIN:
            gaming = self._check_gaming_ports()
            if gaming is not None:
                reasons = "; ".join(gaming["reasons"])
                msg = (
                    f"Refused: the GPU is busy ({reasons}). Close it, or set "
                    f"FOVEAI_ALLOW_GAMING_OVERLOAD=1 to load anyway."
                )
                print(f"[VRAM Guardrail] 🎮 {msg}")
                self._lane_journal(
                    {"verdict": gaming["verdict"], "reasons": gaming["reasons"]},
                    "acquire_slot",
                    "refuse",
                )
                return (False, requested_layers, msg)

        if active and active.get("pid") != current_pid:
            old_name = active.get("model", "unknown")
            old_pid = active.get("pid")
            old_path = active.get("path", "")

            # 1. Same model already loaded in THIS process — reuse (same PID only)
            #    Cross-process model sharing is not supported by llama-cpp-python.
            #    Always evict stale locks and load fresh.

            # 2. Model mismatch or stale lock: Preemptive Hot-Swap (Evict previous model)
            print(
                f"[VRAM Guardrail] 🔄 Preemptive Hot-Swap: Program requested '{requested_model_name}'."
            )
            print(
                f"   Cleanly evicting previous {role} model '{old_name}' (PID {old_pid}) to protect 8GB VRAM..."
            )
            self._evict_model_process(role, active, requested_model_name)

        # Calculate model weights size
        size_gb = 0.0
        try:
            p = Path(model_path)
            if p.exists():
                size_gb = p.stat().st_size / (1024**3)
        except Exception:
            pass

        real_free_gb = self.get_realtime_free_vram_gb()
        SAFETY_RESERVE_GB = (
            1.8  # Floor reserved for Windows DWM, display, and CUDA runtime context
        )
        usable_budget_gb = max(1.0, real_free_gb - SAFETY_RESERVE_GB)
        kv_cache_gb = self.estimate_kv_cache_gb(
            n_ctx, total_model_layers, model_path=model_path
        )

        safe_layers = requested_layers
        is_hybrid = False
        status_msg = "Slot acquired successfully"

        # ── TIER 1: MAIN COGNITIVE MODEL ──
        if role == ROLE_MAIN:
            total_required_gb = size_gb + kv_cache_gb

            print(
                f"[VRAM Guardrail] 📊 Real-time NVML: {real_free_gb:.2f} GB Free | Safety Floor: {SAFETY_RESERVE_GB:.1f} GB | Usable Budget: {usable_budget_gb:.2f} GB"
            )
            print(
                f"   Model Weights: {size_gb:.2f} GB | KV Cache (n_ctx={n_ctx}): ~{kv_cache_gb:.2f} GB | Total Required: ~{total_required_gb:.2f} GB"
            )

            if total_required_gb <= usable_budget_gb:
                # Comfortable fit! Full GPU acceleration
                safe_layers = requested_layers
                status_msg = f"Full GPU Offload ({size_gb:.1f}GB + {kv_cache_gb:.1f}GB KV in VRAM)"
                print(f"[VRAM Guardrail] 🚀 {status_msg}")
            else:
                # Exceeds usable budget -> DYNAMIC CLAMPING (Avoid PC Crash!)
                available_for_weights = max(0.5, usable_budget_gb - kv_cache_gb)

                if available_for_weights < 1.0:
                    # Not enough VRAM even for minimal weights -> Full CPU Fallback
                    safe_layers = 0
                    is_hybrid = False
                    status_msg = f"Full CPU Mode (VRAM tight: {real_free_gb:.1f}GB free) — Expect longer latency"
                    print(
                        "[VRAM Guardrail] 🛡️ 8GB VRAM GOVERNOR: Spawning on CPU (n_gpu_layers=0) to prevent PC crash."
                    )
                else:
                    # Hybrid GPU/CPU Partial Offload
                    ratio = min(0.85, available_for_weights / max(0.1, size_gb))
                    safe_layers = max(1, int(total_model_layers * ratio))
                    is_hybrid = True
                    status_msg = f"⚡ Hybrid GPU/CPU ({safe_layers}/{total_model_layers} layers on GPU) — Expect longer latency"
                    print("[VRAM Guardrail] 🛡️ 8GB VRAM GOVERNOR ENGAGED:")
                    print(
                        f"   Clamping GPU layers: {requested_layers} → {safe_layers}/{total_model_layers} layers."
                    )
                    print(f"   {status_msg}")

        # ── TIER 2: HELPER / DRAFT / ROUTER / AUXILIARY MODEL (Strict CPU Fallback) ──
        elif role == ROLE_HELPER:
            allow_gpu_helper = os.environ.get("FOVEAI_ALLOW_HELPER_GPU", "0") == "1"
            if not allow_gpu_helper:
                # Helper models MUST run on CPU to keep GPU VRAM 100% clear for the main model & Flash Attention
                safe_layers = 0
                is_hybrid = False
                status_msg = (
                    "Helper on CPU (n_gpu_layers=0) — Preserving VRAM for Main Model"
                )
                print(
                    f"[VRAM Guardrail] 💡 Helper/Auxiliary model ({size_gb:.2f} GB) strictly routed to CPU (n_gpu_layers=0) to maximize Main Model VRAM & Flash Attention."
                )
            else:
                safe_layers = (
                    requested_layers if requested_layers != -1 else total_model_layers
                )
                status_msg = f"Helper GPU offload ({safe_layers} layers)"
                print(
                    f"[VRAM Guardrail] 🚀 Helper model GPU offload allowed: {status_msg}"
                )

        # Estimate actual VRAM commitment
        vram_used = (
            size_gb if safe_layers == -1 or safe_layers >= total_model_layers else 0.0
        )
        if safe_layers > 0 and safe_layers < total_model_layers:
            vram_used = size_gb * (safe_layers / total_model_layers) + kv_cache_gb

        # Register active lock
        lock_data = {
            "role": role,
            "pid": current_pid,
            "model": requested_model_name,
            "path": str(model_path),
            "size_gb": round(size_gb, 2),
            "kv_cache_gb": round(kv_cache_gb, 2),
            "vram_used_gb": round(vram_used, 2),
            "gpu_layers": safe_layers,
            "total_layers": total_model_layers,
            "is_hybrid": is_hybrid,
            "status_text": status_msg,
            "timestamp": time.time(),
        }
        try:
            with open(self._lock_file(role), "w", encoding="utf-8") as f:
                json.dump(lock_data, f, indent=2)
        except Exception as e:
            print(f"[VRAM Guardrail] Warning: failed to write lockfile: {e}")

        return (True, safe_layers, status_msg)

    def _evict_model_process(self, role: str, active: dict[str, Any], new_model: str):
        """Cleanly evict prior model process and notify programs silently."""
        old_pid = active.get("pid")
        old_name = active.get("model", "unknown")
        if not old_pid:
            return
        if not self._pid_exists(old_pid):
            # Lock holder is already dead — just drop the stale lock, no notices.
            self._lock_file(role).unlink(missing_ok=True)
            return

        eviction_notice = {
            "role": role,
            "evicted_pid": old_pid,
            "evicted_model": old_name,
            "new_model": new_model,
            "timestamp": time.time(),
            "silent": True,
        }

        # 1. Post notice file for target PID
        notice_file = self.lock_dir / f"evict_{old_pid}.json"
        try:
            with open(notice_file, "w", encoding="utf-8") as f:
                json.dump(eviction_notice, f, indent=2)
        except Exception:
            pass

        # 2. Also record general role eviction notice
        try:
            with open(
                self.lock_dir / f"{role}_eviction.json", "w", encoding="utf-8"
            ) as f:
                json.dump(eviction_notice, f, indent=2)
        except Exception:
            pass

        # 3. Broadcast silent IPC event to port 8400 (if active)
        self._broadcast_silent_ipc("model_evicted", eviction_notice)

        # 4. Give the old process a grace period (up to 1.0s) to exit cleanly
        for _ in range(10):
            if not self._pid_exists(old_pid):
                break
            time.sleep(0.1)

        # 5. If still alive, terminate process to reclaim VRAM
        if self._pid_exists(old_pid):
            self._terminate_pid(old_pid)

        # 6. Unlink the old lock and pause briefly for NVIDIA driver memory reclaim
        self._lock_file(role).unlink(missing_ok=True)
        time.sleep(0.4)
        print(
            f"[VRAM Guardrail] 🧹 Eviction complete. VRAM reclaimed for '{new_model}'."
        )

    def _terminate_pid(self, pid: int):
        """Forcefully terminate a process holding VRAM."""
        try:
            if os.name == "nt":
                import subprocess

                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True,
                    timeout=3,
                )
            else:
                import signal

                os.kill(pid, signal.SIGKILL)
        except Exception as e:
            print(f"[VRAM Guardrail] Warning terminating PID {pid}: {e}")

    def _broadcast_silent_ipc(self, event_type: str, payload: dict[str, Any]):
        """
        Notify other services/programs.

        Historically this posted straight to :8400/v1/internal/ipc and swallowed
        every error — a route that exists nowhere in the codebase, so the notice
        died silently every single time. It now goes through runtime/hotline.py,
        which writes to disk BEFORE attempting delivery, so a missing listener
        costs latency instead of losing the message.
        """
        try:
            from hotline import publish

            level = str(payload.get("level") or "info")
            publish(
                event_type,
                payload,
                level=level if level in ("info", "notice", "warn", "urgent") else "info",
                actor="vram_guard",
                explain=payload.get("body") or payload.get("explain"),
                explanation=payload.get("explanation"),
            )
        except Exception:
            pass

    def poll_eviction(self, pid: int | None = None) -> dict[str, Any] | None:
        """
        Check if the current process has been evicted by a newer model request.
        Returns the eviction notice dict if evicted, or None.
        """
        target_pid = pid or os.getpid()
        notice_file = self.lock_dir / f"evict_{target_pid}.json"
        if not notice_file.exists():
            return None
        try:
            with open(notice_file, "r", encoding="utf-8") as f:
                notice = json.load(f)
            notice_file.unlink(missing_ok=True)
            return notice
        except Exception:
            return None

    def release_slot(self, role: str):
        """Release the model slot when unloading or exiting."""
        lf = self._lock_file(role)
        try:
            if lf.exists():
                with open(lf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("pid") == os.getpid():
                    lf.unlink(missing_ok=True)
                    print(f"[VRAM Guardrail] 🔓 Released {role} model slot.")
        except Exception:
            lf.unlink(missing_ok=True)

    # ── Smart Model Loader with Dynamic CPU Offloading ─────────────────────
    def calculate_smart_offload(
        self,
        model_path: str,
        total_layers: int = 33,
        n_ctx: int = 4096,
        safety_floor_gb: float = 1.6,
    ) -> dict[str, Any]:
        """
        Dynamically calculate how many layers to allocate to GPU vs offload to CPU/RAM.
        Accounts for all other active processes consuming VRAM.
        """
        size_gb = 0.0
        try:
            p = Path(model_path)
            if p.exists():
                size_gb = round(p.stat().st_size / (1024**3), 2)
        except Exception:
            pass

        real_free_gb = round(self.get_realtime_free_vram_gb(), 2)
        usable_budget_gb = round(max(0.5, real_free_gb - safety_floor_gb), 2)
        kv_cache_gb = self.estimate_kv_cache_gb(
            n_ctx, total_layers, model_path=model_path
        )
        total_needed_gb = round(size_gb + kv_cache_gb, 2)

        # Determine layer split
        if total_needed_gb <= usable_budget_gb:
            # Full GPU offload fits comfortably
            gpu_layers = total_layers
            cpu_layers = 0
            mode = "Full GPU ⚡"
            is_hybrid = False
            summary = (
                f"Full GPU Acceleration: All {total_layers} layers in VRAM "
                f"({size_gb}GB weights + {kv_cache_gb}GB KV cache)."
            )
        else:
            # Overflow condition -> Offload excess layers to CPU
            available_for_weights = max(0.0, usable_budget_gb - kv_cache_gb)
            if available_for_weights < 0.8 or usable_budget_gb < 1.0:
                # VRAM too cramped for weights -> 100% CPU offload
                gpu_layers = 0
                cpu_layers = total_layers
                mode = "Full CPU 💻"
                is_hybrid = False
                summary = (
                    f"Full CPU Offload: All {total_layers} layers running on CPU/RAM "
                    f"({real_free_gb}GB free VRAM preserved for active desktop & WebXR apps)."
                )
            else:
                # Hybrid offload: Partial GPU, remainder offloaded to CPU
                ratio = min(0.85, available_for_weights / max(0.1, size_gb))
                gpu_layers = max(1, int(total_layers * ratio))
                cpu_layers = max(0, total_layers - gpu_layers)
                mode = "Smart Hybrid ⚡/💻"
                is_hybrid = True
                summary = (
                    f"Smart CPU Offload: {gpu_layers} layers on GPU, {cpu_layers} layers offloaded to CPU/RAM "
                    f"({safety_floor_gb}GB VRAM permanently protected for desktop apps)."
                )

        return {
            "model_path": str(model_path),
            "size_gb": size_gb,
            "real_free_vram_gb": real_free_gb,
            "safety_floor_gb": safety_floor_gb,
            "usable_budget_gb": usable_budget_gb,
            "kv_cache_gb": kv_cache_gb,
            "total_needed_gb": total_needed_gb,
            "total_layers": total_layers,
            "gpu_layers": gpu_layers,
            "cpu_layers": cpu_layers,
            "mode": mode,
            "is_hybrid": is_hybrid,
            "summary": summary,
        }

    def find_llama_server_binary(self) -> str | None:
        """Locate the Windows llama-server.exe binary."""
        candidates = [
            r"C:\Users\danie\.unsloth\llama.cpp\build\bin\Release\llama-server.exe",
            os.path.expanduser(
                r"~\.unsloth\llama.cpp\build\bin\Release\llama-server.exe"
            ),
            r"C:\llama.cpp\llama-server.exe",
            os.path.join(
                os.environ.get("UNSLOTH_STUDIO_HOME", ""),
                "llama.cpp",
                "build",
                "bin",
                "Release",
                "llama-server.exe",
            ),
        ]
        for c in candidates:
            if c and os.path.exists(c):
                return c
        return None

    def launch_smart_model(
        self,
        model_path: str,
        total_layers: int = 33,
        port: int = 8888,
        n_ctx: int = 4096,
    ) -> tuple[bool, str, dict[str, Any]]:
        """
        Launch llama-server with smart dynamic CPU/GPU offload.
        Prevents VRAM overflow and PCIe thrashing.
        """
        p = Path(model_path)
        if not p.exists():
            return False, f"Model file not found: {model_path}", {}

        binary = self.find_llama_server_binary()
        if not binary:
            return False, "llama-server.exe binary not found on system.", {}

        # 1. Compute smart layer offloading
        offload = self.calculate_smart_offload(
            model_path, total_layers=total_layers, n_ctx=n_ctx
        )
        gpu_layers = offload["gpu_layers"]

        # 2. Stop any existing llama-server process cleanly
        self.unload_all_models()
        time.sleep(0.5)

        # 3. Prepare execution environment and directory
        unsloth_dir = str(Path(binary).parent)
        env = os.environ.copy()
        env["GGML_CUDA_NO_PIN_SHARED"] = "1"
        env["PATH"] = unsloth_dir + ";" + env.get("PATH", "")

        cmd = [
            binary,
            "-m",
            str(model_path),
            "-c",
            str(n_ctx),
            "--port",
            str(port),
            "-ngl",
            str(gpu_layers),
            "-t",
            "4",
            "--flash-attn",
            "on",
        ]

        try:
            import subprocess

            popen_kwargs = dict(cwd=unsloth_dir, env=env)
            if os.name == "nt":
                # Windows: hidden background execution
                popen_kwargs["creationflags"] = 0x08000000
            else:
                # Linux: detach from parent so it survives this process exiting
                popen_kwargs["start_new_session"] = True
            proc = subprocess.Popen(cmd, **popen_kwargs)

            # Record lock
            lock_data = {
                "role": ROLE_MAIN,
                "model": p.name,
                "path": str(model_path),
                "pid": proc.pid,
                "port": port,
                "gpu_layers": gpu_layers,
                "cpu_layers": offload["cpu_layers"],
                "total_layers": total_layers,
                "mode": offload["mode"],
                "timestamp": time.time(),
            }
            with open(self._lock_file(ROLE_MAIN), "w", encoding="utf-8") as f:
                json.dump(lock_data, f, indent=2)

            msg = f"🚀 Loaded {p.name} on :{port} [{offload['mode']}]\n{offload['summary']}"
            return True, msg, offload
        except Exception as e:
            return False, f"Failed to launch llama-server: {e}", offload

    def unload_all_models(self) -> tuple[bool, str]:
        """Safely terminate llama-server and clean locks to free all VRAM."""
        try:
            import subprocess

            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/IM", "llama-server.exe", "/F"],
                    capture_output=True,
                    creationflags=0x08000000,
                )
            else:
                subprocess.run(
                    ["pkill", "-f", "llama-server"], capture_output=True, timeout=3
                )
            for f in self.lock_dir.glob("*.lock"):
                try:
                    f.unlink(missing_ok=True)
                except Exception:
                    pass
            return True, "All models unloaded. VRAM liberated."
        except Exception as e:
            return False, f"Error unloading models: {e}"

    # ═══════════════════════════════════════════════════════════════════
    # LANE SENSING — measure, then explain
    # ═══════════════════════════════════════════════════════════════════
    # Default posture is COLLABORATION: unless pressure is measured, the
    # governor gets out of the way and stays quiet. Two actors doing different
    # work is not a conflict, and a governor that only knows how to refuse will
    # never notice the difference.

    def _psi(self, resource: str) -> dict[str, float]:
        """Kernel pressure-stall averages for cpu/io/memory, in percent."""
        out: dict[str, float] = {}
        try:
            with open(f"/proc/pressure/{resource}", "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.split()
                    if not parts:
                        continue
                    kind = parts[0].rstrip(":")
                    for kv in parts[1:]:
                        if "=" in kv:
                            k, v = kv.split("=", 1)
                            out[f"{kind}_{k}"] = float(v)
        except Exception:
            pass
        return out

    def _mem_available_gb(self) -> float | None:
        """MemAvailable — the honest 'can anything big still fit' number."""
        try:
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("MemAvailable:"):
                        return float(line.split()[1]) / (1024**2)
        except Exception:
            pass
        return None

    def foreign_vram_consumers(self) -> list[dict[str, Any]]:
        """
        Who is holding the GPU, and how much — the question the old governor
        never asked. It only ever asked how much was free, so it could clamp
        itself but could never name the thing that caused the pressure.
        Our own llama-servers are excluded; they are accounted for separately.
        """
        consumers: list[dict[str, Any]] = []
        try:
            import subprocess as _sp

            out = _sp.check_output(
                ["nvidia-smi", "--query-compute-apps=pid,used_memory",
                 "--format=csv,noheader,nounits"],
                timeout=5, text=True,
            )
        except Exception:
            return consumers

        for line in out.strip().splitlines():
            bits = [b.strip() for b in line.split(",")]
            if len(bits) < 2:
                continue
            try:
                pid, mib = int(bits[0]), float(bits[1])
            except ValueError:
                continue
            name = "?"
            try:
                with open(f"/proc/{pid}/cmdline", "rb") as f:
                    raw = f.read().split(b"\0")[0].decode("utf-8", "replace")
                if raw:
                    name = Path(raw).name
            except Exception:
                pass
            consumers.append({"pid": pid, "name": name, "gb": mib / 1024.0})
        return consumers

    def human_idle_s(self) -> float | None:
        """
        Seconds since the human last touched the keyboard/mouse.
        Tries the cheap X11 probe first, then falls back to systemd-logind
        (which works on a bare console with no X at all), then w(1).
        Returns None only when nothing can be measured — and says so rather
        than guessing.
        """
        # 1) X11 / Wayland (xprintidle) — exact milliseconds.
        try:
            import subprocess as _sp

            out = _sp.check_output(["xprintidle"], timeout=3, text=True)
            return float(out.strip()) / 1000.0
        except Exception:
            pass
        # 2) systemd-logind — the X-free path. IdleHint flips to 'yes' once the
        #    session is idle; IdleSinceHintMonotonic is CLOCK_MONOTONIC µs.
        try:
            import subprocess as _sp

            out = _sp.check_output(
                ["loginctl", "show-user", getpass.getuser(),
                 "-p", "IdleHint", "-p", "IdleSinceHintMonotonic"],
                timeout=3, text=True,
            )
            props = dict(
                ln.split("=", 1) for ln in out.strip().splitlines() if "=" in ln
            )
            if props.get("IdleHint", "").strip().lower() != "yes":
                return 0.0  # a session is active -> the human is here
            since_us = int(props.get("IdleSinceHintMonotonic", "0") or "0")
            if since_us <= 0:
                return None
            return max(0.0, time.monotonic() - since_us / 1e6)
        except Exception:
            return None

    def lane_state(self, footprint_gb: float = 0.0) -> dict[str, Any]:
        """
        One survey of the machine, with a verdict and the evidence behind it.
        verdict: 'clear' | 'busy' | 'blocked'
        """
        io = self._psi("io")
        mem = self._psi("memory")
        avail = self._mem_available_gb()
        foreign = [
            c for c in self.foreign_vram_consumers()
            if "llama" not in c["name"].lower()
        ]
        idle = self.human_idle_s()

        reasons: list[str] = []
        code = "clear"

        stall = io.get("some_avg60", 0.0)
        if stall >= LANE_IO_STALL_BLOCK:
            code = "blocked_io"
            reasons.append(f"disk stalled {stall:.0f}% of the last 60s")
        elif stall >= LANE_IO_STALL_WARN:
            code = "busy"
            reasons.append(f"disk stalled {stall:.0f}% of the last 60s")

        hogs = [c for c in foreign if c["gb"] >= LANE_FOREIGN_VRAM_GB]
        if hogs:
            who = ", ".join(f"{c['name']} ({c['gb']:.1f} GB)" for c in hogs)
            if code != "blocked_io":
                code = "blocked_vram"
                reasons.append(f"GPU held by {who}")

        if avail is not None and footprint_gb > 0:
            need = footprint_gb + LANE_HEADROOM_GB
            if avail < need:
                if code == "clear":
                    code = "blocked_ram"
                reasons.append(f"{avail:.1f} GB RAM free, this needs {need:.1f} GB")

        if code == "clear" and idle is not None and idle >= LANE_HUMAN_IDLE_GRACE_S:
            code = "busy"
            reasons.append(f"no input for {idle / 60:.0f} min")

        return {
            "verdict": code,
            "reasons": reasons,
            "io_stall_pct": stall,
            "mem_stall_pct": mem.get("some_avg60", 0.0),
            "mem_available_gb": avail,
            "foreign_vram": foreign,
            "human_idle_s": idle,
            "footprint_gb": footprint_gb,
        }

    def lane_trend(self) -> dict[str, Any]:
        """
        Which way is the lane heading?

        Compares the fast PSI window (avg10) against the slow one (avg300). A
        short window sitting above the long one is pressure building — the only
        moment where acting early is actually possible.
        """
        io = self._psi("io")
        mem = self._psi("memory")
        fast = io.get("some_avg10", 0.0)
        slow = io.get("some_avg300", 0.0)

        ratio = (fast / slow) if slow > 0.01 else (2.0 if fast > 1.0 else 1.0)

        if fast >= LANE_IO_STALL_BLOCK:
            direction, urgency = "storm", "now"
        elif ratio >= 1.8 and fast >= LANE_IO_STALL_WARN:
            direction, urgency = "rising", "soon"
        elif ratio >= 1.4:
            direction, urgency = "rising", "watch"
        elif fast < LANE_IO_STALL_WARN * 0.5:
            direction, urgency = "calm", "none"
        else:
            direction, urgency = "steady", "none"

        # Project when a rising short window would cross the block threshold.
        eta_s = None
        if direction == "rising" and fast > 0 and ratio > 1.0:
            per_s = fast / 600.0  # avg10 growth per second, roughly
            if per_s > 0:
                eta_s = max(0.0, (LANE_IO_STALL_BLOCK - fast) / per_s)

        return {
            "direction": direction,
            "urgency": urgency,
            "io_fast_pct": fast,
            "io_slow_pct": slow,
            "ratio": round(ratio, 2),
            "mem_fast_pct": mem.get("some_avg10", 0.0),
            "eta_s": eta_s,
        }

    def forecast_notice(self) -> dict[str, Any] | None:
        """
        The post-it note. Publish a warning when the lane is heading into
        trouble, scheduled for when it is expected to arrive — so every actor
        gets told while there is still time to act.
        """
        trend = self.lane_trend()
        if trend["urgency"] not in ("now", "soon"):
            return trend

        import time as _t

        eta = trend.get("eta_s")
        not_before = (_t.time() + eta) if eta else None
        minutes = f"about {int(eta / 60)} min" if eta else "shortly"

        body = (
            f"Heads up — the lane is filling. Disk stall is {trend['io_fast_pct']:.0f}% "
            f"and climbing (vs {trend['io_slow_pct']:.0f}% over the last 5 min).\n"
            f"  • expect pressure to peak {minutes}\n"
            f"  • heavy work started now will finish {minutes}\n"
            f"  • finishing early is free; being interrupted is not\n"
            f"  (Nothing has been stopped. Yield only happens between batches.)"
        )

        try:
            from hotline import publish

            publish(
                "lane.forecast",
                {"trend": trend, "eta_s": eta},
                level="urgent" if trend["urgency"] == "now" else "warn",
                actor="vram_guard",
                explain=body,
                not_before=not_before,
                warn_ahead_s=600.0 if eta else 0.0,
            )
        except Exception:
            pass

        self._lane_journal(
            {"verdict": f"forecast:{trend['direction']}",
             "reasons": [f"io {trend['io_fast_pct']:.1f}% rising, eta {minutes}"]},
            "vram_guard", "forecast",
        )
        return trend

    def explain(self, state: dict[str, Any]) -> str:
        """Turn a lane decision into a sentence a human can act on."""
        verdict = state.get("verdict", "clear")
        why = LANE_EXPLAIN.get(verdict, verdict)
        lines = [why]
        for r in state.get("reasons", []):
            lines.append(f"  • {r}")
        lines.append(f"  ({LANE_EXPLAIN['never_preempt']})")
        return "\n".join(lines)

    def _lane_journal(self, state: dict[str, Any], actor: str, action: str) -> None:
        """Durable, greppable record. Survives the IPC port being down."""
        try:
            import datetime as _dt

            LANE_LOG.parent.mkdir(parents=True, exist_ok=True)
            with open(LANE_LOG, "a", encoding="utf-8") as f:
                f.write(
                    f"{_dt.datetime.now().isoformat(timespec='seconds')} "
                    f"[{action}] actor={actor} verdict={state.get('verdict')} "
                    f"io={state.get('io_stall_pct', 0):.1f}% "
                    f"mem_avail={state.get('mem_available_gb')} "
                    f"reasons={'; '.join(state.get('reasons', [])) or '-'}\n"
                )
        except Exception:
            pass

    def announce(self, state: dict[str, Any], eta_s: float | None = None) -> None:
        """
        Tell a human, in words, what is happening and roughly for how long.
        This is the whole point: a slow machine that explains itself is an
        inconvenience; one that does not is a mystery.
        """
        body = self.explain(state)
        if eta_s:
            body += f"\n  Expected to need the lane for about {eta_s / 60:.0f} min."
        title = "FoveAI — resource lane"
        try:
            import subprocess as _sp

            _sp.run(["notify-send", title, body], timeout=3, capture_output=True)
        except Exception:
            pass
        level = "urgent" if state.get("verdict", "").startswith("blocked") else "notice"
        structured = self._explain_block(state, eta_s)
        try:
            from hotline import render_explanation

            body = body + "\n\n" + render_explanation(structured)
        except Exception:
            pass
        self._broadcast_silent_ipc(
            "lane.notice",
            {"verdict": state.get("verdict"), "body": body, "level": level,
             "reasons": state.get("reasons", []), "explanation": structured},
        )

    def _explain_block(
        self, state: dict[str, Any], eta_s: float | None = None
    ) -> dict[str, Any]:
        """
        Build a COMPLETE four-component explanation for a refusal.

        Cause / category / horizon / implication — all four, every time. The
        category is what lets the reader respond correctly: "contention" is
        something to wait out, "malfunction" is something to report, and
        "illness" is something to be gentle with. Same obstruction, opposite
        behaviour, and the category is what picks it.

        Where we genuinely do not know (e.g. an ETA we cannot estimate), we say
        'unknown' rather than omitting the field. A stated unknown is honest and
        complete; silence about duration is opaque, and opacity is what turns
        a blockage into frustration.
        """
        verdict = str(state.get("verdict", "clear"))
        reasons = state.get("reasons", []) or []

        if verdict.startswith("blocked_io"):
            category = "contention — many things are competing for the disk"
            cause = "tasks are spending real time stalled on I/O"
            implication = "let current work finish, then retry — starting now only adds to the queue"
        elif verdict.startswith("blocked_vram"):
            hogs = ", ".join(
                f"{c['name']} ({c['gb']:.1f} GB)" for c in state.get("foreign_vram", [])
                if c.get("gb", 0) >= LANE_FOREIGN_VRAM_GB
            )
            category = "contention — another program is using the GPU"
            cause = f"the GPU is already held by {hogs or 'another process'}"
            implication = "close or minimise that program, or let the model run on CPU instead"
        elif verdict.startswith("blocked_ram"):
            avail = state.get("mem_available_gb")
            need = (state.get("footprint_gb") or 0) + LANE_HEADROOM_GB
            category = "contention — system memory is spoken for"
            cause = f"only {avail:.1f} GB of RAM is free and this needs {need:.1f} GB"
            implication = "close something memory-hungry, or wait for it to finish"
        else:
            category = "informational"
            cause = "; ".join(reasons) or "no specific pressure detected"
            implication = "nothing to do — this is only so you know"

        horizon = (
            f"about {int(eta_s / 60)} min" if eta_s
            else ("unknown — flagged rather than guessed" if verdict.startswith("blocked")
                  else "no duration, this is not a block")
        )

        return {
            "cause": cause,
            "category": category,
            "horizon": horizon,
            "implication": implication,
        }

    def request_lane(
        self, actor: str, footprint_gb: float, eta_s: float | None = None
    ) -> tuple[bool, dict[str, Any]]:
        """
        Collaboration-first gate.

        clear  -> proceed, silently (unless heavy: then announce)
        busy   -> proceed, announced
        blocked-> refuse, with the reason and the evidence
        """
        # ── Gaming / Exclusive Model Guardrail: block model loading when a
        # game or active streaming session owns the GPU. Measured, named, and
        # takes precedence over the generic lane sensors below.
        state = self.lane_state(footprint_gb)
        gaming_verdict = self._check_gaming_ports()
        if gaming_verdict is not None:
            state["verdict"] = gaming_verdict["verdict"]
            state["reasons"] = gaming_verdict["reasons"]
            state["foreign_vram"] = gaming_verdict.get("foreign_vram", [])

        heavy = footprint_gb >= LANE_ANNOUNCE_MIN_GB
        # Verdicts are blocked_ram / blocked_vram / blocked_io — comparing
        # against the bare string "blocked" would grant the start we exist to
        # prevent. Prefix-match instead.
        granted = not str(state["verdict"]).startswith("blocked")

        # Silence is only appropriate when there is genuinely nothing to say:
        # small work, lane clear, nothing pending. A REFUSAL always speaks —
        # an unexplained "no" is the exact failure this whole system exists to
        # prevent, so it must never be the quiet path.
        if not granted or heavy or state["verdict"] == "busy":
            self.announce(state, eta_s)
        self._lane_journal(state, actor, "grant" if granted else "refuse")
        return granted, state

    def _registered_pids(self) -> set[int]:
        """PIDs we have loaded models under — our own GPU users, never a game."""
        pids: set[int] = set()
        for lf in self.lock_dir.glob("*.lock"):
            try:
                with open(lf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("pid"):
                    pids.add(int(data["pid"]))
            except Exception:
                pass
        return pids

    def _gpu_processes(self) -> list[dict[str, Any]]:
        """Every process on the GPU — graphics (G) AND compute (C) — with VRAM.

        The compute-apps query alone is not enough: a game is a *graphics*
        process and never appears there. We parse the full nvidia-smi table so
        a running game is actually seen. Falls back to the compute-apps CSV if
        the table cannot be parsed.
        """
        procs: list[dict[str, Any]] = []
        try:
            import re as _re
            import subprocess as _sp

            out = _sp.check_output(
                ["nvidia-smi"], timeout=6, text=True, stderr=_sp.DEVNULL
            )
            row = _re.compile(
                r"\|\s*\d+\s+\S+\s+\S+\s+(\d+)\s+([CG][CG+]*)\s+(.+?)\s+(\d+)\s*MiB\s*\|"
            )
            for line in out.splitlines():
                m = row.search(line)
                if m:
                    procs.append({
                        "pid": int(m.group(1)),
                        "type": m.group(2),
                        "name": Path(m.group(3).strip()).name or m.group(3).strip(),
                        "mib": int(m.group(4)),
                    })
        except Exception:
            procs = []

        if procs:
            return procs

        # Fallback: compute-only CSV.
        try:
            import subprocess as _sp

            out = _sp.check_output(
                ["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory",
                 "--format=csv,noheader,nounits"],
                timeout=5, text=True,
            )
            for line in out.strip().splitlines():
                bits = [b.strip() for b in line.split(",")]
                if len(bits) < 3:
                    continue
                try:
                    procs.append({
                        "pid": int(bits[0]),
                        "type": "C",
                        "name": Path(bits[1]).name or bits[1],
                        "mib": int(float(bits[2])),
                    })
                except (ValueError, IndexError):
                    continue
        except Exception:
            pass
        return procs

    def _check_gaming_ports(self) -> dict | None:
        """
        Detect a game / exclusive GPU session BEFORE loading the main model.

        Trigger: a foreign GPU process (graphics or compute) holding at least
        FOVEAI_GAMING_VRAM_GB of VRAM. Measured, not guessed — a game always
        holds gigabytes; a listening xrdp/sunshine port holds nothing and must
        not trip the gate. Our own llama-servers (by name and by registered
        lock PID) are never treated as foreign, so reloading the main model
        never mistakes itself for a blocker.

        Returns a verdict dict when the load should be refused, else None.
        """
        if GAMING_OVERLOAD_OVERRIDE:
            return None

        ours = self._registered_pids()
        ours.add(os.getpid())

        def known_name(proc_name: str) -> str | None:
            low = proc_name.lower()
            for info in GAMING_PORTS.values():
                hint = str(info.get("proc", "")).lower()
                if hint and hint in low:
                    return info["name"]
            return None

        hogs: list[dict[str, Any]] = []
        for p in self._gpu_processes():
            if p["pid"] in ours:
                continue
            if "llama-server" in p["name"].lower():
                continue  # ours — accounted for by the lock, not a foreign game
            if p["mib"] / 1024.0 >= GAMING_VRAM_GB:
                hogs.append(p)

        if not hogs:
            return None

        reasons = []
        foreign_vram = []
        for p in hogs:
            label = known_name(p["name"]) or p["name"]
            reasons.append(
                f"{label} is holding {p['mib'] / 1024:.1f} GB of GPU VRAM "
                f"(PID {p['pid']})"
            )
            foreign_vram.append(
                {"name": label, "pid": p["pid"], "gb": p["mib"] / 1024.0}
            )

        return {
            "granted": False,
            "verdict": "blocked_vram",
            "reasons": reasons,
            "foreign_vram": foreign_vram,
        }

    def gaming_gate(self) -> dict[str, Any] | None:
        """Public accessor for loaders that start their own engine (e.g. the
        Taskbar's direct llama-server Popen). Returns None when the GPU is free
        for a main-model load, else a verdict dict naming what holds it — the
        caller should refuse and surface verdict['reasons'] to the human."""
        return self._check_gaming_ports()


# Global instance
guardrail = VRAMGuardrail()
