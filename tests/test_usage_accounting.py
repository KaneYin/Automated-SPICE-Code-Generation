"""Accounting invariants and portable baseline reconciliation; no provider calls."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import subprocess
import sys
from types import SimpleNamespace
import unittest

from usage_accounting.aggregate import aggregate, export_run, load_calls, summarize, summary_markdown
from usage_accounting.cli import backfill, infer_phase, update_log
from usage_accounting.components import attribute_with_tokenizer, message_components, validate_spans
from usage_accounting.pricing import api_cost, estimate_costs, load_pricing
from usage_accounting.providers import normalize
from usage_accounting.recorder import Recorder
from usage_accounting.schema import atomic_json, fingerprint

FIXTURE = Path(__file__).parent / 'fixtures/usage/historical_metadata.json'


def record(provider='ollama', response=None, **extra):
    return dict(provider=provider, requested_model='model', task_id=1, trial_id=0,
                status='completed', phase='initial_generation', model_digest=None,
                **normalize(provider, response or {}), **extra)


class NormalizationTests(unittest.TestCase):
    def test_missing_zero_and_weighted_cache(self):
        a = record(response={'prompt_eval_count': 100, 'prompt_eval_cached_count': 90, 'eval_count': 10})
        b = record(response={'prompt_eval_count': 900, 'prompt_eval_cached_count': 0, 'eval_count': 10})
        missing = record(response={'prompt_eval_count': 100, 'eval_count': 10})
        s = summarize([a, b, missing])
        self.assertEqual(s['cache']['token_reuse_rate'], .09)
        self.assertEqual(s['cache']['eligible_calls'], 2)
        self.assertAlmostEqual(s['cache']['input_token_coverage'], 1000/1100)
        self.assertFalse(s['cache']['complete'])
        self.assertIsNone(missing['usage']['cached_input_tokens'])
        self.assertEqual(b['usage']['cached_input_tokens'], 0)
        self.assertIsNone(summarize([])['cache']['token_reuse_rate'])
        self.assertIsNone(summarize([record(response={'prompt_eval_count': 0, 'prompt_eval_cached_count': 0})])['cache']['token_reuse_rate'])
        report = summary_markdown(aggregate([missing]))
        self.assertIn('cached: 0 (observed subtotal; 0/1 calls)', report)

    def test_invalid_counts_and_subsets_are_unknown(self):
        for invalid in [-1, True, 1.5, '100']:
            r = normalize('ollama', {'prompt_eval_count': invalid})
            self.assertIsNone(r['usage']['input_tokens'])
            self.assertTrue(r['validation_errors'])
        r = normalize('openai', {'usage': {'prompt_tokens': 5,
                          'prompt_tokens_details': {'cache_write_tokens': 6}}})
        self.assertIsNone(r['usage']['cache_write_tokens'])
        r = normalize('ollama', {'prompt_eval_count': 10, 'prompt_eval_cached_count': 11,
                                 'prompt_eval_duration': float('inf')})
        self.assertIsNone(r['usage']['cached_input_tokens'])
        self.assertNotIn('prefill_seconds', r['timing'])
        self.assertEqual(len(r['validation_errors']), 2)

    def test_provider_semantics_and_timing(self):
        r = normalize('ollama', {'prompt_eval_count': 20, 'prompt_eval_cached_count': 15,
                                'eval_count': 8, 'prompt_eval_duration': 1000000000,
                                'eval_duration': 2000000000})
        self.assertEqual(r['usage']['uncached_input_tokens'], 5)
        self.assertEqual(r['timing']['prefill_seconds'], 1)
        compatible = normalize('openai_compatible', {'usage': {'prompt_tokens': 10,
                                   'prompt_tokens_details': {'cached_tokens': 8}}})
        self.assertIsNone(compatible['usage']['cached_input_tokens'])
        bad = normalize('deepseek', {'usage': {'prompt_tokens': 10, 'prompt_cache_hit_tokens': 4,
                                               'prompt_cache_miss_tokens': 9}})
        self.assertIsNone(bad['usage']['cached_input_tokens'])


class PersistenceTests(unittest.TestCase):
    def test_lifecycle_empty_error_interruption_and_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = Recorder(tmp, 'ollama', task_id=1, trial_id=0)
            a = r.start({'model': 'qwen', 'messages': []})
            r.finish(a, response={'prompt_eval_count': 12, 'eval_count': 2, 'message': {'content': ''}})
            b = r.start({'model': 'qwen', 'messages': []})
            r.finish(b, error=TimeoutError('timeout'))
            r.start({'model': 'qwen', 'messages': []})
            self.assertEqual(r.interrupt_pending(1, 0), 1)
            self.assertEqual(r.interrupt_pending(1, 0), 0)
            restarted = Recorder(tmp, 'ollama', task_id=1, trial_id=0)
            restarted.start({'model': 'qwen', 'messages': []})
            calls = load_calls(tmp)
            self.assertEqual(len(calls), 4)
            self.assertEqual([c['status'] for c in calls], ['completed', 'error', 'interrupted', 'started'])
            self.assertIsNone(calls[2]['usage']['input_tokens'])
            self.assertTrue(aggregate(calls)['snapshot_partial'])

    def test_duplicate_conflict_and_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            recorder = Recorder(tmp, 'ollama')
            r = recorder.start({'model': 'model'})
            extra = Path(tmp)/'usage/calls/duplicate.json'
            atomic_json(extra, r)
            self.assertEqual(len(load_calls(tmp)), 1)
            atomic_json(extra, dict(r, status='interrupted'))
            with self.assertRaisesRegex(ValueError, 'Conflicting'):
                load_calls(tmp)
            atomic_json(extra, dict(r, schema_version=99))
            with self.assertRaisesRegex(ValueError, 'Unsupported'):
                load_calls(tmp)

    def test_atomic_read_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'value.json'
            atomic_json(path, {'number': 0})
            def writer():
                for i in range(40):
                    atomic_json(path, {'number': i})
            thread = threading.Thread(target=writer)
            thread.start()
            while thread.is_alive():
                self.assertIsInstance(json.loads(path.read_text())['number'], int)
            thread.join()


class CostTests(unittest.TestCase):
    def setUp(self):
        self.config = {'currency': 'USD', 'api_rates': [{'provider': 'openai', 'model': 'model',
            'effective_date': 'test-only', 'uncached_input_per_million': '2',
            'cached_input_per_million': '1', 'cache_write_per_million': '3', 'output_per_million': '4'}],
            'local': {'power_watts': 100, 'electricity_per_kwh': '.15', 'machine_per_hour': '1.5'}}
        self.r = record('openai', {'usage': {'prompt_tokens': 1000, 'completion_tokens': 50,
                        'prompt_tokens_details': {'cached_tokens': 200, 'cache_write_tokens': 100}}})

    def test_disjoint_prices_failure_cohort_and_zero_success(self):
        cost = api_cost(self.r, self.config)
        self.assertEqual(cost['known_subtotal'], '0.0021')
        self.assertTrue(cost['complete'])
        totals = estimate_costs([self.r], self.config, 7200, 1, {(1,0)})
        self.assertEqual(totals['electricity']['estimate'], '0.03')
        self.assertEqual(totals['machine']['estimate'], '3.0')
        self.assertEqual(totals['api']['cost_per_accepted_circuit'], '0.0021')
        self.assertIsNone(estimate_costs([self.r], self.config, 7200, 0, {(1,0)})['api']['cost_per_accepted_circuit'])
        pending = dict(self.r, task_id=2)
        totals = estimate_costs([self.r, pending], self.config, 7200, 1, {(1,0)})
        self.assertEqual(totals['api']['active_or_unclassified_subtotal'], '0.0021')
        self.assertEqual(totals['api']['cost_per_accepted_circuit'], '0.0021')

    def test_unknown_compute_rates_and_remote_ollama(self):
        self.assertEqual(api_cost(record(), load_pricing())['known_subtotal'], '0')
        self.assertFalse(api_cost(record(billing_mode='unknown'), load_pricing())['complete'])
        self.assertFalse(estimate_costs([], completed_seconds=1)['electricity']['complete'])
        self.assertFalse(api_cost(self.r, load_pricing())['complete'])
        missing = record('openai', {'usage': {'prompt_tokens': 1000, 'completion_tokens': 50}})
        self.assertFalse(api_cost(missing, self.config)['complete'])
        for invalid in ['NaN', '-1', 'Infinity']:
            bad = deepcopy(self.config)
            bad['local']['power_watts'] = invalid
            with self.assertRaises(ValueError):
                load_pricing(bad)

    def test_overlap_and_group_costs(self):
        results = {'results': [{'task_id': 1, 'trial': 0, 'status': 'passed', 'wall_seconds': 3600,
                               'started_at': 0, 'ended_at': 3600},
                              {'task_id': 2, 'trial': 0, 'status': 'failed', 'wall_seconds': 3600,
                               'started_at': 1800, 'ended_at': 5400}]}
        summary = aggregate([self.r], self.config, results)
        self.assertEqual(summary['costs']['electricity']['estimate'], '0.0225')
        self.assertEqual(summary['by_stage']['initial_generation']['api_cost']['known_subtotal'], '0.0021')

    def test_immutable_price_snapshots(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = Recorder(tmp, 'openai')
            call = r.start({'model': 'model'})
            r.finish(call, {'usage': {'prompt_tokens': 10, 'completion_tokens': 5,
                                    'prompt_tokens_details': {'cached_tokens': 0}}})
            one = export_run(tmp, self.config)
            changed = deepcopy(self.config)
            changed['api_rates'][0]['output_per_million'] = '8'
            two = export_run(tmp, changed)
            self.assertNotEqual(one['estimate_snapshot'], two['estimate_snapshot'])
            self.assertTrue((Path(tmp)/'usage'/one['estimate_snapshot']).exists())
            self.assertEqual(export_run(tmp, changed), two)


class ComponentTests(unittest.TestCase):
    def test_nonoverlapping_template_spans_and_estimate_label(self):
        text = 'Instructions\nHere is an example:\nExample\nAs you have seen, use code.\n## Question\nDesign an amplifier.\nInput node name: Vin.\n## Answer\n'
        messages = [{'role':'system','content':'system'}, {'role':'user','content':text}]
        spans = message_components(messages, 'initial_generation')
        validate_spans(messages, spans)
        self.assertEqual(sum(s['end']-s['start'] for s in spans), len(text)+6)
        self.assertIn('examples', {s['category'] for s in spans})
        self.assertIn('task_specification', {s['category'] for s in spans})
        self.assertTrue(all(s['tokens'] is None for s in spans))
        tokenizer = SimpleNamespace(identity='test-only', encode=lambda x: list(x))
        attr = attribute_with_tokenizer(messages, spans, tokenizer, 10)
        self.assertEqual(attr['quality'], 'estimated')
        self.assertLess(attr['reconciliation_difference'], 0)
        self.assertEqual(messages[1]['content'], text)
        with self.assertRaisesRegex(ValueError, 'Overlapping'):
            validate_spans(messages, [spans[0], spans[0]])

    def test_image_bytes_never_counted(self):
        messages = [{'role':'user','content':[{'type':'text','text':'look'},
                       {'type':'image_url','image_url':{'url':'data:image/png;base64,'+'a'*500}}]}]
        spans = message_components(messages, 'waveform_analysis')
        self.assertEqual(spans[0]['end'], 4)
        self.assertIsNone(spans[1]['tokens'])

    def test_estimated_exports_do_not_replace_canonical_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            raw = directory/'api_calls/call_1.json'
            request = {'model':'qwen','messages':[{'role':'user','content':'abc'}]}
            atomic_json(raw, {'request':request})
            r = Recorder(tmp, 'ollama', model_digest='digest')
            call = r.start(request, raw_path=raw)
            r.finish(call, {'prompt_eval_count':10, 'eval_count':1})
            encoder = SimpleNamespace(identity='test-only', model_digest='digest', encode=list, provenance={'identity':'test-only'})
            summary = export_run(directory, tokenizer=encoder)
            self.assertEqual(summary['component_attribution']['estimated_calls'], 1)
            self.assertIsNone(load_calls(directory)[0]['components'][0]['tokens'])
            self.assertIn('estimated', (directory/'usage/components.csv').read_text())
            self.assertTrue((directory/'usage'/summary['estimate_snapshot']).exists())


class BackfillTests(unittest.TestCase):
    def setup_run(self, directory, name='baseline-qwen35-9b-28tasks'):
        data = json.loads(FIXTURE.read_text())['runs'][name]
        atomic_json(directory/'manifest.json', data['manifest'])
        atomic_json(directory/'results.json', data['results'])
        for call in data['calls']:
            atomic_json(directory/call['path'], call['raw'])
        return data

    def test_baselines_exact_preserved_idempotent_and_moved(self):
        for name, expected in [('baseline-qwen35-9b-28tasks', (63,231860,112874,161216)),
                               ('pilot-qwen35-9b', (3,4073,847,3258))]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                directory = Path(tmp)/'run'
                self.setup_run(directory, name)
                before = {str(p.relative_to(directory)):hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in directory.rglob('*') if p.is_file()}
                summary = backfill(directory)
                self.assertEqual((summary['calls'], summary['usage']['input_tokens'],
                                  summary['usage']['cached_input_tokens'], summary['usage']['output_tokens']), expected)
                self.assertEqual(backfill(directory), summary)
                ids = {r['call_id'] for r in load_calls(directory)}
                moved = Path(tmp)/'renamed'
                directory.rename(moved)
                self.assertEqual(backfill(moved), summary)
                self.assertEqual({r['call_id'] for r in load_calls(moved)}, ids)
                for path, digest in before.items():
                    self.assertEqual(hashlib.sha256((moved/path).read_bytes()).hexdigest(), digest)
                if expected[0] == 63:
                    self.assertEqual(summary['by_stage']['repair_generation']['calls'], 34)
                    self.assertEqual(summary['by_stage']['waveform_analysis']['calls'], 1)
                    self.assertAlmostEqual(summary['cache']['token_reuse_rate'], 112874/231860)

    def test_live_calls_not_duplicated_and_pending_evidence_recovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            data = self.setup_run(directory, 'pilot-qwen35-9b')
            path = directory/data['calls'][0]['path']
            raw = json.loads(path.read_text())
            r = Recorder(directory, 'ollama', task_id=1, trial_id=0)
            pending = r.start(raw['request'], {'phase':'initial_generation', 'generation_index':0}, path)
            self.assertEqual(backfill(directory)['calls'], 3)
            same = next(c for c in load_calls(directory) if c['call_id'] == pending['call_id'])
            self.assertEqual(same['status'], 'completed')
            self.assertEqual(same['phase_source'], 'explicit')
            raw['response']['eval_count'] += 1
            atomic_json(path, raw)
            with self.assertRaisesRegex(ValueError, 'conflicts'):
                backfill(directory)

    def test_unknown_schema_inference_and_log_upsert(self):
        self.assertEqual(infer_phase({'messages':[{'role':'user','content':'unknown'}]}, {})[0], 'unknown')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'log.md'
            original = '# Log\n\n## Run 001: run\n\nHuman notes.\n\n## Other\n\nKeep me.\n'
            path.write_text(original)
            summary = aggregate([])
            update_log(path, 'run', summary)
            once = path.read_text()
            update_log(path, 'run', summary)
            self.assertEqual(path.read_text(), once)
            start = once.index('<!-- usage-accounting:run:start -->')
            end = once.index('<!-- usage-accounting:run:end -->') + len('<!-- usage-accounting:run:end -->\n\n')
            self.assertEqual(once[:start]+once[end:], original)

    def test_reports_and_status_support_historical_and_measured_runs(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            data = self.setup_run(directory)
            for row in data['results']['results']:
                (directory/row['log']).write_text('offline report fixture\n')
            for measured in (False, True):
                if measured:
                    backfill(directory)
                for script in ('report.py', 'status.py'):
                    result = subprocess.run([sys.executable, str(root/'baselines/analogcoder_pro'/script), str(directory)],
                                            cwd=tmp, capture_output=True, text=True, timeout=15)
                    self.assertEqual(result.returncode, 0, result.stderr)
                text = (directory/'REPORT.md').read_text()
                self.assertIn('14/28', text)
                self.assertIn('48.68%', text) if measured else self.assertIn('not been backfilled', text)


if __name__ == '__main__':
    unittest.main()
