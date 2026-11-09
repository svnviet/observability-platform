import itertools
from datetime import UTC, datetime, timedelta
from typing import Any

_counter = itertools.count(1)
T0 = datetime(2026, 11, 9, 12, 0, 0, tzinfo=UTC)


def at(seconds: float) -> str:
    return (T0 + timedelta(seconds=seconds)).isoformat()


def event(
    event_type: str,
    *,
    t: float = 0,
    run: str = "run-1",
    wf: str = "wf-1",
    step: str | None = None,
    attempt: int = 1,
    service: str = "video-generator",
    worker: str | None = "worker-1",
    event_id: str | None = None,
    **data: Any,
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "workflow_id": wf,
        "workflow_run_id": run,
        "correlation_id": "corr-1",
        "trace_id": "trace-1",
    }
    if step:
        context["step_id"] = step
        context["step_attempt_id"] = f"{step}-a{attempt}"
    payload_data = dict(data)
    if step:
        payload_data.setdefault("attempt_number", attempt)
    return {
        "event_id": event_id or f"evt-{next(_counter)}",
        "event_type": event_type,
        "event_version": 1,
        "occurred_at": at(t),
        "source": {"service_name": service, "instance_id": f"{service}-01", "worker_id": worker},
        "context": context,
        "data": payload_data,
    }
