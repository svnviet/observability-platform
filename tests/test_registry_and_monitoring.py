from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from app.db.models import ServiceInstanceRow, WorkerRow
from app.db.session import get_database
from tests.factories import event

INSTANCE = {"service_name": "video-generator", "instance_id": "vg-01", "environment": "prod",
            "service_version": "1.2.0", "hostname": "host-1"}  # fmt: skip
WORKER = {**INSTANCE, "worker_name": "render-1", "worker_type": "render", "capacity": 2}


def age_heartbeats(seconds: int):
    old = datetime.now(UTC) - timedelta(seconds=seconds)
    session = get_database().session()
    try:
        session.execute(update(WorkerRow).values(last_heartbeat_at=old))
        session.execute(update(ServiceInstanceRow).values(last_heartbeat_at=old))
        session.commit()
    finally:
        session.close()


def test_service_registration_and_listing(client):
    reg = client.post("/services/register", json=INSTANCE).json()
    again = client.post("/services/register", json={**INSTANCE, "instance_id": "vg-02"}).json()
    assert reg["service_id"] == again["service_id"]  # two instances, one service

    [svc] = client.get("/services").json()
    assert (svc["name"], svc["version"], svc["environment"]) == ("video-generator", "1.2.0", "prod")
    assert (svc["instances_total"], svc["instances_healthy"], svc["status"]) == (2, 2, "HEALTHY")
    detail = client.get(f"/services/{reg['service_id']}").json()
    assert {i["instance_id"] for i in detail["instances"]} == {"vg-01", "vg-02"}


def test_service_heartbeat_and_graceful_stop(client):
    sid = client.post("/services/register", json=INSTANCE).json()["service_id"]
    assert client.post(f"/services/{sid}/heartbeat", json={"instance_id": "vg-01"}).status_code == 200
    stopped = client.post(
        f"/services/{sid}/heartbeat", json={"instance_id": "vg-01", "stopping": True}
    ).json()
    assert stopped["status"] == "STOPPED"
    assert client.get("/services").json()[0]["status"] == "STOPPED"
    assert client.post(f"/services/{sid}/heartbeat", json={"instance_id": "ghost"}).status_code == 404


def test_worker_lifecycle_and_current_job(client):
    w = client.post("/workers/register", json=WORKER).json()
    assert (w["status"], w["service_name"], w["capacity"]) == ("REGISTERED", "video-generator", 2)
    wid = w["id"]
    busy = client.post(f"/workers/{wid}/heartbeat", json={"status": "BUSY", "current_job_id": "job-7"}).json()
    assert (busy["status"], busy["current_job_id"]) == ("BUSY", "job-7")
    idle = client.post(f"/workers/{wid}/status", json={"status": "IDLE"}).json()
    assert (idle["status"], idle["current_job_id"]) == ("IDLE", None)
    assert client.get("/workers", params={"status": "IDLE"}).json()[0]["id"] == wid
    assert client.get("/workers", params={"service": "nobody"}).json() == []
    assert client.get(f"/workers/{wid}").json()["worker_name"] == "render-1"


def test_reregistering_worker_is_idempotent(client):
    a = client.post("/workers/register", json=WORKER).json()
    b = client.post("/workers/register", json=WORKER).json()
    assert a["id"] == b["id"] and len(client.get("/workers").json()) == 1


def test_missed_heartbeat_marks_unhealthy_opens_incident_then_recovers(client):
    wid = client.post("/workers/register", json=WORKER).json()["id"]
    client.post(f"/workers/{wid}/heartbeat", json={"status": "BUSY", "current_job_id": "job-9"})
    age_heartbeats(120)

    scan = client.post("/monitoring/scan").json()
    assert scan == {"instances_marked": 1, "workers_marked": 1}
    assert client.post("/monitoring/scan").json() == {
        "instances_marked": 0,
        "workers_marked": 0,
    }  # idempotent
    assert client.get(f"/workers/{wid}").json()["status"] == "UNHEALTHY"
    assert client.get("/services").json()[0]["status"] == "UNHEALTHY"

    incidents = client.get("/incidents", params={"status": "OPEN"}).json()
    assert incidents["total"] == 2
    worker_incident = next(i for i in incidents["items"] if "Worker render-1" in i["title"])
    assert "job-9" in worker_incident["description"] and worker_incident["severity"] == "HIGH"

    recovered = client.post(f"/workers/{wid}/heartbeat", json={}).json()  # worker comes back
    assert recovered["status"] == "IDLE"
    assert client.get("/services").json()[0]["status"] == "HEALTHY"
    assert client.get("/incidents", params={"status": "OPEN"}).json()["total"] == 0
    assert client.get("/incidents", params={"status": "RESOLVED"}).json()["total"] == 2


