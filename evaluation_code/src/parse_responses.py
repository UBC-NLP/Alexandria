import argparse
import json
from pathlib import Path
import pandas as pd
import logging
from utils.parsers import parse_output
from utils.common import setup_logging, read_jsonl, discover_countries

logger = logging.getLogger(__name__)

def id_to_task(custom_id):
    if 'turn' in custom_id:
        return 'turn'
    if 'cont' in custom_id:
        return 'context'
    return 'conversation'

def get_geimini_response(response):
    model = response['response']['modelVersion']
    response_id = response['response']['responseId']

    if response['status']:
        error = {
            'code': response['status'].get('code', 'unknown_error'),
            'message': response['status'].get('message', 'Could not retrieve error message.')
        }
    else:
        error = None

    candidates = response['response'].get('candidates', [])
    if not candidates:
        output = None
    else:
        if response['response']['candidates'][0]['finishReason'] == 'MAX_TOKENS':
            output = None # NOTE: Will be catched later in `build_response`
            error = {
                'code': 'max_tokens',
                'message': 'Response reached maximum token limit.'
            }
        else:
            error = None
            content = response['response']['candidates'][0]['content']
            output = '\n'.join([part['text'] for part in content['parts']])

    return {
        'response_id': response_id,
        'model': model,
        'error': error,
        'output': output,
    }

def get_vllm_response(response):
    model = Path(response['response']['body']['model']).name
    error = response['error']
    response_id = response['id']
    output = response['response']['body']['choices'][0]['message']['content']
    return {
        'response_id': response_id,
        'model': model,
        'error': error,
        'output': output,
    }

def get_response(response, provider):
    if provider == 'vllm':
        return get_vllm_response(response)
    elif provider == 'gemini':
        return get_geimini_response(response)
    else:
        raise ValueError(f"Unknown provider: {provider}")

def build_response(sample, provider, n_turns=None):
    custom_id = sample['custom_id']
    task = id_to_task(custom_id)
    response = get_response(sample, provider)

    if response['error'] is not None:
        logger.error(f"Error in response for {custom_id}: {response['error']}")
        return {
            'custom_id': custom_id,
            'response_id': response['response_id'],
            'model': response['model'],
            'response': {} if task == 'conversation' else '',
            'raw_response': None,
            'error': response['error'],
            'warning': None,
        }

    output = parse_output(
        response['output'], task, n_turns=n_turns, custom_id=custom_id)

    return {
        'custom_id': custom_id,
        'response_id': response['response_id'],
        'model': response['model'],
        'response': output['response'],
        'raw_response': response['output'],
        'error': output['error'],
        'warning': output['warning'],
    }


def parse_reference(sample):
    task = id_to_task(sample['id'])
    meta_data = sample['input'].get('meta_data', {})
    if task == 'conversation':
        input_ = {
            k: v['text']
            for k, v in sample['input']['turns'].items()
        }
        reference = {
            k: v['text']
            for k, v in sample['reference'].items()
        }
        gender_direction = {
            k: v['gender_direction']
            for k, v in sample['reference'].items()
        }
    elif task == 'turn':
        input_ = sample['input']['turn']['text']
        reference = sample['reference']['text']
        gender_direction = sample['reference']['gender_direction']
    elif task == 'context':
        input_ = sample['input']['turns']['current']['text']
        reference = sample['reference']['text']
        gender_direction = sample['reference']['gender_direction']
    meta_data['gender_direction'] = gender_direction
    return {
        'custom_id': sample['id'],
        'task': task,
        'input': input_,
        'reference': reference,
        'meta_data': meta_data,
    }

def build_output(parsed_output, reference_input):
    output = {
        'custom_id': reference_input['custom_id'],
        'response_id': parsed_output['response_id'],
        'model': parsed_output['model'],
        'response': parsed_output['response'],
        'raw_response': parsed_output['raw_response'],
        'task': reference_input['task'],
        'input': reference_input['input'],
        'reference': reference_input['reference'],
        'meta_data': reference_input['meta_data'],
        'error': parsed_output['error'],
        'warning': parsed_output['warning'],
    }
    return output

