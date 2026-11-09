from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.event_repository import EventRepository
from app.db.session import get_session
from app.db.workflow_repository import WorkflowRepository
from app.workflows.catalog import WorkflowCatalogService
from app.workflows.service import WorkflowQueryService


def get_query_service(session: Session = Depends(get_session)) -> WorkflowQueryService:
    return WorkflowQueryService(WorkflowRepository(session), EventRepository(session))


def get_catalog_service(session: Session = Depends(get_session)) -> WorkflowCatalogService:
    return WorkflowCatalogService(session, WorkflowRepository(session))
