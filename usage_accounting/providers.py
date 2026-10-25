"""Normalize known provider semantics, preserving missing/invalid evidence."""
import math
from .schema import NORMALIZATION_VERSION, plain

FIELDS = ('input_tokens', 'output_tokens', 'cached_input_tokens', 'cache_write_tokens',
          'uncached_input_tokens', 'reasoning_tokens', 'image_tokens', 'provider_total_tokens')


def normalize(provider, response):
    response = plain(response or {})
    usage = dict.fromkeys(FIELDS)
    errors = []
    timings = {'client_wall_seconds': None, 'source': provider,
               'original_unit': 'nanoseconds' if provider == 'ollama' else None}

    def count(name, value):
        if value is not None:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                errors.append('Invalid ' + name)
                return
            usage[name] = value

    if provider == 'ollama':
        raw = {k: v for k, v in response.items() if k.endswith('_count') or k.endswith('_duration')}
        for key, native in [('input_tokens', 'prompt_eval_count'), ('output_tokens', 'eval_count'),
                            ('cached_input_tokens', 'prompt_eval_cached_count')]:
            count(key, response.get(native))
        # Ollama does not expose a separately charged cache-write token category.
        usage['cache_write_tokens'] = 0
        for label, field in [('server_total_seconds', 'total_duration'), ('load_seconds', 'load_duration'),
                             ('prefill_seconds', 'prompt_eval_duration'), ('decode_seconds', 'eval_duration')]:
            value = response.get(field)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0:
                timings[label] = value / 1e9
            elif value is not None:
                errors.append('Invalid ' + field)
        finish = response.get('done_reason')
    elif provider in {'openai', 'openai_compatible', 'deepseek'}:
        raw = response.get('usage') or {}
        for key, native in [('input_tokens', 'prompt_tokens'), ('output_tokens', 'completion_tokens'),
                            ('provider_total_tokens', 'total_tokens')]:
            count(key, raw.get(native))
        details = raw.get('prompt_tokens_details') or {}
        out = raw.get('completion_tokens_details') or {}
        count('reasoning_tokens', out.get('reasoning_tokens'))
        count('image_tokens', details.get('image_tokens'))
        if provider == 'openai':
            count('cached_input_tokens', details.get('cached_tokens'))
            count('cache_write_tokens', details.get('cache_write_tokens', 0))
        elif provider == 'deepseek':
            count('cached_input_tokens', raw.get('prompt_cache_hit_tokens'))
            # DeepSeek exposes cache hits and misses; writes are not a separate input bucket here.
            usage['cache_write_tokens'] = 0
        # An arbitrary compatible endpoint has no established cache billing semantics.
        choices = response.get('choices') or []
        finish = choices[0].get('finish_reason') if choices else None
    else:
        raw = response.get('usage') or {}
        finish = None
        errors.append('Unsupported provider semantics: ' + provider)

    p, c, w = (usage[k] for k in ('input_tokens', 'cached_input_tokens', 'cache_write_tokens'))
    if p is not None and ((c is not None and c > p) or
                          (w is not None and w > p) or
                          (c is not None and w is not None and c + w > p)):
        errors.append('Cached read/write counts exceed input tokens')
        usage['cached_input_tokens'] = usage['cache_write_tokens'] = None
        c = w = None
    if provider == 'deepseek':
        miss = (response.get('usage') or {}).get('prompt_cache_miss_tokens')
        if miss is not None and (isinstance(miss, bool) or not isinstance(miss, int) or miss < 0
                                 or p is not None and c is not None and miss + c != p):
            errors.append('Inconsistent DeepSeek cache miss count')
            usage['cached_input_tokens'] = None
            c = None
    if p is not None and c is not None and w is not None:
        usage['uncached_input_tokens'] = p - c - w
    for subset, total in [('reasoning_tokens', 'output_tokens'), ('image_tokens', 'input_tokens')]:
        if usage[subset] is not None and usage[total] is not None and usage[subset] > usage[total]:
            errors.append(subset + ' exceeds ' + total)
            usage[subset] = None
    return {'usage': usage, 'raw_usage': raw, 'timing': timings, 'finish_reason': finish,
            'normalization_version': NORMALIZATION_VERSION, 'validation_errors': errors,
            'returned_model': response.get('model'), 'provider_request_id': response.get('id')}
