"""Opt-in transport accounting for the original AnalogCoder runner.

This adapter deliberately does not replace the historical money-quota arithmetic.
A dispatch receives exactly the keyword arguments provided by the legacy caller.
"""
from __future__ import annotations

from pathlib import Path
import time
from typing import Any, Callable
import uuid
import warnings

from .schema import atomic_json, plain


def create_recorder(run_dir: Path | None, provider: str,
                    pricing_path: Path | None = None):
    """Create an isolated telemetry run, or return None when not requested."""
    if run_dir is None:
        return None
    from .recorder import Recorder

    from .pricing import load_pricing
    pricing = load_pricing(pricing_path)
    # A fresh invocation gets its own directory, avoiding accidental coalescing
    # of distinct runs when a user repeats --usage-dir.
    target = Path(run_dir) / (time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:12])
    recorder = Recorder(target, provider=provider, pricing=pricing)
    atomic_json(target / 'manifest.json', {
        'run_id': recorder.run_id, 'framework': 'original_analogcoder',
        'provider': provider, 'usage_schema_version': 1,
        'usage_pricing': pricing, 'legacy_quota_policy': 'unchanged_historical_estimate',
    })
    print('Usage accounting directory: ' + str(target))
    return recorder


def recorded_call(recorder, dispatch: Callable[..., Any], context: dict, **request):
    """Record each transport attempt and return the untouched provider object."""
    if recorder is None:
        return dispatch(**request)
    raw_relative = (Path("api_calls") / ("task_" + str(context.get("task_id"))) /
                    ("trial_" + str(context.get("trial_id"))) /
                    ("call_" + uuid.uuid4().hex + ".json"))
    context = dict(context, phase_source="explicit", transport_attempt_coverage=(
        "one_invocation" if recorder.provider == "ollama" else "sdk_internal_retries_unknown"))
    raw_path = recorder.directory / raw_relative
    record = recorder.start(request, context, raw_path=raw_path)
    raw = {"request": plain(request)}
    # Fail before dispatch if the request cannot be recorded.
    atomic_json(raw_path, raw)
    started = time.monotonic()
    try:
        response = dispatch(**request)
    except BaseException as error:
        wall_seconds = time.monotonic() - started
        raw.update(error={"type": type(error).__name__, "message": str(error)},
                   wall_seconds=wall_seconds)
        try:
            atomic_json(raw_path, raw)
            recorder.finish(record, error=error, wall_seconds=wall_seconds)
            from .aggregate import export_run
            export_run(recorder.directory, pricing=recorder.pricing)
        except Exception as accounting_error:
            # Preserve the original timeout/API exception and its retry handler.
            warnings.warn("Could not finalize usage for failed request: " +
                          str(accounting_error), RuntimeWarning)
        raise
    wall_seconds = time.monotonic() - started
    raw.update(response=plain(response), wall_seconds=wall_seconds)
    atomic_json(raw_path, raw)
    recorder.finish(record, response=response, wall_seconds=wall_seconds)
    from .aggregate import export_run
    export_run(recorder.directory, pricing=recorder.pricing)
    return response
