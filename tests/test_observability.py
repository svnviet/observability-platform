import uuid

from tests.factories import event

def test_service_and_worker_links_use_their_own_ids(client, monkeypatch):
    monkeypatch.setenv("OBSKIT_PLATFORM_DASHBOARD_URL_TEMPLATE", "http://perses.local/d/w?s={service}&i={instance}&w={worker}")
    worker = client.post(
        "/workers/register",
        json={"service_name": "video", "instance_id": "video-1", "worker_name": "w-1", "environment": "prod"},
    ).json()
    sid = client.get("/services").json()[0]["id"]

    svc = client.get(f"/services/{sid}/observability").json()
    assert svc["entity"] == {"type": "service", "id": sid}
    assert svc["correlation"]["service"] == "video"
    assert svc["links"]["dashboard"]["available"] is False  # {instance} and {worker} have no value at service level

    wrk = client.get(f"/workers/{worker['id']}/observability").json()
    assert wrk["correlation"]["instance"] == "video-1" and wrk["correlation"]["worker"] == "w-1"
    assert wrk["links"]["dashboard"]["url"] == "http://perses.local/d/w?s=video&i=video-1&w=w-1"
    assert wrk["capabilities"] == {name: link["available"] for name, link in wrk["links"].items()}


def test_run_link_uses_the_runs_trace_and_run_id(client, monkeypatch):
    monkeypatch.setenv("OBSKIT_PLATFORM_JAEGER_URL", "http://jaeger.local")
    assert client.post("/events", json=event("WORKFLOW_STARTED")).status_code == 200
    run = client.get("/workflow-runs").json()["items"][0]
    seen = client.get(f"/workflow-runs/{run['id']}/observability").json()
    assert seen["entity"]["type"] == "workflow_run"
    assert seen["correlation"]["workflow_run_id"] == run["run_key"]
    assert seen["links"]["trace"]["url"] == f"http://jaeger.local/trace/{run['trace_id']}"
    assert seen["capabilities"]["trace"] is True


def test_incident_links_carry_a_bounded_time_window(client, monkeypatch):
    monkeypatch.setenv("OBSKIT_PLATFORM_LOGS_URL_TEMPLATE", "http://logs.local/q?svc={service}&from={from}&to={to}")
    client.post("/services/register", json={"service_name": "video", "instance_id": "v-1", "environment": "prod"})
    client.post("/events", json=event("WORKFLOW_STARTED", t=0))
    client.post("/events", json=event("WORKFLOW_FAILED", t=5, error={"type": "Boom", "message": "x"}))
    incidents = client.get("/incidents").json()["items"]
    assert incidents, "a failed workflow opens an incident"
    seen = client.get(f"/incidents/{incidents[0]['id']}/observability").json()
    assert seen["entity"]["type"] == "incident"
    assert "from" not in seen["correlation"] and "to" not in seen["correlation"]  # window is for the URL only
    assert seen["links"]["logs"]["available"] is False  # {service} has no value: this incident belongs to a run


def test_unknown_entities_are_404_and_reads_are_open(client, anon_client):
    for path in ("services", "workers", "workflow-runs", "incidents"):
        assert client.get(f"/{path}/{uuid.uuid4()}/observability").status_code == 404
        assert anon_client.get(f"/{path}/{uuid.uuid4()}/observability").status_code == 404  # 404, not 401


def test_window_is_never_wider_than_a_day():
    from datetime import UTC, datetime, timedelta

    from app.observability.service import ObservabilityService

    start, end = ObservabilityService._window(datetime(2026, 1, 1, tzinfo=UTC), None)
    assert end - start <= timedelta(hours=24)
    s2, e2 = ObservabilityService._window(datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 1, 1, tzinfo=UTC))
    assert e2 - s2 == timedelta(hours=1, minutes=10)
