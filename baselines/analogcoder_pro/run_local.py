#!/usr/bin/env python3
"""Run pinned AnalogCoder-Pro prompts/checkers against a local Ollama model."""
from __future__ import annotations

import argparse
import csv
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import runpy
import shutil
import signal
import subprocess
import sys
import time
from types import SimpleNamespace
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from usage_accounting.recorder import Recorder, current_context
from usage_accounting.aggregate import export_run, load_calls
from usage_accounting.pricing import load_pricing
from usage_accounting.components import load_tokenizer
from usage_accounting.cli import _local_endpoint
from baselines.analogcoder_pro.instrumentation import instrument_runtime


def write_json(path, data):
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n")
    temporary.replace(path)


def api(endpoint, route, payload=None, timeout=30):
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        endpoint.rstrip("/") + route, data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def verify_upstream():
    provenance = json.loads((HERE / "UPSTREAM.json").read_text())
    for name, digest in provenance["sha256"].items():
        path = HERE / "upstream" / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"Pinned upstream file changed: {name}")
    return provenance


def child_environment():
    env = os.environ.copy()
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env["PATH"]
    env["MPLBACKEND"] = "Agg"
    env["PYTHONUNBUFFERED"] = "1"
    for candidate in (
        env.get("NGSPICE_LIBRARY_PATH", ""),
        "/opt/homebrew/opt/libngspice/lib/libngspice.dylib",
        "/opt/homebrew/lib/libngspice.dylib",
        "/usr/local/lib/libngspice.dylib",
    ):
        if candidate and Path(candidate).is_file():
            env["NGSPICE_LIBRARY_PATH"] = candidate
            break
    return env


def simulator_check(env, directory):
    """A real voltage-divider simulation checks the shared-library installation."""
    code = """from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import *
c = Circuit('Baseline environment check')
c.V('dd', 'supply', c.gnd, 5)
c.R('1', 'supply', 'out', 1000)
c.R('2', 'out', c.gnd, 1000)
a = c.simulator().operating_point()
v = float(a['out'][0])
assert abs(v - 2.5) < 1e-6, v
print('Voltage-divider operating point: %.6f V' % v)
"""
    result = subprocess.run(
        [sys.executable, "-c", code], env=env,
        capture_output=True, text=True, timeout=60,
    )
    (directory / "simulator_check.log").write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f"Simulator check failed. See {directory / 'simulator_check.log'}")
    print(result.stdout.strip(), flush=True)


class OllamaCompletions:
    def __init__(self, config, call_dir, seed, recorder=None):
        self.config, self.call_dir, self.seed = config, call_dir, seed
        self.count = 0
        self.recorder = recorder

    def create(self, *, model, messages, temperature, **kwargs):
        self.count += 1
        native_messages = []
        for message in messages:
            item = {"role": message["role"]}
            if isinstance(message["content"], str):
                item["content"] = message["content"]
            else:
                item["content"] = "\n".join(
                    block["text"] for block in message["content"] if block["type"] == "text"
                )
                item["images"] = [
                    block["image_url"]["url"].split(",", 1)[1]
                    for block in message["content"] if block["type"] == "image_url"
                ]
            native_messages.append(item)
        request = {
            "model": model, "messages": native_messages, "stream": False,
            "think": self.config["thinking"], "keep_alive": "30m",
            "options": {
                "temperature": temperature,
                "num_ctx": self.config["context"],
                "num_predict": self.config["max_tokens"],
                "seed": self.seed + self.count - 1,
            },
        }
        path = self.call_dir / f"call_{self.count:03d}.json"
        record = {"request": request, "started_at": time.time()}
        write_json(path, record)
        # Persist lifecycle before dispatch. Persistence failure stops the request.
        usage_record = self.recorder.start(request, current_context(), raw_path=path) if self.recorder else None
        started = time.monotonic()
        print(f"Ollama call {self.count}: {'vision' if any(m.get('images') for m in native_messages) else 'text'}", flush=True)
        try:
            response = api(self.config["endpoint"], "/api/chat", request, self.config["request_timeout"])
            record["response"] = response
            # Save provider evidence before accounting or answer extraction.
            record["wall_seconds"] = round(time.monotonic() - started, 3)
            write_json(path, record)
            if self.recorder:
                self.recorder.finish(usage_record, response=response, wall_seconds=record["wall_seconds"])
        except Exception as exc:
            record["error"] = str(exc)
            if self.recorder and "response" not in record:
                self.recorder.finish(usage_record, error=str(exc), wall_seconds=time.monotonic() - started)
            raise
        finally:
            record["wall_seconds"] = round(time.monotonic() - started, 3)
            write_json(path, record)
        answer = response["message"].get("content", "")
        if not answer.strip():
            raise RuntimeError(f"Ollama returned no answer (done_reason={response.get('done_reason')}). See {path}")
        prompt_tokens = response.get("prompt_eval_count")
        completion_tokens = response.get("eval_count")
        print(f"Ollama call {self.count}: {completion_tokens} output tokens in {record['wall_seconds']}s", flush=True)
        result = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=answer))])
        # The upstream guards usage with hasattr. Missing telemetry must not look
        # like a measured zero and must not cause its cumulative additions to fail.
        if all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in (prompt_tokens, completion_tokens)):
            result.usage = SimpleNamespace(
                prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            )
        return result


