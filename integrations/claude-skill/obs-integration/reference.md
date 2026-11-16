# OBS integration reference

Base URL = `OBS_URL`. JSON everywhere, UTC ISO 8601 timestamps with timezone. Writes need
`X-API-Key`; `GET` routes and `/health` do not. No version prefix.
(Live schema: `GET $OBS_URL/openapi.json` with the API key. If this file and the live schema disagree, the live schema wins.)

## Register / heartbeat

```
POST /services/register
{"service_name":"video-service","instance_id":"video-1","environment":"production",
 "service_version":"1.2.0","hostname":"host-a","metadata":{"health_url":"https://svc.example/health"}}
→ ServiceRegisterOut (contains the service id used in the heartbeat path)

POST /services/{service_id}/heartbeat   {"instance_id":"video-1","stopping":false}   # 404 → re-register
PUT  /services/{service_id}/instances/{instance_id}/health-url   {"health_url":"https://..."|null}
```
Re-registering the same `(service_name, environment)` + `instance_id` is an upsert.

Edit and remove (all need `X-API-Key`):
```
PATCH  /services/{service_id}                          {"version":"1.3.0","metadata":{"team":"media","old_key":null}}
PATCH  /services/{service_id}/instances/{instance_id}  {"hostname":"host-b","metadata":{"health_url":"https://..."}}
DELETE /services/{service_id}/instances/{instance_id}  # any state; removes its workers; jobs keep their history
DELETE /services/{service_id}[?delete_jobs=true]       # 409 while an instance is not STOPPED, or while jobs exist
PATCH  /workers/{worker_id}                            {"capacity":4,"worker_type":"render","metadata":{}}
DELETE /workers/{worker_id}
DELETE /workflow-runs/{run_id}[?force=true]            # force is required for a run that has not finished
```
Only the fields sent change; `metadata` is merged and a key set to `null` is removed. `service_name` and
`environment` are the identity and cannot be edited. Use these to clean up after yourself (a retired instance,
a test run); never delete another service's records.

## Workers

```
POST /workers/register  {"service_name","instance_id","worker_name","environment","service_version",
                         "worker_type","capacity":4,"metadata":{}}
POST /workers/{worker_id}/heartbeat {"status":"BUSY","current_job_id":"job-1"}
POST /workers/{worker_id}/status    {"status":"STOPPED"}
```
Worker status: `REGISTERED STARTING IDLE BUSY DRAINING STOPPED UNHEALTHY`.

## Jobs

```
POST /jobs
{"service_name":"video-service","external_job_id":"job-123","status":"RUNNING",
 "environment":"production","instance_id":"video-1","worker_name":"w-1",
 "workflow_run_key":"run-001","trace_id":"<trace id>","metadata":{},
 "error":{"type":"TimeoutError","message":"..."}}        # error only with FAILED
```
Job status: `QUEUED RUNNING COMPLETED FAILED CANCELLED`. Terminal states are final.
Query by your own id: `GET /jobs?external_job_id=job-123`. Detail: `/jobs/{uuid}`,
`/jobs/{uuid}/events`, `/jobs/{uuid}/timeline`, `/jobs/{uuid}/observability`.

## Events

```json
{
  "event_id": "unique-per-event",
  "event_type": "STEP_FAILED",
  "event_version": 1,
  "occurred_at": "2026-11-14T10:00:00Z",
  "source":  {"service_name": "video-service", "instance_id": "video-1", "worker_id": "w-1",
              "environment": "production", "service_version": "1.2.0"},
  "context": {"workflow_id": "video", "workflow_run_id": "run-001", "correlation_id": "c-1",
              "trace_id": "abc123", "step_id": "render", "step_attempt_id": "render-1"},
  "data":    {"workflow_name": "Video", "step_name": "Render", "attempt_number": 1,
              "will_retry": true, "error": {"type": "TimeoutError", "message": "slow"}}
}
```
Required: `event_id`, `event_type`, `occurred_at` (with timezone), `source.service_name`,
`context.workflow_id`, `context.workflow_run_id`; `STEP_*` also `context.step_id`.
`event_version` is `1`. Extra keys in `data` are kept.

Event types: `WORKFLOW_CREATED QUEUED STARTED COMPLETED FAILED CANCELLED TIMED_OUT` (prefix
`WORKFLOW_`) and `STEP_QUEUED STEP_STARTED STEP_COMPLETED STEP_FAILED STEP_SKIPPED STEP_CANCELLED`.

Response `outcome`: `ACCEPTED` (`disposition` `APPLIED`/`STALE`/`QUARANTINED`), `DUPLICATE`
(idempotent, safe), `REJECTED` (HTTP still 200; fix the event, see `GET /events/rejected`).
Batch: `POST /events/batch {"events":[...]}` returns `accepted`/`duplicates`/`rejected` counts;
one bad event does not fail the batch.

Optional: `POST /workflows` registers a definition; `POST /workflow-runs` creates a run
explicitly (idempotent by run id). Events create runs implicitly, so most services skip both.

Typical lifecycle: `WORKFLOW_STARTED` → per step `STEP_STARTED` → `STEP_COMPLETED`/`STEP_FAILED`
→ `WORKFLOW_COMPLETED` / `WORKFLOW_FAILED` (a run ending FAILED/TIMED_OUT opens an incident).

## `/health` contract (service side)

OBS calls `GET <health_url>` every 30 s (default). 2xx = UP. Body `status` of
`down|error|fail|failed|unhealthy` = DOWN. Redirects are not followed, body ≤ 64 KB, timeout 5 s.
Optional numbers at top level or under `"system"`: `cpu_percent memory_percent disk_percent
load_1m cpu_count memory_total_mb memory_used_mb disk_total_gb disk_used_gb process_cpu_percent
process_memory_mb active_requests queue_depth`.

## Timing defaults (server side, may differ per deployment)

| Setting | Default | Implication for the client |
|---|---|---|
| Heartbeat timeout | 30 s | heartbeat every ~10 s |
| Health probe interval | 30 s | `/health` must answer within 5 s |
| Probe failures to open incident | 3 | |
| Silent → STOPPED | 24 h | |
| STOPPED → purged | 7 days | jobs/incidents keep history |

## Read endpoints useful for checks

`GET /services`, `/workers`, `/jobs`, `/workflow-runs`, `/incidents?status=OPEN`,
`/monitoring/overview|queues|errors|metrics`, `/monitoring/infra/instances|hosts`.
