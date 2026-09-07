import os
import re
import sys
import json
import asyncio
import logging
import httpx
from pathlib import Path
from typing import AsyncGenerator, Dict, Any, List

logger = logging.getLogger("ag-coder")

# --- Resolve Paths ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # backend/
FoveAI_ROOT = os.path.dirname(BASE_DIR)

def load_dotenv_keys():
    """Load keys from .env directly"""
    env_path = os.path.join(FoveAI_ROOT, ".env")
    keys = {}
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                idx = line.index("=")
                key = line[:idx].strip()
                val = line[idx + 1:].strip().strip("'").strip('"')
                keys[key] = val
    return keys

# System Prompt detailing how to modify files via search/replace blocks
SYSTEM_PROMPT = """You are REMAX (REquest MAnaging eXecutive), the sovereign non-interactive code engineer of the FoveAI-lite system.
Your mission is to safely, cleanly, and efficiently implement the User's development requests in the codebase.

You have direct access to make changes in the project workspace (root directory: {workspace_root}).

### WORKSPACE COMPOSITION
- frontend/XR_Vessel/src/components/ — WebUI Dashboard tabs (Dashboard.ts, DevToolsTab.ts, FeatureMapTab.ts, MonetizingTab.ts)
- frontend/XR_Vessel/src/senses/ — Client-side sensors and text parsers (BracketParser.ts)
- backend/Cognition/ — Core cognitive reasoning (MindCore.py, compagent.py, cloud_repertoire.py)
- Scripts/ — Background daemon utilities

### FILE MODIFICATION PROTOCOL
To edit files, you must output special XML-like tags in your response. You can make multiple modifications across multiple files.
Specify each file modification using the following exact tag format:

<edit_file path="relative/path/from/root/to/file">
<search>
Exact contiguous block of code to find in the existing file. Include exact indentation and whitespace.
</search>
<replace>
The exact replacement code. Include matching indentation and correct logical structures.
</replace>
</edit_file>

RULES FOR SAFE EDITING:
1. Ensure the <search> content EXACTLY matches a unique contiguous block in the target file.
2. Maintain existing comments, docstrings, and styling principles (Matchbox styling, Share Tech Mono, neon borders, and glow effects).
3. Do not shorten code with placeholders like "... existing code ..." in the <replace> tag. Write out the full replacement.
4. Verify import paths and typescript compiling norms.

Explain your plan first in clear, high-tech, professional terminology. Then output your <edit_file> tags. Finally, summarize what changes you applied. Use a warm, confident, and professional developer tone.
"""

