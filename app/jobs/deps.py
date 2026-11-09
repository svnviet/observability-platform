from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.job_repository import JobRepository
from app.db.registry_repository import RegistryRepository
from app.db.session import get_session
from app.db.workflow_repository import WorkflowRepository
from app.jobs.service import JobService


def get_job_service(session: Session = Depends(get_session)) -> JobService:
    return JobService(
        session, JobRepository(session), WorkflowRepository(session), RegistryRepository(session)
    )
