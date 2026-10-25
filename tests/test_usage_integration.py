"""Offline checks for Pro stage patches and the unchanged native transport."""
import ast
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from baselines.analogcoder_pro.instrumentation import HELPER, instrument_source
from baselines.analogcoder_pro import run_local
from usage_accounting.aggregate import load_calls
from usage_accounting.recorder import Recorder, current_context, call_context

ROOT = Path(__file__).resolve().parents[1]


class ProInstrumentationTests(unittest.TestCase):
    def test_five_explicit_stages_preserve_provider_arguments(self):
        source = (ROOT / "baselines/analogcoder_pro/upstream/run.py").read_text()
        patched, provenance = instrument_source(source)
        self.assertEqual(provenance["call_sites"], 5)
        self.assertNotEqual(provenance["source_sha256"], provenance["runtime_sha256"])
        wrappers = [n for n in ast.walk(ast.parse(patched)) if isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Name) and n.func.id == "_usage_invoke"]
        observed = []

        def create(**kwargs):
            observed.append((kwargs, current_context()))
            return "answer"

        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        env = dict(client=client, client_vlm=client, args=SimpleNamespace(model="qwen", temperature=.5),
                   optimize_prompt="original optimization prompt", messages=[{"role": "user", "content": "original prompt"}],
                   vlm_model="qwen", messages_vlm=[{"role": "user", "content": "waveform"}], code_id=2)
        exec(HELPER, env)
        phases = set()
        for wrapper in wrappers:
            original_call = wrapper.args[1].body
            before = eval(compile(ast.Expression(original_call), "original", "eval"), env)
            original_kwargs = observed[-1][0]
            result = eval(compile(ast.Expression(wrapper), "instrumented", "eval"), env)
            kwargs, context = observed[-1]
            self.assertEqual(result, before)
            self.assertEqual(kwargs, original_kwargs)
            phases.add(context["phase"])
            if context["phase"] == "initial_generation":
                self.assertEqual(context["generation_index"], 0)
            if context["phase"] == "repair_generation":
                self.assertEqual(context["generation_index"], 2)
            if context["phase"] == "waveform_analysis":
                self.assertEqual(context["diagnoses_generation_index"], 2)
            self.assertEqual(current_context(), {})
        self.assertEqual(phases, {"initial_generation", "repair_generation", "waveform_analysis", "retrieval", "optimization"})
        with self.assertRaises(RuntimeError):
            instrument_source(source + "\n")

    def test_native_payload_seed_and_empty_answer_usage(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            calls = directory / "api_calls/task_1/trial_0"
            calls.mkdir(parents=True)
            config = dict(thinking=False, context=4096, max_tokens=64,
                          endpoint="http://localhost:11434", request_timeout=5)
            recorder = Recorder(directory, "ollama", task_id=1, trial_id=0)
            adapter = run_local.OllamaCompletions(config, calls, 100, recorder=recorder)
            response = dict(message={"content": ""}, prompt_eval_count=20,
                            prompt_eval_cached_count=12, eval_count=5, done_reason="length")
            messages = [{"role": "user", "content": "unchanged"}]
            with patch.object(run_local, "api", return_value=response) as transport:
                with call_context("initial_generation", generation_index=0):
                    with self.assertRaisesRegex(RuntimeError, "no answer"):
                        adapter.create(model="qwen", messages=messages, temperature=.5)
            payload = transport.call_args.args[2]
            self.assertEqual(payload["messages"], messages)
            self.assertEqual(payload["options"], dict(temperature=.5, num_ctx=4096, num_predict=64, seed=100))
            record = load_calls(directory)[0]
            self.assertEqual(record["status"], "completed")
            self.assertEqual(record["usage"]["input_tokens"], 20)
            self.assertEqual(record["usage"]["cached_input_tokens"], 12)
            self.assertEqual(record["phase"], "initial_generation")
            self.assertEqual(json.loads((calls / "call_001.json").read_text())["response"], response)

    def test_missing_usage_and_transport_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            calls = directory / "api_calls/task_1/trial_0"
            calls.mkdir(parents=True)
            config = dict(thinking=False, context=4096, max_tokens=64,
                          endpoint="http://localhost:11434", request_timeout=5)
            recorder = Recorder(directory, "ollama", task_id=1, trial_id=0)
            adapter = run_local.OllamaCompletions(config, calls, 100, recorder=recorder)
            with patch.object(run_local, "api", return_value={"message": {"content": "answer"}}):
                answer = adapter.create(model="qwen", messages=[], temperature=.5)
                self.assertFalse(hasattr(answer, "usage"))
            with patch.object(run_local, "api", side_effect=TimeoutError("timeout")):
                with self.assertRaises(TimeoutError):
                    adapter.create(model="qwen", messages=[], temperature=.5)
            records = load_calls(directory)
            self.assertEqual(records[0]["usage"]["input_tokens"], None)
            self.assertEqual(records[1]["status"], "error")


if __name__ == "__main__":
    unittest.main()
