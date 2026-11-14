from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.db.incident_repository import IncidentRepository
from app.db.registry_repository import RegistryRepository
from app.registry.service import instance_stale_key, worker_stale_key
from app.schemas.enums import InstanceStatus, WorkerStatus


@dataclass
class RetentionResult:
    instances_stopped: int
    workers_stopped: int
    instances_purged: int
    workers_purged: int


class RegistryRetention:
    """Keeps the registry from filling up with dead entries.

    Two stages, each disabled by a 0 duration: an UNHEALTHY entry that stays silent for `lost_after_s`
    (a process killed without a clean shutdown) is presumed gone and becomes STOPPED, closing its
    incident; a STOPPED entry silent for `purge_after_s` is deleted.
    """

    def __init__(
        self,
        session: Session,
        registry: RegistryRepository,
        incidents: IncidentRepository,
        lost_after_s: float,
        purge_after_s: float,
    ) -> None:
        self._session = session
        self._registry = registry
        self._incidents = incidents
        self._lost_after = timedelta(seconds=lost_after_s)
        self._purge_after = timedelta(seconds=purge_after_s)

    def sweep(self, now: datetime) -> RetentionResult:
        instances = workers = 0
        if self._lost_after:
            for instance in self._registry.lost_instances(now - self._lost_after):
                instance.status = InstanceStatus.STOPPED.value
                self._incidents.resolve_by_key(instance_stale_key(instance.id), now)
                instances += 1
            for worker in self._registry.lost_workers(now - self._lost_after):
                worker.status = WorkerStatus.STOPPED.value
                self._incidents.resolve_by_key(worker_stale_key(worker.id), now)
                workers += 1
        purged = (0, 0)
        if self._purge_after:
            purged = self._registry.purge_stopped(now - self._purge_after)
        self._session.commit()
        return RetentionResult(instances, workers, *purged)
