"""Rebuildable reports from canonical per-call records."""
from collections import Counter, defaultdict
import csv
from decimal import Decimal
import json
from pathlib import Path
from .providers import FIELDS
from .components import attribute_with_tokenizer
from .pricing import api_cost, estimate_costs, load_pricing
from .schema import atomic_json, canonical, fingerprint, validate_record


def load_calls(directory):
    calls = {}
    for path in sorted((Path(directory) / 'usage' / 'calls').rglob('*.json')):
        record = validate_record(json.loads(path.read_text()))
        existing = calls.get(record['call_id'])
        if existing is not None and canonical(existing) != canonical(record):
            raise ValueError('Conflicting usage call ID: ' + record['call_id'])
        calls[record['call_id']] = record
    return list(calls.values())


def summarize(records):
    usage, coverage = {}, {}
    for field in FIELDS:
        known = [r['usage'].get(field) for r in records if r['usage'].get(field) is not None]
        usage[field] = sum(known)
        coverage[field] = {'known_calls': len(known), 'total_calls': len(records),
                           'complete': len(known) == len(records)}
    eligible = [r for r in records if r['usage'].get('input_tokens') is not None and
                r['usage'].get('cached_input_tokens') is not None]
    p = sum(r['usage']['input_tokens'] for r in eligible)
    c = sum(r['usage']['cached_input_tokens'] for r in eligible)
    total_p = usage['input_tokens']
    cache = {'token_reuse_rate': c / p if p else None,
             'request_hit_fraction': sum(r['usage']['cached_input_tokens'] > 0 for r in eligible) / len(eligible) if eligible else None,
             'eligible_calls': len(eligible), 'total_calls': len(records),
             'input_token_coverage': p / total_p if total_p else None,
             'complete': len(eligible) == len(records) and coverage['input_tokens']['complete']}
    return {'calls': len(records), 'usage': usage, 'coverage': coverage, 'cache': cache,
            'statuses': dict(Counter(r['status'] for r in records)),
            'validation_errors': sum(len(r.get('validation_errors', [])) for r in records)}


def aggregate(records, pricing=None, results=None):
    pricing = load_pricing(pricing)
    result = summarize(records)
    for key, getter in [('by_stage', lambda r: r['phase']),
                        ('by_task', lambda r: str(r['task_id'])),
                        ('by_model', lambda r: r['provider'] + '/' + str(r['requested_model']) + '/' + str(r.get('model_digest')))]:
        groups = defaultdict(list)
        for record in records:
            groups[getter(record)].append(record)
        result[key] = {}
        for name, items in sorted(groups.items()):
            group = summarize(items)
            group['api_cost'] = estimate_costs(items, pricing)['api']
            result[key][name] = group
    rows = (results or {}).get('results', [])
    keys = {(r['task_id'], r.get('trial', r.get('trial_id'))) for r in rows}
    seconds = sum(r['wall_seconds'] for r in rows) if rows else None
    time_reason = None
    # Attempt wall sums are valid for the explicitly sequential launcher. Other
    # runners must supply nonoverlapping attempt intervals or stay unknown.
    if rows and any('started_at' in r or 'ended_at' in r for r in rows):
        intervals = [(r.get('started_at'), r.get('ended_at')) for r in rows]
        if any(not isinstance(a, (int, float)) or not isinstance(b, (int, float)) or b < a
               for a, b in intervals):
            seconds, time_reason = None, 'Invalid/missing attempt intervals'
        else:
            intervals.sort()
            merged = []
            for a, b in intervals:
                if merged and a <= merged[-1][1]:
                    merged[-1][1] = max(merged[-1][1], b)
                else:
                    merged.append([a, b])
            seconds = sum(b-a for a, b in merged)
    accepted = sum(r['status'] == 'passed' for r in rows)
    result['costs'] = estimate_costs(records, pricing, seconds, accepted, keys if results is not None else None,
                                     local_time_reason=time_reason)
    result['schema_version'] = 1
    result['snapshot_partial'] = (any(r['status'] == 'started' for r in records) or
                                  results is not None and results.get('finished_attempts', len(rows)) < results.get('planned_attempts', len(rows)))
    return result