def test_failed_workflow_opens_incident_and_can_be_resolved(client):
    client.post("/events", json=event("WORKFLOW_STARTED", workflow_name="news-video-pipeline"))
    client.post(
        "/events", json=event("WORKFLOW_FAILED", t=2, error={"type": "Boom", "message": "render died"})
    )
    page = client.get("/incidents", params={"status": "OPEN"}).json()
    [inc] = page["items"]
    assert inc["title"] == "Workflow news-video-pipeline failed" and inc["description"] == "render died"
    assert inc["workflow_run_id"] is not None
    resolved = client.post(f"/incidents/{inc['id']}/resolve").json()
    assert resolved["status"] == "RESOLVED" and resolved["resolved_at"]
    assert client.post(f"/incidents/{inc['id']}/resolve").json()["status"] == "RESOLVED"  # idempotent


def test_replay_closes_failure_incident_when_run_is_no_longer_failed(client):
    client.post("/events", json=event("WORKFLOW_STARTED", t=0))
    client.post("/events", json=event("WORKFLOW_FAILED", t=9, error={"type": "Late"}))  # arrives first
    client.post("/events", json=event("WORKFLOW_COMPLETED", t=5))  # happened first; quarantined on arrival
    rid = client.get("/workflow-runs").json()["items"][0]["id"]
    assert client.get(f"/workflow-runs/{rid}").json()["status"] == "FAILED"
    assert client.get("/incidents", params={"status": "OPEN"}).json()["total"] == 1

    client.post("/events/replay", json={"workflow_run_ids": [rid]})  # by occurrence, COMPLETED came first
    assert client.get(f"/workflow-runs/{rid}").json()["status"] == "COMPLETED"
    assert client.get("/incidents", params={"status": "OPEN"}).json()["total"] == 0


def test_jobs_upsert_and_terminal_state_is_final(client):
    client.post("/workflow-runs", json={"workflow_name": "p", "workflow_id": "wf-1", "run_id": "run-1"})
    job = {"service_name": "video-generator", "external_job_id": "job-1", "environment": "prod",
           "workflow_run_key": "run-1"}  # fmt: skip
    queued = client.post("/jobs", json={**job, "status": "QUEUED"}).json()
    running = client.post("/jobs", json={**job, "status": "RUNNING"}).json()
    done = client.post("/jobs", json={**job, "status": "COMPLETED"}).json()
    late = client.post("/jobs", json={**job, "status": "RUNNING"}).json()
    assert queued["id"] == running["id"] == done["id"]
    assert done["started_at"] and done["finished_at"] and done["workflow_run_id"]
    assert late["status"] == "COMPLETED"
    assert client.get("/jobs", params={"status": "COMPLETED"}).json()["total"] == 1


def test_job_reported_before_its_run_is_linked_when_the_run_appears(client):
    job = {"service_name": "video-generator", "external_job_id": "early", "status": "RUNNING",
           "environment": "prod", "workflow_run_key": "run-later"}  # fmt: skip
    assert client.post("/jobs", json=job).json()["workflow_run_id"] is None
    client.post("/events", json=event("WORKFLOW_STARTED", run="run-later", wf="wf-9"))
    [listed] = client.get("/jobs").json()["items"]
    run = client.get("/workflow-runs", params={"run_key": "run-later"}).json()["items"][0]
    assert listed["workflow_run_id"] == run["id"]


