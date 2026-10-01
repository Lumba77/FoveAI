import torch
from datasets import load_dataset
from transformers import TrainingArguments
from trl import SFTTrainer
from unsloth import FastLanguageModel, is_bfloat16_supported
from unsloth.chat_templates import get_chat_template, train_on_responses_only

# Config
MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"
DATASET_PATH = "Tools/foveai-xrl/xrl_prefetch_dataset.jsonl"
MAX_SEQ_LENGTH = 4096  # Good enough for skeletons
OUTPUT_DIR = "Tools/foveai-xrl/outputs"


def format_dataset(dataset_path):
    dataset = load_dataset("json", data_files={"train": dataset_path}, split="train")
    return dataset


def main():
    print("🚀 Loading Unsloth FastLanguageModel...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=MODEL_ID,
        max_seq_length=MAX_SEQ_LENGTH,
        dtype=None,  # Auto detect
        load_in_4bit=True,
    )

    print("🧠 Adding LoRA Adapters...")
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,  # LoRA rank
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        lora_alpha=16,
        lora_dropout=0,  # Optimization
        bias="none",  # Optimization
        use_gradient_checkpointing="unsloth",  # True or "unsloth" for very long context
        random_state=3407,
        use_rslora=False,
        loftq_config=None,
    )

    print("📚 Formatting Dataset...")
    tokenizer = get_chat_template(
        tokenizer,
        chat_template="qwen-2.5",  # Standard chat template
        mapping={
            "role": "from",
            "content": "value",
            "user": "user",
            "assistant": "assistant",
        },
    )

    def formatting_prompts_func(examples):
        convos = examples["conversations"]
        texts = [
            tokenizer.apply_chat_template(
                convo, tokenize=False, add_generation_prompt=False
            )
            for convo in convos
        ]
        return {"text": texts}

    dataset = format_dataset(DATASET_PATH)
    dataset = dataset.map(
        formatting_prompts_func,
        batched=True,
    )

    # Only train on the assistant's responses (the predicted XRL URIs), ignoring the large prompt
    dataset = train_on_responses_only(
        dataset,
        tokenizer=tokenizer,
        instruction_part="<|im_start|>user\n",
        response_part="<|im_start|>assistant\n",
    )

    print("🏃 Starting Training...")
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=MAX_SEQ_LENGTH,
        dataset_num_proc=2,
        packing=False,  # Can make training 5x faster for short sequences
        args=TrainingArguments(
            per_device_train_batch_size=2,
            gradient_accumulation_steps=4,
            warmup_steps=5,
            num_train_epochs=1,
            learning_rate=2e-4,
            fp16=not is_bfloat16_supported(),
            bf16=is_bfloat16_supported(),
            logging_steps=1,
            optim="adamw_8bit",
            weight_decay=0.01,
            lr_scheduler_type="linear",
            seed=3407,
            output_dir=OUTPUT_DIR,
        ),
    )

    # Measure memory
    gpu_stats = torch.cuda.get_device_properties(0)
    start_gpu_memory = round(torch.cuda.max_memory_reserved() / 1024 / 1024 / 1024, 3)
    max_memory = round(gpu_stats.total_memory / 1024 / 1024 / 1024, 3)
    print(f"GPU = {gpu_stats.name}. Max memory = {max_memory} GB.")
    print(f"{start_gpu_memory} GB of memory reserved.")

    trainer_stats = trainer.train()

    print("💾 Saving LoRA weights...")
    model.save_pretrained("lora_model")
    tokenizer.save_pretrained("lora_model")

    # Export to GGUF
    print("📦 Exporting to GGUF (q4_k_m)...")
    # Save to 8bit Q8_0 or 4bit q4_k_m.
    # Qwen2.5 0.5B is tiny, so we can export to q8_0 for maximum accuracy, or q4_k_m for size.
    try:
        model.save_pretrained_gguf(
            "model_gguf", tokenizer, quantization_method="q4_k_m"
        )
        print("✅ Successfully exported GGUF to model_gguf/")
    except Exception as e:
        print(f"⚠️ Warning: Could not export GGUF automatically: {e}")
        print("You may need to convert it manually using llama.cpp")


if __name__ == "__main__":
    main()
