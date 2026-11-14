"""Structured JSON logging with OBS correlation context (Python 3.10+, stdlib only).

Copy next to obs_client.py. Usage:

    from log_template import setup_logging, job_context
    setup_logging()                                   # once at startup
    with job_context(job_id="job-123", workflow_id="video", workflow_run_id="run-001",
                     step_id="render", attempt=2, worker="w-1", trace_id=tid):
        logging.getLogger(__name__).info("rendering")  # line carries all context fields

Env: OBS_SERVICE_NAME, OBS_INSTANCE_ID, OBS_ENVIRONMENT (same values used for OBS registration).
If OpenTelemetry is installed and a span is active, its trace_id/span_id are used automatically.
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import logging
import os
import socket
import sys
import traceback
from datetime import datetime, timezone

_CTX: contextvars.ContextVar[dict] = contextvars.ContextVar("obs_log_ctx", default={})

_FIELD_MAP = {
    "job_id": "job_id", "worker": "worker_id", "workflow_id": "workflow_id",
    "workflow_run_id": "workflow_run_id", "step_id": "step_id", "attempt": "step_attempt_id",
    "trace_id": "trace_id", "span_id": "span_id",
}


@contextlib.contextmanager
def job_context(**fields):
    """Attach job/workflow/trace ids to every log line emitted inside the block (nests, async-safe)."""
    token = _CTX.set({**_CTX.get(), **{k: v for k, v in fields.items() if v is not None}})
    try:
        yield
    finally:
        _CTX.reset(token)


def _otel_ids() -> dict:
    try:
        from opentelemetry import trace  # optional dependency

        ctx = trace.get_current_span().get_span_context()
        if ctx.is_valid:
            return {"trace_id": f"{ctx.trace_id:032x}", "span_id": f"{ctx.span_id:016x}"}
    except Exception:  # noqa: BLE001 - logging must never raise
        pass
    return {}


class ObsJsonFormatter(logging.Formatter):
    def __init__(self) -> None:
        super().__init__()
        env = os.environ
        self._static = {
            "service_name": env.get("OBS_SERVICE_NAME", "unknown-service"),
            "instance_id": env.get("OBS_INSTANCE_ID") or socket.gethostname(),
            "environment": env.get("OBS_ENVIRONMENT", "unknown"),
        }

    def format(self, record: logging.LogRecord) -> str:
        try:
            ctx = {**_CTX.get(), **_otel_ids()}
            out = {
                "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
                "level": record.levelname, "message": record.getMessage(), **self._static,
                **{_FIELD_MAP[k]: v for k, v in ctx.items() if k in _FIELD_MAP},
            }
            if getattr(record, "event", None):
                out["event"] = record.event
            if record.exc_info:
                et, ev, tb = record.exc_info
                out["exception_type"] = et.__name__ if et else None
                out["stack_trace"] = "".join(traceback.format_exception(et, ev, tb))[-8000:]
            return json.dumps(out, default=str, ensure_ascii=False)
        except Exception:  # noqa: BLE001 - never break the host service over a log line
            return json.dumps({"level": "ERROR", "message": "log formatting failed"})


def setup_logging(level: str | int = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ObsJsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
