"""Decimal estimates using explicit, versioned assumptions, never commercial defaults."""
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from .schema import fingerprint


def number(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError('Invalid price/assumption: ' + str(value))
    if not result.is_finite() or result < 0:
        raise ValueError('Prices and assumptions must be finite and nonnegative')
    return result


def load_pricing(value=None):
    if value is None:
        value = {'currency': 'USD', 'api_rates': [], 'local': {}}
    elif isinstance(value, (str, Path)):
        value = json.loads(Path(value).read_text())
    if not isinstance(value, dict) or not isinstance(value.get('currency'), str) or not value['currency']:
        raise ValueError('Pricing requires one currency')
    if not isinstance(value.get('api_rates', []), list):
        raise ValueError('api_rates must be a list')
    seen = set()
    for rate in value.get('api_rates', []):
        for required in ('provider', 'model', 'effective_date'):
            if not isinstance(rate.get(required), str) or not rate[required]:
                raise ValueError('Rate requires ' + required)
        if rate.get('currency', value['currency']) != value['currency']:
            raise ValueError('Mixed currencies require separate reports')
        key = (rate['provider'], rate['model'])
        if key in seen:
            raise ValueError('Ambiguous provider/model rates')
        seen.add(key)
        for field in ('uncached_input_per_million', 'cached_input_per_million', 'cache_write_per_million', 'output_per_million'):
            if rate.get(field) is not None:
                number(rate[field])
    local = value.get('local', {})
    if not isinstance(local, dict):
        raise ValueError('local must be an object')
    for key in ('power_watts', 'electricity_per_kwh', 'machine_per_hour'):
        if local.get(key) is not None:
            number(local[key])
    if local and local.get('time_scope', 'completed_attempt_wall') != 'completed_attempt_wall':
        raise ValueError('Only completed_attempt_wall local cost scope is supported')
    return value


def api_cost(record, config):
    if record['provider'] == 'ollama' and record.get('billing_mode', 'local') == 'local':
        return {'known_subtotal': '0', 'complete': True, 'currency': config['currency'],
                'unknown_reason': None, 'label': 'Local API charge; compute excluded'}
    rates = [r for r in config.get('api_rates', []) if r['provider'] == record['provider']
             and r['model'] == record['requested_model']]
    if not rates:
        return {'known_subtotal': '0', 'complete': False, 'currency': config['currency'],
                'unknown_reason': 'No configured provider/model price'}
    rate = rates[0]
    usage = record['usage']
    subtotal = Decimal(0)
    missing = []
    for field, price in [('uncached_input_tokens', 'uncached_input_per_million'),
                         ('cached_input_tokens', 'cached_input_per_million'),
                         ('cache_write_tokens', 'cache_write_per_million'),
                         ('output_tokens', 'output_per_million')]:
        amount = usage.get(field)
        if amount == 0:
            continue
        if amount is None or rate.get(price) is None:
            missing.append(field)
        else:
            subtotal += Decimal(amount) * number(rate[price]) / Decimal(1000000)
    return {'known_subtotal': str(subtotal), 'complete': not missing, 'currency': config['currency'],
            'unknown_reason': ', '.join(missing) or None, 'effective_date': rate['effective_date']}


def estimate_costs(records, config=None, completed_seconds=None, accepted=None, completed_keys=None,
                   local_time_reason=None):
    config = load_pricing(config)
    costs = [api_cost(r, config) for r in records]
    subtotal = sum((Decimal(c['known_subtotal']) for c in costs), Decimal(0))
    completed = [api_cost(r, config) for r in records if completed_keys is not None and
                 (r.get('task_id'), r.get('trial_id')) in completed_keys]
    completed_total = sum((Decimal(c['known_subtotal']) for c in completed), Decimal(0))
    api = {'known_subtotal': str(subtotal), 'complete': all(c['complete'] for c in costs),
           'currency': config['currency'], 'known_calls': sum(c['complete'] for c in costs),
           'total_calls': len(records), 'completed_attempt_subtotal': str(completed_total),
           'active_or_unclassified_subtotal': str(subtotal - completed_total),
           'cost_per_accepted_circuit': str(completed_total / Decimal(accepted))
           if accepted and completed_keys is not None and all(c['complete'] for c in completed) else None}
    local = config.get('local', {})
    def local_estimate(kind, keys, denominator):
        if completed_seconds is None or any(local.get(k) is None for k in keys):
            return {'estimate': None, 'currency': config['currency'], 'complete': False,
                    'unknown_reason': local_time_reason or 'Required local assumptions/time unavailable'}
        value = number(completed_seconds)
        for k in keys:
            value *= number(local[k])
        return {'estimate': str(value / Decimal(denominator)), 'currency': config['currency'],
                'complete': True, 'time_scope': 'completed_attempt_wall',
                'label': 'Estimated, not measured energy; separate from other cost categories'}
    return {'api': api, 'electricity': local_estimate('electricity', ['power_watts', 'electricity_per_kwh'], 3600000),
            'machine': local_estimate('machine', ['machine_per_hour'], 3600),
            'pricing_config_hash': fingerprint(config), 'pricing_config': config}
