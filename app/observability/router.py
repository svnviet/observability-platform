import uuid

from fastapi import APIRouter, Depends

from app.core.errors import or_404
from app.observability.deps import get_observability_service
from app.observability.service import ObservabilityService
from app.schemas.observability import EntityObservability

# One read-only route per entity, mounted under that entity's own path. Jobs keep their richer
# GET /jobs/{id}/observability.
services_router = APIRouter(prefix="/services", tags=["observability"])
workers_router = APIRouter(prefix="/workers", tags=["observability"])
runs_router = APIRouter(prefix="/workflow-runs", tags=["observability"])
incidents_router = APIRouter(prefix="/incidents", tags=["observability"])


@services_router.get("/{service_id}/observability", response_model=EntityObservability)
def service_observability(service_id: uuid.UUID, svc: ObservabilityService = Depends(get_observability_service)):
    return or_404(svc.for_service(service_id), "service")


@workers_router.get("/{worker_id}/observability", response_model=EntityObservability)
def worker_observability(worker_id: uuid.UUID, svc: ObservabilityService = Depends(get_observability_service)):
    return or_404(svc.for_worker(worker_id), "worker")


@runs_router.get("/{run_id}/observability", response_model=EntityObservability)
def run_observability(run_id: uuid.UUID, svc: ObservabilityService = Depends(get_observability_service)):
    """A run can span several traces (one per job/attempt); this returns the run's own trace, if it has one."""
    return or_404(svc.for_run(run_id), "workflow run")


@incidents_router.get("/{incident_id}/observability", response_model=EntityObservability)
def incident_observability(incident_id: uuid.UUID, svc: ObservabilityService = Depends(get_observability_service)):
    """Links scoped to the incident's service, worker or run, with a time window (at most 24 h) when the template uses it."""
    return or_404(svc.for_incident(incident_id), "incident")
