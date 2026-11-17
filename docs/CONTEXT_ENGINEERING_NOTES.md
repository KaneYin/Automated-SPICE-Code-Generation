# Context engineering for simulation-guided circuit repair: research notes

Status on 2026-11-16: implemented, tested offline, and measured in one small
live comparison (three tasks, one trial per mode). These notes record the idea,
the design, where each part lives in the code, the evidence so far, and the
related work. They are written to be the starting material for the method and
experiment sections of a paper.

Companion documents: [usage guide](CONTEXT_STRATEGIES.md),
[experiment log](../EXPERIMENT_LOG.md), [implementation log](../IMPLEMENTATION_LOG.md).

## 1. The contribution in one paragraph

AnalogCoder-style agents repair a failed circuit by appending the simulator's
complaint to a growing chat and asking the model to try again. We replace that
growing chat with a **structured repair state that the harness rebuilds from
scratch before every repair request**. The state holds only what the next fix
needs: the candidate code, what is already verified, the failure's layer and
class, trimmed evidence, and a ledger of what was tried. The harness derives
every field deterministically from text it already has, so maintaining the state
costs zero model tokens and cannot invent facts. In the first live comparison,
this cut repair-stage input tokens by 55–62% and total tokens by 29–34% against
the unchanged baseline, while a model-written summary saved almost nothing
because the summary calls cost as much as they saved.

A software analogy: the baseline debugs by re-reading the entire chat log of a
debugging session before each fix. Our method debugs from a bug ticket: current
code, failing check, error excerpt, and a list of fixes already tried.

## 2. The problem we measured

