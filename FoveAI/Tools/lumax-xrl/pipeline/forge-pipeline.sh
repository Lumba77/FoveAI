#!/bin/bash
# =============================================================================
# 70XRL Forge Pipeline — One-Command Model Optimization
# =============================================================================
# Converts any HuggingFace model into a super-optimized 70XRL model:
#   safetensors → GGUF FP16 → MoQ quantization → XRL fine-tuning → deploy
#
# Usage:
#   bash forge-pipeline.sh --model Qwen/Qwen2.5-Coder-7B
#   bash forge-pipeline.sh --model Qwen/Qwen2.5-Coder-7B --quant moq-2.0 --xrl-train
#   bash forge-pipeline.sh --model ./models/my-custom-model --local --quant moq-3.0
#
# Options:
#   --model <id|path>   HuggingFace model ID or local path
#   --output <dir>      Output directory (default: ./models/70xrl-{model-name})
#   --quant <type>      Quantization type (default: moq-2.0)
#                       Options: moq-2.0, moq-3.0, moq-3.5, moq-4.0, q4_k_m, q5_k_m, q8_0
#   --xrl-train         Also fine-tune with XRL dataset after quantization
#   --xrl-depth <0-3>   XRL skeleton depth for training (default: 2)
#   --dataset <path>    Local code dataset for XRL fine-tuning
#   --hf-dataset <id>   HuggingFace dataset for XRL fine-tuning
#   --local             Run on local machine (slower, no GPU rental)
#   --server            Rent cloud GPU (RunPod) for faster processing
#   --dry-run           Show what would be done without executing
#   --verbose           Show detailed output
#
# Examples:
#   # Quick: download + quantize a 7B model locally
#   bash forge-pipeline.sh --model Qwen/Qwen2.5-Coder-7B --quant moq-2.0 --local
#
#   # Full: download + quantize + XRL-train a 12B model
#   bash forge-pipeline.sh --model google/gemma-4-12B-it --quant moq-2.0 --xrl-train --hf-dataset bigcode/the-stack
#
#   # Server: rent H100 for 70B model over weekend
#   bash forge-pipeline.sh --model deepseek-ai/DeepSeek-Coder-70B --quant moq-2.0 --server
# =============================================================================

set -euo pipefail

# ─── Colors ─────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ─── Defaults ───────────────────────────────────────────────────────
MODEL=""
OUTPUT=""
QUANT_TYPE="moq-2.0"
XRL_TRAIN=false
XRL_DEPTH=2
DATASET=""
HF_DATASET=""
LOCAL=false
SERVER=false
DRY_RUN=false
VERBOSE=false

LUMAX_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FORGE_NURSERY="$LUMAX_ROOT/Forge/nursery"
XRL_DIR="$LUMAX_ROOT/Forge/xrs"
PIPELINE_DIR="$LUMAX_ROOT/Forge/pipeline"
MODELS_DIR="$LUMAX_ROOT/models"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# ─── Parse Arguments ───────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --model)       MODEL="$2"; shift 2 ;;
        --output)      OUTPUT="$2"; shift 2 ;;
        --quant)       QUANT_TYPE="$2"; shift 2 ;;
        --xrl-train)   XRL_TRAIN=true; shift ;;
        --xrl-depth)   XRL_DEPTH="$2"; shift 2 ;;
        --dataset)     DATASET="$2"; shift 2 ;;
        --hf-dataset)  HF_DATASET="$2"; shift 2 ;;
        --local)       LOCAL=true; shift ;;
        --server)      SERVER=true; shift ;;
        --dry-run)     DRY_RUN=true; shift ;;
        --verbose)     VERBOSE=true; shift ;;
        -h|--help)     head -50 "$0"; exit 0 ;;
        *) echo -e "${RED}Unknown option: $1${NC}"; exit 1 ;;
    esac
done

# ─── Validation ────────────────────────────────────────────────────
if [[ -z "$MODEL" ]]; then
    echo -e "${RED}Error: --model is required${NC}"
    echo "Usage: bash forge-pipeline.sh --model <model-id> [options]"
    exit 1
