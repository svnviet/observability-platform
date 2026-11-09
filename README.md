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
- **Jobs and incidents:** `POST|GET /jobs`; `GET /incidents`, `POST /incidents/{id}/resolve`.
- **Monitoring:** `/monitoring/overview|services|workers|queues|errors|metrics|links`, `POST /monitoring/scan`.
- **Management UI:** `GET /ui` (static, no build step): overview, workflow explorer and detail (timeline, steps and
  attempts, errors, trace link, event history), services, workers, error explorer, incidents. It asks for the API key
  and keeps it for the browser tab. Runs and attempts carry a `trace_url` when `OBSKIT_PLATFORM_JAEGER_URL` is set.
- A background scan marks instances and workers `UNHEALTHY` after `OBSKIT_PLATFORM_HEARTBEAT_TIMEOUT_S`
  without a heartbeat and opens an incident; the next heartbeat resolves it. A workflow that ends `FAILED` or
  `TIMED_OUT` also opens an incident.

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
- Auth is a shared `X-API-Key` header; RBAC for the UI is not built.
- `/ui` (the static shell and its assets) is open besides `/health`: a browser cannot send a header when it navigates,
  the shell holds no data, and it is served with a strict CSP (no inline script or style). Every data call needs the key.
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
