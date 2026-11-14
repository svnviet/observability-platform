---
name: obs-scope
description: Keep work on the OBS platform itself aligned with its scope. Use when adding or changing an OBS feature, API route, table, event contract or UI view, when asked "does OBS support X", when auditing capability coverage (SUPPORTED/PARTIAL/NOT_SUPPORTED), or when working on log/trace/metric/dashboard correlation. Not for connecting another service to OBS (that is the obs-integration skill in integrations/).
---

# OBS scope guard

You are working on the OBS platform: a generic control plane that tracks the lifecycle of **any**
service's Service / Instance / Worker / Job / Workflow / Incident, and **links** them to telemetry
backends. Two documents define the scope; read the relevant part first, never restate it here:

- `docs/OBS_SCOPE.md` — in/out of scope, the capability checklist (IDs `SYS-01` … `REL-15`, with
  priority P0/P1/P2 and a `Status` column).
- `docs/correlation-design.md` — the correlation contract (IDs, `trace_id`/`span_id`, `obs.*`),
  rules, and the current-state gap table.

Code conventions (layout, classes, auth, testing, commits) come from `CLAUDE.md`. Follow them; this
skill does not replace them.

## Hard rules (check every change against these)

1. **OBS stores lifecycle + correlation IDs, never log/trace/metric content.** Link to Loki / Jaeger
   / Prometheus / Perses instead (ADR-0002, ADR-0012). A table or column that holds log lines, spans
   or time series is a scope violation.
2. **Generic, not Tin360-specific.** No hard-coded service, workflow or step names; domain
   specifics are configuration or data.
3. **OBS tracks, it does not execute.** No workflow orchestration, no queue/scheduler.
4. **Entity identity stays distinct:** `job_id` (OBS UUID) ≠ `external_job_id`; `workflow_id` ≠
   `workflow_run_id`; a workflow can span several traces. Never merge or substitute them.
5. **No high-cardinality labels:** `job_id`, `workflow_run_id`, `trace_id` must not become
   Prometheus labels or Loki indexed labels in any link template, query or doc.
6. **Links are template-driven:** values URL-encoded, no caller-supplied LogQL/PromQL, a bounded
   time range, and a link is `available: false` when a needed value is missing.
7. **Fail-open and idempotent ingestion:** a bad event/job update is recorded as rejected or
   ignored, never a crash; replays and duplicates are safe. Ordering rules in the README hold.
8. **OBS-specific attributes use the `obs.*` prefix**, not OTel semantic-convention names.

## Process

1. **Map the request to the checklist.** Name the IDs it affects (e.g. `JOB-12`, `TRACE-04`). If it
   fits none, say so and decide whether it is out of scope (see `docs/OBS_SCOPE.md` §1) before
   building. Prefer P0 over P1 over P2 when choosing what to do first.
2. **Check the gap table** in `docs/correlation-design.md` §3 if the work touches correlation,
   links, trace/log/metric data or dashboards; extend an existing gap instead of inventing a
   parallel mechanism (e.g. reuse `app/jobs/links.py` rendering rather than a new URL builder).
3. **Design the smallest change** that satisfies the hard rules. Schema changes: write the
   Alembic migration file and tests, but do not run it against a shared/real database; say so.
4. **Implement per `CLAUDE.md`** (service/repository classes, thin routes, config in
   `app/core/config.py` + `.env.example`, `X-API-Key` on writes).
5. **Test:** add pytest cases next to the existing ones (`tests/test_*.py`), including the
   failure path (missing trace id → link unavailable, duplicate event, unknown entity → 404).
6. **Update the docs in the same change:** `docs/api.md` for routes, `docs/data-model.md` for
   tables, and the `Status` of each affected checklist ID in `docs/OBS_SCOPE.md` (and the gap table
   if a gap closed). If the event or job contract changed, also update
   `integrations/claude-skill/obs-integration/reference.md` — that skill is how other services
   learn the contract, so a drift there silently breaks integrations.

## Capability audit mode

When asked "what does OBS support?" or to fill `Status`:

- For each ID, find evidence in code (route, repository query, schema column) and in tests; do not
  judge from names. Record `SUPPORTED` only if data exists **and** an endpoint/view answers the
  question; `PARTIAL` if the data exists but the answer needs a manual step or lacks a link;
  `NOT_SUPPORTED` otherwise; `NOT_APPLICABLE` only with a reason tied to scope.
- Cite the evidence as `file:line` or `GET /path` in the Status cell or a notes column.
- Report totals per group and the P0 items that are not `SUPPORTED`.

## Definition of done

Hard rules hold; tests pass (`python -m pytest`, plus `ruff check` / `ruff format --check` if
present); docs and checklist statuses updated; migrations written but not applied; any contract
change mirrored in the integration skill. State plainly what you ran and what you could not.
