import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.incident_repository import IncidentRepository
from app.schemas.enums import IncidentStatus, Severity
from app.schemas.ops import IncidentRead
from app.schemas.workflows import Page


class IncidentService:
    def __init__(self, session: Session, incidents: IncidentRepository) -> None:
        self._session = session
        self._incidents = incidents

    def list(
        self, *, status: IncidentStatus | None, severity: Severity | None, limit: int, offset: int
    ) -> Page[IncidentRead]:
        rows, total = self._incidents.list(status=status, severity=severity, limit=limit, offset=offset)
        return Page(
            items=[IncidentRead.model_validate(r, from_attributes=True) for r in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    def resolve(self, incident_id: uuid.UUID) -> IncidentRead | None:
        row = self._incidents.get(incident_id)
        if row is None:
            return None
        if row.status != IncidentStatus.RESOLVED.value:
            row.status = IncidentStatus.RESOLVED.value
            row.resolved_at = datetime.now(UTC)
            self._session.commit()
        return IncidentRead.model_validate(row, from_attributes=True)
