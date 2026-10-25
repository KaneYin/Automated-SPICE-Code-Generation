# Token usage, cache reuse, and cost accounting implementation plan

Status: Implemented with documented boundaries. This document preserves the
original implementation plan. See [implementation notes](../IMPLEMENTATION_LOG.md)
for milestone outcomes, rationale, validation, and deviations, and the
[usage guide](USAGE_ACCOUNTING.md) for supported commands.
Prepared: 2026-10-15. Primary target: the local AnalogCoder-Pro launcher.

## Goal and scope

Measure every actual model request, aggregate usage by framework stage and task,
attribute prompt components where supportable, and estimate costs with explicit
assumptions. Reuse the accounting core in the original AnalogCoder runner.

Implement telemetry without changing prompts, model options, seed progression,
retry behavior, supported tasks, checkers, or acceptance decisions. Cache tuning,
context pruning, streaming, budget enforcement changes, new providers, and another
28-task inference run are separate work. Retrieval and sizing instrumentation
must not enable unavailable upstream functionality.

## Source review and integration points

Paths below are relative to the repository root. Line numbers describe the current
source snapshot and are navigation aids, not patch anchors.

| Source | Current behavior | Planned change |
| --- | --- | --- |
| `baselines/analogcoder_pro/run_local.py:89` | One Ollama adapter handles text and vision; raw responses are saved, but normalized usage drops cache data. | Record lifecycle, context, normalized usage, and timing at the transport boundary. |
| `baselines/analogcoder_pro/run_local.py:153` | Workers share a completions adapter across upstream clients. | Give every worker a recorder and bind run/task/trial identity. |
| `baselines/analogcoder_pro/run_local.py:182` and `:293` | Parent sums prompt/output fields, substituting zero for missing responses. | Use the shared aggregator, preserve legacy result fields, add completeness metadata. |
| `baselines/analogcoder_pro/upstream/run.py:779,912,1227,1284,1364` | Optimization, initial generation, vision, repair, and retrieval are separate call sites. Vision is omitted from upstream cumulative token counters. | Tag all five sites in the runtime copy; use call records as the accounting authority. |
| `baselines/analogcoder_pro/upstream/run.py:834-885,1179-1279` | Templates, task fields, examples, and diagnostics are concatenated into prompts. | Add sidecar component spans while preserving the rendered text. |
| `baselines/analogcoder_pro/report.py` and `status.py` | Report task results, aggregate tokens, truncation, and pending requests. | Render usage/cache/cost summaries, coverage, and active call stage. |
| `gpt_run.py:811,833,1208,1228,1302` | Separate Ollama/OpenAI call paths; token accounting is mostly GPT-specific and prices are hardcoded. | Route accounting through the same recorder and provider normalizers. Keep existing quota/termination behavior unchanged in this feature. |
| `EXPERIMENT_LOG.md` | Handwritten experiment narrative and result summaries. | Update only marked generated usage blocks keyed by run ID. |

The pinned `upstream/` directory and existing run workspaces remain unchanged.
New runs receive a checksum-guarded instrumentation patch in their copied
workspace. Use unique source anchors and expected replacement counts, parse the
patched source, and fail before model requests if the pinned source no longer
matches. Record original/runtime source hashes and instrumentation version in
the manifest. Do not use call-stack inspection or call order as live stage labels.

## Proposed file layout

```text
usage_accounting/
    __init__.py
    schema.py          # Versioned record types and validation
    recorder.py        # Atomic request lifecycle persistence
    providers.py       # Ollama and supported OpenAI-compatible normalization
    aggregate.py       # Shared totals, coverage, grouping, reconciliation
    pricing.py         # Decimal arithmetic and configured cost assumptions
    components.py      # Prompt spans, tokenizer adapters, attribution quality
    cli.py             # Offline backfill and generated experiment-log blocks
baselines/analogcoder_pro/instrumentation.py
config/usage_pricing.example.json
tests/test_usage_accounting.py
tests/test_usage_integration.py
tests/fixtures/usage/  # Small metadata fixtures; no image payload copies
```

