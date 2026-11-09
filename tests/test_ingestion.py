from tests.factories import event


def run_id(client, run_key="run-1"):
    page = client.get("/workflow-runs", params={"run_key": run_key}).json()
    assert page["total"] == 1
    return page["items"][0]["id"]


def post_all(client, events):
    return [client.post("/events", json=e).json() for e in events]


def test_happy_path_builds_state_and_history(client):
    post_all(
        client,
        [
            event("WORKFLOW_STARTED", t=0, workflow_name="news-video-pipeline"),
            event("STEP_STARTED", t=1, step="render", step_name="video-render"),
            event("STEP_COMPLETED", t=5, step="render"),
            event("WORKFLOW_COMPLETED", t=6),
        ],
    )
    rid = run_id(client)
    detail = client.get(f"/workflow-runs/{rid}").json()
    assert detail["status"] == "COMPLETED"
    assert detail["workflow_name"] == "news-video-pipeline"
    assert detail["duration_ms"] == 6000
    assert detail["correlation_id"] == "corr-1"
    [step] = detail["steps"]
    assert (step["step_name"], step["status"], step["service_name"]) == (
        "video-render",
        "COMPLETED",
        "video-generator",
    )
    assert step["attempts"][0]["status"] == "COMPLETED"
    assert step["attempts"][0]["worker_key"] == "worker-1"

    events = client.get(f"/workflow-runs/{rid}/events").json()
    assert events["total"] == 4
    assert all(e["disposition"] == "APPLIED" for e in events["items"])


def test_retries_create_separate_attempts(client):
    post_all(
        client,
        [
            event("WORKFLOW_STARTED", t=0),
            event("STEP_STARTED", t=1, step="render", attempt=1),
            event(
                "STEP_FAILED", t=2, step="render", attempt=1, will_retry=True, error={"type": "RenderError"}
            ),
            event("STEP_STARTED", t=3, step="render", attempt=2),
            event("STEP_FAILED", t=4, step="render", attempt=2, will_retry=True),
            event("STEP_STARTED", t=5, step="render", attempt=3),
            event("STEP_COMPLETED", t=6, step="render", attempt=3),
        ],
    )
    [step] = client.get(f"/workflow-runs/{run_id(client)}/steps").json()
    assert step["status"] == "COMPLETED"
    assert step["latest_attempt_number"] == 3
    assert [a["status"] for a in step["attempts"]] == ["FAILED", "FAILED", "COMPLETED"]
    assert step["attempts"][0]["error_details"] == {"type": "RenderError"}


def test_step_in_retrying_state_between_attempts(client):
    post_all(
        client,
        [
            event("STEP_STARTED", t=1, step="render", attempt=1),
            event("STEP_FAILED", t=2, step="render", attempt=1, will_retry=True),
        ],
    )
    [step] = client.get(f"/workflow-runs/{run_id(client)}/steps").json()
    assert step["status"] == "RETRYING"
    assert step["finished_at"] is None


def test_terminal_failure_without_retry(client):
    post_all(
        client,
        [event("STEP_STARTED", t=1, step="s"), event("STEP_FAILED", t=2, step="s", will_retry=False)],
    )
    [step] = client.get(f"/workflow-runs/{run_id(client)}/steps").json()
    assert step["status"] == "FAILED"


def test_duplicate_event_does_not_change_history(client):
    e = event("WORKFLOW_STARTED", event_id="evt-dup")
    first = client.post("/events", json=e).json()
    second = client.post("/events", json=e).json()
    assert first["outcome"] == "ACCEPTED"
    assert second["outcome"] == "DUPLICATE"
    rid = run_id(client)
    assert client.get(f"/workflow-runs/{rid}/events").json()["total"] == 1


def test_invalid_events_rejected_without_breaking_batch(client):
    good = event("WORKFLOW_STARTED")
    bad_type = {**event("WORKFLOW_STARTED"), "event_type": "NOPE"}
    no_step = event("STEP_STARTED")  # step event without context.step_id
    future = {**event("WORKFLOW_STARTED"), "event_version": 99}
    naive_time = {**event("WORKFLOW_STARTED"), "occurred_at": "2026-11-09T12:00:00"}
    res = client.post("/events/batch", json={"events": [good, bad_type, no_step, future, naive_time]}).json()
    assert (res["accepted"], res["duplicates"], res["rejected"]) == (1, 0, 4)
    assert "unsupported event_version" in res["results"][3]["detail"]


def test_out_of_order_completion_before_start(client):
    post_all(
        client,
        [
            event("WORKFLOW_COMPLETED", t=10),
            event("WORKFLOW_STARTED", t=0),
        ],
    )
    rid = run_id(client)
    detail = client.get(f"/workflow-runs/{rid}").json()
    assert detail["status"] == "COMPLETED"
    assert detail["duration_ms"] == 10000
    dispositions = [e["disposition"] for e in client.get(f"/workflow-runs/{rid}/events").json()["items"]]
    # listed by occurrence: STARTED (t=0) arrived late and is stale, COMPLETED (t=10) applied
    assert dispositions == ["STALE", "APPLIED"]


def test_late_attempt_event_does_not_regress_step(client):
    post_all(
        client,
        [
            event("STEP_STARTED", t=3, step="s", attempt=2),
            event("STEP_COMPLETED", t=4, step="s", attempt=2),
            event("STEP_STARTED", t=1, step="s", attempt=1),  # arrives late
            event("STEP_FAILED", t=2, step="s", attempt=1, will_retry=True),  # arrives late
        ],
    )
    [step] = client.get(f"/workflow-runs/{run_id(client)}/steps").json()
    assert step["status"] == "COMPLETED"
    assert step["latest_attempt_number"] == 2
    assert [a["status"] for a in step["attempts"]] == ["FAILED", "COMPLETED"]


def test_conflicting_terminal_is_quarantined_and_replay_is_deterministic(client):
    # FAILED happened first (t=5) but COMPLETED (t=9) was received first.
    post_all(
        client,
        [
            event("WORKFLOW_STARTED", t=0),
            event("WORKFLOW_COMPLETED", t=9, event_id="evt-completed"),
            event("WORKFLOW_FAILED", t=5, event_id="evt-failed", error={"type": "Boom"}),
        ],
    )
    rid = run_id(client)
    assert client.get(f"/workflow-runs/{rid}").json()["status"] == "COMPLETED"
    assert client.get("/events/evt-failed").json()["disposition"] == "QUARANTINED"

    replay = client.post("/events/replay", json={"workflow_run_ids": [rid]}).json()["results"][0]
    assert replay["found"] and replay["events_replayed"] == 3

    detail = client.get(f"/workflow-runs/{rid}").json()
    assert detail["status"] == "FAILED"
    assert detail["error_details"] == {"type": "Boom"}
    assert client.get("/events/evt-completed").json()["disposition"] == "QUARANTINED"

    # replaying again changes nothing
    again = client.post("/events/replay", json={"workflow_run_ids": [rid]}).json()["results"][0]
    assert (again["applied"], again["stale"], again["quarantined"]) == (
        replay["applied"],
        replay["stale"],
        replay["quarantined"],
    )


def test_replay_unknown_run(client):
    res = client.post("/events/replay", json={"workflow_run_ids": ["00000000-0000-0000-0000-000000000000"]})
    assert res.json()["results"][0]["found"] is False
