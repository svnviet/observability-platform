# Log format: ready for trace correlation

Goal: every log line a service writes can be found from OBS by `job_id`, `workflow_run_id` or
`trace_id` (Loki), and jumps to the trace (Jaeger) — with no per-service custom parsing.

## Rules

1. **One JSON object per line to stdout or stderr** (`svn-obskit` uses stderr) (let the platform/Promtail/Collector ship it). No
   multi-line text; put stack traces inside the `stack_trace` field.
2. **Fixed field names** (below). Do not rename per service.
3. **IDs are log fields, not labels.** Only low-cardinality fields may become Loki labels:
   `service_name`, `instance_id`, `environment`, `level`. Never label by
   `trace_id`, `job_id`, `workflow_run_id`, `job_id`.
4. Context fields are filled **automatically from the current job/workflow context** (contextvars),
   not passed by hand at each call site. Outside a job/request they are simply omitted.
5. UTC ISO 8601 `timestamp`, `level` ∈ `DEBUG INFO WARNING ERROR CRITICAL`.
6. Never log secrets, tokens, API keys or PII. Truncate large payloads.

## Fields

| Field | Required | Meaning |
|---|---|---|
| `timestamp` | yes | UTC ISO 8601 |
| `level` | yes | log level |
| `message` | yes | short human text |
| `service_name` | yes | same as OBS `service_name` |
| `instance_id` | yes | same as OBS `instance_id` |
| `environment` | yes | same as OBS `environment` |
| `trace_id` | when in a trace | 32 hex chars (OTel trace id) |
| `span_id` | when in a span | 16 hex chars |
| `job_id` | in a job | the job's `external_job_id` (service's own id) |
| `worker_id` | in a worker | `worker_name` |
| `workflow_id` | in a workflow | `workflow_id` |
| `workflow_run_id` | in a workflow | `workflow_run_id` |
| `step_id` | in a step | `step_id` |
| `step_attempt_id` | in a step/job | attempt number (int) |
| `exception_type`, `stack_trace` | on errors | exception info |
| `event` | optional | stable machine name, e.g. `job.failed`, `render.timeout` |

Field names are the ones `svn-obskit` emits (the standard for every Tin360/OBS service); do not rename them. Log the **same ids you send to OBS** (`external_job_id`, `workflow_run_id`,
`trace_id`), so a search from OBS finds the lines.

Example line:

```json
{"timestamp":"2026-11-14T10:00:01.234Z","level":"ERROR","message":"render timed out",
 "service_name":"video-service","instance_id":"video-1","environment":"production",
 "trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","span_id":"00f067aa0ba902b7",
 "job_id":"job-123","worker_id":"w-1","workflow_id":"video","workflow_run_id":"run-001",
 "step_id":"render","step_attempt_id":"run-001:render:2","event":"job.failed",
 "exception_type":"TimeoutError","stack_trace":"Traceback ..."}
```

## Querying (what OBS links to)

- Loki by job: `{service_name="video-service"} | json | job_id="job-123"`
- by trace: `{...} | json | trace_id="<id>"`; by run: `| json | workflow_run_id="run-001"`
  - Jaeger: open the `trace_id`; logs ↔ spans match on `trace_id` + `span_id`.

## Context propagation

Across HTTP: send `traceparent` (`00-<trace_id>-<parent_span_id>-01`). Across queues: put
`traceparent`, `job_id`, `workflow_id`, `workflow_run_id`, `step_id`, `attempt` in the message
envelope; the consumer restores them into the log context before doing work. If the service has
OpenTelemetry, take `trace_id`/`span_id` from the current span; otherwise generate a 32-hex
`trace_id` at the entry point and pass it on. Wrong or absent context must never raise.

A service using `svn-obskit` gets exactly this format from `Observability.initialize()`; `log_template.py` is only for services that do not use the SDK.
