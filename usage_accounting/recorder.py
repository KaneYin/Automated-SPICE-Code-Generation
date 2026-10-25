"""Atomic per-call lifecycle. Each worker owns distinct task/trial paths."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from .components import message_components
from .providers import normalize
from .schema import SCHEMA_VERSION, atomic_json, fingerprint, validate_record

_CONTEXT = ContextVar('usage_call_context', default={})


def current_context():
    return dict(_CONTEXT.get())


@contextmanager
def call_context(phase, generation_index=None, diagnoses_generation_index=None, **metadata):
    token = _CONTEXT.set(dict(phase=phase, generation_index=generation_index,
                             diagnoses_generation_index=diagnoses_generation_index, **metadata))
    try:
        yield
    finally:
        _CONTEXT.reset(token)


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class Recorder:
    def __init__(self, run_dir, provider, run_id=None, task_id=None, trial_id=None,
                 model_digest=None, server_version=None, pricing=None, model_name=None,
                 tokenizer=None, billing_mode='local'):
        self.directory = Path(run_dir)
        self.run_id = run_id or self.directory.name
        self.provider = provider
        self.task_id, self.trial_id = task_id, trial_id
        self.model_digest, self.server_version = model_digest, server_version
        self.pricing = pricing
        self.model_name, self.tokenizer = model_name, tokenizer
        self.billing_mode = billing_mode
        self.sequence = 0

    def _path(self, record):
        return self.directory / record['record_path']

    def start(self, request, context=None, raw_path=None):
        context = dict(current_context() if context is None else context)
        task = context.get('task_id', self.task_id)
        trial = context.get('trial_id', self.trial_id)
        root = self.directory / 'usage' / 'calls' / f'task_{task}' / f'trial_{trial}'
        self.sequence += 1
        # Restarted workers must not overwrite an earlier transport call.
        while (root / f'call_{self.sequence:06d}.json').exists():
            self.sequence += 1
        relative = (root / f'call_{self.sequence:06d}.json').relative_to(self.directory)
        phase = context.get('phase', 'unknown')
        record = {'schema_version': SCHEMA_VERSION, 'run_id': self.run_id,
                  'call_id': fingerprint([self.run_id, str(relative)]),
                  'record_path': str(relative), 'task_id': task, 'trial_id': trial,
                  'sequence': self.sequence, 'phase': phase,
                  'phase_source': 'explicit' if phase != 'unknown' else 'unknown',
                  'generation_index': context.get('generation_index'),
                  'diagnoses_generation_index': context.get('diagnoses_generation_index'),
                  'provider': self.provider, 'requested_model': request.get('model'),
                  'model_digest': self.model_digest if self.model_name is None or request.get('model') == self.model_name else None,
                  'server_version': self.server_version, 'billing_mode': self.billing_mode,
                  'started_at': timestamp(), 'ended_at': None, 'status': 'started', 'error': None,
                  'request_fingerprint': fingerprint(request), 'raw_record_path':
                  str(Path(raw_path).relative_to(self.directory)) if raw_path is not None else None,
                  'settings': {k: v for k, v in request.items() if k not in {'messages', 'model'}},
                  'components': context.get('components') or message_components(request.get('messages', []), phase),
                  'transport_attempt_coverage': context.get('transport_attempt_coverage', 'one_invocation'),
                  **normalize(self.provider, {})}
        if str(request.get('model', '')).endswith(('-cloud', ':cloud')):
            record['billing_mode'] = 'unknown'
        # In a started record no response was available, including local API charges.
        if self.tokenizer is not None:
            self._attribute(record, request)
        atomic_json(self._path(record), validate_record(record))
        return record

    def _attribute(self, record, request):
        from .components import attribute_with_tokenizer
        if record.get('model_digest') != self.tokenizer.model_digest:
            record['component_attribution'] = {'quality': 'unavailable', 'unknown_reason': 'Tokenizer/model digest mismatch'}
            return
        attributed = attribute_with_tokenizer(request.get('messages', []), record['components'],
                                              self.tokenizer, record['usage']['input_tokens'])
        record.update(components=attributed.pop('components'), component_attribution=attributed)

    def finish(self, record, response=None, error=None, wall_seconds=None):
        result = dict(record)
        if response is not None:
            result.update(normalize(self.provider, response))
        result.update(status='error' if error is not None else 'completed',
                      error=str(error) if error is not None else None, ended_at=timestamp())
        result['timing']['client_wall_seconds'] = wall_seconds
        if result.get('component_attribution', {}).get('quality') == 'estimated':
            result['component_attribution'] = dict(result['component_attribution'], reconciliation_difference=(
                result['usage']['input_tokens'] - sum(s['tokens'] for s in result['components'] if s.get('tokens') is not None)
                if result['usage']['input_tokens'] is not None else None))
        atomic_json(self._path(result), validate_record(result))
        return result

    def interrupt_pending(self, task_id=None, trial_id=None):
        """Caller must establish worker exit before using this method."""
        count = 0
        for path in (self.directory / 'usage' / 'calls').rglob('*.json'):
            record = json.loads(path.read_text())
            if record['status'] != 'started':
                continue
            if task_id is not None and record['task_id'] != task_id:
                continue
            if trial_id is not None and record['trial_id'] != trial_id:
                continue
            record.update(status='interrupted', ended_at=timestamp(),
                          error='Worker exited before response accounting; server work/billing unknown')
            atomic_json(path, record)
            count += 1
        return count