The baseline loop is in the pinned upstream runner. It appends each answer and
each feedback message to one list and resends the whole list
([`upstream/run.py:1019`](../baselines/analogcoder_pro/upstream/run.py#L1019),
[`upstream/run.py:1279`](../baselines/analogcoder_pro/upstream/run.py#L1279)).

Run 002 (28 tasks, `qwen3.5:9b`, full history) shows what that costs
([experiment log, Run 002](../EXPERIMENT_LOG.md#run-002-baseline-qwen35-9b-28tasks)):

| Observation in Run 002 | Value |
| --- | --- |
| Total tokens | 393,076 (231,860 input + 161,216 output) |
| Tokens spent on the 14 failed tasks | 307,155 (78%) |
| Share of input tokens used by repair calls | 195,960 of 231,860 (85%) |
| Responses cut off at the 4,096-token output cap | 20 of 63 |
| Input growth on task 13 across three calls | 1,354 → 5,475 → 9,593 |

Three failure patterns in the saved conversations motivated the design:

1. **Bad answers are resent.** A reply that loops until the output cap contains
   no code, yet it is appended and paid for again on every later call.
2. **Feedback names the wrong problem.** Task 7 failed with
   `NameError: name 'volt' is not defined`, a Python slip. The upstream template
   asked the model to "identify any structural errors in this circuit's
   topology". The model made the same error again.
3. **Nothing records what was tried.** The only memory of a failed fix is the
   full text of the failed answer.

## 3. Design principles

1. **State, not transcript.** Each repair request is one fresh prompt: the
   original task prompt followed by a state block. Earlier answers are never
   resent.
2. **The harness writes the state.** Every field comes from text the harness
   produced or received. No model call builds or updates the state.
3. **Route the instruction by failure layer.** A Python error, a broken netlist,
   a bias problem, and a wrong waveform need different instructions.
4. **Evidence, not logs.** The model sees the failing line and the verdict, with
   template text, absolute paths, and simulator noise removed.
5. **Remember attempts as change → outcome.** A ledger entry is the code diff
   and the failure it produced, not the model's own account of what it did.
6. **Keep the best candidate.** If a fix makes things worse, repair the earlier,
   better candidate instead.
7. **Stable prefix.** The task prompt always comes first and the state last, so
   the provider's prompt cache can reuse the prefix.
8. **Do not touch the baseline.** The pinned upstream runner is unmodified. The
   rewrite happens at the transport boundary, and the default mode sends
   byte-identical requests.

## 4. The five context modes

All five are selected with `--context-mode`
([`run_local.py:301`](../baselines/analogcoder_pro/run_local.py#L301)) and built
by one function, `build_context`
([`strategies.py:108`](../context_engineering/strategies.py#L108)).

| Mode | A repair request contains | Extra model calls | Role in the study |
| --- | --- | --- | --- |
| `full_history` | Task prompt and every earlier answer and feedback | None | Baseline (upstream behavior) |
| `latest_feedback` | Task prompt, the latest answer verbatim, the latest feedback | None | Simple truncation baseline, as in AutoChip's succinct mode |
| `llm_summary` | Task prompt, a model-written summary, the latest code, the latest feedback | One per repair | Compaction baseline |
| `structured_state` | Task prompt and the state block | None | Our method, core |
| `structured_ledger` | The state block plus attempt ledger, rollback, and repeated-failure warning | None | Our method, full |

## 5. How the structured state is built

All code is in [`context_engineering/state.py`](../context_engineering/state.py)
and [`context_engineering/strategies.py`](../context_engineering/strategies.py).
The package uses only the Python standard library.

### 5.1 Parse the conversation into attempts

`parse_attempts` ([`state.py:201`](../context_engineering/state.py#L201)) splits
the upstream message list into the task prefix and a list of `Attempt` records
([`state.py:86`](../context_engineering/state.py#L86)), one per answer/feedback
pair. The candidate code is the last fenced block of the answer, the same rule
the upstream runner uses (`extract_code`,
[`state.py:125`](../context_engineering/state.py#L125)). If the conversation
does not have the expected shape, the request is sent unchanged rather than
guessed at.

### 5.2 Classify the failure

`classify` ([`state.py:154`](../context_engineering/state.py#L154)) maps the
templated upstream feedback to a failure class. Each class has a layer
(`LAYER`, [`state.py:26`](../context_engineering/state.py#L26)) and a rank
(`RANK`, [`state.py:14`](../context_engineering/state.py#L14)). The rank says
how far the candidate got through the checks.

| Class | Layer | Rank | Meaning |
| --- | --- | ---: | --- |
| `NO_CODE` | `OUTPUT_FORMAT` | 0 | The reply had no complete code block |
| `PYTHON_ERROR`, `TIMEOUT`, `UNKNOWN` | `PYTHON_API` / `UNKNOWN` | 1 | The script itself did not run |
| `SIMULATION_FAILURE`, `FLOATING_NODE` | `NETLIST` | 2 | The script ran but the simulator could not solve the circuit |
| `NODE_NAMING` | `NETLIST` | 3 | Required input/output node names are missing |
| `OPERATING_POINT` | `BIAS` | 3 | Transistors are not in their intended operating regions |
| `DC_SWEEP_NO_RESPONSE`, `FUNCTION_CHECK` | `BEHAVIOR` | 4 | The circuit simulates but does not do its job |

Classification runs on the evidence after the template text is removed. This
matters because the upstream template itself contains the word "error"; an
early version misread checker output as a simulator failure for that reason.

### 5.3 Trim the evidence

Inside `classify`: template boilerplate is removed (`_BOILERPLATE`,
[`state.py:70`](../context_engineering/state.py#L70)), absolute paths become
file names, and simulator version noise is dropped. A traceback keeps only its
innermost frame and the exception line (`_traceback_evidence`,
[`state.py:142`](../context_engineering/state.py#L142)). Evidence is capped at
15 lines (`_clip`, [`state.py:133`](../context_engineering/state.py#L133)).

### 5.4 Verified facts

A failure at rank *r* implies the checks below *r* passed, so the state lists
them as things to keep working (`VERIFIED_BY_RANK`,
[`state.py:39`](../context_engineering/state.py#L39)). When the harness's DC
sweep reports a best input bias voltage, that value is kept as a fact.

### 5.5 Layer-specific instruction

The instruction is chosen by layer (`INSTRUCTION`,
[`state.py:45`](../context_engineering/state.py#L45)). For example, a
`PYTHON_API` failure gets: "This is a Python/PySpice usage error, not a circuit
topology problem. Fix the failing statement and keep the topology unchanged."

### 5.6 Ledger, rollback, repeated failure (`structured_ledger` only)

- **Ledger.** `describe_change`
  ([`state.py:234`](../context_engineering/state.py#L234)) diffs the
  circuit-building statements of consecutive candidates. Each ledger line is
  that diff and the failure that followed.
- **Rollback.** `best_attempt`
  ([`state.py:254`](../context_engineering/state.py#L254)) picks the attempt
  with the highest rank; ties go to the later attempt. The failure shown is the
  one belonging to the candidate shown
  ([`strategies.py:56`](../context_engineering/strategies.py#L56)).
- **Repeated failure.** Each attempt has a signature: class plus headline with
  numbers masked ([`state.py:120`](../context_engineering/state.py#L120)). When
  the last two signatures match, the instruction asks for a different approach
  (`repeated_failure`, [`state.py:262`](../context_engineering/state.py#L262)).

### 5.7 Assemble the prompt

`_state_block` ([`strategies.py:53`](../context_engineering/strategies.py#L53))
renders the state, and `_fresh_prompt`
([`strategies.py:101`](../context_engineering/strategies.py#L101)) appends it to
the task prompt. The task prompt already states the task, node names, and Vdd,
so the state does not repeat them.

A real state block from Run 010, task 18, third call (code elided):

```
## Repair state

ATTEMPT: 3 of 3

CANDIDATE (attempt 2):
<57 lines of code>

FAILURE: layer=PYTHON_API class=PYTHON_ERROR
EVIDENCE:
  File "p18_0_1.py", line 52, in <module>
    circuit.R('R_load', 'Vout', circuit.gnd, 1@TeraOhm) # High impedance load ...
NameError: name 'TeraOhm' is not defined

TRIED (do not repeat a change that did not help):
1. no code produced -> NO_CODE
2. wrote a new design -> PYTHON_ERROR: NameError: name 'TeraOhm' is not defined

INSTRUCTION: This is a Python/PySpice usage error, not a circuit topology problem.
Fix the failing statement and keep the topology unchanged. Rewrite the complete corrected code.
```

For this call the upstream conversation was 25,797 characters and the request
sent was 8,588 characters (2,695 input tokens). The same call position in the
`full_history` run was 7,557 input tokens.

## 6. The baselines we implemented for comparison

- **`latest_feedback`** keeps the last answer verbatim, including a truncated
  one. This is deliberate: it is the plain truncation baseline.
- **`llm_summary`** asks the same model for a summary of at most 150 words
  covering intended topology, errors seen, and fixes tried (`SUMMARY_PROMPT`,
  [`strategies.py:18`](../context_engineering/strategies.py#L18)). The summarizer
  sees reasoning and earlier feedback with code stripped (`summary_request`,
  [`strategies.py:34`](../context_engineering/strategies.py#L34)). The latest
  code and feedback are passed verbatim. If the summary call fails or is empty,
  that repair falls back to `latest_feedback` and the fallback is recorded.

## 7. Integration and fairness controls

- **Where the rewrite happens.** `OllamaCompletions.create`
  ([`run_local.py:145`](../baselines/analogcoder_pro/run_local.py#L145)) rewrites
  only requests in the `repair_generation` phase. Initial generation and
  waveform analysis are untouched.
- **Summary calls are counted.** `_summarize`
  ([`run_local.py:110`](../baselines/analogcoder_pro/run_local.py#L110)) records
  each summary call in a separate `context_summary` usage stage, so the summary
  mode pays for its own overhead in every total.
- **Same seeds in every mode.** Summary calls use their own seed and file name
  ([`run_local.py:120`](../baselines/analogcoder_pro/run_local.py#L120)), so
  generation calls keep identical numbering and seeds across modes
  ([`run_local.py:175`](../baselines/analogcoder_pro/run_local.py#L175)).
- **Audit trail.** Every rewritten call file stores the strategy and derived
  state ([`run_local.py:181`](../baselines/analogcoder_pro/run_local.py#L181));
  the manifest stores the mode
  ([`run_local.py:341`](../baselines/analogcoder_pro/run_local.py#L341)).
- **Comparison tool.** [`compare_runs.py`](../baselines/analogcoder_pro/compare_runs.py)
  rebuilds the result tables from saved runs without model calls and checks
  whether the runs share identical first answers.

## 8. Evidence so far

### 8.1 Offline tests

[`tests/test_context_engineering.py`](../tests/test_context_engineering.py) has
16 tests: classification and evidence trimming, each mode's output, rollback,
summary fallback, pass-through of unrecognized conversations, and launcher
integration with a fake transport (payload unchanged by default, only repair
requests rewritten, summary calls recorded without shifting seeds). The full
offline suite has 40 tests and passes.

### 8.2 Replay of the Run 002 conversations (no inference)

Feeding the 34 saved repair requests of Run 002 through each mode classified
every feedback message (14 `NO_CODE`, 12 `PYTHON_ERROR`, 4 `SIMULATION_FAILURE`,
3 `FUNCTION_CHECK`, 1 `OPERATING_POINT`). Request sizes in characters relative
to full history: `latest_feedback` 0.73, `llm_summary` 0.37 (placeholder
summary, summary-call input excluded), `structured_state` 0.31,
`structured_ledger` 0.33. One request would have rolled back and seven would
have carried a repeated-failure warning. This is a size estimate on old
conversations, not a prediction
([implementation log](../IMPLEMENTATION_LOG.md)).

### 8.3 Live comparison: Runs 006–010

Tasks 14, 18, and 24; one trial; `qwen3.5:9b`; settings identical to Run 002
except the mode. All five runs produced byte-identical first answers on all
three tasks, so differences come from the repair step
([experiment log](../EXPERIMENT_LOG.md#context-mode-comparison-runs-006010)).

| Mode | Passed | Calls | Input | Output | Total | Mean repair input | Total vs baseline |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `full_history` | 1/3 | 8 | 31,695 | 18,824 | 50,519 | 5,601 | — |
| `latest_feedback` | 1/3 | 9 | 28,399 | 20,270 | 48,669 | 4,118 | −3.7% |
| `llm_summary` | 2/3 | 13 | 27,513 | 20,748 | 48,261 | 2,366 | −4.5% |
| `structured_state` | 2/3 | 9 | 16,170 | 19,780 | 35,950 | 2,080 | −28.8% |
| `structured_ledger` | 1/3 | 8 | 14,289 | 19,195 | 33,484 | 2,120 | −33.7% |

Repair-stage input alone fell by 55.4% (`structured_state`) and 62.2%
(`structured_ledger`).

What the data supports:

1. **Structured repair requests are small and flat.** They stayed between 1,450
   and 2,695 input tokens. In `full_history` the second repair on tasks 18 and
   24 reached 7,557 and 7,398.
2. **Dropping cut-off replies is the largest single effect.** Task 18's first
   reply hit the output cap without code in every mode. The next request was
   5,495 input tokens in the two modes that resend the reply and 1,450–1,632 in
   the three that do not.
3. **A model-written summary does not pay for itself here.** Its five summary
   calls used 11,992 input tokens, against 11,830 for the repair calls they
   shortened.
4. **Context engineering only reduces input.** Output stayed at 18,824–20,748
   tokens in every mode and is over half the total in the structured modes.

What the data does not support yet:

- **Any claim about pass rate.** Three tasks and one trial cannot separate the
  modes; the task 18 differences may be chance.
- **Any claim about rollback or the repeated-failure warning.** Neither fired in
  Run 010. Both are covered only by offline tests and the Run 002 replay.
- **Any claim about other models.** Only `qwen3.5:9b` was run.

## 9. Related work

Entries marked *verified* were checked against the paper's abstract or page
during this project. Entries marked *to verify* are cited from memory and must
be checked before they go into a paper.

### 9.1 Analog and hardware generation with feedback loops

- **AnalogCoder** (Lai et al., AAAI 2025,
  [arXiv:2405.14918](https://arxiv.org/abs/2405.14918)), *verified*. The loop we
  build on: PySpice code generation with simulation feedback and a subcircuit
  library. Repair appends feedback to the chat.
- **AnalogCoder-Pro** ([arXiv:2508.02518](https://arxiv.org/abs/2508.02518)),
  *verified*. Our baseline code. Adds waveform feedback through a multimodal
  model and sizing by Bayesian optimization; up to three design iterations. The
  pages we read state no token or cost figures.
- **AnalogAgent** ([arXiv:2603.23910](https://arxiv.org/abs/2603.23910)),
  *verified*. Multi-agent loop with a self-evolving memory that distills
  feedback into a playbook reused across tasks. It reports about 32K tokens to
  first success against about 40K for AnalogCoder-Pro. Difference from ours: its
  memory is written by a model and persists across tasks; our state is written
  by the harness and is rebuilt within one task.
- **AutoChip** and its follow-up "Can EDA Tool Feedback Improve Verilog
  Generation by LLMs?" ([arXiv:2411.11856](https://arxiv.org/abs/2411.11856)),
  *verified from summaries*. Compares "full context" with a "succinct" mode that
  sends only the latest tool feedback, reporting similar success at lower token
  use. This is the closest precedent in hardware and corresponds to our
  `latest_feedback` baseline. It has no failure classification, ledger, or
  rollback.
- **RTLFixer** ([arXiv:2311.16543](https://arxiv.org/abs/2311.16543)),
  *verified from summaries*. Fixes Verilog syntax errors using compiler messages
  plus retrieved human guidance per error category; about 98.5% of compile
  errors fixed on its debugging set. Supports routing by error class.
- **NetlistBench** ([arXiv:2608.12197](https://arxiv.org/abs/2608.12197)),
  *verified*. Shows local netlist edits are reliable (96–100%) while device
  additions are not (41–83%), and accuracy falls with the number of edit steps.
  Relevant to a future edit-based repair on top of our state.

### 9.2 Why history hurts

- **LLMs Get Lost in Multi-Turn Conversation** (Laban et al.,
  [arXiv:2505.06120](https://arxiv.org/abs/2505.06120)), *verified*. Reports an
  average 39% drop when a task is spread over turns instead of given as one
  prompt, and that models cling to early attempts. Motivates sending one fresh
  prompt per repair.
- **The Debugging Decay Index** (Adnan and Kuhn,
  [arXiv:2506.18403](https://arxiv.org/abs/2506.18403)), *verified from the
  abstract*. Reports that most models lose 60–80% of their debugging capability
  within two to three attempts and that timed fresh starts help. Motivates the
  repeated-failure signal.
- **Is Self-Repair a Silver Bullet for Code Generation?** (Olausson et al.,
  ICLR 2024, [arXiv:2306.09896](https://arxiv.org/abs/2306.09896)), *verified*.
  Finds repair gains are modest once cost is counted and that feedback quality
  is the bottleneck. Motivates spending effort on the failure and evidence
  fields rather than on preserving history.

### 9.3 Context management in general agents

- **The Complexity Trap** (Lindenbauer et al.,
  [arXiv:2508.21433](https://arxiv.org/abs/2508.21433)), *verified*. On
  SWE-bench Verified, simply masking old tool outputs roughly halves cost and
  matches the solve rate of LLM summarization. Our Run 008 result points the same
  way in a different domain: the summarizer did not pay for itself.
- **StateFlow** (Wu et al., [arXiv:2403.11322](https://arxiv.org/abs/2403.11322)),
  *verified from summaries*. Models task solving as a state machine with
  state-specific prompts and reports higher success than ReAct at 3–5× lower
  cost. Our layer-specific instruction is the same idea applied to repair.
- **Effective context engineering for AI agents** (Anthropic,
  [post](https://anthropic.com/research/effective-context-engineering-for-ai-agents)),
  *verified from summaries*. Recommends the smallest set of high-signal tokens,
  with compaction and structured note-taking for long tasks.
- **Reflexion** (Shinn et al., 2023) and **Agentic Context Engineering (ACE)**,
  *to verify*. Reflexion keeps model-written verbal lessons between trials. ACE,
  as we recall it, argues for itemized incremental context updates over
  rewriting a summary; AnalogAgent's playbook follows a similar idea.

### 9.4 Other ways to reduce cost (complementary, not compared)

- **Prompt compression**: LLMLingua-2
  ([paper](https://aclanthology.org/2024.findings-acl.57/)). Compresses text
  with a small model; risky for netlists, where node names and values must
  survive exactly.
- **Model routing**: FrugalGPT ([arXiv:2305.05176](https://arxiv.org/abs/2305.05176)),
  RouteLLM ([arXiv:2406.18665](https://arxiv.org/abs/2406.18665)), MTRouter
  ([arXiv:2604.23530](https://arxiv.org/abs/2604.23530)), Budget-Aware Agentic
  Routing ([arXiv:2602.21227](https://arxiv.org/abs/2602.21227)). These choose
  which model answers; our method changes what any model is sent.

### 9.5 What is new here

To our knowledge from the works above, no prior analog or hardware generation
agent combines all of the following: a repair context rebuilt by the harness
with no model call; failure classification into layers that select the
instruction; an attempt ledger made from code diffs; and rollback by pipeline
progress. The closest pieces are AutoChip's succinct mode (latest feedback
only) and AnalogAgent's memory (model-written, cross-task). This positioning
needs a proper literature search before submission.

## 10. Limitations and threats to validity

- **Sample size.** One trial on three tasks. Run 004 and the smoke tests showed
  the same task can pass or fail between runs at the same settings.
- **Task selection.** Tasks 14, 18, and 24 were chosen because they needed
  repairs in Run 002. Savings on the full benchmark will be smaller, because
  tasks that pass on the first generation send no repair request.
- **Template dependence.** Classification relies on the pinned upstream feedback
  templates. Unmatched feedback becomes `UNKNOWN` and is passed through.
- **Lost reasoning.** The structured modes do not carry the model's design plan.
- **Affected nodes** are filled only for floating-node and node-naming failures.
- **Instruction wording is a confound.** The structured modes change both what
  history is sent and the instruction text. An ablation is needed to separate them.
- **Output is untouched.** Truncated, looping replies still dominate cost.

## 11. Next experiments

1. Three to five trials per mode on the three tasks plus more repair-heavy
   tasks, to get pass-rate intervals and token variance.
2. Field ablations of the state: remove evidence trimming, verified facts,
   layer-specific instruction, ledger, and rollback one at a time.
3. Tasks chosen to trigger rollback and repeated failures (for example 7, 13,
   27 from Run 002).
4. The full 28-task benchmark in `full_history` and `structured_ledger`.
5. A second model, to test whether the result depends on `qwen3.5:9b`.
6. Output-side controls (stop on repetition, shorter plans) as a separate study.
