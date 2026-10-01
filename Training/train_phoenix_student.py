#!/usr/bin/env python3
"""
Phoenix Student Training — Sprint 3
Fine-tunes a 7B model on skeleton→full code pairs using Unsloth + LoRA.
Starts with Gemma-2-2B for rapid prototyping, then scales to Qwen2.5-7B.

Usage:
    # Quick prototype with 2B
    python Training/train_phoenix_student.py --model gemma-2-2b --epochs 3

    # Full training with 7B
    python Training/train_phoenix_student.py --model qwen2.5-7b --epochs 5 --lr 2e-4

    # Resume from checkpoint
    python Training/train_phoenix_student.py --resume outputs/phoenix_student/checkpoint-100

Output:
    outputs/phoenix_student/  — LoRA adapters + merged model
    Training/phoenix_eval_report.md  — evaluation results
"""

import os

# Disable torch.compile (Triton version incompatibility with inductor backend)
os.environ["TORCH_COMPILE_DISABLE"] = "1"
os.environ["TORCHDYNAMO_DISABLE"] = "1"

import sys
import json
import time
import math
import argparse
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

import torch
import torch.nn.functional as F
from datasets import Dataset, load_dataset

# ── Paths ──────────────────────────────────────────────────────
LUMAX_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = LUMAX_ROOT / "Training" / "phoenix_teacher_dataset.jsonl"
DEFAULT_OUTPUT_DIR = LUMAX_ROOT / "outputs" / "phoenix_student"
DEFAULT_EVAL_REPORT = LUMAX_ROOT / "Training" / "phoenix_eval_report.md"

# ── Logging ────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("train_phoenix")

# ── Model Registry ─────────────────────────────────────────────
MODEL_REGISTRY = {
    "gemma-2-2b": {
        "name": "unsloth/gemma-2-2b-it",
        "context": 4096,
        "vram_4bit_gb": 1.5,
        "description": "Lightweight prototype — fits easily on RTX 4060",
    },
    "qwen2.5-7b": {
        "name": "unsloth/Qwen2.5-7B-Instruct",
        "context": 4096,
        "vram_4bit_gb": 4.0,
        "description": "Target model — fits RTX 4060 with 4-bit",
    },
    "deepseek-coder-6.7b": {
        "name": "unsloth/deepseek-coder-6.7b-instruct",
        "context": 4096,
        "vram_4bit_gb": 4.0,
        "description": "Strong code alternative to Qwen",
    },
}


def load_dataset_from_jsonl(path: Path, max_samples: int = 0) -> Dataset:
    """Load skeleton→full pairs from JSONL dataset."""
    logger.info(f"Loading dataset from {path}")
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    
    if max_samples > 0:
        records = records[:max_samples]
    
    logger.info(f"Loaded {len(records)} records")
    
    # Convert to HuggingFace Dataset
    data = {
        "skeleton": [r.get("skeleton", r.get("best_output", "")) for r in records],
        "full": [r.get("original_full", "") for r in records],
        "filepath": [records[i].get("filepath", f"pair_{i}") for i in range(len(records))],
    }
    
    dataset = Dataset.from_dict(data)
    return dataset


def format_training_pair(skeleton: str, full: str) -> str:
    """Format a skeleton→full pair for training.
    
    Format:
    ### Skeleton:
    {skeleton}
    
    ### Full Implementation:
    {full}
    """
    return f"### Skeleton:\n{skeleton}\n\n### Full Implementation:\n{full}"


def tokenize_function(examples, tokenizer, max_seq_length: int):
    """Tokenize skeleton→full pairs for causal LM training."""
    texts = []
    for skel, full in zip(examples["skeleton"], examples["full"]):
        text = format_training_pair(skel, full)
        texts.append(text)
    
    tokenized = tokenizer(
        texts,
        truncation=True,
        padding="max_length",
        max_length=max_seq_length,
        return_tensors=None,
    )
    
    # For causal LM, labels = input_ids
    tokenized["labels"] = tokenized["input_ids"].copy()
    
    return tokenized


