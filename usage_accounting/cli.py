"""Offline accounting: backfill, aggregate, or explicitly update a log block."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from .aggregate import export_run, load_calls, summary_markdown
from .components import attribute_with_tokenizer, load_tokenizer, message_components
from .providers import normalize
from .schema import SCHEMA_VERSION, atomic_json, canonical, fingerprint, validate_record
from .pricing import load_pricing


def infer_phase(request, manifest):
    messages = request.get('messages', [])
    assistants = sum(m.get('role') == 'assistant' for m in messages)
    images = any(m.get('images') or isinstance(m.get('content'), list) and
                 any(b.get('type') == 'image_url' for b in m['content']) for m in messages)
    # Only this known generation-only historical configuration supports inference.
    config = manifest.get('config', {})
    known = manifest.get('upstream', {}).get('revision') == '05542af46020e5c37d5a7e3ca79da9f24626e1c9'
    supported_tasks = config.get('tasks') and all(isinstance(t, int) and 1 <= t <= 28 for t in config['tasks'])
    if known and supported_tasks and images:
        return 'waveform_analysis', None, None, 'inferred'
    if known and supported_tasks and len(messages) >= 2 and messages[0].get('role') == 'system':
        return ('repair_generation' if assistants else 'initial_generation', assistants, None, 'inferred')
    return 'unknown', None, None, 'unknown'


def backfill(directory, pricing=None, tokenizer=None):
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text())
    if manifest.get('upstream', {}).get('revision') != '05542af46020e5c37d5a7e3ca79da9f24626e1c9':
        raise ValueError('Backfill supports saved native Ollama Pro runs at the pinned revision only; use aggregate for live telemetry')
    run_id = manifest.get('run_id') or 'historical-' + fingerprint(manifest)[:24]
    existing = {r['raw_record_path']: r for r in load_calls(directory) if r.get('raw_record_path')}
    previous_generation = {}
    # No raw/manifests/results/workspaces are modified, including on repeated calls.
    for path in sorted((directory / 'api_calls').rglob('*.json')):
        raw = json.loads(path.read_text())
        request = raw.get('request', {})
        relative = str(path.relative_to(directory))
        if relative in existing:
            prior = existing[relative]
            if prior['request_fingerprint'] != fingerprint(request):
                raise ValueError('Raw request conflicts with existing call: ' + relative)
            if prior.get('raw_record_fingerprint') is not None and prior['raw_record_fingerprint'] != fingerprint(raw):
                raise ValueError('Raw response conflicts with existing call: ' + relative)
            if prior.get('raw_record_fingerprint') is None:
                normalized = normalize(prior['provider'], raw.get('response'))
                if prior['status'] in {'started', 'interrupted', 'unknown'} and raw.get('response') is not None:
                    # Recover provider evidence saved before final accounting failed.
                    prior.update(normalized, status='completed', error=None,
                                 raw_record_fingerprint=fingerprint(raw))
                    prior['timing']['client_wall_seconds'] = raw.get('wall_seconds')
                    atomic_json(directory / prior['record_path'], validate_record(prior))
                elif raw.get('response') is not None and prior['usage'] != normalized['usage']:
                    raise ValueError('Raw response usage conflicts with existing call: ' + relative)
            if prior['phase'] in {'initial_generation', 'repair_generation'} and prior['status'] == 'completed':
                previous_generation[(prior['task_id'], prior['trial_id'])] = prior['generation_index']
            # Explicit live records are authoritative. Never create a second,
            # inferred record for a request already measured live.
            continue
        phase, generation, diagnosis, source = infer_phase(request, manifest)
        task_match = re.search(r'(?:^|/)task_(\d+)(?:/|$)', relative)
        trial_match = re.search(r'(?:^|/)trial_(\d+)(?:/|$)', relative)
        task = int(task_match[1]) if task_match else None
        trial = int(trial_match[1]) if trial_match else None
        if phase == 'waveform_analysis':
            diagnosis = previous_generation.get((task, trial))
        call_id = fingerprint([run_id, relative])
        target = Path('usage/calls') / f'task_{task}' / f'trial_{trial}' / (path.stem + '.json')
        response = raw.get('response')
        start = raw.get('started_at')
        started_at = datetime.fromtimestamp(start, timezone.utc).isoformat() if isinstance(start, (int, float)) else None
        end = start + raw['wall_seconds'] if isinstance(start, (int, float)) and isinstance(raw.get('wall_seconds'), (int, float)) else None
        model = manifest.get('model', {})
        same_model = request.get('model') in {model.get('name'), model.get('model')}
        record = {'schema_version': SCHEMA_VERSION, 'run_id': run_id, 'call_id': call_id,
                  'record_path': str(target), 'task_id': task, 'trial_id': trial,
                  'sequence': int(re.search(r'(\d+)$', path.stem)[1]) if re.search(r'(\d+)$', path.stem) else None,
                  'phase': phase, 'phase_source': source, 'generation_index': generation,
                  'diagnoses_generation_index': diagnosis,
                  'provider': 'ollama', 'requested_model': request.get('model'),
                  'model_digest': model.get('digest') if same_model else None,
                  'server_version': manifest.get('ollama_version'), 'started_at': started_at,
                  'ended_at': datetime.fromtimestamp(end, timezone.utc).isoformat() if end else None,
                  'status': 'error' if raw.get('error') else 'completed' if response is not None else 'unknown',
                  'error': raw.get('error'), 'request_fingerprint': fingerprint(request),
                  'raw_record_path': relative, 'raw_record_fingerprint': fingerprint(raw),
                  'settings': {k: v for k, v in request.items() if k not in {'messages', 'model'}},
                  'components': message_components(request.get('messages', []), phase),
                  'transport_attempt_coverage': 'one_invocation',
                  'billing_mode': 'local' if _local_endpoint(manifest.get('config', {}).get('endpoint', ''), request.get('model', '')) else 'unknown',
                  **normalize('ollama', response)}
        record['timing']['client_wall_seconds'] = raw.get('wall_seconds')
        if tokenizer is not None and record['model_digest'] == tokenizer.model_digest:
            attributed = attribute_with_tokenizer(request.get('messages', []), record['components'], tokenizer,
                                                  record['usage']['input_tokens'])
            record.update(components=attributed.pop('components'), component_attribution=attributed)
        if phase in {'initial_generation', 'repair_generation'} and response is not None:
            previous_generation[(task, trial)] = generation
        validate_record(record)
        dest = directory / target
        if dest.exists():
            if canonical(json.loads(dest.read_text())) != canonical(record):
                raise ValueError('Backfill conflicts with existing call: ' + str(dest))
        else:
            atomic_json(dest, record)
    return export_run(directory, pricing, tokenizer=tokenizer)


def _local_endpoint(endpoint, model):
    from urllib.parse import urlparse
    return urlparse(endpoint).hostname in {'127.0.0.1', 'localhost', '::1'} and not model.endswith(('-cloud', ':cloud'))


def update_log(log, run_name, summary):
    """Explicitly upsert only a run's marked block; preserve other bytes."""
    path = Path(log)
    text = path.read_text()
    if '\n' in run_name or '-->' in run_name:
        raise ValueError('Invalid run name')
    start = '<!-- usage-accounting:' + run_name + ':start -->'
    end = '<!-- usage-accounting:' + run_name + ':end -->'
    block = start + '\n' + summary_markdown(summary).replace('## Usage accounting', '### Usage accounting', 1) + end
    if text.count(start) != text.count(end) or text.count(start) > 1:
        raise ValueError('Malformed or duplicate generated usage block')
    if start in text:
        left, rest = text.split(start, 1)
        _, right = rest.split(end, 1)
        updated = left + block + right
    else:
        matches = list(re.finditer(r'^## Run[^\n]*: ' + re.escape(run_name) + r'\s*$', text, re.M))
        if len(matches) != 1:
            raise ValueError('Expected one matching run heading for ' + run_name)
        next_heading = re.search(r'^## ', text[matches[0].end():], re.M)
        index = matches[0].end() + next_heading.start() if next_heading else len(text)
        updated = text[:index] + block + '\n\n' + text[index:]
    # Only explicit log-update writes outside usage/. Preserve all surrounding text.
    import os
    import tempfile
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as handle:
            handle.write(updated)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['backfill', 'aggregate', 'log-update'])
    parser.add_argument('run', type=Path)
    parser.add_argument('--pricing', type=Path)
    parser.add_argument('--log', type=Path)
    parser.add_argument('--run-name')
    parser.add_argument('--tokenizer-config', type=Path, help='Optional local tokenizer identity/file configuration (estimates only)')
    args = parser.parse_args()
    pricing = load_pricing(args.pricing) if args.pricing else None
    if args.command == 'backfill':
        summary = backfill(args.run, pricing, load_tokenizer(args.tokenizer_config))
    else:
        summary = export_run(args.run, pricing, tokenizer=load_tokenizer(args.tokenizer_config))
    if args.command == 'log-update':
        if args.log is None:
            parser.error('log-update requires --log')
        update_log(args.log, args.run_name or args.run.name, summary)
    print(summary_markdown(summary))


if __name__ == '__main__':
    main()
