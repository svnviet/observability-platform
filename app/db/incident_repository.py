import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import IncidentRow
from app.schemas.enums import IncidentStatus, Severity


class IncidentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def open_incident(
        self,
        *,
        dedupe_key: str,
        severity: Severity,
        title: str,
        description: str | None,
        service_id: uuid.UUID | None,
        workflow_run_id: uuid.UUID | None = None,
        worker_id: uuid.UUID | None = None,
        now: datetime,
    ) -> IncidentRow:
        """Idempotent per dedupe_key while an incident for it is still open."""
        existing = self._session.scalar(
            select(IncidentRow).where(
                IncidentRow.dedupe_key == dedupe_key, IncidentRow.status == IncidentStatus.OPEN.value
            )
        )
        if existing is not None:
            return existing
        row = IncidentRow(
            dedupe_key=dedupe_key,
            severity=severity.value,
            title=title,
            description=description,
            service_id=service_id,
            workflow_run_id=workflow_run_id,
            worker_id=worker_id,
            status=IncidentStatus.OPEN.value,
            detected_at=now,
        )
        self._session.add(row)
        self._session.flush()
        return row

    def resolve_by_key(self, dedupe_key: str, now: datetime) -> int:
        rows = self._session.scalars(
            select(IncidentRow).where(
                IncidentRow.dedupe_key == dedupe_key, IncidentRow.status == IncidentStatus.OPEN.value
            )
        ).all()
        for row in rows:
            row.status = IncidentStatus.RESOLVED.value
            row.resolved_at = now
        return len(rows)

    def get(self, incident_id: uuid.UUID) -> IncidentRow | None:
        return self._session.get(IncidentRow, incident_id)

    def list(
        self, *, status: IncidentStatus | None, severity: Severity | None, limit: int, offset: int
    ) -> tuple[list[IncidentRow], int]:
        conditions = []
        if status:
            conditions.append(IncidentRow.status == status.value)
        if severity:
            conditions.append(IncidentRow.severity == severity.value)
        total = self._session.scalar(select(func.count()).select_from(IncidentRow).where(*conditions))
        rows = self._session.scalars(
            select(IncidentRow)
            .where(*conditions)
            .order_by(IncidentRow.detected_at.desc(), IncidentRow.id)
            .limit(limit)
            .offset(offset)
        ).all()
        return list(rows), total or 0
