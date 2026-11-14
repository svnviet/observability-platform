# Obskit Platform (B)

Receives workflow events from the Obskit SDK, keeps an immutable event log in PostgreSQL, and
maintains the current workflow / step / attempt state. See the project spec for the full design;
this README covers what is built and where this service deviates from it.

## Run

```bash
python3.11 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cp .env.example .env            # then export the variables
.venv/bin/alembic upgrade head  # deliberate step; never run automatically
.venv/bin/uvicorn app.main:app --reload
.venv/bin/python -m pytest      # SQLite by default; set TEST_DATABASE_URL to a PostgreSQL URL for the concurrency tests
```

## Built

- **Events:** `POST /events`, `/events/batch` (validated, idempotent by `event_id`, one transaction per event),
  `POST /events/replay`, `GET /events/{event_id}`, `GET /events/rejected`.
- **Workflows:** `GET /workflow-runs` (filters + pagination), `/{id}`, `/timeline`, `/steps`, `/events`;
  `POST /workflow-runs` (explicit, idempotent create); `POST|GET /workflows` (definitions).
- **Registry:** `POST /services/register`, `GET /services`, `/services/{id}`, `/services/{id}/heartbeat`;
  `POST /workers/register`, `GET /workers`, `/workers/{id}`, `/workers/{id}/heartbeat`, `/workers/{id}/status`.
- **Jobs and incidents:** `POST|GET /jobs` (filter by `status`, `service`, `external_job_id`), `GET /jobs/{id}`,
  `/jobs/{id}/events` (every status change, with the previous status and the worker), `/jobs/{id}/timeline` (events plus
  queue wait, run time and total) and `/jobs/{id}/observability` (links to the job's trace, logs and metrics, never the
  data itself; the trace comes from the job's own `trace_id` or its workflow run, logs and metrics from the
  `OBSKIT_PLATFORM_LOGS_URL_TEMPLATE` / `_METRICS_URL_TEMPLATE` settings). A repeated or refused update records nothing;
  jobs older than the history table carry reconstructed started/finished events marked `backfilled`. `GET /incidents`, `POST /incidents/{id}/resolve`.
- **Monitoring:** `/monitoring/overview|services|workers|queues|errors|metrics|links`, `POST /monitoring/scan`.
- **Management UI:** served at `/` (`/ui` redirects there; static, no build step): overview, workflow explorer and detail (timeline, steps and
  attempts, errors, trace link, event history), services, workers, error explorer, incidents. It browses without a key and asks for the key only
  when you change something (replay a run, resolve an incident); it keeps it for the browser tab. Runs and attempts carry a `trace_url` when `OBSKIT_PLATFORM_JAEGER_URL` is set.
- A background scan marks instances and workers `UNHEALTHY` after `OBSKIT_PLATFORM_HEARTBEAT_TIMEOUT_S`
  without a heartbeat and opens an incident; the next heartbeat resolves it. A workflow that ends `FAILED` or
  `TIMED_OUT` also opens an incident.
- **Retention:** the same background loop turns an `UNHEALTHY` instance/worker silent for `OBSKIT_PLATFORM_LOST_AFTER_S`
  (default 24 h) into `STOPPED` and closes its incident, then deletes `STOPPED` ones silent for
  `OBSKIT_PLATFORM_PURGE_AFTER_S` (default 7 days). Jobs, job events and incidents keep their history and only lose the worker link.
- **No duplicate registrations:** registering is an upsert keyed on `(service name, environment)`, `(service, instance_id)`
  and `(instance, worker_name)`, so duplicates only appear when a client changes one of those between runs. Clients must
  set a fixed `OBSKIT_INSTANCE_ID` (one per process/task, never a pid or random value) and fixed environment and worker names.
