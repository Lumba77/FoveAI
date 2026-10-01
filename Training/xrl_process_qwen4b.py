import os
import json
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

# CONFIG — point this to your downloaded model folder
LOCAL_MODEL_PATH = r"C:\Users\danie\program\LUMAX\Training\models--Qwen--Qwen3.5-4B-Base_"

WORK_DIR = os.path.abspath(".")
XRL_DIR = os.path.join(WORK_DIR, "xrl_encoded")

os.makedirs(XRL_DIR, exist_ok=True)

PROBE_PROMPTS = [
    "Explain semantic compression.",
    "Write a Python function that adds two numbers.",
    "Describe pruning vs quantization.",
    "Summarize the concept of attention in transformers.",
]


def load_local_model():
    print(f"=== SAFE LOCAL LOAD: {LOCAL_MODEL_PATH} ===")

    # Force HF to ignore cache and hub registry
    tokenizer = AutoTokenizer.from_pretrained(
        LOCAL_MODEL_PATH,
        local_files_only=True,
        trust_remote_code=True
    )

    model = AutoModelForCausalLM.from_pretrained(
        LOCAL_MODEL_PATH,
        torch_dtype=torch.float16,
        device_map="auto",
        local_files_only=True,
        trust_remote_code=True
    )

    print("=== Local model loaded safely ===\n")
    return tokenizer, model



# -----------------------------------------------------------
# LAYER 1 — QUANTIZATION (real 4-bit via bitsandbytes)
# -----------------------------------------------------------
def quantize_model(model_path):
    print("=== Real 4-bit quantization (bitsandbytes) ===")

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
    )

    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        quantization_config=bnb_config,
        device_map="auto"
    )

    meta = {
        "quantized": True,
        "method": "bitsandbytes_nf4",
        "double_quant": True,
        "dtype": "float16_compute",
    }

    print("=== Quantization complete: model is now in true 4-bit ===\n")
    return model, meta


# -----------------------------------------------------------
# LAYER 2 — Activation probing for pruning
# -----------------------------------------------------------
def probe_activations(tokenizer, model):
    print("=== Probing activations for pruning ===")
    model.eval()

    head_scores = {}
    neuron_scores = {}

    for prompt in PROBE_PROMPTS:
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        with torch.no_grad():
            outputs = model(**inputs, output_attentions=True, output_hidden_states=True)

        attns = outputs.attentions
        for layer_idx, layer_attn in enumerate(attns):
            head_mean = layer_attn.mean(dim=(0, 2, 3))
            for head_idx, score in enumerate(head_mean):
                key = (layer_idx, head_idx)
                head_scores.setdefault(key, 0.0)
                head_scores[key] += score.item()

        hiddens = outputs.hidden_states
        for layer_idx, layer_hidden in enumerate(hiddens):
            neuron_mean = layer_hidden.mean(dim=(0, 1))
            for neuron_idx, score in enumerate(neuron_mean):
                key = (layer_idx, neuron_idx)
                neuron_scores.setdefault(key, 0.0)
                neuron_scores[key] += abs(score.item())

    print("=== Activation probing complete ===\n")
    return head_scores, neuron_scores


