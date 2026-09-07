"""
SummarizerCompressor — Learned compression via GGUF summarizer models.

Wraps llama_cpp.Llama for GGUF inference and provides a drop-in
replacement for regex-based skeletonization in the TokenSlayer proxy.

Architecture:
  SummarizerCompressor
    ├── __init__(model_path, n_ctx, n_gpu_layers, verbose)
    ├── compress(code, level=3) -> str
    │   ├── level 3: deep skeleton (imports + signatures, bodies → ...)
    │   ├── level 4: symbol table (file:line name(params) — one-line)
    │   └── level 5: atomic (hash-based, expand on demand)
    ├── _build_prompt(code, level) -> str
    ├── _infer(prompt, max_tokens, temperature) -> str
    └── _fallback_skeletonize(code, level) -> str  # regex fallback

Integration:
  from summarizer_compressor import SummarizerCompressor
  compressor = SummarizerCompressor()
  skeleton = compressor.compress(source_code, level=3)

Dependencies:
  - llama_cpp (pip install llama-cpp-python)
  - GGUF model file (default: granite-3.3-2b-summarizer Q6_K)
"""

import os
import re
import hashlib
import logging
from typing import Optional

logger = logging.getLogger("SummarizerCompressor")

# Default model path — best candidate from evaluation (granite-3.3-2b, 5/6 quality)
DEFAULT_MODEL_PATH = os.path.join(
    os.path.expanduser("~"),
    ".cache", "huggingface",
    "sillykiwi", "granite-3.3-2b-summarizer-Q6_K-GGUF",
    "granite-3.3-2b-summarizer-q6_k.gguf"
)

# Fallback model paths (tried in order)
FALLBACK_MODEL_PATHS = [
    DEFAULT_MODEL_PATH,
    os.path.join(
        os.path.expanduser("~"),
        ".cache", "huggingface",
        "mradermacher", "Mixture-Summarizer-Qwen3.5-2B-i1-GGUF",
        "Mixture-Summarizer-Qwen3.5-2B.i1-Q6_K.gguf"
    ),
    os.path.join(
        os.path.expanduser("~"),
        ".cache", "huggingface",
        "ericflo", "qwen3-0.6b-summarizer",
        "qwen3-0.6b-summarizer-q8_0.gguf"
    ),
    os.path.join(
        os.path.expanduser("~"),
        ".cache", "huggingface",
        "llmware", "slim-summary-tiny-tool",
        "tiny-summary.gguf"
    ),
    os.path.join(
        os.path.expanduser("~"),
        ".cache", "huggingface", "hub",
        "models--unsloth--medgemma-1.5-4b-it-GGUF",
        "snapshots", "3855f948626b7ae42bccd082757f15078c53e758",
        "medgemma-1.5-4b-it-Q5_K_S.gguf"
    ),
    # Heavy lifter: TQL-Coder-Qwen3.5-4B-thinking (custom fine-tune, Qwen tokenizer)
    "F:\\Lumax\\Models\\Backend\\Cognition\\qwen\\TQL-Coder\\TQL-Coder-Qwen3.5-4B-thinking.IQ4_XS.gguf",
]

# Tokenizer format per model architecture
MODEL_FORMATS = {
    "granite": {
        "system_prefix": "<|start_of_role|>system<|end_of_role|>\n",
        "system_suffix": "<|end_of_text|>\n",
        "user_prefix": "<|start_of_role|>user<|end_of_role|>\n",
        "user_suffix": "<|end_of_text|>\n",
        "assistant_prefix": "<|start_of_role|>assistant<|end_of_role|>\n",
        "assistant_suffix": "<|end_of_text|>",
        "stop_tokens": ["<|end_of_text|>", "<|start_of_role|>"],
    },
    "qwen": {
        "system_prefix": "<|im_start|>system\n",
        "system_suffix": "<|im_end|>\n",
        "user_prefix": "<|im_start|>user\n",
        "user_suffix": "<|im_end|>\n",
        "assistant_prefix": "<|im_start|>assistant\n",
        "assistant_suffix": "<|im_end|>",
        "stop_tokens": ["<|im_end|>", "<|im_start|>"],
    },
}

# Level 3 prompt: deep skeleton (imports + signatures, bodies → ...)
LEVEL3_SYSTEM = """You are a code skeletonizer. Given a source file, output ONLY a compact structural skeleton showing:
1. All import/from statements
2. All class/function signatures with decorators
3. All top-level constants and type aliases

Strip ALL implementation bodies. Replace each function/class body with '...' on its own line.
Do NOT add explanations, markdown fences, or extra text. Preserve the original indentation."""

LEVEL3_USER = """{code}"""

# Level 4 prompt: symbol table (file:line name(params) — one-line)
LEVEL4_SYSTEM = """You are a code symbol table extractor. Given a source file, output ONLY a symbol table in this exact format:
file:line class/function_name(params) — one-line description

Rules:
- One symbol per line
- No imports, no bodies, no extra text
- Include ALL classes, functions, methods, and top-level constants
- For methods, prefix with ClassName.method_name
- Description should be max 80 chars, extracted from docstring or inferred from code"""

