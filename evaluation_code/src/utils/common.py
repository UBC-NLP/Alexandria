import json
import logging
from pathlib import Path


COUNTRY_CODE_TO_NAME = {
    "JO": "Jordan",
    "LB": "Lebanon",
    "PS": "Palestine",
    "SY": "Syria",
    "SA": "Saudi Arabia",
    "OM": "Oman",
    "YE": "Yemen",
    "EG": "Egypt",
    "SD": "Sudan",
    "LY": "Libya",
    "MA": "Morocco",
    "MR": "Mauritania",
    "TN": "Tunisia",
}


def setup_logging(output_dir, name):
    output_dir = Path(output_dir)
    log_dir = output_dir / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    fmt = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)

    fh = logging.FileHandler(log_dir / f'{name}.log')
    fh.setFormatter(fmt)
    root.addHandler(fh)


def discover_countries(output_dir):
    return sorted([d.name for d in Path(output_dir).iterdir()
                   if d.is_dir() and d.name in COUNTRY_CODE_TO_NAME])


def read_jsonl(file_path):
    data = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            data.append(json.loads(line.strip()))
    return data


def write_jsonl(file_path, data):
    with open(file_path, 'a', encoding='utf-8') as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')
