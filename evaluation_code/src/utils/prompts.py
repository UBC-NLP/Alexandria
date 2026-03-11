import json
import logging

logger = logging.getLogger(__name__)


def get_prompt(task, sample, to_english=False, meta_level='full'):
    if task == 'conversation':
        if to_english:
            return prompt_conv_to_en(sample, meta_level)
        else:
            return prompt_conv_to_ar(sample, meta_level)
    elif task == 'turn':
        if to_english:
            return prompt_turn_to_en(sample, meta_level)
        else:
            return prompt_turn_to_ar(sample, meta_level)
    elif task == 'context':
        if to_english:
            return prompt_context_to_en(sample, meta_level)
        else:
            return prompt_context_to_ar(sample, meta_level)
    else:
        raise ValueError(f"Unknown task: {task}")

## GUIDELINES
def guidelines_conv(meta_level, dialect, to_english):
    lines = [
        "- Return the result strictly in valid JSON.",
    ]

    if not to_english:
        lines.append(f"- Translate to {dialect} using Arabic script.")

    lines.append("- Do not add any code, explanations, comments, or any other extra text.")
    lines.append("- The translation of each turn should be faithful to the original turn.")

    if meta_level == 'none':
        lines.append("- Keep the meaning and tone.")
    else:
        lines.append("- Keep the meaning and tone and respect the gender direction.")

    if meta_level == 'full':
        lines.append("- Consider the country and domain of the conversation.")

    return "\n".join(lines)


def guidelines_turn(meta_level, dialect, to_english, is_context=False):
    lines = [
        "- Return the result strictly in valid JSON.",
    ]

    if not to_english:
        lines.append(f"- Translate to {dialect} using Arabic script.")

    lines.append("- Do not add any code, explanations, comments, or any other extra text.")

    if is_context:
        lines.append("- The translation should be faithful to the original turn.")

    if meta_level == 'none':
        lines.append("- Keep the meaning and tone.")
    else:
        lines.append("- Keep the meaning and tone and respect the gender direction.")

    if meta_level == 'full':
        lines.append("- Consider the country, the domain, the participants, and the speaker in your translation.")

    if is_context:
        lines.append('- Only translate the "text" field of the "current_turn".')
        lines.append("- If a context is provided, do not translate it, and use it to inform your translation.")

    return "\n".join(lines)


# PROMPT: CONVERSATION LEVEL

def prompt_conv_to_ar(conversation, meta_level='full'):
    if meta_level == 'full':
        turns = conversation['turns']
    elif meta_level == 'partial':
        turns = {
            k: {'text': v['text'], 'gender_direction': v['gender_direction']}
            for k, v in conversation['turns'].items()
        }
    else:
        turns = {
            k: {'text': v['text']}
            for k, v in conversation['turns'].items()
        }

    sample = {}
    if meta_level == 'full':
        sample['country'] = conversation['meta_data']['country']
        sample['domain'] = conversation['meta_data']['domain']
        sample['participants'] = conversation['meta_data']['participants']
    sample['turns'] = turns

    dialect = conversation['meta_data']['dialect']
    guidelines = guidelines_conv(meta_level, dialect, to_english=False)

    prompt = f"""Translate all turns in the following conversation from English to {dialect}.

Input:
{json.dumps(sample, ensure_ascii=False, indent=4)}

Guidelines:
{guidelines}

Output scheme:
{{
    "turn_1": "translation of the text from turn_1",
    "turn_2": "translation of the text from turn_2",
    ...
}}
"""
    return prompt

def prompt_conv_to_en(conversation, meta_level='full'):
    if meta_level == 'full':
        turns = conversation['turns']
    elif meta_level == 'partial':
        turns = {
            k: {'text': v['text'], 'gender_direction': v['gender_direction']}
            for k, v in conversation['turns'].items()
        }
    else:
        turns = {
            k: {'text': v['text']}
            for k, v in conversation['turns'].items()
        }

    sample = {}
    if meta_level == 'full':
        sample['country'] = conversation['meta_data']['country']
        sample['domain'] = conversation['meta_data']['domain']
        sample['participants'] = conversation['meta_data']['participants']
    sample['turns'] = turns

    dialect = conversation['meta_data']['dialect']
    guidelines = guidelines_conv(meta_level, dialect, to_english=True)

    prompt = f"""Translate all turns in the following conversation from {dialect} to English.

Input:
{json.dumps(sample, ensure_ascii=False, indent=4)}

Guidelines:
{guidelines}

Output scheme:
{{
    "turn_1": "translation of the text from turn_1",
    "turn_2": "translation of the text from turn_2",
    ...
}}
"""
    return prompt


