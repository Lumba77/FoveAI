r"""
export_gemma_e2b_mtp_gguf.py
============================
Export the fine-tuned Gemma-4-E2B-MTP XRLF LoRA adapter to GGUF.

Merges the LoRA adapter back into the base model, then exports to GGUF.
The MTP head metadata must be preserved for speculative decoding.

Input:  Training/outputs/gemma_e2b_mtp_lora/adapter
Output: Training/outputs/gemma_e2b_mtp_q5_k_m.gguf
"""

import shutil
from pathlib import Path
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

BASE_MODEL_CANDIDATES = [
    Path(r"C:\Users\danie\.cache\huggingface\hub\google--gemma-4-E2B"),
    Path(r"C:\Users\danie\.cache\huggingface\hub\google--gemma-4-E2B-it"),
]
ADAPTER_PATH = Path(r"C:\Users\danie\program\LUMAX\Training\outputs\gemma_e2b_mtp_lora\adapter")
OUTPUT_DIR = Path(r"C:\Users\danie\program\LUMAX\Training\outputs")
GGUF_NAME = "gemma_e2b_mtp_xrlf_q5_k_m.gguf"


def find_base_model() -> Path:
    for path in BASE_MODEL_CANDIDATES:
        if path.exists():
            snapshots = path / "snapshots"
            if snapshots.exists():
                for snap in snapshots.iterdir():
                    if (snap / "config.json").exists():
                        return snap
    return None


def main():
    print("=" * 60)
    print("  Export Gemma-4-E2B-MTP XRLF to GGUF")
    print("=" * 60)

    base_model_path = find_base_model()
    if not base_model_path:
        print("  Base model not found.")
        return

    print(f"  Base model : {base_model_path}")
    print(f"  Adapter    : {ADAPTER_PATH}")
    print(f"  Output     : {OUTPUT_DIR / GGUF_NAME}")
    print(f"  MTP head   : Must be preserved for speculative decoding")
    print("=" * 60)

    if not ADAPTER_PATH.exists():
        print(f"  Adapter not found. Run finetune_gemma_e2b_mtp.py first.")
        return

    # ── 1. Load base model ─────────────────────────────────────────────────
    print("\n[1/4] Loading base model...")
    tokenizer = AutoTokenizer.from_pretrained(str(base_model_path))
    model = AutoModelForCausalLM.from_pretrained(
        str(base_model_path),
        torch_dtype="auto",
        device_map="cpu",  # Load on CPU for merge — safer for 8GB VRAM
        trust_remote_code=True,
    )

    # ── 2. Load and merge LoRA adapter ─────────────────────────────────────
    print("[2/4] Loading and merging LoRA adapter...")
    model = PeftModel.from_pretrained(model, str(ADAPTER_PATH))
    merged_model = model.merge_and_unload()

    # Verify MTP head preserved
    has_mtp = any("mtp" in name.lower() for name, _ in merged_model.named_modules())
    if has_mtp:
        print("   MTP head detected in merged model")
    else:
        print("   WARNING: MTP head not detected")

    # ── 3. Save merged model ───────────────────────────────────────────────
    print("[3/4] Saving merged model...")
    merged_name = "gemma_e2b_mtp_xrlf_merged"
    save_dir = OUTPUT_DIR / merged_name
    if save_dir.exists():
        shutil.rmtree(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    merged_model.save_pretrained(str(save_dir))
    tokenizer.save_pretrained(str(save_dir))

    # ── 4. Convert to GGUF ─────────────────────────────────────────────────
    print("[4/4] Converting to GGUF via llama.cpp convert_hf_to_gguf.py...")
    print("   Run manually after this script completes:")
    print(f'   python "C:/Users/danie/.unsloth/llama.cpp/convert_hf_to_gguf.py" '
          f'"{save_dir}" --outfile "{OUTPUT_DIR / GGUF_NAME}" --outtype f16')
    print(f'   Then quantize:')
    print(f'   llama-quantize.exe "{OUTPUT_DIR / "gemma_e2b_mtp_xrlf_f16.gguf"}" '
          f'"{OUTPUT_DIR / GGUF_NAME}" Q5_K_M')
    print(f"\n  Merged model saved to: {save_dir}")


if __name__ == "__main__":
    main()