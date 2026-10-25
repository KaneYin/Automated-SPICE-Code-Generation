# Implementation notes

This log records implementation changes separately from model experiments.
The [experiment log](EXPERIMENT_LOG.md) retains model settings and circuit results.
The [usage accounting plan](docs/TOKEN_USAGE_IMPLEMENTATION_PLAN.md) defines the
feature milestones; the [usage guide](docs/USAGE_ACCOUNTING.md) gives commands.

## 2026-10-15: Token, cache, component, and cost accounting

Status: Implemented and validated offline, with the limitations below. No new
model inference was performed and no changes were committed or pushed.

The user requested a coding agent. A coding agent and two bounded integration
agents wrote the initial shared modules, Pro wrappers, legacy adapter, and
integration tests. Their sessions hit a usage limit before completion. The
primary agent completed the review fixes, offline CLI, regression coverage,
backfill, documentation, and implementation notes. This handoff did not change
the planned feature scope.

### Plan milestone 1: Shared records and offline backfill

Changed:

- Added `usage_accounting/schema.py`, `providers.py`, `recorder.py`, `aggregate.py`,
  and `cli.py`. Records have schema versions, stable call IDs, provenance, stage,
  raw-record references, nullable counts, timings, and lifecycle status.
- Added atomic per-worker JSON persistence and rebuildable CSV/JSON views.
  Started records become completed/error records; confirmed worker exit can mark
  unfinished records interrupted without fabricating usage.
- Added Ollama normalization, explicit OpenAI/DeepSeek cache schemas, validation,
  missing-versus-zero handling, and coverage-aware aggregation. Unsupported
  compatible cache semantics stay unknown.
- Added a pinned-native-Pro backfiller with deterministic historical IDs, request
  shape inference, duplicate/conflict detection, and recovery from raw responses
  saved before accounting finalization. Existing live phase labels take priority.

Why:

Per-call provider evidence is the only reliable accounting source across repairs,
vision calls, failures, and interruptions. Cumulative upstream token text files
omit vision and would double count if summed. Atomic, disjoint worker files avoid
shared append races and let reports be regenerated without inference. Nullable
measurements prevent timeouts or unsupported metrics from appearing free.

Validation:

- Portable metadata fixtures reproduce all 66 saved calls across the pilot/full
  run without depending on ignored local artifacts in CI.
- Backfill is idempotent and keeps stable IDs after moving/renaming a run.
- All 785 original upstream/historical artifact hashes matched after real backfill;
  all 77 pinned upstream source/asset hashes also matched.

### Plan milestone 2: Live Pro instrumentation

Changed:

- Added checksum-guarded `baselines/analogcoder_pro/instrumentation.py`. Five
  known call expressions in the copied runner receive context wrappers for
  optimization, initial generation, waveform analysis, repair, and retrieval.
- Integrated recording into `run_local.py` before transport dispatch and before
  answer extraction. Empty answers and output truncation retain provider usage.
- New manifests record schema, runtime patch/source hashes, price configuration,
  and optional tokenizer identity. New result rows include completeness and
  attempt intervals; worker shutdown finalizes pending lifecycle status.
- Updated report/status readers to expose the shared metrics and preserve
  compatibility with historical runs lacking telemetry.

Why:

Explicit call-site context survives transport retries and future workflow changes.
Call order alone cannot distinguish an initial retry from a repair. Instrumenting
only a checked runtime copy preserves the released source and makes the adaptation
auditable. Transport kwargs, prompts, seeds, and checker behavior stay unchanged.

Validation:

- AST integration tests exercise all five wrappers, phase/generation labels,
  original argument values, context cleanup, and rejection of an unknown checksum.
- Fake-transport tests verify native request options/seeds and persisted usage on
  empty answers, missing counters, and transport errors. No live inference needed.

### Plan milestone 3: Prompt-component attribution

Changed:

- Added `components.py` with nonoverlapping character spans for system text,
  recognized template instructions/examples/task/background, assistant history,
  prior feedback, current diagnostics, waveform text, and images.
- Added an optional local `tokenizer.json` adapter bound to an explicit model
  digest and asset checksum. New-run and offline flags can export per-string
  token estimates, attribution quality, and signed reconciliation differences.
- Added component detail/category exports and immutable attribution snapshots.

Why:

Prompt components are useful for diagnosing history growth, but the server reports
only whole-request counts. Characters, image base64, or an unrelated tokenizer
cannot supply exact model tokens. The default therefore preserves useful spans
and says unknown; optional tokenizer counts remain estimates even with matching
asset identity. Provider totals are never replaced by component sums.

Boundary/deviation:

Fine spans are derived from recognized existing template section markers rather
than changing upstream template rendering. Unrecognized templates stay explicitly
unseparated. Exact evaluated-prompt offsets, image/hidden-reasoning attribution,
component cache hits, and component billing remain unavailable. This implements
the plan's honest fallback rather than asserting unsupported exact counts.

### Plan milestone 4: Pricing, exports, and experiment log

Changed:

