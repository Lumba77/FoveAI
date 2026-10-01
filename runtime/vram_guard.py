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

ROLE_MAIN = "main"
ROLE_HELPER = "helper"


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
        try:
            from gguf import GGUFReader

            r = GGUFReader(model_path)

            def meta(key: str):
                f = r.fields.get(key)
                if f is None:
                    return None
                v = f.parts[f.data[0]]
                if hasattr(v, "tolist"):
                    v = v.tolist()
                if isinstance(v, (list, tuple)) and len(v) == 1:
                    v = v[0]
                return v

            arch_field = meta("general.architecture")
            if arch_field is None:
                return None
            arch = (
                bytes(arch_field).decode("utf-8", "replace")
                if not isinstance(arch_field, str)
                else arch_field
            )

            blocks = meta(f"{arch}.block_count")
            if not blocks:
                return None
            blocks = int(blocks)
            interval = int(meta(f"{arch}.full_attention_interval") or 0)
            attn_layers = max(1, blocks // interval) if interval > 0 else blocks

            kv_heads = int(meta(f"{arch}.attention.head_count_kv") or 1)
            key_len = int(
                meta(f"{arch}.attention.key_length")
                or meta(f"{arch}.embedding_length")
                or 0
            )
            val_len = int(meta(f"{arch}.attention.value_length") or key_len)
            if not key_len:
                return None

            # f16 K+V per token across KV-keeping layers
            kv_bytes = attn_layers * (key_len + val_len) * kv_heads * 2

            # Hybrid SSM state: recurrent layers carry a fixed per-sequence
            # state (~inner_size * state_size * 2B each). Model as a flat
            # per-token allowance; it over-reserves slightly, safely.
            ssm_state = meta(f"{arch}.ssm.state_size")
            ssm_inner = meta(f"{arch}.ssm.inner_size")
            ssm_bytes = 0.0
            if ssm_state and ssm_inner:
                ssm_layers = blocks - attn_layers
                ssm_bytes = (
                    float(ssm_layers) * float(ssm_state) * float(ssm_inner) * 2.0
                )
                # Fixed state, not per-token: amortize over ctx in caller via
                # a pseudo per-token bump of ~10% of KV.
                kv_bytes += ssm_bytes / max(1.0, 8192.0)

            return float(kv_bytes)
        except Exception:
            return None

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
        """Silently notify other services/programs via local Port 8400 IPC."""
        import urllib.request

        try:
            data = json.dumps({"event": event_type, "payload": payload}).encode("utf-8")
            req = urllib.request.Request(
                "http://127.0.0.1:8400/v1/internal/ipc",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=0.2):
                pass
        except Exception:
            # Silent notification — does not raise if port 8400 is not currently running
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
        kv_cache_gb = self.estimate_kv_cache_gb(n_ctx, total_layers)
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


# Global instance
guardrail = VRAMGuardrail()
