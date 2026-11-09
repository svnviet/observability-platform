from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    JobRow,
    ServiceRow,
    StepAttemptRow,
    WorkflowDefinitionRow,
    WorkflowRunRow,
    WorkflowStepRow,
)
from app.schemas.enums import AttemptStatus


class MonitoringRepository:
    """Read-only aggregates for the monitoring endpoints."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def count(self, model, *conditions) -> int:
        return self._session.scalar(select(func.count()).select_from(model).where(*conditions)) or 0

    def group_count(self, column, *conditions) -> dict[str, int]:
        rows = self._session.execute(select(column, func.count()).where(*conditions).group_by(column)).all()
        return {key: n for key, n in rows}

    def job_stats(self) -> list[tuple[str, str, int, datetime | None]]:
        """(service name, job status, count, oldest created_at) per service and status."""
        rows = self._session.execute(
            select(ServiceRow.name, JobRow.status, func.count(), func.min(JobRow.created_at))
            .join(ServiceRow, JobRow.service_id == ServiceRow.id)
            .group_by(ServiceRow.name, JobRow.status)
        ).all()
        return [(name, status, n, oldest) for name, status, n, oldest in rows]

    def failed_attempts(self, since: datetime, limit: int):
        return self._session.execute(
            select(
                StepAttemptRow.error_details,
                StepAttemptRow.finished_at,
                ServiceRow.name,
                WorkflowDefinitionRow.name,
                WorkflowRunRow.id,
            )
            .join(WorkflowStepRow, StepAttemptRow.workflow_step_id == WorkflowStepRow.id)
            .join(WorkflowRunRow, WorkflowStepRow.workflow_run_id == WorkflowRunRow.id)
            .outerjoin(ServiceRow, WorkflowStepRow.service_id == ServiceRow.id)
            .outerjoin(
                WorkflowDefinitionRow, WorkflowRunRow.workflow_definition_id == WorkflowDefinitionRow.id
            )
            .where(StepAttemptRow.status == AttemptStatus.FAILED.value, StepAttemptRow.finished_at >= since)
            .order_by(StepAttemptRow.finished_at.desc())
            .limit(limit)
        ).all()

    def completed_durations(self, since: datetime, limit: int) -> list[int]:
        return list(
            self._session.scalars(
                select(WorkflowRunRow.duration_ms)
                .where(
                    WorkflowRunRow.status == "COMPLETED",
                    WorkflowRunRow.duration_ms.is_not(None),
                    WorkflowRunRow.created_at >= since,
                )
                .order_by(WorkflowRunRow.created_at.desc())
                .limit(limit)
            )
        )

    def retries_since(self, since: datetime) -> int:
        """Attempts numbered above 1: every one of them is a retry of an earlier attempt."""
        return self.count(
            StepAttemptRow,
            StepAttemptRow.attempt_number > 1,
            StepAttemptRow.id.in_(
                select(StepAttemptRow.id)
                .join(WorkflowStepRow, StepAttemptRow.workflow_step_id == WorkflowStepRow.id)
                .join(WorkflowRunRow, WorkflowStepRow.workflow_run_id == WorkflowRunRow.id)
                .where(WorkflowRunRow.created_at >= since)
            ),
        )

    def attempts_since(self, since: datetime) -> int:
        return self.count(
            StepAttemptRow,
            StepAttemptRow.workflow_step_id.in_(
                select(WorkflowStepRow.id)
                .join(WorkflowRunRow, WorkflowStepRow.workflow_run_id == WorkflowRunRow.id)
                .where(WorkflowRunRow.created_at >= since)
            ),
        )
