import argparse
from pathlib import Path
from datetime import datetime
from utils.prompts import get_prompt
from utils.common import COUNTRY_CODE_TO_NAME, write_jsonl, setup_logging
from datasets import load_dataset
import logging

logger = logging.getLogger(__name__)

META_INDEX = {'full': 'f', 'none': 'n', 'partial': 'p'}


def load_hf_dataset(country_code, split="test"):
    logger.info(f"Loading UBC-NLP/alexandria config={country_code} split={split}...")
    try:
        ds = load_dataset("UBC-NLP/alexandria", country_code, split=split)
    except Exception as e:
        if "gated" in str(e).lower() or "401" in str(e) or "403" in str(e):
            logger.error(
                "Dataset is gated. Please accept the terms at "
                "https://huggingface.co/datasets/UBC-NLP/alexandria "
                "and run: huggingface-cli login")
        raise
    data = [dict(row) for row in ds]
    logger.info(f"Loaded {len(data)} conversations for {country_code}")
    return data


def preprocess(sample, to_english, meta_level='full'):
    source_key = 'dialectal_conversation' if to_english else 'english_conversation'
    lang_dir = 'en' if to_english else 'ar'

    meta_suffix = '' if meta_level == 'full' else f'_{META_INDEX[meta_level]}'
    id_ = f'{sample["conv_id"]}_{sample["country"]}{meta_suffix}_{lang_dir}'

    conversation = {
        'id': id_,
        'meta_data': {
            'conv_id': sample['conv_id'],
            'country_id': sample['country'],
            'country': COUNTRY_CODE_TO_NAME[sample['country']],
            'domain': sample['domain'].replace('_', ' ').title(),
            'participants': sample['participants'],
            'dialect': sample['dialect'],
            'to_english': to_english,
            'meta_level': meta_level
        },
        'turns': {}
    }

    for turn in sample[source_key]:
        gender_direction = 'to'.join(turn['direction'].split('->'))
        turn_data = {
            'speaker': turn['speaker'],
            'text': turn['text'],
            'gender_direction': gender_direction
        }
        conversation['turns'][f'turn_{turn["turn_order"]}'] = turn_data
    return conversation


def turn_level(conversation):
    turns = []
    meta_data = conversation['meta_data']
    for turn_key, turn_data in conversation['turns'].items():
        turn_id = turn_key.split('_')[-1]
        turn_info = {
            'id': f"turn_{conversation['id']}_{turn_id}",
            'meta_data': meta_data,
            'turn': turn_data
        }
        turns.append(turn_info)
    return turns


def context_level(conversation):
    contexts = []
    meta_data = conversation['meta_data']
    turn_items = list(conversation['turns'].items())

    for i, (turn_key, turn_data) in enumerate(turn_items):
        turn_id = turn_key.split('_')[-1]
        turn_info = {
            'id': f"cont_{conversation['id']}_{turn_id}",
            'meta_data': meta_data,
            'turns': {
                'context': [data for _, data in turn_items[:i]],
                'current': turn_data
            }
        }
        contexts.append(turn_info)

    return contexts

def build_reference(sample, to_english):
    ref_key = 'english_conversation' if to_english else 'dialectal_conversation'
    reference = {}
    for turn in sample[ref_key]:
        gender_direction = 'to'.join(turn['direction'].split('->'))
        reference[f'turn_{turn["turn_order"]}'] = {
            'speaker': turn['speaker'],
            'text': turn['text'],
            'gender_direction': gender_direction
        }
    return reference


