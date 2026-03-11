#!/bin/bash
# Run vLLM batch inference for all countries in the output directory.
# Usage: bash scripts/vllm.sh -m MODEL_PATH -o OUTPUT_DIR [-t TENSOR_PARALLEL_SIZE] [-l MAX_MODEL_LEN]

set -Eeuo pipefail

VALID_COUNTRIES="JO LB PS SY SA OM YE EG SD LY MA MR TN"

MODEL_PATH=""
OUTPUT_DIR=""
TENSOR_PARALLEL_SIZE=1
MAX_MODEL_LEN=8192

while [[ "$#" -gt 0 ]]; do
    case $1 in
        -m|--model-path)            MODEL_PATH="$2";           shift ;;
        -o|--output-dir)            OUTPUT_DIR="$2";           shift ;;
        -t|--tensor-parallel-size)  TENSOR_PARALLEL_SIZE="$2"; shift ;;
        -l|--max-model-len)         MAX_MODEL_LEN="$2";        shift ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
    shift
done

if [[ -z "$MODEL_PATH" || -z "$OUTPUT_DIR" ]]; then
    echo "Usage: bash scripts/vllm.sh -m MODEL_PATH -o OUTPUT_DIR [-t TENSOR_PARALLEL_SIZE] [-l MAX_MODEL_LEN]"
    exit 1
fi

MODEL_NAME=$(basename "$MODEL_PATH")

export VLLM_CONFIGURE_LOGGING=0
export VLLM_LOGGING_LEVEL=ERROR

run_vllm() {
    local INPUT_FILE="$1"
    local OUTPUT_FILE="$2"
    local TMP_DIR="$3"

    mkdir -p "$(dirname "$OUTPUT_FILE")" "$TMP_DIR"

    python3 -m vllm.entrypoints.openai.run_batch \
        -i "$INPUT_FILE" \
        -o "$OUTPUT_FILE" \
        --output-tmp-dir "$TMP_DIR" \
        --model "$MODEL_PATH" \
        --tensor-parallel-size "$TENSOR_PARALLEL_SIZE" \
        --max-model-len "$MAX_MODEL_LEN" \
        --override-generation-config '{"max_tokens": 2048, "temperature": 0, "top_p": 1}'

    rm -rf "$TMP_DIR"
}

echo "Job started at:  $(date +%T)"
echo "Model path:      $MODEL_PATH"
echo "Output dir:      $OUTPUT_DIR"

# Discover country directories
FOUND=0
for COUNTRY_DIR in "$OUTPUT_DIR"/*/; do
    COUNTRY=$(basename "$COUNTRY_DIR")
    if ! echo "$VALID_COUNTRIES" | grep -qw "$COUNTRY"; then
        continue
    fi

    REQUEST_DIR="${COUNTRY_DIR}requests"
    if [[ ! -d "$REQUEST_DIR" ]]; then
        echo "No requests dir for $COUNTRY, skipping."
        continue
    fi

    REQUEST_FILE="${REQUEST_DIR}/vllm_${MODEL_NAME}_requests.jsonl"
    if [[ ! -f "$REQUEST_FILE" ]]; then
        echo "No request file for $COUNTRY / $MODEL_NAME, skipping."
        continue
    fi
    FOUND=1

    OUTPUT_FILE="${COUNTRY_DIR}responses/${MODEL_NAME}.jsonl"
    TMP_DIR="${COUNTRY_DIR}tmp"

    echo "[$COUNTRY] Input:  $REQUEST_FILE"
    echo "[$COUNTRY] Output: $OUTPUT_FILE"

    run_vllm "$REQUEST_FILE" "$OUTPUT_FILE" "$TMP_DIR"

    echo "[$COUNTRY] Done."
done

if [[ "$FOUND" -eq 0 ]]; then
    echo "No country directories with request files found in $OUTPUT_DIR."
    exit 1
fi

echo "VLLM Job ended at:    $(date +%T)"
