import uuid

from tests.factories import event


def seed(client):
    for e in [
        event("WORKFLOW_STARTED", t=0, run="r1", wf="wf-a", workflow_name="pipeline"),
        event("STEP_STARTED", t=1, run="r1", wf="wf-a", step="render", service="video-generator"),
        event("STEP_COMPLETED", t=2, run="r1", wf="wf-a", step="render", service="video-generator"),
        event("STEP_QUEUED", t=2, run="r1", wf="wf-a", step="qa", service="video-qa"),
        event("WORKFLOW_COMPLETED", t=3, run="r1", wf="wf-a"),
        event("WORKFLOW_STARTED", t=0, run="r2", wf="wf-b"),
        event("WORKFLOW_FAILED", t=1, run="r2", wf="wf-b"),
        event("WORKFLOW_STARTED", t=0, run="r3", wf="wf-b"),
    ]:
        assert client.post("/events", json=e).json()["outcome"] == "ACCEPTED"


def search(client, **params):
    return client.get("/workflow-runs", params=params).json()


def test_search_filters_and_pagination(client):
    seed(client)
    assert search(client)["total"] == 3
    assert search(client, workflow_id="wf-b")["total"] == 2
    assert search(client, status="FAILED")["items"][0]["run_key"] == "r2"
    assert search(client, status="RUNNING")["items"][0]["run_key"] == "r3"
    assert search(client, service="video-qa")["items"][0]["run_key"] == "r1"
    assert search(client, service="nobody")["total"] == 0
    assert search(client, started_after="2026-11-09T12:00:00Z")["total"] == 3

    first = search(client, limit=2, offset=0)
    second = search(client, limit=2, offset=2)
    assert len(first["items"]) == 2 and len(second["items"]) == 1
    assert {r["run_key"] for r in first["items"] + second["items"]} == {"r1", "r2", "r3"}


def test_limit_is_bounded(client):
    assert client.get("/workflow-runs", params={"limit": 100000}).status_code == 422


def test_timeline_orders_attempts_and_includes_unstarted_steps(client):
    seed(client)
    rid = search(client, run_key="r1")["items"][0]["id"]
    timeline = client.get(f"/workflow-runs/{rid}/timeline").json()
    assert [(e["kind"], e["name"], e["status"]) for e in timeline] == [
        ("workflow", "pipeline", "COMPLETED"),
        ("step_attempt", "render", "COMPLETED"),
        ("step_attempt", "qa", "QUEUED"),
    ]
    assert timeline[1]["duration_ms"] == 1000
    assert timeline[1]["service_name"] == "video-generator"


def test_event_pagination_and_lookup(client):
    seed(client)
    rid = search(client, run_key="r1")["items"][0]["id"]
    page = client.get(f"/workflow-runs/{rid}/events", params={"limit": 2}).json()
    assert page["total"] == 5 and len(page["items"]) == 2
    eid = page["items"][0]["event_id"]
    assert client.get(f"/events/{eid}").json()["workflow_run_id"] == rid


def test_not_found(client):
    missing = uuid.uuid4()
    for suffix in ("", "/timeline", "/steps", "/events"):
        assert client.get(f"/workflow-runs/{missing}{suffix}").status_code == 404
    assert client.get("/events/does-not-exist").status_code == 404
