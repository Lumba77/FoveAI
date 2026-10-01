r"""
finetune_xrlf_draft.py
======================
Fine-tune Qwen2.5-0.5B-Instruct as an XRLF-aware draft model.

Uses Unsloth + TRL SFTTrainer for fast LoRA fine-tuning.
Target: Qwen2.5-0.5B-Instruct at C:\Users\danie\.cache\huggingface\hub\qwen2.5-0.5-instruct
Output: LoRA adapter saved to Training/outputs/xrlf_draft_lora
"""

import unsloth
import torch
from pathlib import Path
from datasets import load_dataset
from trl import SFTTrainer, SFTConfig
from unsloth import FastLanguageModel

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_MODEL_PATH = Path(r"C:\Users\danie\.cache\huggingface\hub\qwen2.5-0.5-instruct")
TRAIN_FILE = Path(r"C:\Users\danie\program\LUMAX\Training\data\xrlf_draft_train.jsonl")
EVAL_FILE = Path(r"C:\Users\danie\program\LUMAX\Training\data\xrlf_draft_train.eval.jsonl")
OUTPUT_DIR = Path(r"C:\Users\danie\program\LUMAX\Training\outputs\xrlf_draft_lora")

# ── Hyperparameters (from lora-qlora-recipes skill) ────────────────────────
MAX_SEQ_LENGTH = 2048
LORA_RANK = 32
LORA_ALPHA = 64
LEARNING_RATE = 2e-4
NUM_EPOCHS = 3
BATCH_SIZE = 8
GRADIENT_ACCUMULATION_STEPS = 2
WARMUP_STEPS = 20
LOGGING_STEPS = 10
SAVE_STEPS = 100
EVAL_STEPS = 100


def format_messages(example, tokenizer):
    """Format messages list using Qwen chat template. Assistant answer is trained only."""
    messages = example.get("messages", [])
    if not messages:
        return {"text": ""}

    conversation = [
        {"role": "system", "content": "You are an XRLF draft assistant. Respond with concise XRLF tags, logic, and routing guidance."}
    ]
    conversation.extend(messages)

    text = tokenizer.apply_chat_template(conversation, tokenize=False, add_generation_prompt=False)
    return {"text": text}


def main():
    print("=" * 60)
    print("  XRLF Draft Model Fine-Tuning")
    print("=" * 60)
    print(f"  Base model : {BASE_MODEL_PATH}")
    print(f"  Train data : {TRAIN_FILE}")
    print(f"  Eval data  : {EVAL_FILE}")
    print(f"  Output     : {OUTPUT_DIR}")
    print(f"  Rank       : {LORA_RANK}")
    print(f"  Alpha      : {LORA_ALPHA}")
    print(f"  LR         : {LEARNING_RATE}")
    print(f"  Epochs     : {NUM_EPOCHS}")
    print("=" * 60)

    # ── Load base model ──────────────────────────────────────────────────────
    print("\n[1/5] Loading Qwen2.5-0.5B base model...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(BASE_MODEL_PATH),
        max_seq_length=MAX_SEQ_LENGTH,
        dtype=None,
        load_in_4bit=True,
    )

    # Ensure tokenizer has proper pad token
    tokenizer.pad_token = tokenizer.eos_token

    # ── Add LoRA adapter ─────────────────────────────────────────────────────
    print("[2/5] Adding LoRA adapter...")
    target_modules = [
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ]
    model = FastLanguageModel.get_peft_model(
        model,
        r=LORA_RANK,
        target_modules=target_modules,
        lora_alpha=LORA_ALPHA,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=3407,
    )

    # ── Load dataset ─────────────────────────────────────────────────────────
    print("[3/5] Loading dataset...")
    dataset = load_dataset(
        "json",
        data_files={
            "train": str(TRAIN_FILE),
            "eval": str(EVAL_FILE),
        },
        split=None,
    )

    def map_fn(example):
        return format_messages(example, tokenizer)

    train_dataset = dataset["train"].map(map_fn)
    eval_dataset = dataset["eval"].map(map_fn)

    # ── Configure training ───────────────────────────────────────────────────
    print("[4/5] Configuring trainer...")
    sft_config = SFTConfig(
        output_dir=str(OUTPUT_DIR),
        num_train_epochs=NUM_EPOCHS,
        per_device_train_batch_size=BATCH_SIZE,
        per_device_eval_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=GRADIENT_ACCUMULATION_STEPS,
        learning_rate=LEARNING_RATE,
        warmup_steps=WARMUP_STEPS,
        logging_steps=LOGGING_STEPS,
        save_steps=SAVE_STEPS,
        eval_strategy="steps",
        eval_steps=EVAL_STEPS,
        save_strategy="steps",
        logging_strategy="steps",
        max_length=MAX_SEQ_LENGTH,
        dataset_text_field="text",
        packing=False,
        assistant_only_loss=True,
        bf16=torch.cuda.is_bf16_supported(),
        fp16=not torch.cuda.is_bf16_supported(),
        optim="adamw_8bit",
        lr_scheduler_type="cosine",
        seed=3407,
        report_to="none",
    )

    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        args=sft_config,
    )

    # ── Train ────────────────────────────────────────────────────────────────
    print("[5/5] Training...")
    # Load adapter weights from latest checkpoint if one exists.
    # We do NOT resume optimizer/scheduler because torch.load is blocked
    # on this torch version for .pt/.pth files (CVE-2025-32434).
    checkpoints = sorted(OUTPUT_DIR.glob("checkpoint-*"), key=lambda p: int(p.name.split("-")[-1]))
    if checkpoints:
        latest_checkpoint = checkpoints[-1]
        adapter_weights = latest_checkpoint / "adapter_model.safetensors"
        print(f"    Loading adapter weights from: {adapter_weights}")
        from safetensors.torch import load_file
        from peft import set_peft_model_state_dict
        state_dict = load_file(str(adapter_weights))
        set_peft_model_state_dict(model, state_dict, "default")
        print("    Loaded adapter weights, training will continue with fresh optimizer")
    else:
        print("    Starting from scratch")
    trainer.train()

    # ── Save adapter ─────────────────────────────────────────────────────────
    print("\nSaving LoRA adapter...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(OUTPUT_DIR / "adapter")
    tokenizer.save_pretrained(OUTPUT_DIR / "adapter")

    print(f"\n✅ Fine-tuning complete! LoRA adapter saved to:")
    print(f"   {OUTPUT_DIR / 'adapter'}")
    print("\nNext step: export to GGUF with:")
    print(f"   python Training\\export_xrlf_draft_gguf.py")


if __name__ == "__main__":
    main()
