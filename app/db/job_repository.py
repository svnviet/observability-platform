import uuid

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import JobEventRow, JobRow, ServiceRow, WorkerRow, WorkflowRunRow
from app.schemas.enums import JobStatus


class JobRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_or_create(self, service_id: uuid.UUID, external_job_id: str) -> tuple[JobRow, bool]:
        """Returns the job and whether this call created it."""
        stmt = select(JobRow).where(
            JobRow.service_id == service_id, JobRow.external_job_id == external_job_id
        )
        row = self._session.scalar(stmt)
        if row is not None:
            return row, False
        created = True
        try:
            with self._session.begin_nested():
                self._session.add(
                    JobRow(
                        service_id=service_id, external_job_id=external_job_id, status=JobStatus.QUEUED.value
                    )
                )
        except IntegrityError:
            created = False  # a concurrent request won the race
        return self._session.scalars(stmt).one(), created

    def get(self, job_id: uuid.UUID) -> tuple[JobRow, str] | None:
        row = self._session.execute(
            select(JobRow, ServiceRow.name)
            .join(ServiceRow, JobRow.service_id == ServiceRow.id)
            .where(JobRow.id == job_id)
        ).first()
        return None if row is None else (row[0], row[1])

    def add_event(
        self,
        job: JobRow,
        event_type: str,
        previous: str | None,
        current: str,
        now: datetime,
        detail: dict[str, Any],
    ) -> None:
        self._session.add(
            JobEventRow(
                job_id=job.id,
                event_type=event_type,
                previous_status=previous,
                current_status=current,
                service_id=job.service_id,
                worker_id=job.worker_id,
                occurred_at=now,
                detail=detail,
            )
        )

    def events(self, job_id: uuid.UUID) -> list[JobEventRow]:
        return list(
            self._session.scalars(
                select(JobEventRow).where(JobEventRow.job_id == job_id).order_by(JobEventRow.occurred_at, JobEventRow.id)
            )
        )

    def worker(self, worker_id: uuid.UUID | None) -> WorkerRow | None:
        return None if worker_id is None else self._session.get(WorkerRow, worker_id)

    def run(self, run_id: uuid.UUID | None) -> WorkflowRunRow | None:
        return None if run_id is None else self._session.get(WorkflowRunRow, run_id)

    def list(
        self,
        *,
        status: JobStatus | None,
        service: str | None,
        external_job_id: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[tuple[JobRow, str]], int]:
        conditions = []
        if status:
            conditions.append(JobRow.status == status.value)
        if service:
            conditions.append(ServiceRow.name == service)
        if external_job_id:
            conditions.append(JobRow.external_job_id == external_job_id)
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
