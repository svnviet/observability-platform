import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.core.config import default_page_size, max_page_size
from app.core.errors import Conflict, conflict_409, or_404
from app.schemas.enums import WorkflowStatus
from app.schemas.ops import WorkflowRunCreateIn
from app.schemas.registry import DeleteResult
from app.schemas.workflows import (
    EventRead,
    Page,
    StepRead,
    TimelineEntry,
    WorkflowRunDetail,
    WorkflowRunRead,
)
from app.workflows.catalog import WorkflowCatalogService
from app.workflows.deps import get_catalog_service, get_query_service
from app.workflows.service import WorkflowQueryService

router = APIRouter(prefix="/workflow-runs", tags=["workflow-runs"])


@router.post("", response_model=WorkflowRunRead)
def create_run(body: WorkflowRunCreateIn, svc: WorkflowCatalogService = Depends(get_catalog_service)):
    return svc.create_run(body)


@router.get("", response_model=Page[WorkflowRunRead])
def search_runs(
    workflow_id: str | None = None,
    run_key: str | None = None,
    status: WorkflowStatus | None = None,
    service: str | None = None,
    started_after: datetime | None = None,
    started_before: datetime | None = None,
    limit: int = Query(default_factory=default_page_size, ge=1, le=max_page_size()),
    offset: int = Query(0, ge=0),
    svc: WorkflowQueryService = Depends(get_query_service),
):
    return svc.search(
        workflow_id=workflow_id,
        run_key=run_key,
        status=status,
        service=service,
        started_after=started_after,
        started_before=started_before,
        limit=limit,
        offset=offset,
    )


@router.get("/{run_id}", response_model=WorkflowRunDetail)
def get_run(run_id: uuid.UUID, svc: WorkflowQueryService = Depends(get_query_service)):
    return or_404(svc.detail(run_id), "workflow run")


@router.delete("/{run_id}", response_model=DeleteResult)
def delete_run(
    run_id: uuid.UUID,
    force: bool = Query(False, description="Required to delete a run that has not finished"),
    svc: WorkflowCatalogService = Depends(get_catalog_service),
):
    """Remove a run with its steps and event log. Jobs and incidents keep their history."""
    try:
        return or_404(svc.delete_run(run_id, force=force), "workflow run")
    except Conflict as exc:
        raise conflict_409(exc) from exc


@router.get("/{run_id}/timeline", response_model=list[TimelineEntry])
def get_timeline(run_id: uuid.UUID, svc: WorkflowQueryService = Depends(get_query_service)):
    return or_404(svc.timeline(run_id), "workflow run")


@router.get("/{run_id}/steps", response_model=list[StepRead])
def get_steps(run_id: uuid.UUID, svc: WorkflowQueryService = Depends(get_query_service)):
    return or_404(svc.steps(run_id), "workflow run")


@router.get("/{run_id}/events", response_model=Page[EventRead])
def get_events(
    run_id: uuid.UUID,
    limit: int = Query(default_factory=default_page_size, ge=1, le=max_page_size()),
    offset: int = Query(0, ge=0),
    svc: WorkflowQueryService = Depends(get_query_service),
):
    return or_404(svc.events(run_id, limit, offset), "workflow run")
