"""
Forge Nursery Micro-Tools & Automation Engine
==============================================
Manages micro-models (0.5B - 1.5B) as high-speed automated task workers for:
- Real-time UI Intent Routing & Actions
- Sub-second Code Patching & Linting
- Telemetry & Diagnostic Summarization
- Custom User-Defined Tool Automations
"""

import json
import logging
import os
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .model_registry import get_registry

logger = logging.getLogger("forge-micro-tools")

TOOLS_DIR = Path("/home/lumba/FoveAI/Forge/nursery/tools_data")
TOOLS_FILE = TOOLS_DIR / "custom_tools.json"
TOOLS_DIR.mkdir(parents=True, exist_ok=True)

LLAMA_CLI = "/home/lumba/FoveAI/Tools/llama-b11053-cuda/llama-b11053/llama-cli"
LLAMA_LIB_DIR = "/home/lumba/FoveAI/Tools/llama-b11053-cuda/llama-b11053"


@dataclass
class MicroTool:
    id: str
    name: str
    description: str
    system_prompt: str
    preferred_variant: str = "qwen25_coder_05b"
    output_type: str = "json"  # "json" | "text" | "command"
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Default built-in micro tools
BUILTIN_TOOLS: dict[str, MicroTool] = {
    "ui_action_router": MicroTool(
        id="ui_action_router",
        name="UI Action & Intent Router",
        description="Translates user natural language into structured Multigate UI actions and tab/theme switches.",
        system_prompt=(
            "You are a fast UI command parser. Analyze the user request and return ONLY a valid JSON object "
            "with the target action. Example schema: {\"action\": \"tab_switch|theme_change|voice_toggle|none\", "
            "\"target\": \"CodeEditor|Canvas|Systems|Persona|Diagnostics\", \"details\": \"...\"}. "
            "Do NOT include markdown formatting or explanations."
        ),
        output_type="json",
    ),
    "code_quickfix": MicroTool(
        id="code_quickfix",
        name="Sub-second Code Fixer",
        description="Rapidly detects syntax errors, fixes snippets, and refactors functions.",
        system_prompt=(
            "You are an ultra-fast code repair engine. Fix the provided code snippet or syntax issue. "
            "Return ONLY the fixed code without explanations."
        ),
        output_type="text",
    ),
    "data_crystallizer": MicroTool(
        id="data_crystallizer",
        name="Data & Memory Crystallizer",
        description="Crystallizes messy thoughts, transcripts, or telemetry into concise structured JSON facts.",
        system_prompt=(
            "Extract key facts, decisions, and action items from the text. "
            "Return ONLY a JSON array of objects: [{\"fact\": \"...\", \"category\": \"...\", \"priority\": 1..5}]."
        ),
        output_type="json",
    ),
    "sentry_diagnostics": MicroTool(
        id="sentry_diagnostics",
        name="UI & Stack Sentry Diagnostics",
        description="Analyzes service errors, ping logs, or stack traces and outputs a one-sentence remedy.",
        system_prompt=(
            "You are a system reliability sentry. Given an error log or subsystem status, output a concise 1-sentence "
            "diagnosis and recommended action."
        ),
        output_type="text",
    ),
}


