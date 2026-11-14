---
name: obs-integration
description: Connect any service to the OBS (observability) platform. Use when asked to integrate, onboard, instrument, or "hook up" a service, worker, job queue or workflow to OBS — registering the service, sending heartbeats, exposing /health, reporting job status and workflow events, and propagating trace_id. Works for any language/framework; OBS is generic and not tied to one product.
---

# OBS integration

> **Audience:** this skill is installed in *other* services' repos (copied to `.claude/skills/`) so
> they can connect to OBS. It is not for working on the OBS platform itself.

Make a service report itself to OBS so it appears in the service registry, health/infra views,
job tracking, workflow timelines and incidents. OBS is **generic**: nothing here is specific to
one product. Details of every field live in `reference.md`; a drop-in Python client is in
`client_template.py`.

## Golden rules

1. **OBS must never break the host service.** Every OBS call is best-effort: short timeout
   (≤ 2 s), catch all exceptions, never block the request/job path (send from a background
   thread/task), never let a failure propagate. If OBS is down, the service runs as normal.
2. **Stable identities.** `service_name`, `environment`, `instance_id`, `worker_name` must be
   fixed across restarts (e.g. `OBS_INSTANCE_ID` = hostname/pod/task name). Never use a pid or
   random value, or each restart creates a duplicate registration.
3. **Secrets via env, never in code or logs.** `OBS_URL`, `OBS_API_KEY`. Writes (POST/PUT) need
   header `X-API-Key`; reads are open.
4. **Idempotent and ordered by time.** Events dedupe on `event_id`; job and register calls are
   upserts, so retrying is always safe. Use real UTC timestamps with timezone in `occurred_at`.
5. **No secrets or PII in `metadata`, `error` or `data`.**

## Four concepts — do not mix them up

OBS models four different things. Most integration mistakes are reporting one as another
(e.g. a job as a workflow) or skipping one because it "looks like" another.

| Concept | What it is | Lifetime | Identity (you choose, keep fixed) | Reported via | OBS answers |
|---|---|---|---|---|---|
| **Service** | A deployable application (API, consumer, scheduler). Each running process/pod is an **instance**. | Long-lived; one record per process | `service_name` + `environment`; instance = `instance_id` | register, heartbeat, `/health` | Is it up? healthy? which instance? infra? |
| **Worker** | A concurrent executor *inside* a service instance that takes jobs (thread pool, Celery/RQ worker, consumer loop). | Long-lived, per instance | `worker_name` (within instance), `capacity` | worker register, heartbeat/status | idle/busy/stuck? which job now? over capacity? |
| **Job** | One unit of work: a queue message, task, request-to-process. Has one lifecycle `QUEUED→RUNNING→terminal`. | Short; created and finishes | `external_job_id` (unique per service) | `POST /jobs` upserts | state, duration, retries, error, who ran it |
| **Workflow (run)** | A multi-step business process, usually spanning jobs and often several services, with named steps. | Medium; a run has many steps/attempts | `workflow_id` (the kind) + `workflow_run_id` (one execution) | events (`WORKFLOW_*`, `STEP_*`) | which step, where stuck/failed, total time, retries |

How to tell them apart, in order:

1. **Is it a deployed process I can start/stop?** → Service (its processes are instances).
2. **Is it a loop/thread/consumer inside that process that picks up work?** → Worker.
3. **Is it one item of work with a single start and a single outcome?** → Job.
4. **Does a business outcome need several ordered steps (possibly in different services),
   where "which step failed?" matters?** → Workflow; each step is `STEP_*`, and the jobs that
   execute those steps link to it via `workflow_run_key` = `workflow_run_id`.

Relationships (link them, or OBS cannot answer cause questions):
`Service 1—N Instance 1—N Worker`; a Job runs on one worker (send `instance_id` + `worker_name`);
a Job may belong to one Workflow run (send `workflow_run_key`); all of them share a `trace_id`.
A step ≠ a job: a step is a stage of a workflow, a job is a unit of execution; one step may
run as one job, several, or none (inline code). A workflow with a single step and no handoff is
usually just a job — don't create workflows for trivial work.

