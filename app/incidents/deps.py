from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.incident_repository import IncidentRepository
from app.db.session import get_session
from app.incidents.service import IncidentService


def get_incident_service(session: Session = Depends(get_session)) -> IncidentService:
    return IncidentService(session, IncidentRepository(session))
