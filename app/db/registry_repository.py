import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    HealthCheckRow,
    IncidentRow,
    JobEventRow,
    JobRow,
    ServiceInstanceRow,
    ServiceRow,
    WorkerRow,
    WorkflowStepRow,
)
from app.schemas.enums import InstanceStatus, WorkerStatus


class RegistryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # --- instances ----------------------------------------------------------------------

    def upsert_instance(
        self,
        service: ServiceRow,
        instance_id: str,
        hostname: str | None,
        metadata: dict[str, Any],
        now: datetime,
    ) -> ServiceInstanceRow:
        stmt = select(ServiceInstanceRow).where(
            ServiceInstanceRow.service_id == service.id, ServiceInstanceRow.instance_id == instance_id
        )
        row = self._session.scalar(stmt)
        if row is None:
            try:
                with self._session.begin_nested():
                    self._session.add(
                        ServiceInstanceRow(
                            service_id=service.id,
                            instance_id=instance_id,
                            hostname=hostname,
                            status=InstanceStatus.HEALTHY.value,
                            last_heartbeat_at=now,
                            registered_at=now,
                            metadata_=metadata,
                        )
                    )
            except IntegrityError:
                pass
            return self._session.scalars(stmt).one()
        row.hostname = hostname or row.hostname
        row.metadata_ = {**row.metadata_, **metadata}
        row.status = InstanceStatus.HEALTHY.value
        row.last_heartbeat_at = now
        return row

    def find_instance(self, service_id: uuid.UUID, instance_id: str) -> ServiceInstanceRow | None:
        return self._session.scalar(
            select(ServiceInstanceRow).where(
                ServiceInstanceRow.service_id == service_id, ServiceInstanceRow.instance_id == instance_id
            )
        )

    def get_service(self, service_id: uuid.UUID) -> ServiceRow | None:
        return self._session.get(ServiceRow, service_id)

    def list_services(self) -> list[ServiceRow]:
        return list(
            self._session.scalars(select(ServiceRow).order_by(ServiceRow.name, ServiceRow.environment))
        )

    def instances_of(self, service_id: uuid.UUID) -> list[ServiceInstanceRow]:
        return list(
            self._session.scalars(
                select(ServiceInstanceRow)
                .where(ServiceInstanceRow.service_id == service_id)
                .order_by(ServiceInstanceRow.instance_id)
            )
        )

    def stale_instances(self, cutoff: datetime) -> list[ServiceInstanceRow]:
        return list(
            self._session.scalars(
                select(ServiceInstanceRow).where(
                    ServiceInstanceRow.status == InstanceStatus.HEALTHY.value,
                    ServiceInstanceRow.last_heartbeat_at < cutoff,
                )
            )
        )

    # --- workers ------------------------------------------------------------------------

    def upsert_worker(
        self,
        instance: ServiceInstanceRow,
        name: str,
        worker_type: str,
        capacity: int,
        metadata: dict[str, Any],
        now: datetime,
    ) -> WorkerRow:
        stmt = select(WorkerRow).where(
            WorkerRow.service_instance_id == instance.id, WorkerRow.worker_name == name
        )
        row = self._session.scalar(stmt)
        if row is None:
            try:
                with self._session.begin_nested():
                    self._session.add(
                        WorkerRow(
                            service_instance_id=instance.id,
                            worker_name=name,
                            worker_type=worker_type,
                            status=WorkerStatus.REGISTERED.value,
                            capacity=capacity,
                            last_heartbeat_at=now,
                            registered_at=now,
                            metadata_=metadata,
                        )
                    )
            except IntegrityError:
                pass
            return self._session.scalars(stmt).one()
        row.worker_type = worker_type
        row.capacity = capacity
        row.metadata_ = {**row.metadata_, **metadata}
        row.last_heartbeat_at = now
        if row.status in (WorkerStatus.STOPPED.value, WorkerStatus.UNHEALTHY.value):
            row.status = WorkerStatus.REGISTERED.value
        return row

    def get_worker(self, worker_id: uuid.UUID) -> WorkerRow | None:
        stmt = (
            select(WorkerRow)
            .where(WorkerRow.id == worker_id)
            .options(selectinload(WorkerRow.instance).selectinload(ServiceInstanceRow.service))
        )
        return self._session.scalar(stmt)

    def find_worker(self, instance: ServiceInstanceRow, name: str) -> WorkerRow | None:
        return self._session.scalar(
            select(WorkerRow).where(
                WorkerRow.service_instance_id == instance.id, WorkerRow.worker_name == name
            )
        )

    def list_workers(
        self, *, status: WorkerStatus | None, service: str | None, limit: int, offset: int
    ) -> list[WorkerRow]:
        stmt = (
            select(WorkerRow)
            .join(ServiceInstanceRow, WorkerRow.service_instance_id == ServiceInstanceRow.id)
            .join(ServiceRow, ServiceInstanceRow.service_id == ServiceRow.id)
            .options(selectinload(WorkerRow.instance).selectinload(ServiceInstanceRow.service))
            .order_by(ServiceRow.name, WorkerRow.worker_name, WorkerRow.id)
            .limit(limit)
            .offset(offset)
        )
        if status:
            stmt = stmt.where(WorkerRow.status == status.value)
        if service:
            stmt = stmt.where(ServiceRow.name == service)
        return list(self._session.scalars(stmt))

    def stale_workers(self, cutoff: datetime) -> list[WorkerRow]:
        live = (
            WorkerStatus.REGISTERED.value,
            WorkerStatus.STARTING.value,
            WorkerStatus.IDLE.value,
            WorkerStatus.BUSY.value,
            WorkerStatus.DRAINING.value,
        )
        return list(
            self._session.scalars(
                select(WorkerRow)
                .where(WorkerRow.status.in_(live), WorkerRow.last_heartbeat_at < cutoff)
                .options(selectinload(WorkerRow.instance))
            )
        )


    # --- retention ----------------------------------------------------------------------

    def lost_instances(self, cutoff: datetime) -> list[ServiceInstanceRow]:
        return list(
            self._session.scalars(
                select(ServiceInstanceRow).where(
                    ServiceInstanceRow.status == InstanceStatus.UNHEALTHY.value,
                    ServiceInstanceRow.last_heartbeat_at < cutoff,
                )
            )
        )

    def lost_workers(self, cutoff: datetime) -> list[WorkerRow]:
        return list(
            self._session.scalars(
                select(WorkerRow).where(
                    WorkerRow.status == WorkerStatus.UNHEALTHY.value, WorkerRow.last_heartbeat_at < cutoff
                )
            )
        )

    def purge_stopped(self, cutoff: datetime) -> tuple[int, int]:
        """Delete STOPPED workers and instances silent since before cutoff. Returns (instances, workers).

        Jobs and incidents keep their history; they only lose the link to a worker that no longer exists.
        """
        instance_ids = select(ServiceInstanceRow.id).where(
            ServiceInstanceRow.status == InstanceStatus.STOPPED.value,
            ServiceInstanceRow.last_heartbeat_at < cutoff,
        )
        worker_ids = list(
            self._session.scalars(
                select(WorkerRow.id).where(
                    (WorkerRow.service_instance_id.in_(instance_ids))
                    | (
                        (WorkerRow.status == WorkerStatus.STOPPED.value)
                        & (WorkerRow.last_heartbeat_at < cutoff)
                    )
                )
            )
        )
        self.delete_workers(worker_ids)
        self._session.execute(delete(HealthCheckRow).where(HealthCheckRow.service_instance_id.in_(instance_ids)))
        instances = self._session.execute(
            delete(ServiceInstanceRow).where(ServiceInstanceRow.id.in_(instance_ids))
        ).rowcount
        return instances, len(worker_ids)

    # --- explicit deletes ---------------------------------------------------------------

    def worker_ids_of(self, instance_row_ids: list[uuid.UUID]) -> list[uuid.UUID]:
        if not instance_row_ids:
            return []
        return list(
            self._session.scalars(select(WorkerRow.id).where(WorkerRow.service_instance_id.in_(instance_row_ids)))
        )

    def delete_workers(self, worker_ids: list[uuid.UUID]) -> int:
        """Jobs, job events and incidents keep their history; they only lose the link to the worker."""
        if not worker_ids:
            return 0
        self._session.execute(update(JobRow).where(JobRow.worker_id.in_(worker_ids)).values(worker_id=None))
        self._session.execute(
            update(JobEventRow).where(JobEventRow.worker_id.in_(worker_ids)).values(worker_id=None)
        )
        self._session.execute(
            update(IncidentRow).where(IncidentRow.worker_id.in_(worker_ids)).values(worker_id=None)
        )
        return self._session.execute(delete(WorkerRow).where(WorkerRow.id.in_(worker_ids))).rowcount

    def delete_instances(self, instance_row_ids: list[uuid.UUID]) -> tuple[int, int]:
        """Delete instances with their workers and probe history. Returns (instances, workers)."""
        if not instance_row_ids:
            return 0, 0
        workers = self.delete_workers(self.worker_ids_of(instance_row_ids))
        self._session.execute(
            delete(HealthCheckRow).where(HealthCheckRow.service_instance_id.in_(instance_row_ids))
        )
        instances = self._session.execute(
            delete(ServiceInstanceRow).where(ServiceInstanceRow.id.in_(instance_row_ids))
        ).rowcount
        return instances, workers

    def count_jobs(self, service_id: uuid.UUID) -> int:
        return self._session.scalar(select(func.count()).select_from(JobRow).where(JobRow.service_id == service_id)) or 0

    def delete_service(self, service: ServiceRow) -> int:
        """Delete a service that has no instances left. Its jobs go with it (returns how many);
        incidents and workflow steps stay and only lose the link to the service."""
        self._session.execute(delete(JobEventRow).where(JobEventRow.service_id == service.id))
        jobs = self._session.execute(delete(JobRow).where(JobRow.service_id == service.id)).rowcount
        self._session.execute(
            update(IncidentRow).where(IncidentRow.service_id == service.id).values(service_id=None)
        )
        self._session.execute(
            update(WorkflowStepRow).where(WorkflowStepRow.service_id == service.id).values(service_id=None)
        )
        self._session.delete(service)
        return jobs
