import uuid
from datetime import UTC, datetime

from app.db.incident_repository import IncidentRepository
from app.db.models import ServiceInstanceRow, ServiceRow, WorkerRow
from app.db.registry_repository import RegistryRepository
from app.db.workflow_repository import WorkflowRepository
from app.schemas.enums import InstanceStatus, WorkerStatus
from app.schemas.registry import (
    HealthUrlOut,
    HeartbeatIn,
    InstanceRead,
    ServiceDetail,
    ServiceRead,
    ServiceRegisterIn,
    ServiceRegisterOut,
    WorkerHeartbeatIn,
    WorkerRead,
    WorkerRegisterIn,
    WorkerStatusIn,
)

_WORKER_STALE_KEY = "worker-stale:{}"
_INSTANCE_STALE_KEY = "instance-stale:{}"


def worker_stale_key(worker_id: uuid.UUID) -> str:
    return _WORKER_STALE_KEY.format(worker_id)


def instance_stale_key(instance_row_id: uuid.UUID) -> str:
    return _INSTANCE_STALE_KEY.format(instance_row_id)


class RegistryService:
    def __init__(
        self,
        session,
        registry: RegistryRepository,
        workflows: WorkflowRepository,
        incidents: IncidentRepository,
    ) -> None:
        self._session = session
        self._registry = registry
        self._workflows = workflows
        self._incidents = incidents

    # --- services -----------------------------------------------------------------------

    def set_health_url(self, service_id: uuid.UUID, instance_id: str, health_url: str | None):
        instance = self._registry.find_instance(service_id, instance_id)
        if instance is None:
            return None
        metadata = {k: v for k, v in instance.metadata_.items() if k != "health_url"}
        if health_url:
            metadata["health_url"] = health_url
        instance.metadata_ = metadata  # reassign: in-place JSON mutation is not tracked
        self._session.commit()
        return HealthUrlOut(service_id=service_id, instance_id=instance_id, health_url=health_url)

    def register_service(self, body: ServiceRegisterIn) -> ServiceRegisterOut:
        now = datetime.now(UTC)
        instance = self._register_instance(
            body.service_name,
            body.environment,
            body.service_version,
            body.instance_id,
            body.hostname,
            body.metadata,
            now,
        )
        self._recover_instance(instance, now)
        self._session.commit()
        return ServiceRegisterOut(
            service_id=instance.service_id, instance_id=instance.instance_id, status=InstanceStatus.HEALTHY
        )

    def service_heartbeat(self, service_id: uuid.UUID, body: HeartbeatIn) -> ServiceRegisterOut | None:
        service = self._registry.get_service(service_id)
        if service is None:
            return None
        instance = self._registry.find_instance(service_id, body.instance_id)
        if instance is None:
            return None
        now = datetime.now(UTC)
        instance.last_heartbeat_at = now
        if body.stopping:
            instance.status = InstanceStatus.STOPPED.value
        else:
            self._recover_instance(instance, now)
            instance.status = InstanceStatus.HEALTHY.value
        self._session.commit()
        return ServiceRegisterOut(
            service_id=service_id, instance_id=instance.instance_id, status=InstanceStatus(instance.status)
        )

    def list_services(self) -> list[ServiceRead]:
        return [
            self._service_read(s, self._registry.instances_of(s.id)) for s in self._registry.list_services()
        ]

    def get_service(self, service_id: uuid.UUID) -> ServiceDetail | None:
        service = self._registry.get_service(service_id)
        if service is None:
            return None
        instances = self._registry.instances_of(service_id)
        base = self._service_read(service, instances)
        return ServiceDetail(**base.model_dump(), instances=[_instance_read(i) for i in instances])

    # --- workers ------------------------------------------------------------------------

    def register_worker(self, body: WorkerRegisterIn) -> WorkerRead:
        now = datetime.now(UTC)
        instance = self._register_instance(
            body.service_name, body.environment, body.service_version, body.instance_id, None, {}, now
        )
        worker = self._registry.upsert_worker(
            instance, body.worker_name, body.worker_type, body.capacity, body.metadata, now
        )
        self._session.commit()
        return self._worker_read(self._registry.get_worker(worker.id))

    def worker_heartbeat(self, worker_id: uuid.UUID, body: WorkerHeartbeatIn) -> WorkerRead | None:
        return self._touch_worker(
            worker_id, body.status, body.current_job_id, clear_job=body.status is not None
        )

    def set_worker_status(self, worker_id: uuid.UUID, body: WorkerStatusIn) -> WorkerRead | None:
        return self._touch_worker(worker_id, body.status, body.current_job_id, clear_job=True)

    def get_worker(self, worker_id: uuid.UUID) -> WorkerRead | None:
        worker = self._registry.get_worker(worker_id)
        return None if worker is None else self._worker_read(worker)

    def list_workers(
        self, *, status: WorkerStatus | None, service: str | None, limit: int, offset: int
    ) -> list[WorkerRead]:
        rows = self._registry.list_workers(status=status, service=service, limit=limit, offset=offset)
        return [self._worker_read(w) for w in rows]

    # --- internals ----------------------------------------------------------------------

    def _register_instance(self, service_name, environment, version, instance_id, hostname, metadata, now):
        service = self._workflows.upsert_service(service_name, environment, version)
        return self._registry.upsert_instance(service, instance_id, hostname, metadata, now)

    def _recover_instance(self, instance: ServiceInstanceRow, now: datetime) -> None:
        if self._incidents.resolve_by_key(instance_stale_key(instance.id), now):
            instance.status = InstanceStatus.HEALTHY.value

    def _touch_worker(
        self, worker_id: uuid.UUID, status: WorkerStatus | None, job: str | None, *, clear_job: bool
    ) -> WorkerRead | None:
        worker = self._registry.get_worker(worker_id)
        if worker is None:
            return None
        now = datetime.now(UTC)
        was_unhealthy = worker.status == WorkerStatus.UNHEALTHY.value
        worker.last_heartbeat_at = now
        worker.instance.last_heartbeat_at = now  # a live worker proves its process is alive
        if worker.instance.status == InstanceStatus.UNHEALTHY.value:
            worker.instance.status = InstanceStatus.HEALTHY.value
            self._incidents.resolve_by_key(instance_stale_key(worker.instance.id), now)
        if status is not None:
            worker.status = status.value
        elif was_unhealthy:
            worker.status = WorkerStatus.IDLE.value  # recovered without stating a status
        if clear_job or job is not None:
            worker.current_job_key = job
        if was_unhealthy and worker.status != WorkerStatus.UNHEALTHY.value:
            self._incidents.resolve_by_key(worker_stale_key(worker.id), now)
        self._session.commit()
        return self._worker_read(worker)

    def _service_read(self, service: ServiceRow, instances: list[ServiceInstanceRow]) -> ServiceRead:
        live = [i for i in instances if i.status != InstanceStatus.STOPPED.value]
        healthy = [i for i in live if i.status == InstanceStatus.HEALTHY.value]
        if not instances:
            status = "NO_INSTANCES"
        elif not live:
            status = "STOPPED"
        elif len(healthy) == len(live):
            status = "HEALTHY"
        elif healthy:
            status = "DEGRADED"
        else:
            status = "UNHEALTHY"
        return ServiceRead(
            id=service.id,
            name=service.name,
            version=service.version,
            environment=service.environment,
            status=status,
            instances_total=len(instances),
            instances_healthy=len(healthy),
            last_heartbeat_at=max((i.last_heartbeat_at for i in instances), default=None),
        )

    @staticmethod
    def _worker_read(worker: WorkerRow) -> WorkerRead:
        instance = worker.instance
        return WorkerRead(
            id=worker.id,
            worker_name=worker.worker_name,
            worker_type=worker.worker_type,
            service_name=instance.service.name,
            environment=instance.service.environment,
            instance_id=instance.instance_id,
            status=worker.status,
            current_job_id=worker.current_job_key,
            capacity=worker.capacity,
            last_heartbeat_at=worker.last_heartbeat_at,
            registered_at=worker.registered_at,
            heartbeat_age_s=_age(worker.last_heartbeat_at),
        )


def _instance_read(i: ServiceInstanceRow) -> InstanceRead:
    return InstanceRead(
        instance_id=i.instance_id,
        hostname=i.hostname,
        status=i.status,
        last_heartbeat_at=i.last_heartbeat_at,
        registered_at=i.registered_at,
        heartbeat_age_s=_age(i.last_heartbeat_at),
    )


def _age(moment: datetime) -> float:
    return max(0.0, (datetime.now(UTC) - moment).total_seconds())


__all__ = ["RegistryService", "instance_stale_key", "worker_stale_key"]
