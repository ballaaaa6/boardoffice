import json
from pathlib import Path


def load_action_set(path: str | Path) -> dict:
    path = Path(path)
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema') != 'gds_action_set_v1':
        raise ValueError(f'Unsupported action-set schema: {data.get("schema")!r}')
    if not data.get('action_set_id') or not isinstance(data.get('actions'), dict):
        raise ValueError('Invalid action set')
    return data
