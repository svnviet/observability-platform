import uuid

from fastapi import APIRouter, Depends, Query

from app.core.config import default_page_size, max_page_size
from app.core.errors import or_404
from app.jobs.deps import get_job_service
from app.jobs.service import JobService
from app.schemas.enums import JobStatus
from app.schemas.ops import JobEventRead, JobObservability, JobRead, JobTimeline, JobUpsertIn
from app.schemas.workflows import Page

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobRead)
def upsert_job(body: JobUpsertIn, svc: JobService = Depends(get_job_service)):
    return svc.upsert(body)


@router.get("", response_model=Page[JobRead])
def list_jobs(
    status: JobStatus | None = None,
    service: str | None = None,
    external_job_id: str | None = Query(default=None, description="The job id the service uses, exact match"),
    limit: int = Query(default_factory=default_page_size, ge=1, le=max_page_size()),
    offset: int = Query(0, ge=0),
    svc: JobService = Depends(get_job_service),
):
    return svc.list(status=status, service=service, external_job_id=external_job_id, limit=limit, offset=offset)


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: uuid.UUID, svc: JobService = Depends(get_job_service)):
    return or_404(svc.get(job_id), "job")


@router.get("/{job_id}/events", response_model=list[JobEventRead])
def job_events(job_id: uuid.UUID, svc: JobService = Depends(get_job_service)):
    """Every status change of the job, oldest first."""
    return or_404(svc.events(job_id), "job")


@router.get("/{job_id}/timeline", response_model=JobTimeline)
def job_timeline(job_id: uuid.UUID, svc: JobService = Depends(get_job_service)):
    return or_404(svc.timeline(job_id), "job")


@router.get("/{job_id}/observability", response_model=JobObservability)
def job_observability(job_id: uuid.UUID, svc: JobService = Depends(get_job_service)):
    """Where to open this job's trace, logs and metrics. Links only; no telemetry data passes through here."""
    return or_404(svc.observability(job_id), "job")
