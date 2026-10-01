"""
Quantize Smart Router — Standalone script to export the fine-tuned LoRA to GGUF.
Uses Unsloth's native fast GGUF exporter.
"""

import os
import sys

BASE_MODEL = "unsloth/Llama-3.2-1B-Instruct"
LORA_DIR = os.path.join(os.path.dirname(__file__), "output", "smart-router-lora")
GGUF_DIR = os.path.join(os.path.dirname(__file__), "output", "smart-router-gguf")

# We'll export a standard 4-bit quantization (Q4_K_M) which is perfect for LM Studio
QUANT_METHOD = "q4_k_m"


def main():
    print("=" * 60)
    print("  LUMAX Nursery — Smart Router Quantizer")
    print("=" * 60)

    if not os.path.exists(LORA_DIR):
        print(f"❌ Error: LoRA weights not found at {LORA_DIR}")
        print("Did the training finish successfully?")
        sys.exit(1)

    os.makedirs(GGUF_DIR, exist_ok=True)

    print(f"\n[1/3] Loading base model ({BASE_MODEL}) + LoRA adapters...")
    import torch
    from unsloth import FastLanguageModel

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=LORA_DIR,  # Unsloth automatically handles loading base + lora from a saved peft dir
        max_seq_length=2048,
        dtype=torch.float16,
        load_in_4bit=False,  # Load in 16-bit to merge properly before GGUF quant
    )
    print("  ✅ Model and LoRA loaded successfully.")

    print(f"\n[2/3] Exporting to GGUF ({QUANT_METHOD})...")
    print(
        "  (This will automatically merge the LoRA into the base weights and run llama.cpp)"
    )

    # Unsloth's native GGUF save (this is magic)
    model.save_pretrained_gguf(GGUF_DIR, tokenizer, quantization_method=QUANT_METHOD)

    print("\n[3/3] Quantization Complete!")
    print(f"  ✅ GGUF file saved in: {GGUF_DIR}")
    print("\nNext step: Drag and drop the .gguf file into LM Studio!")


if __name__ == "__main__":
    main()
