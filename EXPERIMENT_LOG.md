# Experiment Log

This file records each AnalogCoder-Pro experiment and its observed results.
Dates use America/Chicago. Counts are taken from each run's saved `manifest.json`,
`results.json`, and native Ollama request/response files.

Raw-artifact links in this file are **local-only**: `runs/` is ignored by Git.
The summaries and generated usage tables below are committed for GitHub readers;
opening a raw report, manifest, API record, or simulator log requires the local
experiment directory.

## Run summary

| Run | Date | Status | Model | Passes / attempts | Failed attempts | Runner errors | Attempt wall time |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| [Pilot](#run-001-pilot-qwen35-9b) | 2026-10-14 | Completed | `qwen3.5:9b` | 3/3 (100.0%) | 0 | 0 | 3.52 min |
| [Full baseline](#run-002-baseline-qwen35-9b-28tasks) | 2026-10-14 | Completed | `qwen3.5:9b` | 14/28 (50.0%) | 14 | 0 | 136.85 min |
| [Instrumented review pilot](#run-003-review-pilot-20261016) | 2026-10-16 | Completed | `qwen3.5:9b` | 3/3 (100.0%) | 0 | 0 | 2.90 min |

`Completed` means all planned attempts finished, regardless of how many circuits
passed. A failed attempt exhausted its generation/repair budget. Runner errors
and timeouts are recorded separately. Passes mean acceptance by the unchanged
upstream checkers; they are not independent certification of circuit correctness.

The pilot repeats tasks included in the full baseline. Keep their scores as
separate experiment results rather than combining them into one benchmark score.
The two manifests also record different model digests despite using the same
`qwen3.5:9b` tag. The reason for that difference is not recorded; use the digest
below when identifying a model snapshot.

## Shared configuration

| Setting | Value |
| --- | --- |
| Framework | AnalogCoder-Pro public generation/repair workflow |
| Upstream revision | `05542af46020e5c37d5a7e3ca79da9f24626e1c9` |
| Serving | Local Ollama, `http://127.0.0.1:11434` |
| Model size / quantization | 9.7B parameters / Q4_K_M |
| Trials per task | 1 |
| Generation budget per attempt | Initial generation + at most 2 repairs |
| Temperature | 0.5 |
| Base seed | 42 |
| Context limit | 16,384 tokens |
| Output limit per request | 4,096 tokens |
| Separate thinking mode | Disabled |
| Waveform-vision feedback | Enabled; called when requested by the upstream repair workflow |
| Python / PySpice / ngspice | Python 3.10.20 / PySpice 1.5 / ngspice 47 |

An attempt can contain multiple model calls. Waveform analysis is an additional
call and is included in the API-call and token totals below. Runtime is the sum
of recorded per-attempt wall times.

## Run 001: pilot-qwen35-9b

- Date: 2026-10-14.
- Status: **Completed**.
- Purpose: Verify local model generation, simulation, and checker execution on a
  small task set before the full baseline.
- Model: `qwen3.5:9b`, 9.7B, Q4_K_M.
- Recorded model digest:
  `6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`.
- Tasks: 1 (common-source amplifier), 6 (NMOS inverter), and 10 (low-pass filter).
- Finished attempts: **3/3**.
- Passes: **3/3 (100.0%)**; first generation: **3**; after repair: **0**.
- Failed attempts: **0**. Runner errors/timeouts: **0**.
- API calls: **3**, including **0** waveform-vision calls.
- Tokens: **4,073 prompt + 3,258 output = 7,331 total**.
- Responses stopped at the output limit: **0**.
- Total attempt wall time: **211.253 seconds (3.52 minutes)**.
- Outcome: The three selected tasks passed. This pilot does not estimate the
  full benchmark's success rate.
- Evidence: [report](runs/analogcoder_pro/pilot-qwen35-9b/REPORT.md),
  [manifest](runs/analogcoder_pro/pilot-qwen35-9b/manifest.json),
  [results JSON](runs/analogcoder_pro/pilot-qwen35-9b/results.json),
  [results CSV](runs/analogcoder_pro/pilot-qwen35-9b/results.csv),
  [API records](runs/analogcoder_pro/pilot-qwen35-9b/api_calls/).

<!-- usage-accounting:pilot-qwen35-9b:start -->
### Usage accounting

Calls: 3. Token totals: complete.
Input: 4,073; cached: 847; uncached: 3,226; output: 3,258.
Prompt/KV cache token reuse rate: 20.80%; eligible calls: 3/3.
API cost known subtotal: 0 USD (complete).
Electricity estimate: unknown; machine estimate: unknown.
Component tokens are unavailable or explicitly estimated per string; character spans are not token counts. Chat framing and image-token attribution remain unallocated.

Stage token values below are observed subtotals; cache coverage is shown separately.

| Stage | Calls | Input | Cached input | Output | Cache eligible calls | API cost subtotal |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| initial_generation | 3 | 4,073 | 847 | 3,258 | 3 | 0 USD (complete) |

| Prompt component | Estimated tokens (observed subtotal) | Measured spans |
| --- | ---: | ---: |
| examples | unknown | 0/3 |
| system_instructions | unknown | 0/3 |
| task_specification | unknown | 0/3 |
| template_instructions | unknown | 0/9 |
<!-- usage-accounting:pilot-qwen35-9b:end -->

## Run 002: baseline-qwen35-9b-28tasks

- Date: 2026-10-14.
- Status: **Completed**.
- Purpose: Establish a first local-model baseline on all 28 selected generation
  tasks under one fixed configuration.
- Model: `qwen3.5:9b`, 9.7B, Q4_K_M.
- Recorded model digest:
  `c97eb11d70b1acdc88af01eef566c1fe4f7fbe93eb1afc06871132f293ff425a`.
- Tasks: 1-28, one attempt per task.
- Finished attempts: **28/28**.
- Passes: **14/28 (50.0%)**; first generation: **9**; after repair: **5**.
- Failed attempts: **14**. Runner errors/timeouts: **0**.
- API calls: **63**, including **1** waveform-vision call.
- Tokens: **231,860 prompt + 161,216 output = 393,076 total**.
- Responses stopped at the output limit: **20**, across **11 tasks**.
- Total attempt wall time: **8,211.132 seconds (136.85 minutes)**.
- Passed task IDs: **1, 2, 3, 4, 5, 6, 8, 10, 11, 12, 15, 16, 19, 26**.
- Failed task IDs: **7, 9, 13, 14, 17, 18, 20, 21, 22, 23, 24, 25, 27, 28**.
- Evidence: [full report and per-task status](runs/analogcoder_pro/baseline-qwen35-9b-28tasks/REPORT.md),
  [manifest](runs/analogcoder_pro/baseline-qwen35-9b-28tasks/manifest.json),
  [results JSON](runs/analogcoder_pro/baseline-qwen35-9b-28tasks/results.json),
  [results CSV](runs/analogcoder_pro/baseline-qwen35-9b-28tasks/results.csv),
  [verification audit](runs/analogcoder_pro/baseline-qwen35-9b-28tasks/verification.json),
  [API records](runs/analogcoder_pro/baseline-qwen35-9b-28tasks/api_calls/).

### Observations

- Ten of the 14 failed tasks experienced at least one truncated response.
  Tasks 13 and 23 hit the output limit on all three generations. Some responses
  ended before complete circuit code was returned, leading to empty-code
  execution errors. These outcomes cannot establish that the model is unable
  to design those circuits.
- Other observed errors included undefined PySpice units (`volt`, `pf`),
  duplicate element names, and unsupported API use (`connect`).
- The comparator checker expects a voltage source named `Vin`. The Schmitt
  checker assumes an existing input voltage source with a `vin` name prefix.
  These contracts affected evaluation and are documented in the saved logs.
- Task 12 passed after waveform analysis and repair, exercising the local
  model's image-input path.
- The audit verified all 28 attempt records, 63 responses, token totals,
  the launcher hash, and 77 unchanged upstream source/assets in the run workspace.
- This is a single-attempt local baseline with a 4,096-token output cap.
  Comparison with paper-reported Pass@1/Pass@5 requires matching the evaluation
  protocol. A higher-output-budget experiment should have a new run ID and
  preserve this run's results.

<!-- usage-accounting:baseline-qwen35-9b-28tasks:start -->
### Usage accounting

Calls: 63. Token totals: complete.
Input: 231,860; cached: 112,874; uncached: 118,986; output: 161,216.
Prompt/KV cache token reuse rate: 48.68%; eligible calls: 63/63.
API cost known subtotal: 0 USD (complete).
Electricity estimate: unknown; machine estimate: unknown.
Component tokens are unavailable or explicitly estimated per string; character spans are not token counts. Chat framing and image-token attribution remain unallocated.

Stage token values below are observed subtotals; cache coverage is shown separately.

| Stage | Calls | Input | Cached input | Output | Cache eligible calls | API cost subtotal |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| initial_generation | 28 | 35,148 | 19,945 | 72,668 | 28 | 0 USD (complete) |
| repair_generation | 34 | 195,960 | 92,929 | 88,220 | 34 | 0 USD (complete) |
| waveform_analysis | 1 | 752 | 0 | 328 | 1 | 0 USD (complete) |

| Prompt component | Estimated tokens (observed subtotal) | Measured spans |
| --- | ---: | ---: |
| examples | unknown | 0/62 |
| image | unknown | 0/1 |
| latest_diagnostics | unknown | 0/34 |
| prior_assistant_responses | unknown | 0/49 |
| prior_feedback | unknown | 0/15 |
| system_instructions | unknown | 0/63 |
| task_specification | unknown | 0/62 |
| template_instructions | unknown | 0/186 |
| waveform_text | unknown | 0/1 |
<!-- usage-accounting:baseline-qwen35-9b-28tasks:end -->

## Run 003: review-pilot-20261016

- Date: 2026-10-16.
- Status: **Completed**.
- Purpose: Review the live instrumented Pro launcher on the three pilot tasks.
  This is a separate smoke-test experiment, not an additional full-suite score.
- Model: `qwen3.5:9b`, 9.7B, Q4_K_M.
- Recorded model digest:
  `c97eb11d70b1acdc88af01eef566c1fe4f7fbe93eb1afc06871132f293ff425a`.
- Tasks: 1 (common-source amplifier), 6 (NMOS inverter), 10 (low-pass filter).
- Configuration: Same temperature, seed, context/output limits, generation budget,
  and thinking/vision settings as the shared configuration above.
- Instrumentation: `pro-stages-v1`, all five call sites patched in the runtime
  copy; original and runtime SHA-256 hashes are recorded in the manifest.
- Finished attempts: **3/3**.
- Passes: **3/3 (100.0%)**, all on the first generation.
- Failed attempts: **0**. Runner errors/timeouts: **0**.
- API calls: **3**, including **0** waveform-vision calls.
- Tokens: **4,073 prompt + 3,258 output = 7,331 total**.
- Cached input: **1,696**. Uncached input: **2,377**. Cache reuse: **41.64%**.
- Total attempt wall time: **174.268 seconds (2.90 minutes)**.
- Outcome: Explicitly labeled initial-generation calls and all three attempts
  completed successfully. Different cache state affects reuse; this result does
  not establish a model-quality improvement over the earlier pilot.
- Evidence (local only): [manifest](runs/analogcoder_pro/review-pilot-20261016/manifest.json),
  [results](runs/analogcoder_pro/review-pilot-20261016/results.json),
  [usage summary](runs/analogcoder_pro/review-pilot-20261016/usage/summary.json),
  [API records](runs/analogcoder_pro/review-pilot-20261016/api_calls/).

<!-- usage-accounting:review-pilot-20261016:start -->
### Usage accounting

Calls: 3. Token totals: complete.
Input: 4,073; cached: 1,696; uncached: 2,377; output: 3,258.
Prompt/KV cache token reuse rate: 41.64%; eligible calls: 3/3.
API cost known subtotal: 0 USD (complete).
Electricity estimate: unknown; machine estimate: unknown.
Component tokens are unavailable or explicitly estimated per string; character spans are not token counts. Chat framing and image-token attribution remain unallocated.

Stage token values below are observed subtotals; cache coverage is shown separately.

| Stage | Calls | Input | Cached input | Output | Cache eligible calls | API cost subtotal |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| initial_generation | 3 | 4,073 | 1,696 | 3,258 | 3 | 0 USD (complete) |

| Prompt component | Estimated tokens (observed subtotal) | Measured spans |
| --- | ---: | ---: |
| examples | unknown | 0/3 |
| system_instructions | unknown | 0/3 |
| task_specification | unknown | 0/3 |
| template_instructions | unknown | 0/9 |
<!-- usage-accounting:review-pilot-20261016:end -->

## Preparatory environment validation

Status: **Passed**. Model: **None; no LLM requests**.

| Check | Observed result |
| --- | --- |
| Voltage-divider operating point | 2.500000 V, matching the expected value |
| Known NMOS inverter | Accepted by the upstream inverter checker, exit 0 |
| Noninverting wire negative control | Rejected by the upstream inverter checker, exit 2 |

Evidence: [control results](runs/analogcoder_pro/environment-check/controls.json)
and [simulator log](runs/analogcoder_pro/environment-check/simulator_check.log).
These controls are not additional model-generated benchmark passes.

## Recording the next run

Append a new entry and summary-table row for each experiment. Use a unique run
ID and artifact directory. Record the exact model digest as well as its tag,
and update status and observed counts as the run progresses. Useful statuses
are `Planned`, `Running`, `Completed`, `Interrupted`, and `Error`; circuit
failures remain counts within the run rather than changing a completed run's
execution status.

```markdown
## Run NNN: <unique-run-id>

- Date:
- Status:
- Purpose / change from the previous run:
- Model tag, exact digest, parameter count, and quantization:
- Framework revision:
- Task IDs and trials per task:
- Temperature, seed, context/output limits, generation budget, thinking/vision:
- Finished attempts / planned attempts:
- Passes / finished attempts and percentage:
- First-generation passes / passes after repair:
- Failed attempts / runner errors / timeouts:
- API calls / vision calls / prompt and output tokens:
- Truncated responses:
- Total attempt wall time:
- Observations and limitations:
- Links to manifest, results, report, and raw logs:
```

Raw artifacts under `runs/` are local and excluded from Git. This Markdown log
retains the experiment summaries for version control. See the
[baseline instructions](baselines/analogcoder_pro/README.md) for execution commands.
