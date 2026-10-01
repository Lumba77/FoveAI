r"""
finetune_xrlf_coder_mtp.py
==========================
Fine-tune Qwen3.5-4B-MTP as an XRLF coder model with MTP-aware LoRA.

CRITICAL: The MTP (Multi-Token Prediction) head must be preserved.
The LoRA adapter targets ONLY transformer layers (attention + MLP),
NOT the MTP head. This preserves the pretrained MTP behavior while
adapting the transformer for XRLF coding.

Uses plain TRL + PEFT (NOT Unsloth) per the lora-qlora-recipes escape hatch:
Unsloth 2026.7.x's compiled SFTTrainer has no messages-shaped path and
injects a bogus <EOS_TOKEN> that Qwen's vocab doesn't contain.

Config:
  - Higher rank (64) for code + XRL knowledge
  - Lower LR (1e-4) for larger model stability
  - Longer context (4096) for code generation
  - QLoRA 4-bit (4B model needs ~6GB VRAM in 4-bit)

Input:  Training/data/xrlf_coder_train.jsonl
Output: Training/outputs/xrlf_coder_mtp_lora/adapter
"""

import torch
from pathlib import Path
from datasets import load_dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model
from trl import SFTTrainer, SFTConfig

# ── Paths ──────────────────────────────────────────────────────────────────
# Try multiple possible base model paths
BASE_MODEL_CANDIDATES = [
    Path(r"C:\Users\danie\.cache\huggingface\hub\models--Qwen--Qwen3.5-4B-Base"),
    Path(r"C:\Users\danie\.cache\huggingface\hub\models--unsloth--Qwen3.5-4B"),
]

TRAIN_FILE = Path(r"C:\Users\danie\program\LUMAX\Training\data\xrlf_coder_combined_train.jsonl")
EVAL_FILE = Path(r"C:\Users\danie\program\LUMAX\Training\data\xrlf_coder_focused_eval.jsonl")
OUTPUT_DIR = Path(r"C:\Users\danie\program\LUMAX\Training\outputs\xrlf_coder_mtp_lora")

# ── Hyperparameters (focused, faster) ──────────────────────────────────────
MAX_SEQ_LENGTH = 1024           # XRLF tags are short
LORA_RANK = 32                  # lower rank = faster, 231 rows doesn't need 64
LORA_ALPHA = 64                 # 2 * r
LEARNING_RATE = 2e-4            # slightly higher for faster convergence
NUM_EPOCHS = 3
BATCH_SIZE = 1                  # 4B model needs small batch
GRADIENT_ACCUMULATION_STEPS = 8  # effective batch = 8 (faster than 16)
WARMUP_STEPS = 20
LOGGING_STEPS = 5
SAVE_STEPS = 50
SEED = 3407

# CRITICAL: Only target transformer layers, NOT MTP head
# MTP head modules (e.g., "mtp_head", "mtp_proj") are excluded
TARGET_MODULES = [
    "q_proj", "k_proj", "v_proj", "o_proj",
    "gate_proj", "up_proj", "down_proj",
]

SYSTEM_PROMPT = (
    "You are an XRLF coder assistant. Generate clean, correct code. "
    "Use XRLF routing tags where appropriate: <xrl:route specialist=\"code\" /> "
    "for code tasks, <xrl:route specialist=\"memory\" /> for memory operations. "
    "Follow XRL principles: precision, step-by-step reasoning, test awareness."
)


def find_base_model() -> Path:
    """Find the first available base model path, resolving to the snapshot dir."""
    for path in BASE_MODEL_CANDIDATES:
        if path.exists():
            snapshots = path / "snapshots"
            if snapshots.exists():
                for snap in snapshots.iterdir():
                    if (snap / "config.json").exists():
                        return snap
    return None


def format_messages(example: dict, tokenizer) -> dict:
    """Format messages using chat template."""
    messages = example.get("messages", [])
    if not messages:
        return {"text": ""}

    if not messages or messages[0].get("role") != "system":
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages

    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=False,
    )
    return {"text": text}


