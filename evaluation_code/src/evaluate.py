import json
import argparse
import logging
from pathlib import Path
import pandas as pd
from sacrebleu.metrics import BLEU, CHRF
from utils.common import discover_countries, setup_logging

logger = logging.getLogger(__name__)


sp_bleu = BLEU(tokenize='flores200', effective_order=True)
chrf_pp = CHRF(word_order=2)


def compute_metrics(results_df):
    output = {
        'all': {},
        'domains': {}
    }

    predictions = results_df['output'].tolist()
    references = results_df['reference'].tolist()

    bleu_score = sp_bleu.corpus_score(predictions, [references]).score
    chrf_score = chrf_pp.corpus_score(predictions, [references]).score

    output['all']['spBLEU'] = bleu_score
    output['all']['CHRF++'] = chrf_score
    output['all']['num_samples'] = len(results_df)

    domains = results_df['domain'].unique()
    for domain in domains:
        domain_df = results_df[results_df['domain'] == domain]
        domain_predictions = domain_df['output'].tolist()
        domain_references = domain_df['reference'].tolist()

        domain_bleu = sp_bleu.corpus_score(
            domain_predictions, [domain_references]).score
        domain_chrf = chrf_pp.corpus_score(
            domain_predictions, [domain_references]).score

        output['domains'][domain] = {
            'spBLEU': domain_bleu,
            'CHRF++': domain_chrf
        }
        output['domains'][domain]['num_samples'] = len(domain_df)

    return output


def compute_task_metrics(df, model_name):
    """Compute metrics for a DataFrame, stratified by task, meta_level, and direction."""
    tasks = df['task'].unique()
    meta_levels = df['meta_level'].unique()
    results = {}

    for task in tasks:
        task_df = df[df['task'] == task].copy().reset_index(drop=True)
        task_result = {'model': model_name}

        for meta_level in meta_levels:
            ml_df = task_df[task_df['meta_level'] == meta_level].copy().reset_index(drop=True)
            dialect_df = ml_df[ml_df['to_english'] == False].copy().reset_index(drop=True).fillna('')
            english_df = ml_df[ml_df['to_english'] == True].copy().reset_index(drop=True).fillna('')

            task_result[meta_level] = {}
            if not dialect_df.empty:
                task_result[meta_level]['to_ar'] = compute_metrics(dialect_df)
            if not english_df.empty:
                task_result[meta_level]['to_en'] = compute_metrics(english_df)

        results[task] = task_result

    return results


def extract_turns(inputs, responses):
    inputs_values = list(inputs.values())
    outputs = [responses.get(key, '') for key in inputs.keys()]
    return inputs_values, outputs

def flatten(data):
    flattend = []

    for sample in data:
        task = sample['task']
        if task == 'conversation':
            inputs, outputs = extract_turns(sample['input'], sample['response'])
            references = list(sample['reference'].values())
            gender_directions = sample['meta_data']['gender_direction'].values()

            for idx, (inp, out, ref, gdct) in enumerate(zip(inputs, outputs, references, gender_directions)):
                flattend.append({
                    'custom_id': f"{sample['custom_id']}_{idx+1}",
                    'conv_id': sample['meta_data']['conv_id'],
                    'turn_order': idx + 1,
                    'task': task,
                    'input': inp,
                    'output': out,
                    'reference': ref,
                    'direction': gdct,
                    'domain': sample['meta_data']['domain'],
                    'meta_data': sample['meta_data'],
                    'to_english': sample['meta_data']['to_english'],
                    'meta_level': sample['meta_data']['meta_level'],
                    'model': sample['model'],
                })

        if task in ['turn', 'context']:
            flattend.append({
                'custom_id': sample['custom_id'],
                'conv_id': sample['meta_data']['conv_id'],
                'turn_order': int(sample['custom_id'].split('_')[-1]),
                'task': task,
                'input': sample['input'],
                'output': sample['response'],
                'reference': sample['reference'],
                'direction': sample['meta_data']['gender_direction'],
                'domain': sample['meta_data']['domain'],
                'meta_data': sample['meta_data'],
                'to_english': sample['meta_data']['to_english'],
                'meta_level': sample['meta_data']['meta_level'],
                'model': sample['model'],
            })

    return flattend

def get_model(df):
    model_names = df['model'].unique()
    if len(model_names) == 1:
        return model_names[0]
    else:
        logger.warning("Multiple models found, setting model_name to 'multiple_models'")
        return 'multiple_models'

def run(parsed_file, output_dir=None):
    parsed_file = Path(parsed_file)

    if output_dir:
        eval_dir = Path(output_dir) / 'evaluate' / parsed_file.stem.removesuffix('_parsed')
    else:
        eval_dir = parsed_file.parent.parent / 'evaluate' / parsed_file.stem.removesuffix('_parsed')

    eval_dir.mkdir(parents=True, exist_ok=True)

    with open(parsed_file, 'r', encoding='utf-8') as f:
        data = [json.loads(line) for line in f]

    flattened_data = flatten(data)
    df = pd.DataFrame(flattened_data)
    model_name = get_model(df)

    df['spBLEU'] = df.apply(lambda row: sp_bleu.sentence_score(row['output'], [row['reference']]).score, axis=1)
    df['CHRF++'] = df.apply(lambda row: chrf_pp.sentence_score(row['output'], [row['reference']]).score, axis=1)

    df.to_json(eval_dir / 'outputs.jsonl', orient='records', lines=True, force_ascii=False)
    logger.info(f"Saved flattened outputs to {eval_dir / 'outputs.jsonl'}")

    task_metrics = compute_task_metrics(df, model_name)
    for task, metrics in task_metrics.items():
        with open(eval_dir / f'{task}_metrics.json', 'w', encoding='utf-8') as out_f:
            json.dump(metrics, out_f, ensure_ascii=False, indent=4)
        logger.info(f"Saved {task} metrics to {eval_dir / f'{task}_metrics.json'}")

    # Return only the "all" results (no per-domain breakdown)
    summary = {}
    for task, metrics in task_metrics.items():
        task_summary = {'model': metrics['model']}
        for key, value in metrics.items():
            if key == 'model':
                continue
            task_summary[key] = {}
            for direction, dir_metrics in value.items():
                task_summary[key][direction] = dir_metrics['all']
        summary[task] = task_summary

    return summary


def main():
    parser = argparse.ArgumentParser(description='Evaluate parsed outputs')
    parser.add_argument('-o', '--output-dir', type=Path, required=True,
                        help='Output directory (with country subdirs)')

    args = parser.parse_args()

    setup_logging(args.output_dir, 'evaluate')

    countries = discover_countries(args.output_dir)
    if not countries:
        parser.error(f"No country directories found in {args.output_dir}.")

    per_country = {}
    for country in countries:
        country_dir = args.output_dir / country
        parsed_dir = country_dir / 'parsed'
        if not parsed_dir.exists():
            logger.warning(f"No parsed dir for {country}, skipping.")
            continue

        parsed_files = list(parsed_dir.glob('*_parsed.jsonl'))
        if not parsed_files:
            logger.warning(f"No parsed files for {country}, skipping.")
            continue

        per_country[country] = {}
        for parsed_file in parsed_files:
            logger.info(f"Evaluating {country} / {parsed_file.name}...")
            summary = run(parsed_file, output_dir=country_dir)
            model_name = next(iter(summary.values()))['model']
            per_country[country][model_name] = summary

    # Write aggregated results
    results_file = args.output_dir / 'results.json'
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(per_country, f, ensure_ascii=False, indent=4)
    logger.info(f"Done. Results: {results_file}")


if __name__ == "__main__":
    main()
