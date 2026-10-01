r"""
export_coder_mtp_clean.py
=========================
Export the XRLF coder MTP LoRA to GGUF without Unsloth.
Uses plain transformers + PEFT (merge) + llama.cpp convert (GGUF).

Per AGENT.md lesson: Unsloth's SFTTrainer monkeypatches trl.SFTTrainer
and injects bogus <EOS_TOKEN>. We trained without Unsloth, so we
export without it too.

Input:  Training/outputs/xrlf_coder_mtp_lora/adapter
Output: Training/outputs/xrlf_coder_mtp_q4_k_m.gguf
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Disable Unsloth completely
os.environ["UNSLOTH_DISABLE"] = "1"

ADAPTER_PATH = Path(r"C:\Users\danie\program\LUMAX\Training\outputs\xrlf_coder_mtp_lora\adapter")
OUTPUT_DIR = Path(r"C:\Users\danie\program\LUMAX\Training\outputs")
MERGED_DIR = OUTPUT_DIR / "xrlf_coder_mtp_merged"
GGUF_OUTPUT = OUTPUT_DIR / "xrlf_coder_mtp_q4_k_m.gguf"

# Base model — the MTP variant
BASE_MODEL_CANDIDATES = [
    Path(r"C:\Users\danie\.cache\huggingface\hub\models--unsloth--Qwen3.5-4B-MTP"),
    Path(r"C:\Users\danie\.cache\huggingface\hub\models--Qwen--Qwen3.5-4B-Base"),
    Path(r"C:\Users\danie\.cache\huggingface\hub\models--unsloth--Qwen3.5-4B"),
]


def find_base_model() -> Path:
    for path in BASE_MODEL_CANDIDATES:
        if not path.exists():
            continue
        snapshots = path / "snapshots"
        if snapshots.exists():
            for snap in snapshots.iterdir():
                if (snap / "config.json").exists():
                    return snap
    return None


def main() -> None:
    print("=" * 60)
    print("  Export XRLF Coder MTP → GGUF (No Unsloth)")
    print("=" * 60)

    if not ADAPTER_PATH.exists():
        print(f"\n  ❌ Adapter not found: {ADAPTER_PATH}")
        return

    base_model_path = find_base_model()
    if not base_model_path:
        print(f"\n  ❌ No base model found in candidates:")
        for c in BASE_MODEL_CANDIDATES:
            print(f"     {c}")
        return

    print(f"  Base model : {base_model_path}")
    print(f"  Adapter    : {ADAPTER_PATH}")
    print(f"  Output     : {GGUF_OUTPUT}")

    # Step 1: Load base model + adapter with plain transformers
    print("\n  [1/4] Loading base model (transformers, no Unsloth)...")
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    model = AutoModelForCausalLM.from_pretrained(
        str(base_model_path),
        torch_dtype="auto",
        device_map="cpu",
        trust_remote_code=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(str(base_model_path), trust_remote_code=True)

    print("  [2/4] Loading LoRA adapter...")
    model = PeftModel.from_pretrained(model, str(ADAPTER_PATH))

    print("  [3/4] Merging LoRA into base weights...")
    merged = model.merge_and_unload()

    # Check for MTP head
    has_mtp = any("mtp" in name.lower() for name, _ in merged.named_modules())
    if has_mtp:
        print("       ✅ MTP head detected — speculative decoding should work")
    else:
        print("       ⚠️ MTP head not detected — speculative decoding may not work")

    # Save merged model
    if MERGED_DIR.exists():
        shutil.rmtree(MERGED_DIR)
    MERGED_DIR.mkdir(parents=True, exist_ok=True)

    merged.config._name_or_path = "xrlf-coder-mtp-qwen3.5-4b"
    merged.save_pretrained(MERGED_DIR)
    tokenizer.save_pretrained(MERGED_DIR)
    print(f"       Merged model saved to {MERGED_DIR}")

    # Step 4: Convert to GGUF using llama.cpp
    print("\n  [4/4] Converting to GGUF Q4_K_M...")
    llama_cpp = Path(r"C:\llama.cpp")
    if not llama_cpp.exists():
        llama_cpp = Path(r"C:\Users\danie\llama.cpp")

    convert_script = llama_cpp / "convert_hf_to_gguf.py"
    if not convert_script.exists():
        print(f"\n  ❌ llama.cpp convert script not found at {convert_script}")
        print("     Please convert manually or install llama.cpp")
        print(f"     Merged model is at: {MERGED_DIR}")
        return

    gguf_dir = OUTPUT_DIR / "xrlf_coder_mtp_gguf"
    if gguf_dir.exists():
        shutil.rmtree(gguf_dir)
    gguf_dir.mkdir(parents=True, exist_ok=True)

    # Convert HF → GGUF (F16 first, then quantize)
    f16_gguf = gguf_dir / "xrlf_coder_mtp.F16.gguf"

    print(f"     Converting HF → F16 GGUF...")
    result = subprocess.run([
        sys.executable, str(convert_script),
        str(MERGED_DIR),
        "--outfile", str(f16_gguf),
        "--outtype", "f16",
    ], capture_output=True, text=True)

    if result.returncode != 0:
        print(f"     ❌ Conversion failed:\n{result.stderr[-500:]}")
        return

    # Quantize to Q4_K_M
    quantize_exe = llama_cpp / "build" / "bin" / "quantize.exe"
    if not quantize_exe.exists():
        quantize_exe = llama_cpp / "quantize.exe"

    if quantize_exe.exists():
        print(f"     Quantizing F16 → Q4_K_M...")
        result = subprocess.run([
            str(quantize_exe),
            str(f16_gguf),
            str(GGUF_OUTPUT),
            "Q4_K_M",
        ], capture_output=True, text=True)

        if result.returncode != 0:
            print(f"     ❌ Quantization failed:\n{result.stderr[-500:]}")
            # Fall back to F16
            shutil.copy2(f16_gguf, GGUF_OUTPUT)
            print(f"     ⚠️ Using F16 instead")
    else:
        # No quantize binary — use F16
        shutil.copy2(f16_gguf, GGUF_OUTPUT)
        print(f"     ⚠️ No quantize.exe found — using F16")

    size_mb = GGUF_OUTPUT.stat().st_size / 1024 / 1024
    print(f"\n  ✅ GGUF exported: {GGUF_OUTPUT}")
    print(f"     Size: {size_mb:.1f} MB")
    print(f"\n  Next: pack as .xrlf with package_big_models_xrlf.py --model qwen3.5-4b-mtp")


if __name__ == "__main__":
    main()
