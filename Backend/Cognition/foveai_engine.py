import os
import re
import sys
import math
import inspect
import logging
import time
from contextlib import contextmanager
from typing import Any, Dict, Optional

import jinja2
import numpy as np
from jinja2.sandbox import ImmutableSandboxedEnvironment

# Provide defaults so flake8 can resolve these names even if imports fail
_TORCH_AVAILABLE = False
try:
    import torch
    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False

# Conditional imports
try:
    from llama_cpp import Llama
    GGUF_AVAILABLE = True
except ImportError:
    GGUF_AVAILABLE = False
    Llama = None  # type: ignore

try:
    from llama_cpp.llama_chat_format import Llava15ChatHandler
except ImportError:
    Llava15ChatHandler = None


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name, "").strip().lower()
    if not val:
        return default
    return val in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return int(default)
    try:
        return int(raw)
    except Exception:
        return int(default)


def _hf_pretrained_dtype_kw(model_cls: Any) -> Dict[str, Any]:
    """Prefer ``dtype`` over deprecated ``torch_dtype`` when ``from_pretrained`` supports it."""
    if not _TORCH_AVAILABLE:
        return {}
    dt = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    try:
        sig = inspect.signature(model_cls.from_pretrained)
        if "dtype" in sig.parameters:
            return {"dtype": dt}
    except (TypeError, ValueError, AttributeError):
        pass
    return {"torch_dtype": dt}


def _model_thinking_enabled() -> bool:
    """Qwen-style CoT / redacted_thinking blocks; set FoveAI_MODEL_THINKING=0 to disable."""
    return _env_bool("FoveAI_MODEL_THINKING", True)


# Strip model-emitted reasoning wrappers when FoveAI_MODEL_THINKING is off (non-stream paths).
_THINKING_BLOCK_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"<think>[\s\S]*?</think>", re.IGNORECASE),
    re.compile(r"<thinking>[\s\S]*?</thinking>", re.IGNORECASE),
    re.compile(r"<thought>[\s\S]*?</thought>", re.IGNORECASE),
)


def _strip_model_thinking_text(text: str) -> str:
    if _model_thinking_enabled() or not text:
        return text
    out = text
    for rx in _THINKING_BLOCK_RES:
        out = rx.sub("", out)
    return out.strip()


def _default_qwen_chat_template_path() -> str:
    """Convention: ship or mount `backend/Cognition/qwen.j2` next to this module."""
    return os.path.join(os.path.dirname(__file__), "qwen.j2")


@contextmanager
def _lenient_jinja_chat_formatter_for_llama_init(lenient: bool):
    """
    llama-cpp-python registers every `tokenizer.chat_template*` from GGUF via Jinja2ChatFormatter.
    Some upstream templates use Jinja features not enabled in the sandbox, which aborts `Llama()`.
    When lenient=True, failed template compiles are replaced with an inert template so init can proceed.
    """
    if not lenient:
        yield
        return
    import llama_cpp.llama_chat_format as lcf

    real_cls = lcf.Jinja2ChatFormatter

    class _LenientJinja2ChatFormatter(real_cls):  # type: ignore[misc, valid-type]
        def __init__(
            self,
            template: str,
            eos_token: str,
            bos_token: str,
            add_generation_prompt: bool = True,
            stop_token_ids: Optional[list[int]] = None,
        ):
            try:
                super().__init__(
                    template,
                    eos_token,
                    bos_token,
                    add_generation_prompt=add_generation_prompt,
                    stop_token_ids=stop_token_ids,
                )
            except Exception as e:
                logging.warning(
                    "FoveAI: skipping incompatible GGUF chat template (metadata). Error: %s",
                    e,
                )
                self.template = ""
                self.eos_token = eos_token
                self.bos_token = bos_token
                self.add_generation_prompt = add_generation_prompt
                self.stop_token_ids = (
                    set(stop_token_ids) if stop_token_ids is not None else None
                )
                self._environment = ImmutableSandboxedEnvironment(
                    loader=jinja2.BaseLoader(),
                    trim_blocks=True,
                    lstrip_blocks=True,
                ).from_string("")

    lcf.Jinja2ChatFormatter = _LenientJinja2ChatFormatter  # type: ignore[assignment]
    try:
        yield
    finally:
        lcf.Jinja2ChatFormatter = real_cls  # type: ignore[assignment]

HF_AVAILABLE = False
try:
    from transformers import AutoTokenizer, AutoProcessor, AutoModelForCausalLM
    HF_AVAILABLE = True
except ImportError:
    AutoTokenizer = None
    AutoProcessor = None
    AutoModelForCausalLM = None

try:
    from transformers import AutoModelForVision2Seq
except ImportError:
    AutoModelForVision2Seq = None

