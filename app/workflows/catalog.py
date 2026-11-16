import uuid

from sqlalchemy.orm import Session

from app.core.errors import Conflict
from app.db.models import WorkflowRunRow
from app.db.workflow_repository import WorkflowRepository
from app.events.state_machine import WORKFLOW_TERMINAL
from app.schemas.enums import WorkflowStatus
from app.schemas.ops import WorkflowDefinitionIn, WorkflowDefinitionRead, WorkflowRunCreateIn
from app.schemas.registry import DeleteResult
from app.schemas.workflows import WorkflowRunRead
from app.workflows.service import _run


class WorkflowCatalogService:
    """Workflow definitions and explicit run creation (runs are otherwise created by events)."""

    def __init__(self, session: Session, workflows: WorkflowRepository) -> None:
        self._session = session
        self._workflows = workflows

    def register_definition(self, body: WorkflowDefinitionIn) -> WorkflowDefinitionRead:
        row = self._workflows.upsert_definition(body.name, body.version)
        row.description = body.description if body.description is not None else row.description
        row.definition = body.definition or row.definition
        self._session.commit()
        return WorkflowDefinitionRead.model_validate(row, from_attributes=True)

    def list_definitions(self, limit: int, offset: int) -> list[WorkflowDefinitionRead]:
        return [
            WorkflowDefinitionRead.model_validate(r, from_attributes=True)
            for r in self._workflows.list_definitions(limit, offset)
        ]

    def create_run(self, body: WorkflowRunCreateIn) -> WorkflowRunRead:
        """Idempotent: an existing run_id is returned unchanged apart from missing metadata."""
        run_key = body.run_id or f"run-{uuid.uuid4().hex[:12]}"
        run: WorkflowRunRow = self._workflows.get_or_create_run_locked(run_key, body.workflow_id)
        if run.workflow_definition_id is None:
            run.workflow_definition_id = self._workflows.upsert_definition(
                body.workflow_name, body.workflow_version
            ).id
        run.correlation_id = run.correlation_id or body.correlation_id
        run.trace_id = run.trace_id or body.trace_id
        if body.input_metadata:
            run.input_metadata = {**run.input_metadata, **body.input_metadata}
        self._session.commit()
        return _run(self._workflows.get_run_with_steps(run.id))

    def delete_run(self, run_id: uuid.UUID, *, force: bool) -> DeleteResult | None:
        """Remove a run and its event log, e.g. a test run abandoned mid-way.

        A run that has not finished is refused unless `force`: it may still be running, and deleting it
        only hides it until its next event recreates it.
        """
        run = self._workflows.get_run(run_id)
        if run is None:
            return None
        if WorkflowStatus(run.status) not in WORKFLOW_TERMINAL and not force:
            raise Conflict(f"run is {run.status}; pass force=true to delete a run that has not finished")
        events = self._workflows.delete_run(run)
        self._session.commit()
        return DeleteResult(deleted="workflow_run", events=events)
