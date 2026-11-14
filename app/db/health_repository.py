import uuid
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import HealthCheckRow, ServiceInstanceRow
from app.schemas.enums import InstanceStatus


class HealthRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def targets(self) -> list[ServiceInstanceRow]:
        """Instances to probe: they have a health_url and have not reported a clean stop."""
        rows = self._session.scalars(
            select(ServiceInstanceRow)
            .where(ServiceInstanceRow.status != InstanceStatus.STOPPED.value)
            .options(selectinload(ServiceInstanceRow.service))
        )
        return [r for r in rows if r.metadata_.get("health_url")]

    def add(self, instance_row_id: uuid.UUID, now: datetime, ok: bool, status_code, latency_ms, error, system):
        row = HealthCheckRow(
            service_instance_id=instance_row_id,
            checked_at=now,
            ok=ok,
            status_code=status_code,
            latency_ms=latency_ms,
            error=error,
            system=system or {},
        )
        self._session.add(row)
        self._session.flush()
        return row

    def recent(self, instance_row_id: uuid.UUID, n: int) -> list[HealthCheckRow]:
        """Newest first."""
        return list(
            self._session.scalars(
                select(HealthCheckRow)
                .where(HealthCheckRow.service_instance_id == instance_row_id)
                .order_by(HealthCheckRow.checked_at.desc())
                .limit(n)
            )
        )

    def since(self, since: datetime) -> list[HealthCheckRow]:
        """Oldest first, for the analytics windows."""
        return list(
            self._session.scalars(
                select(HealthCheckRow).where(HealthCheckRow.checked_at >= since).order_by(HealthCheckRow.checked_at)
            )
        )

    def instances_with_history_or_url(self, instance_row_ids: set[uuid.UUID]) -> list[ServiceInstanceRow]:
        rows = self._session.scalars(select(ServiceInstanceRow).options(selectinload(ServiceInstanceRow.service)))
        return [r for r in rows if r.id in instance_row_ids or r.metadata_.get("health_url")]

    def purge_before(self, cutoff: datetime) -> int:
        return self._session.execute(delete(HealthCheckRow).where(HealthCheckRow.checked_at < cutoff)).rowcount
