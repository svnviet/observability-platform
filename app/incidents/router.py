import uuid

from fastapi import APIRouter, Depends, Query

from app.core.config import default_page_size, max_page_size
from app.core.errors import or_404
from app.incidents.deps import get_incident_service
from app.incidents.service import IncidentService
from app.schemas.enums import IncidentStatus, Severity
from app.schemas.ops import IncidentRead
from app.schemas.workflows import Page

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("", response_model=Page[IncidentRead])
def list_incidents(
    status: IncidentStatus | None = None,
    severity: Severity | None = None,
    limit: int = Query(default_factory=default_page_size, ge=1, le=max_page_size()),
    offset: int = Query(0, ge=0),
    svc: IncidentService = Depends(get_incident_service),
):
    return svc.list(status=status, severity=severity, limit=limit, offset=offset)


@router.post("/{incident_id}/resolve", response_model=IncidentRead)
def resolve_incident(incident_id: uuid.UUID, svc: IncidentService = Depends(get_incident_service)):
    return or_404(svc.resolve(incident_id), "incident")
