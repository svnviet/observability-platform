import uuid

from tests.factories import event

JOB = {"service_name": "video-service", "external_job_id": "job-123", "environment": "prod"}


def post(client, status, **extra):
    return client.post("/jobs", json={**JOB, "status": status, **extra}).json()


def test_job_is_found_by_id_and_by_the_services_own_id(client):
    job = post(client, "QUEUED")
    assert client.get(f"/jobs/{job['id']}").json()["external_job_id"] == "job-123"
    assert client.get("/jobs", params={"external_job_id": "job-123"}).json()["total"] == 1
    assert client.get("/jobs", params={"external_job_id": "nope"}).json()["total"] == 0
    assert client.get(f"/jobs/{uuid.uuid4()}").status_code == 404


def test_every_status_change_is_recorded_with_its_predecessor(client):
    job = post(client, "QUEUED")
    post(client, "QUEUED")  # repeated update: no change, no event
    post(client, "RUNNING")
    post(client, "FAILED", error={"type": "RenderError", "message": "boom"})
    post(client, "RUNNING")  # refused: a finished job stays finished, so nothing is recorded

    events = client.get(f"/jobs/{job['id']}/events").json()
    assert [(e["event_type"], e["previous_status"], e["current_status"]) for e in events] == [
        ("JOB_QUEUED", None, "QUEUED"),
        ("JOB_STARTED", "QUEUED", "RUNNING"),
        ("JOB_FAILED", "RUNNING", "FAILED"),
    ]
    assert events[2]["detail"]["error"]["type"] == "RenderError"
    assert client.get(f"/jobs/{uuid.uuid4()}/events").status_code == 404


def test_a_job_first_seen_running_has_one_event_and_a_timeline(client):
    job = post(client, "RUNNING")
    post(client, "COMPLETED")
    timeline = client.get(f"/jobs/{job['id']}/timeline").json()
    assert [e["event_type"] for e in timeline["events"]] == ["JOB_STARTED", "JOB_COMPLETED"]
    assert timeline["job"]["status"] == "COMPLETED"
    assert timeline["running_s"] >= 0 and timeline["total_s"] >= timeline["running_s"]


def test_the_worker_that_ran_the_job_is_kept_on_its_events(client):
    reg = {"service_name": "video-service", "instance_id": "i-1", "environment": "prod", "worker_name": "w-1"}
    worker = client.post("/workers/register", json=reg).json()
    post(client, "RUNNING", instance_id="i-1", worker_name="w-1")
    [job] = client.get("/jobs").json()["items"]
    [started] = client.get(f"/jobs/{job['id']}/events").json()
    assert started["worker_id"] == worker["id"]
    assert client.get(f"/jobs/{job['id']}/observability").json()["worker_name"] == "w-1"


def test_observability_links_trace_logs_and_metrics(client, monkeypatch):
    client.post("/events", json=event("WORKFLOW_STARTED", run="run-1", wf="wf-1"))
    job = post(client, "RUNNING", workflow_run_key="run-1")

    bare = client.get(f"/jobs/{job['id']}/observability").json()
    assert (bare["workflow_id"], bare["trace_id"]) == ("wf-1", "trace-1")  # the trace comes from its workflow run
    assert bare["trace"] == {"available": False, "url": None}
    assert bare["logs"]["available"] is False and bare["metrics"]["available"] is False

    monkeypatch.setenv("OBSKIT_PLATFORM_JAEGER_URL", "http://jaeger.local:16686")
    monkeypatch.setenv("OBSKIT_PLATFORM_LOGS_URL_TEMPLATE", "http://logs.local/q?trace={trace_id}&job={job_id}")
    monkeypatch.setenv("OBSKIT_PLATFORM_METRICS_URL_TEMPLATE", "http://perses.local/d?service={service}")
    linked = client.get(f"/jobs/{job['id']}/observability").json()
    assert linked["trace"] == {"available": True, "url": "http://jaeger.local:16686/trace/trace-1"}
    assert linked["logs"]["url"] == "http://logs.local/q?trace=trace-1&job=job-123"
    assert linked["metrics"]["url"] == "http://perses.local/d?service=video-service"


def test_a_trace_id_on_the_job_wins_and_a_template_missing_a_value_has_no_link(client, monkeypatch):
    monkeypatch.setenv("OBSKIT_PLATFORM_JAEGER_URL", "http://jaeger.local")
    monkeypatch.setenv("OBSKIT_PLATFORM_LOGS_URL_TEMPLATE", "http://logs.local/?wf={workflow_id}&t={trace_id}")
    with_trace = post(client, "RUNNING", trace_id="abc 123")  # no workflow run: {workflow_id} has no value
    seen = client.get(f"/jobs/{with_trace['id']}/observability").json()
    assert seen["trace_id"] == "abc 123" and seen["trace"]["url"] == "http://jaeger.local/trace/abc 123"
    assert seen["logs"] == {"available": False, "url": None}
    assert client.get(f"/jobs/{with_trace['id']}").json()["trace_id"] == "abc 123"


def test_the_trace_id_is_kept_when_a_later_update_has_none_and_is_not_stored_in_metadata(client):
    first = post(client, "RUNNING", trace_id="t-1", metadata={"kind": "render"})
    later = post(client, "COMPLETED")  # no trace_id this time
    assert later["id"] == first["id"] and later["trace_id"] == "t-1"
    assert "trace_id" not in later["metadata"] and later["metadata"] == {"kind": "render"}


def test_job_reads_are_open_and_writes_need_the_key(anon_client, client):
    job = post(client, "QUEUED")
    for path in ("", f"/{job['id']}", f"/{job['id']}/events", f"/{job['id']}/timeline", f"/{job['id']}/observability"):
        assert anon_client.get(f"/jobs{path}").status_code == 200


def test_purging_a_stopped_worker_keeps_the_job_history(client):
    from datetime import UTC, datetime, timedelta

    from app.db.incident_repository import IncidentRepository
    from app.db.registry_repository import RegistryRepository
    from app.db.session import get_database
    from app.registry.retention import RegistryRetention

    reg = {"service_name": "video-service", "instance_id": "i-1", "environment": "prod", "worker_name": "w-1"}
    client.post("/workers/register", json=reg)
    job = post(client, "RUNNING", instance_id="i-1", worker_name="w-1")
    sid = client.get("/services").json()[0]["id"]
    client.post(f"/services/{sid}/heartbeat", json={"instance_id": "i-1", "stopping": True})
    session = get_database().session()
    try:
        sweep = RegistryRetention(session, RegistryRepository(session), IncidentRepository(session), 3600, 7200)
        assert sweep.sweep(datetime.now(UTC) + timedelta(days=30)).workers_purged == 1
    finally:
        session.close()
    [started] = client.get(f"/jobs/{job['id']}/events").json()
    assert started["event_type"] == "JOB_STARTED" and started["worker_id"] is None
    assert client.get(f"/jobs/{job['id']}").status_code == 200
