"""
runtime/triad_pipeline.py — Holonic Model Collaboration Pipeline
=================================================================
Orchestrates the triad of small specialist models around the main model:

  1. ROUTER (0.5B, CPU)    — classifies the user's intent, outputs a route tag
  2. SUMMARIZER (0.6B, CPU) — compresses conversation history before it enters
                              the main model's context window
  3. MAIN MODEL (GPU)      — generates the actual response, fed clean context

The pipeline runs on every chat() call:
  user_msg → router.classify() → summarizer.compress(history) → main.chat()

The router output determines:
  - Which cognitive profile to activate (code, creative, reasoning, etc.)
  - Whether the summarizer should run (skip for short conversations)
  - Hints/skeletons to inject into the system prompt

The summarizer output replaces raw conversation history with a compressed
version, saving context tokens for the main model.

VRAM impact: zero. Both helpers run entirely on CPU.
Latency impact: ~50-100ms for router (128 tokens), ~200-500ms for summarizer
when it runs (only on long conversations). This is offset by the main model
processing fewer tokens.
"""

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from llama_bridge.helper_model import HelperModel


# ── Route tags the router was trained to output ──────────────────────────────
ROUTE_SPECIALISTS = {
    "code": "code",
    "creative": "creative",
    "reasoning": "reasoning",
    "memory": "memory",
    "audio": "audio",
    "vision": "vision",
    "diagnostic": "diagnostic",
}

# Router signals that control pipeline behavior
SIGNAL_CONTINUE = "continue"
SIGNAL_STOP = "stop"
SIGNAL_SOLVED = "solved"

# When to trigger the summarizer (conversation length thresholds)
SUMMARIZE_MIN_TURNS = 6       # don't compress short conversations
SUMMARIZE_MIN_CHARS = 2000    # only compress if history is substantial


