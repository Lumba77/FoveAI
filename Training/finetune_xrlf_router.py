r"""
finetune_xrlf_router.py
=======================
Fine-tune Qwen2.5-0.5B-Instruct as an XRLF router/draft model.
Learns to emit control tokens: " stop", " solved", " continue",
routing tags, and minimal skeletons.
"""

import unsloth
import torch
from pathlib import Path
from datasets import load_dataset
from trl import SFTTrainer, SFTConfig
from unsloth import FastLanguageModel

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_MODEL_PATH = Path(r"C:\Users\danie\.cache\huggingface\hub\qwen2.5-0.5-instruct")
TRAIN_FILE = Path(r"C:\Users\danie\program\LUMAX\Training\data\xrlf_router_train.jsonl")
EVAL_FILE = Path(r"C:\Users\danie\program\LUMAX\Training\data\xrlf_router_train.eval.jsonl")
OUTPUT_DIR = Path(r"C:\Users\danie\program\LUMAX\Training\outputs\xrlf_router_lora")

# ── Hyperparameters ────────────────────────────────────────────────────────
MAX_SEQ_LENGTH = 1024
LORA_RANK = 32
LORA_ALPHA = 64
LEARNING_RATE = 5e-4
NUM_EPOCHS = 4
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
        {"role": "system", "content": "You are an XRLF router. Emit only a control token or a tiny XRLF tag. Do not explain."}
    ]
    conversation.extend(messages)

    text = tokenizer.apply_chat_template(conversation, tokenize=False, add_generation_prompt=False)
    return {"text": text}


def main():
    print("=" * 60)
    print("  XRLF Router/Draft Model Fine-Tuning")
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

    print("\n[1/5] Loading Qwen2.5-0.5B base model...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(BASE_MODEL_PATH),
        max_seq_length=MAX_SEQ_LENGTH,
        dtype=None,
        load_in_4bit=True,
    )
    tokenizer.pad_token = tokenizer.eos_token

    print("[2/5] Adding LoRA adapter...")
    model = FastLanguageModel.get_peft_model(
        model,
        r=LORA_RANK,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        lora_alpha=LORA_ALPHA,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=3407,
    )

    print("[3/5] Loading router dataset...")
    train_dataset = load_dataset("json", data_files=str(TRAIN_FILE), split="train")
    train_dataset = train_dataset.map(lambda ex: format_messages(ex, tokenizer))

    print("[4/5] Configuring trainer...")
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
        args=sft_config,
    )

    print("[5/5] Training...")
    from peft import set_peft_model_state_dict
    from safetensors.torch import load_file
    checkpoints = sorted(OUTPUT_DIR.glob("checkpoint-*"), key=lambda p: int(p.name.split("-")[-1]))
    if checkpoints:
        latest_checkpoint = checkpoints[-1]
        adapter_weights = latest_checkpoint / "adapter_model.safetensors"
        print(f"    Loading adapter weights from: {adapter_weights}")
        state_dict = load_file(str(adapter_weights))
        set_peft_model_state_dict(model, state_dict, "default")
        print("    Loaded adapter weights, training will continue with fresh optimizer")
    else:
        print("    Starting from scratch")
    trainer.train()

    print("\nSaving LoRA adapter...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(OUTPUT_DIR / "adapter")
    tokenizer.save_pretrained(OUTPUT_DIR / "adapter")

    print(f"\n✅ Router fine-tuning complete! LoRA adapter saved to:")
    print(f"   {OUTPUT_DIR / 'adapter'}")
    print("\nNext step: export to GGUF with:")
    print(f"   python Training\\export_xrlf_router_gguf.py")


if __name__ == "__main__":
    main()
