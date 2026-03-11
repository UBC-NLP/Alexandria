"""Generate batch requests for different LLM providers.

Provider options:
    gemini:
        -n/--model-name     (required) e.g. gemini-2.5-pro, gemini-3-pro
        --thinking-budget   (required for gemini-2.5) Token budget for thinking, int.
                            Cannot be 0 for Pro models.
        --thinking-level    (required for gemini-3) One of: minimal, low, medium, high.
                            Pro models only support: low, high.

    vllm:
        -m/--model-path     (required) Local model path

Usage examples:
    python generate_requests.py -p gemini  -g prompts.jsonl -n gemini-2.5-pro --thinking-budget 1024
    python generate_requests.py -p gemini  -g prompts.jsonl -n gemini-3-pro --thinking-level low
    python generate_requests.py -p vllm    -g prompts.jsonl -m /path/to/model
"""

import json
from pathlib import Path
import argparse
import logging
from utils.common import read_jsonl, discover_countries, setup_logging

logger = logging.getLogger(__name__)


def create_gemini_request(
        sample,
        model_name,
        thinking_budget=None,
        thinking_level=None):
    if 'gemini-3' in model_name:
        thinking_config = {
            "thinkingLevel": "low" if thinking_level is None else thinking_level
        }
    else:
        thinking_config = {
            "thinkingBudget": 1024 if thinking_budget is None else thinking_budget
        }

    return {
        "custom_id": sample['id'],
        "request": {
            "contents": [
                {"role": "USER", "parts": [{"text": sample['prompt']}]}
            ],
            "generation_config": {
                "temperature": 0,
                "thinking_config": thinking_config
            }
        }
    }


def create_vllm_request(sample, model_path):
    return {
        'custom_id': sample['id'],
        'method': 'POST',
        'url': '/v1/chat/completions',
        'body': {
            "model": model_path,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": sample['prompt']}
            ],
            "temperature": 0.0,
            "top_p": 1.0,
        }
    }


def run(provider, prompts_file, model_path=None, model_name=None,
        output_dir=None, thinking_budget=None, thinking_level=None):
    prompts_file = Path(prompts_file)
    if not output_dir:
        req_dir = prompts_file.parent / 'requests'
    else:
        req_dir = Path(output_dir) / 'requests'
    req_dir.mkdir(parents=True, exist_ok=True)

    if provider == 'vllm':
        name = Path(model_path).name
        output_file = req_dir / f"{provider}_{name}_requests.jsonl"
    elif provider == 'gemini':
        thinking_part = thinking_level if 'gemini-3' in model_name else thinking_budget
        output_file = req_dir / f"{provider}_{model_name}_{thinking_part}_requests.jsonl"

    data = read_jsonl(prompts_file)

    if provider == 'gemini':
        all_requests = [
            create_gemini_request(
                sample, model_name,
                thinking_budget=thinking_budget,
                thinking_level=thinking_level)
            for sample in data
        ]
    elif provider == 'vllm':
        all_requests = [
            create_vllm_request(sample, model_path)
            for sample in data
        ]

    logger.info(f"Writing {len(all_requests)} requests to {output_file}")
    with open(output_file, 'w', encoding='utf-8') as f:
        for item in all_requests:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')

    return output_file


def main():
    parser = argparse.ArgumentParser(
        description='Generate batch requests for different providers')
    parser.add_argument('-p', '--provider', type=str, required=True,
                        choices=['gemini', 'vllm'],
                        help='Provider: gemini or vllm')
    parser.add_argument('-o', '--output-dir', type=Path, required=True,
                        help='Output directory (with country subdirs)')
    parser.add_argument('-n', '--model-name', type=str,
                        help='Model name (required for gemini)')
    parser.add_argument('-m', '--model-path', type=str,
                        help='Model path (required for vllm)')

    # Gemini specific parameters
    parser.add_argument(
        '--thinking-budget',
        type=int,
        default=None,
        help='Thinking budget in tokens for Gemini models that support it')
    parser.add_argument(
        '--thinking-level',
        type=str,
        choices=['minimal', 'low', 'medium', 'high'],
        default=None,
        help='Thinking level for Gemini-3 models')

    args = parser.parse_args()

    setup_logging(args.output_dir, 'generate_requests')

    if args.provider == 'gemini' and not args.model_name:
        parser.error("--model-name is required for gemini")
    if args.provider == 'vllm' and not args.model_path:
        parser.error("--model-path is required for vllm")

    if args.provider == 'gemini':
        if 'gemini-3' in args.model_name:
            if args.thinking_budget is not None:
                logger.warning("Thinking budget is not applicable for Gemini-3 models. Ignoring --thinking-budget.")
            if args.thinking_level is None:
                parser.error("--thinking-level is required for Gemini-3 models")
            if 'pro' in args.model_name and args.thinking_level in ['minimal', 'medium']:
                raise ValueError("Gemini-3 Pro only supports 'low' and 'high' thinking levels.")
        else:
            if args.thinking_level is not None:
                logger.warning("Thinking level is not applicable for non-Gemini-3 models. Ignoring --thinking-level.")
            if args.thinking_budget is None:
                parser.error("--thinking-budget is required for non-Gemini-3 models")
            if 'pro' in args.model_name and args.thinking_budget == 0:
                raise ValueError("For Gemini 2.5 Pro, thinking can not be disabled (thinking budget cannot be 0).")

    countries = discover_countries(args.output_dir)
    if not countries:
        parser.error(f"No country directories found in {args.output_dir}. Run generate_prompts first.")

    for country in countries:
        country_dir = args.output_dir / country
        prompts_file = country_dir / 'prompts.jsonl'
        if not prompts_file.exists():
            logger.warning(f"No prompts.jsonl in {country_dir}, skipping.")
            continue
        logger.info(f"Generating requests for {country}...")
        run(args.provider, prompts_file, model_path=args.model_path,
            model_name=args.model_name, output_dir=country_dir,
            thinking_budget=args.thinking_budget, thinking_level=args.thinking_level)

    logger.info(f"Done. Requests generated in {args.output_dir}")


if __name__ == "__main__":
    main()