class TriadPipeline:
    """
    Coordinates router + summarizer + main model into a single inference pipeline.
    """

    def __init__(
        self,
        router_path: Optional[str] = None,
        summarizer_path: Optional[str] = None,
        n_threads: Optional[int] = None,
        verbose: bool = False,
    ):
        self.router_path = router_path
        self.summarizer_path = summarizer_path
        self.n_threads = n_threads
        self.verbose = verbose

        self._router: Optional[HelperModel] = None
        self._summarizer: Optional[HelperModel] = None
        self.loaded: bool = False

        # Stats for observability
        self._stats: Dict[str, Any] = {
            "total_calls": 0,
            "router_calls": 0,
            "summarizer_calls": 0,
            "tokens_saved_estimate": 0,
        }

    def load(self) -> "TriadPipeline":
        if self.loaded:
            return self

        if self.router_path and os.path.exists(self.router_path):
            try:
                self._router = HelperModel(
                    model_path=self.router_path,
                    n_ctx=1024,  # router only needs short context
                    n_threads=self.n_threads,
                    verbose=self.verbose,
                    label="router",
                    n_gpu_layers=0,  # CPU only — zero VRAM impact, doesn't compete with main model
                ).load()
            except Exception as e:
                print(f"  ⚠️ Router load failed: {e}")
        else:
            print(f"  ⏭️ Router skipped (no model path: {self.router_path})")

        if self.summarizer_path and os.path.exists(self.summarizer_path):
            try:
                self._summarizer = HelperModel(
                    model_path=self.summarizer_path,
                    n_ctx=2048,  # summarizer needs to read longer input
                    n_threads=self.n_threads,
                    verbose=self.verbose,
                    label="summarizer",
                    n_gpu_layers=0,  # CPU only — zero VRAM impact, doesn't compete with main model
                ).load()
            except Exception as e:
                print(f"  ⚠️ Summarizer load failed: {e}")
        else:
            print(f"  ⏭️ Summarizer skipped (no model path: {self.summarizer_path})")

        self.loaded = True
        active = []
        if self._router:
            active.append("router")
        if self._summarizer:
            active.append("summarizer")
        if active:
            print(f"  🧠 Triad pipeline active: {' + '.join(active)} + main")
        else:
            print(f"  ⏭️ Triad pipeline: no helpers loaded (main model only)")
        return self

    # ── Router ───────────────────────────────────────────────────────────────

    def classify(self, user_msg: str) -> Dict[str, Any]:
        """
        Run the router on the user message.
        Returns a dict with:
          - specialist: which specialist to route to (code/creative/reasoning/...)
          - signal: continue/stop/solved or None
          - intent: extracted intent tag if present
          - emotion: extracted emotion if present
          - raw: raw router output
          - fovea: fovea signal if present (focus/peripheral)
          - hints: list of hint tags
          - skeleton: skeleton tag if present
        """
        self._stats["total_calls"] += 1
        result: Dict[str, Any] = {
            "specialist": None,
            "signal": None,
            "intent": None,
            "emotion": None,
            "fovea": None,
            "hints": [],
            "skeleton": None,
            "raw": "",
        }

        if not self._router or not self._router.loaded:
            return result

        self._stats["router_calls"] += 1

        try:
            raw = self._router.chat(
                messages=[{
                    "role": "user",
                    "content": user_msg,
                }],
                max_tokens=64,
                temperature=0.1,
            )
            result["raw"] = raw
        except Exception as e:
            if self.verbose:
                print(f"  [triad] router error: {e}")
            return result

        # Parse router output
        # Format: <xrl:route specialist="code" />
        route_match = re.search(r'specialist="(\w+)"', raw)
        if route_match:
            spec = route_match.group(1).lower()
            if spec in ROUTE_SPECIALISTS:
                result["specialist"] = ROUTE_SPECIALISTS[spec]

        # Signal: continue/stop/solved
        raw_lower = raw.lower().strip()
        if raw_lower == SIGNAL_CONTINUE:
            result["signal"] = SIGNAL_CONTINUE
        elif raw_lower == SIGNAL_STOP:
            result["signal"] = SIGNAL_STOP
        elif raw_lower == SIGNAL_SOLVED:
            result["signal"] = SIGNAL_SOLVED

        # Intent: INTENT:announce EMOTION:joy TARGET:release
        intent_match = re.search(r'INTENT:(\w+)', raw)
        if intent_match:
            result["intent"] = intent_match.group(1).lower()
        emotion_match = re.search(r'EMOTION:(\w+)', raw)
        if emotion_match:
            result["emotion"] = emotion_match.group(1).lower()

        # Fovea: <fovea:focus /> or <fovea:peripheral />
        fovea_match = re.search(r'<fovea:(\w+)\s*/>', raw)
        if fovea_match:
            result["fovea"] = fovea_match.group(1).lower()

        # Hints: <hint:consider-map-filter />
        hint_matches = re.findall(r'<hint:(\S+)\s*/>', raw)
        result["hints"] = [h.lower() for h in hint_matches]

        # Skeleton: <skeleton:comfort> ... </skeleton:comfort>
        skeleton_match = re.search(r'<skeleton:(\w+)>(.*?)</skeleton:\1>', raw, re.DOTALL)
        if skeleton_match:
            result["skeleton"] = {
                "type": skeleton_match.group(1).lower(),
                "content": skeleton_match.group(2).strip(),
            }

        if self.verbose:
            print(f"  [triad] router → specialist={result['specialist']} "
                  f"signal={result['signal']} intent={result['intent']}")

        return result

    # ── Summarizer ───────────────────────────────────────────────────────────

    def compress_history(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Compress conversation history using the summarizer model.
        Replaces older turns with a compressed summary, keeping the most
        recent turns intact for continuity.

        Only triggers when the conversation is long enough to benefit.
        Returns the (possibly compressed) messages list.
        """
        if not self._summarizer or not self._summarizer.loaded:
            return messages

        # Count conversation turns and total chars
        turns = [m for m in messages if m.get("role") in ("user", "assistant")]
        total_chars = sum(len(str(m.get("content", ""))) for m in turns)

        if len(turns) < SUMMARIZE_MIN_TURNS or total_chars < SUMMARIZE_MIN_CHARS:
            return messages

        self._stats["summarizer_calls"] += 1

        # Keep the last 2 turns verbatim, compress everything before
        keep_recent = 2
        old_turns = turns[:-keep_recent]
        recent_turns = turns[-keep_recent:]

        # Build the text to compress
        history_text = "\n".join(
            f"{t['role']}: {t['content']}" for t in old_turns
            if isinstance(t.get("content"), str)
        )

        if not history_text.strip():
            return messages

        try:
            compressed = self._summarizer.chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an XRLF summarizer. Compress the input to its "
                            "essential skeleton. Preserve logic, structure, and key "
                            "information. Drop boilerplate, comments, and redundant "
                            "details. Output only the compressed version."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Compress this context to its essential information:\n\n{history_text}",
                    },
                ],
                max_tokens=512,
                temperature=0.1,
            )
        except Exception as e:
            if self.verbose:
                print(f"  [triad] summarizer error: {e}")
            return messages

        if not compressed or len(compressed) < 20:
            return messages

        # Estimate tokens saved (rough: 1 token ≈ 4 chars)
        saved_chars = len(history_text) - len(compressed)
        self._stats["tokens_saved_estimate"] += max(0, saved_chars // 4)

        if self.verbose:
            print(f"  [triad] summarizer compressed {len(history_text)} → {len(compressed)} chars")

        # Rebuild messages: system + compressed summary + recent turns
        result: List[Dict[str, str]] = []
        # Preserve any system messages
        for m in messages:
            if m.get("role") == "system":
                result.append(m)
        # Add compressed history as a system context note
        result.append({
            "role": "system",
            "content": f"[Compressed conversation history]\n{compressed}",
        })
        # Add recent turns verbatim
        for t in recent_turns:
            result.append(t)

        return result

    # ── Full Pipeline ────────────────────────────────────────────────────────

    def pre_process(
        self,
        messages: List[Dict[str, str]],
        user_msg: str,
    ) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
        """
        Run the full pre-processing pipeline before the main model generates.

        1. Router classifies the user message
        2. Summarizer compresses history if needed

        Returns (processed_messages, router_result).
        """
        # Step 1: Route classification
        router_result = self.classify(user_msg)

        # Step 2: History compression
        processed = self.compress_history(messages)

        return processed, router_result

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def unload(self):
        if self._router:
            self._router.unload()
            self._router = None
        if self._summarizer:
            self._summarizer.unload()
            self._summarizer = None
        self.loaded = False

    def get_stats(self) -> Dict[str, Any]:
        return dict(self._stats)
