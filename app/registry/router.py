import uuid

from fastapi import APIRouter, Depends, Query

from app.core.config import default_page_size, max_page_size
from app.core.errors import or_404
from app.registry.deps import get_registry_service
from app.registry.service import RegistryService
from app.schemas.enums import WorkerStatus
from app.schemas.registry import (
    HealthUrlIn,
    HealthUrlOut,
    HeartbeatIn,
    ServiceDetail,
    ServiceRead,
    ServiceRegisterIn,
    ServiceRegisterOut,
    WorkerHeartbeatIn,
    WorkerRead,
    WorkerRegisterIn,
    WorkerStatusIn,
)

services_router = APIRouter(prefix="/services", tags=["services"])
workers_router = APIRouter(prefix="/workers", tags=["workers"])


@services_router.post("/register", response_model=ServiceRegisterOut)
def register_service(body: ServiceRegisterIn, svc: RegistryService = Depends(get_registry_service)):
    return svc.register_service(body)


@services_router.get("", response_model=list[ServiceRead])
def list_services(svc: RegistryService = Depends(get_registry_service)):
    return svc.list_services()


@services_router.get("/{service_id}", response_model=ServiceDetail)
def get_service(service_id: uuid.UUID, svc: RegistryService = Depends(get_registry_service)):
    return or_404(svc.get_service(service_id), "service")


@services_router.post("/{service_id}/heartbeat", response_model=ServiceRegisterOut)
def service_heartbeat(
    service_id: uuid.UUID, body: HeartbeatIn, svc: RegistryService = Depends(get_registry_service)
):
    return or_404(svc.service_heartbeat(service_id, body), "service instance")


@services_router.put("/{service_id}/instances/{instance_id}/health-url", response_model=HealthUrlOut)
def set_health_url(
    service_id: uuid.UUID,
    instance_id: str,
    body: HealthUrlIn,
    svc: RegistryService = Depends(get_registry_service),
):
    """Tell the platform where to probe this instance (null stops probing). Same as metadata.health_url at register."""
    return or_404(svc.set_health_url(service_id, instance_id, body.health_url), "service instance")


@workers_router.post("/register", response_model=WorkerRead)
def register_worker(body: WorkerRegisterIn, svc: RegistryService = Depends(get_registry_service)):
    return svc.register_worker(body)


@workers_router.get("", response_model=list[WorkerRead])
def list_workers(
    status: WorkerStatus | None = None,
    service: str | None = None,
    limit: int = Query(default_factory=default_page_size, ge=1, le=max_page_size()),
    offset: int = Query(0, ge=0),
    svc: RegistryService = Depends(get_registry_service),
):
    return svc.list_workers(status=status, service=service, limit=limit, offset=offset)


@workers_router.get("/{worker_id}", response_model=WorkerRead)
def get_worker(worker_id: uuid.UUID, svc: RegistryService = Depends(get_registry_service)):
    return or_404(svc.get_worker(worker_id), "worker")


@workers_router.post("/{worker_id}/heartbeat", response_model=WorkerRead)
def worker_heartbeat(
    worker_id: uuid.UUID, body: WorkerHeartbeatIn, svc: RegistryService = Depends(get_registry_service)
):
    return or_404(svc.worker_heartbeat(worker_id, body), "worker")


@workers_router.post("/{worker_id}/status", response_model=WorkerRead)
def set_worker_status(
    worker_id: uuid.UUID, body: WorkerStatusIn, svc: RegistryService = Depends(get_registry_service)
):
    return or_404(svc.set_worker_status(worker_id, body), "worker")
