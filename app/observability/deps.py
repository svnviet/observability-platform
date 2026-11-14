from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.observability_repository import ObservabilityRepository
from app.db.session import get_session
from app.observability.service import ObservabilityService


def get_observability_service(session: Session = Depends(get_session)) -> ObservabilityService:
    return ObservabilityService(ObservabilityRepository(session))
