# Repair-context strategies

A repair request can carry the previous attempts in five ways. Select one with
`--context-mode` on the local Pro launcher. The default, `full_history`, is the
unchanged upstream behavior.

```sh
.venv/bin/python baselines/analogcoder_pro/run_local.py \
  --model "$LOCAL_MODEL" --tasks all --trials 1 --max-generations 3 \
  --temperature 0.5 --seed 42 --context 16384 --max-tokens 4096 \
  --no-vision --context-mode structured_ledger --out "$RUN_DIR"
```

| Mode | What a repair request contains | Extra model calls |
| --- | --- | --- |
| `full_history` | Task prompt, then every earlier answer and feedback message | None |
| `latest_feedback` | Task prompt, the latest answer verbatim, the latest feedback | None |
| `llm_summary` | Task prompt, a model-written summary of earlier reasoning and feedback, the latest code, the latest feedback | One per repair |
| `structured_state` | Task prompt plus a state block: latest code, verified facts, failure layer and class, trimmed evidence, a layer-specific instruction | None |
| `structured_ledger` | The state block, plus a ledger of each attempt's change and outcome, rollback to the best candidate, and a repeated-failure warning | None |

Only requests in the `repair_generation` phase are rewritten. Initial
generation and waveform analysis are sent unchanged. The pinned upstream runner
is not modified: it still keeps its full conversation, and the launcher derives
the outgoing request from that conversation on every call.

## How the state is built

`context_engineering/state.py` derives every field from text the harness already
produced. No model call is involved.

- **Failure class and layer.** Upstream feedback is templated, so it maps to
  `NO_CODE`, `PYTHON_ERROR`, `TIMEOUT`, `SIMULATION_FAILURE`, `FLOATING_NODE`,
  `NODE_NAMING`, `OPERATING_POINT`, `DC_SWEEP_NO_RESPONSE`, `FUNCTION_CHECK`, or
  `UNKNOWN`. Each class belongs to a layer (`OUTPUT_FORMAT`, `PYTHON_API`,
  `NETLIST`, `BIAS`, `BEHAVIOR`) that selects the repair instruction.
- **Evidence.** Template boilerplate, absolute paths, and simulator version
  noise are removed. A traceback keeps its innermost frame and exception line.
  Evidence is capped at 15 lines.
- **Verified facts.** A failure late in the pipeline implies the earlier checks
  passed. A DC-sweep bias voltage reported by the harness is kept as a fact.
- **Ledger** (`structured_ledger`). Each entry is the statement-level diff from
  the previous candidate and the resulting failure.
- **Rollback** (`structured_ledger`). The candidate shown is the attempt that got
  furthest through the checks; ties go to the later attempt. The failure shown
  is the one that belongs to that candidate.
- **Repeated failure** (`structured_ledger`). When the last two attempts fail
  with the same signature, the instruction asks for a different approach.

The task prompt always comes first and the state last, so the prompt-cache
prefix stays stable. The task prompt already states the task, node names, and
Vdd, so the state block does not repeat them.

## What is recorded

- `manifest.json` records the mode under `config.context_mode` and
  `context_strategy`.
- Each rewritten call's file under `api_calls/` has a `context_strategy` entry
  with the mode, original and sent sizes, and the derived state.
- A summary call is saved as `call_NNN_summary.json` and recorded in usage
  accounting under the `context_summary` stage, so its tokens count toward the
  run. It uses its own seed; generation calls keep the same numbering and seeds
  in every mode.
- If a summary call fails or returns nothing, that repair falls back to
  `latest_feedback` and the call file records `"fallback"`.

## Comparing runs

Run each mode with identical settings into its own directory, then compare the
saved artifacts. No model calls are made.

```sh
.venv/bin/python baselines/analogcoder_pro/compare_runs.py RUN_A RUN_B ... --json comparison.json
```

The first directory is the reference for the identical-first-answer check. With
the same seed, the first answers usually match across modes, so differences come
from the repair step. The first results are Runs 006–010 in
[the experiment log](../EXPERIMENT_LOG.md#context-mode-comparison-runs-006010).

## Limitations

- Classification depends on the pinned upstream feedback templates. Unmatched
  feedback becomes `UNKNOWN` and is passed through as evidence.
- Affected nodes are filled only for floating-node and node-naming failures.
- The model's design reasoning is not carried in the structured modes.
- The ledger diff compares statement text, so a pure rename looks like a change.
- Prompt-component attribution labels a structured repair prompt as one
  `latest_diagnostics` span, including the task prompt it contains.
- `latest_feedback` keeps the latest answer verbatim, including a truncated one.

## Validation

```sh
.venv/bin/python -m unittest discover -s tests -v
```

`tests/test_context_engineering.py` covers classification, evidence trimming,
each strategy's output, rollback, fallback, and the launcher integration with a
fake transport. It makes no model requests.