fi

# Determine model name
MODEL_NAME=$(basename "$MODEL")
if [[ -z "$OUTPUT" ]]; then
    OUTPUT="$MODELS_DIR/70xrl-$MODEL_NAME-$TIMESTAMP"
fi

# ─── Banner ─────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║           70XRL FORGE PIPELINE                          ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}Model:${NC}        $MODEL"
echo -e "${BLUE}Output:${NC}       $OUTPUT"
echo -e "${BLUE}Quantization:${NC} $QUANT_TYPE"
echo -e "${BLUE}XRL Train:${NC}    $XRL_TRAIN (depth $XRL_DEPTH)"
echo -e "${BLUE}Mode:${NC}         $([ "$LOCAL" = true ] && echo "Local" || echo "Server")"
echo ""

if [[ "$DRY_RUN" = true ]]; then
    echo -e "${YELLOW}🔍 DRY RUN — no commands will be executed${NC}"
fi

# ─── Helper Functions ───────────────────────────────────────────────
run() {
    if [[ "$DRY_RUN" = true ]]; then
        echo -e "${YELLOW}  [DRY-RUN] $ ${NC}$*"
    else
        if [[ "$VERBOSE" = true ]]; then
            echo -e "${GREEN}  $ ${NC}$*"
            "$@"
        else
            echo -e "${GREEN}  → ${NC}$1"
            "$@" > /dev/null 2>&1
        fi
    fi
}

step() {
    echo ""
    echo -e "${CYAN}━━━ Step $1: $2 ━━━${NC}"
}

check_cmd() {
    if ! command -v "$1" &> /dev/null; then
        echo -e "${RED}Error: $1 is not installed${NC}"
        return 1
    fi
}

# ─── Step 1: Download Model ──────────────────────────────────────────
step 1 "Download Model from HuggingFace"

check_cmd python || exit 1
check_cmd node || exit 1

run python "$PIPELINE_DIR/download_model.py" \
    --model "$MODEL" \
    --output "$OUTPUT/base" \
    --convert \
    ${DRY_RUN:+--dry-run}

echo -e "${GREEN}  ✅ Model downloaded to: $OUTPUT/base${NC}"

# ─── Step 2: Convert to GGUF ───────────────────────────────────────
step 2 "Convert to GGUF FP16"

GGUF_FP16="$OUTPUT/$MODEL_NAME-fp16.gguf"

run python "$PIPELINE_DIR/download_model.py" \
    --model "$OUTPUT/base" \
    --output "$OUTPUT/base" \
    --convert \
    ${DRY_RUN:+--dry-run}

echo -e "${GREEN}  ✅ GGUF FP16: $GGUF_FP16${NC}"

# ─── Step 3: MoQ Quantization ──────────────────────────────────────
step 3 "Apply MoQ Quantization ($QUANT_TYPE)"

GGUF_QUANTIZED="$OUTPUT/$MODEL_NAME-$QUANT_TYPE.gguf"

# Use the Forge Nursery quantizer API
if [[ "$DRY_RUN" = false ]]; then
    python -c "
import sys
sys.path.insert(0, '$FORGE_NURSERY')
from quantizer import ForgeQuantizer, QUANT_TYPES

if '$QUANT_TYPE' not in QUANT_TYPES:
    print(f'Error: Unknown quant type: $QUANT_TYPE')
    print(f'Available: {list(QUANT_TYPES.keys())}')
    sys.exit(1)

quantizer = ForgeQuantizer()
job = quantizer.create_job(
    input_path='$GGUF_FP16',
    variant_id='$MODEL_NAME',
    quant_type='$QUANT_TYPE',
)
job.output_path = '$OUTPUT/quantized'
import os
os.makedirs(job.output_path, exist_ok=True)
success = quantizer.run_quantize(job)
if success:
    print(f'✅ Quantization complete')
else:
    print(f'❌ Quantization failed: {job.error}')
    sys.exit(1)
"
fi

echo -e "${GREEN}  ✅ Quantized model: $GGUF_QUANTIZED${NC}"

