# Usage accounting

The shared `usage_accounting` package records model calls, tokens, prompt/KV
cache reuse, stage breakdowns, and configurable cost estimates. The core requires
only the Python standard library. It does not change prompts or enforce budgets.

See the [implementation plan](TOKEN_USAGE_IMPLEMENTATION_PLAN.md) for the design
and [implementation notes](../IMPLEMENTATION_LOG.md) for changes, rationale,
validation, and limitations.

## New AnalogCoder-Pro runs

Existing launcher commands now record telemetry automatically:

```sh
.venv/bin/python baselines/analogcoder_pro/run_local.py --tasks 1 6 10 --trials 1
```

The launcher verifies the pristine upstream source and instruments only its new
runtime copy. Each call records an explicit phase: initial generation, repair,
waveform analysis, retrieval, or optimization. Instrumentation does not enable
unsupported tasks or retrieval/sizing workflows. The manifest records original
and instrumented runner hashes. Text and waveform calls are both counted.

Inspect a run without making inference requests:

```sh
python3 baselines/analogcoder_pro/status.py runs/analogcoder_pro/baseline-qwen35-9b-28tasks
python3 -m usage_accounting.cli aggregate runs/analogcoder_pro/baseline-qwen35-9b-28tasks
```

`status.py` reads the saved records. `aggregate` rebuilds derived files under
`usage/`. The existing `report.py <run-directory>` command incorporates usage into
`REPORT.md`; it deliberately rewrites that report only when explicitly invoked.

## Existing experiments

Backfill saved native Ollama Pro calls at the pinned upstream revision:

```sh
python3 -m usage_accounting.cli backfill runs/analogcoder_pro/pilot-qwen35-9b
python3 -m usage_accounting.cli backfill runs/analogcoder_pro/baseline-qwen35-9b-28tasks
```

Backfill writes only inside each run's `usage/` directory. It preserves raw API
files, manifests, results, reports, checkers, and generated circuits. Repeating it
does not duplicate requests. Historical phases are explicitly labeled inferred;
ambiguous phases remain unknown. The original runner's live records can be
aggregated, but its old unstructured logs are not supported by this backfiller.

Update only the generated usage block under a matching experiment entry:

```sh
python3 -m usage_accounting.cli log-update runs/analogcoder_pro/baseline-qwen35-9b-28tasks --log EXPERIMENT_LOG.md
```

The command uses the run directory name by default. `--run-name` selects a
different existing `## Run NNN: <run-name>` heading. Other prose is preserved.

## Output files

| Output under a run directory | Contents |
| --- | --- |
| `usage/calls/task_*/trial_*/*.json` | Canonical per-call lifecycle, provider evidence, identity, normalized tokens, timings, stage, and component spans. |
| `usage/summary.json` | Latest totals, coverage, per-stage/task/model groups, component estimates, and cost assumptions. |
| `usage/calls.csv` | One row per call, including cache reuse, throughput, and API cost subtotal/completeness. |
| `usage/by_stage.csv`, `usage/by_task.csv` | Grouped token/cache/API cost breakdowns. |
| `usage/components.csv`, `usage/by_component.csv` | Component spans and category totals; unknown counts are empty, never invented zeroes. |
| `usage/components.json` | Attribution details, including signed reconciliation differences when estimated. |
| `usage/pricing_snapshot.json` | Assumptions for the latest estimate. |
| `usage/estimates/<pricing-hash>/<snapshot-hash>/` | Immutable prior summaries, prices, and component attribution. |

JSON and CSV views are replaced atomically. Individual files are consistent;
several derived files may describe adjacent snapshots during an active run. Use
the canonical call records or a single JSON summary for live consumption.

## Meaning of the metrics

Token totals come from provider responses, including failed/truncated requests
that returned usage. A timeout without a response remains unknown. Coverage
fields distinguish an observed subtotal from a fully measured total.

