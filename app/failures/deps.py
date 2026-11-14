from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.event_repository import EventRepository
from app.db.failure_repository import FailureRepository
from app.db.job_repository import JobRepository
from app.db.session import get_session
from app.db.workflow_repository import WorkflowRepository
from app.failures.service import FailureAnalysisService


def get_failure_service(session: Session = Depends(get_session)) -> FailureAnalysisService:
    return FailureAnalysisService(
        JobRepository(session), WorkflowRepository(session), EventRepository(session), FailureRepository(session)
    )
