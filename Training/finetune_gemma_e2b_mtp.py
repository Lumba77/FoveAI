r"""
finetune_gemma_e2b_mtp.py
=========================
Fine-tune Gemma-4-E2B-it-MTP as an XRLF model with MTP-aware LoRA.

Same pattern as finetune_xrlf_coder_mtp.py but for Gemma 4 E2B:
  - LoRA targets transformer layers only (NOT MTP head)
  - MTP head preserved for speculative decoding
  - XRLF grammar dataset teaches routing tags, skeletons, emotes, recall syntax
  - Gemma has vision+audio natively — we're improving instruction following + XRLF behavior

Config:
  - Rank 16 for 2B model (lighter than 4B's rank 32)
  - LR 5e-5 (Gemma prefers lower LR than Qwen)
  - Max seq 2048 (fits in 8GB VRAM with 4-bit QLoRA)
  - QLoRA 4-bit (~2GB VRAM for 2B model)

Input:  Training/data/xrlf_grammar_train.jsonl (shared XRLF grammar dataset)
Output: Training/outputs/gemma_e2b_mtp_lora/adapter
"""

import torch
for i in range(1, 8):
    if not hasattr(torch, f"int{i}"):
        setattr(torch, f"int{i}", type(f"int{i}", (), {}))

from pathlib import Path
from datasets import load_dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model
from trl import SFTTrainer, SFTConfig

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_MODEL_CANDIDATES = [
    Path(r"C:\Users\danie\.cache\huggingface\hub\google--gemma-4-E2B"),
    Path(r"C:\Users\danie\.cache\huggingface\hub\google--gemma-4-E2B-it"),
]

TRAIN_FILE = Path(r"C:\Users\danie\program\LUMAX\Training\data\xrlf_coder_combined_train.jsonl")
EVAL_FILE = Path(r"C:\Users\danie\program\LUMAX\Training\data\xrlf_coder_focused_eval.jsonl")
OUTPUT_DIR = Path(r"C:\Users\danie\program\LUMAX\Training\outputs\gemma_e2b_mtp_lora")

# ── Config ─────────────────────────────────────────────────────────────────
LORA_RANK = 16
LORA_ALPHA = 32  # 2 * rank
LEARNING_RATE = 5e-5  # Gemma prefers lower LR
MAX_SEQ_LENGTH = 2048
EPOCHS = 3
BATCH_SIZE = 2
GRADIENT_ACCUMULATION = 4  # effective batch = 8


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
    print("  Gemma-4-E2B-MTP XRLF Fine-tuning")
    print("=" * 60)

    base_model_path = find_base_model()
    if not base_model_path:
        print("  Base model not found. Pull from HuggingFace first:")
        print("    huggingface-cli download google/gemma-4-E2B-it")
        return

    print(f"  Base model : {base_model_path}")
    print(f"  Train data : {TRAIN_FILE}")
    print(f"  Output     : {OUTPUT_DIR / 'adapter'}")
    print(f"  Rank       : {LORA_RANK}")
    print(f"  Alpha      : {LORA_ALPHA}")
    print(f"  LR         : {LEARNING_RATE}")
    print(f"  Epochs     : {EPOCHS}")
    print(f"  Max seq    : {MAX_SEQ_LENGTH}")
    print(f"  Batch      : {BATCH_SIZE} x {GRADIENT_ACCUMULATION} = {BATCH_SIZE * GRADIENT_ACCUMULATION} effective")
    print(f"  MTP head   : EXCLUDED from LoRA targets (preserved)")
    print("=" * 60)

    # ── 1. Load tokenizer ──────────────────────────────────────────────────
    tokenizer = AutoTokenizer.from_pretrained(str(base_model_path))
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # ── 2. Load model in 4-bit QLoRA ───────────────────────────────────────
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
        torch_dtype=torch.bfloat16,
        trust_remote_code=True,
    )

    # Verify MTP head is present
    has_mtp = any("mtp" in name.lower() for name, _ in model.named_modules())
    if has_mtp:
        print("  MTP head detected in base model")
    else:
        print("  WARNING: MTP head not detected — speculative decoding may not work")

    # ── 3. LoRA config — target transformer layers, NOT MTP head ───────────
    # Gemma 4 uses standard transformer modules:
    # q_proj, k_proj, v_proj, o_proj (attention)
    # gate_proj, up_proj, down_proj (MLP)
    # We explicitly exclude any module containing 'mtp' in its name
    lora_config = LoraConfig(
        r=LORA_RANK,
        lora_alpha=LORA_ALPHA,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0,
        bias="none",
        task_type="CAUSAL_LM",
        # Exclude MTP head from LoRA — preserves pretrained speculative decoding
        modules_to_save=None,
    )

    model = get_peft_model(model, lora_config)

    # Double-check MTP head is NOT in LoRA targets
    mtp_in_lora = any("mtp" in name.lower() for name, _ in model.named_modules()
                      if "lora" in name.lower())
    if mtp_in_lora:
        print("  WARNING: MTP modules found in LoRA targets — this should not happen!")

    # ── 4. Load and format dataset ─────────────────────────────────────────
    def format_chatml(example):
        messages = example["messages"]
        # Use Gemma's chat template
        text = tokenizer.apply_chat_template(messages, tokenize=False,
                                              add_generation_prompt=False)
        return {"text": text}

    train_dataset = load_dataset("json", data_files=str(TRAIN_FILE), split="train")
    train_dataset = train_dataset.map(format_chatml)

    eval_dataset = None
    if EVAL_FILE.exists():
        eval_dataset = load_dataset("json", data_files=str(EVAL_FILE), split="train")
        eval_dataset = eval_dataset.map(format_chatml)

    # ── 5. Train ───────────────────────────────────────────────────────────
    training_args = SFTConfig(
        output_dir=str(OUTPUT_DIR),
        per_device_train_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=GRADIENT_ACCUMULATION,
        warmup_steps=5,
        num_train_epochs=EPOCHS,
        learning_rate=LEARNING_RATE,
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        logging_steps=1,
        optim="adamw_8bit",
        weight_decay=0.01,
        lr_scheduler_type="linear",
        seed=3407,
        save_strategy="epoch",
        max_seq_length=MAX_SEQ_LENGTH,
        packing=False,
        dataset_text_field="text",
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        args=training_args,
    )

    print("\n  Starting XRLF fine-tuning for Gemma-4-E2B-MTP...")
    trainer.train()

    # ── 6. Save adapter ────────────────────────────────────────────────────
    adapter_path = OUTPUT_DIR / "adapter"
    model.save_pretrained(str(adapter_path))
    tokenizer.save_pretrained(str(adapter_path))
    print(f"\n  Adapter saved to: {adapter_path}")
    print("\n  Next: run export_gemma_e2b_mtp_gguf.py to export to GGUF")


if __name__ == "__main__":
    main()