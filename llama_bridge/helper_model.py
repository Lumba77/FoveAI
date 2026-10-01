"""
llama_bridge/helper_model.py — Lightweight CPU-loaded helper models
===================================================================
Loads small GGUF models (router, summarizer) on CPU with minimal context.
These run alongside the main GPU model without competing for VRAM.

The router classifies input → outputs a route tag (e.g. <xrl:route specialist="code" />)
The summarizer compresses context → outputs a shorter version of the input
"""

import os
from pathlib import Path
from typing import Any


class HelperModel:
    """
    A small GGUF model loaded on CPU for auxiliary tasks (routing, summarization).
    Uses llama-cpp-python's Llama class with n_gpu_layers=0.
    """

    def __init__(
        self,
        model_path: str,
        n_ctx: int = 2048,
        n_threads: int | None = None,
        verbose: bool = False,
        label: str = "helper",
        n_gpu_layers: int = -1,  # Use GPU — 0.5B models are tiny (~400MB)
    ):
        self.model_path = str(model_path)
        self.n_ctx = n_ctx
        self.n_threads = n_threads or os.cpu_count() or 4
        self.verbose = verbose
        self.label = label
        self.n_gpu_layers = n_gpu_layers
        self._llm: Any | None = None
        self.loaded: bool = False

    def load(self) -> "HelperModel":
        if self.loaded:
            return self
        if not Path(self.model_path).exists():
            raise FileNotFoundError(f"Helper GGUF not found: {self.model_path}")

        from llama_cpp import Llama

        print(f"  Loading helper [{self.label}]: {Path(self.model_path).name}")
        self._llm = Llama(
            model_path=self.model_path,
            n_gpu_layers=self.n_gpu_layers,
            n_ctx=self.n_ctx,
            n_threads=self.n_threads,
            n_batch=64,
            verbose=self.verbose,
            use_mmap=False,  # Windows: avoids 0xC000001D illegal instruction on CUDA init
        )
        self.loaded = True
        print(f"    ✅ {self.label} ready (CPU-only, n_ctx={self.n_ctx})")
        return self

    def chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 128,
        temperature: float = 0.1,
    ) -> str:
        """Chat completion using Qwen2/ChatML template (all helper models are Qwen-based)."""
        if not self.loaded or self._llm is None:
            return ""

        # Build ChatML prompt (all helper models use Qwen2.5/Qwen3 base)
        system_parts = []
        for m in messages:
            if m.get("role") == "system":
                system_parts.append(str(m.get("content", "")))
        system_text = "\n".join(system_parts).strip()

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

        result = self._llm(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=0.9,
            stop=["<|im_end|>", "<|endoftext|>"],
            echo=False,
        )
        return result["choices"][0]["text"].strip()

    def unload(self):
        if self._llm:
            del self._llm
            self._llm = None
        self.loaded = False
