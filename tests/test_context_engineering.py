"""Offline checks for repair-context strategies. No model requests."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from baselines.analogcoder_pro import run_local
from context_engineering import MODES, build_context
from context_engineering.state import classify, describe_change, parse_attempts
from usage_accounting.aggregate import load_calls
from usage_accounting.recorder import Recorder, call_context

EXECUTION = ("\nI am encountering an error when running the PySpice code. Below is the error message:\n{}\n\n"
             "Identify any structural errors in this circuit's topology (e.g., missing components, incorrect connections) "
             "and rewrite the complete corrected code from scratch, with each modification clearly marked and explained in comments.")
NAME_ERROR = EXECUTION.format('Traceback (most recent call last):\n  File "/tmp/run/work/m/p7/0/p7_0_0.py", line 11, in <module>\n'
                              "    Vdd = 5.0 * volt\nNameError: name 'volt' is not defined\n")
FUNCTION = EXECUTION.format("Maximum gain: -0.00 dB\nFAIL: This is NOT a band-pass filter.\n")
SIMULATOR = EXECUTION.format("Analysis failed due to an error:\nUnsupported Ngspice version 47\nFatal error: instance v1 is a shorted VSRC\n")
NO_CODE = "There is no complete code in your reply. Please generate a complete code."
FLOATING = ("The circuit design has one floating node: n1, causing an error in simulation.\n"
            "Please consider connect it to a voltage or current source or another device.\n"
            "Please identify the cause of the floating node and rewrite the corrected complete code.")
OPERATING = ("According to dc sweep analysis, the best input voltage is 1.2. Please use this voltage.\n"
             "According to the operating point check, there are some issues, which defy the general operating principles of MOSFET devices. \n"
             "For NMOS 1, the drain node (Vout) voltage is 0.\n\nPlease help me fix the issues and rewrite the corrected complete code.\n")


def answer(*lines):
    return "Plan text.\n```python\n" + "\n".join(lines) + "\nsimulator = circuit.simulator()\n```"


def conversation(*turns):
    messages = [{"role": "system", "content": "You are an expert."}, {"role": "user", "content": "TASK PROMPT\n## Answer\n"}]
    for reply, feedback in turns:
        messages += [{"role": "assistant", "content": reply}, {"role": "user", "content": feedback}]
    return messages


class ClassificationTests(unittest.TestCase):
    def test_feedback_templates_map_to_classes(self):
        expected = {NAME_ERROR: "PYTHON_ERROR", FUNCTION: "FUNCTION_CHECK", SIMULATOR: "SIMULATION_FAILURE",
                    NO_CODE: "NO_CODE", FLOATING: "FLOATING_NODE", OPERATING: "OPERATING_POINT",
                    "something unrecognized": "UNKNOWN"}
        for feedback, error_class in expected.items():
            self.assertEqual(classify(feedback)[0], error_class, feedback[:60])

    def test_evidence_is_trimmed_and_facts_are_kept(self):
        _, evidence, _, _ = classify(NAME_ERROR)
        self.assertEqual(evidence.splitlines()[-1], "NameError: name 'volt' is not defined")
        self.assertIn('File "p7_0_0.py", line 11', evidence)
        self.assertNotIn("/tmp/run", evidence)
        self.assertNotIn("Identify any structural errors", evidence)
        self.assertNotIn("Unsupported Ngspice", classify(SIMULATOR)[1])
        _, _, nodes, _ = classify(FLOATING)
        self.assertEqual(nodes, ["n1"])
        _, evidence, _, facts = classify(OPERATING)
        self.assertEqual(facts, ["DC sweep found the best input bias voltage: 1.2 V"])
        self.assertNotIn("best input voltage", evidence)

    def test_change_description(self):
        base = "circuit.R('1', 'a', 'b', 1)\ncircuit.R('2', 'b', 'c', 1)\ncircuit.R('3', 'c', 'd', 1)"
        self.assertEqual(describe_change("", base), "wrote a new design")
        self.assertEqual(describe_change(base, ""), "no code produced")
        self.assertEqual(describe_change(base, base + "  # comment"), "resubmitted the same code")
        self.assertEqual(describe_change(base, base + "\ncircuit.V('b', 'x', 'y', 1)"), "+ circuit.V('b', 'x', 'y', 1)")


class StrategyTests(unittest.TestCase):
    def setUp(self):
        self.first = answer("circuit.V('dd', 'Vdd', circuit.gnd, 5.0 * volt)")
        self.second = answer("circuit.V('dd', 'Vdd', circuit.gnd, 5.0 * volt)", "circuit.R('1', 'Vout', 'Vdd', 1)")
        self.messages = conversation((self.first, NAME_ERROR), (self.second, NAME_ERROR))

    def test_full_history_is_identity(self):
        out, meta = build_context("full_history", self.messages)
        self.assertIs(out, self.messages)
        self.assertFalse(meta["applied"])

    def test_latest_feedback_keeps_only_last_turn(self):
        out, _ = build_context("latest_feedback", self.messages)
        self.assertEqual(out, self.messages[:2] + self.messages[-2:])

    def test_summary_keeps_code_and_feedback_verbatim(self):
        requests = []
        out, meta = build_context("llm_summary", self.messages, summarize=lambda m: requests.append(m) or "SUMMARY TEXT")
        self.assertEqual(len(out), 2)
        text = out[-1]["content"]
        self.assertTrue(text.startswith("TASK PROMPT"))
        self.assertIn("SUMMARY TEXT", text)
        self.assertIn("circuit.R('1', 'Vout', 'Vdd', 1)", text)
        self.assertIn(NAME_ERROR.strip(), text)
        # The summarizer sees reasoning and earlier feedback, but no code.
        self.assertNotIn("circuit.V(", requests[0][-1]["content"])
        self.assertIn("NameError", requests[0][-1]["content"])
        self.assertEqual(meta["summary_chars"], len("SUMMARY TEXT"))

    def test_failed_summary_falls_back(self):
        for summarize in (None, lambda m: None, lambda m: "  "):
            out, meta = build_context("llm_summary", self.messages, summarize=summarize)
            self.assertEqual(meta["fallback"], "latest_feedback")
            self.assertEqual(out, self.messages[:2] + self.messages[-2:])

    def test_structured_state_is_one_fresh_prompt(self):
        out, meta = build_context("structured_state", self.messages, generation_budget=3)
        self.assertEqual([m["role"] for m in out], ["system", "user"])
        text = out[-1]["content"]
        self.assertTrue(text.startswith("TASK PROMPT"))  # stable prefix for prompt caching
        self.assertIn("ATTEMPT: 3 of 3", text)
        self.assertIn("FAILURE: layer=PYTHON_API class=PYTHON_ERROR", text)
        self.assertIn("not a circuit topology problem", text)
        self.assertNotIn("TRIED", text)
        self.assertNotIn("Plan text.", text)
        self.assertEqual(meta["state"]["candidate_attempt"], 1)
        self.assertEqual(self.messages[1]["content"], "TASK PROMPT\n## Answer\n")  # input not mutated

    def test_ledger_records_changes_and_repeats(self):
        out, meta = build_context("structured_ledger", self.messages, generation_budget=3)
        text = out[-1]["content"]
        self.assertIn("1. wrote a new design -> PYTHON_ERROR: NameError: name 'volt' is not defined", text)
        self.assertIn("2. + circuit.R('1', 'Vout', 'Vdd', 1) -> PYTHON_ERROR", text)
        self.assertIn("The last two attempts failed in the same way", text)
        self.assertTrue(meta["state"]["repeated_failure"])

    def test_rollback_prefers_the_candidate_that_got_furthest(self):
        good = answer("circuit.R('good', 'a', 'b', 1)")
        messages = conversation((good, FUNCTION), ("I kept thinking and wrote no code", NO_CODE))
        out, meta = build_context("structured_ledger", messages, generation_budget=3)
        text = out[-1]["content"]
        self.assertTrue(meta["state"]["rolled_back"])
        self.assertEqual(meta["state"]["candidate_attempt"], 0)
        self.assertIn("circuit.R('good'", text)
        self.assertIn("class=FUNCTION_CHECK", text)  # failure shown belongs to the candidate shown
        self.assertIn("FAIL: This is NOT a band-pass filter.", text)
        self.assertIn("2. no code produced -> NO_CODE", text)
        # Without rollback the latest (empty) attempt is the candidate.
        text, meta = (lambda r: (r[0][-1]["content"], r[1]))(build_context("structured_state", messages))
        self.assertIn("CANDIDATE: none", text)
        self.assertEqual(meta["state"]["error_class"], "NO_CODE")

    def test_unrecognized_conversations_are_sent_unchanged(self):
        initial = self.messages[:2]
        vision = [{"role": "user", "content": [{"type": "text", "text": "x"}]}]
        for messages in (initial, vision, self.messages[:-1]):
            for mode in MODES:
                out, meta = build_context(mode, messages, summarize=lambda m: "S")
                self.assertEqual(out, messages)
                self.assertFalse(meta["applied"])
        with self.assertRaises(ValueError):
            build_context("nonsense", self.messages)

    def test_parse_attempts(self):
        prefix, attempts = parse_attempts(self.messages)
        self.assertEqual(len(prefix), 2)
        self.assertEqual([a.index for a in attempts], [0, 1])
        self.assertIn("circuit.R('1'", attempts[1].code)


class TransportTests(unittest.TestCase):
    def run_mode(self, mode, phase="repair_generation"):
        messages = conversation((answer("circuit.R('1', 'a', 'b', 1)"), NAME_ERROR))
        response = {"message": {"content": "reply"}, "prompt_eval_count": 10, "eval_count": 5, "done_reason": "stop"}
        sent = []
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config = {"thinking": False, "context": 2048, "max_tokens": 64, "endpoint": "http://127.0.0.1:11434",
                      "request_timeout": 5, "max_generations": 3, "context_mode": mode}
            call_dir = directory / "api_calls"
            call_dir.mkdir()
            completions = run_local.OllamaCompletions(
                config, call_dir, 42, recorder=Recorder(directory, "ollama", task_id=1, trial_id=0))
            with patch.object(run_local, "api", side_effect=lambda e, r, payload, t: sent.append(payload) or response):
                completions.create(model="m", messages=[{"role": "user", "content": "first"}], temperature=.5)
                with call_context(phase, generation_index=1):
                    completions.create(model="m", messages=messages, temperature=.5)
            files = {p.name: json.loads(p.read_text()) for p in sorted(call_dir.glob("*.json"))}
            return messages, sent, files, load_calls(directory)

    def test_default_mode_leaves_payload_unchanged(self):
        messages, sent, files, _ = self.run_mode("full_history")
        self.assertEqual(sent[1]["messages"], messages)
        self.assertNotIn("context_strategy", files["call_002.json"])

    def test_only_repair_requests_are_rewritten(self):
        messages, sent, _, _ = self.run_mode("structured_ledger", phase="initial_generation")
        self.assertEqual(sent[1]["messages"], messages)

    def test_structured_mode_rewrites_and_records(self):
        _, sent, files, calls = self.run_mode("structured_ledger")
        self.assertEqual(len(sent[1]["messages"]), 2)
        self.assertIn("## Repair state", sent[1]["messages"][-1]["content"])
        self.assertEqual(sent[1]["options"]["seed"], 43)
        self.assertEqual(files["call_002.json"]["context_strategy"]["state"]["error_class"], "PYTHON_ERROR")
        self.assertEqual([c["phase"] for c in calls], ["unknown", "repair_generation"])

    def test_summary_call_is_recorded_without_shifting_seeds(self):
        _, sent, files, calls = self.run_mode("llm_summary")
        self.assertEqual(len(sent), 3)
        self.assertEqual(sorted(files), ["call_001.json", "call_002.json", "call_002_summary.json"])
        self.assertEqual(sent[1]["options"]["temperature"], 0.0)
        self.assertEqual(sent[2]["options"]["seed"], 43)  # same as in every other mode
        self.assertIn("## Summary of previous attempts\nreply", sent[2]["messages"][-1]["content"])
        self.assertEqual(sorted(c["phase"] for c in calls), ["context_summary", "repair_generation", "unknown"])
        self.assertEqual(sum(c["usage"]["input_tokens"] for c in calls), 30)


if __name__ == "__main__":
    unittest.main()
