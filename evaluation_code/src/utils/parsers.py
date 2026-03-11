import json
import re
import logging

logger = logging.getLogger(__name__)

REASONING_TAGS = [
    ('<think>', '</think>'),
    ('<|START_THINKING|>', '<|END_THINKING|>'),
]

def parse_output(output, task, n_turns=None, custom_id=None):

    empty_response = {} if task == 'conversation' else ''

    if output is None:
        logger.error(f"{custom_id} -- No output to parse.")
        return {
            'response': empty_response,
            'error': {'code': 'output_error', 'message': 'No output to parse.'},
            'warning': None,
        }

    output = remove_reasoning_trace(output)

    warning = None
    if task == 'conversation':
        response = parse_conv(output, n_turns=n_turns)
        if len(response) != n_turns:
            warning = f'{custom_id} -- Parsed turns {len(response)} does not match expected {n_turns}.'
            logger.warning(warning)
    elif task in ['turn', 'context']:
        response = parse_turn(output)
    else:
        raise ValueError(f"Unknown task: {task}")

    if not response:
        logger.error(f"{custom_id} -- Failed to parse output.")
        return {
            'response': empty_response,
            'error': {
                'code': 'parsing_error',
                'message': 'Failed to parse output.'
            },
            'warning': None,
        }

    return  {
        'response': response,
        'error': None,
        'warning': warning,
    }

def remove_reasoning_trace(text):
    for start_tag, end_tag in REASONING_TAGS:
        start_idx = text.find(start_tag)
        if start_idx == -1:
            continue
        end_idx = text.find(end_tag)
        if end_idx == -1:
            return ""
        return text[:start_idx] + text[end_idx + len(end_tag):]
    return text

# UTILITY FUNCTIONS
def has_unicode_escapes(text):
    pattern = r'\\u[0-9a-fA-F]{4}'
    return bool(re.search(pattern, text))

def decode_unicode_escapes(text):
    try:
        return text.encode().decode('unicode-escape')
    except Exception:
        return text

def is_desired_conv_format(data):
    if not isinstance(data, dict):
        return False
    for key, value in data.items():
        if not re.match(r'turn_\d+', key):
            return False
        if not isinstance(value, str):
            return False
    return True

def is_input_conv_format(data):
    if not isinstance(data, dict):
        return False
    if 'turns' not in data:
        return False
    if not isinstance(data['turns'], dict):
        return False
    return is_output_conv_format(data['turns'])

def is_output_conv_format(data):
    for key, value in data.items():
        if not re.match(r'turn_\d+', key):
            return False
        if not isinstance(value, dict):
            return False
        if 'text' not in value:
            return False
        if not isinstance(value['text'], str):
            return False
    return True

def valid_conv(data):
    if is_desired_conv_format(data):
        return data
    elif is_input_conv_format(data):
        return {k: v['text'] for k, v in data['turns'].items()}
    elif is_output_conv_format(data):
        return {k: v['text'] for k, v in data.items()}
    return {}

# CONV PARSERS

def parse_json_conv(text):
    try:
        cleaned = re.sub(r'```json\s*|\s*```', '', text.strip())
        data = json.loads(cleaned)
        return valid_conv(data)
    except json.JSONDecodeError as e:
        logger.debug(f"Failed to parse JSON: {e}")
        return {}


def match_conv(text):
    pattern = r'''["']turn_(\d+)["']\s*:\s*["'](.+?)["'](?=\s*[,}])'''
    matches = re.findall(pattern, text, re.DOTALL)
    if not matches:
        return {}
    turns = {f'turn_{num}': content for num, content in matches}
    return turns

def get_text(text):
    text_idx = text.find('"text":')
    if text_idx == -1:
        return text
    start_idx = text_idx + len('"text":')
    end_idx = text.find(',\n', start_idx)
    if end_idx == -1:
        end_idx = len(text)
    content = text[start_idx:end_idx].strip().strip('"\'')
    return content

def match_turns_conv(text):
    pattern = r'"?turn_(\d+)"?\s*:'
    matches = list(re.finditer(pattern, text))

    if not matches:
        logger.debug(f'No matches found in match_turns')
        return {}

    result = {}

    for i, match in enumerate(matches):
        turn_name = f"turn_{match.group(1)}"
        start_pos = match.end()

        if i < len(matches) - 1:
            end_pos = matches[i + 1].start()
        else:
            end_pos = len(text)

        content = text[start_pos:end_pos].strip()
        content = get_text(content)

        content = content.strip('"\'').strip(',').strip()
        content = content.rstrip('}').strip()
        content = content.strip('"\'').strip(',').strip()
        content = content.replace('\\n', ' ').strip()

        result[turn_name] = content

    if not result:
        logger.debug(f'No turns extracted in match_turns')

    return result


def parse_conv(text, n_turns):
    for parser_fn in [parse_json_conv, match_conv, match_turns_conv]:
        result = parser_fn(text)
        if result and (len(result) >= n_turns):
            return valid_conv(result)
    return result


# TURN, CONTEXT

def extract_jsons(text) -> list:
    results = []
    i = 0

    while i < len(text):
        if text[i] == '{':
            brace_count = 0
            start = i

            while i < len(text):
                if text[i] == '{':
                    brace_count += 1
                elif text[i] == '}':
                    brace_count -= 1

                    if brace_count == 0:
                        json_str = text[start:i+1]
                        try:
                            json_str = json_str.replace(r"\'", "'")
                            data = json.loads(json_str)
                            results.append(data)
                        except json.JSONDecodeError as e:
                            logger.debug(f"JSON decoding error: {e} while parsing: {json_str}")
                        break
                i += 1
        i += 1

    return results

def parse_json_turn(output_text):
    json_objects = extract_jsons(output_text)
    for obj in json_objects:
        if "translation" in obj:
            translation = obj['translation']
            if isinstance(translation, dict) and 'text' in translation:
                translation = translation['text']
            if isinstance(translation, dict) and 'current_turn' in translation:
                translation = translation['current_turn']
            if isinstance(translation, str):
                return translation
    return ""

def match_text_turn(text):
    match = re.search(r'"translation":\s*"([^"\n]*)', text)
    if match:
        return match.group(1)
    return ""

def match_json_turn(text):
    match = re.search(r'\{\s*"translation":\s*"([^"]*)"\s*\}', text)
    if match:
        return match.group(1)
    return ""

def load_json_turn(text):
    try:
        cleaned = re.sub(r'```json\s*|\s*```', '', text.strip())
        data = json.loads(cleaned)
        if 'translation' in data and isinstance(data['translation'], str):
            return data['translation']
        return ""
    except json.JSONDecodeError as e:
        logger.debug(f"Failed to parse JSON turn: {e}")
        return ""

def parse_turn(text):

    for parser_fn in [load_json_turn, match_json_turn, match_text_turn, parse_json_turn]:
        result = parser_fn(text)
        if result:
            if has_unicode_escapes(result):
                result = decode_unicode_escapes(result)
            return result

    if '\\' in text and not has_unicode_escapes(text):
        text = text.replace('\\','')
        result = parse_turn(text)
        if result and isinstance(result, str):
            return result
    return ""
