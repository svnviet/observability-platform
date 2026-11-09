from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.monitoring_repository import MonitoringRepository
from app.db.session import get_session
from app.monitoring.service import MonitoringService
from app.registry.deps import get_registry_service
from app.registry.service import RegistryService


def get_monitoring_service(
    session: Session = Depends(get_session), registry: RegistryService = Depends(get_registry_service)
) -> MonitoringService:
    return MonitoringService(MonitoringRepository(session), registry)
