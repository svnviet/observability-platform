from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.db.incident_repository import IncidentRepository
from app.db.registry_repository import RegistryRepository
from app.registry.service import instance_stale_key, worker_stale_key
from app.schemas.enums import InstanceStatus, Severity, WorkerStatus


@dataclass
class ScanResult:
    instances_marked: int
    workers_marked: int


class HeartbeatMonitor:
    """Marks instances and workers that stopped heartbeating, and opens an incident for each.

    Recovery is handled on the next heartbeat (see RegistryService), which resolves the incident.
    """

    def __init__(
        self, session: Session, registry: RegistryRepository, incidents: IncidentRepository, timeout_s: float
    ) -> None:
        self._session = session
        self._registry = registry
        self._incidents = incidents
        self._timeout = timedelta(seconds=timeout_s)

    def scan(self, now: datetime) -> ScanResult:
        cutoff = now - self._timeout
        instances = self._registry.stale_instances(cutoff)
        for instance in instances:
            instance.status = InstanceStatus.UNHEALTHY.value
            self._incidents.open_incident(
                dedupe_key=instance_stale_key(instance.id),
                severity=Severity.HIGH,
                title=f"{instance.service.name} instance {instance.instance_id} stopped heartbeating",
                description=f"No heartbeat since {instance.last_heartbeat_at.isoformat()}.",
                service_id=instance.service_id,
                now=now,
            )
        workers = self._registry.stale_workers(cutoff)
        for worker in workers:
            worker.status = WorkerStatus.UNHEALTHY.value
            self._incidents.open_incident(
                dedupe_key=worker_stale_key(worker.id),
                severity=Severity.HIGH,
                title=f"Worker {worker.worker_name} stopped heartbeating",
                description=(
                    f"No heartbeat since {worker.last_heartbeat_at.isoformat()}."
                    + (f" It was running job {worker.current_job_key}." if worker.current_job_key else "")
                ),
                service_id=worker.instance.service_id,
                worker_id=worker.id,
                now=now,
            )
        self._session.commit()
        return ScanResult(len(instances), len(workers))