async def run_remax_agent(prompt: str) -> AsyncGenerator[str, None]:
    """
    Executes the REMAX (REquest MAnaging eXecutive) non-interactive code agent.
    Streams output, then parses and applies file modifications automatically.
    """
    yield "[REMAX] Initializing non-interactive pipeline...\n"
    keys = load_dotenv_keys()
    
    # Resolve slot key credentials
    gemini_key = keys.get("FoveAI_REPERTOIRE_GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    openai_key = keys.get("FoveAI_REPERTOIRE_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    openrouter_key = keys.get("FoveAI_CLOUD_OPENROUTER_API") or os.environ.get("OPENROUTER_API_KEY")
    
    # Resolve local LLM endpoints
    lmstudio_url = keys.get("LMSTUDIO_URL") or os.environ.get("LMSTUDIO_URL") or os.getenv("FoveAI_LOCAL_BASE_URL", "http://localhost:8888/v1")
    lmstudio_model = keys.get("FoveAI_AGY_LMSTUDIO_MODEL") or os.environ.get("FoveAI_AGY_LMSTUDIO_MODEL") or ""
    
    # Resolve Ollama Cloud credentials
    ollama_key = keys.get("FoveAI_REPERTOIRE_OLLAMA_API_KEY") or keys.get("OLLAMA_API_KEY") or os.environ.get("OLLAMA_API_KEY")
    ollama_base_url = keys.get("FoveAI_REPERTOIRE_OLLAMA_BASE_URL") or keys.get("FoveAI_CLOUD_BASE_URL") or "https://ollama.com/v1"
    ollama_model = keys.get("FoveAI_REPERTOIRE_OLLAMA_MODEL") or keys.get("FoveAI_MODEL_CLOUD_ID") or "glm-5.1"

    # Resolve slot model names dynamically from env slots with reliable defaults
    gemini_model = keys.get("FoveAI_MODEL_GEMINI_ID") or os.environ.get("FoveAI_MODEL_GEMINI_ID") or "gemini-2.5-pro"
    openai_model = keys.get("FoveAI_REPERTOIRE_OPENAI_MODEL") or os.environ.get("FoveAI_REPERTOIRE_OPENAI_MODEL") or "gpt-4o"
    openrouter_model = keys.get("FoveAI_MODEL_OPENROUTER_ID") or os.environ.get("FoveAI_MODEL_OPENROUTER_ID") or "google/gemini-2.5-pro"
    
    # Define slots to try in priority order
    slots = []
    
    # 1. Ollama Cloud (Primary Cloud Provider)
    if ollama_key:
        slots.append({
            "name": "Ollama Cloud",
            "base_url": ollama_base_url,
            "api_key": ollama_key,
            "model": ollama_model
        })
        
    # 2. Gemini Direct (low quota — deprioritized)
    if gemini_key:
        sanitized_gemini_model = gemini_model
        if sanitized_gemini_model and ("gemini-3" in sanitized_gemini_model or "preview" in sanitized_gemini_model):
            sanitized_gemini_model = "gemini-2.5-pro"
        slots.append({
            "name": "Google Gemini (low quota)",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/v1",
            "api_key": gemini_key,
            "model": sanitized_gemini_model
        })
        
    # 3. OpenRouter Slot
    if openrouter_key:
        slots.append({
            "name": "OpenRouter Venice",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": openrouter_key,
            "model": openrouter_model
        })
        
    # 4. LM Studio (Local) — last resort fallback, no API key needed
    slots.append({
        "name": "LM Studio (Local)",
        "base_url": lmstudio_url.rstrip("/"),
        "api_key": os.environ.get("LMSTUDIO_API_TOKEN", ""),
        "model": lmstudio_model  # Empty = use currently loaded model
    })

    if not slots:
        yield "[REMAX] Error: No configured LLM slots found! Check .env and local services.\n"
        return

    # Build complete prompt structure
    system_instruction = SYSTEM_PROMPT.format(workspace_root=FoveAI_ROOT)
    
    full_response = ""
    success = False
    
    for slot_idx, slot in enumerate(slots):
        name = slot["name"]
        base_url = slot["base_url"]
        api_key = slot["api_key"]
        model = slot["model"]
        
        yield f"[REMAX] Slot {slot_idx + 1}/{len(slots)}: Attempting {name} ({model})...\n"
        
        # Assemble request
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1, # Low temperature for precise code editing
            "stream": True
        }
        
        endpoint = f"{base_url}/chat/completions"
        
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", endpoint, headers=headers, json=payload) as response:
                    if response.status_code != 200:
                        err_body = await response.aread()
                        err_msg = err_body.decode('utf-8', errors='replace')
                        yield f"  ⚠️ Quota or API limit encountered on slot {name} (HTTP {response.status_code})\n"
                        # Try parsing friendly message
                        try:
                            err_json = json.loads(err_msg)
                            friendly_err = err_json.get("error", {}).get("message", "")
                            if friendly_err:
                                yield f"    Detail: {friendly_err[:200]}...\n"
                        except Exception:
                            pass
                        yield "  Cascading to next slot...\n\n"
                        continue
                        
                    yield f"[REMAX] Connection established! Streaming from {name}...\n"
                    yield "=" * 60 + "\n\n"
                    
                    async for chunk in response.aiter_lines():
                        if not chunk:
                            continue
                        line = chunk.strip()
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                break
                            try:
                                data_json = json.loads(data_str)
                                choice = data_json.get("choices", [{}])[0]
                                delta = choice.get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    full_response += content
                                    yield content
                            except Exception:
                                pass
                    success = True
                    break # Break slot iteration on successful stream completion
        except Exception as e:
            yield f"  ⚠️ {name} connection aborted: {e}\n"
            yield "  Cascading to next slot...\n\n"
            continue
            
    if not success:
        yield "\n[REMAX] All slots failed. Pipeline aborted.\n"
        return

    # Once stream is completely received, check for file modifications
    yield "\n\n" + "=" * 60 + "\n"
    yield "[REMAX] Code generation stream complete.\n"
    yield "[REMAX] Scanning response for file modification instructions...\n"

    # Regex to parse <edit_file path="..."> ... <search>...</search> ... <replace>...</replace> ... </edit_file>
    # Handle single or multi-line edit blocks safely
    edit_blocks = re.findall(r'<edit_file\s+path=["\']([^"\']+)["\']\s*>(.*?)</edit_file>', full_response, re.DOTALL)
    
    if not edit_blocks:
        yield "[REMAX] No file modification blocks detected. Execution complete.\n"
        return
        
    yield f"[REMAX] Detected {len(edit_blocks)} modification block(s).\n"
    
    for idx, (rel_path, block_content) in enumerate(edit_blocks):
        file_path = os.path.abspath(os.path.join(FoveAI_ROOT, rel_path))
        yield f"\n[Action {idx + 1}] Target file: {rel_path} (exists: {os.path.exists(file_path)})\n"
        
        # Extract search and replace contents
        search_match = re.search(r'<search>(.*?)</search>', block_content, re.DOTALL)
        replace_match = re.search(r'<replace>(.*?)</replace>', block_content, re.DOTALL)
        
        if not search_match or not replace_match:
            yield f"  ⚠️ FAIL: Could not parse search or replace tags in this block.\n"
            continue
            
        search_content = search_match.group(1)
        replace_content = replace_match.group(1)
        
        if not os.path.exists(file_path):
            # If the file does not exist, check if we should create it
            # To be safe, let's create the directories if needed
            try:
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(replace_content.lstrip("\n"))
                yield f"  🟢 SUCCESS: Created new file and written content.\n"
            except Exception as err:
                yield f"  ⚠️ FAIL: Failed to create new file: {err}\n"
            continue
            
        # Read existing file content
        with open(file_path, "r", encoding="utf-8") as f:
            file_data = f.read()
            
        # Standardize line endings for matching
        normalized_file_data = file_data.replace("\r\n", "\n")
        normalized_search = search_content.replace("\r\n", "\n")
        normalized_replace = replace_content.replace("\r\n", "\n")
        
        # Strip trailing/leading matching spacing checks if exact fails, but try exact match first
        if normalized_search in normalized_file_data:
            updated_content = normalized_file_data.replace(normalized_search, normalized_replace, 1)
            # Restore line endings based on original file type
            if "\r\n" in file_data:
                updated_content = updated_content.replace("\n", "\r\n")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(updated_content)
            yield f"  🟢 SUCCESS: File modification applied cleanly.\n"
        else:
            # Try fuzzy check by stripping trailing/leading newlines/whitespace
            stripped_search = normalized_search.strip()
            stripped_file_data = normalized_file_data.strip()
            if stripped_search in normalized_file_data:
                # Resolve match within data
                idx_start = normalized_file_data.find(stripped_search)
                idx_end = idx_start + len(stripped_search)
                updated_content = normalized_file_data[:idx_start] + normalized_replace + normalized_file_data[idx_end:]
                if "\r\n" in file_data:
                    updated_content = updated_content.replace("\n", "\r\n")
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(updated_content)
                yield f"  🟢 SUCCESS: Applied modifications with soft-spacing alignment.\n"
            else:
                yield f"  ❌ FAIL: Target <search> block not found in file. Indentation or lines may mismatch.\n"

    # Trigger compiler tests automatically to confirm stability
    yield "\n" + "=" * 60 + "\n"
    yield "[REMAX] Initiating automated compile check...\n"
    
    try:
        proc = await asyncio.create_subprocess_exec(
            "npm.cmd", "run", "build",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=os.path.join(FoveAI_ROOT, "Frontend", "XR_Vessel")
        )
        
        yield "[Compiler] Running: tsc && vite build\n"
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            yield f"[Compiler] {line.decode('utf-8', errors='replace')}"
            
        await proc.wait()
        yield f"\n[Compiler] Compile test completed with exit code: {proc.returncode}\n"
        if proc.returncode == 0:
            yield "🟢 BUILD SUCCESSFUL: Codebase is fully stable.\n"
        else:
            yield "🔴 BUILD FAILURE: Compiling failed. Please check changes.\n"
    except Exception as err:
        yield f"[Compiler Error] Failed to run compiler check: {err}\n"


# Export run_antigravity_agent as an alias to run_remax_agent for xr_app.py compatibility
run_antigravity_agent = run_remax_agent

