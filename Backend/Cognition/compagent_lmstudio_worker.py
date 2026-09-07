import os
import asyncio
import logging
from lmstudio import Client

logger = logging.getLogger("lmstudio-worker")

FoveAI_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

SYSTEM_PROMPT = f"""You are Jen's parallel coding worker. 
Your mission is to safely and efficiently implement the User's development requests in the codebase.
You have direct access to make changes in the project workspace (root directory: {FoveAI_ROOT}).

To edit files, output special XML-like tags. You can make multiple modifications across files.
<edit_file path="relative/path/from/root/to/file">
<search>
Exact contiguous block of code to find in the existing file. Include exact indentation and whitespace.
</search>
<replace>
The exact replacement code. Include matching indentation and correct logical structures.
</replace>
</edit_file>
"""

async def run_lmstudio_worker(instruction: str):
    logger.info(f"[LM Studio Worker] Starting parallel coding task: {instruction}")
    
    # Use standard LMStudio host/port from environment or default
    lmstudio_url = os.getenv("LMSTUDIO_URL", "http://localhost:8888")
    lmstudio_url = lmstudio_url.replace("/v1", "") # SDK handles /v1 suffix
    
    try:
        # Initialize the Python SDK client
        client = Client(base_url=lmstudio_url)
        
        # We can run it in a thread to avoid blocking asyncio loop if SDK is sync
        # SDK methods are async via .async_client or sync via .chat.completions
        # lmstudio python sdk 1.5.0 supports async!
        # Actually it's just client.chat.completions
        
        def _do_chat():
            return client.chat.completions.create(
                model="local-model",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": instruction}
                ],
                temperature=0.1
            )
            
        response = await asyncio.to_thread(_do_chat)
        content = response.choices[0].message.content
        logger.info("[LM Studio Worker] Received generated code modifications.")
        
        # Process the edits
        import re
        edit_blocks = re.findall(r'<edit_file\s+path=["\']([^"\']+)["\']\s*>(.*?)</edit_file>', content, re.DOTALL)
        
        for idx, (rel_path, block_content) in enumerate(edit_blocks):
            file_path = os.path.abspath(os.path.join(FoveAI_ROOT, rel_path))
            
            search_match = re.search(r'<search>(.*?)</search>', block_content, re.DOTALL)
            replace_match = re.search(r'<replace>(.*?)</replace>', block_content, re.DOTALL)
            
            if not search_match or not replace_match:
                logger.warning(f"[LM Studio Worker] Could not parse block {idx} for {rel_path}")
                continue
                
            search_content = search_match.group(1).replace("\r\n", "\n")
            replace_content = replace_match.group(1).replace("\r\n", "\n")
            
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as f:
                    file_data = f.read()
                
                normalized = file_data.replace("\r\n", "\n")
                if search_content in normalized:
                    new_data = normalized.replace(search_content, replace_content, 1)
                    if "\r\n" in file_data:
                        new_data = new_data.replace("\n", "\r\n")
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(new_data)
                    logger.info(f"[LM Studio Worker] Successfully updated {rel_path}")
                else:
                    logger.warning(f"[LM Studio Worker] Search block not found in {rel_path}")
                    
        # Inform the XR scene or Jen that the task is complete
        bridge_file = os.path.join(FoveAI_ROOT, "Forge", "scratch", "agy_bridge.txt")
        if os.path.exists(os.path.dirname(bridge_file)):
            with open(bridge_file, "a", encoding="utf-8") as f:
                f.write(f"\nBackground task '{instruction[:20]}...' completed by LM Studio Worker.\n")
                
    except Exception as e:
        logger.error(f"[LM Studio Worker] Failed: {e}")