def run(responses_file, prompts_file, provider, output_dir=None, save_stats=False):
    responses_file = Path(responses_file)
    prompts_file = Path(prompts_file)

    if output_dir:
        output_dir = Path(output_dir)
        output_file = output_dir / 'parsed' / f'{responses_file.stem}_parsed.jsonl'
        stats_file = output_dir / 'parse_stats' / f'{responses_file.stem}_parse_stats.json'
    else:
        output_file = responses_file.parent.parent / 'parsed' / f'{responses_file.stem}_parsed.jsonl'
        stats_file = responses_file.parent.parent / 'parse_stats' / f'{responses_file.stem}_parse_stats.json'

    output_file.parent.mkdir(parents=True, exist_ok=True)
    if save_stats:
        stats_file.parent.mkdir(parents=True, exist_ok=True)

    input_df = read_jsonl(prompts_file)
    sample_inputs = []
    for sample in input_df:
        sample = parse_reference(sample)
        sample_inputs.append(sample)
    input_df = pd.DataFrame(sample_inputs)

    data = read_jsonl(responses_file)
    parsed_outputs = []
    for sample in data:
        reference_input = input_df[input_df['custom_id'] == sample['custom_id']].iloc[0]
        if reference_input.empty:
            logger.warning(f"Warning: No reference found for custom_id {sample['custom_id']}")
            continue
        parsed_output = build_response(
            sample, provider, len(reference_input['reference']))
        parsed_o = build_output(parsed_output, reference_input)
        parsed_outputs.append(parsed_o)

    stats_df = pd.DataFrame(parsed_outputs)
    failed_df = stats_df[stats_df['error'].notnull() | stats_df['warning'].notnull()]
    failed_items = failed_df[['custom_id', 'error', 'warning', 'response', 'raw_response']].to_dict('records')
    logger.info(f"Failed responses (errors or warnings): {len(failed_df)} / {len(stats_df)}")

    logger.info(f"Writing parsed responses...")
    with open(output_file, 'w', encoding='utf-8') as f:
        for item in parsed_outputs:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')
    logger.info(f"Parsed responses written to {output_file}")

    if save_stats:
        failed_stats = {
            'total_responses': len(stats_df),
            'failed_responses': len(failed_df),
            'n_errors': len(failed_df[failed_df['error'].notnull()]),
            'n_warnings': len(failed_df[failed_df['warning'].notnull()]),
            'failed_items': failed_items,
        }
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(failed_stats, f, indent=4, ensure_ascii=False)
        logger.info(f"Parsing statistics written to {stats_file}")

    return output_file


def main():
    parser = argparse.ArgumentParser(description='Parse JSONL responses')
    parser.add_argument('-p', '--provider', type=str, default='vllm',
                        help='Provider name (default: vllm)')
    parser.add_argument('-o', '--output-dir', type=Path, required=True,
                        help='Output directory (with country subdirs)')
    parser.add_argument('-s', '--save-stats', action='store_true',
                        help='Whether to save parsing statistics.')

    args = parser.parse_args()

    setup_logging(args.output_dir, 'parse_responses')

    countries = discover_countries(args.output_dir)
    if not countries:
        parser.error(f"No country directories found in {args.output_dir}.")

    for country in countries:
        country_dir = args.output_dir / country
        prompts_file = country_dir / 'prompts.jsonl'
        responses_dir = country_dir / 'responses'

        if not prompts_file.exists():
            logger.warning(f"No prompts.jsonl in {country_dir}, skipping.")
            continue
        if not responses_dir.exists():
            logger.warning(f"No responses dir in {country_dir}, skipping.")
            continue

        response_files = list(responses_dir.glob('*.jsonl'))
        if not response_files:
            logger.warning(f"No response files in {responses_dir}, skipping.")
            continue

        for responses_file in response_files:
            logger.info(f"Parsing {country} / {responses_file.name}...")
            run(responses_file, prompts_file, args.provider,
                output_dir=country_dir, save_stats=args.save_stats)

    logger.info(f"Done. Parsed outputs in {args.output_dir}")


if __name__ == "__main__":
    main()
