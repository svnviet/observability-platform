from fastapi import APIRouter, Depends, Query

from app.core.config import default_page_size, max_page_size
from app.core.errors import or_404
from app.events.deps import get_ingestion_service, get_replay_service
from app.events.ingestion import EventIngestionService
from app.events.replay import EventReplayService
from app.schemas.events import EventBatchIn, EventBatchResult, IngestResult
from app.schemas.ops import RejectedEventRead
from app.schemas.workflows import EventRead, Page, ReplayRequest, ReplayResponse
from app.workflows.deps import get_query_service
from app.workflows.service import WorkflowQueryService

router = APIRouter(prefix="/events", tags=["events"])


@router.post("", response_model=IngestResult)
def publish_event(body: dict, svc: EventIngestionService = Depends(get_ingestion_service)):
    return svc.ingest(body)


@router.post("/batch", response_model=EventBatchResult)
def publish_batch(body: EventBatchIn, svc: EventIngestionService = Depends(get_ingestion_service)):
    return svc.ingest_batch(body.events)


@router.post("/replay", response_model=ReplayResponse)
def replay_events(body: ReplayRequest, svc: EventReplayService = Depends(get_replay_service)):
    return ReplayResponse(results=svc.replay_runs(body.workflow_run_ids))


@router.get("/rejected", response_model=Page[RejectedEventRead])
def list_rejected(
    limit: int = Query(default_factory=default_page_size, ge=1, le=max_page_size()),
    offset: int = Query(0, ge=0),
    svc: WorkflowQueryService = Depends(get_query_service),
):
    return svc.rejected(limit, offset)


@router.get("/{event_id}", response_model=EventRead)
def get_event(event_id: str, svc: WorkflowQueryService = Depends(get_query_service)):
    return or_404(svc.event(event_id), "event")
