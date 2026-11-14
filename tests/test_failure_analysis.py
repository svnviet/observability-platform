import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.db.models import JobRow
from app.db.session import get_database
from app.failures.classifier import ErrorClassifier
from tests.factories import event

JOB = {"service_name": "news-crawler", "external_job_id": "pipeline-1", "environment": "prod"}
PY_TRACE = (
    'Traceback (most recent call last):\n  File "C:\\app\\main.py", line 10, in run\n    fetch()\n'
    '  File "C:\\app\\db\\client.py", line 42, in connect\n    raise AutoReconnect\n'
)


@pytest.mark.parametrize(
    "error,category",
    [
        ({"type": "AutoReconnect", "message": "localhost:27017: connection forcibly closed (timeouts: 20000ms)"}, "DEPENDENCY"),
        ({"type": "ReadTimeout", "message": "read timed out"}, "TIMEOUT"),
        ({"message": "No space left on device"}, "RESOURCE"),
        ({"message": "HTTP 403 forbidden"}, "AUTH"),
        ({"message": "loop crashed; restarting in 60s"}, "CRASH"),
        ({"type": "KeyError", "message": "'title'"}, "CODE"),
        ({"message": "HTTP 429 from api"}, "RESOURCE"),
        ({"type": "Mystery", "message": "???"}, "UNKNOWN"),
        (None, "UNKNOWN"),
    ],
)
def test_error_categories(error, category):
    assert ErrorClassifier.classify(error)[0] == category


def test_location_is_the_innermost_frame():
    assert ErrorClassifier.location(PY_TRACE) == "app/db/client.py:42 in connect"
    node = "Error: x\n    at connect (/srv/app/db.js:7:11)\n    at main (/srv/app/index.js:2:3)"
    assert ErrorClassifier.location(node) == "srv/app/db.js:7 in connect"
    assert ErrorClassifier.location("no frames here") is None and ErrorClassifier.location(None) is None


def fail_job(client, name="pipeline-1", **error):
    client.post("/jobs", json={**JOB, "external_job_id": name, "status": "RUNNING"})
    return client.post("/jobs", json={**JOB, "external_job_id": name, "status": "FAILED", "error": error}).json()


def test_a_job_that_did_not_fail_says_so(client):
    job = client.post("/jobs", json={**JOB, "status": "RUNNING"}).json()
    a = client.get(f"/jobs/{job['id']}/failure").json()
    assert a["failed"] is False and a["root_cause"] is None
    assert client.get(f"/jobs/{uuid.uuid4()}/failure").status_code == 404


def test_failed_job_root_cause_category_and_location(client):
    job = fail_job(client, type="AutoReconnect", message="connection forcibly closed", stack_trace=PY_TRACE)
    a = client.get(f"/jobs/{job['id']}/failure").json()
    rc = a["root_cause"]
    assert a["failed"] and rc["service_name"] == "news-crawler"
    assert (rc["error_type"], rc["category"]) == ("AutoReconnect", "DEPENDENCY")
    assert rc["location"] == "app/db/client.py:42 in connect" and "forcibly closed" in rc["message"]
    assert "news-crawler" in a["summary"] and "AutoReconnect" in a["summary"]
    assert [p["what"] for p in a["precedents"]] == ["JOB_STARTED"]  # what happened before it failed


def test_occurrences_tell_a_repeat_from_a_first_time(client):
    first = fail_job(client, "j1", type="AutoReconnect", message="boom")
    assert client.get(f"/jobs/{first['id']}/failure").json()["occurrences"]["is_new"] is True
    second = fail_job(client, "j2", type="AutoReconnect", message="boom again")
    other = fail_job(client, "j3", type="KeyError", message="x")
    occ = client.get(f"/jobs/{second['id']}/failure").json()["occurrences"]
    assert (occ["count_7d"], occ["count_24h"], occ["is_new"]) == (2, 2, False)
    assert client.get(f"/jobs/{other['id']}/failure").json()["occurrences"]["is_new"] is True  # a different error


