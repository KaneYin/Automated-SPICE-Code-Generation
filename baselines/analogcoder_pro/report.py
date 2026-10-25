#!/usr/bin/env python3
"""Write a readable report from a saved local baseline run."""
import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from usage_accounting.aggregate import export_run, summary_markdown


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    directory = args.run.resolve()
    manifest = json.loads((directory / "manifest.json").read_text())
    data = json.loads((directory / "results.json").read_text())
    config = manifest["config"]
    rows = data["results"]
    passes = sum(r["status"] == "passed" for r in rows)
    first_generation = 0
    for row in rows:
        if row["status"] != "passed" or not row["success_file"]:
            continue
        retry_id = Path(row["success_file"]).stem.split("_")[-2]
        first_generation += retry_id == "0"
    total_time = sum(r["wall_seconds"] for r in rows)
    model = manifest["model"]
    details = model.get("details", {})
    call_records = [(p, json.loads(p.read_text())) for p in (directory / "api_calls").rglob("*.json")]
    calls = [record for _, record in call_records]
    truncated = sum(c.get("response", {}).get("done_reason") == "length" for c in calls)
    truncated_tasks = {int(p.parent.parent.name.removeprefix("task_")) for p, c in call_records if c.get("response", {}).get("done_reason") == "length"}
    truncated_failures = truncated_tasks & {r["task_id"] for r in rows if r["status"] == "failed"}
    lines = [
        "# AnalogCoder-Pro local baseline results", "",
        f"Model: `{config['model']}` ({details.get('parameter_size', 'unknown size')}, {details.get('quantization_level', 'unknown quantization')}).",
        f"Model digest: `{model['digest']}`.", "",
        f"Upstream: [{manifest['upstream']['revision']}]({manifest['upstream']['repository']}/tree/{manifest['upstream']['revision']}).",
        "",
        f"Finished attempts: {len(rows)}/{data['planned_attempts']}. Upstream-checker acceptances: {passes}/{len(rows)}.",
        f"Accepted on first generation: {first_generation}. Accepted after repair: {passes - first_generation}.",
        f"Total attempt wall time: {total_time / 60:.1f} minutes. API calls: {sum(r['api_calls'] for r in rows)} (including {sum(r['vision_calls'] for r in rows)} waveform-vision calls).",
        f"Tokens: {sum(r['prompt_tokens'] for r in rows):,} prompt + {sum(r['completion_tokens'] for r in rows):,} output.",
        f"Responses stopped at the configured output limit: {truncated}.",
        f"Tasks with at least one output-limit response: {len(truncated_tasks)}. Of these, {len(truncated_failures)} ended without upstream-checker acceptance.",
        "",
        f"Each attempt allows {config['max_generations']} generation calls including repairs. Temperature {config['temperature']}; context {config['context']:,}; maximum output {config['max_tokens']:,}; base seed {config['seed']}; separate thinking {config['thinking']}; waveform feedback {config['vision']}.",
        "",
        "| Task | Circuit | Status | Calls | Vision calls | Seconds | Log |",
        "| --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        circuit = row["circuit"].replace("|", "\\|")
        lines.append(f"| {row['task_id']} | {circuit} | {row['status']} | {row['api_calls']} | {row['vision_calls']} | {row['wall_seconds']:.1f} | [log]({row['log']}) |")
    if (directory / "usage" / "calls").exists():
        usage = export_run(directory, pricing=manifest.get("usage_pricing"))
        lines += ["", summary_markdown(usage), "",
                  "Provider-reported prompt/KV reuse measures cached prompt tokens, not hardware cache lookup performance. "
                  "Unknown telemetry remains unknown; partial totals include only observed usage.", "",
                  "See [usage summary](usage/summary.json), [per-call usage](usage/calls.csv), "
                  "and [stage breakdown](usage/by_stage.csv)."]
    else:
        lines += ["", "## Usage accounting", "",
                  "Detailed usage has not been backfilled for this historical run. "
                  "Legacy token totals above do not establish cache or cost measurement coverage."]
    failures = [row for row in rows if row["status"] != "passed"]
    if failures:
        lines += ["", "## Failure diagnostics", "", "These are excerpts from the saved execution logs, not an independent judgment of circuit correctness.", ""]
        for row in failures:
            log = (directory / row["log"]).read_text()
            errors = re.findall(r"(?:NameError|TypeError|ImportError|ModuleNotFoundError|SyntaxError|ValueError|AttributeError|Fatal error):[^\n]+", log)
            detail = errors[-1] if errors else f"Upstream result: {row['status']}; inspect the saved log and feedback."
            lines.append(f"- Task {row['task_id']}: {detail}")
    lines += [
        "", "## Interpretation", "",
        "These are acceptances by the unchanged public upstream checkers. They do not constitute independent circuit validation or reproduction of the paper's numerical results. Runner errors and timeouts count as non-successes in the acceptance rate.",
        "",
        "The 4,096-token cap is material: an output may end during the design plan or before a complete code fence. The upstream extractor then produces an empty circuit body, which can surface as `NameError: circuit is not defined`. Such outcomes must not be described as proof that the model cannot design the circuit. A higher-output-budget experiment should be reported separately, preserving this run.",
        "",
        "The unchanged comparator checker sweeps a voltage source named `Vin`, and the Schmitt checker expects an existing input voltage source with a `vin` name prefix. Evaluation failures can reflect these input/source contracts as well as circuit behavior; task logs retain the exact errors.",
        "",
        "This is the AnalogCoder-Pro generation benchmark, not the original AnalogCoder 24-task benchmark. The released VCO checker, sizing helper, and complete dynamic retrieval pipeline are unavailable; they are not silently replaced in this run.",
        "",
        "Runtime adaptations include a native local Ollama transport, an alias for the upstream complex-prompt filename typo, simulator/attempt timeouts, and stage metadata instrumentation when listed in the manifest. Prompts, device examples, checkers, and acceptance thresholds remain unchanged.",
        "",
        "See [manifest.json](manifest.json), [model_info.json](model_info.json), [results.json](results.json), [results.csv](results.csv), and [installed_packages.txt](installed_packages.txt) for settings and machine-readable evidence.",
    ]
    path = directory / "REPORT.md"
    path.write_text("\n".join(lines) + "\n")
    print(path)


if __name__ == "__main__":
    main()