def build_sample(sample, to_english, tasks, meta_level='full'):
    prompts = []
    reference_turns = build_reference(sample, to_english)

    conversation = preprocess(sample, to_english, meta_level=meta_level)
    conversation_prompt = get_prompt('conversation', conversation, to_english, meta_level=meta_level)

    if 'conversation' in tasks:
        prompts.append({
            'id': f'conv_{conversation["id"]}',
            'prompt': conversation_prompt,
            'task': 'conversation',
            'input': conversation,
            'reference': reference_turns
        })

    if 'turn' in tasks:
        turns = turn_level(conversation)
        for turn in turns:
            turn_id = turn['id'].split('_')[-1]
            turn_prompt = get_prompt('turn', turn, to_english, meta_level=meta_level)
            prompts.append({
                'id': turn['id'],
                'prompt': turn_prompt,
                'task': 'turn',
                'input': turn,
                'reference': reference_turns[f'turn_{turn_id}']
            })

    if 'context' in tasks:
        contexts = context_level(conversation)
        for context in contexts:
            turn_id = context['id'].split('_')[-1]
            context_prompt = get_prompt('context', context, to_english, meta_level=meta_level)
            prompts.append({
                'id': context['id'],
                'prompt': context_prompt,
                'task': 'context',
                'input': context,
                'reference': reference_turns[f'turn_{turn_id}']
            })

    if len(prompts) == 0:
        logger.warning(f"No prompts generated for sample with conv_id {sample['conv_id']} and to_english={to_english}")

    return prompts


def run(data, tasks, meta_levels, direction='both', output_dir=None):
    if output_dir is None:
        raise ValueError("output_dir is required.")

    output_file = Path(output_dir) / 'prompts.jsonl'
    output_file.parent.mkdir(parents=True, exist_ok=True)

    if output_file.exists():
        logger.warning(f"Output file {output_file} already exists.")

    for sample in data:
        for meta_level in meta_levels:
            if direction in ('to_en', 'both'):
                write_jsonl(output_file, build_sample(sample, to_english=True, tasks=tasks, meta_level=meta_level))
            if direction in ('to_ar', 'both'):
                write_jsonl(output_file, build_sample(sample, to_english=False, tasks=tasks, meta_level=meta_level))

    return output_file


def main():
    parser = argparse.ArgumentParser(
        description='Load HuggingFace data and generate prompts for multiple countries')
    parser.add_argument('-c', '--country', nargs='+', required=True,
                        choices=list(COUNTRY_CODE_TO_NAME.keys()),
                        help='Country code(s) to process')
    parser.add_argument('-o', '--output-dir', type=Path, default=None,
                        help='Output directory (default: outputs/run_<timestamp>)')
    parser.add_argument('--split', default='test',
                        help='HF dataset split (default: test)')
    parser.add_argument('-t', '--tasks', nargs='+',
                        choices=['conversation', 'turn', 'context', 'all'],
                        default=['conversation'],
                        help='Task type(s) to process')
    parser.add_argument('-m', '--meta-level', nargs='+',
                        choices=['full', 'none', 'partial', 'all'],
                        default=['full'],
                        help='Metadata level(s)')
    parser.add_argument('-d', '--direction',
                        choices=['to_ar', 'to_en', 'both'],
                        default='both',
                        help='Translation direction (default: both)')

    args = parser.parse_args()
    
    if args.output_dir is None:
        run_key = datetime.now().strftime('%Y%m%d_%H%M%S')
        args.output_dir = Path('outputs') / f'run_{run_key}'

    setup_logging(args.output_dir, 'generate_prompts')

    tasks = ['conversation', 'turn', 'context'] if 'all' in args.tasks else args.tasks
    meta_levels = ['full', 'none', 'partial'] if 'all' in args.meta_level else args.meta_level

    logger.info(f"Output directory: {args.output_dir}")

    for country in args.country:
        logger.info(f"Processing {country}...")
        data = load_hf_dataset(country, split=args.split)
        country_dir = args.output_dir / country
        prompts_file = run(data, tasks, meta_levels, args.direction, output_dir=country_dir)
        logger.info(f"Prompts: {prompts_file}")

    logger.info(f"Done. Output: {args.output_dir}")


if __name__ == "__main__":
    main()
