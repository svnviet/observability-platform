from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select

from app.db.event_repository import EventRepository
from app.db.incident_repository import IncidentRepository
from app.db.models import WorkflowEventRow, WorkflowRunRow, WorkflowStepRow
from app.db.session import get_database
from app.db.workflow_repository import WorkflowRepository
from app.events.ingestion import EventIngestionService
from app.events.processor import EventProcessor
from tests.factories import event

pytestmark = pytest.mark.skipif(
    get_database().engine.dialect.name != "postgresql",
    reason="needs row locking: set TEST_DATABASE_URL to a PostgreSQL database",
)


def ingest_in_own_session(raw):
    session = get_database().session()
    try:
        workflows = WorkflowRepository(session)
        service = EventIngestionService(
            session,
            EventRepository(session),
            workflows,
            EventProcessor(workflows, IncidentRepository(session)),
        )
        return service.ingest(raw)
    finally:
        session.close()


def run_concurrently(raws, workers=16):
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(ingest_in_own_session, raws))


def count(model):
    session = get_database().session()
    try:
        return session.scalar(select(func.count()).select_from(model))
    finally:
        session.close()


def test_same_event_delivered_concurrently_is_stored_once():
    raw = event("WORKFLOW_STARTED", event_id="evt-same")
    results = run_concurrently([raw] * 20)
    outcomes = [r.outcome.value for r in results]
    assert outcomes.count("ACCEPTED") == 1
    assert outcomes.count("DUPLICATE") == 19
    assert count(WorkflowEventRow) == 1


def test_concurrent_first_events_for_one_run_create_one_run_and_unique_steps():
    raws = [event("STEP_STARTED", t=i, step=f"s{i}") for i in range(30)]
    results = run_concurrently(raws)
    assert all(r.outcome.value == "ACCEPTED" for r in results)
    assert count(WorkflowRunRow) == 1
    assert count(WorkflowStepRow) == 30
    session = get_database().session()
    try:
        sequences = list(session.scalars(select(WorkflowStepRow.sequence_number)))
    finally:
        session.close()
    assert sorted(sequences) == list(range(1, 31))
