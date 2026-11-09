def test_health_is_open(anon_client):
    assert anon_client.get("/health").json() == {"status": "ok"}


def test_protected_routes_need_key(anon_client):
    assert anon_client.get("/workflow-runs").status_code == 401
    assert anon_client.post("/events", json={}).status_code == 401


def test_wrong_key_rejected(anon_client):
    assert anon_client.get("/workflow-runs", headers={"X-API-Key": "nope"}).status_code == 401


def test_docs_routes_are_not_public(anon_client):
    for path in ("/docs", "/redoc"):
        assert anon_client.get(path).status_code == 404
    assert anon_client.get("/openapi.json").status_code == 401


def test_openapi_schema_available_with_key(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/events" in paths and "/workflow-runs/{run_id}/timeline" in paths