def test_workflow_definitions_and_explicit_run_creation(client):
    d = client.post("/workflows", json={"name": "p", "version": "2", "description": "pipeline",
                                         "definition": {"steps": ["a", "b"]}}).json()  # fmt: skip
    assert d["definition"] == {"steps": ["a", "b"]}
    assert client.get("/workflows").json()[0]["name"] == "p"
    run = client.post("/workflow-runs", json={"workflow_name": "p", "workflow_version": "2",
                                               "workflow_id": "wf-1", "run_id": "run-x"}).json()  # fmt: skip
    again = client.post("/workflow-runs", json={"workflow_name": "p", "workflow_version": "2",
                                                 "workflow_id": "wf-1", "run_id": "run-x"}).json()  # fmt: skip
    assert run["id"] == again["id"] and run["status"] == "CREATED" and run["workflow_name"] == "p"
    client.post("/events", json=event("WORKFLOW_STARTED", run="run-x", wf="wf-1"))
    assert client.get(f"/workflow-runs/{run['id']}").json()["status"] == "RUNNING"


def test_monitoring_overview_queues_errors_metrics(client):
    # same (name, environment) as the events below, so everything belongs to one service
    worker = {**WORKER, "environment": "unknown"}
    wid = client.post("/workers/register", json=worker).json()["id"]
    client.post(f"/workers/{wid}/heartbeat", json={"status": "BUSY"})
    job = {"service_name": "video-generator", "environment": "unknown"}
    client.post("/jobs", json={**job, "external_job_id": "j1", "status": "QUEUED"})
    client.post("/jobs", json={**job, "external_job_id": "j2", "status": "RUNNING"})
    for e in [
        event("WORKFLOW_STARTED", t=0, run="r1", wf="w1", workflow_name="pipeline"),
        event("STEP_STARTED", t=1, run="r1", wf="w1", step="render", attempt=1),
        event(
            "STEP_FAILED",
            t=2,
            run="r1",
            wf="w1",
            step="render",
            attempt=1,
            will_retry=True,
            error={"type": "TimeoutError", "message": "slow"},
        ),  # fmt: skip
        event("STEP_STARTED", t=3, run="r1", wf="w1", step="render", attempt=2),
        event("STEP_COMPLETED", t=4, run="r1", wf="w1", step="render", attempt=2),
        event("WORKFLOW_COMPLETED", t=5, run="r1", wf="w1"),
        event("WORKFLOW_STARTED", t=0, run="r2", wf="w2"),
        event("WORKFLOW_FAILED", t=1, run="r2", wf="w2", error={"type": "Boom"}),
        event("WORKFLOW_STARTED", t=0, run="r3", wf="w3"),
    ]:
        client.post("/events", json=e)
    client.post("/events", json={"event_id": "bad"})  # rejected

    o = client.get("/monitoring/overview").json()
    assert (o["services_total"], o["workers_active"], o["workers_unhealthy"]) == (1, 1, 0)
    assert (o["workflows_active"], o["workflows_completed"], o["workflows_failed"]) == (1, 1, 1)
    assert (o["jobs_running"], o["jobs_queued"], o["open_incidents"], o["rejected_events"]) == (1, 1, 1, 1)

    [q] = client.get("/monitoring/queues").json()
    assert (q["service_name"], q["queued"], q["running"]) == ("video-generator", 1, 1)
    assert q["oldest_queued_age_s"] is not None

    [g] = client.get("/monitoring/errors").json()
    assert (g["exception_type"], g["service_name"], g["workflow_name"], g["count"]) == (
        "TimeoutError", "video-generator", "pipeline", 1)  # fmt: skip

    m = client.get("/monitoring/metrics").json()
    assert m["workflows_by_status"] == {"COMPLETED": 1, "FAILED": 1, "RUNNING": 1}
    assert m["attempts_total"] == 2 and m["retries_total"] == 1
    assert m["workflow_duration_avg_ms"] == 5000.0
    assert m["steps_by_status"] == {"COMPLETED": 1}
    assert client.get("/monitoring/services").json()[0]["name"] == "video-generator"
    assert client.get("/monitoring/workers").json()[0]["status"] == "BUSY"