Common mistakes: one "service" per queue or per request; using a pid/random id as `instance_id`;
reporting workers only as jobs (worker view stays empty); sending job `FAILED` while the
workflow never gets `WORKFLOW_FAILED`; different `workflow_run_id` in each service for the same
run; marking a job terminal before its retries are over.

## Process

1. **Inventory the target repo first** and write the result as a table before coding — this is
   what prevents omissions. Search for each row; "none" must be a conclusion, not a skip:

   | Concept | Where to look | Found (file/symbol) | Layer |
   |---|---|---|---|
   | Service/instances | entrypoints (`main`, `app`, Dockerfile CMD, compose/k8s services), one per deployable | | L1 |
   | Health | `/health`, `/healthz`, `/ready` routes | | L2 |
   | Workers | Celery/RQ/Dramatiq/Sidekiq workers, `ThreadPool`/`asyncio` consumers, queue consumers, cron/scheduler loops | | L3 |
   | Jobs | task definitions, queue publish/consume, `enqueue`/`delay`/`apply_async`, DB tables with status columns, webhook handlers that defer work | | L4 |
   | Workflows | multi-stage pipelines, state machines, saga/orchestrator code, calls chained across services, step enums | | L5 |
   | Correlation | existing trace/request/correlation ids, OTel setup, logging config | | L6 |

   Every deployable in the repo (not just the main one: also separate worker/scheduler
   processes) needs its own L1. Every place work enters a queue and every place it is consumed
   needs L4 at *both* ends (QUEUED at enqueue, RUNNING/terminal at consume). Integrate only the
   layers that exist; ask the user only for what you cannot find: `OBS_URL`, where the API key
   is kept, `service_name`, environment.
