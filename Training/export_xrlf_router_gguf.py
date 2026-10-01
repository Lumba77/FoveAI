r"""
export_xrlf_router_gguf.py
============================
Export the fine-tuned Qwen2.5-0.5B router LoRA adapter to GGUF Q4_K_M.

Input:  Training/outputs/xrlf_router_lora/adapter
Output: Training/outputs/xrlf_router_qwen0.5b_q4_k_m.gguf
"""

import shutil
from pathlib import Path
from unsloth import FastLanguageModel
from peft import PeftModel

BASE_MODEL_PATH = Path(r"C:\Users\danie\.cache\huggingface\hub\qwen2.5-0.5-instruct")
ADAPTER_PATH = Path(r"C:\Users\danie\program\LUMAX\Training\outputs\xrlf_router_lora\adapter")
OUTPUT_DIR = Path(r"C:\Users\danie\program\LUMAX\Training\outputs")
GGUF_NAME = "xrlf_router_qwen0.5b_q4_k_m.gguf"


def main():
    print("=" * 60)
    print("  Export XRLF Router Model to GGUF")
    print("=" * 60)
    print(f"  Base model : {BASE_MODEL_PATH}")
    print(f"  Adapter    : {ADAPTER_PATH}")
    print(f"  Output     : {OUTPUT_DIR / GGUF_NAME}")
    print("=" * 60)

    if not ADAPTER_PATH.exists():
        print(f"\n❌ Adapter not found at {ADAPTER_PATH}")
        return

    print("\n[1/3] Loading base model and LoRA adapter...")
    base_model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(BASE_MODEL_PATH),
        max_seq_length=1024,
        dtype=None,
        load_in_4bit=False,
    )
    tokenizer.pad_token = tokenizer.eos_token

    model = PeftModel.from_pretrained(base_model, str(ADAPTER_PATH))

    print("[2/3] Merging LoRA adapter into base weights...")
    merged_model = model.merge_and_unload()

    merged_model_name = "xrlf_router_qwen0.5b_merged"
    merged_model.config._name_or_path = merged_model_name
    merged_model.config.name_or_path = merged_model_name

    print("[3/3] Exporting to GGUF Q4_K_M...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    save_dir = OUTPUT_DIR / merged_model_name
    gguf_dir = OUTPUT_DIR / f"{merged_model_name}_gguf"
    gguf_source = gguf_dir / f"{merged_model_name}.Q4_K_M.gguf"
    output_path = OUTPUT_DIR / GGUF_NAME

    if save_dir.exists():
        shutil.rmtree(save_dir)
    if gguf_dir.exists():
        shutil.rmtree(gguf_dir)

    save_dir.mkdir(parents=True, exist_ok=True)
    merged_model.save_pretrained(save_dir)
    tokenizer.save_pretrained(save_dir)

    merged_model.save_pretrained_gguf(
        str(save_dir),
        tokenizer,
        quantization_method="q4_k_m",
    )

    if not gguf_source.exists():
        generated = list(gguf_dir.glob("*.gguf")) if gguf_dir.exists() else []
        if generated:
            print(f"\n⚠️ Expected GGUF not at {gguf_source}, using {generated[0]}")
            shutil.copy2(generated[0], output_path)
        else:
            print("\n❌ No GGUF file found after conversion.")
            return
    else:
        shutil.copy2(gguf_source, output_path)

    print(f"\n✅ GGUF exported to:")
    print(f"   {output_path}")
    print(f"\nFile size: {output_path.stat().st_size / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()
