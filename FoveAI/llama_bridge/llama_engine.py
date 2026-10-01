"""
llama_bridge/llama_engine.py — llama-cpp-python Wrapper
========================================================
Thin, fault-tolerant wrapper around llama-cpp-python for the XRLF runtime.

Gemma-4-12B MoQ supports native multimodal input (image, video, audio).
This engine handles the multimodal chat template for llama.cpp.
"""

import os
from collections.abc import Generator
from pathlib import Path
from typing import Any

# ── llama-cpp-python import (with helpful error if not installed) ──────────────

try:
    from llama_cpp import Llama, LlamaGrammar

    _LLAMA_AVAILABLE = True
except ImportError:
    _LLAMA_AVAILABLE = False
    Llama = None


LLAMA_INSTALL_HINT = """
llama-cpp-python is not installed.

Install with CUDA support (recommended for Gemma-4-12B):

    pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124

Or CPU-only:

    pip install llama-cpp-python
"""


class LlamaEngine:
    """
    Wraps a llama.cpp model loaded from a GGUF path.

    Supports:
      - Text generation (generate)
      - Chat completion (chat) with automatic template application
      - Text embedding (embed) for semantic cluster routing
      - Streaming generation (generate_stream)
    """

    def __init__(
        self,
        gguf_path: str,
        n_gpu_layers: int = -1,  # -1 = offload all layers
        n_ctx: int = 8192,
        n_threads: int | None = None,
        verbose: bool = False,
        flash_attn: bool = True,
        mmproj_path: str | None = None,
        draft_model_path: str | None = None,
    ):
        if not _LLAMA_AVAILABLE:
            raise RuntimeError(LLAMA_INSTALL_HINT)

        self.gguf_path = str(gguf_path)
        self.n_gpu_layers = n_gpu_layers
        self.n_ctx = n_ctx
        self.n_threads = n_threads or os.cpu_count()
        self.verbose = verbose
        self.flash_attn = flash_attn
        self.mmproj_path = mmproj_path
        self.draft_model_path = draft_model_path
        self._llm: Llama | None = None
        self._draft_llm: Any | None = None
        self._mtp_active: bool = False
        self.status_message: str = ""
        self.loaded = False

    def load(self) -> "LlamaEngine":
        if self.loaded:
            return self

        if not Path(self.gguf_path).exists():
            raise FileNotFoundError(f"GGUF not found: {self.gguf_path}")

        print(f"  Loading GGUF: {self.gguf_path}")
        print(
            f"    n_ctx={self.n_ctx}  gpu_layers={self.n_gpu_layers}  threads={self.n_threads}"
        )

        # ── VRAM & Concurrency Guardrail (8GB Ceiling) ──
        try:
            from runtime.vram_guard import guardrail

            ok, safe_layers, msg = guardrail.acquire_slot(
                role="main",
                model_path=self.gguf_path,
                requested_layers=self.n_gpu_layers,
                total_model_layers=40,
                n_ctx=self.n_ctx,
            )
            if not ok:
                raise RuntimeError(msg)
            self.n_gpu_layers = safe_layers
            self.status_message = msg
        except ImportError:
            pass

        # NOTE: KV cache safety net (n_ctx cap) is handled upstream in XRLFRuntime._cap_n_ctx_for_vram()
        # so that memory planning uses the actual capped value. No cap here — trust the caller.

        kwargs = dict(
            model_path=self.gguf_path,
            n_ctx=self.n_ctx,
            n_gpu_layers=self.n_gpu_layers,
            n_threads=self.n_threads,
            verbose=self.verbose,
            n_batch=128,
            use_mmap=False,  # Windows: avoids 0xC000001D illegal instruction on CUDA init
        )
        # KV cache quantization — requires flash_attn, which Gemma 4 can't use
        # (mismatched V embedding sizes across layers). Left here for non-Gemma models.
        kv_quant = os.getenv("FOVEAI_KV_QUANT", "f16")
        if kv_quant and kv_quant != "f16":
            import llama_cpp

            type_map = {
                "q8_0": llama_cpp.GGML_TYPE_Q8_0,
                "q4_0": llama_cpp.GGML_TYPE_Q4_0,
                "q4_1": llama_cpp.GGML_TYPE_Q4_1,
                "q5_0": llama_cpp.GGML_TYPE_Q5_0,
                "q5_1": llama_cpp.GGML_TYPE_Q5_1,
            }
            if kv_quant in type_map:
                # V cache quantization requires flash_attn — skip if FA is off
                fa_enabled = kwargs.get("flash_attn", False)
                if fa_enabled:
                    kwargs["type_k"] = type_map[kv_quant]
                    kwargs["type_v"] = type_map[kv_quant]
                    print(f"    KV cache quantized: {kv_quant}")
                else:
                    print(
                        f"    KV quantization {kv_quant} skipped — requires flash_attn (disabled for this model)"
                    )
        # Flash Attention — accelerated prompt processing when requested
        if self.flash_attn and os.getenv("FOVEAI_FLASH_ATTN", "1") == "1":
            kwargs["flash_attn"] = True

        # Multimodal Chat Handler
        if self.mmproj_path and Path(self.mmproj_path).exists():
            print(f"  Loading MMPROJ handler: {self.mmproj_path}")
            try:
                # Use our local patched handler first (has audio_url support + Kokoro fixes)
                from llama_bridge.gemma4_handler import Gemma4ChatHandler

                kwargs["chat_handler"] = Gemma4ChatHandler(
                    clip_model_path=self.mmproj_path
                )
                print("    Using Gemma4ChatHandler (local patched — audio+vision)")
            except (ImportError, AttributeError):
                try:
                    # Fall back to native Gemma4 handler from llama_cpp (0.3.34+)
                    from llama_cpp.llama_chat_format import Gemma4ChatHandler

                    kwargs["chat_handler"] = Gemma4ChatHandler(
                        clip_model_path=self.mmproj_path
                    )
                    print("    Using Gemma4ChatHandler (native fallback)")
                except (ImportError, AttributeError):
                    try:
                        from llama_cpp.llama_chat_format import Qwen25VLChatHandler

                        kwargs["chat_handler"] = Qwen25VLChatHandler(
                            clip_model_path=self.mmproj_path
                        )
                        print("    Using Qwen25VLChatHandler")
                    except (ImportError, AttributeError):
                        from llama_cpp.llama_chat_format import Llava15ChatHandler

                        kwargs["chat_handler"] = Llava15ChatHandler(
                            clip_model_path=self.mmproj_path
                        )
                        print("    Using Llava15ChatHandler (fallback)")

        from llama_cpp import Llama, llama_cpp

        # ── MTP / Speculative Decoding ──────────────────────────────────────────
        # The 12B XRLF packs an MTP (Multi-Token Prediction) head, not a standalone
        # draft LLM. MTP layers are embedded in the main GGUF (667 tensors for a
        # 48-block model). We activate them via load_mtp=True on the model params.
        # If the draft file is a full LLM instead, we fall back to classic
        # LlamaDraftModel speculative decoding on CPU.
        use_spec = os.environ.get(
            "XRLF_SPECULATIVE_DECODING", "false"
        ).lower().strip() in ("true", "1", "on")
        if use_spec and self.draft_model_path and Path(self.draft_model_path).exists():
            print(
                f"  Speculative decoding enabled (draft: {Path(self.draft_model_path).name})"
            )
            try:
                # Detect MTP head vs full draft model by tensor count.
                # MTP heads have <80 tensors; full models have 100+.
                import struct as _struct

                with open(self.draft_model_path, "rb") as _df:
                    _df.read(4)  # magic
                    _df.read(4)  # version
                    _draft_tensors: int = _struct.unpack("<Q", _df.read(8))[0]

                if _draft_tensors < 80:
                    # MTP head — activate native MTP layers in the main GGUF.
                    # Llama() doesn't expose load_mtp, so we monkey-patch the
                    # default-params factory to set load_mtp=True before the
                    # model is constructed.
                    print(
                        f"    Draft has {_draft_tensors} tensors → MTP head. Activating native load_mtp."
                    )
                    _orig_default_params = llama_cpp.llama_model_default_params

                    def _mtp_default_params():
                        p = _orig_default_params()
                        p.load_mtp = True
                        return p

                    llama_cpp.llama_model_default_params = _mtp_default_params
                    self._mtp_active = True
                else:
                    # Full draft model — classic speculative decoding on CPU.
                    print(
                        f"    Draft has {_draft_tensors} tensors → full model. Using LlamaDraftModel on CPU."
                    )
                    import numpy as np
                    from llama_cpp.llama_speculative import LlamaDraftModel

                    class GGUFDraftModel(LlamaDraftModel):
                        def __init__(self, draft_llm, num_pred_tokens=3):
                            self.draft_llm = draft_llm
                            self.num_pred_tokens = num_pred_tokens

                        def __call__(self, input_ids, /, **kwargs):
                            if input_ids is None or len(input_ids) == 0:
                                return np.array([], dtype=np.intc)
                            try:
                                tokens = []
                                for t in self.draft_llm.generate(
                                    input_ids.tolist(), top_k=1, top_p=1.0, temp=0.0
                                ):
                                    tokens.append(t)
                                    if len(tokens) >= self.num_pred_tokens:
                                        break
                                return np.array(tokens, dtype=np.intc)
                            except Exception:
                                return np.array([], dtype=np.intc)

                    draft_layers = 0
                    try:
                        from runtime.vram_guard import guardrail

                        _, draft_layers, _ = guardrail.acquire_slot(
                            role="helper",
                            model_path=self.draft_model_path,
                            requested_layers=0,
                            total_model_layers=24,
                            n_ctx=min(2048, self.n_ctx),
                        )
                    except Exception:
                        draft_layers = 0

                    self._draft_llm = Llama(
                        model_path=self.draft_model_path,
                        n_gpu_layers=draft_layers,
                        n_ctx=min(2048, self.n_ctx),
                        n_threads=self.n_threads,
                        verbose=self.verbose,
                    )
                    kwargs["draft_model"] = GGUFDraftModel(self._draft_llm)
                    print(
                        f"    Draft model running on CPU (n_gpu_layers={draft_layers}) to protect VRAM."
                    )
            except Exception as e:
                print(
                    f"  ⚠️ MTP/draft setup failed: {e}. Continuing without speculative decoding."
                )

        self._llm = Llama(**kwargs)

        # Restore the monkey-patched default_params if MTP was activated
        if self._mtp_active:
            try:
                llama_cpp.llama_model_default_params = _orig_default_params
            except NameError:
                pass

        self.loaded = True
        print(f"  ✅ GGUF loaded into llama.cpp [{self.status_message}]")
        return self

    # ── Generation ────────────────────────────────────────────────────────────

    def generate(
        self,
        prompt: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        top_p: float = 0.95,
        repeat_penalty: float = 1.1,
        stop: list[str] | None = None,
    ) -> str:
        """Raw text completion."""
        self._require_loaded()
        result = self._llm(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            repeat_penalty=repeat_penalty,
            stop=stop or ["<end_of_turn>", "<eos>", "<|im_end|>"],
            echo=False,
        )
        return result["choices"][0]["text"]

    def generate_stream(
        self,
        prompt: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        top_p: float = 0.95,
        stop: list[str] | None = None,
    ) -> Generator[str, None, None]:
        """Streaming text completion — yields token chunks."""
        self._require_loaded()
        for chunk in self._llm(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stop=stop or ["<end_of_turn>", "<eos>", "<|im_end|>"],
            stream=True,
            echo=False,
        ):
            delta = chunk["choices"][0].get("text", "")
            if delta:
                yield delta

    def _format_messages(self, messages: list[dict[str, str]]) -> str:
        """Auto-detect chat template from model architecture.
        Qwen2 → <|im_start|>/<|im_end|> format
        Gemma → <start_of_turn>/<end_of_turn> format
        """
        # Detect architecture from loaded model metadata
        arch = "qwen2"  # default — our XRLF cores are Qwen2-based
        try:
            meta = self._llm.metadata if self._llm else {}
            arch = str(meta.get("general.architecture", "qwen2")).lower()
        except Exception:
            pass

        system_parts = []
        for m in messages:
            if m.get("role") == "system":
                system_parts.append(str(m.get("content", "")))
        system_text = "\n".join(system_parts).strip()

        if "gemma" in arch:
            # Gemma chat template
            prompt = ""
            first_user = True
            for m in messages:
                role = m.get("role")
                content = str(m.get("content", ""))
                if role == "system":
                    continue
                if role == "assistant":
                    role = "model"
                if first_user and role == "user" and system_text:
                    content = f"{system_text}\n{content}"
                    first_user = False
                prompt += f"<start_of_turn>{role}\n{content}<end_of_turn>\n"
            if first_user and system_text:
                prompt += f"<start_of_turn>user\n{system_text}<end_of_turn>\n"
            prompt += "<start_of_turn>model\n"
            return prompt
        else:
            # Qwen2 / ChatML template
            prompt = ""
            if system_text:
                prompt += f"<|im_start|>system\n{system_text}<|im_end|>\n"
            for m in messages:
                role = m.get("role")
                content = str(m.get("content", ""))
                if role == "system":
                    continue
                prompt += f"<|im_start|>{role}\n{content}<|im_end|>\n"
            prompt += "<|im_start|>assistant\n"
            return prompt

    def chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 1024,
        temperature: float = 0.7,
        stream: bool = False,
    ) -> str | Generator[str, None, None]:
        """
        Chat completion using the model's built-in chat template.
        Messages format: [{"role": "user"|"assistant"|"system", "content": "..."}]

        For multimodal (Gemma-4 native):
          content can also be a list:
          [{"type": "text", "text": "..."}, {"type": "image_url", "image_url": {...}}]
        """
        self._require_loaded()
        if stream:
            return self._chat_stream(messages, max_tokens, temperature)

        # If a chat handler is loaded (e.g. Gemma4ChatHandler), use
        # create_chat_completion which applies the model's native chat template
        # and handles multimodal content (images, audio) properly.
        if hasattr(self._llm, "chat_handler") and self._llm.chat_handler:
            try:
                result = self._llm.create_chat_completion(
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=False,
                )
                return result["choices"][0]["message"]["content"].strip()
            except Exception as e:
                print(f"  [LlamaEngine] create_chat_completion failed ({e})")
                # If messages contain multimodal objects (lists), falling back to text template
                # will inject massive base64 strings into the prompt and blow up the context window.
                if any(isinstance(m.get("content"), list) for m in messages):
                    raise ValueError(
                        f"Multimodal chat completion failed (likely unsupported modality): {e}"
                    )
                print("  [LlamaEngine] falling back to manual template")

        # Fallback: manual template formatting
        prompt = self._format_messages(messages)
        result = self._llm(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=["<end_of_turn>", "<eos>"],
            echo=False,
        )
        return result["choices"][0]["text"].strip()

    def _chat_stream(
        self,
        messages: list[dict[str, str]],
        max_tokens: int,
        temperature: float,
    ) -> Generator[str, None, None]:
        # If a chat handler is loaded, use streaming create_chat_completion
        if hasattr(self._llm, "chat_handler") and self._llm.chat_handler:
            try:
                for chunk in self._llm.create_chat_completion(
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=True,
                ):
                    delta = chunk["choices"][0].get("delta", {}).get("content", "")
                    if delta:
                        yield delta
                return
            except Exception as e:
                print(
                    f"  [LlamaEngine] streaming create_chat_completion failed ({e}), falling back"
                )

        # Fallback: manual template streaming
        prompt = self._format_messages(messages)
        for chunk in self._llm(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=["<end_of_turn>", "<eos>"],
            stream=True,
            echo=False,
        ):
            delta = chunk["choices"][0].get("text", "")
            if delta:
                yield delta

    def embed(self, text: str) -> list[float]:
        """
        Generate a text embedding vector.
        Used for semantic cluster activation scoring.
        Falls back to empty list if embedding not supported.
        """
        self._require_loaded()
        try:
            result = self._llm.embed(text)
            # llama_cpp returns list or ndarray
            if hasattr(result, "tolist"):
                return result.tolist()
            return list(result)
        except Exception:
            return []

    def tokenize(self, text: str) -> list[int]:
        self._require_loaded()
        return self._llm.tokenize(text.encode("utf-8"))

    def token_count(self, text: str) -> int:
        return len(self.tokenize(text))

    def _require_loaded(self):
        if not self.loaded or self._llm is None:
            raise RuntimeError("LlamaEngine not loaded — call .load() first")
        try:
            from runtime.vram_guard import guardrail

            eviction = guardrail.poll_eviction()
            if eviction:
                new_model = eviction.get("new_model", "another model")
                print(
                    f"  [LlamaEngine] Model evicted by incoming '{new_model}'. Unloading VRAM gracefully."
                )
                self.unload()
                raise RuntimeError(f"Model evicted to make room for {new_model}.")
        except ImportError:
            pass

    # ── Context ───────────────────────────────────────────────────────────────

    @property
    def context_length(self) -> int:
        return self.n_ctx

    def unload(self):
        """Unload model from VRAM and release model concurrency slot."""
        if self._llm:
            try:
                del self._llm
            except Exception:
                pass
            self._llm = None
        if self._draft_llm:
            try:
                del self._draft_llm
            except Exception:
                pass
            self._draft_llm = None
        self.loaded = False
        try:
            import gc

            gc.collect()
        except Exception:
            pass
        try:
            from runtime.vram_guard import guardrail

            guardrail.release_slot("main")
            guardrail.release_slot("helper")
        except Exception:
            pass
        print("  LlamaEngine unloaded and VRAM slots released.")

    def close(self):
        self.unload()

    def __repr__(self) -> str:
        status = "loaded" if self.loaded else "unloaded"
        return f"LlamaEngine({Path(self.gguf_path).name}, {status}, ctx={self.n_ctx})"