- Added `pricing.py`, validated price assumptions, decimal arithmetic, per-call
  and per-stage/task API cost subtotals/completeness, cohort cost per acceptance,
  and separate electricity/machine estimates. The example bundles no cloud rates.
- Price and usage changes create immutable hash-keyed estimates. Latest files are
  convenience views; previous cost assumptions/results remain inspectable.
- Added explicit generated-block upserts in `EXPERIMENT_LOG.md`. Handwritten prose
  is preserved. Existing reports/raw results are not rewritten by backfill.
- Added overlapping attempt-interval merging for compute estimates. The recorded
  historical Pro launcher is sequential, so its attempt wall sum is applicable.

Why:

Local API charges, electricity assumptions, and provider invoices are different
quantities. Failed attempts consume resources too. Cache-write categories must
not be billed twice, and unknown prices must not become zero. Separating canonical
usage from derived pricing permits repricing without modifying measurement data.

Boundary/deviation:

API costs are derived exports, not mutable fields embedded in canonical call
records. This keeps provider measurements stable across pricing revisions.
Hypothetical model-to-model cloud billing and legacy compute/acceptance cost are
not implemented. There is no implied equivalence between local and cloud tokens.

### Plan milestone 5: Original AnalogCoder adapter

Changed:

- Added `legacy.py` and opt-in `--usage-dir`/`--usage-pricing` integration in all
  five `gpt_run.py` transport call sites. Each invocation gets a unique run child.
- Native Ollama, OpenAI, and DeepSeek responses are retained without mutation.
  Initial/repair/retrieval stages carry task/trial/generation identity.
- Existing quota arithmetic and retry behavior remain unchanged. SDK-internal
  HTTP retry coverage is explicitly unknown; it is not fabricated from API calls.

Why:

One accounting core prevents the Pro and original runners from drifting. Opt-in
legacy telemetry preserves historical command behavior. Changing quota policy
would affect acceptance budgets and is a separate behavioral change.

Boundary:

Legacy Ollama records have unknown cache counts. ollama-python's `ChatResponse`
(checked at 0.6.3) does not declare `prompt_eval_cached_count`, so the field is
dropped before the adapter sees the response. Found during a 2026-10-16 review run.
See the [usage guide](docs/USAGE_ACCOUNTING.md#original-analogcoder).

### Review fixes and final validation

Review added independent cache-subset checks, nonfinite timing rejection, partial
cache labels, grouped costs, immutable price history, live/backfill duplicate
protection, pending-response recovery, and remote/cloud billing uncertainty.
It also added portable fixtures, read/write race coverage, report/status tests
from an unrelated cwd, and generated-log preservation/idempotence checks.

The validation command is `python3 -m unittest discover -s tests -v`: 24 tests
passed. The optional real tokenizer-file backend was not exercised because no
matching local asset was configured; its estimation interface was tested with a
small fake tokenizer. No circuit success improvement is claimed by telemetry.

| Saved run | Calls | Input | Cached input | Uncached input | Output | Reuse |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Pilot | 3 | 4,073 | 847 | 3,226 | 3,258 | 20.80% |
| Full baseline | 63 | 231,860 | 112,874 | 118,986 | 161,216 | 48.68% |

Circuit results remain 3/3 and 14/28. Local API charges are 0 USD; electricity and
machine estimates remain unknown because no power or hourly-rate assumptions
were supplied. Historical phases are inferred; new instrumented phases are
explicit. A new end-to-end live model run remains outside this telemetry change.

## 2026-10-25: Local-model testing documentation and GitHub publication

Changed:

- Appended a local-model testing guide at the end of the root README. It covers
  setup, exact Ollama tags, a three-task pilot, the 28-task suite, a sequential
  model sweep, report/accounting commands, and explicit output directories.
- Documented where raw logs, console output, manifests, generated circuits,
  normalized usage, experiment summaries, and implementation notes belong.
- Added the existing October 16 instrumented review pilot to `EXPERIMENT_LOG.md`
  and labeled raw-artifact links as local-only. No new inference was requested.

Why:

Each invocation needs an independent run directory so changing models never
overwrites evidence. Equal text-only budgets provide a usable comparison when
some models have no vision. The documentation distinguishes that condition from
the earlier vision-enabled baseline and distinguishes experiment outcomes from
implementation changes. Capturing console output beside the run avoids creating
the `--out` directory before the launcher's own existence check.

Publication scope: framework code, pinned upstream files/provenance, dependency
lock, tests/portable fixtures, configuration example, documentation, and Markdown
summaries. Raw runs and local environments remain excluded from Git. The missing
review entry was reconstructed from its saved manifest, results, and usage summary;
its 3/3 outcome and 41.64% reuse remain separate from the full baseline.

Validation: command flags checked against the launcher, shell examples checked
for syntax, the offline unit suite and whitespace checks run before commit, and
the configured Git author verified as `KaneYin <yinkunq@gmail.com>`.
All 24 tests passed, and eight README command blocks passed Bash/Zsh syntax
checks. The staged project-owned changes passed the whitespace check. The pinned
upstream snapshot contains inherited whitespace warnings and is intentionally
preserved byte-for-byte; its 77 file hashes were verified before publication.
