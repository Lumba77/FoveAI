r"""
finetune_xrlf_summarizer.py
===========================
Fine-tune Qwen3-0.6B as an XRLF summarizer (context compression model).

Config follows "LoRA Without Regret" reference recipe:
  - All-linear target modules (attention + MLP)
  - lora_alpha = 2 * r
  - QLoRA LR = 2e-4
  - Effective batch size = 16 (under 32 cap)
  - MAX_SEQ_LENGTH = 2048 (summarizer needs longer context than router)

Uses plain TRL + PEFT (NOT Unsloth) per the lora-qlora-recipes escape hatch:
Unsloth 2026.7.x's compiled SFTTrainer has no messages-shaped path and
injects a bogus <EOS_TOKEN> that Qwen's vocab doesn't contain.

Input:  Training/data/xrlf_summarizer_train.jsonl
Output: Training/outputs/xrlf_summarizer_lora/adapter
"""

import torch
from pathlib import Path
from datasets import load_dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model
from trl import SFTTrainer, SFTConfig

# ── Paths ──────────────────────────────────────────────────────────────────
_HUB_ROOT = Path(r"C:\Users\danie\.cache\huggingface\hub\models--Qwen--Qwen3-0.6B")


def _resolve_snapshot(hub_root: Path) -> Path:
    """Resolve the actual snapshot directory from a HF hub cache root."""
    snapshots = hub_root / "snapshots"
    if snapshots.exists():
        for snap in snapshots.iterdir():
            if (snap / "config.json").exists():
                return snap
    return hub_root


BASE_MODEL_PATH = _resolve_snapshot(_HUB_ROOT)
TRAIN_FILE = Path(r"C:\Users\danie\program\LUMAX\Training\data\xrlf_summarizer_train.jsonl")
EVAL_FILE = Path(r"C:\Users\danie\program\LUMAX\Training\data\xrlf_summarizer_eval.jsonl")
OUTPUT_DIR = Path(r"C:\Users\danie\program\LUMAX\Training\outputs\xrlf_summarizer_lora")

# ── Hyperparameters ────────────────────────────────────────────────────────
MAX_SEQ_LENGTH = 1024          # reduced from 2048 to fit 8GB VRAM
LORA_RANK = 32
LORA_ALPHA = 64                # 2 * r
LEARNING_RATE = 2e-4           # QLoRA standard
NUM_EPOCHS = 3
BATCH_SIZE = 1
GRADIENT_ACCUMULATION_STEPS = 16  # effective batch = 16
WARMUP_STEPS = 20
LOGGING_STEPS = 10
SAVE_STEPS = 100
SEED = 3407

TARGET_MODULES = [
    "q_proj", "k_proj", "v_proj", "o_proj",
    "gate_proj", "up_proj", "down_proj",
]

SYSTEM_PROMPT = (
    "You are an XRLF summarizer. Compress the input to its essential skeleton. "
    "Preserve logic, structure, and key information. Drop boilerplate, comments, "
    "and redundant details. Output only the compressed version."
)


def format_messages(example: dict, tokenizer) -> dict:
    """Format messages using Qwen chat template."""
    messages = example.get("messages", [])
    if not messages:
        return {"text": ""}

    # Ensure system prompt is first
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
    print("  XRLF Summarizer — Qwen3-0.6B LoRA SFT")
    print("=" * 60)
    print(f"  Base model : {BASE_MODEL_PATH}")
    print(f"  Train data : {TRAIN_FILE}")
    print(f"  Eval data  : {EVAL_FILE}")
    print(f"  Output     : {OUTPUT_DIR}")
    print(f"  Rank       : {LORA_RANK}")
    print(f"  Alpha      : {LORA_ALPHA} (2 * r)")
    print(f"  LR         : {LEARNING_RATE}")
    print(f"  Epochs     : {NUM_EPOCHS}")
    print(f"  Max seq    : {MAX_SEQ_LENGTH}")
    print(f"  Batch      : {BATCH_SIZE} x {GRADIENT_ACCUMULATION_STEPS} = {BATCH_SIZE * GRADIENT_ACCUMULATION_STEPS} effective")
    print("=" * 60)

    if not TRAIN_FILE.exists():
        print(f"\n❌ Training data not found at {TRAIN_FILE}")
        print("   Run prepare_xrlf_summarizer_dataset.py first.")
        return
    if not BASE_MODEL_PATH.exists():
        print(f"\n❌ Base model not found at {BASE_MODEL_PATH}")
        return

    print("\n[1/5] Loading Qwen3-0.6B base model (QLoRA 4-bit)...")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        str(BASE_MODEL_PATH),
        quantization_config=bnb_config,
        device_map="auto",
        attn_implementation="sdpa",
    )
    model.config.use_cache = False
    tokenizer = AutoTokenizer.from_pretrained(str(BASE_MODEL_PATH))
    tokenizer.pad_token = tokenizer.eos_token

    print("[2/5] Adding LoRA adapter...")
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

    print("[3/5] Loading summarizer dataset...")
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
        packing=False,
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

    print(f"\n✅ Summarizer fine-tuning complete! LoRA adapter saved to:")
    print(f"   {OUTPUT_DIR / 'adapter'}")
    print("\nNext step: export to GGUF with:")
    print(f"   python Training\\export_xrlf_summarizer_gguf.py")


if __name__ == "__main__":
    main()