def _csv(path, rows, fields):
    # CSV is derived; readers should use canonical atomic JSON for live snapshots.
    import io
    import os
    import tempfile
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    fd, name = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as handle:
            handle.write(output.getvalue())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def export_run(directory, pricing=None, tokenizer=None):
    directory = Path(directory)
    if pricing is None and (directory / 'manifest.json').exists():
        manifest = json.loads((directory / 'manifest.json').read_text())
        pricing = manifest.get('usage_pricing')
    records = load_calls(directory)
    if tokenizer is not None:
        for record in records:
            if record.get('model_digest') != tokenizer.model_digest or not record.get('raw_record_path'):
                continue
            raw = json.loads((directory / record['raw_record_path']).read_text())
            if fingerprint(raw['request']) != record['request_fingerprint']:
                raise ValueError('Request changed since component recording')
            attribution = attribute_with_tokenizer(raw['request'].get('messages', []), record['components'],
                                                   tokenizer, record['usage']['input_tokens'])
            record.update(components=attribution.pop('components'), component_attribution=attribution)
    results = json.loads((directory / 'results.json').read_text()) if (directory / 'results.json').exists() else None
    summary = aggregate(records, pricing, results)
    summary['component_attribution'] = {
        'estimated_calls': sum(any(s.get('quality') == 'estimated' for s in r.get('components', [])) for r in records),
        'total_calls': len(records),
        'tokenizer': tokenizer.provenance if tokenizer is not None else None,
        'exact_evaluated_prompt_mapping': False,
    }
    parts = defaultdict(list)
    for record in records:
        for component in record.get('components', []):
            parts[component['category']].append(component)
    summary['by_component'] = {}
    for category, items in sorted(parts.items()):
        known = [p['tokens'] for p in items if p.get('tokens') is not None]
        summary['by_component'][category] = {
            'tokens_estimated_subtotal': sum(known) if known else None,
            'known_spans': len(known), 'total_spans': len(items),
            'characters': sum(p['end']-p['start'] for p in items if 'start' in p),
            'quality': 'estimated' if known else 'unavailable',
        }
    target = directory / 'usage'
    target.mkdir(parents=True, exist_ok=True)
    # Immutable hash-keyed estimates preserve both earlier prices and earlier
    # usage snapshots. The top-level files are convenience views of the latest.
    estimate = Path('estimates') / fingerprint(load_pricing(pricing)) / fingerprint([records, results, summary])
    summary['estimate_snapshot'] = str(estimate / 'summary.json')
    component_snapshot = [{'call_id': r['call_id'], 'components': r.get('components', []),
                           'attribution': r.get('component_attribution')} for r in records]
    for name, data in [('summary.json', summary), ('pricing_snapshot.json', load_pricing(pricing)),
                       ('components.json', component_snapshot)]:
        archive = target / estimate / name
        if archive.exists() and canonical(json.loads(archive.read_text())) != canonical(data):
            raise ValueError('Conflicting immutable estimate: ' + str(archive))
        if not archive.exists():
            atomic_json(archive, data)
        atomic_json(target / name, data)
    fields = ['call_id', 'task_id', 'trial_id', 'phase', 'phase_source', 'provider', 'requested_model', 'status', *FIELDS,
              'token_cache_reuse_rate', 'uncached_prefill_tokens_per_second', 'decode_tokens_per_second',
              'api_cost_known_subtotal', 'api_cost_complete', 'currency']
    rows = []
    for record in records:
        usage = record['usage']
        timing = record['timing']
        p, c = usage['input_tokens'], usage['cached_input_tokens']
        row = {k: record.get(k) for k in fields if k in record}
        row.update(usage)
        cost = api_cost(record, load_pricing(pricing))
        row.update(api_cost_known_subtotal=cost['known_subtotal'], api_cost_complete=cost['complete'], currency=cost['currency'])
        row['token_cache_reuse_rate'] = c / p if p and c is not None else None
        row['uncached_prefill_tokens_per_second'] = (p-c) / timing['prefill_seconds'] if p is not None and c is not None and timing.get('prefill_seconds') else None
        row['decode_tokens_per_second'] = usage['output_tokens'] / timing['decode_seconds'] if usage['output_tokens'] is not None and timing.get('decode_seconds') else None
        rows.append(row)
    _csv(target / 'calls.csv', rows, fields)
    for key, name in [('by_stage', 'phase'), ('by_task', 'task_id')]:
        grouped = [{name: group, 'calls': value['calls'], **value['usage'],
                    'cache_reuse_rate': value['cache']['token_reuse_rate'],
                    'cache_eligible_calls': value['cache']['eligible_calls'],
                    'api_cost_known_subtotal': value['api_cost']['known_subtotal'],
                    'api_cost_complete': value['api_cost']['complete'], 'currency': value['api_cost']['currency']}
                   for group, value in summary[key].items()]
        _csv(target / (key + '.csv'), grouped, [name, 'calls', *FIELDS, 'cache_reuse_rate', 'cache_eligible_calls',
                                             'api_cost_known_subtotal', 'api_cost_complete', 'currency'])
    components = []
    for record in records:
        for component in record.get('components', []):
            components.append({'call_id': record['call_id'], **{k: component.get(k) for k in
                ['message_index', 'category', 'start', 'end', 'tokens', 'quality', 'method', 'tokenizer']}})
    if components:
        _csv(target / 'components.csv', components, ['call_id', 'message_index', 'category', 'start', 'end', 'tokens', 'quality', 'method', 'tokenizer'])
        _csv(target / 'by_component.csv', [{'category': k, **v} for k, v in summary['by_component'].items()],
             ['category', 'tokens_estimated_subtotal', 'known_spans', 'total_spans', 'characters', 'quality'])
    return summary


