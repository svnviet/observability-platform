import uuid

from fastapi import APIRouter, Depends, Query

from app.core.config import default_page_size, max_page_size
from app.core.errors import Conflict, conflict_409, or_404
from app.registry.deps import get_registry_service
from app.registry.service import RegistryService
from app.schemas.enums import WorkerStatus
from app.schemas.registry import (
    DeleteResult,
    HealthUrlIn,
    HealthUrlOut,
    HeartbeatIn,
    InstanceRead,
    InstanceUpdateIn,
    ServiceDetail,
    ServiceRead,
    ServiceRegisterIn,
    ServiceRegisterOut,
    ServiceUpdateIn,
    WorkerHeartbeatIn,
    WorkerRead,
    WorkerRegisterIn,
    WorkerStatusIn,
    WorkerUpdateIn,
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


@services_router.patch("/{service_id}", response_model=ServiceDetail)
def update_service(
    service_id: uuid.UUID, body: ServiceUpdateIn, svc: RegistryService = Depends(get_registry_service)
):
    """Edit a service's version and metadata. Name and environment are its identity and do not change."""
    return or_404(svc.update_service(service_id, body), "service")


@services_router.delete("/{service_id}", response_model=DeleteResult)
def delete_service(
    service_id: uuid.UUID,
    delete_jobs: bool = Query(False, description="Also delete the service's jobs; without it a service with jobs is refused"),
    svc: RegistryService = Depends(get_registry_service),
):
    """Remove a service whose instances are all stopped. 409 while one is alive, or while it has jobs."""
    try:
        return or_404(svc.delete_service(service_id, delete_jobs=delete_jobs), "service")
    except Conflict as exc:
        raise conflict_409(exc) from exc


@services_router.patch("/{service_id}/instances/{instance_id}", response_model=InstanceRead)
def update_instance(
    service_id: uuid.UUID,
    instance_id: str,
    body: InstanceUpdateIn,
    svc: RegistryService = Depends(get_registry_service),
):
    return or_404(svc.update_instance(service_id, instance_id, body), "service instance")


@services_router.delete("/{service_id}/instances/{instance_id}", response_model=DeleteResult)
def delete_instance(
    service_id: uuid.UUID, instance_id: str, svc: RegistryService = Depends(get_registry_service)
):
    """Remove one instance and its workers. Jobs and incidents keep their history."""
    return or_404(svc.delete_instance(service_id, instance_id), "service instance")


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


@workers_router.patch("/{worker_id}", response_model=WorkerRead)
def update_worker(
    worker_id: uuid.UUID, body: WorkerUpdateIn, svc: RegistryService = Depends(get_registry_service)
):
    return or_404(svc.update_worker(worker_id, body), "worker")


@workers_router.delete("/{worker_id}", response_model=DeleteResult)
def delete_worker(worker_id: uuid.UUID, svc: RegistryService = Depends(get_registry_service)):
    """Remove one worker. Its jobs stay and only lose the link to it."""
    return or_404(svc.delete_worker(worker_id), "worker")


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
