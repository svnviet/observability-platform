import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import JobRow, ServiceRow
from app.schemas.enums import JobStatus


class JobRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_or_create(self, service_id: uuid.UUID, external_job_id: str) -> JobRow:
        stmt = select(JobRow).where(
            JobRow.service_id == service_id, JobRow.external_job_id == external_job_id
        )
        row = self._session.scalar(stmt)
        if row is not None:
            return row
        try:
            with self._session.begin_nested():
                self._session.add(
                    JobRow(
                        service_id=service_id, external_job_id=external_job_id, status=JobStatus.QUEUED.value
                    )
                )
        except IntegrityError:
            pass
        return self._session.scalars(stmt).one()

    def list(
        self, *, status: JobStatus | None, service: str | None, limit: int, offset: int
    ) -> tuple[list[tuple[JobRow, str]], int]:
        conditions = []
        if status:
            conditions.append(JobRow.status == status.value)
        if service:
            conditions.append(ServiceRow.name == service)
        base = select(JobRow, ServiceRow.name).join(ServiceRow, JobRow.service_id == ServiceRow.id)
        total = self._session.scalar(
            select(func.count())
            .select_from(JobRow)
            .join(ServiceRow, JobRow.service_id == ServiceRow.id)
            .where(*conditions)
        )
        rows = self._session.execute(
            base.where(*conditions).order_by(JobRow.created_at.desc(), JobRow.id).limit(limit).offset(offset)
        ).all()
        return [(job, name) for job, name in rows], total or 0