def test_an_old_failure_is_judged_by_its_own_week(client):
    old = fail_job(client, "old", type="AutoReconnect", message="x")
    session = get_database().session()
    try:
        row = session.get(JobRow, uuid.UUID(old["id"]))
        row.finished_at = datetime.now(UTC) - timedelta(days=30)
        session.commit()
    finally:
        session.close()
    recent = fail_job(client, "recent", type="AutoReconnect", message="x")
    assert client.get(f"/jobs/{old['id']}/failure").json()["occurrences"]["is_new"] is True
    assert client.get(f"/jobs/{recent['id']}/failure").json()["occurrences"]["is_new"] is True  # old one is outside 7 days


def test_run_failure_names_the_first_failed_step_and_its_service(client):
    for e in [
        event("WORKFLOW_STARTED", t=0),
        event("STEP_STARTED", t=1, step="collect", service="news-crawler", step_name="Collect", sequence_number=0),
        event("STEP_COMPLETED", t=2, step="collect", service="news-crawler"),
        event("STEP_STARTED", t=3, step="render", service="video-service", worker="w-9", step_name="Render", sequence_number=1),
        event("STEP_FAILED", t=4, step="render", service="video-service", worker="w-9",
              error={"type": "RenderError", "message": "ffmpeg exited with 1", "stack_trace": PY_TRACE}),
        event("STEP_QUEUED", t=4.5, step="upload", service="yt", step_name="Upload", sequence_number=2),
        event("WORKFLOW_FAILED", t=5, error={"type": "WorkflowError", "message": "step failed"}),
    ]:
        client.post("/events", json=e)
    [run] = client.get("/workflow-runs").json()["items"]
    a = client.get(f"/workflow-runs/{run['id']}/failure").json()
    rc = a["root_cause"]
    assert a["failed"] and a["kind"] == "workflow_run"
    assert (rc["service_name"], rc["step_name"], rc["worker"], rc["error_type"]) == ("video-service", "Render", "w-9", "RenderError")
    assert rc["source"] == "step_attempt" and rc["location"] == "app/db/client.py:42 in connect"
    assert any("Upload" in line for line in a["impact"])
    assert a["precedents"] and a["trace_id"] == "trace-1"
    assert [i["status"] for i in a["incidents"]] == ["OPEN"]  # the workflow-failed incident


def test_a_step_that_recovered_on_retry_is_not_the_cause(client):
    for e in [
        event("WORKFLOW_STARTED", t=0),
        event("STEP_STARTED", t=1, step="a", step_name="A", sequence_number=0),
        event("STEP_FAILED", t=2, step="a", will_retry=True, error={"type": "Flaky", "message": "once"}),
        event("STEP_STARTED", t=3, step="a", attempt=2),
        event("STEP_COMPLETED", t=4, step="a", attempt=2),
        event("STEP_STARTED", t=5, step="b", step_name="B", sequence_number=1, service="svc-b"),
        event("STEP_FAILED", t=6, step="b", service="svc-b", error={"type": "Real", "message": "this one"}),
        event("WORKFLOW_FAILED", t=7),
    ]:
        client.post("/events", json=e)
    [run] = client.get("/workflow-runs").json()["items"]
    rc = client.get(f"/workflow-runs/{run['id']}/failure").json()["root_cause"]
    assert (rc["step_name"], rc["error_type"]) == ("B", "Real")


def test_a_run_that_failed_without_a_failed_step_uses_the_run_error(client):
    client.post("/events", json=event("WORKFLOW_STARTED", t=0))
    client.post("/events", json=event("WORKFLOW_FAILED", t=1, error={"type": "Boom", "message": "no steps"}))
    [run] = client.get("/workflow-runs").json()["items"]
    a = client.get(f"/workflow-runs/{run['id']}/failure").json()
    assert a["root_cause"]["source"] == "workflow"
    assert (a["root_cause"]["error_type"], a["root_cause"]["message"]) == ("Boom", "no steps")
    assert "without a failed step" in a["impact"][0]


def test_completed_run_and_unknown_ids(client):
    client.post("/events", json=event("WORKFLOW_STARTED", t=0))
    client.post("/events", json=event("WORKFLOW_COMPLETED", t=1))
    [run] = client.get("/workflow-runs").json()["items"]
    assert client.get(f"/workflow-runs/{run['id']}/failure").json()["failed"] is False
    assert client.get(f"/workflow-runs/{uuid.uuid4()}/failure").status_code == 404


def test_failure_reads_are_open(anon_client, client):
    job = fail_job(client, type="X", message="y")
    assert anon_client.get(f"/jobs/{job['id']}/failure").status_code == 200