# -----------------------------------------------------------
# LAYER 3 — Real pruning + routing
# -----------------------------------------------------------
def prune_and_route_model(model, head_scores, neuron_scores, head_keep_ratio=0.5, neuron_keep_ratio=0.7):
    print("=== Real pruning and routing ===")

    head_items = list(head_scores.items())
    neuron_items = list(neuron_scores.items())

    head_items.sort(key=lambda x: x[1], reverse=True)
    neuron_items.sort(key=lambda x: x[1], reverse=True)

    num_heads_keep = int(len(head_items) * head_keep_ratio)
    num_neurons_keep = int(len(neuron_items) * neuron_keep_ratio)

    kept_heads = set(key for key, _ in head_items[:num_heads_keep])
    kept_neurons = set(key for key, _ in neuron_items[:num_neurons_keep])

    routing_map = {
        "kept_heads": [{"layer": k[0], "head": k[1]} for k in kept_heads],
        "kept_neurons": [{"layer": k[0], "neuron": k[1]} for k in kept_neurons],
    }

    for name, module in model.named_modules():
        if isinstance(module, torch.nn.Linear):
            layer_idx = None
            parts = name.split(".")
            for p in parts:
                if p.isdigit():
                    layer_idx = int(p)
                    break
            if layer_idx is None:
                continue

            out_features = module.out_features
            mask = torch.ones(out_features, dtype=torch.bool, device=module.weight.device)
            for neuron_idx in range(out_features):
                key = (layer_idx, neuron_idx)
                if key not in kept_neurons:
                    mask[neuron_idx] = False

            with torch.no_grad():
                module.weight[~mask, :] = 0
                if module.bias is not None:
                    module.bias[~mask] = 0

    meta = {
        "pruned": True,
        "head_keep_ratio": head_keep_ratio,
        "neuron_keep_ratio": neuron_keep_ratio,
        "routing_map": routing_map,
    }

    print("=== Pruning and routing complete ===\n")
    return model, meta


# -----------------------------------------------------------
# LAYER 4 — XRL threading
# -----------------------------------------------------------
def xrl_trace_threads(tokenizer, model):
    print("=== XRL threading: tracing semantic paths ===")

    prompts = [
        "Explain semantic compression.",
        "Write a Python function that adds two numbers.",
        "Describe pruning vs quantization."
    ]

    threads = []
    model.eval()

    for prompt in prompts:
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        with torch.no_grad():
            outputs = model(**inputs, output_attentions=True)

        attns = outputs.attentions
        layer_summaries = []

        for layer_idx, layer_attn in enumerate(attns):
            avg_attn = layer_attn.mean().item()
            layer_summaries.append({
                "layer": layer_idx,
                "avg_attention": avg_attn
            })

        threads.append({
            "prompt": prompt,
            "layers": layer_summaries
        })

    threads_path = os.path.join(XRL_DIR, "threads.json")
    with open(threads_path, "w", encoding="utf-8") as f:
        json.dump(threads, f, indent=2)

    print(f"=== XRL threads saved to {threads_path} ===\n")
    return threads


# -----------------------------------------------------------
# LAYER 5 — XRL principiation
# -----------------------------------------------------------
def xrl_principiate(threads):
    print("=== XRL principiation: deriving layer principles ===")

    layer_principles = {}

    for thread in threads:
        for layer in thread["layers"]:
            idx = layer["layer"]
            val = layer["avg_attention"]
            if idx not in layer_principles:
                layer_principles[idx] = {"sum": 0.0, "count": 0}
            layer_principles[idx]["sum"] += val
            layer_principles[idx]["count"] += 1

    principles = []
    for idx, stats in layer_principles.items():
        avg = stats["sum"] / stats["count"]
        principles.append({
            "layer": idx,
            "principle_strength": avg,
            "role": "semantic_transform"
        })

    principles_path = os.path.join(XRL_DIR, "principles.json")
    with open(principles_path, "w", encoding="utf-8") as f:
        json.dump(principles, f, indent=2)

    print(f"=== XRL principles saved to {principles_path} ===\n")
    return principles


# -----------------------------------------------------------
# MAIN PIPELINE
# -----------------------------------------------------------
def main():
    tokenizer, _ = load_local_model()

    model, quant_meta = quantize_model(LOCAL_MODEL_PATH)

    head_scores, neuron_scores = probe_activations(tokenizer, model)

    model, prune_meta = prune_and_route_model(model, head_scores, neuron_scores)

    threads = xrl_trace_threads(tokenizer, model)
    principles = xrl_principiate(threads)

    meta = {
        "model_path": LOCAL_MODEL_PATH,
        "quantization": quant_meta,
        "pruning": prune_meta,
        "threads_file": "threads.json",
        "principles_file": "principles.json"
    }

    meta_path = os.path.join(XRL_DIR, "meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    print(f"=== XRL meta saved to {meta_path} ===")
    print("=== XRL processing complete ===")


if __name__ == "__main__":
    main()
