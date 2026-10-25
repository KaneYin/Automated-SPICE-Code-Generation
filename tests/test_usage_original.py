"""Offline transport invariants for the original runner (no simulator/SDK needed)."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from usage_accounting.legacy import recorded_call
from usage_accounting.recorder import Recorder

ROOT = Path(__file__).resolve().parents[1]


class LegacyIntegrationTests(unittest.TestCase):
    def test_all_five_calls_preserve_payload_and_identify_stage(self):
        tree = ast.parse((ROOT / 'gpt_run.py').read_text())
        calls = sorted([node for node in ast.walk(tree)
                        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == 'recorded_call'], key=lambda node: node.lineno)
        self.assertEqual(len(calls), 5)
        expected_phases = ['initial_generation', 'initial_generation',
                           'repair_generation', 'repair_generation', 'retrieval']
        messages = [{'role': 'user', 'content': 'unchanged prompt'}]
        for index, (node, phase) in enumerate(zip(calls, expected_phases)):
            received = []
            response = object()
            def dispatch(**kwargs):
                received.append(kwargs)
                return response
            contexts = []
            def record(recorder, callback, context, **request):
                contexts.append(context)
                return recorded_call(None, callback, context, **request)
            namespace = {
                'recorded_call': record, 'usage_recorder': None,
                'ollama': SimpleNamespace(chat=dispatch),
                'client': SimpleNamespace(chat=SimpleNamespace(
                    completions=SimpleNamespace(create=dispatch))),
                'args': SimpleNamespace(model='model', temperature=0.5),
                'messages': messages, 'task_id': 4, 'it': 2,
                'code_id': 1, 'trial_id': 2,
            }
            result = eval(compile(ast.Expression(node), '<transport>', 'eval'), namespace)
            expected = {'model': 'model', 'messages': messages}
            if index in (0, 2):
                expected['options'] = {'temperature': 0.5, 'top_p': 1.0}
            else:
                expected['temperature'] = 0.5
            self.assertIs(result, response)
            self.assertEqual(received, [expected])
            self.assertIs(received[0]['messages'], messages)
            self.assertEqual(contexts[0]['phase'], phase)
            self.assertEqual(contexts[0]['task_id'], 4)
            self.assertEqual(contexts[0]['trial_id'], 2)
            self.assertEqual(contexts[0]['generation_index'],
                             None if phase == 'retrieval' else 0 if index < 2 else 1)

    def test_provider_responses_retained_without_mutating_caller_object(self):
        responses = {
            'ollama': {'model': 'qwen', 'prompt_eval_count': 12,
                       'prompt_eval_cached_count': 5, 'eval_count': 3,
                       'message': {'role': 'assistant', 'content': 'code'}},
            'openai': {'model': 'gpt', 'choices': [], 'usage': {
                'prompt_tokens': 12, 'completion_tokens': 3, 'total_tokens': 15,
                'prompt_tokens_details': {'cached_tokens': 5}}},
            'deepseek': {'model': 'deepseek-chat', 'choices': [], 'usage': {
                'prompt_tokens': 12, 'completion_tokens': 3, 'total_tokens': 15,
                'prompt_cache_hit_tokens': 5}},
        }
        for provider, response in responses.items():
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as directory:
                recorder = Recorder(directory, provider)
                model = SimpleNamespace(model_dump=lambda mode: response)
                messages = [{'role': 'user', 'content': 'prompt'}]
                result = recorded_call(recorder, lambda **kwargs: model,
                                       {'phase': 'initial_generation', 'generation_index': 0,
                                        'task_id': 1, 'trial_id': 0},
                                       model='model', messages=messages)
                self.assertIs(result, model)
                raw_paths = list((Path(directory) / 'api_calls').rglob('*.json'))
                records = list((Path(directory) / 'usage' / 'calls').rglob('*.json'))
                self.assertEqual(len(raw_paths), 1)
                self.assertEqual(len(records), 1)
                raw = json.loads(raw_paths[0].read_text())
                record = json.loads(records[0].read_text())
                self.assertEqual(raw['response'], response)
                self.assertEqual(raw['request']['messages'], messages)
                self.assertEqual(record['status'], 'completed')
                self.assertEqual(record['transport_attempt_coverage'],
                                 'one_invocation' if provider == 'ollama' else
                                 'sdk_internal_retries_unknown')
                self.assertTrue((Path(directory) / 'usage' / 'summary.json').exists())

    def test_transport_exception_is_same_object_and_attempt_is_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = Recorder(directory, 'ollama')
            timeout = TimeoutError('model timeout')
            def dispatch(**request):
                raise timeout
            with self.assertRaises(TimeoutError) as caught:
                recorded_call(recorder, dispatch, {'phase': 'repair_generation',
                              'task_id': 1, 'trial_id': 0, 'generation_index': 1},
                              model='qwen', messages=[])
            self.assertIs(caught.exception, timeout)
            record = json.loads(next((Path(directory) / 'usage' / 'calls').rglob('*.json')).read_text())
            self.assertEqual(record['status'], 'error')
            self.assertIsNone(record['usage']['input_tokens'])

    def test_pre_dispatch_persistence_failure_prevents_transport(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = Recorder(directory, 'ollama')
            sent = []
            with patch('usage_accounting.legacy.atomic_json', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    recorded_call(recorder, lambda **request: sent.append(request),
                                  {'phase': 'initial_generation'}, model='qwen')
            self.assertEqual(sent, [])


if __name__ == '__main__':
    unittest.main()
