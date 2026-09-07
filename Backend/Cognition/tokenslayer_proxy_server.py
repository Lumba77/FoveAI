import json
import logging
import httpx
import re
import hashlib
import os
import sys
from fastapi import FastAPI, Request, Query
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

# Ensure Forge is in path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "Forge")))
# Ensure Tools/foveai-xrl/xrs is in path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "Tools", "foveai-xrl", "xrs")))

try:
    # pyrefly: ignore [missing-import]
    from context_stripper import ContextStripper
except ImportError:
    ContextStripper = None

try:
    import importlib
    xrl_mcp_bridge = importlib.import_module("xrl-mcp-bridge")
except ImportError:
    xrl_mcp_bridge = None

# Optional: SummarizerCompressor for learned compression
try:
    from summarizer_compressor import get_compressor, SummarizerCompressor
    _COMPRESSOR = None  # Lazy-loaded
except ImportError:
    get_compressor = None
    SummarizerCompressor = None
    _COMPRESSOR = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TokenSlayerProxy")

app = FastAPI(title="TokenSlayer Proxy Server", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEFAULT_DOWNSTREAM_URL = "https://ollama.com/v1/chat/completions"
CACHE_FILE = os.path.join(os.path.dirname(__file__), "proxy_cache.json")
RAW_NODES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", ".gemini", "cache", "raw_nodes")
os.makedirs(RAW_NODES_DIR, exist_ok=True)

# ============================================================
# TIER CONFIGURATION
# ============================================================
# Context window thresholds (in tokens)
TIER_THRESHOLDS = {
    "micro": 4096,     # <4K context → micro-skeleton only
    "standard": 32768, # 4K-32K → standard skeleton
    "full": 999999,    # >32K → full skeleton (use large int, not inf, for JSON compat)
}

# Default context windows for known local models
LOCAL_MODEL_CONTEXTS = {
    "qwen2.5:0.5b": 32768,
    "qwen2.5:1.5b": 32768,
    "qwen3.5:4b": 32768,
    "llama3.2:1b": 8192,
    "llama3.2:3b": 8192,
    "phi3:mini": 128000,
    "phi3:small": 128000,
    "gemma2:2b": 8192,
    "gemma2:7b": 8192,
    "mistral:7b": 32768,
    "default": 4096,  # fallback for unknown models
}

# Sidecar cache for atomic hash expansion
ATOMIC_CACHE_FILE = os.path.join(os.path.dirname(__file__), "atomic_cache.json")

# XRL Protocol namespace
XRL_NAMESPACE = "foveai"

def load_atomic_cache() -> dict:
    """Load the atomic hash → signature mapping."""
    if os.path.exists(ATOMIC_CACHE_FILE):
        try:
            with open(ATOMIC_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_atomic_cache(cache: dict):
    """Save the atomic hash → signature mapping."""
    try:
        with open(ATOMIC_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save atomic cache: {e}")

_ATOMIC_CACHE = load_atomic_cache()

# ============================================================
# XRL PROTOCOL — eXpandable Reference Links
# ============================================================
def generate_xrl(filepath: str, line: int, content: str, namespace: str = XRL_NAMESPACE) -> str:
    """Generate an XRL URI for a code location.
    Format: xrl://{namespace}/{filepath}:{line}:{hash6}"""
    content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
    hash6 = content_hash[:6]
    return f"xrl://{namespace}/{filepath}:{line}:{hash6}"

def parse_xrl(uri: str) -> Optional[dict]:
    """Parse an XRL URI into its components.
    Format: xrl://{namespace}/{filepath}:{line}:{hash6}
    Returns dict with namespace, filepath, line, hash or None if invalid."""
    try:
        if not uri.startswith("xrl://"):
            return None
        parts = uri.replace("xrl://", "").split("/", 1)
        if len(parts) != 2:
            return None
        namespace = parts[0]
        rest = parts[1]
        # Find the last two colons for line:hash6
        last_colon = rest.rfind(":")
        if last_colon == -1:
            return None
        second_last_colon = rest.rfind(":", 0, last_colon)
        if second_last_colon == -1:
            return None
        filepath = rest[:second_last_colon]
        line = int(rest[second_last_colon+1:last_colon])
        hash6 = rest[last_colon+1:]
        return {
            "namespace": namespace,
            "filepath": filepath,
            "line": line,
            "hash": hash6
        }
    except (ValueError, IndexError):
        return None

def register_xrl_in_cache(filepath: str, line: int, content: str, signature: str, namespace: str = XRL_NAMESPACE) -> str:
    """Generate an XRL URI and register it in the atomic cache."""
    uri = generate_xrl(filepath, line, content, namespace)
    content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
    hash6 = content_hash[:6]
    node_tag = f"tag_{hash6}"
    
    _ATOMIC_CACHE[uri] = {
        "signature": signature,
        "filepath": filepath,
        "line": line,
        "hash": hash6,
        "namespace": namespace,
        "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat().replace("+00:00", "Z"),
        "version": 1,
        "content_hash": content_hash,
        "raw_node_path": os.path.join(RAW_NODES_DIR, f"{node_tag}.txt")
    }
    save_atomic_cache(_ATOMIC_CACHE)
    return uri

# ============================================================
# CONTEXT WINDOW DETECTION
# ============================================================
def detect_context_window(model_name: str, mode: str = "cloud") -> int:
    """Detect the model's context window and return the appropriate tier."""
    if mode == "local":
        # For local models, check known context windows
        model_lower = model_name.lower()
        for known_model, ctx in LOCAL_MODEL_CONTEXTS.items():
            if known_model in model_lower:
                logger.info(f"📏 Detected local model '{model_name}' with {ctx} context window")
                return ctx
        logger.info(f"📏 Unknown local model '{model_name}', assuming {LOCAL_MODEL_CONTEXTS['default']} context")
        return LOCAL_MODEL_CONTEXTS["default"]
    else:
        # Cloud models typically have large context windows
        return 128000  # conservative estimate for cloud models

def select_tier(context_window: int) -> str:
    """Select the appropriate skeleton tier based on context window size."""
    for tier, threshold in sorted(TIER_THRESHOLDS.items(), key=lambda x: x[1]):
        if context_window <= threshold:
            logger.info(f"🎯 Selected tier '{tier}' for {context_window} context window")
            return tier
    return "full"

# ============================================================
# ON-DEMAND EXPANSION
# ============================================================
def expand_hash(hash_id: str) -> Optional[str]:
    """Expand an atomic hash back to its full signature."""
    if hash_id in _ATOMIC_CACHE:
        return _ATOMIC_CACHE[hash_id]
    return None

def expand_file_line(filepath: str, line_num: int, context_lines: int = 3) -> Optional[str]:
    """Expand a file:line reference to show surrounding context."""
    try:
        full_path = os.path.join(os.path.dirname(__file__), "..", "..", filepath)
        if not os.path.exists(full_path):
            # Try relative to FoveAI root
            full_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", filepath)
        if not os.path.exists(full_path):
            return None
        
        with open(full_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        start = max(0, line_num - context_lines - 1)
        end = min(len(lines), line_num + context_lines)
        
        result = []
        for i in range(start, end):
            prefix = "→" if i == line_num - 1 else " "
            result.append(f"{prefix} {i+1}: {lines[i].rstrip()}")
        
        return "\n".join(result)
    except Exception as e:
        logger.error(f"Failed to expand {filepath}:{line_num}: {e}")
        return None

# ============================================================
# SEMANTIC SKELETON MODE (Local LLM)
# ============================================================
def _call_local_llm_for_summary(filepath: str, content_preview: str) -> str:
    """Use the local LLM middleman to generate a semantic summary of a file."""
    try:
        # Try to call the local LLM via the MCP server's middleman
        import urllib.request
        import urllib.error
        
        prompt = f"""Summarize this file in ONE LINE (max 120 chars). Focus on what it DOES, not how it's structured.
File: {filepath}
First 500 chars: {content_preview[:500]}"""
        
        payload = json.dumps({
            "model": "qwen3.5-4b",
            "messages": [
                {"role": "system", "content": "You are a concise code summarizer. Output ONLY the one-line summary, nothing else."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 50,
            "temperature": 0.1
        }).encode("utf-8")
        
        req = urllib.request.Request(
            "http://127.0.0.1:8002/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            summary = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            if summary:
                return summary[:120]
    except Exception as e:
        logger.debug(f"Local LLM summary failed for {filepath}: {e}")
    
    # Fallback: extract first docstring line
    doc_match = re.search(r'"""(.*?)"""', content_preview, re.DOTALL)
    if doc_match:
        return doc_match.group(1).strip().split('\n')[0][:120]
    return ""

# ============================================================
# API KEY LOADING
# ============================================================
def _load_api_key():
    """Try env vars first, then read from .env file."""
    key = os.environ.get("FoveAI_PROXY_API_KEY", "") or os.environ.get("OLLAMA_API_KEY", "")
    if key:
        return key
    env_paths = [
        os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"),
        os.path.join(os.path.dirname(__file__), "..", "..", ".env"),
    ]
    for env_path in env_paths:
        env_path = os.path.abspath(env_path)
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, _, v = line.partition("=")
                            k = k.strip()
                            v = v.strip().strip('"').strip("'")
                            if k in ("OLLAMA_API_KEY", "FoveAI_PROXY_API_KEY") and v:
                                logger.info(f"🔑 Loaded API key from {env_path}")
                                return v
            except Exception:
                pass
    logger.warning("⚠️ No Ollama API key found — requests will be unauthorized")
    return ""

OLLAMA_API_KEY = _load_api_key()

# ============================================================
# CACHE
# ============================================================
def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cache(cache):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except Exception as e:
        logger.error(f"Failed to save cache: {e}")

_AI_CACHE = load_cache()

# ============================================================
# SKELETONIZATION HELPERS
# ============================================================
def _extract_skeleton(code: str, lang: str = "") -> tuple[str, str]:
    """Extract a structural skeleton from code. Returns (skeleton_text, node_tag)."""
    node_tag = "tag_" + hashlib.md5(code.encode("utf-8")).hexdigest()[:6]
    raw_file_path = os.path.abspath(os.path.join(RAW_NODES_DIR, f"{node_tag}.txt"))
    
    try:
        with open(raw_file_path, "w", encoding="utf-8") as f:
            f.write(code)
    except Exception as e:
        logger.error(f"Failed to side-cache raw node {node_tag}: {e}")

    lines = code.split("\n")
    skeleton = []
    for line in lines:
        trimmed = line.strip()
        if trimmed.startswith(("import ", "from ", "def ", "class ", "async def ", "@", "export ", "function ", "interface ", "type ", "struct ", "const ", "let ", "var ", "fn ", "pub ", "impl ", "trait ", "enum ", "case ", "object ", "trait ")):
            skeleton.append(line + (" ..." if ":" in line or "{" in line else ""))
        elif "{" in line or "}" in line:
            skeleton.append(line)
    
    if len(skeleton) < 2:
        half = len(code) // 2
        return f"{code[:500]}\n...\n[Massive file truncated by TokenSlayer Devourer]\n...\n{code[-min(500, len(code) - half):]}", node_tag
    
    return "\n".join(skeleton), node_tag

def _extract_symbol_content(lines: list, start_line: int) -> str:
    """Extract the full content of a symbol starting at start_line.
    Continues until the next top-level definition at same or lesser indent, or end of file.
    Handles both indentation-based (Python) and brace-based (JS/TS/Rust) languages."""
    content_lines = []
    indent = None
    brace_depth = 0
    in_braces = False
    
    for i in range(start_line, len(lines)):
        line = lines[i]
        if i == start_line:
            content_lines.append(line)
            stripped = line.lstrip()
            indent = len(line) - len(stripped)
            # Check if this line opens a brace block
            if "{" in stripped:
                in_braces = True
                brace_depth = stripped.count("{") - stripped.count("}")
            continue
        
        stripped = line.strip()
        current_indent = len(line) - len(line.lstrip())
        
        if in_braces:
            # Brace-based language (JS/TS/Rust/C#/Java)
            brace_depth += stripped.count("{") - stripped.count("}")
            content_lines.append(line)
            if brace_depth <= 0:
                break
        else:
            # Indentation-based language (Python)
            if stripped and not stripped.startswith(("#", "//", "/*", "*", "'''", '"""')):
                # Check if this is a new top-level definition at same or lesser indent
                if current_indent <= indent and any(
                    stripped.startswith(prefix) for prefix in 
                    ("def ", "class ", "async def ", "function ", "fn ", "pub ", 
                     "impl ", "trait ", "enum ", "struct ", "interface ", "type ", 
                     "export ", "const ", "let ", "var ")
                ):
                    break
            content_lines.append(line)
    
    return "\n".join(content_lines)


def _extract_symbols_and_register(code: str, source_hint: str = "") -> list:
    """Parse code to find function/class symbols and register each in atomic cache with XRL URIs.
    Returns list of XRL URIs for all extracted symbols."""
    if not source_hint:
        return []
    
    xrl_uris = []
    lines = code.split("\n")
    
    # Patterns that indicate a symbol definition — ordered by specificity
    symbol_patterns = [
        (r"^\s*(?:async\s+)?def\s+(\w+)", "function"),
        (r"^\s*class\s+(\w+)", "class"),
        (r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*(?:\*\s*)?(\w+)", "function"),
        (r"^\s*(?:export\s+)?(?:default\s+)?class\s+(\w+)", "class"),
        (r"^\s*(?:export\s+)?interface\s+(\w+)", "interface"),
        (r"^\s*(?:export\s+)?type\s+(\w+)", "type"),
        (r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+(\w+)", "function"),
        (r"^\s*(?:pub\s+)?struct\s+(\w+)", "struct"),
        (r"^\s*(?:pub\s+)?trait\s+(\w+)", "trait"),
        (r"^\s*(?:pub\s+)?enum\s+(\w+)", "enum"),
        (r"^\s*(?:pub\s+)?impl\s+(?:\w+\s+)?(?:for\s+\w+\s+)?(?:{)?", "impl"),
    ]
    
    for i, line in enumerate(lines):
        trimmed = line.strip()
        for pattern, sym_type in symbol_patterns:
            match = re.match(pattern, trimmed)
            if match:
                symbol_name = match.group(1) if match.lastindex and match.lastindex >= 1 else f"{sym_type}_{i}"
                # Extract content for this symbol
                symbol_content = _extract_symbol_content(lines, i)
                uri = register_xrl_in_cache(
                    filepath=source_hint,
                    line=i + 1,
                    content=symbol_content,
                    signature=trimmed
                )
                xrl_uris.append(uri)
                break
    
    return xrl_uris

def _learned_extract_skeleton(code: str, lang: str = "", level: int = 3) -> tuple[str, str]:
    """Extract a structural skeleton using the SummarizerCompressor (learned compression).
    Falls back to regex-based _extract_skeleton if compressor is unavailable or fails.
    Returns (skeleton_text, node_tag)."""
    node_tag = "tag_" + hashlib.md5(code.encode("utf-8")).hexdigest()[:6]
    raw_file_path = os.path.abspath(os.path.join(RAW_NODES_DIR, f"{node_tag}.txt"))
    
    try:
        with open(raw_file_path, "w", encoding="utf-8") as f:
            f.write(code)
    except Exception as e:
        logger.error(f"Failed to side-cache raw node {node_tag}: {e}")

    # Try learned compression
    if get_compressor is not None:
        global _COMPRESSOR
        try:
            if _COMPRESSOR is None:
                _COMPRESSOR = get_compressor()
            compressed = _COMPRESSOR.compress(code, level=level)
            if compressed and len(compressed) < len(code) * 0.9:
                logger.info(f"🧠 Learned compression: {len(code)} → {len(compressed)} chars ({100 - (len(compressed)/len(code)*100):.0f}% reduction)")
                return compressed, node_tag
        except Exception as e:
            logger.warning(f"🧠 Learned compression failed, falling back to regex: {e}")
    
    # Fallback to regex-based skeletonization
    return _extract_skeleton(code, lang)


def _build_skeleton_block(code: str, lang: str = "", source_hint: str = "", use_learned: bool = False, skeleton_override: Optional[str] = None) -> str:
    """Build a complete skeleton block with header, XRL URIs, and raw node reference.
    If use_learned=True, attempts learned compression via SummarizerCompressor.
    If skeleton_override is provided, uses it instead of extracting from code.
    Registers each extracted symbol in the atomic cache with XRL URIs."""
    if skeleton_override:
        skeleton = skeleton_override
        node_tag = hashlib.md5(skeleton.encode()).hexdigest()[:6]
    elif use_learned:
        skeleton, node_tag = _learned_extract_skeleton(code, lang)
    else:
        skeleton, node_tag = _extract_skeleton(code, lang)
    raw_file_path = os.path.abspath(os.path.join(RAW_NODES_DIR, f"{node_tag}.txt"))
    
    # Register all extracted symbols in atomic cache with XRL URIs
    xrl_uris = []
    if source_hint:
        xrl_uris = _extract_symbols_and_register(code, source_hint)
    
    # Also register the first meaningful signature line for backward compatibility
    first_sig_line = ""
    for line in skeleton.split("\n"):
        stripped = line.strip()
        if stripped and not stripped.startswith(("#", "//", "/*", "*", "<!--", "import ", "from ", "export ", "package ", "use ", "require")):
            first_sig_line = stripped
            break
    
    if source_hint and first_sig_line and not xrl_uris:
        # Only register first sig line if _extract_symbols_and_register didn't find anything
        first_uri = register_xrl_in_cache(
            filepath=source_hint,
            line=1,
            content=code,
            signature=first_sig_line
        )
        if first_uri:
            xrl_uris.append(first_uri)
    
    header_parts = [
        f"```{lang}",
        f"# [TokenSlayer Devourer: Structural Skeleton Only]",
        f"# RAW CONTEXT NODE: {node_tag}",
    ]
    if xrl_uris:
        header_parts.append(f"# XRL: {xrl_uris[0]}")
        if len(xrl_uris) > 1:
            header_parts.append(f"# XRL_SYMBOLS: {len(xrl_uris)} symbols registered")
            # Add compact symbol table
            for uri in xrl_uris[:10]:  # Show first 10 in header
                header_parts.append(f"#   {uri}")
            if len(xrl_uris) > 10:
                header_parts.append(f"#   ... and {len(xrl_uris) - 10} more")
    if source_hint:
        header_parts.append(f"# Source: {source_hint}")
    if use_learned:
        header_parts.append(f"# Compression: learned (SummarizerCompressor)")
    
    # Build expand hint with all URIs
    expand_hint = ""
    if xrl_uris:
        uris_json = ",".join(xrl_uris[:5])  # First 5 for the hint
        expand_hint = f"curl -X POST http://localhost:8103/api/xrl/expand -H 'Content-Type: application/json' -d '{{\"uris\": [\"{uris_json}\"]}}'"
    
    header_parts.extend([
        f"# The uncompressed raw code was automatically saved at the side to:",
        f"# {raw_file_path}",
    ])
    if expand_hint:
        header_parts.append(f"# (To expand, use: {expand_hint})")
    
    return "\n".join(header_parts) + "\n" + skeleton + "\n```"


# ============================================================
# PLAIN TEXT CODE DETECTION
# ============================================================
# Patterns that indicate a line is likely code (not prose)
_CODE_INDICATORS = [
    r"^(import |from |def |class |async def |@\w|export |function |interface |type |struct |const |let |var |fn |pub |impl |trait |enum )",
    r"^[a-zA-Z_][\w.]*\s*[=:]\s*(lambda |def |class |\[|\{|\()",
    r"^# (include|define|pragma|ifndef|endif)",
    r"^package\s+[a-zA-Z]",
    r"^use\s+[a-zA-Z]",
    r"^require\(|^import\s+\{",
    r"^from\s+[a-zA-Z]",
    r"^@\w+",
    r"^\/\/",
    r"^\/\*",
    r"^\s*#",
]

# File extension patterns for detecting file path references
_FILE_PATH_PATTERN = re.compile(
    r'(?:^|\s)(?:[A-Za-z]:\\[^\s:]+|\.\.?/[^\s:]+|[a-zA-Z_][\w./-]*\.(?:py|js|ts|jsx|tsx|go|rs|java|kt|cs|cpp|c|h|hpp|rb|php|swift|scala|ex|exs|vue|svelte|css|scss|less|html|xml|yaml|yml|json|toml|md|sql|sh|bash|zsh|fish|ps1|bat|cmd))(?::\d+)?(?:\s|$)'
)

# Thresholds for auto-skeletonization
_AUTO_SKELETON_MIN_LINES = 10
_AUTO_SKELETON_MIN_CHARS = 500
_CODE_LINE_RATIO_THRESHOLD = 0.3  # 30% of lines must look like code


def _looks_like_code(text_block: str) -> bool:
    """Check if a text block looks like code (not prose)."""
    lines = text_block.split("\n")
    if len(lines) < 3:
        return False
    
    code_lines = 0
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(("# ", "// ", "/*", "* ", "<!--")):
            continue
        for pattern in _CODE_INDICATORS:
            if re.match(pattern, stripped):
                code_lines += 1
                break
    
    ratio = code_lines / len(lines) if lines else 0
    return ratio >= _CODE_LINE_RATIO_THRESHOLD


def _find_code_blocks_in_text(text: str) -> list[tuple[int, int, str]]:
    """Find contiguous code-like blocks in plain text (no markdown fences).
    Returns list of (start_pos, end_pos, block_text)."""
    lines = text.split("\n")
    blocks = []
    current_start = None
    current_lines = []
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Skip empty lines
        if not stripped:
            if current_start is not None and len(current_lines) >= _AUTO_SKELETON_MIN_LINES:
                block_text = "\n".join(current_lines)
                if len(block_text) >= _AUTO_SKELETON_MIN_CHARS and _looks_like_code(block_text):
                    start_pos = sum(len(l) + 1 for l in lines[:current_start])
                    end_pos = start_pos + len(block_text)
                    blocks.append((start_pos, end_pos, block_text))
            current_start = None
            current_lines = []
            continue
        
        # Check if this line looks like code
        is_code = False
        for pattern in _CODE_INDICATORS:
            if re.match(pattern, stripped):
                is_code = True
                break
        
        if is_code:
            if current_start is None:
                current_start = i
            current_lines.append(line)
        else:
            if current_start is not None and len(current_lines) >= _AUTO_SKELETON_MIN_LINES:
                block_text = "\n".join(current_lines)
                if len(block_text) >= _AUTO_SKELETON_MIN_CHARS and _looks_like_code(block_text):
                    start_pos = sum(len(l) + 1 for l in lines[:current_start])
                    end_pos = start_pos + len(block_text)
                    blocks.append((start_pos, end_pos, block_text))
            current_start = None
            current_lines = []
    
    # Handle block at end of text
    if current_start is not None and len(current_lines) >= _AUTO_SKELETON_MIN_LINES:
        block_text = "\n".join(current_lines)
        if len(block_text) >= _AUTO_SKELETON_MIN_CHARS and _looks_like_code(block_text):
            start_pos = sum(len(l) + 1 for l in lines[:current_start])
            end_pos = start_pos + len(block_text)
            blocks.append((start_pos, end_pos, block_text))
    
    return blocks


def _detect_file_paths(text: str) -> list[str]:
    """Detect file path references in text and return unique paths."""
    matches = _FILE_PATH_PATTERN.findall(text)
    # Clean up matches (remove trailing colon+line numbers)
    cleaned = []
    for m in matches:
        m = m.strip()
        if ":" in m and m.count(":") == 1:
            # Could be file:line — check if the part after : is a number
            parts = m.split(":")
            if parts[-1].isdigit():
                m = parts[0]
        if m not in cleaned:
            cleaned.append(m)
    return cleaned


def auto_skeletonize_plain_text(text: str) -> str:
    """Detect large code-like blocks in plain text and skeletonize them.
    This catches file content that's embedded without markdown fences."""
    blocks = _find_code_blocks_in_text(text)
    if not blocks:
        return text
    
    # Process blocks in reverse order to preserve positions
    result = text
    for start, end, block_text in reversed(blocks):
        skeleton_block = _build_skeleton_block(block_text, lang="", source_hint="auto-detected code block")
        result = result[:start] + skeleton_block + result[end:]
        logger.info(f"💀 Auto-skeletonized plain text block ({len(block_text)} chars → skeleton)")
    
    return result


def skeletonize_file_content(filepath: str, level: int = 3, source_hint: str = "") -> Optional[str]:
    """Read a file and return its TokenSlayer skeleton.
    Uses the standalone CLI if available, otherwise falls back to inline extraction.
    If source_hint is provided, registers XRL entries in the atomic cache."""
    try:
        # Resolve full path first (needed for both CLI and fallback)
        full_path = os.path.abspath(filepath)
        if not os.path.exists(full_path):
            full_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", filepath)
            full_path = os.path.abspath(full_path)
        if not os.path.exists(full_path):
            return None
        
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        if len(content) < 100:
            return content  # Small files pass through
        
        lang = os.path.splitext(filepath)[1].lstrip(".")
        effective_hint = source_hint or filepath
        skeleton_text = None
        
        # 1. Try XRL MCP Bridge (calls xrs.cjs)
        if xrl_mcp_bridge:
            try:
                # Map level to depth (0-3 is supported)
                depth = level if level <= 3 else 3
                data = xrl_mcp_bridge.skeletonize(full_path, depth=depth)
                if data and "skeleton" in data and "content" in data["skeleton"]:
                    skeleton_text = data["skeleton"]["content"]
                    logger.info(f"💀 Skeletonized {filepath} via xrl_mcp_bridge (xrs.cjs)")
            except Exception as e:
                logger.warning(f"Failed to skeletonize via xrl_mcp_bridge: {e}")
                
        # 2. Try standalone tokenslayer.js CLI
        if not skeleton_text:
            import subprocess
            cli_path = os.path.abspath(os.path.join(
                os.path.dirname(__file__), "..", "..", "Forge", "scratch", "TokenSlayer", "standalone", "tokenslayer.js"
            ))
            if os.path.exists(cli_path):
                try:
                    result = subprocess.run(
                        ["node", cli_path, filepath, f"--level", str(level)],
                        capture_output=True, text=True, timeout=10
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        skeleton_text = result.stdout.strip()
                        logger.info(f"💀 Skeletonized {filepath} via tokenslayer.js")
                except Exception as e:
                    logger.warning(f"Failed running tokenslayer.js: {e}")
        
        # 3. Fallback: inline extraction
        if not skeleton_text:
            skeleton_text, _ = _extract_skeleton(content, lang)
            logger.info(f"💀 Skeletonized {filepath} via inline python extraction")
        
        # Build skeleton block with XRL registration (always, even when CLI succeeds)
        return _build_skeleton_block(content, lang=lang, source_hint=effective_hint, use_learned=False, skeleton_override=skeleton_text)
    except Exception as e:
        logger.error(f"Failed to skeletonize {filepath}: {e}")
        return None


# ============================================================
# DEVOUR SKELETONS (enhanced)
# ============================================================
def devour_skeletons(text: str, use_learned: bool = False) -> str:
    """Detects large code blocks (fenced AND plain text), saves raw content to side-cache, and shrinks to structural skeletons.
    If use_learned=True, attempts learned compression via SummarizerCompressor (GGUF model)."""
    def replacer(match):
        lang = match.group(1)
        code = match.group(2)
        if len(code) < 1500:
            return match.group(0)
        return _build_skeleton_block(code, lang, use_learned=use_learned)

    # Step 1: Process markdown-fenced code blocks
    result = re.sub(r"```(\w*)\n(.*?)```", replacer, text, flags=re.DOTALL)
    
    # Step 2: Auto-skeletonize plain text code blocks (no markdown fences)
    result = auto_skeletonize_plain_text(result)
    
    # Step 3: Detect file path references and annotate
    file_paths = _detect_file_paths(result)
    if file_paths:
        logger.info(f"📁 Detected {len(file_paths)} file path references in message")
    
    return result

# ============================================================
# STREAMING HELPERS
# ============================================================
async def _stream_generator(response):
    async for chunk in response.aiter_bytes():
        yield chunk

async def _mock_stream_generator(text_content):
    chunk_size = 20
    for i in range(0, len(text_content), chunk_size):
        chunk = text_content[i:i+chunk_size]
        data = {
            "id": "chatcmpl-cached",
            "object": "chat.completion.chunk",
            "model": "cached-model",
            "choices": [{"index": 0, "delta": {"content": chunk}, "finish_reason": None}]
        }
        yield f"data: {json.dumps(data)}\n\n".encode("utf-8")
        
    final_data = {
        "id": "chatcmpl-cached",
        "object": "chat.completion.chunk",
        "model": "cached-model",
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
    }
    yield f"data: {json.dumps(final_data)}\n\n".encode("utf-8")
    yield b"data: [DONE]\n\n"

# ============================================================
# EXPANSION ENDPOINTS
# ============================================================
class ExpandRequest(BaseModel):
    hash_id: Optional[str] = None
    filepath: Optional[str] = None
    line: Optional[int] = None
    context_lines: Optional[int] = 3

@app.post("/api/expand")
async def api_expand(request: ExpandRequest):
    """Expand an atomic hash or file:line reference back to full context."""
    if request.hash_id:
        result = expand_hash(request.hash_id)
        if result:
            return {"expanded": result, "source": "atomic_cache"}
        return JSONResponse(status_code=404, content={"error": f"Hash '{request.hash_id}' not found in atomic cache"})
    
    if request.filepath and request.line:
        result = expand_file_line(request.filepath, request.line, request.context_lines)
        if result:
            return {"expanded": result, "source": "file"}
        return JSONResponse(status_code=404, content={"error": f"File '{request.filepath}' not found"})
    
    return JSONResponse(status_code=400, content={"error": "Provide either hash_id or filepath+line"})

@app.get("/api/expand/{filepath:path}")
async def api_expand_get(filepath: str, line: int = Query(..., description="Line number"), context: int = Query(3, description="Context lines")):
    """GET endpoint for expansion — easier for agents to call."""
    result = expand_file_line(filepath, line, context)
    if result:
        return {"expanded": result, "source": "file"}
    return JSONResponse(status_code=404, content={"error": f"File '{filepath}' not found"})

# ============================================================
# XRL PROTOCOL ENDPOINTS
# ============================================================
class XrlExpandRequest(BaseModel):
    uris: List[str] = []
    hash_ids: Optional[List[str]] = None

class XrlResolveRequest(BaseModel):
    uri: str

class XrlPruneRequest(BaseModel):
    max_age_days: int = 7

@app.post("/api/xrl/expand")
async def api_xrl_expand(request: XrlExpandRequest):
    """Expand one or more XRL URIs back to full context.
    Accepts a list of XRL URIs and/or hash IDs.
    Returns a dict mapping each URI/hash to its expanded content."""
    results = {}
    
    # Expand XRL URIs
    for uri in request.uris:
        parsed = parse_xrl(uri)
        if parsed is None:
            results[uri] = {"error": "Invalid XRL URI format"}
            continue
        
        # Check atomic cache first
        if uri in _ATOMIC_CACHE:
            entry = _ATOMIC_CACHE[uri]
            # Try to expand from raw node file
            raw_path = entry.get("raw_node_path", "")
            if raw_path and os.path.exists(raw_path):
                try:
                    with open(raw_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    results[uri] = {
                        "expanded": content,
                        "source": "raw_node_cache",
                        "signature": entry.get("signature", ""),
                        "filepath": entry.get("filepath", ""),
                        "line": entry.get("line", 0),
                        "hash": entry.get("hash", ""),
                        "namespace": entry.get("namespace", ""),
                        "version": entry.get("version", 1)
                    }
                    continue
                except Exception as e:
                    logger.warning(f"Failed to read raw node for {uri}: {e}")
            
            # Fallback: expand from file:line
            filepath = parsed["filepath"]
            line = parsed["line"]
            result = expand_file_line(filepath, line, context_lines=5)
            if result:
                results[uri] = {
                    "expanded": result,
                    "source": "file_line_expansion",
                    "signature": entry.get("signature", ""),
                    "filepath": filepath,
                    "line": line,
                    "hash": parsed["hash"]
                }
            else:
                results[uri] = {
                    "expanded": entry.get("signature", ""),
                    "source": "atomic_cache_only",
                    "signature": entry.get("signature", ""),
                    "filepath": filepath,
                    "line": line
                }
        else:
            # URI not in cache — try file:line expansion directly
            filepath = parsed["filepath"]
            line = parsed["line"]
            result = expand_file_line(filepath, line, context_lines=5)
            if result:
                results[uri] = {
                    "expanded": result,
                    "source": "direct_file_expansion",
                    "filepath": filepath,
                    "line": line,
                    "hash": parsed["hash"]
                }
            else:
                results[uri] = {"error": f"XRL URI not found in cache and file '{filepath}' not accessible"}
    
    # Expand hash IDs (backward compatibility)
    if request.hash_ids:
        for hid in request.hash_ids:
            result = expand_hash(hid)
            if result:
                results[hid] = {"expanded": result, "source": "atomic_cache"}
            else:
                results[hid] = {"error": f"Hash '{hid}' not found"}
    
    return {"results": results, "count": len(results)}

@app.post("/api/xrl/resolve")
async def api_xrl_resolve(request: XrlResolveRequest):
    """Resolve an XRL URI to its metadata without expanding the full content."""
    parsed = parse_xrl(request.uri)
    if parsed is None:
        return JSONResponse(status_code=400, content={"error": "Invalid XRL URI format"})
    
    entry = _ATOMIC_CACHE.get(request.uri, {})
    return {
        "uri": request.uri,
        "parsed": parsed,
        "in_cache": request.uri in _ATOMIC_CACHE,
        "metadata": entry if entry else {},
        "raw_node_exists": os.path.exists(entry.get("raw_node_path", "")) if entry else False
    }

@app.get("/api/xrl/status")
async def api_xrl_status():
    """Get XRL protocol status — cache size, namespace, version info."""
    total_entries = len(_ATOMIC_CACHE)
    xrl_entries = {k: v for k, v in _ATOMIC_CACHE.items() if k.startswith("xrl://")}
    raw_node_count = len([f for f in os.listdir(RAW_NODES_DIR) if f.endswith(".txt")]) if os.path.exists(RAW_NODES_DIR) else 0
    
    return {
        "protocol": "XRL",
        "version": 1,
        "namespace": XRL_NAMESPACE,
        "total_cache_entries": total_entries,
        "xrl_entries": len(xrl_entries),
        "raw_node_count": raw_node_count,
        "raw_nodes_dir": RAW_NODES_DIR,
        "cache_file": ATOMIC_CACHE_FILE
    }

@app.post("/api/xrl/prune")
async def api_xrl_prune(request: XrlPruneRequest):
    """Prune stale entries from the XRL cache (older than max_age_days)."""
    from datetime import datetime, timezone, timedelta
    
    cutoff = datetime.now(timezone.utc) - timedelta(days=request.max_age_days)
    pruned = []
    kept = []
    
    for uri, entry in list(_ATOMIC_CACHE.items()):
        created_str = entry.get("created_at", "")
        if created_str:
            try:
                created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                if created < cutoff:
                    pruned.append(uri)
                    del _ATOMIC_CACHE[uri]
                else:
                    kept.append(uri)
            except (ValueError, TypeError):
                kept.append(uri)
        else:
            kept.append(uri)
    
    save_atomic_cache(_ATOMIC_CACHE)
    return {
        "pruned": len(pruned),
        "kept": len(kept),
        "max_age_days": request.max_age_days,
        "pruned_uris": pruned[:20],  # First 20 for preview
        "note": "Use POST /api/xrl/expand with uris to re-expand pruned entries"
    }

# ============================================================
# TIER INFO ENDPOINT (MUST be before expand route to avoid shadowing)
# ============================================================
@app.get("/api/tier-info")
async def api_tier_info(model: str = Query("default", description="Model name"), mode: str = Query("cloud", description="Cognitive mode")):
    """Get the recommended skeleton tier for a given model."""
    ctx = detect_context_window(model, mode)
    tier = select_tier(ctx)
    return {
        "model": model,
        "mode": mode,
        "context_window": ctx,
        "recommended_tier": tier,
        "thresholds": TIER_THRESHOLDS
    }

# ============================================================
# SKELETONIZE ENDPOINT
# ============================================================
class SkeletonizeRequest(BaseModel):
    filepath: str
    level: int = 3
    source_hint: Optional[str] = None

@app.post("/api/skeletonize")
async def api_skeletonize(request: SkeletonizeRequest):
    """Skeletonize a file on demand. Returns structural skeleton with raw node reference and XRL URI."""
    source_hint = request.source_hint or request.filepath
    result = skeletonize_file_content(request.filepath, request.level, source_hint=source_hint)
    if result:
        return {
            "filepath": request.filepath,
            "level": request.level,
            "skeleton": result,
            "source_hint": source_hint
        }
    return JSONResponse(status_code=404, content={"error": f"File '{request.filepath}' not found or could not be skeletonized"})

# ============================================================
# SEMANTIC SUMMARY ENDPOINT
# ============================================================
class SemanticSummaryRequest(BaseModel):
    filepath: str
    content: Optional[str] = None

@app.post("/api/semantic-summary")
async def api_semantic_summary(request: SemanticSummaryRequest):
    """Generate a one-line semantic summary of a file using the local LLM."""
    if request.content:
        content = request.content
    else:
        full_path = os.path.join(os.path.dirname(__file__), "..", "..", request.filepath)
        if not os.path.exists(full_path):
            full_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", request.filepath)
        if not os.path.exists(full_path):
            return JSONResponse(status_code=404, content={"error": f"File '{request.filepath}' not found"})
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
    
    summary = _call_local_llm_for_summary(request.filepath, content)
    return {"filepath": request.filepath, "summary": summary}

# ============================================================
# CHAT COMPLETIONS (main proxy endpoint)
# ============================================================
@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    payload = await request.json()
    headers = dict(request.headers)
    
    headers.pop("host", None)
    headers.pop("content-length", None)
    
    if OLLAMA_API_KEY:
        headers["Authorization"] = f"Bearer {OLLAMA_API_KEY}"
    
    downstream_url = headers.pop("x-downstream-url", os.environ.get("LM_STUDIO_URL", DEFAULT_DOWNSTREAM_URL))
    messages = payload.get("messages", [])
    model = payload.get("model", "default")
    
    # PASSIVE / RAW PASSTHROUGH MODE FOR BENCHMARKING
    raw_mode = os.environ.get("FoveAI_RAW_PASSTHROUGH_MODE", "true").lower() in ("1", "true", "yes")
    if raw_mode:
        logger.info("🧪 [RAW BENCHMARK PROXY :8106] Passthrough enabled — 0 compression, 0 devouring, 1:1 forward to LM Studio")
        stream = payload.get("stream", False)
        client = httpx.AsyncClient(timeout=300.0)
        if stream:
            req = client.build_request("POST", downstream_url, json=payload, headers=headers)
            response = await client.send(req, stream=True)
            return StreamingResponse(_stream_generator(response), status_code=response.status_code, headers=dict(response.headers))
        else:
            response = await client.post(downstream_url, json=payload, headers=headers)
            try:
                return response.json()
            except Exception:
                return {"error": "Downstream did not return valid JSON", "status_code": response.status_code}

    # Detect cognitive mode and context window
    _cognitive_mode = os.environ.get("FoveAI_COGNITIVE_MODE", "cloud").lower()
    context_window = detect_context_window(model, _cognitive_mode)
    active_tier = select_tier(context_window)
    
    # Inject tier info into system message
    tier_injection = f"\n[TokenSlayer Tier: {active_tier} | Context: {context_window} tokens | Mode: {_cognitive_mode}]"
    for msg in messages:
        if msg.get("role") == "system" and isinstance(msg.get("content"), str):
            msg["content"] += tier_injection
            break
    
    # 1. Devour Skeletons (with optional learned compression)
    use_learned = os.environ.get("FoveAI_USE_LEARNED_COMPRESSION", "0").lower() in ("1", "true", "yes")
    for msg in messages:
        if isinstance(msg.get("content"), str):
            original_len = len(msg["content"])
            msg["content"] = devour_skeletons(msg["content"], use_learned=use_learned)
            if len(msg["content"]) < original_len:
                compression_method = "🧠 learned" if use_learned else "💀 regex"
                logger.info(f"{compression_method} Devourer stripped {original_len - len(msg['content'])} characters from a message.")
    
    # 2. ContextStripper
    if ContextStripper:
        # Preserve more recent turns when the cloud cap is tight (default now ~8K)
        preserve_last = int(os.environ.get("FoveAI_CLOUD_PRESERVE_LAST", "10"))
        stripper = ContextStripper(preserve_last=preserve_last)
        try:
            messages = stripper.strip_messages(messages)
            payload["messages"] = messages
        except Exception as e:
            logger.error(f"Failed to compress messages: {e}")

    # 3. Mode-aware budget enforcement
    if _cognitive_mode == "local":
        _n_ctx    = int(os.environ.get("FoveAI_LOCAL_N_CTX", str(context_window)))
        _max_out  = int(os.environ.get("FoveAI_SOFT_LOCAL_MAX_TOKENS_NORMAL", "512"))
        _budget_tokens = _n_ctx - _max_out
    else:
        # Cloud target: aggressively compress toward ~8K upstream tokens.
        # Old default (70000) left context nearly uncompressed. Override via env.
        _budget_tokens = int(os.environ.get("FoveAI_CLOUD_MAX_TOKENS_CAP", "8192"))

    _budget_chars = _budget_tokens * 3

    total_chars = sum(len(m.get("content", "") or "") for m in messages)
    if total_chars > _budget_chars:
        system_msgs = [m for m in messages if m.get("role") == "system"]
        convo_msgs  = [m for m in messages if m.get("role") != "system"]
        system_chars = sum(len(m.get("content", "") or "") for m in system_msgs)
        budget_left = _budget_chars - system_chars
        while convo_msgs and sum(len(m.get("content", "") or "") for m in convo_msgs) > budget_left:
            convo_msgs.pop(0)
        logger.info(f"✂️  Safety trim [{_cognitive_mode}]: {total_chars} → {budget_left + system_chars} chars (budget: {_budget_chars} / {_budget_tokens} tok)")
        messages = system_msgs + convo_msgs
        payload["messages"] = messages

    # 4. Cache Check
    cache_key_data = {"model": payload.get("model", ""), "messages": messages, "url": downstream_url}
    cache_hash = hashlib.md5(json.dumps(cache_key_data, sort_keys=True).encode("utf-8")).hexdigest()
    
    stream = payload.get("stream", False)
    
    if cache_hash in _AI_CACHE:
        logger.info(f"⚡ CACHE HIT! Serving cached response for hash {cache_hash[:8]}")
        cached_text = _AI_CACHE[cache_hash]
        if stream:
            return StreamingResponse(_mock_stream_generator(cached_text), media_type="text/event-stream")
        else:
            return {
                "id": "chatcmpl-cached",
                "object": "chat.completion",
                "model": payload.get("model", "cached"),
                "choices": [{"index": 0, "message": {"role": "assistant", "content": cached_text}, "finish_reason": "stop"}]
            }
            
    # 5. Forward
    client = httpx.AsyncClient()
    if stream:
        req = client.build_request("POST", downstream_url, json=payload, headers=headers)
        response = await client.send(req, stream=True)
        return StreamingResponse(_stream_generator(response), status_code=response.status_code, headers=dict(response.headers))
    else:
        response = await client.post(downstream_url, json=payload, headers=headers)
        try:
            resp_json = response.json()
            if "choices" in resp_json and len(resp_json["choices"]) > 0:
                if text := resp_json["choices"][0].get("message", {}).get("content", ""):
                    _AI_CACHE[cache_hash] = text
                    save_cache(_AI_CACHE)
                    logger.info(f"💾 Cached new response for hash {cache_hash[:8]}")
            return resp_json
        except Exception:
            return {"error": "Downstream proxy did not return valid JSON.", "status_code": response.status_code, "text": response.text}

@app.get("/v1/models")
async def get_models(request: Request):
    headers = dict(request.headers)
    headers.pop("host", None)
    
    downstream_url = headers.pop("x-downstream-url", "https://ollama.com/v1/models")
    
    async with httpx.AsyncClient() as client:
        response = await client.get(downstream_url, headers=headers)
        try:
            return response.json()
        except Exception:
            return {"error": "Failed to parse models"}

@app.get("/health")
async def health():
    return {
        "status": "ONLINE",
        "service": "TokenSlayer Proxy v2.0",
        "tier": "auto-detect",
        "atomic_cache_size": len(_ATOMIC_CACHE),
        "response_cache_size": len(_AI_CACHE),
        "raw_nodes_dir": RAW_NODES_DIR
    }

def _auto_prune_cache(max_age_days: int = 7):
    """Auto-prune stale XRL cache entries older than max_age_days at startup."""
    from datetime import datetime, timezone, timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    pruned = 0

    for uri, entry in list(_ATOMIC_CACHE.items()):
        created_str = entry.get("created_at", "")
        if created_str:
            try:
                created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                if created < cutoff:
                    del _ATOMIC_CACHE[uri]
                    pruned += 1
            except (ValueError, TypeError):
                pass

    if pruned > 0:
        save_atomic_cache(_ATOMIC_CACHE)
        print(f"[XRL] Auto-pruned {pruned} stale cache entries (>{max_age_days} days old)")


if __name__ == "__main__":
    _auto_prune_cache(max_age_days=7)
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8106)