For Ollama, cached input is `prompt_eval_cached_count`; uncached input is total
input minus cached input. Run cache reuse is `sum(cached) / sum(input)` over the
same eligible requests. It is not an average of request percentages and is not a
hardware cache hit rate. Reports also show eligible calls and input-token coverage.
The Pro launcher reads this field from the native HTTP response. The original
runner does not receive it; see [Original AnalogCoder](#original-analogcoder).

Prefill/decode durations are converted from Ollama nanoseconds. Prefill throughput
uses uncached prompt tokens, while decode throughput uses output tokens. Exact
time to first token is unavailable for this nonstreaming client.

Known template sections are partitioned into instructions, examples, task
specification, and background spans. Other messages distinguish system text,
assistant history, prior feedback, latest diagnostics, and waveform text/images.
Unrecognized templates retain an unseparated category. All spans preserve the
outgoing message content exactly; resubmitted history counts on every request.

### Optional component token estimates

Exact stage totals work without a tokenizer. Fine component token counts default
to unknown because the provider does not return them. An optional local
`tokenizer.json` can produce per-string estimates. This requires the optional
`tokenizers` Python package, which the framework does not install automatically.

Create a JSON configuration with these fields:

```json
{
  "identity": "your-local-tokenizer-version",
  "model_digest": "exact digest from the run manifest",
  "tokenizer_json": "tokenizer.json",
  "sha256": "SHA-256 of tokenizer.json",
  "chat_template_identity": "optional template identifier"
}
```

The asset path is relative to the configuration file. Only matching model digests
are eligible, and the tokenizer file's checksum must match. The binding is
user-supplied provenance, not proof that the provider uses an identical tokenizer.
No assets are downloaded.

For a new local run, pass `--usage-tokenizer-config <config.json>`. For an existing
run, use `aggregate <run> --tokenizer-config <config.json>` or the same option with
`backfill`. Reaggregation with this option writes estimated component exports and
a new immutable snapshot without replacing provider token counts. Repeat the
option when regenerating those historical estimates.

All per-string counts remain labeled estimated: chat-template overhead, token
boundaries, context truncation, vision preprocessing, and reasoning splits can
prevent reconciliation. Signed differences are reported; they are not clamped.
Image base64 length is never treated as token usage. Component-level cache hits
and costs are not inferred from character spans.

## Cost configuration

Local API charges are zero for a recognized loopback Ollama endpoint and a local
model. Remote/explicit cloud model billing is unknown unless configured. Hardware
and electricity costs remain unknown without your assumptions.

Copy [the example configuration](../config/usage_pricing.example.json), then add
the applicable values. A configuration can contain:

```json
{
  "currency": "USD",
  "api_rates": [],
  "local": {
    "time_scope": "completed_attempt_wall",
    "power_watts": 100,
    "electricity_per_kwh": "0.15"
  }
}
```

The numbers above illustrate arithmetic, not measured Mac power or a recommended
electricity tariff. `machine_per_hour` is an alternative independent estimate.
Electricity and machine estimates are not automatically added together. New runs
include attempt intervals; overlapping intervals are merged before estimating
run compute cost. Historical Pro runs use their known sequential attempt times.

Each optional `api_rates` entry requires `provider`, `model`, `effective_date`, and
applicable `uncached_input_per_million`, `cached_input_per_million`,
`cache_write_per_million`, and `output_per_million` values. Rates use the outer
currency; mixed currencies and ambiguous model entries are rejected. No commercial
prices are bundled. Supported cache schemas are Ollama, OpenAI Chat Completions,
and DeepSeek hit/miss fields. Arbitrary compatible endpoints retain unknown cache
billing semantics. Unknown rates/counts produce a subtotal with an unknown remainder.

Pass `--usage-pricing <prices.json>` to the Pro launcher, or
`--pricing <prices.json>` to offline commands. Cost estimates are separate from
provider invoices. Cost per accepted circuit includes unsuccessful attempts in
the same completed-attempt cohort; with no acceptances it is unknown. In-progress
costs are included in total observed spend and reported separately from that cohort.

## Original AnalogCoder

Telemetry is opt-in to preserve existing command behavior:

```sh
.venv/bin/python gpt_run.py --model qwen3.5:9b --task_id 1 --num_per_task 1 --usage-dir runs/original_usage
```

Each invocation creates a unique child directory. The optional `--usage-pricing`
argument requires `--usage-dir`. Provider responses and payloads pass through
unchanged. Existing hardcoded money-quota decisions remain a separate legacy
estimate; this feature does not replace them. Hidden SDK HTTP retries are labeled
unknown rather than represented as fully observed transport attempts. Acceptance
and compute-cost reconciliation for this legacy adapter remain unavailable until
its task outcomes/intervals are exported; API usage and configured API prices work.

The Ollama path of `gpt_run.py` imports the `ollama` Python package, which is not
in `baselines/analogcoder_pro/requirements.lock`. Install it into the environment
before running the command above (`uv pip install --python .venv/bin/python ollama`).

Limitation: original-runner Ollama records have no cache counts. `ollama.chat`
returns a pydantic `ChatResponse`, and its schema (checked with ollama-python
0.6.3) does not declare `prompt_eval_cached_count`. Pydantic discards the field
during parsing, before the adapter receives the response. The saved raw response
therefore lacks it, `cached_input_tokens` and `uncached_input_tokens` stay unknown,
and the run's cache reuse rate is unknown with zero eligible calls. Input, output,
and timing fields are unaffected. The adapter does not substitute a separate HTTP
transport because that would change the legacy runner's request behavior. For
Ollama cache measurements, use the Pro launcher, which reads the native HTTP
response.

## Validation

```sh
python3 -m unittest discover -s tests -v
```

The tests use portable metadata fixtures with original texts/images omitted. They
cover historical totals, phase wrappers, payload/seed preservation, failures,
partial data, prices, attribution, idempotence, atomic writes, and report/log
compatibility. They make no live model or cloud requests.
