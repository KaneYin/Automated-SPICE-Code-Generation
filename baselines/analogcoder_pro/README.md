# AnalogCoder-Pro local Ollama baseline

This baseline runs the official AnalogCoder-Pro generation/repair workflow with
the locally installed `qwen3.5:9b` model. This is the Pro benchmark, not the
original AnalogCoder 24-task benchmark stored at the repository root.

See the repository-wide [experiment log](../../EXPERIMENT_LOG.md) for each run's
status, exact model identity, pass counts, configuration, and evidence links.

The [usage guide](../../docs/USAGE_ACCOUNTING.md) explains token, component,
cache-reuse, and cost telemetry. See the
[implementation plan](../../docs/TOKEN_USAGE_IMPLEMENTATION_PLAN.md) and
[implementation notes](../../IMPLEMENTATION_LOG.md) for design rationale,
validation, and limitations. New runs record usage automatically; historical
runs can be backfilled without inference.

## First full run: October 14, 2026

The 28-task run completed with 14 upstream-checker acceptances (50%): 9 on the
first generation and 5 after repair. There were 14 exhausted attempts and zero
harness errors. Total attempt wall time was 136.9 minutes, with 63 local model
calls including one waveform-vision call.

The output cap matters: 20 responses reached 4,096 tokens across 11 tasks.
Ten of those tasks ultimately failed. This is a first local baseline under the
recorded budget, rather than an estimate of the paper's reported performance.

The generated local artifacts are in
[`runs/analogcoder_pro/baseline-qwen35-9b-28tasks`](../../runs/analogcoder_pro/baseline-qwen35-9b-28tasks/REPORT.md).
They include the full report, per-task CSV, native API requests/responses,
generated circuits, simulation files, and `verification.json`. The audit verifies
all 28 attempts, 63 responses, token totals, the launcher hash, and all 77 pinned
upstream source/assets in the actual run workspace. These generated artifacts
are excluded from Git.

