import uuid

from tests.factories import event

SVC = {"service_name": "video", "instance_id": "video-1", "environment": "prod"}


def register(client, **extra):
    return client.post("/services/register", json={**SVC, **extra}).json()["service_id"]


def worker(client, name="w-1", **extra):
    return client.post("/workers/register", json={**SVC, "worker_name": name, **extra}).json()


def test_service_metadata_and_version_are_edited_by_merge_and_null_removes_a_key(client):
    sid = register(client)
    first = client.patch(f"/services/{sid}", json={"version": "2.0", "metadata": {"team": "media", "tier": "gold"}}).json()
    assert (first["version"], first["metadata"]) == ("2.0", {"team": "media", "tier": "gold"})
    second = client.patch(f"/services/{sid}", json={"metadata": {"tier": None, "owner": "an"}}).json()
    assert second["metadata"] == {"team": "media", "owner": "an"} and second["version"] == "2.0"
    assert client.get(f"/services/{sid}").json()["name"] == "video"  # identity is not editable
    assert client.patch(f"/services/{uuid.uuid4()}", json={"version": "1"}).status_code == 404


def test_instance_is_edited_and_a_bad_health_url_is_rejected(client):
    sid = register(client)
    seen = client.patch(
        f"/services/{sid}/instances/video-1",
        json={"hostname": "host-b", "metadata": {"health_url": "https://video.example/health", "zone": "a"}},
    ).json()
    assert seen["hostname"] == "host-b" and seen["metadata"]["zone"] == "a"
    assert client.get(f"/services/{sid}").json()["instances"][0]["metadata"]["health_url"].startswith("https://")
    bad = client.patch(f"/services/{sid}/instances/video-1", json={"metadata": {"health_url": "ftp://x"}})
    assert bad.status_code == 422
    assert client.patch(f"/services/{sid}/instances/nope", json={"hostname": "h"}).status_code == 404


def test_worker_is_edited(client):
    w = worker(client)
    seen = client.patch(f"/workers/{w['id']}", json={"capacity": 4, "worker_type": "render", "metadata": {"gpu": True}}).json()
    assert (seen["capacity"], seen["worker_type"], seen["metadata"]) == (4, "render", {"gpu": True})
    assert client.patch(f"/workers/{w['id']}", json={"capacity": 0}).status_code == 422
    assert client.patch(f"/workers/{uuid.uuid4()}", json={"capacity": 1}).status_code == 404


def test_deleting_a_worker_keeps_its_jobs(client):
    w = worker(client)
    job = client.post("/jobs", json={**SVC, "external_job_id": "j-1", "status": "RUNNING", "worker_name": "w-1"}).json()
    assert job["worker_id"] == w["id"]
    assert client.delete(f"/workers/{w['id']}").json() == {
        "deleted": "worker", "instances": 0, "workers": 1, "jobs": 0, "events": 0}  # fmt: skip
    assert client.get(f"/workers/{w['id']}").status_code == 404
    kept = client.get(f"/jobs/{job['id']}").json()
    assert kept["status"] == "RUNNING" and kept["worker_id"] is None
    assert client.delete(f"/workers/{w['id']}").status_code == 404


def test_deleting_an_instance_removes_its_workers_and_it_can_register_again(client):
    sid = register(client)
    worker(client, "w-1")
    worker(client, "w-2")
    gone = client.delete(f"/services/{sid}/instances/video-1").json()
    assert (gone["deleted"], gone["instances"], gone["workers"]) == ("instance", 1, 2)
    assert client.get(f"/services/{sid}").json()["status"] == "NO_INSTANCES"
    assert client.get("/workers").json() == []
    assert client.post(f"/services/{sid}/heartbeat", json={"instance_id": "video-1"}).status_code == 404
    assert register(client) == sid  # the same service id; the instance simply registers again
    assert client.get(f"/services/{sid}").json()["status"] == "HEALTHY"


