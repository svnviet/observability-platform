from typing import Any

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.event_repository import EventRepository
from app.db.models import WorkflowEventRow
from app.db.workflow_repository import WorkflowRepository
from app.events.processor import EventProcessor
from app.schemas.enums import IngestOutcome
from app.schemas.events import SUPPORTED_EVENT_VERSIONS, EventBatchResult, EventIn, IngestResult

_MAX_ATTEMPTS = 3  # IntegrityError retries for concurrent first-sight creation of the same run/step


class EventIngestionService:
    """Validate, deduplicate, persist and apply events — one transaction per event."""

    def __init__(
        self,
        session: Session,
        events: EventRepository,
        workflows: WorkflowRepository,
        processor: EventProcessor,
    ) -> None:
        self._session = session
        self._events = events
        self._workflows = workflows
        self._processor = processor

    def ingest(self, raw: dict[str, Any]) -> IngestResult:
        try:
            event = EventIn.model_validate(raw)
        except ValidationError as exc:
            return self._reject(raw, _summarize(exc), _event_id_of(raw))
        if event.event_version not in SUPPORTED_EVENT_VERSIONS:
            return self._reject(raw, f"unsupported event_version {event.event_version}", event.event_id)

        for _ in range(_MAX_ATTEMPTS):
            if self._events.exists(event.event_id):
                return IngestResult(event_id=event.event_id, outcome=IngestOutcome.DUPLICATE)
            try:
                result = self._persist(event)
                self._session.commit()
                return result
            except IntegrityError:
                # Either the same event_id raced in (caught as DUPLICATE next loop) or two
                # events raced to create the same run/step; a retry sees the committed row.
                self._session.rollback()
        return IngestResult(
            event_id=event.event_id, outcome=IngestOutcome.REJECTED, detail="persistent write conflict"
        )

    def ingest_batch(self, raws: list[dict[str, Any]]) -> EventBatchResult:
        results = [self.ingest(raw) for raw in raws]
        count = lambda outcome: sum(1 for r in results if r.outcome is outcome)  # noqa: E731
        return EventBatchResult(
            results=results,
            accepted=count(IngestOutcome.ACCEPTED),
            duplicates=count(IngestOutcome.DUPLICATE),
            rejected=count(IngestOutcome.REJECTED),
        )

    def _persist(self, event: EventIn) -> IngestResult:
        run = self._workflows.get_or_create_run_locked(
            event.context.workflow_run_id, event.context.workflow_id
        )
        applied = self._processor.apply(event, run)
        self._events.add(
            WorkflowEventRow(
                event_id=event.event_id,
                workflow_run_id=run.id,
                workflow_step_id=applied.step.id if applied.step else None,
                attempt_id=applied.attempt.id if applied.attempt else None,
                event_type=event.event_type.value,
                event_version=event.event_version,
                occurred_at=event.occurred_at,
                source_service=event.source.service_name,
                payload=event.model_dump(mode="json"),
                disposition=applied.disposition.value,
                disposition_reason=applied.reason,
            )
        )
        return IngestResult(
            event_id=event.event_id,
            outcome=IngestOutcome.ACCEPTED,
            disposition=applied.disposition,
            detail=applied.reason,
        )

    def _reject(self, raw: Any, error: str, event_id: str | None) -> IngestResult:
        self._events.add_rejected(raw, error)
        self._session.commit()
        return IngestResult(event_id=event_id, outcome=IngestOutcome.REJECTED, detail=error)


def _event_id_of(raw: Any) -> str | None:
    value = raw.get("event_id") if isinstance(raw, dict) else None
    return value if isinstance(value, str) else None


def _summarize(exc: ValidationError) -> str:
    parts = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()[:5]]
    return "; ".join(parts)
