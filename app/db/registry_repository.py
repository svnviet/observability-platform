import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db.models import ServiceInstanceRow, ServiceRow, WorkerRow
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
