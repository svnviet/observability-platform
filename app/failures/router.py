import uuid

from fastapi import APIRouter, Depends

from app.core.errors import or_404
from app.failures.deps import get_failure_service
from app.failures.service import FailureAnalysisService
from app.schemas.failure import FailureAnalysis

router = APIRouter(tags=["failures"])


@router.get("/jobs/{job_id}/failure", response_model=FailureAnalysis)
def job_failure(job_id: uuid.UUID, svc: FailureAnalysisService = Depends(get_failure_service)):
    """Why a job failed: the error, where it came from, how often it happens and what surrounded it."""
    return or_404(svc.job(job_id), "job")


@router.get("/workflow-runs/{run_id}/failure", response_model=FailureAnalysis)
def run_failure(run_id: uuid.UUID, svc: FailureAnalysisService = Depends(get_failure_service)):
    """Why a workflow run failed: the first failed step and its service, worker and error."""
    return or_404(svc.run(run_id), "workflow run")
