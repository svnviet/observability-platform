from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import heartbeat_timeout_s
from app.db.incident_repository import IncidentRepository
from app.db.registry_repository import RegistryRepository
from app.db.session import get_session
from app.db.workflow_repository import WorkflowRepository
from app.registry.heartbeat import HeartbeatMonitor
from app.registry.service import RegistryService


def get_registry_service(session: Session = Depends(get_session)) -> RegistryService:
    return RegistryService(
        session, RegistryRepository(session), WorkflowRepository(session), IncidentRepository(session)
    )


def get_heartbeat_monitor(session: Session = Depends(get_session)) -> HeartbeatMonitor:
    return HeartbeatMonitor(
        session, RegistryRepository(session), IncidentRepository(session), heartbeat_timeout_s()
    )
