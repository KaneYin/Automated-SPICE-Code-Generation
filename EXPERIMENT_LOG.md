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
| [Five-mode sweep, stopped](#run-004-ctx-full_history-qwen35-9b-20261115) | 2026-11-15 | Interrupted | `qwen3.5:9b` | 7/8 finished (28 planned) | 1 | 0 | 23.58 min |
| [Context-mode smoke tests](#run-005-context-mode-smoke-tests-20261115) | 2026-11-15 | Completed | `qwen3.5:9b` | 2/4 (forced-repair runs 0/2 by design) | 2 | 0 | 9.68 min |
| [Context: full history](#run-006-ctx3-full_history-qwen35-9b-20261115-1714) | 2026-11-15 | Completed | `qwen3.5:9b` | 1/3 | 2 | 0 | 15.90 min |
| [Context: latest feedback](#run-007-ctx3-latest_feedback-qwen35-9b-20261115-1714) | 2026-11-15 | Completed | `qwen3.5:9b` | 1/3 | 2 | 0 | 16.51 min |
| [Context: LLM summary](#run-008-ctx3-llm_summary-qwen35-9b-20261115-1714) | 2026-11-15 | Completed | `qwen3.5:9b` | 2/3 | 1 | 0 | 17.32 min |
| [Context: structured state](#run-009-ctx3-structured_state-qwen35-9b-20261115-1714) | 2026-11-15 | Completed | `qwen3.5:9b` | 2/3 | 1 | 0 | 15.94 min |
| [Context: structured state + ledger](#run-010-ctx3-structured_ledger-qwen35-9b-20261115-1714) | 2026-11-15 | Completed | `qwen3.5:9b` | 1/3 | 2 | 0 | 15.41 min |

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

## Run 004: ctx-full_history-qwen35-9b-20261115

- Date: 2026-11-15.
- Status: **Interrupted** at the user's request, so that Ollama could be stopped.
- Purpose: First of a planned five-run sweep comparing repair-context modes on
  all 28 tasks (`--context-mode full_history`). The other four modes never started.
  The sweep was replaced by the three-task comparison in Runs 006–010.
- Model: `qwen3.5:9b`, digest `c97eb11d70b1acdc88af01eef566c1fe4f7fbe93eb1afc06871132f293ff425a`,
  Ollama 0.40.16.
- Configuration: same as the shared configuration above (vision enabled).
- Finished attempts: **8/28** (tasks 1–8). Passes: **7/8**; task 2 failed after
  three generations (no code, then a function-check failure). Task 2 passed on
  the first generation in Run 002, so single runs of the same task vary.
- Task 9 was running when the launcher was interrupted; its one unfinished call is
  recorded as `interrupted` with unknown usage.
- Finished-attempt tokens: **23,974 prompt + 27,309 output**, 10 API calls.
- Attempt wall time for the 8 finished tasks: **23.58 minutes**.
- This partial run is not a benchmark score and is not compared with Run 002.
- Evidence (local only): `runs/analogcoder_pro/ctx-full_history-qwen35-9b-20261115/`.

<!-- usage-accounting:ctx-full_history-qwen35-9b-20261115:start -->
### Usage accounting

Calls: 11. Token totals: partial observed subtotal.
Input: 23,974 (observed subtotal; 10/11 calls); cached: 15,172 (observed subtotal; 10/11 calls); uncached: 8,802 (observed subtotal; 10/11 calls); output: 27,309 (observed subtotal; 10/11 calls).
Prompt/KV cache token reuse rate: 63.29%; eligible calls: 10/11.
API cost known subtotal: 0 USD (complete).
Electricity estimate: unknown; machine estimate: unknown.
Component tokens are unavailable or explicitly estimated per string; character spans are not token counts. Chat framing and image-token attribution remain unallocated.

Stage token values below are observed subtotals; cache coverage is shown separately.

| Stage | Calls | Input | Cached input | Output | Cache eligible calls | API cost subtotal |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| initial_generation | 9 | 10,938 | 8,323 | 21,216 | 8 | 0 USD (complete) |
| repair_generation | 2 | 13,036 | 6,849 | 6,093 | 2 | 0 USD (complete) |

| Prompt component | Estimated tokens (observed subtotal) | Measured spans |
| --- | ---: | ---: |
| examples | unknown | 0/11 |
| latest_diagnostics | unknown | 0/2 |
| prior_assistant_responses | unknown | 0/3 |
| prior_feedback | unknown | 0/1 |
| system_instructions | unknown | 0/11 |
| task_specification | unknown | 0/11 |
| template_instructions | unknown | 0/33 |
<!-- usage-accounting:ctx-full_history-qwen35-9b-20261115:end -->

## Run 005: context-mode-smoke-tests-20261115

- Date: 2026-11-15.
- Status: **Completed**.
- Purpose: Check the new `structured_ledger` and `llm_summary` code paths with a
  live model before longer runs. Four one-task runs on task 7 (CMOS inverter).
- With the standard 4,096-token output cap, both modes passed task 7 on the first
  generation (1 call, 1,363 input + 3,584 output tokens each), so no repair
  request was sent. Task 7 failed all three generations in Run 002.
- To force repairs, both modes were rerun with a **512-token output cap**, which
  cuts every reply off before its code. Both failed after three generations, as
  intended:
  - `structured_ledger`: 3 calls. Repair requests were 1,462 and 1,471 input
    tokens and carried the derived state; the second set the repeated-failure flag.
  - `llm_summary`: 5 calls (3 generations + 2 summaries). Summary calls used 624
    and 1,166 input tokens and were recorded in the `context_summary` stage; no
    fallback occurred.
- These runs validate plumbing only. The 512-token runs are not comparable with
  any other experiment.
- Evidence (local only): `runs/analogcoder_pro/smoke-*-20261115-*`.

## Context-mode comparison: Runs 006–010

Five runs that differ only in `--context-mode`. Everything else matches the
shared configuration above: `qwen3.5:9b` (same digest as Run 002), temperature
0.5, seed 42, 16,384-token context, 4,096-token output cap, three generations
per attempt, vision enabled, one trial.

Tasks 14 (two-stage Miller amplifier), 18 (single-stage differential opamp),
and 24 (opamp integrator) were chosen because all three needed the full repair
budget in Run 002, with different failure types. A task that passes on the first
generation sends the same requests in every mode.

All five runs produced byte-identical first answers on all three tasks (3,691
input and 8,627 output tokens in each run). Differences therefore come from the
repair step. After the first repair the replies diverge, so later calls are not
paired across modes.

| Mode | Passed | Passing generation (14 / 18 / 24) | Calls | Input | Cached | Output | Total | Mean repair input |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `full_history` | 1/3 | 1 / – / – | 8 | 31,695 | 13,289 | 18,824 | 50,519 | 5,601 |
| `latest_feedback` | 1/3 | 2 / – / – | 9 | 28,399 | 18,855 | 20,270 | 48,669 | 4,118 |
| `llm_summary` | 2/3 | 2 / 1 / – | 13 | 27,513 | 6,361 | 20,748 | 48,261 | 2,366 |
| `structured_state` | 2/3 | 2 / 2 / – | 9 | 16,170 | 6,792 | 19,780 | 35,950 | 2,080 |
| `structured_ledger` | 1/3 | 1 / – / – | 8 | 14,289 | 9,649 | 19,195 | 33,484 | 2,120 |

Generation 0 is the initial answer; "–" means the task failed. `llm_summary`
calls include five summary calls (11,992 input + 1,052 output tokens). Its mean
repair input excludes them; adding them gives about 4,760 input tokens per repair.

Change relative to `full_history`:

| Mode | Repair-stage input | All input | Total tokens |
| --- | ---: | ---: | ---: |
| `latest_feedback` | −11.8% | −10.4% | −3.7% |
| `llm_summary` (summary calls included) | −14.9% | −13.2% | −4.5% |
| `structured_state` | −55.4% | −49.0% | −28.8% |
| `structured_ledger` | −62.2% | −54.9% | −33.7% |

Observations:

- **Structured modes keep repair requests small and flat.** In `full_history`, the
  second repair on tasks 18 and 24 reached 7,557 and 7,398 input tokens. Structured
  repair requests stayed between 1,450 and 2,695.
- **Dropping truncated replies matters most.** Task 18's first reply hit the
  4,096-token cap without code in every mode. The first repair request was 5,495
  input tokens in `full_history` and `latest_feedback`, which resend that reply,
  but 1,450–1,632 in the structured and summary modes, which do not.
- **The summary calls cancel the summary mode's savings.** Its repair calls were
  the second smallest (11,830 input), but the summary calls added 11,992 input
  tokens, mostly from reading earlier replies that were cut off at the cap.
- **Output is unchanged.** Output stayed between 18,824 and 20,748 tokens and is
  now 53–59% of the total in the structured modes. Context strategies reduce only
  input; truncated, looping replies are a separate problem.
- **Pass counts are inconclusive.** Every mode passed task 14 and failed task 24.
  Task 18 passed only in `llm_summary` and `structured_state`. With three tasks
  and one trial, this does not show that any mode changes success.
- **The ledger's extra features were not exercised.** No request rolled back and
  none carried a repeated-failure warning, so Run 010 effectively measured the
  structured state plus a short attempt list. Its task 14 passed one generation
  earlier than in Run 009 after the replies diverged, which is chance at n=1.
- Prompt-cache reuse (23–68%) depends on the server's cache state carried over
  from the previous run and is not compared between modes.

Reproduce the table from saved artifacts, without model calls:

```sh
P=runs/analogcoder_pro; S=qwen35-9b-20261115-1714
.venv/bin/python baselines/analogcoder_pro/compare_runs.py \
  $P/ctx3-full_history-$S $P/ctx3-latest_feedback-$S $P/ctx3-llm_summary-$S \
  $P/ctx3-structured_state-$S $P/ctx3-structured_ledger-$S
```

Local comparison export: `runs/analogcoder_pro/ctx3-comparison-20261115-1714.json`.

## Run 006: ctx3-full_history-qwen35-9b-20261115-1714

- Date: 2026-11-15. Status: **Completed**. Part of the
  [context-mode comparison](#context-mode-comparison-runs-006010).
- Mode: `--context-mode full_history`. Upstream behavior: every earlier answer and feedback message is resent.
- Tasks 14, 18, 24; one trial; settings as in the comparison above.
- Task 14 passed at generation 1 (one repair after a Python error). Task 18 failed: no code (truncated), then a node-naming error. Task 24 failed: Python error, then no code (truncated).
- Runner errors/timeouts: **0**.
- Evidence (local only): `runs/analogcoder_pro/ctx3-full_history-qwen35-9b-20261115-1714/`.

<!-- usage-accounting:ctx3-full_history-qwen35-9b-20261115-1714:start -->
### Usage accounting

Calls: 8. Token totals: complete.
Input: 31,695; cached: 13,289; uncached: 18,406; output: 18,824.
Prompt/KV cache token reuse rate: 41.93%; eligible calls: 8/8.
API cost known subtotal: 0 USD (complete).
Electricity estimate: unknown; machine estimate: unknown.
Component tokens are unavailable or explicitly estimated per string; character spans are not token counts. Chat framing and image-token attribution remain unallocated.

Stage token values below are observed subtotals; cache coverage is shown separately.

| Stage | Calls | Input | Cached input | Output | Cache eligible calls | API cost subtotal |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| initial_generation | 3 | 3,691 | 846 | 8,627 | 3 | 0 USD (complete) |
| repair_generation | 5 | 28,004 | 12,443 | 10,197 | 5 | 0 USD (complete) |

| Prompt component | Estimated tokens (observed subtotal) | Measured spans |
| --- | ---: | ---: |
| examples | unknown | 0/8 |
| latest_diagnostics | unknown | 0/5 |
| prior_assistant_responses | unknown | 0/7 |
| prior_feedback | unknown | 0/2 |
| system_instructions | unknown | 0/8 |
| task_specification | unknown | 0/8 |
| template_instructions | unknown | 0/24 |
<!-- usage-accounting:ctx3-full_history-qwen35-9b-20261115-1714:end -->

## Run 007: ctx3-latest_feedback-qwen35-9b-20261115-1714

- Date: 2026-11-15. Status: **Completed**. Part of the
  [context-mode comparison](#context-mode-comparison-runs-006010).
- Mode: `--context-mode latest_feedback`. Only the latest answer and feedback follow the task prompt.
- Tasks 14, 18, 24; one trial; settings as in the comparison above.
- Task 14 passed at generation 2 (two Python errors first). Task 18 failed: no code, then a node-naming error. Task 24 failed: Python error, then a simulation failure.
- Runner errors/timeouts: **0**.
- Evidence (local only): `runs/analogcoder_pro/ctx3-latest_feedback-qwen35-9b-20261115-1714/`.

<!-- usage-accounting:ctx3-latest_feedback-qwen35-9b-20261115-1714:start -->
### Usage accounting

Calls: 9. Token totals: complete.
Input: 28,399; cached: 18,855; uncached: 9,544; output: 20,270.
Prompt/KV cache token reuse rate: 66.39%; eligible calls: 9/9.
API cost known subtotal: 0 USD (complete).
Electricity estimate: unknown; machine estimate: unknown.
Component tokens are unavailable or explicitly estimated per string; character spans are not token counts. Chat framing and image-token attribution remain unallocated.

Stage token values below are observed subtotals; cache coverage is shown separately.

| Stage | Calls | Input | Cached input | Output | Cache eligible calls | API cost subtotal |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| initial_generation | 3 | 3,691 | 3,155 | 8,627 | 3 | 0 USD (complete) |
| repair_generation | 6 | 24,708 | 15,700 | 11,643 | 6 | 0 USD (complete) |

| Prompt component | Estimated tokens (observed subtotal) | Measured spans |
| --- | ---: | ---: |
| examples | unknown | 0/9 |
| latest_diagnostics | unknown | 0/6 |
| prior_assistant_responses | unknown | 0/6 |
| system_instructions | unknown | 0/9 |
| task_specification | unknown | 0/9 |
| template_instructions | unknown | 0/27 |
<!-- usage-accounting:ctx3-latest_feedback-qwen35-9b-20261115-1714:end -->

## Run 008: ctx3-llm_summary-qwen35-9b-20261115-1714

- Date: 2026-11-15. Status: **Completed**. Part of the
  [context-mode comparison](#context-mode-comparison-runs-006010).
- Mode: `--context-mode llm_summary`. A model-written summary of earlier attempts plus the latest code and feedback. Five extra summary calls.
- Tasks 14, 18, 24; one trial; settings as in the comparison above.
- Task 14 passed at generation 2. Task 18 passed at generation 1 after one repair following a truncated reply. Task 24 failed: Python error, then a simulation failure. No summary fell back.
- Runner errors/timeouts: **0**.
- Evidence (local only): `runs/analogcoder_pro/ctx3-llm_summary-qwen35-9b-20261115-1714/`.

<!-- usage-accounting:ctx3-llm_summary-qwen35-9b-20261115-1714:start -->
### Usage accounting

Calls: 13. Token totals: complete.
Input: 27,513; cached: 6,361; uncached: 21,152; output: 20,748.
Prompt/KV cache token reuse rate: 23.12%; eligible calls: 13/13.
API cost known subtotal: 0 USD (complete).
Electricity estimate: unknown; machine estimate: unknown.
Component tokens are unavailable or explicitly estimated per string; character spans are not token counts. Chat framing and image-token attribution remain unallocated.

Stage token values below are observed subtotals; cache coverage is shown separately.

| Stage | Calls | Input | Cached input | Output | Cache eligible calls | API cost subtotal |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| context_summary | 5 | 11,992 | 205 | 1,052 | 5 | 0 USD (complete) |
| initial_generation | 3 | 3,691 | 3,155 | 8,627 | 3 | 0 USD (complete) |
| repair_generation | 5 | 11,830 | 3,001 | 11,069 | 5 | 0 USD (complete) |

| Prompt component | Estimated tokens (observed subtotal) | Measured spans |
| --- | ---: | ---: |
| examples | unknown | 0/3 |
| latest_diagnostics | unknown | 0/5 |
| system_instructions | unknown | 0/13 |
| task_specification | unknown | 0/3 |
| template_and_task_unseparated | unknown | 0/5 |
| template_instructions | unknown | 0/9 |
<!-- usage-accounting:ctx3-llm_summary-qwen35-9b-20261115-1714:end -->

## Run 009: ctx3-structured_state-qwen35-9b-20261115-1714

- Date: 2026-11-15. Status: **Completed**. Part of the
  [context-mode comparison](#context-mode-comparison-runs-006010).
- Mode: `--context-mode structured_state`. A structured state block (code, verified facts, failure class, trimmed evidence, instruction) replaces the history.
- Tasks 14, 18, 24; one trial; settings as in the comparison above.
- Task 14 passed at generation 2. Task 18 passed at generation 2 (no code, then a Python error). Task 24 failed: Python error, then a simulation failure.
- Runner errors/timeouts: **0**.
- Evidence (local only): `runs/analogcoder_pro/ctx3-structured_state-qwen35-9b-20261115-1714/`.

<!-- usage-accounting:ctx3-structured_state-qwen35-9b-20261115-1714:start -->
### Usage accounting

Calls: 9. Token totals: complete.
Input: 16,170; cached: 6,792; uncached: 9,378; output: 19,780.
Prompt/KV cache token reuse rate: 42.00%; eligible calls: 9/9.
API cost known subtotal: 0 USD (complete).
Electricity estimate: unknown; machine estimate: unknown.
Component tokens are unavailable or explicitly estimated per string; character spans are not token counts. Chat framing and image-token attribution remain unallocated.

Stage token values below are observed subtotals; cache coverage is shown separately.

| Stage | Calls | Input | Cached input | Output | Cache eligible calls | API cost subtotal |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| initial_generation | 3 | 3,691 | 1,966 | 8,627 | 3 | 0 USD (complete) |
| repair_generation | 6 | 12,479 | 4,826 | 11,153 | 6 | 0 USD (complete) |

| Prompt component | Estimated tokens (observed subtotal) | Measured spans |
| --- | ---: | ---: |
| examples | unknown | 0/3 |
| latest_diagnostics | unknown | 0/6 |
| system_instructions | unknown | 0/9 |
| task_specification | unknown | 0/3 |
| template_instructions | unknown | 0/9 |
<!-- usage-accounting:ctx3-structured_state-qwen35-9b-20261115-1714:end -->

## Run 010: ctx3-structured_ledger-qwen35-9b-20261115-1714

- Date: 2026-11-15. Status: **Completed**. Part of the
  [context-mode comparison](#context-mode-comparison-runs-006010).
- Mode: `--context-mode structured_ledger`. The structured state plus an attempt ledger, rollback, and repeated-failure warning.
- Tasks 14, 18, 24; one trial; settings as in the comparison above.
- Task 14 passed at generation 1. Task 18 failed: no code, then a Python error. Task 24 failed: Python error, then a simulation failure. No rollback or repeated-failure warning occurred.
- Runner errors/timeouts: **0**.
- Evidence (local only): `runs/analogcoder_pro/ctx3-structured_ledger-qwen35-9b-20261115-1714/`.

<!-- usage-accounting:ctx3-structured_ledger-qwen35-9b-20261115-1714:start -->
### Usage accounting

Calls: 8. Token totals: complete.
Input: 14,289; cached: 9,649; uncached: 4,640; output: 19,195.
Prompt/KV cache token reuse rate: 67.53%; eligible calls: 8/8.
API cost known subtotal: 0 USD (complete).
Electricity estimate: unknown; machine estimate: unknown.
Component tokens are unavailable or explicitly estimated per string; character spans are not token counts. Chat framing and image-token attribution remain unallocated.

Stage token values below are observed subtotals; cache coverage is shown separately.

| Stage | Calls | Input | Cached input | Output | Cache eligible calls | API cost subtotal |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| initial_generation | 3 | 3,691 | 3,429 | 8,627 | 3 | 0 USD (complete) |
| repair_generation | 5 | 10,598 | 6,220 | 10,568 | 5 | 0 USD (complete) |

| Prompt component | Estimated tokens (observed subtotal) | Measured spans |
| --- | ---: | ---: |
| examples | unknown | 0/3 |
| latest_diagnostics | unknown | 0/5 |
| system_instructions | unknown | 0/8 |
| task_specification | unknown | 0/3 |
| template_instructions | unknown | 0/9 |
<!-- usage-accounting:ctx3-structured_ledger-qwen35-9b-20261115-1714:end -->

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
