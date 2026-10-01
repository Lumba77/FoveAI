"""
Train Smart Router — standalone script that drives Unsloth directly.
Bypasses ForgeFineTuner's dataset curator (which only knows about HF cache)
and loads our local JSONL dataset instead.
"""

import json
import os

# ── Config ──────────────────────────────────────────────────────────────
BASE_MODEL = "unsloth/Llama-3.2-1B-Instruct"
DATASET_PATH = os.path.join(
    os.path.dirname(__file__), "datasets", "middleman-combined-v3.jsonl"
)
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output", "smart-router-lora")
MAX_SEQ_LEN = 2048
EPOCHS = 3
BATCH_SIZE = 2
GRAD_ACCUM = 4
LR = 2e-4
LORA_R = 16
LORA_ALPHA = 32


def main():
    print("=" * 60)
    print("  LUMAX Nursery — Smart Router Training")
    print("=" * 60)

    # ── 1. Load model ───────────────────────────────────────────────
    print("\n[1/5] Loading base model with Unsloth...")
    from unsloth import FastLanguageModel

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=MAX_SEQ_LEN,
        dtype=None,
        load_in_4bit=True,
    )
    print(f"  ✅ Model loaded: {BASE_MODEL}")

    # ── 2. Apply LoRA ──────────────────────────────────────────────
    print("\n[2/5] Applying LoRA adapters...")
    model = FastLanguageModel.get_peft_model(
        model,
        r=LORA_R,
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        lora_alpha=LORA_ALPHA,
        lora_dropout=0.05,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )
    print(f"  ✅ LoRA applied (r={LORA_R}, alpha={LORA_ALPHA})")

    # ── 3. Load dataset ────────────────────────────────────────────
    print(f"\n[3/5] Loading dataset from {DATASET_PATH}...")
    from datasets import Dataset

    samples = []
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line.strip())
            # Convert ChatML messages to a single text string for SFT
            msgs = row.get("messages", [])
            text_parts = []
            for m in msgs:
                role = m["role"]
                content = m["content"]
                text_parts.append(f"<|im_start|>{role}\n{content}<|im_end|>")
            text_parts.append("<|im_start|>assistant\n")  # generation prompt
            samples.append({"text": "\n".join(text_parts)})

    dataset = Dataset.from_list(samples)
    print(f"  ✅ Loaded {len(dataset)} training samples")

    # ── 4. Train ───────────────────────────────────────────────────
    print(f"\n[4/5] Starting training ({EPOCHS} epochs, batch={BATCH_SIZE})...")
    from transformers import TrainingArguments
    from trl import SFTTrainer

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    training_args = TrainingArguments(
        per_device_train_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=GRAD_ACCUM,
        warmup_steps=5,
        num_train_epochs=EPOCHS,
        learning_rate=LR,
        fp16=False,
        bf16=True,
        logging_steps=10,
        optim="adamw_8bit",
        weight_decay=0.01,
        lr_scheduler_type="linear",
        seed=42,
        output_dir=os.path.join(OUTPUT_DIR, "checkpoints"),
        report_to="none",
        save_strategy="no",  # Don't save checkpoints mid-training (avoids TRL pickle bug)
        save_total_limit=0,
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=MAX_SEQ_LEN,
        args=training_args,
    )

    trainer.train()
    print("  ✅ Training complete!")

    # ── 5. Save ────────────────────────────────────────────────────
    print(f"\n[5/5] Saving LoRA weights to {OUTPUT_DIR}...")
    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    print(f"  ✅ LoRA saved to: {OUTPUT_DIR}")
    print("\n🎉 Done! Next step: quantize to GGUF with quantizer.py")


if __name__ == "__main__":
    main()
