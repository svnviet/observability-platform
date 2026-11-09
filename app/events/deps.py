from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.event_repository import EventRepository
from app.db.incident_repository import IncidentRepository
from app.db.session import get_session
from app.db.workflow_repository import WorkflowRepository
from app.events.ingestion import EventIngestionService
from app.events.processor import EventProcessor
from app.events.replay import EventReplayService


def get_ingestion_service(session: Session = Depends(get_session)) -> EventIngestionService:
    workflows = WorkflowRepository(session)
    return EventIngestionService(
        session, EventRepository(session), workflows, EventProcessor(workflows, IncidentRepository(session))
    )


def get_replay_service(session: Session = Depends(get_session)) -> EventReplayService:
    workflows = WorkflowRepository(session)
    return EventReplayService(
        session, EventRepository(session), workflows, EventProcessor(workflows, IncidentRepository(session))
    )