2. **Add configuration** (env vars, with the repo's existing config mechanism):
   `OBS_URL`, `OBS_API_KEY`, `OBS_SERVICE_NAME`, `OBS_ENVIRONMENT`, `OBS_INSTANCE_ID`,
   `OBS_ENABLED` (default true; false = all calls are no-ops). Add them to `.env.example`.
3. **Implement the layers** below, copying `client_template.py` (Python) or porting its shape
   to the service's language. Keep OBS code in one module/package.
4. **Verify against a real OBS** (see Verification). Report what you ran and what you saw;
   if you could not reach OBS, say so rather than claiming it works.

## Layers (do in this order; stop where the service has nothing to report)

### L1 — Register + heartbeat (every service)
- On startup: `POST /services/register` with `service_name`, `instance_id`, `environment`,
  `service_version`, `hostname`, and `metadata.health_url` if the service has one.
- Every ~10 s (must be well under OBS's heartbeat timeout, default 30 s):
  `POST /services/{service_id}/heartbeat` `{"instance_id": ...}`. `service_id` comes from the
  register response. If heartbeat returns 404, re-register.
- On graceful shutdown: heartbeat with `"stopping": true`.

### L2 — Health endpoint (every HTTP service)
Expose `GET /health` returning HTTP 2xx and JSON `{"status": "ok", "system": {...}}`. OBS probes
it every 30 s for uptime, latency and outages. Include host figures when cheap
(`cpu_percent`, `memory_percent`, `disk_percent`, `load_1m`, `process_memory_mb`,
`queue_depth`, ...; full list in `reference.md`). Return `status` `down|error|fail|unhealthy`
(or non-2xx) when a critical dependency is broken. Register the URL via `metadata.health_url`;
it must be reachable **from OBS**, not just from localhost.

### L3 — Workers (services that run background workers)
`POST /workers/register` per worker (`worker_name`, `capacity`, `worker_type`), then
`POST /workers/{worker_id}/heartbeat` with `status` (`IDLE`/`BUSY`) and `current_job_id` while
working. Set `STOPPED`/`DRAINING` via `POST /workers/{id}/status` on shutdown.

### L4 — Jobs (services with a queue/task unit)
`POST /jobs` (upsert) at every state change: `QUEUED` when created, `RUNNING` when a worker
picks it up (include `instance_id` + `worker_name`), then exactly one terminal state
`COMPLETED` / `FAILED` (with `error`) / `CANCELLED`. Always send a stable `external_job_id`,
plus `workflow_run_key` and `trace_id` when known — they are what links Job → Workflow → Trace.
Terminal jobs are frozen, so do not report a terminal state until it is really final.

### L5 — Workflow events (multi-step processes spanning steps/services)
Emit events to `POST /events` (or `/events/batch`, ≤ 1000) as the workflow progresses:
`WORKFLOW_*` and `STEP_*` (types in `reference.md`). OBS only **tracks** state from events; it
does not run or orchestrate anything. Every event needs a unique `event_id`, `event_type`,
`occurred_at`, `source.service_name`, `context.workflow_id`, `context.workflow_run_id`, and
`context.step_id` for `STEP_*`. Retry-able failure: `STEP_FAILED` with `data.will_retry: true`
and increment `attempt_number` on the next try. Different services working on the same run must
share the same `workflow_run_id`; pass it (and `trace_id`) along in messages/headers.

### L6 — Trace and log correlation
Generate or accept a `trace_id` (use the OpenTelemetry trace id if the service already has OTel;
otherwise a 32-hex random id at the start of the request/job) and: put it in every job and event
`context`, propagate it to downstream calls (`traceparent` header) and queue messages, and
include `trace_id`/`job_id`/`workflow_run_id` as fields in the service's structured logs. This is
what makes "find logs/trace for this job" answerable.

**Log format is mandatory for L6:** one JSON object per line to stdout, with the fixed field names
in `logging.md` (`service_name`, `instance_id`, `trace_id`, `span_id`, `job_id`,
`workflow_run_id`, ...; the same names `svn-obskit` emits). If the service uses `svn-obskit`, `Observability.initialize()` already does this: do not add another logger. Otherwise copy `log_template.py` (JSON formatter + `job_context()`), call
`setup_logging()` at startup and wrap each job/step in `job_context(...)` so every line carries the
context automatically. The ids in logs must be the same ones sent to OBS. Convert the service's
existing logging config instead of adding a second logger; never make IDs Loki labels.

## Do not

- Do not call OBS synchronously inside a user request or job loop, or retry in a tight loop.
- Do not invent states or event types outside the enums in `reference.md`.
- Do not register one instance per request/job; instances are per process.
- Do not hard-code the API key, base URL or tenant-specific names in shared code.
- Do not treat HTTP 200 from `/events` as accepted: check `outcome` (`REJECTED` is still 200).

## Verification (run it, do not assume)

1. `curl $OBS_URL/health` → `{"status":"ok"}`; `curl -H "X-API-Key: $OBS_API_KEY" $OBS_URL/auth/check` → `{"ok":true}`.
2. Start the service; `curl $OBS_URL/services` shows it with `HEALTHY` and an instance.
3. Wait one probe interval; `curl $OBS_URL/monitoring/infra/instances` shows `state: UP` (if L2).
4. Trigger one job/workflow; `GET /jobs?external_job_id=<id>` and `/jobs/{id}/timeline`, or
   `/workflow-runs?workflow_id=<id>`, show the expected states in order.
   Logs: run one job and check a stdout line parses as JSON (`... | jq .`) and contains
   `service_name`, `job_id`, `trace_id` (and `workflow_run_id` if a workflow), with the
   same values as in OBS `GET /jobs/{id}`.
5. Failure drill: stop the service (or kill -9) and confirm UNHEALTHY + incident after the
   timeout, then restart and confirm it recovers and the incident closes.
6. OBS-down drill: point `OBS_URL` at an unreachable host and confirm the service still starts,
   serves traffic and does not slow down.

7. Completeness check: re-run the inventory greps; every found row must map to a layer that
   is implemented or explicitly skipped with a reason. Any queue producer or consumer without
   job reporting, any worker loop without worker reporting, or any multi-step pipeline without
   events counts as a miss.

Report a short table: concept → found (file) → layer implemented / skipped (why) → verified how.
