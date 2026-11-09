import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import RejectedEventRow, WorkflowEventRow


class EventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def exists(self, event_id: str) -> bool:
        return (
            self._session.scalar(select(WorkflowEventRow.id).where(WorkflowEventRow.event_id == event_id))
            is not None
        )

    def add(self, row: WorkflowEventRow) -> None:
        self._session.add(row)
        self._session.flush()

    def add_rejected(self, raw: Any, error: str) -> None:
        self._session.add(RejectedEventRow(raw=raw, error=error))
        self._session.flush()

    def get_by_event_id(self, event_id: str) -> WorkflowEventRow | None:
        return self._session.scalar(select(WorkflowEventRow).where(WorkflowEventRow.event_id == event_id))

    def list_for_run(self, run_id: uuid.UUID, limit: int, offset: int) -> tuple[list[WorkflowEventRow], int]:
        where = WorkflowEventRow.workflow_run_id == run_id
        total = self._session.scalar(select(func.count()).select_from(WorkflowEventRow).where(where))
        rows = self._session.scalars(
            select(WorkflowEventRow)
            .where(where)
            .order_by(WorkflowEventRow.occurred_at, WorkflowEventRow.received_at, WorkflowEventRow.id)
            .limit(limit)
            .offset(offset)
        ).all()
        return list(rows), total or 0

    def all_for_run_ordered(self, run_id: uuid.UUID) -> list[WorkflowEventRow]:
        return list(
            self._session.scalars(
                select(WorkflowEventRow)
                .where(WorkflowEventRow.workflow_run_id == run_id)
                .order_by(WorkflowEventRow.occurred_at, WorkflowEventRow.received_at, WorkflowEventRow.id)
            )
        )

    def list_rejected(self, limit: int, offset: int) -> tuple[list[RejectedEventRow], int]:
        total = self._session.scalar(select(func.count()).select_from(RejectedEventRow))
        rows = self._session.scalars(
            select(RejectedEventRow)
            .order_by(RejectedEventRow.received_at.desc(), RejectedEventRow.id)
            .limit(limit)
            .offset(offset)
        ).all()
        return list(rows), total or 0
