# Alexandria Evaluation Code

This section contains the evaluation workflow for Alexandria. The full pipeline can be run using the Quick Start script below.

The pipeline evaluates large language models on translation between Arabic dialects and English across 13 countries. It supports multiple task settings, metadata levels, and translation directions. Results are computed with spBLEU and CHRF++ and reported by country, task type, metadata level, direction, and domain.

Advanced usage with step by step scripts is described after the Quick Start section.

---

## 📑 Table of Contents

1. [Quick Start](#-quick-start)
2. [Step-by-step Usage](#-step-by-step-usage)
   - [Step 1 — Generate Prompts](#step-1--generate-prompts)
   - [Step 2 — Generate Requests](#step-2--generate-requests)
   - [Step 3 — Run Inference](#step-3--run-inference)
   - [Step 4 — Parse Responses](#step-4--parse-responses)
   - [Step 5 — Evaluate](#step-5--evaluate)
3. [Understanding the Outputs](#-understanding-the-outputs)
4. [End-to-end Examples](#-end-to-end-examples)
5. [Prompt ID Encoding](#-prompt-id-encoding)
6. [Project Structure](#-project-structure)

---

## 🚀 Quick Start

**Prerequisites:**
- Install dependencies: `pip install -r requirements.txt`
- Accept the dataset terms at [huggingface.co/datasets/UBC-NLP/alexandria](https://huggingface.co/datasets/UBC-NLP/alexandria) and log in with `huggingface-cli login`.

### Usage

```bash
bash scripts/run.sh -m MODEL -c COUNTRY [COUNTRY ...]
```

`MODEL` is a HuggingFace model name (e.g. `Qwen/Qwen2.5-3B-Instruct`) or a local model path (e.g. `/models/Qwen2.5-3B-Instruct`).

### Examples

```bash
# Evaluate on Morocco
bash scripts/run.sh -m Qwen/Qwen2.5-3B-Instruct -c MA

# Multiple countries
bash scripts/run.sh -m Qwen/Qwen2.5-3B-Instruct -c MA EG PS

# Multi-GPU with all tasks and metadata levels
bash scripts/run.sh -m Qwen/Qwen2.5-3B-Instruct -c MA \
    -t 4 -l 8192 --tasks all --meta-level all

# Custom output directory
bash scripts/run.sh -m Qwen/Qwen2.5-3B-Instruct -c MA PS \
    -o outputs/my_run

# All countries
bash scripts/run.sh -m Qwen/Qwen2.5-3B-Instruct \
    -c JO LB PS SY SA OM YE EG SD LY MA MR TN
```

### Parameters

| Flag | Required | Default | Description |
|---|---|---|---|
| `-m / --model-path` | Yes | — | HuggingFace model name or local path |
| `-c / --country` | Yes | — | One or more country codes (see below) |
| `-o / --output-dir` | No | `outputs/run_<timestamp>` | Output directory |
| `-t / --tensor-parallel-size` | No | `1` | Number of GPUs for tensor parallelism |
| `-l / --max-model-len` | No | `8192` | Maximum sequence length for vLLM |
| `--tasks` | No | `conversation` | Task type(s): `conversation`, `turn`, `context`, `all` |
| `--meta-level` | No | `full` | Metadata level(s): `full`, `partial`, `none`, `all` |
| `--direction` | No | `both` | Translation direction: `to_en`, `to_ar`, `both` |
| `--save-stats` | No | — | Save parsing statistics |

### Country codes

| Code | Country | Code | Country | Code | Country |
|---|---|---|---|---|---|
| `JO` | Jordan | `SA` | Saudi Arabia | `MA` | Morocco |
| `LB` | Lebanon | `OM` | Oman | `MR` | Mauritania |
| `PS` | Palestine | `YE` | Yemen | `TN` | Tunisia |
| `SY` | Syria | `EG` | Egypt | `SD` | Sudan |
| | | | | `LY` | Libya |

### Task types

The three task types provide different levels of conversational context to the model:

**`conversation`** — The model receives the entire conversation in a single prompt and must translate every turn at once, returning all translations together in one response.

**`turn`** — Each turn is sent as a standalone prompt with no information about the rest of the conversation. The model translates one sentence in isolation, with no knowledge of what came before or after the current turn.

**`context`** — Each turn is sent individually, but the preceding turns are included in the prompt as context. The model only needs to translate the current turn, but can use the prior conversation to inform its translation. The following turns are not included, so the model cannot see future context.

**`all`** — Include for all three task types.

### Metadata levels

The three metadata levels control how much information about the conversation is provided to the model:

**`full`** — The prompt includes everything known about the conversation: the country of origin, the domain/topic, the participant role, and the gender direction for each turn (e.g., "male to male"). The model has the richest possible metadata to adapt its translation.

**`partial`** — Only the gender direction is included for each turn. No country, domain, participant, or speaker information is given. This isolates the effect of gender-aware translation from other metadata.

**`none`** — The prompt contains only the raw text. No metadata of any kind.

**`all`** — Include for all three metadata levels.

### Translation direction

**`to_en`** — Arabic dialect → English only.

**`to_ar`** — English → Arabic dialect only.

**`both`** — Both directions (default).

### Metrics

| Metric | Description |
|---|---|
| **spBLEU** | BLEU using FLORES-200 sentencepiece tokenization |
| **CHRF++** | Character n-gram F-score with word-order penalty (word_order=2) |

### Output structure

When no `-o` is given, the output directory defaults to `outputs/run_<timestamp>`.

```
outputs/run_20260311_120000/
├── results.json                           ← aggregated metrics (all countries, all models)
├── logs/
│   ├── generate_prompts.log
│   ├── generate_requests.log
│   ├── parse_responses.log
│   └── evaluate.log
├── MA/
│   ├── prompts.jsonl                      ← generated prompts
│   ├── requests/
│   │   └── vllm_Qwen2.5-3B-Instruct_requests.jsonl
│   ├── responses/
│   │   └── Qwen2.5-3B-Instruct.jsonl
│   ├── parsed/
│   │   └── Qwen2.5-3B-Instruct_parsed.jsonl
│   └── evaluate/
│       └── Qwen2.5-3B-Instruct/
│           ├── outputs.jsonl              ← per-sample scores
│           ├── conversation_metrics.json
│           ├── turn_metrics.json
│           └── context_metrics.json
├── PS/
│   └── ...
```

**`results.json`** contains the summary metrics per country and model:

```json
{
    "MA": {
        "Qwen2.5-3B-Instruct": {
            "conversation": {
                "model": "Qwen2.5-3B-Instruct",
                "full": {
                    "to_ar": { "spBLEU": 9.03, "CHRF++": 17.83, "num_samples": 455 },
                    "to_en": { "spBLEU": 12.5, "CHRF++": 35.2, "num_samples": 455 }
                }
            }
        }
    }
}
```

---

## 🔧 Step-by-step Usage

### Step 1 — Generate Prompts

**Script:** `src/generate_prompts.py`

Downloads the dataset from HuggingFace for each country and generates prompt files. The script produces prompts for all requested task types, metadata levels, and translation directions.

```bash
python src/generate_prompts.py -c COUNTRY [COUNTRY ...] [OPTIONS]
```

| Flag | Required | Default | Description |
|---|---|---|---|
| `-c / --country` | Yes | — | Country code(s) |
| `-o / --output-dir` | No | `outputs/run_<timestamp>` | Output directory |
| `--split` | No | `test` | HuggingFace dataset split |
| `-t / --tasks` | No | `conversation` | Task type(s): `conversation`, `turn`, `context`, `all` |
| `-m / --meta-level` | No | `full` | Metadata level(s): `full`, `partial`, `none`, `all` |
| `-d / --direction` | No | `both` | Translation direction: `to_en`, `to_ar`, `both` |

```bash
# All tasks, all metadata levels, Morocco and Palestine
python src/generate_prompts.py -c MA PS -t all -m all

# Only turn-level prompts with partial metadata
python src/generate_prompts.py -c MA -t turn -m partial -o outputs/my_run

# Multiple task types, specific metadata levels
python src/generate_prompts.py -c MA -t conversation turn -m partial none -o outputs/my_run

# Arabic to English only, all tasks
python src/generate_prompts.py -c MA -t all -d to_en -o outputs/my_run
```

**Output:** `<output_dir>/<country>/prompts.jsonl` for each country.

---

### Step 2 — Generate Requests

**Script:** `src/generate_requests.py`

Reads the prompts from Step 1 and generates a batch request file formatted for the specified provider (vLLM or Gemini).

```bash
python src/generate_requests.py -p PROVIDER -o OUTPUT_DIR [OPTIONS]
```

| Flag | Required | Default | Description |
|---|---|---|---|
| `-p / --provider` | Yes | — | `vllm` or `gemini` |
| `-o / --output-dir` | Yes | — | Output directory (from Step 1) |
| `-m / --model-path` | For vLLM | — | HuggingFace model name or local path |
| `-n / --model-name` | For Gemini | — | Gemini model name |
| `--thinking-level` | For Gemini-3 | — | `minimal`, `low`, `medium`, `high` |
| `--thinking-budget` | For Gemini-2.5 | — | Token budget for thinking |

The request file is written to `<country>/requests/` and named after the provider and model:

| Provider | Output filename |
|---|---|
| vLLM | `vllm_<model_name>_requests.jsonl` |
| Gemini | `gemini_<model_name>_<thinking_level_or_budget>_requests.jsonl` |

#### Provider: vLLM

```bash
python src/generate_requests.py -p vllm -o outputs/my_run \
    -m Qwen/Qwen2.5-3B-Instruct
```

#### Provider: Gemini

Gemini has two request formats depending on the model generation.

**Gemini-3 models** use `--thinking-level`:

```bash
python src/generate_requests.py -p gemini -o outputs/my_run \
    -n gemini-3-pro --thinking-level low
```

Valid `--thinking-level` values: `minimal`, `low`, `medium`, `high`. Gemini-3 **Pro** only supports `low` and `high`.

**Gemini-2.5 models** use `--thinking-budget`:

```bash
python src/generate_requests.py -p gemini -o outputs/my_run \
    -n gemini-2.5-flash --thinking-budget 0
```

`--thinking-budget 0` disables thinking for Flash models. For `gemini-2.5-pro`, thinking cannot be disabled so `--thinking-budget` must be > 0.

---

### Step 3 — Run Inference

#### vLLM (local models)

**Script:** `scripts/vllm.sh`

Runs vLLM batch inference on the request files matching the given model.

```bash
bash scripts/vllm.sh -m MODEL_PATH -o OUTPUT_DIR [-t TENSOR_PARALLEL_SIZE] [-l MAX_MODEL_LEN]
```

```bash
bash scripts/vllm.sh -m Qwen/Qwen2.5-3B-Instruct -o outputs/my_run
bash scripts/vllm.sh -m Qwen/Qwen2.5-3B-Instruct -o outputs/my_run -t 4 -l 16384
```

**Output:** `<country>/responses/<model_name>.jsonl`

#### Gemini

Submit the request files from Step 2 to the Gemini Batch API. Place the response files at `<country>/responses/<model_name>.jsonl`.

---

### Step 4 — Parse Responses

**Script:** `src/parse_responses.py`

Parses raw model outputs, extracts translated sentences, and aligns them with the original prompts and reference translations.

```bash
python src/parse_responses.py -p PROVIDER -o OUTPUT_DIR [-s]
```

| Flag | Required | Default | Description |
|---|---|---|---|
| `-p / --provider` | No | `vllm` | `vllm` or `gemini` |
| `-o / --output-dir` | Yes | — | Output directory |
| `-s / --save-stats` | No | — | Save parsing statistics |

```bash
python src/parse_responses.py -p vllm -o outputs/my_run --save-stats
```

**Output:** `<country>/parsed/<model_name>_parsed.jsonl`

#### Parse statistics

When `--save-stats` is used, a JSON file is written to `<country>/parse_stats/<model_name>_parse_stats.json`:

```json
{
    "total_responses": 15468,
    "failed_responses": 42,
    "n_errors": 10,
    "n_warnings": 32,
    "failed_items": [
        {
            "custom_id": "turn_B0-0-0-105_MA_en_3",
            "error": {"code": "max_tokens", "message": "..."},
            "warning": null,
            "response": "",
            "raw_response": "..."
        }
    ]
}
```

**Errors** are hard failures (API errors, max tokens exceeded, or output that could not be parsed at all). **Warnings** apply only to the `conversation` task: a warning is raised when the number of turns extracted from the response does not match the expected number of turns in the conversation.

---

### Step 5 — Evaluate

**Script:** `src/evaluate.py`

Computes spBLEU and CHRF++ against reference translations. Writes one metrics file per task type (conversation, turn, context) with results broken down by metadata level, translation direction, and domain. Also writes an aggregated `results.json` at the top level.

```bash
python src/evaluate.py -o OUTPUT_DIR
```

```bash
python src/evaluate.py -o outputs/my_run
```

**Output:**
- `<country>/evaluate/<model_name>/outputs.jsonl` — per-sample scores
- `<country>/evaluate/<model_name>/<task>_metrics.json` — corpus-level metrics with domain breakdowns
- `<output_dir>/results.json` — aggregated summary across all countries and models

---

## 📊 Understanding the Outputs

The per-task metric files (e.g. `conversation_metrics.json`) contain detailed per-domain breakdowns:

```json
{
    "model": "Qwen2.5-3B-Instruct",
    "full": {
        "to_ar": {
            "all": {
                "spBLEU": 18.42,
                "CHRF++": 41.7,
                "num_samples": 2504
            },
            "domains": {
                "Everyday And Social": {
                    "spBLEU": 20.1,
                    "CHRF++": 43.2,
                    "num_samples": 412
                },
                "Agriculture And Farming": { "..." }
            }
        },
        "to_en": {
            "all": {
                "spBLEU": 24.8,
                "CHRF++": 52.3,
                "num_samples": 2504
            },
            "domains": { "..." }
        }
    },
    "partial": { "..." },
    "none": { "..." }
}
```

---

## 📋 End-to-end Examples

### With vLLM (local model)

```bash
# 1. Generate prompts — all tasks, all metadata levels
python src/generate_prompts.py \
    -c MA \
    -t all \
    -m all \
    -o outputs/my_run

# 2. Create vLLM batch request file
python src/generate_requests.py \
    -p vllm \
    -o outputs/my_run \
    -m Qwen/Qwen2.5-3B-Instruct

# 3. Run inference
bash scripts/vllm.sh \
    -m Qwen/Qwen2.5-3B-Instruct \
    -o outputs/my_run

# 4. Parse responses (with statistics)
python src/parse_responses.py \
    -p vllm \
    -o outputs/my_run \
    --save-stats

# 5. Evaluate
python src/evaluate.py -o outputs/my_run
```

### With Gemini

```bash
# 1. Generate prompts
python src/generate_prompts.py \
    -c MA \
    -t all \
    -m all \
    -o outputs/my_run

# 2. Create Gemini batch request file (Gemini-3 Pro, low thinking)
python src/generate_requests.py \
    -p gemini \
    -o outputs/my_run \
    -n gemini-3-pro-preview \
    --thinking-level low

# 3. Submit to Google Gemini Batch API (provider-specific step)
#    Upload the request files and retrieve the responses JSONL.
#    Place the output at: <country>/responses/gemini-3-pro-preview_low.jsonl

# 4. Parse responses
python src/parse_responses.py \
    -p gemini \
    -o outputs/my_run \
    --save-stats

# 5. Evaluate
python src/evaluate.py -o outputs/my_run
```

---

## 🏷️ Prompt ID Encoding

Every prompt has a structured ID that encodes its properties:

```
conv_{conv_id}_{country}{meta_suffix}_{direction}
turn_{conv_id}_{country}{meta_suffix}_{direction}_{turn_index}
cont_{conv_id}_{country}{meta_suffix}_{direction}_{turn_index}
```

Where:
- `meta_suffix`: empty = `full`, `_p` = `partial`, `_n` = `none`
- `direction`: `en` = to English, `ar` = to Arabic dialect

---

## 📁 Project Structure

```
alexandria/
├── readme.md
├── src/
│   ├── generate_prompts.py       Step 1: HF dataset → prompts
│   ├── generate_requests.py      Step 2: prompts → provider batch requests
│   ├── parse_responses.py        Step 4: raw responses → parsed translations
│   ├── evaluate.py               Step 5: parsed translations → metrics
│   └── utils/
│       ├── common.py             Shared utilities (logging, I/O, country codes)
│       ├── prompts.py            Prompt template construction
│       └── parsers.py            LLM output parsing
└── scripts/
    ├── run.sh                    Full pipeline (quick start)
    └── vllm.sh                   vLLM batch inference
```
