#!/usr/bin/env python3
"""Compare runs that differ in --context-mode. Reads saved artifacts only.

Usage (from the repository root):
    python baselines/analogcoder_pro/compare_runs.py RUN_DIR [RUN_DIR ...] [--json OUT]

The first run is the reference for the identical-initial-answer check.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context_engineering.state import classify  # noqa: E402
from usage_accounting.aggregate import load_calls  # noqa: E402


def feedback_sequence(work, task):
    """Feedback the upstream runner produced, in order. Identical in every mode."""
    path = next(work.glob(f"*/p{task}/p{task}_0_input.txt"), None)
    return [] if path is None else [p.strip() for p in path.read_text().split("\n----------\n")[1:]]


def tokens(call):
    usage = call["usage"]
    return (usage["input_tokens"] or 0) + (usage["output_tokens"] or 0)


def analyse(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    results = json.loads((directory / "results.json").read_text())
    max_tokens = manifest["config"]["max_tokens"]
    calls = load_calls(directory)
    rows = {r["task_id"]: r for r in results["results"]}
    out = {"run": directory.name, "mode": manifest["config"].get("context_mode", "full_history"),
           "digest": manifest["model"]["digest"][:12], "finished": results["finished_attempts"],
           "planned": results["planned_attempts"], "passed": results["passed_attempts"],
           "runner_errors": results["runner_errors"],
           "wall_minutes": round(sum(r["wall_seconds"] for r in rows.values()) / 60, 2)}
    tasks = {}
    for task, row in sorted(rows.items()):
        task_calls = [c for c in calls if c["task_id"] == task]
        generation = None
        if row["status"] == "passed":
            generation = int(re.search(r"_(\d+)_success\.py$", row["success_file"]).group(1))
        repairs = [c for c in task_calls if c["phase"] == "repair_generation"]
        seq = feedback_sequence(directory / "work", task)
        tasks[task] = {
            "status": row["status"], "passing_generation": generation, "calls": len(task_calls),
            "input_tokens": sum(c["usage"]["input_tokens"] or 0 for c in task_calls),
            "output_tokens": sum(c["usage"]["output_tokens"] or 0 for c in task_calls),
            "repair_input_tokens": [c["usage"]["input_tokens"] for c in repairs],
            "truncated": sum((c["usage"]["output_tokens"] or 0) >= max_tokens for c in task_calls),
            "feedback_classes": [classify(f)[0] for f in seq],
        }
    out["tasks"] = tasks
    out["first_pass"] = sum(t["passing_generation"] == 0 for t in tasks.values())
    out["repair_pass"] = sum((t["passing_generation"] or 0) > 0 for t in tasks.values())
    by_phase = collections.defaultdict(collections.Counter)
    for call in calls:
        group = by_phase[call["phase"]]
        group["calls"] += 1
        for key in ("input_tokens", "output_tokens", "cached_input_tokens"):
            group[key] += call["usage"][key] or 0
        group["truncated"] += (call["usage"]["output_tokens"] or 0) >= max_tokens
        group["unknown_usage"] += call["usage"]["input_tokens"] is None
        group["non_completed"] += call["status"] != "completed"
    total = collections.Counter()
    for group in by_phase.values():
        total.update(group)
    out["by_phase"] = {k: dict(v) for k, v in sorted(by_phase.items())}
    out["total"] = dict(total)
    out["total_tokens"] = total["input_tokens"] + total["output_tokens"]
    out["tokens_per_pass"] = round(out["total_tokens"] / out["passed"]) if out["passed"] else None
    repairs = by_phase.get("repair_generation", collections.Counter())
    out["repair_input_mean"] = round(repairs["input_tokens"] / repairs["calls"]) if repairs["calls"] else None
    out["cache_reuse"] = round(total["cached_input_tokens"] / total["input_tokens"], 4) if total["input_tokens"] else None
    # Same failure twice in a row, judged on upstream feedback text in every mode.
    repeats = transitions = 0
    for task in rows:
        parsed = [classify(f) for f in feedback_sequence(directory / "work", task)]
        keys = [(c, re.sub(r"\d+(?:\.\d+)?", "N", e)) for c, e, _, _ in parsed]
        transitions += max(len(keys) - 1, 0)
        repeats += sum(a == b for a, b in zip(keys, keys[1:]))
    out["repeated_failures"] = [repeats, transitions]
    initial = {}
    for path in sorted((directory / "api_calls").glob("task_*/trial_0/call_001.json")):
        response = json.loads(path.read_text()).get("response") or {}
        text = (response.get("message") or {}).get("content", "")
        initial[int(path.parts[-3].split("_")[1])] = hashlib.sha256(text.encode()).hexdigest()[:12]
    out["initial_answer_hashes"] = initial
    strategy = collections.Counter()
    for path in (directory / "api_calls").glob("task_*/trial_*/call_*.json"):
        meta = json.loads(path.read_text()).get("context_strategy")
        if not meta:
            continue
        strategy["applied"] += bool(meta.get("applied"))
        strategy["fallbacks"] += bool(meta.get("fallback"))
        state = meta.get("state") or {}
        strategy["rollbacks"] += bool(state.get("rolled_back"))
        strategy["repeat_warnings"] += bool(state.get("repeated_failure"))
    out["strategy"] = dict(strategy)
    return out


def table(runs):
    lines = ["| Mode | Passed | First / after repair | Calls | Input | Cached | Output | Total | Mean repair input | Truncated | Tokens per pass |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for r in runs:
        t = r["total"]
        lines.append(f"| `{r['mode']}` | {r['passed']}/{r['finished']} | {r['first_pass']} / {r['repair_pass']} | {t['calls']} | "
                     f"{t['input_tokens']:,} | {t['cached_input_tokens']:,} | {t['output_tokens']:,} | {r['total_tokens']:,} | "
                     f"{r['repair_input_mean'] if r['repair_input_mean'] is not None else '-':,} | {t['truncated']} | "
                     f"{format(r['tokens_per_pass'], ',') if r['tokens_per_pass'] else '-'} |")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+", type=Path)
    parser.add_argument("--json", type=Path, help="Also write the full comparison as JSON")
    args = parser.parse_args()
    runs = [analyse(p) for p in args.runs]
    print(table(runs))
    reference = runs[0]["initial_answer_hashes"]
    for run in runs[1:]:
        same = sum(run["initial_answer_hashes"].get(t) == h for t, h in reference.items())
        print(f"{run['mode']}: identical initial answers vs {runs[0]['mode']}: {same}/{len(reference)}")
    if args.json:
        args.json.write_text(json.dumps(runs, indent=2, default=str) + "\n")


if __name__ == "__main__":
    main()