Keep the accounting core independent of OpenAI, Ollama, PySpice, and NumPy.
Use the Python standard library initially. Existing script entry points must work
from the documented repository-root commands and absolute paths; establish the
repository import path explicitly rather than depending on the worker's cwd.

## Data contract

Each call has one canonical JSON record under
`usage/calls/task_<id>/trial_<n>/call_<sequence>.json`. Write to a temporary file
in the same directory and atomically replace it. Workers own distinct paths;
the parent only reads them. CSV/summary files are derived artifacts, never a
second source of usage truth.

| Group | Required fields or rules |
| --- | --- |
| Identity | `schema_version`, `run_id`, `call_id`, `task_id`, `trial_id`, worker call sequence. Stable IDs survive backfill/reaggregation. |
| Stage | `phase`, nullable `generation_index`, nullable `diagnoses_generation_index`, `phase_source` (`explicit`, `inferred`, `unknown`). Initial generation index is 0; vision references the candidate it diagnoses. Transport retries are distinct calls for the same generation. |
| Model | Provider, requested/returned model, digest when known, server version, nullable provider request ID. Do not apply one model's digest to another model. |
| Request | Start/end timestamps, request fingerprint, relative raw-record path, settings reference. Reuse existing raw payloads instead of duplicating base64 images. |
| Lifecycle | `started`, `completed`, `error`, `interrupted`, or `unknown`; finish reason and nullable error. A completed response can still contain an empty answer or fail circuit checks. |
| Usage | Nullable input, output, cached-read, cache-write, uncached-input, reasoning, image, and provider-total counts. Preserve raw usage fields and normalization version. |
| Timing | Client wall seconds and nullable server total/load/prefill/decode seconds, with source and original unit. |
| Attribution | Component spans/counts with method, tokenizer/template identity, and exact/estimated/unavailable quality. |
| Cost | Separate API, electricity, machine, and optional hypothetical API estimates; currency, assumptions/config hash, coverage, and unknown reason. |

Validate nonnegative counts and provider-specific subset relationships. Invalid
or unsupported fields are flagged and excluded from affected calculations;
never silently clamp them or turn them into zero. Reasoning/image counts may be
subsets of output/input counts, not additional tokens to sum again.

Persist `started` before sending the request. Persist reported usage even if
answer extraction subsequently fails. If a worker is killed, the parent marks
unfinished records interrupted after confirming worker exit. Client timeout does
not establish whether server work or billing stopped. Preserve unknown usage.

Legacy `prompt_tokens` and `completion_tokens` result fields remain available
as sums of observed values, alongside explicit completeness/coverage fields.
Reports label partial totals accordingly; provider-returned missing usage remains
nullable. Do not fabricate `.usage` values to make an unsupported backend appear
fully measured.

## Measurement definitions

### Tokens and cache

For the current Ollama records:

```text
P = prompt_eval_count
C = prompt_eval_cached_count
O = eval_count
uncached_input = P - C
call_cache_hit_rate = C / P                         # P > 0 and C known
run_cache_hit_rate = sum(C) / sum(P)                # same eligible call set
request_hit_fraction = calls(C > 0) / calls(C known)
```

Publish eligible/total call counts and input-token coverage with cache metrics.
If cache metadata is missing, report the ratio over the measured subset and
mark it partial. A measured zero is different from unavailable telemetry.
Never average per-call percentages or interpret `keep_alive` as proof of a hit.

Name the metric "prompt/KV cache token reuse rate". It measures reported prompt
reuse, not hardware cache performance or the fraction of all attention lookups
served from KV memory. Per-component cache hits remain unavailable unless the
backend exposes token-level attribution or a verified prefix mapping supports it.

Current Ollama durations are nanoseconds. Convert once during normalization.
Uncached prefill throughput is `(P-C) / prefill_seconds`; decode throughput is
`O / decode_seconds`, when the necessary counts/durations are valid. Client wall
time, server timings, task duration, and run elapsed time are distinct metrics.
The current nonstreaming client does not measure exact time to first token.

### Prompt components