def worker(directory, task_id, trial):
    """Adapt transport only; execute the vendored upstream runner and checkers."""
    import openai

    manifest = json.loads((directory / "manifest.json").read_text())
    config = manifest["config"]
    call_dir = directory / "api_calls" / f"task_{task_id}" / f"trial_{trial}"
    call_dir.mkdir(parents=True)
    tokenizer = load_tokenizer(manifest["usage_tokenizer"]["config_path"]) if manifest.get("usage_tokenizer") else None
    if tokenizer is not None and tokenizer.provenance != manifest["usage_tokenizer"]:
        raise RuntimeError("Tokenizer identity changed after manifest snapshot")
    recorder = Recorder(directory, provider="ollama", run_id=manifest.get("run_id"), task_id=task_id, trial_id=trial,
                        model_digest=manifest["model"].get("digest"),
                        model_name=config['model'], tokenizer=tokenizer,
                        billing_mode='local' if _local_endpoint(config['endpoint'], config['model']) else 'unknown',
                        server_version=manifest.get("ollama_version"), pricing=manifest.get("usage_pricing"))
    completions = OllamaCompletions(config, call_dir, config["seed"] + task_id * 1000 + trial * 100, recorder=recorder)

    def local_client(**kwargs):
        return SimpleNamespace(chat=SimpleNamespace(completions=completions))

    openai.OpenAI = local_client
    # Upstream omits timeouts on some simulator subprocesses.
    original_run = subprocess.run

    def bounded_run(*args, **kwargs):
        kwargs.setdefault("timeout", 60)
        return original_run(*args, **kwargs)

    subprocess.run = bounded_run
    os.chdir(directory / "work")
    sys.argv = [
        "run.py", "--model", config["model"], "--temperature", str(config["temperature"]),
        "--task_id", str(task_id), "--num_of_done", str(trial),
        "--num_per_task", str(trial + 1), "--num_of_retry", str(config["max_generations"]),
        "--api_key", "ollama-local",
    ]
    if not config["vision"]:
        sys.argv.append("--no_vlm")
    runpy.run_path("run.py", run_name="__main__")