LEVEL4_USER = """{code}"""

# Level 5 prompt: atomic hash table (file:line #hash)
LEVEL5_SYSTEM = """You are a code atomic indexer. Given a source file, output ONLY an atomic symbol table in this exact format:
file:line #hash name(params)

Rules:
- One symbol per line
- No imports, no bodies, no extra text
- hash is a 4-char hex digest of the function/class body (first 4 chars of md5)
- Include ALL classes, functions, methods, and top-level constants"""

LEVEL5_USER = """{code}"""


class SummarizerCompressor:
    """Learned compression via GGUF summarizer model.
    
    Uses a small LLM to transform full code → compact structural skeleton,
    achieving better compression than regex-based skeletonizer for complex files.
    """
    
    def __init__(
        self,
        model_path: Optional[str] = None,
        n_ctx: int = 0,  # 0 = auto-detect from model metadata
        n_gpu_layers: int = 0,  # 0 = CPU offload (preserves GPU VRAM for main LLM)
        verbose: bool = False,
        auto_load: bool = True,
    ):
        self.model_path = model_path or DEFAULT_MODEL_PATH
        self.n_ctx = n_ctx if n_ctx > 0 else 0  # 0 = auto-detect
        self.n_gpu_layers = n_gpu_layers
        self.verbose = verbose
        self._llm = None
        self._format = self._detect_format()
        
        if auto_load:
            self._load_model()
    
    def _detect_format(self) -> dict:
        """Detect tokenizer format from model path."""
        path_lower = self.model_path.lower()
        if "granite" in path_lower:
            return MODEL_FORMATS["granite"]
        elif "qwen" in path_lower:
            return MODEL_FORMATS["qwen"]
        else:
            # Default to granite format
            logger.warning(f"Unknown model format for {self.model_path}, using granite format")
            return MODEL_FORMATS["granite"]
    
    def _load_model(self) -> bool:
        """Load the GGUF model via llama_cpp. Returns True on success."""
        if not os.path.exists(self.model_path):
            logger.error(f"Model not found: {self.model_path}")
            return False
        
        try:
            from llama_cpp import Llama
            logger.info(f"Loading model: {self.model_path}")
            self._llm = Llama(
                model_path=self.model_path,
                n_ctx=self.n_ctx,
                n_gpu_layers=self.n_gpu_layers,
                verbose=self.verbose,
            )
            logger.info(f"Model loaded: {os.path.basename(self.model_path)}")
            return True
        except ImportError:
            logger.error("llama_cpp not installed. Install with: pip install llama-cpp-python")
            return False
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            return False
    
    @property
    def is_loaded(self) -> bool:
        """Check if model is loaded and ready."""
        return self._llm is not None
    
    def _build_prompt(self, code: str, level: int) -> str:
        """Build a prompt for the given compression level."""
        fmt = self._format
        
        if level == 3:
            system_content = LEVEL3_SYSTEM
            user_content = LEVEL3_USER.format(code=code)
        elif level == 4:
            system_content = LEVEL4_SYSTEM
            user_content = LEVEL4_USER.format(code=code)
        elif level == 5:
            system_content = LEVEL5_SYSTEM
            user_content = LEVEL5_USER.format(code=code)
        else:
            logger.warning(f"Unknown level {level}, defaulting to level 3")
            return self._build_prompt(code, 3)
        
        prompt = (
            f"{fmt['system_prefix']}{system_content}{fmt['system_suffix']}"
            f"{fmt['user_prefix']}{user_content}{fmt['user_suffix']}"
            f"{fmt['assistant_prefix']}"
        )
        return prompt
    
    def _infer(self, prompt: str, max_tokens: int = 1024, temperature: float = 0.1) -> Optional[str]:
        """Run inference on the loaded model."""
        if not self.is_loaded:
            logger.warning("Model not loaded, cannot infer")
            return None
        
        try:
            output = self._llm(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                stop=self._format["stop_tokens"],
                echo=False,
            )
            result = output["choices"][0]["text"].strip()
            return result
        except Exception as e:
            logger.error(f"Inference failed: {e}")
            return None
    
    def compress(self, code: str, level: int = 3) -> str:
        """Compress code to a structural skeleton using the learned model.
        
        Args:
            code: Full source code to compress
            level: Compression level (3=deep, 4=ultra, 5=atomic)
            
        Returns:
            Structural skeleton string, or regex fallback if model fails
        """
        if not code or len(code) < 50:
            return code  # Small code passes through
        
        # Try learned compression first
        if self.is_loaded:
            prompt = self._build_prompt(code, level)
            result = self._infer(prompt)
            if result and len(result) > 10:
                logger.info(f"Learned compression: {len(code)} → {len(result)} chars ({len(result)/max(len(code),1)*100:.1f}%)")
                return result
        
        # Fallback to regex-based skeletonization
        logger.info("Falling back to regex skeletonization")
        return self._fallback_skeletonize(code, level)
    
    def _fallback_skeletonize(self, code: str, level: int = 3) -> str:
        """Regex-based fallback skeletonization (same as proxy's _extract_skeleton)."""
        lines = code.split("\n")
        
        if level == 4:
            # Symbol table: file:line name(params) — one-line
            symbols = []
            for i, line in enumerate(lines):
                stripped = line.strip()
                # Class definitions
                class_match = re.match(r'^(?:class\s+(\w+)(?:\(.*?\))?\s*:)', stripped)
                if class_match:
                    symbols.append(f"file:line {class_match.group(1)}()")
                    continue
                # Function definitions
                func_match = re.match(r'^(?:async\s+)?def\s+(\w+)\s*\((.*?)\)\s*(?:->.*?)?\s*:', stripped)
                if func_match:
                    symbols.append(f"file:line {func_match.group(1)}({func_match.group(2)})")
                    continue
                # Top-level constants
                const_match = re.match(r'^(\w+)\s*[=:]', stripped)
                if const_match and not stripped.startswith(('import ', 'from ', '#', '"""', "'''")):
                    symbols.append(f"file:line {const_match.group(1)}")
            return "\n".join(symbols) if symbols else f"# [TokenSlayer Fallback: Level 4]\n# No symbols detected"
        
        elif level == 5:
            # Atomic: file:line #hash name(params)
            symbols = []
            for i, line in enumerate(lines):
                stripped = line.strip()
                class_match = re.match(r'^(?:class\s+(\w+)(?:\(.*?\))?\s*:)', stripped)
                if class_match:
                    h = hashlib.md5(stripped.encode()).hexdigest()[:4]
                    symbols.append(f"file:line #{h} {class_match.group(1)}()")
                    continue
                func_match = re.match(r'^(?:async\s+)?def\s+(\w+)\s*\((.*?)\)\s*(?:->.*?)?\s*:', stripped)
                if func_match:
                    h = hashlib.md5(stripped.encode()).hexdigest()[:4]
                    symbols.append(f"file:line #{h} {func_match.group(1)}({func_match.group(2)})")
                    continue
            return "\n".join(symbols) if symbols else f"# [TokenSlayer Fallback: Level 5]\n# No symbols detected"
        
        else:
            # Level 3: deep skeleton (default)
            skeleton = []
            for line in lines:
                trimmed = line.strip()
                if trimmed.startswith(("import ", "from ", "def ", "class ", "async def ", "@", "export ", "function ", "interface ", "type ", "struct ", "const ", "let ", "var ", "fn ", "pub ", "impl ", "trait ", "enum ")):
                    skeleton.append(line + (" ..." if ":" in line or "{" in line else ""))
                elif "{" in line or "}" in line:
                    skeleton.append(line)
            
            if len(skeleton) < 2:
                half = len(code) // 2
                return f"{code[:500]}\n...\n[Massive file truncated by TokenSlayer Fallback]\n...\n{code[-min(500, len(code) - half):]}"
            
            return "\n".join(skeleton)


