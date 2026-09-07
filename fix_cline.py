#!/usr/bin/env python3
"""Auto-patch Cline extension.js for Ollama Cloud model support.

This script is designed to be run automatically on VSCode startup.
It's idempotent — checks if each patch is already applied before modifying.

Patches applied:
1. Adds DeepSeek V3/V4, GLM-5, Qwen3, Llama4, Codestral, Devstral, Magistral to "advanced model" check
2. Replaces "less capable models" nag with neutral guidance
3. Expands DeepSeek model detection for V3/V4 variants
4. Increases default context window from 128k to 256k for OpenAI-compatible providers

Usage: python fix_cline.py [--quiet]
  --quiet  Only print if patches were actually applied
"""
import sys
import os
import glob

def find_cline_extension():
    """Find the latest Cline extension directory automatically."""
    extensions_dir = os.path.expanduser(r"~\.vscode\extensions")
    pattern = os.path.join(extensions_dir, "saoudrizwan.claude-dev-*")
    matches = glob.glob(pattern)
    if not matches:
        return None
    # Sort by version number (newest last in lexicographic order)
    matches.sort()
    ext_dir = matches[-1]
    ext_js = os.path.join(ext_dir, "dist", "extension.js")
    if os.path.exists(ext_js):
        return ext_js
    return None