def save_results(directory, manifest, results):
    summary = {
        "label": "Local-model AnalogCoder-Pro baseline; upstream checker acceptance",
        "planned_attempts": len(manifest["config"]["tasks"]) * manifest["config"]["trials"],
        "finished_attempts": len(results),
        "passed_attempts": sum(r["status"] == "passed" for r in results),
        "failed_attempts": sum(r["status"] == "failed" for r in results),
        "runner_errors": sum(r["status"] not in {"passed", "failed"} for r in results),
        "attempt_acceptance_rate": sum(r["status"] == "passed" for r in results) / len(results) if results else None,
        "api_calls": sum(r["api_calls"] for r in results),
        "prompt_tokens": sum(r["prompt_tokens"] for r in results),
        "completion_tokens": sum(r["completion_tokens"] for r in results),
        "note": "Each attempt permits initial generation plus repairs. Pilot results are not a paper reproduction. Runner errors/timeouts count as non-successes in attempt_acceptance_rate and are also reported separately.",
        "results": results,
    }
    write_json(directory / "results.json", summary)
    summary["usage"] = export_run(directory, pricing=manifest.get("usage_pricing"))
    write_json(directory / "results.json", summary)
    if results:
        with (directory / "results.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(results[0]))
            writer.writeheader()
            writer.writerows(results)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="qwen3.5:9b")
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    parser.add_argument("--tasks", nargs="+", default=["1", "6", "10"], help="Task IDs, or 'all' for 1-28")
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--max-generations", type=int, default=3, help="Includes initial generation")
    parser.add_argument("--temperature", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--context", type=int, default=16384)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--thinking", action="store_true", help="Enable Qwen's separate thinking mode")
    parser.add_argument("--no-vision", dest="vision", action="store_false")
    parser.add_argument("--request-timeout", type=int, default=600)
    parser.add_argument("--attempt-timeout", type=int, default=1800)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--usage-pricing", type=Path, help="Optional versioned usage-price configuration; stored in run manifest")
    parser.add_argument("--usage-tokenizer-config", type=Path, help="Optional local tokenizer configuration for estimated component counts")
    args = parser.parse_args()
    args.tasks = list(range(1, 29)) if args.tasks == ["all"] else list(dict.fromkeys(map(int, args.tasks)))
    if any(task not in range(1, 29) for task in args.tasks):
        parser.error("Use tasks 1-28. Upstream lacks the VCO checker and sizing helper for other tasks.")
    if min(args.trials, args.max_generations, args.context, args.max_tokens, args.request_timeout, args.attempt_timeout) < 1:
        parser.error("Trial counts, budgets, and timeouts must be positive.")
    pricing = load_pricing(args.usage_pricing) if args.usage_pricing else None
    tokenizer = load_tokenizer(args.usage_tokenizer_config)
    provenance = verify_upstream()
    tags = api(args.endpoint, "/api/tags")
    model = next((m for m in tags["models"] if m["name"] == args.model), None)
    if model is None:
        parser.error(f"Model {args.model!r} is not installed. Available: {[m['name'] for m in tags['models']]}")
    if tokenizer is not None and tokenizer.model_digest != model['digest']:
        parser.error('Tokenizer model digest does not match the installed model')
    show = api(args.endpoint, "/api/show", {"model": args.model})
    if args.vision and "vision" not in show.get("capabilities", []):
        parser.error("This model has no vision capability. Pass --no-vision for a text-only ablation.")
    directory = (args.out or ROOT / "runs" / "analogcoder_pro" / time.strftime("%Y%m%d-%H%M%S")).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    env = child_environment()
    env["MPLCONFIGDIR"] = str(directory / "matplotlib")
    manifest = {
        'run_id': directory.name,
        "upstream": {k: provenance[k] for k in ("repository", "revision")},
        "config": {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items() if key != "out"},
        "model": model, "ollama_version": api(args.endpoint, "/api/version"),
        "python": sys.version, "platform": platform.platform(),
        "launcher_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "ngspice_library": env.get("NGSPICE_LIBRARY_PATH"),
        "compatibility": ["Native Ollama transport with explicit context/output/seed/thinking settings", "Runtime alias for upstream prompt_template_comptex.md typo", "60s cap on simulator subprocesses"],
        "usage_schema_version": 1,
        "usage_pricing": pricing,
        "usage_tokenizer": tokenizer.provenance if tokenizer is not None else None,
    }
    write_json(directory / "manifest.json", manifest)
    write_json(directory / "model_info.json", show)
    packages = sorted(f"{d.metadata['Name']}=={d.version}" for d in metadata.distributions())
    (directory / "installed_packages.txt").write_text("\n".join(packages) + "\n")
    simulator_check(env, directory)
    shutil.copytree(HERE / "upstream", directory / "work")
    manifest["usage_instrumentation"] = instrument_runtime(directory / "work" / "run.py")
    write_json(directory / "manifest.json", manifest)
    shutil.copyfile(directory / "work" / "prompt_template_comptex.md", directory / "work" / "prompt_template_complex.md")
    with (HERE / "upstream" / "problem_set.tsv").open() as handle:
        task_names = {int(row["Id"]): row["Circuit"] for row in csv.DictReader(handle, delimiter="\t")}
    results = []
    save_results(directory, manifest, results)
    print(f"Artifacts: {directory}", flush=True)
    for task_id in args.tasks:
        for trial in range(args.trials):
            print(f"Task {task_id}, trial {trial}: {task_names[task_id]}", flush=True)
            log_path = directory / f"task_{task_id}_trial_{trial}.log"
            started = time.monotonic()
            attempt_started_at = time.time()
            timed_out = False
            with log_path.open("w") as log:
                process = subprocess.Popen(
                    [sys.executable, str(Path(__file__).resolve()), "_worker", str(directory), str(task_id), str(trial)],
                    stdout=log, stderr=subprocess.STDOUT, env=env, start_new_session=True,
                )
                try:
                    returncode = process.wait(timeout=args.attempt_timeout)
                except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                    Recorder(directory, provider="ollama").interrupt_pending(task_id, trial)
                    if isinstance(exc, KeyboardInterrupt):
                        save_results(directory, manifest, results)
                        raise
                    timed_out = True
                    returncode = process.returncode
            Recorder(directory, provider="ollama").interrupt_pending(task_id, trial)
            successes = sorted((directory / "work").glob(f"*/p{task_id}/{trial}/*_success.py"))
            calls = [json.loads(p.read_text()) for p in sorted((directory / "api_calls" / f"task_{task_id}" / f"trial_{trial}").glob("*.json"))]
            measured = [c for c in load_calls(directory) if c["task_id"] == task_id and c["trial_id"] == trial]
            input_known = [c["usage"]["input_tokens"] for c in measured if c["usage"]["input_tokens"] is not None]
            output_known = [c["usage"]["output_tokens"] for c in measured if c["usage"]["output_tokens"] is not None]
            status = "timeout" if timed_out else "error" if returncode else "passed" if successes else "failed"
            row = {
                "task_id": task_id, "trial": trial, "circuit": task_names[task_id], "status": status,
                "returncode": returncode, "wall_seconds": round(time.monotonic() - started, 3),
                "started_at": attempt_started_at, "ended_at": time.time(),
                "api_calls": len(calls),
                "vision_calls": sum(any(m.get("images") for m in c["request"]["messages"]) for c in calls),
                "prompt_tokens": sum(input_known),
                "completion_tokens": sum(output_known),
                "prompt_tokens_known_calls": len(input_known),
                "completion_tokens_known_calls": len(output_known),
                "usage_complete": len(measured) == len(calls) == len(input_known) == len(output_known),
                "success_file": str(successes[0].relative_to(directory)) if successes else "",
                "log": log_path.name,
            }
            results.append(row)
            summary = save_results(directory, manifest, results)
            print(f"  {status}: {row['api_calls']} API calls, {row['wall_seconds']}s; log: {log_path.name}", flush=True)
    print(f"Passed {summary['passed_attempts']}/{summary['finished_attempts']}; runner errors: {summary['runner_errors']}", flush=True)
    print(f"Results: {directory / 'results.json'}", flush=True)
    return int(summary["runner_errors"] > 0)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "_worker":
        worker(Path(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]))
    else:
        raise SystemExit(main())
