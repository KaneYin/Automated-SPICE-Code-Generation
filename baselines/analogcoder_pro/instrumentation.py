"""Checksum-guarded metadata instrumentation for the copied Pro runtime only."""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path

VERSION = "pro-stages-v1"
PINNED_SHA256 = "8dc0f6948d2446f5c3f9896b472fda6b4e84a0f2afdd92550aa042f18e601029"
SITES = {
    779: ("optimization", ""),
    912: ("initial_generation", ", generation_index=0"),
    1227: ("waveform_analysis", ", diagnoses_generation_index=code_id"),
    1284: ("repair_generation", ", generation_index=code_id"),
    1364: ("retrieval", ""),
}
HELPER = '''from usage_accounting.recorder import call_context as _usage_context

def _usage_invoke(phase, callback, **metadata):
    with _usage_context(phase, **metadata):
        return callback()

'''


def instrument_source(source: str) -> tuple[str, dict]:
    """Reject unknown source before adding context to the five known requests.

    Lambdas defer argument evaluation until context is active and do not modify
    any provider kwargs, prompt contents, seed progression, or retry loop.
    """
    original_hash = hashlib.sha256(source.encode()).hexdigest()
    if original_hash != PINNED_SHA256:
        raise RuntimeError("Unknown Pro run.py checksum; refusing telemetry patch")
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    replacements = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or node.lineno not in SITES:
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "create"
                and ast.unparse(func.value) in {"client.chat.completions", "client_vlm.chat.completions"}):
            continue
        # AST columns are UTF-8 byte offsets; the call lines are ASCII.
        start = offsets[node.lineno - 1] + len(lines[node.lineno - 1].encode()[:node.col_offset].decode())
        end = offsets[node.end_lineno - 1] + len(lines[node.end_lineno - 1].encode()[:node.end_col_offset].decode())
        phase, metadata = SITES[node.lineno]
        expression = source[start:end]
        replacements.append((start, end, f"_usage_invoke({phase!r}, lambda: {expression}{metadata})"))
    if len(replacements) != len(SITES):
        raise RuntimeError("Expected exactly five Pro model-call instrumentation anchors")
    for start, end, replacement in sorted(replacements, reverse=True):
        source = source[:start] + replacement + source[end:]
    source = HELPER + source
    compile(source, "instrumented_pro_run.py", "exec")
    return source, {
        "version": VERSION,
        "source_sha256": original_hash,
        "runtime_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "call_sites": len(replacements),
    }


def instrument_runtime(path: Path) -> dict:
    source, provenance = instrument_source(path.read_text())
    path.write_text(source)
    return provenance
