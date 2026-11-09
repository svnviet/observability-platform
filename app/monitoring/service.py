import statistics
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db.models import (
    IncidentRow,
    JobRow,
    RejectedEventRow,
    ServiceInstanceRow,
    WorkerRow,
    WorkflowEventRow,
    WorkflowRunRow,
    WorkflowStepRow,
)
from app.db.monitoring_repository import MonitoringRepository
from app.registry.service import RegistryService
from app.schemas.enums import IncidentStatus, JobStatus, WorkerStatus
from app.schemas.ops import ErrorGroup, MetricSummary, OverviewRead, QueueStat
from app.schemas.registry import ServiceRead, WorkerRead

_ACTIVE_WORKFLOWS = ("CREATED", "QUEUED", "RUNNING")
_ACTIVE_WORKERS = ("IDLE", "BUSY", "STARTING", "REGISTERED", "DRAINING")
_ERROR_WINDOW = 2000  # most recent failed attempts considered when grouping errors


class MonitoringService:
    def __init__(self, stats: MonitoringRepository, registry: RegistryService) -> None:
        self._stats = stats
        self._registry = registry

    def overview(self) -> OverviewRead:
        s = self._stats
        services = self._registry.list_services()
        by_status = s.group_count(WorkflowRunRow.status)
        return OverviewRead(
            services_total=len(services),
            services_healthy=sum(1 for x in services if x.status == "HEALTHY"),
            services_unhealthy=sum(1 for x in services if x.status in ("UNHEALTHY", "DEGRADED")),
            instances_total=s.count(ServiceInstanceRow),
            workers_total=s.count(WorkerRow),
            workers_active=s.count(WorkerRow, WorkerRow.status.in_(_ACTIVE_WORKERS)),
            workers_unhealthy=s.count(WorkerRow, WorkerRow.status == WorkerStatus.UNHEALTHY.value),
            workflows_active=sum(by_status.get(k, 0) for k in _ACTIVE_WORKFLOWS),
            workflows_completed=by_status.get("COMPLETED", 0),
            workflows_failed=by_status.get("FAILED", 0) + by_status.get("TIMED_OUT", 0),
            jobs_running=s.count(JobRow, JobRow.status == JobStatus.RUNNING.value),
            jobs_queued=s.count(JobRow, JobRow.status == JobStatus.QUEUED.value),
            open_incidents=s.count(IncidentRow, IncidentRow.status == IncidentStatus.OPEN.value),
            rejected_events=s.count(RejectedEventRow),
        )

    def services(self) -> list[ServiceRead]:
        return self._registry.list_services()

    def workers(
        self, *, status: WorkerStatus | None, service: str | None, limit: int, offset: int
    ) -> list[WorkerRead]:
        return self._registry.list_workers(status=status, service=service, limit=limit, offset=offset)

    def queues(self) -> list[QueueStat]:
        now = datetime.now(UTC)
        per_service: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        oldest_queued: dict[str, datetime] = {}
        for name, status, count, oldest in self._stats.job_stats():
            per_service[name][status] = count
            if status == JobStatus.QUEUED.value and oldest is not None:
                oldest_queued[name] = oldest
        return [
            QueueStat(
                service_name=name,
                queued=counts.get("QUEUED", 0),
                running=counts.get("RUNNING", 0),
                completed=counts.get("COMPLETED", 0),
                failed=counts.get("FAILED", 0),
                oldest_queued_age_s=(now - oldest_queued[name]).total_seconds()
                if name in oldest_queued
                else None,
            )
            for name, counts in sorted(per_service.items())
        ]

    def errors(self, window_hours: int, limit: int) -> list[ErrorGroup]:
        since = datetime.now(UTC) - timedelta(hours=window_hours)
        groups: dict[tuple, dict] = {}
        for error, finished_at, service, workflow, run_id in self._stats.failed_attempts(
            since, _ERROR_WINDOW
        ):
            error = error or {}
            key = (error.get("type", "Unknown"), service, workflow)
            group = groups.setdefault(
                key,
                {
                    "count": 0,
                    "first": finished_at,
                    "last": finished_at,
                    "message": error.get("message"),
                    "run": run_id,
                },
            )
            group["count"] += 1
            if finished_at:
                group["first"] = min(group["first"] or finished_at, finished_at)
                group["last"] = max(
                    group["last"] or finished_at, finished_at
                )  # newest-first rows: sample = latest
        ranked = sorted(groups.items(), key=lambda kv: kv[1]["count"], reverse=True)[:limit]
        return [
            ErrorGroup(
                exception_type=etype,
                service_name=service,
                workflow_name=workflow,
                count=g["count"],
                first_seen=g["first"],
                last_seen=g["last"],
                sample_message=g["message"],
                sample_workflow_run_id=g["run"],
            )
            for (etype, service, workflow), g in ranked
        ]

    def metrics(self, window_hours: int) -> MetricSummary:
        s = self._stats
        since = datetime.now(UTC) - timedelta(hours=window_hours)
        durations = s.completed_durations(since, 5000)
        p95 = None
        if len(durations) >= 2:
            p95 = float(statistics.quantiles(durations, n=100, method="inclusive")[94])
        elif durations:
            p95 = float(durations[0])
        return MetricSummary(
            window_hours=window_hours,
            workflows_by_status=s.group_count(WorkflowRunRow.status, WorkflowRunRow.created_at >= since),
            workflow_duration_avg_ms=(sum(durations) / len(durations)) if durations else None,
            workflow_duration_p95_ms=p95,
            steps_by_status=s.group_count(
                WorkflowStepRow.status,
                WorkflowStepRow.workflow_run_id.in_(
                    select(WorkflowRunRow.id).where(WorkflowRunRow.created_at >= since)
                ),
            ),
            attempts_total=s.attempts_since(since),
            retries_total=s.retries_since(since),
            events_received=s.count(WorkflowEventRow, WorkflowEventRow.received_at >= since),
            events_by_disposition=s.group_count(
                WorkflowEventRow.disposition, WorkflowEventRow.received_at >= since
            ),
        )
