import uuid
from datetime import UTC, datetime, timedelta

from app.core.config import dashboard_url_template
from app.db.observability_repository import ObservabilityRepository
from app.jobs.links import link, logs_link, metrics_link, render
from app.schemas.observability import EntityObservability, EntityRef
from app.workflows.service import trace_url

_PAD = timedelta(minutes=5)
_MAX_WINDOW = timedelta(hours=24)  # a link may never ask a backend for more than a day of data


class ObservabilityService:
    """Builds the correlation ids and telemetry links for services, workers, workflow runs and incidents.

    Backends are reached only through configured URL templates; callers cannot supply queries.
    """

    def __init__(self, repo: ObservabilityRepository) -> None:
        self._repo = repo

    def for_service(self, service_id: uuid.UUID) -> EntityObservability | None:
        service = self._repo.service(service_id)
        if service is None:
            return None
        values = {"service": service.name, "environment": service.environment}
        return self._build("service", service.id, values, trace_id=None)

    def for_worker(self, worker_id: uuid.UUID) -> EntityObservability | None:
        worker = self._repo.worker(worker_id)
        if worker is None:
            return None
        instance = self._repo.instance(worker.service_instance_id)
        service = self._repo.service(instance.service_id) if instance else None
        values = {
            "service": service.name if service else None,
            "environment": service.environment if service else None,
            "instance": instance.instance_id if instance else None,
            "worker": worker.worker_name,
        }
        return self._build("worker", worker.id, values, trace_id=None)

    def for_run(self, run_id: uuid.UUID) -> EntityObservability | None:
        run = self._repo.run(run_id)
        if run is None:
            return None
        values = {"workflow_id": run.workflow_id, "workflow_run_id": run.run_key}
        return self._build("workflow_run", run.id, values, trace_id=run.trace_id)

    def for_incident(self, incident_id: uuid.UUID) -> EntityObservability | None:
        incident = self._repo.incident(incident_id)
        if incident is None:
            return None
        service = self._repo.service(incident.service_id)
        worker = self._repo.worker(incident.worker_id)
        instance = self._repo.instance(worker.service_instance_id) if worker else None
        run = self._repo.run(incident.workflow_run_id)
        start, end = self._window(incident.detected_at, incident.resolved_at)
        values = {
            "service": service.name if service else None,
            "environment": service.environment if service else None,
            "instance": instance.instance_id if instance else None,
            "worker": worker.worker_name if worker else None,
            "workflow_id": run.workflow_id if run else None,
            "workflow_run_id": run.run_key if run else None,
            "from": str(int(start.timestamp() * 1000)),  # epoch milliseconds, the form Grafana-style tools take
            "to": str(int(end.timestamp() * 1000)),
        }
        return self._build("incident", incident.id, values, trace_id=run.trace_id if run else None)

    @staticmethod
    def _window(detected_at: datetime, resolved_at: datetime | None) -> tuple[datetime, datetime]:
        """Incident time range with a little context either side, never wider than a day."""
        end = (resolved_at or datetime.now(UTC)) + _PAD
        start = max(detected_at - _PAD, end - _MAX_WINDOW)
        return start, end

    @staticmethod
    def _build(
        kind: str, id_: uuid.UUID, values: dict[str, str | None], *, trace_id: str | None
    ) -> EntityObservability:
        values = {**values, "trace_id": trace_id}
        links = {
            "logs": logs_link(values),
            "trace": link(trace_url(trace_id)),
            "metrics": metrics_link(values),
            "dashboard": link(render(dashboard_url_template(), values)),
        }
        correlation = {k: v for k, v in values.items() if k not in ("from", "to")}
        return EntityObservability(
            entity=EntityRef(type=kind, id=id_),
            correlation=correlation,
            links=links,
            capabilities={name: item.available for name, item in links.items()},
        )