class LumaxEngine:
    def __init__(self, model_path: str):
        self.model_path = model_path
        self.model_name = os.path.basename(model_path.rstrip("/"))
        self.engine_type = self._detect_type()
        self.model = None
        self.tokenizer = None
        self.processor = None
        # Set in load() when FoveAI_GGUF_NATIVE_VISION=1 and mmproj + Llava15ChatHandler init succeeds.
        self.gguf_multimodal_ready = False
        self.mmproj_path: Optional[str] = None
        # GGUF context window (supports long-context models if VRAM permits).
        # Default matches docker-compose foveai_soul (8192). Older default 32768 surprised users when
        # MindCore+memories exceeded n_ctx — env still wins when set (e.g. .env / compose).
        # Unrelated: backend/Memory/config.json "max_position_embeddings" is HF metadata, not read here.
        try:
            ctx_cap = int(os.getenv("FoveAI_LOCAL_N_CTX_MAX", "65536") or "65536")
        except Exception:
            ctx_cap = 65536
            
        try:
            self.n_gpu_layers = int(os.getenv("FoveAI_GGUF_N_GPU_LAYERS", "99") or "99")
        except Exception:
            self.n_gpu_layers = 99
            
        self.gguf_n_ctx_max = max(4096, min(ctx_cap, 65536))
        try:
            ctx_raw = int(os.getenv("FoveAI_LOCAL_N_CTX", "8192") or "8192")
        except Exception:
            ctx_raw = 8192
        self.gguf_n_ctx = max(4096, min(ctx_raw, self.gguf_n_ctx_max))
        # Initial n_ctx (also the default minimum for adaptive shrink unless FoveAI_ADAPTIVE_N_CTX_FLOOR is set).
        self.gguf_n_ctx_baseline: int = self.gguf_n_ctx
        cpu_count = max(1, (os.cpu_count() or 1))
        # Keep local GGUF from saturating every host thread by default.
        self.gguf_n_threads = max(1, min(_env_int("FoveAI_LOCAL_N_THREADS", min(4, cpu_count)), cpu_count))
        self.gguf_n_threads_batch = max(
            1,
            min(_env_int("FoveAI_LOCAL_N_THREADS_BATCH", self.gguf_n_threads), cpu_count),
        )
        # Optional lower bound for shrink (e.g. start FoveAI_LOCAL_N_CTX=32768 but allow urgent shrink toward 4096).
        self.gguf_adaptive_shrink_floor: int = self._compute_adaptive_shrink_floor()
        # Adaptive n_ctx: EMA of (prompt + reserve) need; grow/shrink reload throttles.
        self._adaptive_ema_need: float = 0.0
        self._adaptive_last_any_reload_ts: float = 0.0
        self._adaptive_last_grow_ts: float = 0.0
        self._adaptive_last_shrink_ts: float = 0.0

        # Standard Settings (Optimized for Qwen 3.5 4B)
        # NOTE: presence_penalty was 1.5 (pathologically high for small models — caused
        # word-avoidance loops). Lowered to 0.8; repeat_penalty raised to 1.15.
        self.gen_config = {
            "temperature": 0.7,
            "top_p": 0.8,
            "top_k": 20,
            "min_p": 0.0,
            "presence_penalty": 0.8,
            "frequency_penalty": 0.5,
            "repetition_penalty": 1.15,
            "repeat_last_n": 128,
            "do_sample": True
        }
        
        logging.info(f"LumaxEngine: Init {self.engine_type} for {self.model_name}")
        logging.info(
            "LumaxEngine: GGUF perf threads n_threads=%d n_threads_batch=%d",
            self.gguf_n_threads,
            self.gguf_n_threads_batch,
        )

    def _gguf_perf_kwargs(self) -> Dict[str, Any]:
        return {
            "n_threads": self.gguf_n_threads,
            "n_threads_batch": self.gguf_n_threads_batch,
        }

    def _compute_adaptive_shrink_floor(self) -> int:
        raw = os.getenv("FoveAI_ADAPTIVE_N_CTX_FLOOR", "").strip()
        if not raw:
            return self.gguf_n_ctx_baseline
        try:
            v = int(raw)
        except Exception:
            return self.gguf_n_ctx_baseline
        return max(4096, min(v, self.gguf_n_ctx_max))

    def _gguf_chat_format(self) -> Optional[str]:
        """
        Preset llama-cpp-python chat formatter (e.g. ``qwen``) — avoids the GGUF metadata Jinja path
        for *completions* when no external template is used.

        If ``backend/Cognition/qwen.j2`` (or ``FoveAI_GGUF_CHAT_TEMPLATE_PATH``) is present, the engine
        prefers a ``chat_handler`` built from that file instead; ``FoveAI_GGUF_CHAT_FORMAT`` is then
        only used when no template file is available.
        """
        v = os.getenv("FoveAI_GGUF_CHAT_FORMAT", "").strip()
        return v or None

    def _read_external_chat_template_text(self) -> Optional[str]:
        """Load optional Jinja chat template from disk (Qwen / tool-use aware templates)."""
        p = os.getenv("FoveAI_GGUF_CHAT_TEMPLATE_PATH", "").strip()
        if not p:
            p = _default_qwen_chat_template_path()
        if not p or not os.path.isfile(p):
            return None
        try:
            with open(p, "r", encoding="utf-8-sig") as f:
                return f.read()
        except OSError as e:
            logging.warning("LumaxEngine: could not read chat template %r: %s", p, e)
            return None

    def _gguf_chat_format_kwargs_only(self) -> Dict[str, Any]:
        cf = self._gguf_chat_format()
        if cf:
            return {"chat_format": cf}
        return {}

    def _gguf_chat_kwargs_text_only(self, template_text: Optional[str]) -> Dict[str, Any]:
        """Extra kwargs for ``Llama()`` on text-only GGUF loads (custom Jinja file or preset format)."""
        if template_text and GGUF_AVAILABLE:
            import llama_cpp.llama_chat_format as lcf

            eos = os.getenv("FoveAI_GGUF_CHAT_TEMPLATE_EOS_TOKEN", "<|im_end|>").strip()
            bos = os.getenv("FoveAI_GGUF_CHAT_TEMPLATE_BOS_TOKEN", "").strip()
            try:
                handler = lcf.Jinja2ChatFormatter(
                    template=template_text,
                    eos_token=eos,
                    bos_token=bos,
                    add_generation_prompt=_model_thinking_enabled(),
                ).to_chat_handler()
            except Exception as e:
                logging.error("LumaxEngine: custom chat template failed to compile: %s", e)
                return self._gguf_chat_format_kwargs_only()
            return {"chat_handler": handler, "chat_format": None}
        return self._gguf_chat_format_kwargs_only()

    def _detect_type(self):
        m_name = self.model_name.lower()
        
        # Check for GGUF files in the path (direct or inside dir)
        if self.model_path.endswith(".gguf"): return "GGUF"
        if os.path.isdir(self.model_path):
            for f in os.listdir(self.model_path):
                if f.endswith(".gguf"): return "GGUF"
            
            if "vl" in m_name: return "QWEN_VL"
            if "dflash" in m_name: return "DFLASH"
            if "gptq" in m_name or "awq" in m_name: return "QUANTIZED_HF"
            return "TRANSFORMERS"
        return "UNKNOWN"

    def _resolve_mmproj_path(self, model_file: str) -> Optional[str]:
        """mmproj path: FoveAI_MMPROJ_PATH, or *mmproj*.gguf next to weights / in model dir."""
        env_p = os.getenv("FoveAI_MMPROJ_PATH", "").strip()
        if env_p and os.path.isfile(env_p):
            return env_p
        search_dirs = []
        if os.path.isdir(self.model_path):
            search_dirs.append(self.model_path)
        else:
            parent = os.path.dirname(os.path.abspath(model_file))
            if os.path.isdir(parent):
                search_dirs.append(parent)
        for d in search_dirs:
            try:
                names = sorted(os.listdir(d))
            except OSError:
                continue
            for f in names:
                if f.endswith(".gguf") and "mmproj" in f.lower():
                    return os.path.join(d, f)
        return None

    def _manifest_gguf_llama(self) -> bool:
        """Instantiate GGUF Llama with current self.gguf_n_ctx (load or adaptive reload)."""
        if not GGUF_AVAILABLE or Llama is None:
            return False
        self.gguf_multimodal_ready = False
        self.mmproj_path = None
        model_file = self.model_path
        if os.path.isdir(self.model_path):
            non_mm = sorted(
                f
                for f in os.listdir(self.model_path)
                if f.endswith(".gguf") and "mmproj" not in f.lower()
            )
            if non_mm:
                model_file = os.path.join(self.model_path, non_mm[0])

        mmproj_file = self._resolve_mmproj_path(model_file)
        self.mmproj_path = mmproj_file
        native_vision = _env_bool("FoveAI_GGUF_NATIVE_VISION", False)
        use_multimodal = bool(
            mmproj_file
            and native_vision
            and Llava15ChatHandler is not None
        )

        tpl_text = self._read_external_chat_template_text()
        # Build file-based handler *before* lenient monkeypatch so user `qwen.j2` uses stock Jinja2ChatFormatter.
        text_chat_kw = self._gguf_chat_kwargs_text_only(tpl_text)
        lenient = _env_bool("FoveAI_GGUF_LENIENT_CHAT_TEMPLATE", tpl_text is not None)
        vl_extra_kw = self._gguf_chat_format_kwargs_only()

        logging.info(f"LumaxEngine: Manifesting GGUF Soul from {model_file}...")
        logging.info("LumaxEngine: GGUF n_ctx=%d (max=%d)", self.gguf_n_ctx, self.gguf_n_ctx_max)
        perf_kw = self._gguf_perf_kwargs()
        use_flash_attn = os.getenv("FOVEAI_FLASH_ATTN", "1") == "1"
        with _lenient_jinja_chat_formatter_for_llama_init(lenient):
            if use_multimodal:
                logging.info(
                    "LumaxEngine: Native VL (experimental) — mmproj=%s, handler=Llava15ChatHandler",
                    mmproj_file,
                )
                try:
                    chat_handler = Llava15ChatHandler(clip_model_path=mmproj_file)  # type: ignore[misc]
                    self.model = Llama(
                        model_path=model_file,
                        chat_handler=chat_handler,
                        n_ctx=self.gguf_n_ctx,
                        n_gpu_layers=self.n_gpu_layers,
                        flash_attn=use_flash_attn,
                        embedding=True,
                        **vl_extra_kw,
                        **perf_kw,
                    )

                    self.gguf_multimodal_ready = True
                except Exception as mm_ex:
                    logging.warning(
                        "LumaxEngine: Native VL init failed (%s); loading text-only GGUF.",
                        mm_ex,
                    )
                    try:
                        self.model = Llama(
                            model_path=model_file,
                            n_ctx=self.gguf_n_ctx,
                            n_gpu_layers=self.n_gpu_layers,
                            flash_attn=use_flash_attn,
                            embedding=True,
                            **text_chat_kw,
                            **perf_kw,
                        )
                    except Exception as fallback_ex:
                        logging.error("LumaxEngine: Fallback text-only GGUF init failed: %s", fallback_ex)
                        self.model = None
                        return False

            else:
                if mmproj_file and not native_vision:
                    logging.info(
                        "LumaxEngine: mmproj found at %s but FoveAI_GGUF_NATIVE_VISION is off — text-only load.",
                        mmproj_file,
                    )
                try:
                    self.model = Llama(
                        model_path=model_file,
                        n_ctx=self.gguf_n_ctx,
                        n_gpu_layers=self.n_gpu_layers,
                        flash_attn=use_flash_attn,
                        embedding=True,
                        **text_chat_kw,
                        **perf_kw,
                    )
                except Exception as ex:
                    logging.error("LumaxEngine: Failed to manifest GGUF Soul: %s", ex)
                    self.model = None
                    return False

        logging.info("LumaxEngine: GGUF Soul Manifested.")
        return True

    def _gpu_free_mem_ratio(self) -> Optional[float]:
        """CUDA free / total if torch sees a GPU; else None (CPU-only — VRAM shrink disabled)."""
        if not _TORCH_AVAILABLE:
            return None
        try:
            if torch.cuda.is_available():
                free_b, total_b = torch.cuda.mem_get_info()
                if total_b and total_b > 0:
                    return float(free_b) / float(total_b)
        except Exception as ex:
            logging.debug("LumaxEngine: GPU mem probe skipped: %s", ex)
        return None

    def _adaptive_apply_n_ctx(self, new_ctx: int, reason: str) -> bool:
        """Reload GGUF at new_ctx (grow or shrink). On failure restores previous n_ctx."""
        new_ctx = max(4096, min(int(new_ctx), self.gguf_n_ctx_max))
        if new_ctx == self.gguf_n_ctx:
            return True
        old_ctx = self.gguf_n_ctx
        logging.info(
            "LumaxEngine: adaptive n_ctx %s → %d (was %d)",
            reason,
            new_ctx,
            old_ctx,
        )
        self.gguf_n_ctx = new_ctx
        try:
            if self.model:
                del self.model
                self.model = None
            if not self._manifest_gguf_llama():
                raise RuntimeError("_manifest_gguf_llama returned False")
            self._adaptive_last_any_reload_ts = time.time()
            return True
        except Exception as e:
            logging.error("LumaxEngine: adaptive n_ctx reload failed: %s", e, exc_info=True)
            self.gguf_n_ctx = old_ctx
            try:
                if self.model:
                    del self.model
                    self.model = None
                self._manifest_gguf_llama()
            except Exception as e2:
                logging.error("LumaxEngine: adaptive n_ctx restore failed: %s", e2, exc_info=True)
            return False

    def ensure_gguf_context_for_prompt(
        self, prompt: str, max_tokens: int, extra_token_slots: int = 0
    ) -> None:
        """
        Adaptive GGUF n_ctx (reload): grow when prompt+gen exceeds window; shrink when VRAM is tight
        or when EMA need stays well below current (lazy).

        FoveAI_ADAPTIVE_N_CTX=1 — master switch.
        FoveAI_ADAPTIVE_N_CTX_SHRINK=1 — bidirectional (default on); set 0 for grow-only.
        FoveAI_ADAPTIVE_N_CTX_FLOOR — optional minimum n_ctx after shrink (default: same as initial
        FoveAI_LOCAL_N_CTX). Set lower than initial to allow “start high, shrink under VRAM”
        (e.g. FoveAI_LOCAL_N_CTX=32768 and FoveAI_ADAPTIVE_N_CTX_FLOOR=4096).
        Grow: FoveAI_ADAPTIVE_N_CTX_COOLDOWN_SEC, FoveAI_LOCAL_N_CTX_MAX.
        Shrink lazy: FoveAI_ADAPTIVE_N_CTX_SHRINK_COOLDOWN_SEC, FoveAI_ADAPTIVE_SHRINK_EMA_*.
        Shrink urgent (low free VRAM): FoveAI_ADAPTIVE_SHRINK_URGENT_FREE_RATIO, *_CRITICAL_*.
        """
        if self.engine_type != "GGUF" or not self.model or not prompt:
            return
        if not _env_bool("FoveAI_ADAPTIVE_N_CTX", False):
            return

        now = time.time()
        try:
            min_reload_gap = float(os.getenv("FoveAI_ADAPTIVE_N_CTX_MIN_RELOAD_SEC", "1.5") or "1.5")
        except Exception:
            min_reload_gap = 1.5

        reserve = max(96, min(768, max_tokens + 64))
        try:
            ids = self.model.tokenize(prompt.encode("utf-8"))
            n = len(ids) + max(0, int(extra_token_slots))
        except Exception as ex:
            logging.debug("LumaxEngine: adaptive n_ctx tokenize skipped: %s", ex)
            return
        need = n + reserve

        try:
            alpha = float(os.getenv("FoveAI_ADAPTIVE_SHRINK_EMA_ALPHA", "0.07") or "0.07")
        except Exception:
            alpha = 0.07
        alpha = min(0.5, max(0.01, alpha))
        if self._adaptive_ema_need <= 0:
            self._adaptive_ema_need = float(need)
        else:
            self._adaptive_ema_need = (1.0 - alpha) * self._adaptive_ema_need + alpha * float(need)

        try:
            step = int(os.getenv("FoveAI_ADAPTIVE_N_CTX_STEP", "2048") or "2048")
        except Exception:
            step = 2048
        step = max(256, step)

        baseline = self.gguf_n_ctx_baseline
        shrink_floor = self.gguf_adaptive_shrink_floor
        try:
            margin = int(os.getenv("FoveAI_ADAPTIVE_SHRINK_MARGIN_TOKENS", "768") or "768")
        except Exception:
            margin = 768
        try:
            headroom = float(os.getenv("FoveAI_ADAPTIVE_SHRINK_EMA_HEADROOM", "1.2") or "1.2")
        except Exception:
            headroom = 1.2
        raw_safe = self._adaptive_ema_need * headroom + float(margin)
        safe_min = int(math.ceil(raw_safe / float(step)) * float(step))
        safe_min = max(shrink_floor, min(safe_min, self.gguf_n_ctx_max))

        try:
            critical_thr = float(os.getenv("FoveAI_ADAPTIVE_SHRINK_CRITICAL_FREE_RATIO", "0.05") or "0.05")
        except Exception:
            critical_thr = 0.05
        free_ratio = self._gpu_free_mem_ratio()

        def can_reload() -> bool:
            gap = now - self._adaptive_last_any_reload_ts
            if self._adaptive_last_any_reload_ts <= 0 or gap >= min_reload_gap:
                return True
            if free_ratio is not None and free_ratio < critical_thr:
                return True
            return False

        # --- Grow when this turn does not fit ---
        if need > self.gguf_n_ctx:
            try:
                grow_cd = float(os.getenv("FoveAI_ADAPTIVE_N_CTX_COOLDOWN_SEC", "8") or "8")
            except Exception:
                grow_cd = 8.0
            if self._adaptive_last_grow_ts > 0 and (now - self._adaptive_last_grow_ts) < grow_cd:
                return
            if not can_reload():
                return
            target = min(self.gguf_n_ctx_max, need)
            target = int(((target + step - 1) // step) * step)
            target = min(target, self.gguf_n_ctx_max)
            if target <= self.gguf_n_ctx:
                return
            logging.info(
                "LumaxEngine: adaptive n_ctx grow prompt≈%d + reserve=%d → need %d > n_ctx=%d",
                n,
                reserve,
                need,
                self.gguf_n_ctx,
            )
            if self._adaptive_apply_n_ctx(target, "grow"):
                self._adaptive_last_grow_ts = now
            return

        if not _env_bool("FoveAI_ADAPTIVE_N_CTX_SHRINK", True):
            return
        if self.gguf_n_ctx <= shrink_floor:
            return

        try:
            urgent_thr = float(os.getenv("FoveAI_ADAPTIVE_SHRINK_URGENT_FREE_RATIO", "0.09") or "0.09")
        except Exception:
            urgent_thr = 0.09

        urgent = free_ratio is not None and free_ratio < urgent_thr
        try:
            urgent_cd = float(os.getenv("FoveAI_ADAPTIVE_SHRINK_URGENT_COOLDOWN_SEC", "4") or "4")
        except Exception:
            urgent_cd = 4.0
        try:
            lazy_cd = float(os.getenv("FoveAI_ADAPTIVE_N_CTX_SHRINK_COOLDOWN_SEC", "60") or "60")
        except Exception:
            lazy_cd = 60.0

        new_ctx: Optional[int] = None
        tag = ""

        if urgent:
            if self._adaptive_last_shrink_ts > 0 and (now - self._adaptive_last_shrink_ts) < urgent_cd:
                return
            if not can_reload():
                return
            target = max(shrink_floor, min(self.gguf_n_ctx - step, safe_min))
            if free_ratio is not None and free_ratio < critical_thr:
                target = max(shrink_floor, min(target, self.gguf_n_ctx // 2))
            if target < self.gguf_n_ctx:
                new_ctx = target
                tag = "shrink_vram_urgent"
        else:
            if safe_min >= self.gguf_n_ctx - step:
                return
            if self._adaptive_last_shrink_ts > 0 and (now - self._adaptive_last_shrink_ts) < lazy_cd:
                return
            if not can_reload():
                return
            target = max(shrink_floor, min(self.gguf_n_ctx - step, safe_min))
            if target < self.gguf_n_ctx:
                new_ctx = target
                tag = "shrink_lazy_ema"

        if new_ctx is None:
            return
        if self._adaptive_apply_n_ctx(new_ctx, tag):
            self._adaptive_last_shrink_ts = now

    def load(self):
        try:
            if self.engine_type == "GGUF" and GGUF_AVAILABLE:
                return self._manifest_gguf_llama()
            
            elif self.engine_type == "QWEN_VL" or self.engine_type == "QUANTIZED_HF":
                if not HF_AVAILABLE or not _TORCH_AVAILABLE:
                    logging.error("LumaxEngine: %s requires transformers+torch, but one or both are not installed.", self.engine_type)
                    return False
                from transformers import AutoTokenizer, AutoModelForCausalLM
                logging.info(f"LumaxEngine: Manifesting {self.engine_type} Soul...")
                self.tokenizer = AutoTokenizer.from_pretrained(self.model_path, trust_remote_code=True)
                
                # Check for Flash Attention availability
                attn_impl = "eager"
                try:
                    import flash_attn
                    attn_impl = "flash_attention_2"
                    logging.info("LumaxEngine: Flash Attention 2 detected and enabled.")
                except ImportError:
                    logging.warning("LumaxEngine: Flash Attention not found, falling back to eager.")
 
                self.model = AutoModelForCausalLM.from_pretrained(
                    self.model_path,
                    device_map="auto",
                    trust_remote_code=True,
                    attn_implementation=attn_impl,
                    **_hf_pretrained_dtype_kw(AutoModelForCausalLM),
                )
                logging.info(f"LumaxEngine: {self.engine_type} Soul Manifested on {self.model.device}.")
                return True

            elif self.engine_type == "DFLASH":
                if not HF_AVAILABLE or not _TORCH_AVAILABLE:
                    logging.error("LumaxEngine: DFlash requires transformers+torch, but one or both are not installed.")
                    return False
                logging.info(f"LumaxEngine: Manifesting Qwen3.5-4B-DFlash Soul...")
                self.tokenizer = AutoTokenizer.from_pretrained(self.model_path, trust_remote_code=True)
                
                # Use importlib to load dflash.py directly to avoid sys.path pollution or naming conflicts
                dflash_path = os.path.join(self.model_path, "dflash.py")
                if os.path.exists(dflash_path):
                    import importlib.util
                    import sys
                    spec = importlib.util.spec_from_file_location("dflash_model", dflash_path)
                    dflash_mod = importlib.util.module_from_spec(spec)
                    sys.modules["dflash_model"] = dflash_mod
                    spec.loader.exec_module(dflash_mod)
                    
                    self.model = dflash_mod.DFlashDraftModel.from_pretrained(
                        self.model_path,
                        device_map="auto",
                        trust_remote_code=True,
                        **_hf_pretrained_dtype_kw(dflash_mod.DFlashDraftModel),
                    )
                    logging.info("LumaxEngine: DFlash Soul Manifested (Block Diffusion Active).")
                    return True
                else:
                    logging.warning("dflash.py not found in model path, using transformers fallback...")
                    from transformers import AutoModelForCausalLM
                    
                    # Check for Flash Attention availability
                    attn_impl = "eager"
                    try:
                        import flash_attn
                        attn_impl = "flash_attention_2"
                    except ImportError:
                        pass

                    self.model = AutoModelForCausalLM.from_pretrained(
                        self.model_path,
                        device_map="auto",
                        trust_remote_code=True,
                        attn_implementation=attn_impl,
                        **_hf_pretrained_dtype_kw(AutoModelForCausalLM),
                    )
                    return True

            elif self.engine_type == "TRANSFORMERS":
                if not HF_AVAILABLE or not _TORCH_AVAILABLE:
                    logging.error("LumaxEngine: Transformers engine requires transformers+torch, but one or both are not installed.")
                    return False
                from transformers import AutoModelForCausalLM, BitsAndBytesConfig
                logging.info(f"LumaxEngine: Manifesting {self.model_name} with 4-bit optimization...")
                
                self.tokenizer = AutoTokenizer.from_pretrained(self.model_path, trust_remote_code=True)
                
                # 4-bit Quantization Config for RTX 4060 efficiency
                bnb_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_compute_dtype=torch.bfloat16
                )

                self.model = AutoModelForCausalLM.from_pretrained(
                    self.model_path,
                    quantization_config=bnb_config,
                    device_map="auto",
                    trust_remote_code=True
                )
                logging.info(f"LumaxEngine: Soul Manifested (4-bit Active).")
                return True
                
        except Exception as e:
            logging.error(f"LumaxEngine: Manifestation Failed -> {e}", exc_info=True)
        return False

    def flush(self):
        """Evict VRAM: purge Torch cache to yield priority for external sensory tasks (STT/TTS)."""
        import torch
        import gc
        try:
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
            logging.info("LumaxEngine: VRAM Purge (Agile Flush) completed.")
        except Exception as e:
            logging.error(f"LumaxEngine: VRAM Purge failed -> {e}")

    def _fit_gguf_prompt(self, prompt: str, max_tokens: int) -> str:
        """Shrink prompt token count so prompt + generation fits n_ctx (llama.cpp rejects oversized prompts)."""
        if not self.model or not prompt or self.engine_type != "GGUF":
            return prompt
        if not hasattr(self.model, "tokenize") or not hasattr(self.model, "detokenize"):
            return prompt
        reserve = max(96, min(768, max_tokens + 64))
        budget = max(256, self.gguf_n_ctx - reserve)
        try:
            ids = self.model.tokenize(prompt.encode("utf-8"))
        except Exception as ex:
            logging.debug("LumaxEngine: tokenize failed, using raw prompt: %s", ex)
            return prompt
        if len(ids) <= budget:
            return prompt
        logging.warning(
            "LumaxEngine: prompt %d tokens > budget %d (n_ctx=%d); keeping last %d tokens (tail). "
            "Raise FoveAI_LOCAL_N_CTX / FoveAI_LOCAL_N_CTX_MAX, enable FoveAI_ADAPTIVE_N_CTX, or trim MindCore/memories if quality drops.",
            len(ids),
            budget,
            self.gguf_n_ctx,
            budget,
        )
        tail = ids[-budget:]
        try:
            raw = self.model.detokenize(tail)
        except Exception as ex:
            logging.warning("LumaxEngine: detokenize after trim failed: %s", ex)
            return prompt
        if isinstance(raw, bytes):
            return raw.decode("utf-8", errors="replace")
        return str(raw)

    def generate(self, prompt: str, image_base64: str = None, max_tokens: int = 768) -> str:
        if not self.model:
            logging.info("LumaxEngine: Model not loaded. Attempting JIT load...")
            if not self.load():
                return "Soul not manifested. No local GGUF or Transformers model is currently loaded in the engine."
        
        try:
            if self.engine_type == "GGUF":
                vl_extra = 0
                if image_base64 and getattr(self, "gguf_multimodal_ready", False):
                    try:
                        vl_extra = int(os.getenv("FoveAI_ADAPTIVE_VL_EXTRA_TOKENS", "768") or "768")
                    except Exception:
                        vl_extra = 768
                self.ensure_gguf_context_for_prompt(prompt, max_tokens, extra_token_slots=vl_extra)
                gguf_config = {
                    "temperature": self.gen_config.get("temperature", 0.7),
                    "top_p": self.gen_config.get("top_p", 0.8),
                    "top_k": self.gen_config.get("top_k", 20),
                    "min_p": self.gen_config.get("min_p", 0.0),
                    "repeat_penalty": self.gen_config.get("repetition_penalty", 1.15),
                    "presence_penalty": self.gen_config.get("presence_penalty", 0.8),
                    "frequency_penalty": self.gen_config.get("frequency_penalty", 0.5),
                }
                # Stops: do NOT use "\n\n" — it cuts off normal paragraphs after a few words.
                _stops = [
                    "USER:", "\nUSER:",
                    "<|eot_id|>", "<|end_of_text|>", "<|im_end|>", "<|im_end|>",
                ]
                if image_base64 and getattr(self, "gguf_multimodal_ready", False):
                    try:
                        raw_img = (image_base64 or "").strip()
                        if raw_img.startswith("data:"):
                            img_url = raw_img
                        else:
                            img_url = f"data:image/jpeg;base64,{raw_img}"
                        messages = [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "image_url", "image_url": {"url": img_url}},
                                    {"type": "text", "text": prompt},
                                ],
                            }
                        ]
                        out = self.model.create_chat_completion(
                            messages=messages,
                            max_tokens=max_tokens,
                            stop=_stops,
                            frequency_penalty=gguf_config.get("frequency_penalty", 0.5),
                            presence_penalty=gguf_config.get("presence_penalty", 0.8),
                            repeat_penalty=gguf_config.get("repeat_penalty", 1.15),
                            temperature=gguf_config.get("temperature", 0.7),
                            top_p=gguf_config.get("top_p", 0.8),
                            top_k=gguf_config.get("top_k", 20),
                        )
                        ch0 = out["choices"][0]
                        msg = ch0.get("message") or {}
                        raw_c = msg.get("content")
                        if isinstance(raw_c, list):
                            piece = "".join(
                                x.get("text", "") if isinstance(x, dict) else str(x) for x in raw_c
                            ).strip()
                        elif isinstance(raw_c, str):
                            piece = raw_c.strip()
                        else:
                            piece = ""
                        if piece:
                            return _strip_model_thinking_text(piece)
                    except Exception as mm_ex:
                        logging.warning(
                            "LumaxEngine: GGUF multimodal chat completion failed, falling back to text-only: %s",
                            mm_ex,
                        )
                prompt = self._fit_gguf_prompt(prompt, max_tokens)
                output = self.model(prompt, max_tokens=max_tokens, stop=_stops, **gguf_config)
                return _strip_model_thinking_text(output["choices"][0]["text"].strip())

            elif (
                self.engine_type == "DFLASH"
                or self.engine_type == "TRANSFORMERS"
                or self.engine_type == "QUANTIZED_HF"
            ):
                # AWQ / GPTQ / plain HF text: vision is text-injected (compagent helper stack), not raw pixels here.
                inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
                outputs = self.model.generate(**inputs, max_new_tokens=max_tokens, **self.gen_config)
                return _strip_model_thinking_text(
                    self.tokenizer.decode(outputs[0], skip_special_tokens=True)
                )

            else:
                if not HF_AVAILABLE or not _TORCH_AVAILABLE:
                    return "Soul not manifested: Qwen3-VL requires transformers+torch which are not installed."
                # Qwen3-VL Logic
                content = [{"type": "text", "text": prompt}]
                if image_base64:
                    content.insert(0, {"type": "image", "image": f"data:image/jpeg;base64,{image_base64}"})
                
                messages = [{"role": "user", "content": content}]
                text = self.processor.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=_model_thinking_enabled()
                )
                inputs = self.processor(text=[text], padding=True, return_tensors="pt").to(self.model.device)

                generated_ids = self.model.generate(**inputs, max_new_tokens=max_tokens)
                generated_ids_trimmed = [out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)]
                return _strip_model_thinking_text(
                    self.processor.batch_decode(
                        generated_ids_trimmed,
                        skip_special_tokens=True,
                        clean_up_tokenization_spaces=False,
                    )[0]
                )
                
        except Exception as e:
            return f"Cognition Error: {e}"

    def generate_stream(self, prompt: str, max_tokens: int = 768):
        """Streams tokens word-by-word for GGUF models. Multimodal (native mmproj) is not wired here — use generate() with image_base64.

        Note: FoveAI_MODEL_THINKING=0 does not post-process streamed chunks; use non-stream generate() for stripped CoT.
        """
        if not self.model:
            logging.info("LumaxEngine: Model not loaded. Attempting JIT load...")
            if not self.load():
                yield "Soul not manifested or engine doesn't support streaming."
                return
        if self.engine_type != "GGUF":
            yield "Soul not manifested or engine doesn't support streaming."
            return

        try:
            self.ensure_gguf_context_for_prompt(prompt, max_tokens)
            gguf_config = {
                "temperature": self.gen_config.get("temperature", 0.7),
                "top_p": self.gen_config.get("top_p", 0.8),
                "top_k": self.gen_config.get("top_k", 20),
                "min_p": self.gen_config.get("min_p", 0.0),
                "repeat_penalty": self.gen_config.get("repetition_penalty", 1.15),
                "presence_penalty": self.gen_config.get("presence_penalty", 0.8),
                "frequency_penalty": self.gen_config.get("frequency_penalty", 0.5),
            }
            prompt = self._fit_gguf_prompt(prompt, max_tokens)
            stream = self.model(
                prompt, 
                max_tokens=max_tokens, 
                stop=["USER:", "<|redacted_im_end|>", "\n\n"], 
                stream=True,
                **gguf_config
            )
            
            for chunk in stream:
                if "choices" in chunk and len(chunk["choices"]) > 0:
                    text = chunk["choices"][0].get("text", "")
                    if text:
                        yield text
        except Exception as e:
            yield f" [Cognition Stream Error: {e}] "
    def embed(self, text: str) -> list[float]:
        """Generate embeddings in-place using the manifested GGUF soul."""
        if not self.model or self.engine_type != "GGUF":
            return []
        try:
            # llama-cpp-python create_embedding returns {'data': [{'embedding': [...]}, ...]}
            res = self.model.create_embedding(text)
            if "data" in res and len(res["data"]) > 0:
                return res["data"][0]["embedding"]
        except Exception as e:
            logging.error(f"LumaxEngine: In-place Embedding Failed -> {e}")
        return []