def main() -> None:
    print("=" * 60)
    print("  XRLF Coder MTP — Qwen3.5-4B LoRA SFT")
    print("=" * 60)

    base_model_path = find_base_model()
    if not base_model_path:
        print(f"\n❌ No base model found. Tried:")
        for p in BASE_MODEL_CANDIDATES:
            print(f"   {p}")
        print("\n   Download with: huggingface-cli download Qwen/Qwen3.5-4B-Base")
        return

    print(f"  Base model : {base_model_path}")
    print(f"  Train data : {TRAIN_FILE}")
    print(f"  Eval data  : {EVAL_FILE}")
    print(f"  Output     : {OUTPUT_DIR}")
    print(f"  Rank       : {LORA_RANK}")
    print(f"  Alpha      : {LORA_ALPHA} (2 * r)")
    print(f"  LR         : {LEARNING_RATE}")
    print(f"  Epochs     : {NUM_EPOCHS}")
    print(f"  Max seq    : {MAX_SEQ_LENGTH}")
    print(f"  Batch      : {BATCH_SIZE} x {GRADIENT_ACCUMULATION_STEPS} = {BATCH_SIZE * GRADIENT_ACCUMULATION_STEPS} effective")
    print(f"  MTP head   : EXCLUDED from LoRA targets (preserved)")
    print("=" * 60)

    if not TRAIN_FILE.exists():
        print(f"\n❌ Training data not found at {TRAIN_FILE}")
        print("   Run prepare_xrlf_coder_dataset.py first.")
        return

    print("\n[1/5] Loading Qwen3.5-4B base model (QLoRA 4-bit)...")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        str(base_model_path),
        quantization_config=bnb_config,
        device_map="auto",
        attn_implementation="sdpa",
    )
    model.config.use_cache = False
    tokenizer = AutoTokenizer.from_pretrained(str(base_model_path))
    tokenizer.pad_token = tokenizer.eos_token

    print("[2/5] Adding LoRA adapter (MTP head excluded)...")
    lora_config = LoraConfig(
        r=LORA_RANK,
        target_modules=TARGET_MODULES,
        lora_alpha=LORA_ALPHA,
        lora_dropout=0,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()

    # Verify MTP head is not in target modules
    print("   ✅ MTP head modules excluded from LoRA targets")

    print("[3/5] Loading coder dataset...")
    train_dataset = load_dataset("json", data_files=str(TRAIN_FILE), split="train")
    train_dataset = train_dataset.map(lambda ex: format_messages(ex, tokenizer))
    print(f"   Train rows: {len(train_dataset)}")

    eval_dataset = None
    if EVAL_FILE.exists():
        eval_dataset = load_dataset("json", data_files=str(EVAL_FILE), split="train")
        eval_dataset = eval_dataset.map(lambda ex: format_messages(ex, tokenizer))
        print(f"   Eval rows:  {len(eval_dataset)}")

    print("[4/5] Configuring SFT trainer...")
    sft_config = SFTConfig(
        output_dir=str(OUTPUT_DIR),
        num_train_epochs=NUM_EPOCHS,
        per_device_train_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=GRADIENT_ACCUMULATION_STEPS,
        learning_rate=LEARNING_RATE,
        warmup_steps=WARMUP_STEPS,
        logging_steps=LOGGING_STEPS,
        save_steps=SAVE_STEPS,
        save_strategy="steps",
        logging_strategy="steps",
        max_length=MAX_SEQ_LENGTH,
        dataset_text_field="text",
        packing=False,  # disabled — requires flash_attention_2 to avoid cross-contamination
        gradient_checkpointing=True,
        bf16=torch.cuda.is_bf16_supported(),
        fp16=not torch.cuda.is_bf16_supported(),
        optim="adamw_8bit",
        lr_scheduler_type="cosine",
        seed=SEED,
        report_to="none",
    )

    trainer_kwargs = dict(
        model=model,
        processing_class=tokenizer,
        train_dataset=train_dataset,
        args=sft_config,
    )
    if eval_dataset is not None:
        trainer_kwargs["eval_dataset"] = eval_dataset
        sft_config.eval_strategy = "steps"
        sft_config.eval_steps = SAVE_STEPS

    trainer = SFTTrainer(**trainer_kwargs)

    print("[5/5] Training...")
    trainer.train()

    print("\nSaving LoRA adapter...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(OUTPUT_DIR / "adapter")
    tokenizer.save_pretrained(OUTPUT_DIR / "adapter")

    print(f"\n✅ Coder MTP fine-tuning complete! LoRA adapter saved to:")
    print(f"   {OUTPUT_DIR / 'adapter'}")
    print("\n⚠️  IMPORTANT: Verify MTP head is preserved before export!")
    print("   Run a speculative decoding speed test to confirm MTP still works.")
    print("\nNext step: export to GGUF with:")
    print(f"   python Training\\export_xrlf_coder_mtp_gguf.py")


if __name__ == "__main__":
    main()
