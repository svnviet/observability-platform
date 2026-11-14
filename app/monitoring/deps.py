from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import health_fail_threshold
from app.db.health_repository import HealthRepository
from app.db.monitoring_repository import MonitoringRepository
from app.db.session import get_session
from app.monitoring.infra import InfraAnalytics
from app.monitoring.service import MonitoringService
from app.registry.deps import get_registry_service
from app.registry.service import RegistryService


def get_monitoring_service(
    session: Session = Depends(get_session), registry: RegistryService = Depends(get_registry_service)
) -> MonitoringService:
    return MonitoringService(MonitoringRepository(session), registry)


def get_infra_analytics(session: Session = Depends(get_session)) -> InfraAnalytics:
    return InfraAnalytics(HealthRepository(session), health_fail_threshold())
