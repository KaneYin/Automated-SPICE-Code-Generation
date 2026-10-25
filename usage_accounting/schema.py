"""Versioned, JSON-safe records and atomic persistence."""
import hashlib
import json
import os
from pathlib import Path
import tempfile

SCHEMA_VERSION = 1
NORMALIZATION_VERSION = 1


def plain(value):
    if hasattr(value, 'model_dump'):
        return value.model_dump(mode='json')
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError('Unsupported record value: ' + type(value).__name__)


def canonical(value):
    return json.dumps(plain(value), sort_keys=True, separators=(',', ':'), allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(plain(value), indent=2, sort_keys=True, allow_nan=False) + '\n'
    fd, temp = tempfile.mkstemp(prefix='.' + path.name, suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def validate_record(record):
    if record.get('schema_version') != SCHEMA_VERSION:
        raise ValueError('Unsupported usage schema: ' + str(record.get('schema_version')))
    if not record.get('call_id') or not record.get('run_id'):
        raise ValueError('Usage identity missing')
    if record.get('status') not in {'started', 'completed', 'error', 'interrupted', 'unknown'}:
        raise ValueError('Invalid usage lifecycle')
    for key, value in record.get('usage', {}).items():
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
            raise ValueError('Invalid normalized token count: ' + key)
    usage = record.get('usage', {})
    p, c, w = (usage.get(k) for k in ('input_tokens', 'cached_input_tokens', 'cache_write_tokens'))
    if p is not None and ((c is not None and c > p) or (w is not None and w > p)
                          or c is not None and w is not None and c + w > p):
        raise ValueError('Invalid normalized cache subsets')
    if all(x is not None for x in (p, c, w)) and usage.get('uncached_input_tokens') != p-c-w:
        raise ValueError('Inconsistent normalized input categories')
    return record
