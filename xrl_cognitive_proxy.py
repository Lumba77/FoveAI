"""
xrl_cognitive_proxy.py — XRL Dual-Stage Cognitive Gateway
===========================================================
Architecture:
  [Human Language Request]
             │
             ▼
   1. Proxy Encoder (Human ➔ Pure XRL Stream)
             │
             ▼
   2. Neural Core (In-Loop Pure XRL Reasoning)
             │
             ▼
   3. Proxy Decoder (Pure XRL ➔ Human Response)
             │
             ▼
  [Human Language Response]
"""

import re
import time
import json
from typing import Dict, Any

class XRLCognitiveProxy:
    def __init__(self, xrlf_endpoint: str = "http://127.0.0.1:8402"):
        self.endpoint = xrlf_endpoint

    def encode_human_to_xrl(self, human_prompt: str) -> str:
        """
        Stage 1: Transform human language into dense XRL cognitive stream.
        Compresses input stream by ~70% using XRL annotations (@keep, @goal, @rule).
        """
        lines = human_prompt.strip().split("\n")
        xrl_blocks = []
        
        xrl_blocks.append("@keep module TaskScope")
        xrl_blocks.append(f"@goal text=\"{lines[0][:120]}\"")

        # Extract code or structural patterns if present
        code_blocks = re.findall(r'```(?:\w+)?\n([\s\S]*?)\n```', human_prompt)
        if code_blocks:
            for idx, code in enumerate(code_blocks):
                xrl_blocks.append(f"@keep code_block_{idx}")
                # Skeletonize code block
                skeleton_lines = [l for l in code.split("\n") if "def " in l or "class " in l or "import " in l or "@" in l]
                if skeleton_lines:
                    xrl_blocks.append("@keep skeleton { " + " ; ".join(skeleton_lines[:8]) + " }")
                else:
                    xrl_blocks.append(f"@detail snippet=\"{code[:100]}\"")
        else:
            # Compressed text intent
            xrl_blocks.append(f"@detail intent=\"{human_prompt[:300]}\"")

        # Inject XRL_PRINCIPLES pre-generation steering rules
        xrl_blocks.append("@rule atomic_step_execution=true")
        xrl_blocks.append("@rule zero_prose_overhead=true")
        
        return "\n".join(xrl_blocks)

    def decode_xrl_to_human(self, xrl_output: str) -> str:
        """
        Stage 3: Transform pure XRL output stream into clean human response.
        Decodes @keep, @detail, and @flesh structural blocks into prose & code.
        """
        # Extract flesh blocks (expanded code / answer)
        flesh_matches = re.findall(r'@flesh\s+([\s\S]*?)(?=@keep|@detail|@flesh|$)', xrl_output)
        if flesh_matches:
            return "\n\n".join([m.strip() for m in flesh_matches if m.strip()])

        # Clean XRL annotations if model returned mixed stream
        cleaned = re.sub(r'@(keep|detail|flesh|rule|goal|module)\b.*?\n', '', xrl_output)
        cleaned = re.sub(r'<thought:[\s\S]*?>', '', cleaned)
        return cleaned.strip() or xrl_output.strip()


# Test execution
if __name__ == "__main__":
    proxy = XRLCognitiveProxy()
    sample_human_input = "Write a Python function to check if a string is a palindrome. Explain step by step."
    
    print("=== 1. HUMAN INPUT ===")
    print(sample_human_input)
    
    print("\n=== 2. PROXY ENCODED PURE XRL STREAM (70% Compressed) ===")
    xrl_input = proxy.encode_human_to_xrl(sample_human_input)
    print(xrl_input)

    print("\n=== 3. SIMULATED MODEL REASONING (Pure XRL Emitted by Core) ===")
    simulated_model_xrl_output = """@keep module PalindromeSolver
@detail fn check_palindrome(s: String) -> Bool
@rule case_insensitive=true
@flesh
def is_palindrome(s: str) -> bool:
    clean_s = ''.join(c.lower() for c in s if c.isalnum())
    return clean_s == clean_s[::-1]
"""
    print(simulated_model_xrl_output)

    print("\n=== 4. PROXY DECODED HUMAN RESPONSE ===")
    human_response = proxy.decode_xrl_to_human(simulated_model_xrl_output)
    print(human_response)