The upstream files in `upstream/` are unchanged at revision
`05542af46020e5c37d5a7e3ca79da9f24626e1c9` of
[laiyao1/AnalogCoderPro](https://github.com/laiyao1/AnalogCoderPro).
`UPSTREAM.json` records their SHA-256 hashes; the launcher verifies them before
each experiment. The official remote HEAD was checked on October 14, 2026.
Five committed upstream `.pyc` cache files are omitted; their paths are listed in
`UPSTREAM.json`. All Python source, prompts, checkers, and supplied assets remain
unchanged.

## Environment

Validated setup: Apple Silicon macOS, Python 3.10, PySpice 1.5, NumPy 1.26,
Homebrew ngspice/libngspice 47, and the installed Ollama `qwen3.5:9b` model
(9.7B parameters, Q4_K_M quantization). The complete Python package versions
are pinned in `requirements.lock` and copied into every experiment directory.

From the repository root:

```sh
brew install ngspice
uv venv --python 3.10 .venv
UV_CACHE_DIR=.cache/uv uv pip install --python .venv/bin/python -r baselines/analogcoder_pro/requirements.lock
ollama list
```

Ollama must already be running with `qwen3.5:9b` installed. The launcher does not
download models, alter existing models, or call cloud APIs. If needed, start
Ollama with its desktop app or `ollama serve`. A real voltage-divider simulation
must produce 2.500000 V before any LLM requests are made.

Check the simulator and the unchanged upstream inverter checker without any LLM
requests. This verifies that a known NMOS inverter is accepted and a noninverting
wire is rejected:

```sh
.venv/bin/python baselines/analogcoder_pro/check_environment.py
```

## Run

Three-task pilot: common-source amplifier, NMOS inverter, and low-pass filter:

```sh
.venv/bin/python baselines/analogcoder_pro/run_local.py --tasks 1 6 10 --trials 1
```

One attempt on each of the 28 generation tasks:

```sh
.venv/bin/python baselines/analogcoder_pro/run_local.py --tasks all --trials 1
```

Repeated attempts for a larger baseline:

```sh
.venv/bin/python baselines/analogcoder_pro/run_local.py --tasks all --trials 30
```

Thirty trials on 28 tasks means 840 independent attempts, each with up to three
generation calls and optional waveform-diagnosis calls. Measure the pilot runtime
before choosing this budget. The task sets, model, device models, public-code
limitations, and checker behavior must be stated when comparing with a paper.

Each attempt permits initial generation plus at most two repairs
(`--max-generations 3`). Defaults are temperature 0.5, 16,384-token context,
4,096 output tokens per call, and seed 42. Request seeds are
`seed + task_id * 1000 + trial * 100 + call_index`, with a zero-based call index.
Seeds are recorded for repeatability; GPU execution is not guaranteed to be
bitwise deterministic. Qwen's separate thinking mode is off by default; the
upstream prompt still asks for a design plan before the Python circuit.

Waveform feedback is enabled by default because this installed model supports
vision. It is called only when the upstream repair workflow requests it.
`--no-vision` selects the text-only ablation. `--thinking` enables Qwen's separate
thinking mode; allow a larger output budget if using it.

## Outputs and interpretation

Every invocation creates a new directory in `runs/analogcoder_pro/`. `--out`
can name another new directory; an existing directory is rejected to protect
previous runs. Outputs include:

- `manifest.json`: upstream commit, model digest, Ollama version, settings,
  platform, and shared-library path.
- `model_info.json`, `installed_packages.txt`, `simulator_check.log`.
- `results.json` and `results.csv`: per-attempt status, model calls, vision calls,
  prompt/output tokens, and wall time; updated after each attempt.
- `api_calls/`: complete native Ollama requests and responses, including seeds,
  timing, output-limit termination, and separate thinking text when enabled.
- `task_<id>_trial_<n>.log`: upstream console output and Python failures.
- `work/<model>/p<id>/<trial>/`: generated Python, SPICE netlists when emitted by
  upstream, operating points, DC sweeps, figures, prompts, and repair feedback.

The top-level token totals include both generation and waveform-vision calls.
The upstream per-task token text files do not include vision-token usage.

`passed` means the upstream runner created a success artifact and exited
normally. It is upstream-checker acceptance, not independent circuit
certification. `failed` means its generation/repair budget was exhausted.
`error` and `timeout` expose runner failures and count as non-successes in the
reported attempt acceptance rate. A three-task pilot does not estimate full-suite
Pass@1 or reproduce the paper's results.

Create a readable report from any saved run (including a run still in progress):

```sh
.venv/bin/python baselines/analogcoder_pro/report.py runs/analogcoder_pro/pilot-qwen35-9b
```

The report is written to `REPORT.md` inside that run directory.

Inspect progress and the pending generation or waveform request:

```sh
.venv/bin/python baselines/analogcoder_pro/status.py runs/analogcoder_pro/baseline-qwen35-9b-28tasks
```

## Compatibility changes and public-code limits

The pinned source snapshot, prompts, transistor examples, and checkers remain
unchanged. The launcher makes four explicit runtime adaptations in new workspaces:

1. Replace the upstream OpenAI client transport with Ollama's local `/api/chat`.
   It preserves text/image messages and temperatures, and records the native
   token counts. Native transport gives explicit control of context, seed,
   output budget, and thinking without creating a modified Ollama model.
2. Copy the upstream `prompt_template_comptex.md` to the expected
   `prompt_template_complex.md` inside each run's workspace. Content is unchanged.
3. Limit simulator subprocesses to 60 seconds and impose an attempt timeout.
4. Add metadata-only usage contexts around five model call sites in the runtime
   copy. The manifest records the original and patched runner hashes. Provider
   kwargs and prompts remain unchanged.

Tasks 1-28 are supported by the released generation/checker files. Task 29 is
excluded because its VCO checker is missing. Sizing tasks 51-66 are excluded
because the released code lacks `mosfet_model/model.py` and
`optimize/circuit_optimizer_helper.py`. The default released entry point does
not wire up dynamic subcircuit retrieval. These limits prevent claiming a full
reproduction of all paper experiments.

PySpice 1.5 may print `Unsupported Ngspice version 47`; the voltage-divider
preflight and actual checker executions establish what works in this environment.
Keep the warning in the logs instead of treating it as proof of failure or
suppressing real simulator errors.