# PROMPTS: TURN LEVEL

def prompt_turn_to_ar(turn, meta_level='full'):
    sample = {}
    if meta_level == 'full':
        sample['country'] = turn['meta_data']['country']
        sample['domain'] = turn['meta_data']['domain']
        sample['participants'] = turn['meta_data']['participants']
        sample['gender_direction'] = turn['turn']['gender_direction']
        sample['speaker'] = turn['turn']['speaker']
    elif meta_level == 'partial':
        sample['gender_direction'] = turn['turn']['gender_direction']
    sample['text'] = turn['turn']['text']

    dialect = turn['meta_data']['dialect']
    guidelines = guidelines_turn(meta_level, dialect, to_english=False)

    prompt = f"""Translate the English text contained in the JSON input into {dialect}.

Input:
{json.dumps(sample, ensure_ascii=False, indent=4)}

Guidelines:
{guidelines}

Output scheme:
{{
    "translation": "translated text here",
}}
"""
    return prompt


def prompt_turn_to_en(turn, meta_level='full'):
    sample = {}
    if meta_level == 'full':
        sample['country'] = turn['meta_data']['country']
        sample['domain'] = turn['meta_data']['domain']
        sample['participants'] = turn['meta_data']['participants']
        sample['gender_direction'] = turn['turn']['gender_direction']
        sample['speaker'] = turn['turn']['speaker']
    elif meta_level == 'partial':
        sample['gender_direction'] = turn['turn']['gender_direction']
    sample['text'] = turn['turn']['text']

    dialect = turn['meta_data']['dialect']
    guidelines = guidelines_turn(meta_level, dialect, to_english=True)

    prompt = f"""Translate the {dialect} text contained in the JSON input into English.

Input:
{json.dumps(sample, ensure_ascii=False, indent=4)}

Guidelines:
{guidelines}

Output scheme:
{{
    "translation": "translated text here",
}}
"""
    return prompt


# PROMPTS: CONTEXT LEVEL


def prompt_context_to_ar(context, meta_level='full'):
    def _filter_turn(turn_data):
        if meta_level == 'full':
            return turn_data
        elif meta_level == 'partial':
            return {'text': turn_data['text'], 'gender_direction': turn_data['gender_direction']}
        else:
            return {'text': turn_data['text']}

    sample = {}
    if meta_level == 'full':
        sample['country'] = context['meta_data']['country']
        sample['domain'] = context['meta_data']['domain']
        sample['participants'] = context['meta_data']['participants']
    sample['context'] = [_filter_turn(t) for t in context['turns']['context']]
    sample['current_turn'] = _filter_turn(context['turns']['current'])

    dialect = context['meta_data']['dialect']
    guidelines = guidelines_turn(meta_level, dialect, to_english=False, is_context=True)

    prompt = f"""Translate the given turn of a conversation from English to {dialect}, considering the previous context if provided.

Input:
{json.dumps(sample, ensure_ascii=False, indent=4)}

Guidelines:
{guidelines}

Output scheme:
{{
    "translation": "translation of the text from the current turn",
}}
"""
    return prompt


def prompt_context_to_en(context, meta_level='full'):
    def _filter_turn(turn_data):
        if meta_level == 'full':
            return turn_data
        elif meta_level == 'partial':
            return {'text': turn_data['text'], 'gender_direction': turn_data['gender_direction']}
        else:
            return {'text': turn_data['text']}

    sample = {}
    if meta_level == 'full':
        sample['country'] = context['meta_data']['country']
        sample['domain'] = context['meta_data']['domain']
        sample['participants'] = context['meta_data']['participants']
    sample['context'] = [_filter_turn(t) for t in context['turns']['context']]
    sample['current_turn'] = _filter_turn(context['turns']['current'])

    dialect = context['meta_data']['dialect']
    guidelines = guidelines_turn(meta_level, dialect, to_english=True, is_context=True)

    prompt = f"""Translate the given turn of a conversation from {dialect} to English, considering the previous context if provided.

Input:
{json.dumps(sample, ensure_ascii=False, indent=4)}

Guidelines:
{guidelines}

Output scheme:
{{
    "translation": "translation of the text from the current turn",
}}
"""
    return prompt