def compute_metrics(model, tokenizer, eval_dataset, device) -> Dict[str, float]:
    """Compute evaluation metrics on a held-out set."""
    model.eval()
    total_loss = 0.0
    total_tokens = 0
    exact_matches = 0
    total_pairs = 0
    
    with torch.no_grad():
        for i, example in enumerate(eval_dataset):
            skeleton = example["skeleton"]
            full = example["full"]
            
            # Tokenize
            input_text = format_training_pair(skeleton, "")
            inputs = tokenizer(input_text, return_tensors="pt", truncation=True, 
                              max_length=4096).to(device)
            
            # Generate
            outputs = model.generate(
                **inputs,
                max_new_tokens=512,
                temperature=0.3,
                do_sample=True,
                pad_token_id=tokenizer.eos_token_id,
            )
            
            generated = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
            
            # Compare with ground truth
            full_clean = full.strip()[:500]  # Compare first 500 chars
            gen_clean = generated.strip()[:500]
            
            # Exact match (relaxed — first 100 chars)
            if full_clean[:100] == gen_clean[:100]:
                exact_matches += 1
            
            total_pairs += 1
    
    accuracy = exact_matches / max(total_pairs, 1)
    
    return {
        "exact_match_accuracy": accuracy,
        "total_eval_pairs": total_pairs,
    }