def summary_markdown(summary):
    u, cache, cost = summary['usage'], summary['cache'], summary['costs']
    ratio = f"{cache['token_reuse_rate']:.2%}" if cache['token_reuse_rate'] is not None else 'unknown'
    complete = all(summary['coverage'][k]['complete'] for k in ('input_tokens', 'output_tokens'))
    def metric(key):
        coverage = summary['coverage'][key]
        return f"{u[key]:,}" + ('' if coverage['complete'] else f" (observed subtotal; {coverage['known_calls']}/{coverage['total_calls']} calls)")
    lines = ['## Usage accounting', '',
             f"Calls: {summary['calls']}. Token totals: {'complete' if complete else 'partial observed subtotal'}.",
             f"Input: {metric('input_tokens')}; cached: {metric('cached_input_tokens')}; uncached: {metric('uncached_input_tokens')}; output: {metric('output_tokens')}.",
             f"Prompt/KV cache token reuse rate: {ratio}; eligible calls: {cache['eligible_calls']}/{cache['total_calls']}.",
             f"API cost known subtotal: {cost['api']['known_subtotal']} {cost['api']['currency']} ({'complete' if cost['api']['complete'] else 'partial; unknown remainder'}).",
             f"Electricity estimate: {cost['electricity']['estimate'] or 'unknown'}; machine estimate: {cost['machine']['estimate'] or 'unknown'}.",
             'Component tokens are unavailable or explicitly estimated per string; character spans are not token counts. Chat framing and image-token attribution remain unallocated.', '',
             'Stage token values below are observed subtotals; cache coverage is shown separately.', '',
             '| Stage | Calls | Input | Cached input | Output | Cache eligible calls | API cost subtotal |',
             '| --- | ---: | ---: | ---: | ---: | ---: | --- |']
    for phase, group in summary['by_stage'].items():
        v = group['usage']
        g = group['api_cost']
        lines.append(f"| {phase} | {group['calls']} | {v['input_tokens']:,} | {v['cached_input_tokens']:,} | {v['output_tokens']:,} | {group['cache']['eligible_calls']} | {g['known_subtotal']} {g['currency']} ({'complete' if g['complete'] else 'partial'}) |")
    if summary.get('by_component'):
        lines += ['', '| Prompt component | Estimated tokens (observed subtotal) | Measured spans |',
                  '| --- | ---: | ---: |']
        for category, value in summary['by_component'].items():
            tokens = value['tokens_estimated_subtotal']
            lines.append(f"| {category} | {tokens if tokens is not None else 'unknown'} | {value['known_spans']}/{value['total_spans']} |")
    return '\n'.join(lines) + '\n'
