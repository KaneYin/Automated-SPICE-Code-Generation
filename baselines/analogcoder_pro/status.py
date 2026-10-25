#!/usr/bin/env python3
"""Show saved results and the currently pending local model request."""
import argparse
import json
from pathlib import Path
import time
import sys
from datetime import datetime

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from usage_accounting.aggregate import aggregate, load_calls


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    directory = parser.parse_args().run.resolve()
    manifest = json.loads((directory / "manifest.json").read_text())
    summary = json.loads((directory / "results.json").read_text())
    print(f"Completed {summary['finished_attempts']}/{summary['planned_attempts']}; passed {summary['passed_attempts']}; failed {summary['failed_attempts']}; runner errors {summary['runner_errors']}")
    if (directory / "usage" / "calls").exists():
        calls = load_calls(directory)
        usage = aggregate(calls, pricing=manifest.get("usage_pricing"), results=summary)
        tokens, cache = usage["usage"], usage["cache"]
        complete = all(usage["coverage"][k]["complete"] for k in ("input_tokens", "output_tokens"))
        print(f"Usage ({'complete' if complete else 'partial observed subtotal'}): {usage['calls']} calls; "
              f"{tokens['input_tokens']:,} input + {tokens['output_tokens']:,} output tokens")
        ratio = f"{cache['token_reuse_rate']:.2%}" if cache["token_reuse_rate"] is not None else "unknown"
        print(f"Prompt/KV cache reuse: {ratio}; measured calls {cache['eligible_calls']}/{cache['total_calls']}")
        cost = usage["costs"]["api"]
        print(f"API cost known subtotal: {cost['known_subtotal']} {cost['currency']} "
              f"({'complete' if cost['complete'] else 'partial; unknown remainder'})")
        for record in calls:
            if record["status"] == "started":
                started = datetime.fromisoformat(record["started_at"]).timestamp()
                print(f"Active: task_{record['task_id']}, trial_{record['trial_id']}, "
                      f"call_{record['sequence']}: {record['phase']}; "
                      f"{round(time.time() - started)} seconds elapsed")
        print(f"Model: {manifest['config']['model']}; results: {directory / 'results.json'}")
        return
    pending = []
    for path in (directory / "api_calls").rglob("*.json"):
        try:
            record = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue  # A response may currently be getting written.
        if "response" not in record and "error" not in record:
            pending.append((record["started_at"], path, record))
    for started, path, record in sorted(pending):
        images = any(m.get("images") for m in record["request"]["messages"])
        kind = "waveform analysis" if images else "circuit generation/repair"
        print(f"Active: {path.parent.parent.name}, {path.parent.name}, {path.stem}: {kind}; {round(time.time() - started)} seconds elapsed")
    print(f"Model: {manifest['config']['model']}; results: {directory / 'results.json'}")


if __name__ == "__main__":
    main()