def main():
    parser = argparse.ArgumentParser(description="Phoenix Student Training — Sprint 3")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET), help="Training dataset (JSONL)")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Output directory")
    parser.add_argument("--eval-report", default=str(DEFAULT_EVAL_REPORT), help="Evaluation report path")
    parser.add_argument("--model", default="gemma-2-2b", choices=list(MODEL_REGISTRY.keys()),
                       help="Base model to fine-tune")
    parser.add_argument("--epochs", type=int, default=3, help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=2, help="Per-device batch size")
    parser.add_argument("--grad-accum", type=int, default=4, help="Gradient accumulation steps")
    parser.add_argument("--lr", type=float, default=2e-4, help="Learning rate")
    parser.add_argument("--max-steps", type=int, default=0, help="Max training steps (0=auto from epochs)")
    parser.add_argument("--max-seq-length", type=int, default=4096, help="Max sequence length")
    parser.add_argument("--lora-r", type=int, default=16, help="LoRA rank")
    parser.add_argument("--lora-alpha", type=int, default=32, help="LoRA alpha")
    parser.add_argument("--eval-split", type=float, default=0.1, help="Fraction for evaluation")
    parser.add_argument("--max-samples", type=int, default=0, help="Limit samples (0=all)")
    parser.add_argument("--resume", type=str, default="", help="Resume from checkpoint path")
    parser.add_argument("--save-steps", type=int, default=50, help="Save checkpoint every N steps")
    parser.add_argument("--logging-steps", type=int, default=10, help="Log every N steps")
    parser.add_argument("--warmup-steps", type=int, default=10, help="Warmup steps")
    parser.add_argument("--seed", type=int, default=3407, help="Random seed")
    args = parser.parse_args()
    
    dataset_path = Path(args.dataset)
    output_dir = Path(args.output_dir)
    eval_report_path = Path(args.eval_report)
    
    if not dataset_path.exists():
        logger.error(f"Dataset not found: {dataset_path}")
        logger.error("Run Training/distill_teacher.py first (Sprint 2)")
        sys.exit(1)
    
    model_info = MODEL_REGISTRY[args.model]
    logger.info(f"Model: {model_info['name']} ({model_info['description']})")
    logger.info(f"Estimated VRAM: {model_info['vram_4bit_gb']}GB (4-bit)")
    
    # ── Check CUDA ─────────────────────────────────────────────
    if not torch.cuda.is_available():
        logger.error("CUDA is not available! Training requires a GPU.")
        sys.exit(1)
    
    device = torch.device("cuda")
    logger.info(f"Using device: {torch.cuda.get_device_name(0)}")
    logger.info(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f}GB")
    
    # ── Load Dataset ───────────────────────────────────────────
    dataset = load_dataset_from_jsonl(dataset_path, args.max_samples)
    
    # Split into train/eval
    if args.eval_split > 0:
        split_dataset = dataset.train_test_split(test_size=args.eval_split, seed=args.seed)
        train_dataset = split_dataset["train"]
        eval_dataset = split_dataset["test"]
        logger.info(f"Train: {len(train_dataset)} pairs, Eval: {len(eval_dataset)} pairs")
    else:
        train_dataset = dataset
        eval_dataset = None
    
    # ── Load Model ─────────────────────────────────────────────
    print()
    print("=" * 60)
    print(f"  Loading {model_info['name']}...")
    print("=" * 60)
    
    from unsloth import FastLanguageModel
    
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_info["name"],
        max_seq_length=args.max_seq_length,
        dtype=None,  # Auto-detect (fp16 for RTX 4060)
        load_in_4bit=True,
        device_map="auto",
    )
    
    logger.info(f"Model loaded: {sum(p.numel() for p in model.parameters()):,} params")
    
    # ── Add LoRA Adapters ──────────────────────────────────────
    model = FastLanguageModel.get_peft_model(
        model,
        r=args.lora_r,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        lora_alpha=args.lora_alpha,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=args.seed,
        max_seq_length=args.max_seq_length,
    )
    
    logger.info(f"LoRA adapters added (r={args.lora_r}, alpha={args.lora_alpha})")
    logger.info(f"Trainable params: {sum(p.numel() for p in model.parameters() if p.requires_grad):,}")
    
    # ── Tokenize Dataset ───────────────────────────────────────
    logger.info("Tokenizing dataset...")
    
    def tokenize_wrapper(examples):
        return tokenize_function(examples, tokenizer, args.max_seq_length)
    
    train_dataset = train_dataset.map(
        tokenize_wrapper,
        batched=True,
        remove_columns=["skeleton", "full", "filepath"],
    )
    
    if eval_dataset is not None:
        eval_dataset = eval_dataset.map(
            tokenize_wrapper,
            batched=True,
            remove_columns=["skeleton", "full", "filepath"],
        )
    
    # ── Training Setup ─────────────────────────────────────────
    from transformers import TrainingArguments
    from trl import SFTTrainer
    
    # Calculate max steps if not specified
    if args.max_steps == 0:
        steps_per_epoch = len(train_dataset) // (args.batch_size * args.grad_accum)
        max_steps = steps_per_epoch * args.epochs
    else:
        max_steps = args.max_steps
    
    logger.info(f"Training for {max_steps} steps ({args.epochs} epochs)")
    
    training_args = TrainingArguments(
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        warmup_steps=args.warmup_steps,
        max_steps=max_steps,
        learning_rate=args.lr,
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        logging_steps=args.logging_steps,
        save_steps=args.save_steps,
        eval_strategy="steps" if eval_dataset is not None else "no",
        eval_steps=args.save_steps if eval_dataset is not None else None,
        output_dir=str(output_dir),
        save_total_limit=3,
        load_best_model_at_end=True if eval_dataset is not None else False,
        report_to="none",
        seed=args.seed,
        dataloader_num_workers=0,  # Windows compatibility
    )
    
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        dataset_text_field="input_ids",  # Already tokenized
        max_seq_length=args.max_seq_length,
        dataset_num_proc=1,
        packing=False,
        args=training_args,
    )
    
    # ── Train ──────────────────────────────────────────────────
    print()
    print("=" * 60)
    print(f"  🔥 Training Phoenix Student ({model_info['name']})")
    print(f"  Device: {torch.cuda.get_device_name(0)}")
    print(f"  VRAM: {torch.cuda.mem_get_info()[1] / 1e9:.1f}GB")
    print(f"  Steps: {max_steps} | LR: {args.lr} | Batch: {args.batch_size}")
    print("=" * 60)
    print()
    
    t0 = time.time()
    trainer_stats = trainer.train(resume_from_checkpoint=args.resume if args.resume else None)
    elapsed = time.time() - t0
    
    # ── Save Model ─────────────────────────────────────────────
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save LoRA adapters
    model.save_pretrained(str(output_dir / "lora"))
    tokenizer.save_pretrained(str(output_dir / "lora"))
    logger.info(f"LoRA adapters saved to {output_dir / 'lora'}")
    
    # Save merged model (4-bit)
    logger.info("Saving merged model (4-bit)...")
    model.save_pretrained_merged(
        str(output_dir / "merged_4bit"),
        tokenizer,
        save_method="merged_16bit",  # 4-bit merged
    )
    logger.info(f"Merged model saved to {output_dir / 'merged_4bit'}")
    
    # ── Evaluation ─────────────────────────────────────────────
    print()
    print("=" * 60)
    print("  Evaluating model...")
    print("=" * 60)
    
    eval_metrics = {}
    if eval_dataset is not None:
        # Quick eval on a few samples
        eval_samples = eval_dataset.select(range(min(10, len(eval_dataset))))
        eval_metrics = compute_metrics(model, tokenizer, eval_samples, device)
    
    # ── Generate Report ───────────────────────────────────────
    final_loss = trainer_stats.training_loss if hasattr(trainer_stats, 'training_loss') else 0
    
    report_lines = [
        f"# Phoenix Student Training Report",
        f"",
        f"Generated: {datetime.now().isoformat()}",
        f"Model: `{model_info['name']}`",
        f"",
        f"## Training Summary",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Base model | {model_info['name']} |",
        f"| Training time | {elapsed:.1f}s ({elapsed/60:.1f}min) |",
        f"| Total steps | {max_steps} |",
        f"| Epochs | {args.epochs} |",
        f"| Batch size | {args.batch_size} |",
        f"| Gradient accumulation | {args.grad_accum} |",
        f"| Learning rate | {args.lr} |",
        f"| LoRA rank | {args.lora_r} |",
        f"| LoRA alpha | {args.lora_alpha} |",
        f"| Max sequence length | {args.max_seq_length} |",
        f"| Training loss | {final_loss:.4f} |",
        f"| Train samples | {len(train_dataset)} |",
        f"| Eval samples | {len(eval_dataset) if eval_dataset else 0} |",
    ]
    
    if eval_metrics:
        report_lines.extend([
            f"",
            f"## Evaluation Results",
            f"",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Exact match accuracy | {eval_metrics.get('exact_match_accuracy', 0):.3f} |",
            f"| Eval pairs | {eval_metrics.get('total_eval_pairs', 0)} |",
        ])
    
    report_lines.extend([
        f"",
        f"## Output Files",
        f"",
        f"| File | Path |",
        f"|------|------|",
        f"| LoRA adapters | `{output_dir / 'lora'}` |",
        f"| Merged model (4-bit) | `{output_dir / 'merged_4bit'}` |",
        f"| Training checkpoints | `{output_dir}` |",
        f"",
        f"## Next Steps",
        f"",
        f"1. Test the model: `python Training/test_phoenix.py`",
        f"2. Proceed to Sprint 4: Expansion Head",
        f"   ```bash",
        f"   python Training/train_expansion_head.py",
        f"   ```",
        f"3. If results are promising, scale to Qwen2.5-7B:",
        f"   ```bash",
        f"   python Training/train_phoenix_student.py --model qwen2.5-7b --epochs 5",
        f"   ```",
    ])
    
    with open(eval_report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines) + "\n")
    
    print()
    print("=" * 60)
    print(f"  ✅ Training Complete!")
    print(f"  Time: {elapsed:.1f}s ({elapsed/60:.1f}min)")
    print(f"  Loss: {final_loss:.4f}")
    print(f"  Model: {output_dir / 'merged_4bit'}")
    print(f"  Report: {eval_report_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()