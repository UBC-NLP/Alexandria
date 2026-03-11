#!/bin/bash
# Alexandria Benchmark Harness
# Runs the full pipeline: generate_prompts → generate_requests → vllm inference → parse_responses → evaluate
#
# Usage:
#   bash scripts/run.sh -m MODEL_PATH -c COUNTRY [COUNTRY ...] [OPTIONS]
#
# Required:
#   -m, --model-path            Local model or hugging face model path for vLLM
#   -c, --country               Country code(s): JO LB PS SY SA OM YE EG SD LY MA MR TN
#
# Optional:
#   -o, --output-dir            Output directory (default: outputs/run_<timestamp>)
#   -t, --tensor-parallel-size  vLLM tensor parallel size (default: 1)
#   -l, --max-model-len         vLLM max model length (default: 8192)
#   --tasks                     Task type(s): conversation turn context all (default: conversation)
#   --meta-level                Metadata level(s): full none partial all (default: full)
#   --direction                 Translation direction: to_ar to_en both (default: both)
#   --save-stats                Save parsing statistics
#
# Examples:
#   bash scripts/run.sh -m Qwen/Qwen2.5-3B-Instruct -c MA PS
#   bash scripts/run.sh -m Qwen/Qwen2.5-3B-Instruct -c MA -o outputs/my_run --tasks all --meta-level all
#   bash scripts/run.sh -m Qwen/Qwen2.5-3B-Instruct -c MA PS EG -t 4 -l 8024

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_DIR="$(dirname "$SCRIPT_DIR")/src"

MODEL_PATH=""
COUNTRIES=""
OUTPUT_DIR=""
TENSOR_PARALLEL_SIZE=1
MAX_MODEL_LEN=8192
TASKS="conversation"
META_LEVEL="full"
DIRECTION="both"
SAVE_STATS=""

while [[ "$#" -gt 0 ]]; do
    case $1 in
        -m|--model-path)            MODEL_PATH="$2";           shift ;;
        -c|--country)
            shift
            while [[ "$#" -gt 0 && ! "$1" =~ ^- ]]; do
                COUNTRIES="$COUNTRIES $1"
                shift
            done
            continue
            ;;
        -o|--output-dir)            OUTPUT_DIR="$2";           shift ;;
        -t|--tensor-parallel-size)  TENSOR_PARALLEL_SIZE="$2"; shift ;;
        -l|--max-model-len)         MAX_MODEL_LEN="$2";        shift ;;
        --tasks)
            shift
            TASKS=""
            while [[ "$#" -gt 0 && ! "$1" =~ ^- ]]; do
                TASKS="$TASKS $1"
                shift
            done
            TASKS=$(echo "$TASKS" | xargs)
            continue
            ;;
        --meta-level)
            shift
            META_LEVEL=""
            while [[ "$#" -gt 0 && ! "$1" =~ ^- ]]; do
                META_LEVEL="$META_LEVEL $1"
                shift
            done
            META_LEVEL=$(echo "$META_LEVEL" | xargs)
            continue
            ;;
        --direction)                DIRECTION="$2";            shift ;;
        --save-stats)               SAVE_STATS="--save-stats"        ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
    shift
done

COUNTRIES=$(echo "$COUNTRIES" | xargs)

if [[ -z "$MODEL_PATH" || -z "$COUNTRIES" ]]; then
    echo "Usage: bash scripts/run.sh -m MODEL_PATH -c COUNTRY [COUNTRY ...] [OPTIONS]"
    echo "Run 'bash scripts/run.sh --help' for more details."
    exit 1
fi

if [[ -z "$OUTPUT_DIR" ]]; then
    OUTPUT_DIR="outputs/run_$(date +%Y%m%d_%H%M%S)"
fi

echo "============================================"
echo "Alexandria Benchmark"
echo "============================================"
echo "Model:       $MODEL_PATH"
echo "Countries:   $COUNTRIES"
echo "Output:      $OUTPUT_DIR"
echo "Tasks:       $TASKS"
echo "Meta level:  $META_LEVEL"
echo "Direction:   $DIRECTION"
echo "Started at:  $(date +%T)"
echo "============================================"

# Step 1: Generate prompts
echo ""
echo "[Step 1/5] Generating prompts..."
python3 "$SRC_DIR/generate_prompts.py" \
    -c $COUNTRIES \
    -o "$OUTPUT_DIR" \
    -t $TASKS \
    -m $META_LEVEL \
    -d "$DIRECTION"

# Step 2: Generate requests
echo ""
echo "[Step 2/5] Generating requests..."
python3 "$SRC_DIR/generate_requests.py" \
    -p vllm \
    -o "$OUTPUT_DIR" \
    -m "$MODEL_PATH"

# Step 3: vLLM inference
echo ""
echo "[Step 3/5] Running vLLM inference..."
bash "$SCRIPT_DIR/vllm.sh" \
    -m "$MODEL_PATH" \
    -o "$OUTPUT_DIR" \
    -t "$TENSOR_PARALLEL_SIZE" \
    -l "$MAX_MODEL_LEN"

# Step 4: Parse responses
echo ""
echo "[Step 4/5] Parsing responses..."
python3 "$SRC_DIR/parse_responses.py" \
    -p vllm \
    -o "$OUTPUT_DIR" \
    $SAVE_STATS

# Step 5: Evaluate
echo ""
echo "[Step 5/5] Evaluating..."
python3 "$SRC_DIR/evaluate.py" \
    -o "$OUTPUT_DIR"

echo ""
echo "============================================"
echo "Done!"
echo "Results:     $OUTPUT_DIR/results.json"
echo "Finished at: $(date +%T)"
echo "============================================"