Use nonoverlapping leaf categories: system instructions, template instructions,
examples, task specification, retrieved/background material, prior assistant
responses, prior feedback, latest diagnostics, waveform text, and protocol or
unattributed overhead. Attach message index and character offsets without changing
the provider payload. Repeated history is counted each time it is submitted;
unique text volume can be a separate diagnostic, not the usage total.

First implement coarse message-level attribution. Then add spans at the template
substitution and feedback construction points. Assert byte-identical rendered
messages before and after instrumentation.

Use the matching model tokenizer and chat template only when their identity is
verified. Assign boundary-crossing tokens consistently when exact token offsets
are available. If only per-string tokenization is available, label component
counts estimates, expose signed reconciliation differences, and keep provider
totals authoritative. Context truncation or image processing can prevent an exact
mapping to the evaluated prompt. Do not count image base64 characters as tokens.
Do not claim exact plan-versus-code or thinking-versus-answer counts without
appropriate tokenizer/provider support.

### Costs

For the local Ollama endpoint, record API charges as zero. Electricity and
machine cost stay unknown until configured. Accept either average power plus
electricity price, or a machine hourly rate, with an explicit time scope:

```text
electricity_cost = power_watts / 1000 * elapsed_seconds / 3600 * price_per_kwh
machine_cost = elapsed_seconds / 3600 * hourly_rate
```

These are estimates, not measured energy. Keep the two estimates separate unless
the configuration explicitly establishes nonoverlapping costs. Compute run-level
wall-based costs once; summing overlapping requests must not multiply run cost.
Attribute simulation time only in a clearly labeled end-to-end estimate.

Cloud pricing is optional configuration, keyed by provider/model, currency,
effective date, and price per million tokens for disjoint billing categories.
Provider adapters define whether reported cached reads/writes are included in
input totals before applying a formula. Never apply one provider's semantics to
all compatible endpoints. Missing rates or required counts yield a partial known
subtotal and unknown remainder. Do not hardcode current commercial prices.

Record a canonical pricing-config hash and use decimal arithmetic. A hypothetical
cloud estimate for local tokens must be labeled hypothetical and use an explicit
model/rate mapping, rather than presenting it as an incurred bill. Pricing
changes can regenerate an estimate without changing raw calls or prior estimates.

Cost per accepted circuit includes costs from failed attempts and repairs in the
numerator, using the same completed-attempt cohort as the acceptance denominator.
Report interrupted/in-progress costs separately and include them in the full run
spend. With no acceptances, cost per accepted circuit is null.

## Deliverables in dependency order

### 1. Normalization and offline backfill

- Implement schema, provider normalization, atomic persistence, and aggregation.
- Add `python -m usage_accounting.cli backfill <run-directory>` (proposed CLI).
- Read existing native API files; write only a new `usage/` subtree. Preserve raw
  requests, results, original manifests, verification files, and workspaces.
- Assign deterministic call IDs from run identity and relative raw-record path.
  Reject duplicate IDs with conflicting content. Repeating backfill is idempotent.
- Infer phases only for supported historical request shapes. Mark provenance as
  inferred; ambiguous calls remain unknown. Do not treat every text call after
  call 1 as repair, because initial requests can be retried at the transport layer.
- Extract small response/role metadata fixtures from the existing runs for tests.
  The full ignored run directories are optional reconciliation inputs, not CI
  dependencies.

### 2. Live Pro instrumentation

- Add explicit context at all five call sites in the copied runtime source.
- Record each transport invocation, including automatic retry invocations, with
  unchanged request payload and seed progression.
- Add schema/instrumentation/model/config provenance to new run manifests.
- Aggregate from saved call records after each attempt and during status reads.
  Clearly label partial snapshots when a request or attempt is active.
- A persistence failure before dispatch stops the unrecordable request. Errors
  after receiving a response retain the raw response for reconciliation.

### 3. Prompt-component attribution

- Add coarse role/message counts and then template/diagnostic spans.
- Provide a tokenizer interface and an explicit unavailable fallback. Resolve
  tokenizer/template identity before enabling claims of exact counts.
- Store attribution quality, evaluated-prompt mapping coverage, and reconciliation
  differences. Exact request/stage metrics remain usable without this dependency.

### 4. Pricing and presentation