def test_rejected_events_are_listable(client):
    client.post("/events", json={"event_id": "bad-1", "event_type": "NOPE"})
    page = client.get("/events/rejected").json()
    assert page["total"] == 1 and page["items"][0]["raw"]["event_id"] == "bad-1" and page["items"][0]["error"]


def test_new_write_routes_require_api_key(anon_client):
    for path in ("/services/register", "/workers/register", "/jobs", "/monitoring/scan", "/workflows"):
        assert anon_client.post(path, json={}).status_code == 401


def test_trace_links_and_tool_links_follow_configuration(client, monkeypatch):
    client.post("/events", json=event("WORKFLOW_STARTED", run="r-t", wf="w-t"))
    client.post("/events", json=event("STEP_STARTED", run="r-t", wf="w-t", step="s"))
    run = client.get("/workflow-runs", params={"run_key": "r-t"}).json()["items"][0]
    assert run["trace_url"] is None and client.get("/monitoring/links").json()["jaeger_url"] is None

    monkeypatch.setenv("OBSKIT_PLATFORM_JAEGER_URL", "http://jaeger.local:16686/")
    monkeypatch.setenv("OBSKIT_PLATFORM_PERSES_URL", "http://perses.local")
    detail = client.get(f"/workflow-runs/{run['id']}").json()
    assert detail["trace_url"] == "http://jaeger.local:16686/trace/trace-1"
    assert detail["steps"][0]["attempts"][0]["trace_url"] == "http://jaeger.local:16686/trace/trace-1"
    assert client.get("/monitoring/links").json() == {
        "jaeger_url": "http://jaeger.local:16686/",
        "perses_url": "http://perses.local",
        "prometheus_url": None,
    }


def _retention(lost_after_s: float, purge_after_s: float, now: datetime | None = None):
    from app.db.incident_repository import IncidentRepository
    from app.db.registry_repository import RegistryRepository
    from app.registry.retention import RegistryRetention

    session = get_database().session()
    try:
        sweep = RegistryRetention(
            session, RegistryRepository(session), IncidentRepository(session), lost_after_s, purge_after_s
        )
        return sweep.sweep(now or datetime.now(UTC))
    finally:
        session.close()


def test_retention_stops_lost_entries_then_purges_them(client):
    w = client.post("/workers/register", json=WORKER).json()
    client.post(f"/workers/{w['id']}/heartbeat", json={"status": "IDLE"})
    age_heartbeats(60)
    client.post("/monitoring/scan")
    assert client.get("/incidents", params={"status": "OPEN"}).json()["total"] == 2

    # not silent long enough yet: nothing changes
    assert _retention(3600, 7200).instances_stopped == 0
    later = datetime.now(UTC) + timedelta(hours=2)
    result = _retention(3600, 0, later)  # purge disabled
    assert (result.instances_stopped, result.workers_stopped, result.instances_purged) == (1, 1, 0)
    assert client.get("/incidents", params={"status": "OPEN"}).json()["total"] == 0
    assert client.get("/workers").json()[0]["status"] == "STOPPED"

    result = _retention(3600, 7200, later + timedelta(hours=3))
    assert (result.instances_purged, result.workers_purged) == (1, 1)
    assert client.get("/workers").json() == []
    assert client.get("/services").json()[0]["instances_total"] == 0


def test_retention_keeps_healthy_and_recent_entries(client):
    client.post("/services/register", json=INSTANCE)
    stopped = {**INSTANCE, "instance_id": "vg-02"}
    sid = client.post("/services/register", json=stopped).json()["service_id"]
    client.post(f"/services/{sid}/heartbeat", json={"instance_id": "vg-02", "stopping": True})
    result = _retention(3600, 7200, datetime.now(UTC) + timedelta(hours=1))
    assert (result.instances_stopped, result.instances_purged) == (0, 0)
    assert client.get("/services").json()[0]["instances_total"] == 2