- **Active health checks and infra figures:** besides the heartbeats a service pushes, the platform probes each
  instance's `health_url` every `OBSKIT_PLATFORM_HEALTH_PROBE_INTERVAL_S` (default 30 s) and keeps the history
  (`OBSKIT_PLATFORM_HEALTH_RETENTION_DAYS`, default 14). `UP`/`DOWN`, latency and the figures below are recorded;
  `OBSKIT_PLATFORM_HEALTH_FAIL_THRESHOLD` (default 3) consecutive failures open an incident and count as an outage.
  `GET /monitoring/infra/instances` and `/infra/hosts` (`window_hours`) report uptime, outages, latency percentiles,
  CPU/memory/disk and findings per host; the UI shows them under **Infra**. A service that missed heartbeats but still
  answers its health URL is a client problem, not an outage, and the two views now show the difference.

  Set the URL at registration (`"metadata": {"health_url": "https://svc.example.com/health"}`) or later with
  `PUT /services/{service_id}/instances/{instance_id}/health-url` (`{"health_url": null}` stops probing). The URL must
  be reachable from the platform; redirects are not followed and only `http`/`https` is accepted. Instances that
  reported a clean stop are not probed.

  The health response is JSON; HTTP 2xx means up (a body `status` of `down`/`error`/`fail`/`unhealthy` means down).
  To report infra figures, include any of these numbers at the top level or under `"system"` (anything else is ignored):
  host-level `cpu_percent`, `memory_percent`, `disk_percent`, `load_1m`, `cpu_count`, `memory_total_mb`,
  `memory_used_mb`, `disk_total_gb`, `disk_used_gb`; service-level `process_cpu_percent`, `process_memory_mb`,
  `active_requests`, `queue_depth`. Example (FastAPI + `psutil`):

  ```python
  @app.get("/health")
  def health():
      vm = psutil.virtual_memory()
      return {"status": "ok", "system": {
          "cpu_percent": psutil.cpu_percent(interval=None), "memory_percent": vm.percent,
          "disk_percent": psutil.disk_usage("/").percent, "load_1m": os.getloadavg()[0],
          "cpu_count": psutil.cpu_count(), "process_memory_mb": psutil.Process().memory_info().rss / 1e6}}
  ```

  Capacity findings are only as good as the history behind them: judge a host after it has seen a normal busy period.
  The probe makes outbound requests to URLs that holders of the API key supply, so keep the key private.

## Ordering rules

State only moves forward, so arrival order does not change the result. Each stored event gets a
disposition: `APPLIED`, `STALE` (late or no-op; history kept) or `QUARANTINED` (contradicts current
state, e.g. a second, different terminal state). A step's order is `(attempt_number, status rank)`, so a
higher attempt supersedes a failed lower one. `STEP_FAILED` with `data.will_retry = true` puts the step in
`RETRYING`. Replay re-applies events by `occurred_at`, which resolves arrival-order conflicts deterministically.

## Deviations from the spec (CLAUDE.md conventions win)

- No `/api/v1` prefix (no second version exists yet).
- Single open `GET /health` instead of `/health/live` + `/health/ready`.
- `app/<package-per-concern>` layout instead of `apps/ domain/ repositories/`.
- Auth is a shared `X-API-Key` header, required only for requests that change data (POST/PUT/PATCH/DELETE) and for
  `/openapi.json`; read-only `GET` routes are open so the UI browses without a key. Anyone who can reach the host can read
  all registry, job, event and error data, so put it behind a private network or an access proxy if that is not acceptable.
  RBAC for the UI is not built.
- The UI is served at `/` and its assets at `/ui/static`, with a strict CSP (no inline script or style).
- `/docs` and `/redoc` are disabled (they cannot send the API key). The OpenAPI schema is served at
  `GET /openapi.json` behind the key.
- `POST /events` and `POST /events/batch` accept raw JSON objects and validate each one inside
  `EventIngestionService` (not via a Pydantic body). A malformed event must be recorded as `REJECTED` in
  `rejected_events` and must not fail the rest of a batch, which a request-level 422 would do.

## Choices where the spec was open

- Run/step/attempt/event identifiers are SDK-generated strings (`run_key`, `step_key`, `event_id`); the
  platform keeps its own UUID primary keys beside them.
- `step_attempts.worker_key` is the worker's name as the SDK reports it; it is not a foreign key to `workers`.
- Jobs keep the SDK's `workflow_run_key` so a job that arrives before its run is linked when the run appears.
- `event_id` is a string, not a UUID: the contract examples use `evt-123`.
- Only `workflow_events.disposition*` change after insert (on replay); payloads are never rewritten.

## Not built yet

RabbitMQ consumer, retention and time partitioning, role-based access, and anything that notifies people about
incidents. Telemetry (OpenTelemetry, Prometheus, Jaeger, Perses) runs beside this service, see the observability-stack repository.

## Integrating other services

`integrations/claude-skill/obs-integration/` is a Claude skill meant to be copied into **other** services'
repos so they can connect to this platform (register, heartbeat, health, workers, jobs, workflow events,
trace ids). It is not used by this repo itself; see `integrations/claude-skill/README.md`.