def test_a_service_is_deleted_only_when_stopped_and_jobs_need_an_explicit_yes(client):
    sid = register(client)
    client.post("/jobs", json={**SVC, "external_job_id": "j-1", "status": "COMPLETED"})
    alive = client.delete(f"/services/{sid}")
    assert alive.status_code == 409 and "video-1" in alive.json()["detail"]

    client.post(f"/services/{sid}/heartbeat", json={"instance_id": "video-1", "stopping": True})
    has_jobs = client.delete(f"/services/{sid}")
    assert has_jobs.status_code == 409 and "delete_jobs=true" in has_jobs.json()["detail"]
    assert client.get(f"/services/{sid}").status_code == 200  # nothing was removed by the refused calls

    done = client.delete(f"/services/{sid}", params={"delete_jobs": True}).json()
    assert (done["deleted"], done["instances"], done["jobs"]) == ("service", 1, 1)
    assert client.get(f"/services/{sid}").status_code == 404
    assert client.get("/jobs").json()["total"] == 0
    assert client.delete(f"/services/{sid}").status_code == 404


def test_deleting_a_service_keeps_workflow_history(client):
    client.post("/events", json=event("WORKFLOW_STARTED", service="video"))
    client.post("/events", json=event("STEP_STARTED", step="render", service="video", t=1))
    sid = next(s["id"] for s in client.get("/services").json() if s["name"] == "video")
    assert client.delete(f"/services/{sid}").json()["deleted"] == "service"  # no instances, no jobs
    run = client.get("/workflow-runs").json()["items"][0]
    steps = client.get(f"/workflow-runs/{run['id']}/steps").json()
    assert [s["step_key"] for s in steps] == ["render"] and steps[0]["service_name"] is None


def test_an_unfinished_run_needs_force_and_deleting_a_run_keeps_its_jobs(client):
    client.post("/events", json=event("WORKFLOW_STARTED"))
    client.post("/events", json=event("STEP_STARTED", step="render", t=1))
    job = client.post("/jobs", json={**SVC, "external_job_id": "j-1", "status": "RUNNING", "workflow_run_key": "run-1"}).json()
    run = client.get("/workflow-runs").json()["items"][0]
    assert job["workflow_run_id"] == run["id"]

    refused = client.delete(f"/workflow-runs/{run['id']}")
    assert refused.status_code == 409 and "force=true" in refused.json()["detail"]
    done = client.delete(f"/workflow-runs/{run['id']}", params={"force": True}).json()
    assert done["deleted"] == "workflow_run" and done["events"] == 2
    assert client.get(f"/workflow-runs/{run['id']}").status_code == 404
    assert client.get(f"/jobs/{job['id']}").json()["workflow_run_id"] is None
    assert client.delete(f"/workflow-runs/{uuid.uuid4()}").status_code == 404


def test_a_finished_run_is_deleted_without_force(client):
    client.post("/events", json=event("WORKFLOW_STARTED"))
    client.post("/events", json=event("WORKFLOW_COMPLETED", t=5))
    run = client.get("/workflow-runs").json()["items"][0]
    assert client.delete(f"/workflow-runs/{run['id']}").status_code == 200


def test_edits_and_deletes_need_the_api_key(anon_client, client):
    sid = register(client)
    w = worker(client)
    assert anon_client.patch(f"/services/{sid}", json={"version": "9"}).status_code == 401
    assert anon_client.delete(f"/services/{sid}").status_code == 401
    assert anon_client.delete(f"/services/{sid}/instances/video-1").status_code == 401
    assert anon_client.patch(f"/workers/{w['id']}", json={"capacity": 2}).status_code == 401
    assert anon_client.delete(f"/workers/{w['id']}").status_code == 401
    assert anon_client.delete(f"/workflow-runs/{uuid.uuid4()}").status_code == 401
    assert client.get(f"/services/{sid}").json()["version"] is None  # nothing changed