- Add a validated example configuration with no invented cloud rates. Add
  proposed `--usage-pricing <path>` support to the local launcher.
- Produce `usage/summary.json`, `usage/calls.csv`, `usage/by_stage.csv`,
  `usage/by_task.csv`, and `usage/components.csv` when attribution exists.
- Render token/cache/cost tables and coverage in reports and concise status.
- Provide an explicit log-update command that upserts a generated usage block
  under the matching run entry in `EXPERIMENT_LOG.md`, preserving all other text.
- Keep schema-version handling backward compatible and report unsupported future
  schemas clearly rather than silently dropping fields.

### 5. Original AnalogCoder integration

- Instrument the original runner's native Ollama and OpenAI-compatible call sites
  using the same recorder, phase labels, and aggregation rules.
- Add fixtures for each supported response shape, especially non-GPT usage.
- Keep legacy money-quota decisions unchanged for this feature. Replacement of
  quota enforcement requires its own behavioral change and tests; label legacy
  quota estimates separately from the new telemetry cost estimate.
- Document backend support and missing cache/component fields explicitly.

## Acceptance checks

Use offline tests first. No live provider call is required to pass the core work.

1. Reconcile the saved full run to exactly 63 calls: 28 initial, 34 repair, and
   1 waveform-analysis call; 231,860 input, 112,874 cached input, 118,986 uncached
   input, and 161,216 output tokens. Cache reuse is 48.68196325368757%.
2. Reconcile the pilot to 3 calls, 4,073 input, 847 cached input, 3,226 uncached
   input, and 3,258 output tokens. Its cache rate is independent of the full run.
3. Preserve 14/28 full-run and 3/3 pilot acceptance results and all original
   artifact hashes during backfill. A second backfill produces identical usage
   totals without duplicate calls.
4. Cover missing versus zero cache counts, zero denominators, weighted ratios,
   malformed counts, response errors, empty answers, output truncation, and killed
   workers. Test that partial coverage never appears as a complete measurement.
5. Verify atomic reads while another process writes, stable IDs after moving a
   run directory, duplicate/conflict detection, and safe active-run aggregation.
6. Verify each runtime patch anchor and phase with a fake transport. Compare
   outgoing messages/options/seeds and checker inputs against the uninstrumented
   path; only local metadata may differ. Verify pristine upstream hashes.
7. Test local API zero cost versus unknown compute cost, configured local cost,
   disjoint cloud billing categories, missing prices, currencies, price snapshots,
   and zero-success cost-per-acceptance handling using small hand-calculated cases.
8. Test prompt span reconstruction and boundary handling. Unavailable tokenizer,
   image details, or reasoning details must yield labeled unavailable/estimated
   components while leaving exact request totals intact.
9. Test generated experiment-log upserts twice and verify handwritten content is
   byte-identical. Existing report/status commands still accept historical runs.

Suggested implementation validation: standard-library `unittest` plus offline
baseline reconciliation. A short local live smoke test can follow implementation
if needed; another full-suite run is unnecessary for validating telemetry.

## Current evidence for reconciliation

The October 14 full-run raw responses contain `prompt_eval_cached_count` on all
63 calls, with every count between zero and total input. The existing run uses
local `qwen3.5:9b` (9.7B, Q4_K_M), not a verified 7B model.

| Historical phase (inferred) | Calls | Input | Cached input | Output |
| --- | ---: | ---: | ---: | ---: |
| Initial generation | 28 | 35,148 | 19,945 | 72,668 |
| Repair generation | 34 | 195,960 | 92,929 | 88,220 |
| Waveform analysis | 1 | 752 | 0 | 328 |
| Total | 63 | 231,860 | 112,874 | 161,216 |

Local evidence: [experiment log](../EXPERIMENT_LOG.md),
[raw calls](../runs/analogcoder_pro/baseline-qwen35-9b-28tasks/api_calls/),
[manifest](../runs/analogcoder_pro/baseline-qwen35-9b-28tasks/manifest.json),
and [results](../runs/analogcoder_pro/baseline-qwen35-9b-28tasks/results.json).
Raw run artifacts are ignored by Git; exported metadata fixtures must make the
accounting tests independently reproducible.
