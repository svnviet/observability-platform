import uuid
from datetime import datetime

from sqlalchemy import and_, delete, exists, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    IncidentRow,
    JobRow,
    ServiceRow,
    StepAttemptRow,
    WorkflowDefinitionRow,
    WorkflowEventRow,
    WorkflowRunRow,
    WorkflowStepRow,
)
from app.schemas.enums import AttemptStatus, StepStatus, WorkflowStatus


class WorkflowRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # --- write side (called inside the ingestion transaction) -------------------------

    def get_or_create_run_locked(self, run_key: str, workflow_id: str) -> WorkflowRunRow:
        """Return the run with a row lock held, so concurrent events for one run serialize."""
        stmt = select(WorkflowRunRow).where(WorkflowRunRow.run_key == run_key).with_for_update()
        run = self._session.scalar(stmt)
        if run is not None:
            return run
        try:
            with self._session.begin_nested():
                self._session.add(
                    WorkflowRunRow(
                        run_key=run_key, workflow_id=workflow_id, status=WorkflowStatus.CREATED.value
                    )
                )
        except IntegrityError:
            pass  # another transaction created it first
        run = self._session.scalars(stmt).one()
        # Jobs reported before this run existed are linked now.
        self._session.execute(
            update(JobRow)
            .where(JobRow.workflow_run_key == run_key, JobRow.workflow_run_id.is_(None))
            .values(workflow_run_id=run.id)
        )
        return run

    def upsert_definition(self, name: str, version: str) -> WorkflowDefinitionRow:
        stmt = select(WorkflowDefinitionRow).where(
            WorkflowDefinitionRow.name == name, WorkflowDefinitionRow.version == version
        )
        row = self._session.scalar(stmt)
        if row is not None:
            return row
        try:
            with self._session.begin_nested():
                self._session.add(WorkflowDefinitionRow(name=name, version=version))
        except IntegrityError:
            pass
        return self._session.scalars(stmt).one()

    def upsert_service(self, name: str, environment: str, version: str | None) -> ServiceRow:
        stmt = select(ServiceRow).where(ServiceRow.name == name, ServiceRow.environment == environment)
        row = self._session.scalar(stmt)
        if row is None:
            try:
                with self._session.begin_nested():
                    self._session.add(ServiceRow(name=name, environment=environment, version=version))
            except IntegrityError:
                pass
            row = self._session.scalars(stmt).one()
        if version and row.version != version:
            row.version = version
        return row

    def get_or_create_step(
        self, run: WorkflowRunRow, step_key: str, step_name: str, sequence_number: int | None
    ) -> WorkflowStepRow:
        stmt = select(WorkflowStepRow).where(
            WorkflowStepRow.workflow_run_id == run.id, WorkflowStepRow.step_key == step_key
        )
        step = self._session.scalar(stmt)
        if step is not None:
            return step
        if sequence_number is None:
            count = self._session.scalar(
                select(func.count())
                .select_from(WorkflowStepRow)
                .where(WorkflowStepRow.workflow_run_id == run.id)
            )
            sequence_number = (count or 0) + 1
        step = WorkflowStepRow(
            workflow_run_id=run.id,
            step_key=step_key,
            step_name=step_name,
            status=StepStatus.PENDING.value,
            latest_attempt_number=0,
            sequence_number=sequence_number,
        )
        self._session.add(step)
        self._session.flush()
        return step

    def find_step_by_key(self, run: WorkflowRunRow, step_key: str) -> WorkflowStepRow | None:
        return self._session.scalar(
            select(WorkflowStepRow).where(
                WorkflowStepRow.workflow_run_id == run.id, WorkflowStepRow.step_key == step_key
            )
        )

    def get_or_create_attempt(self, step: WorkflowStepRow, attempt_number: int) -> StepAttemptRow:
        stmt = select(StepAttemptRow).where(
            StepAttemptRow.workflow_step_id == step.id, StepAttemptRow.attempt_number == attempt_number
        )
        attempt = self._session.scalar(stmt)
        if attempt is not None:
            return attempt
        attempt = StepAttemptRow(
            workflow_step_id=step.id,
            attempt_number=attempt_number,
            status=AttemptStatus.RUNNING.value,
        )
        self._session.add(attempt)
        self._session.flush()
        return attempt

    def find_run_by_key(self, run_key: str) -> WorkflowRunRow | None:
        return self._session.scalar(select(WorkflowRunRow).where(WorkflowRunRow.run_key == run_key))

    def list_definitions(self, limit: int, offset: int) -> list[WorkflowDefinitionRow]:
        return list(
            self._session.scalars(
                select(WorkflowDefinitionRow)
                .order_by(WorkflowDefinitionRow.name, WorkflowDefinitionRow.version)
                .limit(limit)
                .offset(offset)
            )
        )

    def reset_projection(self, run: WorkflowRunRow) -> None:
        """Drop derived step/attempt rows and clear run state ahead of a replay."""
        step_ids = select(WorkflowStepRow.id).where(WorkflowStepRow.workflow_run_id == run.id)
        for attempt in self._session.scalars(
            select(StepAttemptRow).where(StepAttemptRow.workflow_step_id.in_(step_ids))
        ):
            self._session.delete(attempt)
        for step in self._session.scalars(
            select(WorkflowStepRow).where(WorkflowStepRow.workflow_run_id == run.id)
        ):
            self._session.delete(step)
        run.status = WorkflowStatus.CREATED.value
        run.started_at = run.finished_at = run.duration_ms = run.last_event_at = None
        run.error_details = None
        run.input_metadata = {}
        run.output_metadata = {}
        self._session.flush()

    # --- read side --------------------------------------------------------------------

    def delete_run(self, run: WorkflowRunRow) -> int:
        """Delete a run with its steps, attempts and event log. Returns how many events went with it.

        Jobs and incidents stay and only lose the link to the run.
        """
        step_ids = select(WorkflowStepRow.id).where(WorkflowStepRow.workflow_run_id == run.id)
        events = self._session.execute(
            delete(WorkflowEventRow).where(WorkflowEventRow.workflow_run_id == run.id)
        ).rowcount
        self._session.execute(delete(StepAttemptRow).where(StepAttemptRow.workflow_step_id.in_(step_ids)))
        self._session.execute(delete(WorkflowStepRow).where(WorkflowStepRow.workflow_run_id == run.id))
        self._session.execute(update(JobRow).where(JobRow.workflow_run_id == run.id).values(workflow_run_id=None))
        self._session.execute(
            update(IncidentRow).where(IncidentRow.workflow_run_id == run.id).values(workflow_run_id=None)
        )
        self._session.execute(delete(WorkflowRunRow).where(WorkflowRunRow.id == run.id))
        return events

    def get_run(self, run_id: uuid.UUID) -> WorkflowRunRow | None:
        return self._session.get(WorkflowRunRow, run_id)

    def get_run_with_steps(self, run_id: uuid.UUID) -> WorkflowRunRow | None:
        stmt = (
            select(WorkflowRunRow)
            .where(WorkflowRunRow.id == run_id)
            .options(
                selectinload(WorkflowRunRow.definition),
                selectinload(WorkflowRunRow.steps).selectinload(WorkflowStepRow.attempts),
                selectinload(WorkflowRunRow.steps).selectinload(WorkflowStepRow.service),
            )
        )
        return self._session.scalar(stmt)

    def search_runs(
        self,
        *,
        workflow_id: str | None,
        run_key: str | None,
        status: WorkflowStatus | None,
        service: str | None,
        started_after: datetime | None,
        started_before: datetime | None,
        limit: int,
        offset: int,
    ) -> tuple[list[WorkflowRunRow], int]:
        conditions = []
        if workflow_id:
            conditions.append(WorkflowRunRow.workflow_id == workflow_id)
        if run_key:
            conditions.append(WorkflowRunRow.run_key == run_key)
        if status:
            conditions.append(WorkflowRunRow.status == status.value)
        if started_after:
            conditions.append(WorkflowRunRow.started_at >= started_after)
        if started_before:
            conditions.append(WorkflowRunRow.started_at < started_before)
        if service:
            conditions.append(
                exists().where(
                    and_(
                        WorkflowStepRow.workflow_run_id == WorkflowRunRow.id,
                        WorkflowStepRow.service_id == ServiceRow.id,
                        ServiceRow.name == service,
                    )
                )
            )
        total = self._session.scalar(select(func.count()).select_from(WorkflowRunRow).where(*conditions))
        rows = self._session.scalars(
            select(WorkflowRunRow)
            .where(*conditions)
            .options(selectinload(WorkflowRunRow.definition))
            .order_by(WorkflowRunRow.created_at.desc(), WorkflowRunRow.id)
            .limit(limit)
            .offset(offset)
        ).all()
        return list(rows), total or 0
