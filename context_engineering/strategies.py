"""Context strategies for repair requests.

Each strategy receives the full upstream conversation and returns the message
list actually sent to the model. The upstream runner keeps its own full
history, so every strategy is recomputed from the same source of truth.
"""
from __future__ import annotations

import re

from .state import (INSTRUCTION, VERIFIED_BY_RANK, best_attempt, describe_change,
                    parse_attempts, repeated_failure)

MODES = ("full_history", "latest_feedback", "llm_summary", "structured_state", "structured_ledger")
VERSION = "context-strategies-v1"

SUMMARY_SYSTEM = "You summarize failed analog circuit design attempts for a repair step."
SUMMARY_PROMPT = """Below are earlier design attempts for one circuit task and the feedback each received.
Write a summary of at most 150 words for the engineer who will fix the design. Include:
- the intended topology,
- every error observed so far,
- every fix that was tried and whether it helped.
Do not write code. Do not propose new fixes.

{history}
"""


def _strip_code(answer):
    """Reasoning text of an answer; the code is carried separately."""
    return re.sub(r"```.*?```", "[code omitted]", answer, flags=re.DOTALL).strip()


def summary_request(attempts, max_chars=12000):
    """Messages asking the model to summarize everything before the latest feedback."""
    parts = []
    for attempt in attempts:
        parts.append(f"### Attempt {attempt.index + 1} reasoning\n{_strip_code(attempt.answer)}")
        if attempt is not attempts[-1]:
            parts.append(f"### Feedback on attempt {attempt.index + 1}\n{attempt.feedback.strip()}")
    history = "\n\n".join(parts)
    if len(history) > max_chars:
        # Degenerate answers can be very long; the tail holds the latest reasoning.
        history = "... (earlier text truncated)\n" + history[-max_chars:]
    return [{"role": "system", "content": SUMMARY_SYSTEM},
            {"role": "user", "content": SUMMARY_PROMPT.format(history=history)}]


def _code_block(code):
    return f"```python\n{code}\n```" if code else "(no code was produced)"


def _state_block(attempts, generation_budget, ledger):
    latest = attempts[-1]
    candidate = best_attempt(attempts) if ledger else (latest if latest.code else None)
    rolled_back = ledger and candidate is not None and candidate is not latest
    # The failure shown must be the one that belongs to the candidate shown.
    failure = candidate if rolled_back else latest
    lines = ["## Repair state", "",
             f"ATTEMPT: {len(attempts) + 1} of {generation_budget}" if generation_budget else f"ATTEMPT: {len(attempts) + 1}",
             ""]
    if candidate is None:
        lines += ["CANDIDATE: none; " + ("no attempt so far produced code." if ledger
                                         else "the latest reply contained no code.")]
    elif rolled_back:
        lines += [f"CANDIDATE (attempt {candidate.index + 1}, the best so far; later attempts were worse and are discarded):",
                  _code_block(candidate.code)]
    else:
        lines += [f"CANDIDATE (attempt {candidate.index + 1}):", _code_block(candidate.code)]
    verified = list(VERIFIED_BY_RANK.get(failure.rank, [])) if candidate is not None else []
    for attempt in attempts if ledger else [latest]:
        verified += [fact for fact in attempt.facts if fact not in verified]
    if verified:
        lines += ["", "VERIFIED (keep these working):"] + [f"- {fact}" for fact in verified]
    lines += ["", f"FAILURE: layer={failure.layer} class={failure.error_class}"]
    if failure.affected_nodes:
        lines += [f"AFFECTED NODES: {', '.join(failure.affected_nodes)}"]
    if failure.evidence:
        lines += ["EVIDENCE:", failure.evidence]
    if ledger:
        lines += ["", "TRIED (do not repeat a change that did not help):"]
        previous_code = ""
        for attempt in attempts:
            outcome = attempt.error_class + (f": {attempt.headline}" if attempt.headline else "")
            lines.append(f"{attempt.index + 1}. {describe_change(previous_code, attempt.code)} -> {outcome}")
            previous_code = attempt.code or previous_code
    instruction = INSTRUCTION[failure.layer]
    if candidate is None:
        instruction = INSTRUCTION["OUTPUT_FORMAT"]
    elif ledger and repeated_failure(attempts):
        instruction = ("The last two attempts failed in the same way, so the previous kind of fix does not work. "
                       "Take a different approach. " + instruction)
    lines += ["", "INSTRUCTION: " + instruction]
    state = {"candidate_attempt": candidate.index if candidate is not None else None,
             "rolled_back": bool(rolled_back), "layer": failure.layer, "error_class": failure.error_class,
             "affected_nodes": failure.affected_nodes, "repeated_failure": bool(ledger and repeated_failure(attempts)),
             "attempt_classes": [a.error_class for a in attempts]}
    return "\n".join(lines), state


def _fresh_prompt(prefix, addition):
    """Task prompt first (stable cache prefix), then the per-round addition."""
    messages = [dict(m) for m in prefix]
    messages[-1]["content"] = messages[-1]["content"].rstrip() + "\n\n" + addition
    return messages


def build_context(mode, messages, generation_budget=None, summarize=None):
    """Return (messages to send, metadata describing what was done).

    `summarize` is a callable taking summary-request messages and returning
    the summary text; it is required only for `llm_summary`.
    """
    if mode not in MODES:
        raise ValueError(f"Unknown context mode {mode!r}; choose from {MODES}")
    metadata = {"version": VERSION, "mode": mode, "applied": False,
                "original_messages": len(messages), "original_chars": sum(len(m["content"]) for m in messages
                                                                           if isinstance(m["content"], str))}
    if mode == "full_history":
        return messages, metadata
    try:
        prefix, attempts = parse_attempts(messages)
    except ValueError as exc:
        # Unrecognized shape: send unchanged rather than guess.
        metadata["skipped_reason"] = str(exc)
        return messages, metadata
    latest = attempts[-1]
    if mode == "llm_summary":
        summary = summarize(summary_request(attempts)) if summarize is not None else None
        if summary and summary.strip():
            addition = "\n".join([
                "## Summary of previous attempts", summary.strip(), "",
                "## Latest candidate", _code_block(latest.code), "",
                "## Latest feedback", latest.feedback.strip()])
            result = _fresh_prompt(prefix, addition)
            metadata["summary_chars"] = len(summary)
        else:
            metadata["fallback"] = "latest_feedback"
            mode = "latest_feedback"
    if mode == "latest_feedback":
        result = [dict(m) for m in prefix] + [
            {"role": "assistant", "content": latest.answer}, {"role": "user", "content": latest.feedback}]
    elif mode in {"structured_state", "structured_ledger"}:
        block, state = _state_block(attempts, generation_budget, ledger=mode == "structured_ledger")
        result = _fresh_prompt(prefix, block)
        metadata["state"] = state
    metadata.update(applied=True, sent_messages=len(result), sent_chars=sum(len(m["content"]) for m in result))
    return result, metadata
