from fastapi import APIRouter, Depends, Query

from app.core.config import default_page_size, max_page_size
from app.schemas.ops import WorkflowDefinitionIn, WorkflowDefinitionRead
from app.workflows.catalog import WorkflowCatalogService
from app.workflows.deps import get_catalog_service

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.post("", response_model=WorkflowDefinitionRead)
def register_definition(
    body: WorkflowDefinitionIn, svc: WorkflowCatalogService = Depends(get_catalog_service)
):
    return svc.register_definition(body)


@router.get("", response_model=list[WorkflowDefinitionRead])
def list_definitions(
    limit: int = Query(default_factory=default_page_size, ge=1, le=max_page_size()),
    offset: int = Query(0, ge=0),
    svc: WorkflowCatalogService = Depends(get_catalog_service),
):
    return svc.list_definitions(limit, offset)