def apply_patches(quiet=False):
    """Apply all patches to Cline extension.js. Returns True if any changes were made."""
    ext_path = find_cline_extension()
    if not ext_path:
        if not quiet:
            print("ERROR: Could not find Cline extension.js")
            print("Make sure Cline is installed in VSCode.")
        return False
    
    if not quiet:
        print(f"Patching: {ext_path}")
    
    c = open(ext_path, 'r', encoding='utf-8').read()
    original = c
    changes = 0
    
    # ═══════════════════════════════════════════════════════════
    # Patch 1: Add more models to "advanced model" checker
    # ═══════════════════════════════════════════════════════════
    # Check if already patched (look for our custom model strings)
    if 'deepseek-v3' in c and 'glm-5' in c and 'devstral' in c:
        if not quiet:
            print("Patch 1: Already applied (advanced model check) - SKIP")
    else:
        # Try exact match first
        old1 = r'function aM(t){let e=Om(t);return $2n(e)||J2n(e)||zph(e)||fx(e)||oot(e)||$ph(e)||uot(e)||Jph(e)||Xph(e)||Zph(e)||e0h(e)}'
        new1 = r'function aM(t){let e=Om(t);return $2n(e)||J2n(e)||zph(e)||fx(e)||oot(e)||$ph(e)||uot(e)||Jph(e)||Xph(e)||Zph(e)||e0h(e)||e.includes("deepseek-v3")||e.includes("deepseek-v4")||e.includes("deepseek_v3")||e.includes("deepseek_v4")||e.includes("deepcode")||e.includes("glm-5")||e.includes("glm5")||e.includes("glm_5")||e.includes("qwen3")||e.includes("qwen-3")||e.includes("llama-4")||e.includes("llama4")||e.includes("devstral")||e.includes("codestral")||e.includes("magistral")}'
        
        if old1 in c:
            c = c.replace(old1, new1)
            changes += 1
            if not quiet: print("Patch 1: Applied (exact match) - OK")
        else:
            # Fallback: find function by name and replace
            idx = c.find('function aM(t)')
            if idx >= 0:
                end_idx = c.find('}function', idx + 10)
                if end_idx >= 0:
                    new_func = 'function aM(t){let e=Om(t);return $2n(e)||J2n(e)||zph(e)||fx(e)||oot(e)||$ph(e)||uot(e)||Jph(e)||Xph(e)||Zph(e)||e0h(e)||e.includes("deepseek-v3")||e.includes("deepseek-v4")||e.includes("deepseek_v3")||e.includes("deepseek_v4")||e.includes("deepcode")||e.includes("glm-5")||e.includes("glm5")||e.includes("glm_5")||e.includes("qwen3")||e.includes("qwen-3")||e.includes("llama-4")||e.includes("llama4")||e.includes("devstral")||e.includes("codestral")||e.includes("magistral")}'
                    c = c[:idx] + new_func + c[end_idx+1:]
                    changes += 1
                    if not quiet: print("Patch 1: Applied (index-based) - OK")
                else:
                    print("Patch 1: FAILED - could not find function boundary")
            else:
                print("Patch 1: FAILED - could not find aM function")
    
    # ═══════════════════════════════════════════════════════════
    # Patch 2: Replace "less capable models" nag with neutral message
    # ═══════════════════════════════════════════════════════════
    if 'less capable models' not in c:
        if not quiet: print("Patch 2: Already applied (nag removed) - SKIP")
    else:
        old2 = "Cline uses complex prompts and iterative task execution that may be challenging for less capable models. For best results, it's recommended to use Claude 4.5 Sonnet for its advanced agentic coding capabilities."
        new2 = "Note: This model may need more guidance for complex tasks. Try breaking tasks into smaller steps if needed."
        
        if old2 in c:
            c = c.replace(old2, new2)
            changes += 1
            if not quiet: print("Patch 2: Applied (exact match) - OK")
        else:
            # Fallback: find and replace the key phrase
            idx = c.find('less capable models')
            if idx >= 0:
                # Find the full sentence containing this phrase
                start = max(0, c.rfind('.', idx - 200, idx) + 1)
                end = c.find('.', idx) + 1
                if end > idx:
                    old_text = c[start:end].strip()
                    c = c[:start] + new2 + c[end:]
                    changes += 1
                    if not quiet: print(f"Patch 2: Applied (phrase-based) - OK")
            else:
                print("Patch 2: FAILED - could not find nag message")
    
    # ═══════════════════════════════════════════════════════════
    # Patch 3: Expand DeepSeek model detection
    # ═══════════════════════════════════════════════════════════
    if 'deepseek-v3' in c and c.find('deepseek-v3') < c.find('function Zph') + 200 if 'function Zph' in c else True:
        # Check if our additions are in the Zph function specifically
        zph_idx = c.find('function Zph(t)')
        if zph_idx >= 0:
            zph_end = c.find('}', zph_idx)
            zph_body = c[zph_idx:zph_end+1]
            if 'deepseek-v3' in zph_body:
                if not quiet: print("Patch 3: Already applied (DeepSeek detection) - SKIP")
            else:
                # Apply patch
                old3 = 'function Zph(t){let e=Om(t);return e.includes("deepseek-chat")||e.includes("deepseek-reasoner")}'
                new3 = 'function Zph(t){let e=Om(t);return e.includes("deepseek-chat")||e.includes("deepseek-reasoner")||e.includes("deepseek-v3")||e.includes("deepseek-v4")||e.includes("deepseek_v3")||e.includes("deepseek_v4")}'
                if old3 in c:
                    c = c.replace(old3, new3)
                    changes += 1
                    if not quiet: print("Patch 3: Applied (exact match) - OK")
                else:
                    print("Patch 3: NEEDS UPDATE - Zph function changed in new version")
        else:
            if not quiet: print("Patch 3: Already applied or Zph not found - SKIP")
    else:
        old3 = 'function Zph(t){let e=Om(t);return e.includes("deepseek-chat")||e.includes("deepseek-reasoner")}'
        new3 = 'function Zph(t){let e=Om(t);return e.includes("deepseek-chat")||e.includes("deepseek-reasoner")||e.includes("deepseek-v3")||e.includes("deepseek-v4")||e.includes("deepseek_v3")||e.includes("deepseek_v4")}'
        if old3 in c:
            c = c.replace(old3, new3)
            changes += 1
            if not quiet: print("Patch 3: Applied (exact match) - OK")
        else:
            print("Patch 3: NEEDS UPDATE - Zph function signature changed")
    
    # ═══════════════════════════════════════════════════════════
    # Patch 4: Increase default context window 128k → 256k
    # ═══════════════════════════════════════════════════════════
    if 'contextWindow:256e3' in c:
        if not quiet: print("Patch 4: Already applied (context window 256k) - SKIP")
    else:
        # Try exact match
        old4 = '$3={maxTokens:-1,contextWindow:128e3,supportsImages:!0,supportsPromptCache:!1,isR1FormatRequired:!1,inputPrice:0,outputPrice:0,temperature:0}'
        new4 = '$3={maxTokens:-1,contextWindow:256e3,supportsImages:!0,supportsPromptCache:!1,isR1FormatRequired:!1,inputPrice:0,outputPrice:0,temperature:0}'
        
        if old4 in c:
            c = c.replace(old4, new4)
            changes += 1
            if not quiet: print("Patch 4: Applied (exact match) - OK")
        elif 'contextWindow:128e3' in c:
            c = c.replace('contextWindow:128e3', 'contextWindow:256e3')
            changes += 1
            if not quiet: print("Patch 4: Applied (fuzzy match) - OK")
        else:
            print("Patch 4: NEEDS UPDATE - context window format changed")
    
    # ═══════════════════════════════════════════════════════════
    # Write changes if any
    # ═══════════════════════════════════════════════════════════
    if c != original:
        open(ext_path, 'w', encoding='utf-8').write(c)
        print(f"Patched {changes} changes to {os.path.basename(os.path.dirname(ext_path))}")
        return True
    else:
        if not quiet: print("All patches already applied. No changes needed.")
        return False


if __name__ == "__main__":
    quiet = "--quiet" in sys.argv
    apply_patches(quiet=quiet)