# Global singleton (lazy-loaded)
_COMPRESSOR_INSTANCE = None


def get_compressor(
    model_path: Optional[str] = None,
    n_ctx: int = 0,  # 0 = auto-detect from model metadata
    n_gpu_layers: int = 0,
) -> SummarizerCompressor:
    """Get or create the global SummarizerCompressor singleton."""
    global _COMPRESSOR_INSTANCE
    if _COMPRESSOR_INSTANCE is None:
        _COMPRESSOR_INSTANCE = SummarizerCompressor(
            model_path=model_path,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            auto_load=True,
        )
    return _COMPRESSOR_INSTANCE


# Quick test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    test_code = '''import asyncio
from typing import Optional

class Server:
    """Async HTTP server."""
    def __init__(self, host: str = "localhost", port: int = 8080):
        self.host = host
        self.port = port
    
    async def start(self) -> None:
        """Start the server."""
        self._server = await asyncio.start_server(
            self._handle_client, host=self.host, port=self.port
        )
        async with self._server:
            await self._server.serve_forever()
    
    async def _handle_client(self, reader, writer):
        data = await reader.read(1024)
        writer.write(data)
        await writer.drain()
        writer.close()

async def main():
    server = Server()
    await server.start()
'''
    
    print("=" * 60)
    print("SummarizerCompressor Test")
    print("=" * 60)
    print(f"Input: {len(test_code)} chars, {len(test_code.splitlines())} lines")
    
    compressor = get_compressor()
    
    for level in [3, 4, 5]:
        print(f"\n--- Level {level} ---")
        result = compressor.compress(test_code, level=level)
        print(f"Output: {len(result)} chars ({len(result)/len(test_code)*100:.1f}% of original)")
        print(result[:500])
        print("..." if len(result) > 500 else "")