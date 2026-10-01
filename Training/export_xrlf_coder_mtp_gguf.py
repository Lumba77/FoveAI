r"""
export_xrlf_coder_mtp_gguf.py
=============================
Export the fine-tuned Qwen3.5-4B-MTP coder LoRA adapter to GGUF Q4_K_M.

CRITICAL: The MTP head metadata must be preserved during export for
speculative decoding to work. This script uses Unsloth's GGUF export
which should preserve the full model architecture including MTP.

Input:  Training/outputs/xrlf_coder_mtp_lora/adapter
Output: Training/outputs/xrlf_coder_mtp_q4_k_m.gguf
"""

import shutil
from pathlib import Path
from unsloth import FastLanguageModel
from peft import PeftModel

BASE_MODEL_CANDIDATES = [
    Path(r"C:\Users\danie\.cache\huggingface\hub\models--Qwen--Qwen3.5-4B-Base"),
    Path(r"C:\Users\danie\.cache\huggingface\hub\models--unsloth--Qwen3.5-4B"),
]
ADAPTER_PATH = Path(r"C:\Users\danie\program\LUMAX\Training\outputs\xrlf_coder_mtp_lora\adapter")
OUTPUT_DIR = Path(r"C:\Users\danie\program\LUMAX\Training\outputs")
GGUF_NAME = "xrlf_coder_mtp_q4_k_m.gguf"


def find_base_model() -> Path:
    for path in BASE_MODEL_CANDIDATES:
        if path.exists():
            snapshots = path / "snapshots"
            if snapshots.exists():
                for snap in snapshots.iterdir():
                    if (snap / "config.json").exists():
                        return snap
    return None


def main() -> None:
    print("=" * 60)
    print("  Export XRLF Coder MTP to GGUF (Qwen3.5-4B)")
    print("=" * 60)

    base_model_path = find_base_model()
    if not base_model_path:
        print(f"\n❌ No base model found.")
        return

    print(f"  Base model : {base_model_path}")
    print(f"  Adapter    : {ADAPTER_PATH}")
    print(f"  Output     : {OUTPUT_DIR / GGUF_NAME}")
    print(f"  MTP head   : Must be preserved for speculative decoding")
    print("=" * 60)

    if not ADAPTER_PATH.exists():
        print(f"\n❌ Adapter not found at {ADAPTER_PATH}")
        print("   Run finetune_xrlf_coder_mtp.py first.")
        return

    print("\n[1/3] Loading base model and LoRA adapter...")
    base_model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(base_model_path),
        max_seq_length=4096,
        dtype=None,
        load_in_4bit=False,
    )
    tokenizer.pad_token = tokenizer.eos_token

    model = PeftModel.from_pretrained(base_model, str(ADAPTER_PATH))

    print("[2/3] Merging LoRA adapter into base weights...")
    merged_model = model.merge_and_unload()

    # Verify MTP head is still present
    has_mtp = any("mtp" in name.lower() for name, _ in merged_model.named_modules())
    if has_mtp:
        print("   ✅ MTP head detected in merged model")
    else:
        print("   ⚠️ MTP head not detected — speculative decoding may not work")

    merged_model_name = "xrlf_coder_mtp_qwen3.5-4b_merged"
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
    print("\n⚠️  Run speculative decoding speed test to verify MTP works:")
    print("   python Training\\evaluate_xrlf_coder_mtp.py --speed-test")


if __name__ == "__main__":
    main()
