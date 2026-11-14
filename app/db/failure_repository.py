import uuid
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import IncidentRow, JobRow, StepAttemptRow, WorkflowStepRow
from app.schemas.enums import AttemptStatus, JobStatus


class FailureRepository:
    """Queries that look across failures, for the root-cause view."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def failed_jobs(
        self, service_id: uuid.UUID, since: datetime, until: datetime, limit: int = 2000
    ) -> list[JobRow]:
        return list(
            self._session.scalars(
                select(JobRow)
                .where(
                    JobRow.service_id == service_id,
                    JobRow.status == JobStatus.FAILED.value,
                    JobRow.finished_at >= since,
                    JobRow.finished_at <= until,
                )
                .order_by(JobRow.finished_at.desc())
                .limit(limit)
            )
        )

    def failed_attempts(
        self, since: datetime, until: datetime, limit: int = 2000
    ) -> list[tuple[StepAttemptRow, WorkflowStepRow]]:
        rows = self._session.execute(
            select(StepAttemptRow, WorkflowStepRow)
            .join(WorkflowStepRow, StepAttemptRow.workflow_step_id == WorkflowStepRow.id)
            .where(StepAttemptRow.status == AttemptStatus.FAILED.value,
                StepAttemptRow.finished_at >= since,
                StepAttemptRow.finished_at <= until,
            )
            .order_by(StepAttemptRow.finished_at.desc())
            .limit(limit)
        ).all()
        return [(a, s) for a, s in rows]

    def jobs_of_run(self, run_id: uuid.UUID) -> list[JobRow]:
        return list(self._session.scalars(select(JobRow).where(JobRow.workflow_run_id == run_id)))

    def incidents_around(
        self,
        *,
        at: datetime | None,
        run_id: uuid.UUID | None = None,
        worker_id: uuid.UUID | None = None,
        service_id: uuid.UUID | None = None,
        window: timedelta = timedelta(hours=1),
    ) -> list[IncidentRow]:
        """Incidents tied to this run or worker, or on the same service within `window` of the failure."""
        conditions = []
        if run_id:
            conditions.append(IncidentRow.workflow_run_id == run_id)
        if worker_id:
            conditions.append(IncidentRow.worker_id == worker_id)
        if service_id and at:
            conditions.append(
                (IncidentRow.service_id == service_id)
                & (IncidentRow.detected_at >= at - window)
                & (IncidentRow.detected_at <= at + window)
            )
        if not conditions:
            return []
        stmt = select(IncidentRow).where(or_(*conditions))
        return list(self._session.scalars(stmt.order_by(IncidentRow.detected_at.desc()).limit(20)))
