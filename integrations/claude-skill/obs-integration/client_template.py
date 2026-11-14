"""Drop-in OBS client (Python 3.10+, stdlib only).

Copy into a service as e.g. `<pkg>/obs_client.py` and adapt. Design rules:
- never raises into the caller, never blocks the request/job path (background sender thread);
- drops events when its bounded queue is full rather than growing memory;
- everything is a no-op when OBS_ENABLED=false or OBS_URL/OBS_API_KEY are missing.

Env: OBS_URL, OBS_API_KEY, OBS_SERVICE_NAME, OBS_ENVIRONMENT, OBS_INSTANCE_ID (fixed per process, not a pid),
     OBS_SERVICE_VERSION, OBS_HEALTH_URL (reachable from OBS), OBS_ENABLED.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import socket
import threading
import urllib.request
import uuid
from datetime import datetime, timezone

log = logging.getLogger("obs")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ObsClient:
    def __init__(self) -> None:
        env = os.environ
        self.url = env.get("OBS_URL", "").rstrip("/")
        self.key = env.get("OBS_API_KEY", "")
        self.enabled = env.get("OBS_ENABLED", "true").lower() != "false" and bool(self.url and self.key)
        self.service = env.get("OBS_SERVICE_NAME", "unknown-service")
        self.environment = env.get("OBS_ENVIRONMENT", "unknown")
        self.instance_id = env.get("OBS_INSTANCE_ID") or socket.gethostname()  # must be stable across restarts
        self.version = env.get("OBS_SERVICE_VERSION")
        self.health_url = env.get("OBS_HEALTH_URL")
        self.service_id: str | None = None
        self._q: queue.Queue[tuple[str, str, dict]] = queue.Queue(maxsize=1000)
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    # ---- lifecycle -------------------------------------------------------------------------
    def start(self, heartbeat_s: float = 10.0) -> None:
        if not self.enabled:
            return
        self._threads = [
            threading.Thread(target=self._sender, daemon=True, name="obs-sender"),
            threading.Thread(target=self._heartbeat_loop, args=(heartbeat_s,), daemon=True, name="obs-heartbeat"),
        ]
        for t in self._threads:
            t.start()

    def stop(self) -> None:
        """Call on graceful shutdown so OBS records STOPPED instead of waiting for a heartbeat timeout."""
        if not self.enabled:
            return
        self._stop.set()
        if self.service_id:
            self._request("POST", f"/services/{self.service_id}/heartbeat",
                          {"instance_id": self.instance_id, "stopping": True})

    # ---- registry --------------------------------------------------------------------------
    def register(self) -> None:
        body = {"service_name": self.service, "instance_id": self.instance_id, "environment": self.environment,
                "service_version": self.version, "hostname": socket.gethostname(),
                "metadata": {"health_url": self.health_url} if self.health_url else {}}
        out = self._request("POST", "/services/register", body)
        if isinstance(out, dict):
            self.service_id = str(out["service_id"]) if out.get("service_id") else None

    def _heartbeat_loop(self, every: float) -> None:
        while not self._stop.is_set():
            if not self.service_id:
                self.register()
            elif self._request("POST", f"/services/{self.service_id}/heartbeat",
                               {"instance_id": self.instance_id}) is None:
                self.service_id = None  # 404 or unreachable: re-register next tick
            self._stop.wait(every)

    # ---- jobs / events (fire and forget) ---------------------------------------------------
    def job(self, external_job_id: str, status: str, *, worker_name: str | None = None,
            workflow_run_key: str | None = None, trace_id: str | None = None,
            error: dict | None = None, metadata: dict | None = None) -> None:
        """status: QUEUED | RUNNING | COMPLETED | FAILED | CANCELLED. Terminal states are final."""
        self._enqueue("POST", "/jobs", {
            "service_name": self.service, "external_job_id": external_job_id, "status": status,
            "environment": self.environment, "instance_id": self.instance_id, "worker_name": worker_name,
            "workflow_run_key": workflow_run_key, "trace_id": trace_id, "error": error,
            "metadata": metadata or {}})

    def event(self, event_type: str, *, workflow_id: str, workflow_run_id: str, step_id: str | None = None,
              trace_id: str | None = None, worker_id: str | None = None, data: dict | None = None,
              event_id: str | None = None) -> None:
        """event_type e.g. WORKFLOW_STARTED, STEP_STARTED, STEP_COMPLETED, STEP_FAILED, WORKFLOW_FAILED."""
        ctx = {"workflow_id": workflow_id, "workflow_run_id": workflow_run_id}
        if step_id:
            ctx["step_id"] = step_id
        if trace_id:
            ctx["trace_id"] = trace_id
        self._enqueue("POST", "/events", {
            "event_id": event_id or str(uuid.uuid4()), "event_type": event_type, "event_version": 1,
            "occurred_at": _now(),
            "source": {"service_name": self.service, "instance_id": self.instance_id, "worker_id": worker_id,
                       "environment": self.environment, "service_version": self.version},
            "context": ctx, "data": data or {}})

    # ---- transport -------------------------------------------------------------------------
    def _enqueue(self, method: str, path: str, body: dict) -> None:
        if not self.enabled:
            return
        try:
            self._q.put_nowait((method, path, body))
        except queue.Full:
            log.warning("obs queue full, dropping %s", path)

    def _sender(self) -> None:
        while not self._stop.is_set():
            try:
                method, path, body = self._q.get(timeout=1)
            except queue.Empty:
                continue
            self._request(method, path, body)

    def _request(self, method: str, path: str, body: dict) -> dict | None:
        try:
            req = urllib.request.Request(
                self.url + path, data=json.dumps(body).encode(), method=method,
                headers={"Content-Type": "application/json", "X-API-Key": self.key})
            with urllib.request.urlopen(req, timeout=2) as resp:  # short timeout: OBS must never slow the service
                return json.loads(resp.read() or b"{}")
        except Exception as exc:  # noqa: BLE001 - OBS failures must never reach the host service
            log.debug("obs %s %s failed: %s", method, path, exc)
            return None


obs = ObsClient()

# Usage:
#   obs.start()                                   # app startup (registers, then heartbeats in background)
#   obs.job("job-1", "QUEUED", trace_id=tid)
#   obs.job("job-1", "RUNNING", worker_name="w-1", trace_id=tid)
#   obs.job("job-1", "FAILED", error={"type": "TimeoutError", "message": "..."}, trace_id=tid)
#   obs.event("STEP_STARTED", workflow_id="video", workflow_run_id="run-1", step_id="render", trace_id=tid)
#   obs.stop()                                    # app shutdown
