from fastapi import APIRouter, Depends, Query

from app.core.config import default_page_size, max_page_size
from app.jobs.deps import get_job_service
from app.jobs.service import JobService
from app.schemas.enums import JobStatus
from app.schemas.ops import JobRead, JobUpsertIn
from app.schemas.workflows import Page

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobRead)
def upsert_job(body: JobUpsertIn, svc: JobService = Depends(get_job_service)):
    return svc.upsert(body)


@router.get("", response_model=Page[JobRead])
def list_jobs(
    status: JobStatus | None = None,
    service: str | None = None,
    limit: int = Query(default_factory=default_page_size, ge=1, le=max_page_size()),
    offset: int = Query(0, ge=0),
    svc: JobService = Depends(get_job_service),
):
    return svc.list(status=status, service=service, limit=limit, offset=offset)
