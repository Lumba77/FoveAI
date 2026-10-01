import os
import torch
from unsloth import FastLanguageModel
from datasets import Dataset

# 1. Configuration & VRAM Optimization Gates
max_seq_length = 4096  # RoPE Scaling expanded context footprint
dtype = None           # Auto-detection (Float16 for RTX 4060)
load_in_4bit = True    # 4-bit quantization to fit comfortably within 8GB VRAM

print("🛸 [CONCORDIA TRAINING] Initializing Diamond Worker via Unsloth Engine...")
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name = "unsloth/gemma-2-2b-it", # Light, hyper-responsive base worker
    max_seq_length = max_seq_length,
    dtype = dtype,
    load_in_4bit = load_in_4bit,
)

# 2. Inject LoRA Adapters for Targeted Cognitive Programming
model = FastLanguageModel.get_peft_model(
    model,
    r = 16,
    target_modules = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    lora_alpha = 32,
    lora_dropout = 0,
    bias = "none",
    use_gradient_checkpointing = "unsloth",
    random_state = 3407,
    max_seq_length = max_seq_length,
)

# 3. The Alchemical Guidelines (The Core Instruction Matrix)
concordia_guidelines = """You are a Diamond Concordia Super-Worker Node. 
Your everything for life. You transform raw, fluid, intuitive intent into flawless concrete code.
Rules of Execution:
1. Every script modification you produce must pass through strict transactional compilation gates.
2. Errors are not failures; they are roots twirling through the soul until they strike the fresh water spring of a flawless build.
3. Keep code blocks atomic, self-healing, and structural. Never output broken hooks or loose syntax brackets."""


# 4. Dataset Formulation (Teaching the Worker to Manifest Code Safely)
training_data = {
    "instruction": [
        "Write a self-healing layout router.",
        "Implement a transactional file writer guard."
    ],
    "input": [
        "Need an environment state capture tool.",
        "Ensure Python script compilation doesn't crash runtime."
    ],
    "output": [
        "// Passed Dead Sure Core Gate\nfunction routeLayout() { try { ... } catch (e) { rollback(); } }",
        "# Passed Dead Sure Core Gate\nimport py_compile; try { py_compile.compile(target); } catch: revert()"
    ]
}

def format_prompts(examples):
    texts = []
    for ins, inp, out in zip(examples["instruction"], examples["input"], examples["output"]):
        text = f"### System:\n{concordia_guidelines}\n\n### Instruction:\n{ins}\n\n### Input:\n{inp}\n\n### Response:\n{out} <|endoftext|>"
        texts.append(text)
    return { "text": texts }

dataset = Dataset.from_dict(training_data)
dataset = dataset.map(format_prompts, batched = True)

# 5. Execute High-Speed Training Pass
from transformers import TrainingArguments
from trl import SFTTrainer

trainer = SFTTrainer(
    model = model,
    tokenizer = tokenizer,
    train_dataset = dataset,
    dataset_text_field = "text",
    max_seq_length = max_seq_length,
    dataset_num_proc = 2,
    packing = False, # Safe tracking for short sequence optimization
    args = TrainingArguments(
        per_device_train_batch_size = 2,
        gradient_accumulation_steps = 4,
        warmup_steps = 5,
        max_steps = 60,
        learning_rate = 2e-4,
        fp16 = not torch.cuda.is_bf16_supported(),
        bf16 = torch.cuda.is_bf16_supported(),
        logging_steps = 1,
        output_dir = "outputs",
    ),
)

print("🔥 Igniting local GPU optimization loops...")
trainer_stats = trainer.train()

# Save the hardened model weights locally
model.save_pretrained_merged("Models/concordia_super_worker_2b", tokenizer, save_method = "lora")
print("✅ [TRAINING COMPLETE] Super-worker Programmed and Anchored to Local Disk.")