# ─── Step 4: XRL Fine-Tuning (Optional) ─────────────────────────────
if [[ "$XRL_TRAIN" = true ]]; then
    step 4 "XRL Fine-Tuning"

    # Prepare XRL dataset
    XRL_DATASET_DIR="$OUTPUT/xrl-dataset"
    if [[ -n "$DATASET" ]]; then
        echo -e "${BLUE}  Processing local dataset: $DATASET${NC}"
        run python "$PIPELINE_DIR/xrl_preprocessor.py" \
            --input "$DATASET" \
            --output "$XRL_DATASET_DIR" \
            --depth "$XRL_DEPTH" \
            --workers 4
    elif [[ -n "$HF_DATASET" ]]; then
        echo -e "${BLUE}  Processing HF dataset: $HF_DATASET${NC}"
        run python "$PIPELINE_DIR/xrl_preprocessor.py" \
            --hf-dataset "$HF_DATASET" \
            --output "$XRL_DATASET_DIR" \
            --depth "$XRL_DEPTH" \
            --max-samples 10000
    else
        # Use LUMAX's own codebase as training data
        echo -e "${BLUE}  Using LUMAX codebase as XRL training data${NC}"
        run python "$PIPELINE_DIR/xrl_preprocessor.py" \
            --input "$LUMAX_ROOT/Backend" \
            --output "$XRL_DATASET_DIR" \
            --depth "$XRL_DEPTH" \
            --max-samples 5000
    fi

    # Start fine-tuning via Forge Nursery API
    echo -e "${BLUE}  Starting XRL fine-tuning via Forge Nursery...${NC}"
    if [[ "$DRY_RUN" = false ]]; then
        curl -s -X POST "http://localhost:8105/api/train/start" \
            -H "Content-Type: application/json" \
            -d '{
                "variant_id": "70xrl-'"$MODEL_NAME"'",
                "base_model": "'"$GGUF_QUANTIZED"'",
                "dataset_path": "'"$XRL_DATASET_DIR"'",
                "xrl_depth": '"$XRL_DEPTH"',
                "epochs": 3,
                "learning_rate": 2e-4,
                "auto_quantize": true,
                "quant_type": "'"$QUANT_TYPE"'"
            }' | python -m json.tool
    fi

    echo -e "${GREEN}  ✅ XRL fine-tuning started${NC}"
fi

# ─── Step 5: Deploy ─────────────────────────────────────────────────
step 5 "Deploy 70XRL Model"

FINAL_MODEL="$OUTPUT/$MODEL_NAME-$QUANT_TYPE-70xrl.gguf"

if [[ "$DRY_RUN" = false ]]; then
    # Copy the quantized model to final location
    if [[ -f "$GGUF_QUANTIZED" ]]; then
        cp "$GGUF_QUANTIZED" "$FINAL_MODEL"
        echo -e "${GREEN}  ✅ Model deployed: $FINAL_MODEL${NC}"
    else
        echo -e "${YELLOW}  ⚠️ Quantized model not found, checking output directory...${NC}"
        find "$OUTPUT" -name "*.gguf" -type f 2>/dev/null | head -5
    fi
fi

# ─── Summary ────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║          70XRL PIPELINE COMPLETE                         ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}Model:${NC}        $MODEL"
echo -e "${GREEN}Output:${NC}       $OUTPUT"
echo -e "${GREEN}Quantization:${NC} $QUANT_TYPE"
echo -e "${GREEN}XRL Trained:${NC}  $XRL_TRAIN"
echo ""
echo -e "${BLUE}To use this model with LUMAX:${NC}"
echo "  1. Copy to models directory:"
echo "     cp $FINAL_MODEL $LUMAX_ROOT/models/"
echo ""
echo "  2. Update .env:"
echo "     LUMAX_LOCAL_MODEL_PATH=$FINAL_MODEL"
echo "     LUMAX_LOCAL_LLM_BASE=http://127.0.0.1:8888/v1"
echo ""
echo "  3. Start LUMAX and select '70XRL' as provider in Model Hub"
echo ""
echo -e "${GREEN}🎉 70XRL model ready!${NC}"