class MicroToolEngine:
    def __init__(self):
        self.tools: dict[str, MicroTool] = dict(BUILTIN_TOOLS)
        self._load_custom_tools()

    def _load_custom_tools(self):
        if TOOLS_FILE.exists():
            try:
                with open(TOOLS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for k, v in data.items():
                        self.tools[k] = MicroTool(**v)
            except Exception as e:
                logger.error(f"Failed to load custom tools from {TOOLS_FILE}: {e}")

    def _save_custom_tools(self):
        try:
            custom_only = {k: v.to_dict() for k, v in self.tools.items() if k not in BUILTIN_TOOLS}
            with open(TOOLS_FILE, "w", encoding="utf-8") as f:
                json.dump(custom_only, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save custom tools to {TOOLS_FILE}: {e}")

    def register_tool(
        self,
        tool_id: str,
        name: str,
        description: str,
        system_prompt: str,
        preferred_variant: str = "qwen25_coder_05b",
        output_type: str = "json",
    ) -> MicroTool:
        """Register a new custom automation tool for micro-models."""
        tool = MicroTool(
            id=tool_id,
            name=name,
            description=description,
            system_prompt=system_prompt,
            preferred_variant=preferred_variant,
            output_type=output_type,
        )
        self.tools[tool_id] = tool
        self._save_custom_tools()
        logger.info(f"Registered custom micro-tool: {tool_id}")
        return tool

    def get_tool(self, tool_id: str) -> MicroTool | None:
        return self.tools.get(tool_id)

    def list_tools(self) -> list[dict[str, Any]]:
        return [t.to_dict() for t in self.tools.values()]

    def execute_tool(
        self,
        tool_id: str,
        user_input: str,
        model_variant: str | None = None,
        max_tokens: int = 128,
    ) -> dict[str, Any]:
        """
        Execute an automated tool task on the dedicated micro-model via llama-cli.
        Runs in ~50-200ms on CPU/GPU without locking main VRAM.
        """
        tool = self.get_tool(tool_id)
        if not tool:
            return {"ok": False, "error": f"Tool '{tool_id}' not found"}

        variant_id = model_variant or tool.preferred_variant
        reg = get_registry()
        variant = reg.get_variant(variant_id)

        model_path = None
        if variant and variant.training_config.get("adopted_from"):
            # Check adopted model path on /opt/foveai-models
            from huggingface_hub import hf_hub_download
            repo = variant.training_config.get("adopted_from")
            filename = variant.training_config.get("file")
            cache_dir = os.environ.get("FORGE_NURSERY_MODELS_DIR", "/opt/foveai-models") + "/hub"
            try:
                model_path = hf_hub_download(repo_id=repo, filename=filename, cache_dir=cache_dir)
            except Exception:
                pass

        if not model_path or not os.path.exists(model_path):
            # Fallback search in /opt/foveai-models
            models_root = Path(os.environ.get("FORGE_NURSERY_MODELS_DIR", "/opt/foveai-models"))
            found = list(models_root.glob("**/*.gguf"))
            if found:
                model_path = str(found[0])

        if not model_path or not os.path.exists(model_path):
            return {"ok": False, "error": f"Micro-model binary not found on disk for {variant_id}"}

        # Build prompt with system instructions
        prompt = (
            f"<|im_start|>system\n{tool.system_prompt}<|im_end|>\n"
            f"<|im_start|>user\n{user_input}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )

        cmd = [
            LLAMA_CLI,
            "-m", model_path,
            "-p", prompt,
            "-n", str(max_tokens),
            "--temp", "0.2",
            "-ngl", "0",
            "--simple-io",
            "--no-display-prompt",
            "-st",
        ]

        env = os.environ.copy()
        env["LD_LIBRARY_PATH"] = f"{LLAMA_LIB_DIR}:{env.get('LD_LIBRARY_PATH', '')}"

        t0 = time.time()
        try:
            res = subprocess.run(
                cmd,
                env=env,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=20,
            )
            elapsed_ms = round((time.time() - t0) * 1000, 1)

            if res.returncode != 0:
                return {"ok": False, "error": res.stderr.strip() or "Process failed"}

            raw = res.stdout.strip()
            if "<|im_start|>assistant" in raw:
                content = raw.split("<|im_start|>assistant")[-1]
            elif "> " in raw:
                content = raw.split("> ")[-1]
                if user_input in content:
                    content = content.split(user_input)[-1]
            else:
                content = raw

            if "[ Prompt:" in content:
                content = content.split("[ Prompt:")[0]
            if "Exiting..." in content:
                content = content.split("Exiting...")[0]

            for stop in ["<|im_end|>", "<|endoftext|>"]:
                content = content.replace(stop, "")

            content = content.strip()

            parsed = content
            if tool.output_type == "json":
                import re
                m = re.search(r'(\{.*\}|\[.*\])', content, re.DOTALL)
                if m:
                    candidate = m.group(1).strip()
                    try:
                        parsed = json.loads(candidate)
                    except Exception:
                        parsed = {"raw": candidate}
                else:
                    parsed = {"raw": content}

            return {
                "ok": True,
                "tool_id": tool.id,
                "model_used": os.path.basename(model_path),
                "elapsed_ms": elapsed_ms,
                "result": parsed,
            }

        except Exception as e:
            return {"ok": False, "error": str(e)}


_engine_instance: MicroToolEngine | None = None


def get_micro_tool_engine() -> MicroToolEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = MicroToolEngine()
    return _engine_instance
