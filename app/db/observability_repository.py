import uuid

from sqlalchemy.orm import Session

from app.db.models import (
    IncidentRow,
    ServiceInstanceRow,
    ServiceRow,
    WorkerRow,
    WorkflowRunRow,
)


class ObservabilityRepository:
    """Read-only lookups of the entities that observability links are built from."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def service(self, service_id: uuid.UUID | None) -> ServiceRow | None:
        return None if service_id is None else self._session.get(ServiceRow, service_id)

    def worker(self, worker_id: uuid.UUID | None) -> WorkerRow | None:
        return None if worker_id is None else self._session.get(WorkerRow, worker_id)

    def instance(self, instance_pk: uuid.UUID) -> ServiceInstanceRow | None:
        return self._session.get(ServiceInstanceRow, instance_pk)

    def run(self, run_id: uuid.UUID | None) -> WorkflowRunRow | None:
        return None if run_id is None else self._session.get(WorkflowRunRow, run_id)

    def incident(self, incident_id: uuid.UUID) -> IncidentRow | None:
        return self._session.get(IncidentRow, incident_id)
