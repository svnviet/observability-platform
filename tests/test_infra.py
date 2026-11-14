from datetime import UTC, datetime, timedelta

from app.db.health_repository import HealthRepository
from app.db.incident_repository import IncidentRepository
from app.db.session import get_database
from app.registry.health_client import HealthClient, ProbeResult, extract_system
from app.registry.prober import HealthProber

INSTANCE = {"service_name": "news-image", "instance_id": "img-1", "environment": "prod", "hostname": "vps-1",
            "metadata": {"health_url": "http://img.local/health"}}  # fmt: skip


class FakeClient:
    def __init__(self, *results: ProbeResult) -> None:
        self._results = list(results)

    def probe(self, url: str) -> ProbeResult:
        return self._results.pop(0) if len(self._results) > 1 else self._results[0]


UP = ProbeResult(True, 200, 12.0, None, {"cpu_percent": 30.0, "memory_percent": 50.0})
DOWN = ProbeResult(False, None, 5000.0, "TimeoutError: timed out")


def probe_round(client, now, threshold=3):
    session = get_database().session()
    try:
        return HealthProber(session, HealthRepository(session), IncidentRepository(session), client, threshold).run(now)
    finally:
        session.close()


def test_extract_system_keeps_only_known_numeric_figures():
    body = {"status": "ok", "system": {"cpu_percent": 41.5, "memory_percent": True, "secret": 1, "disk_percent": 70}}
    assert extract_system(body) == {"cpu_percent": 41.5, "disk_percent": 70.0}
    assert extract_system({"cpu_percent": 5, "token": "x"}) == {"cpu_percent": 5.0}
    assert extract_system(["not", "a", "dict"]) == {}


def test_client_rejects_non_http_urls_without_connecting():
    result = HealthClient(1).probe("file:///etc/passwd")
    assert not result.ok and "http" in result.error


def test_probe_unreachable_host_is_a_failed_result_not_an_exception():
    result = HealthClient(1).probe("http://127.0.0.1:9/health")
    assert not result.ok and result.error


def test_set_health_url_and_probing_flow(client):
    sid = client.post("/services/register", json={**INSTANCE, "metadata": {}}).json()["service_id"]
    url = f"/services/{sid}/instances/img-1/health-url"
    assert client.put(url, json={"health_url": "ftp://x"}).status_code == 422
    assert client.put(url, json={"health_url": "http://img.local/health"}).json()["health_url"] == "http://img.local/health"
    assert client.put(f"/services/{sid}/instances/ghost/health-url", json={"health_url": None}).status_code == 404

    now = datetime.now(UTC)
    assert probe_round(FakeClient(UP), now).checked == 1
    [inst] = client.get("/monitoring/infra/instances").json()
    assert (inst["state"], inst["checks"], inst["uptime_pct"]) == ("UP", 1, 100.0)
    assert inst["system_latest"] == {"cpu_percent": 30.0, "memory_percent": 50.0}

    client.put(url, json={"health_url": None})  # stop probing
    assert probe_round(FakeClient(UP), now).checked == 0


def test_consecutive_failures_open_an_incident_and_recovery_closes_it(client):
    client.post("/services/register", json=INSTANCE)
    start = datetime.now(UTC) - timedelta(minutes=10)
    for i, result in enumerate([UP, DOWN, DOWN]):
        probe_round(FakeClient(result), start + timedelta(minutes=i))
    assert client.get("/incidents", params={"status": "OPEN"}).json()["total"] == 0  # 2 failures < threshold 3

    probe_round(FakeClient(DOWN), start + timedelta(minutes=3))
    [incident] = client.get("/incidents", params={"status": "OPEN"}).json()["items"]
    assert "health check failing" in incident["title"]
    [inst] = client.get("/monitoring/infra/instances").json()
    assert inst["state"] == "DOWN" and inst["down_since"] is not None and inst["last_error"]
    assert inst["outages"][0]["ended_at"] is None

    probe_round(FakeClient(UP), start + timedelta(minutes=4))
    assert client.get("/incidents", params={"status": "OPEN"}).json()["total"] == 0
    [inst] = client.get("/monitoring/infra/instances").json()
    assert inst["state"] == "UP" and inst["outages"][0]["ended_at"] is not None
    assert inst["uptime_pct"] == 40.0  # 2 of 5 probes succeeded


def test_hosts_report_capacity_findings(client):
    for name in ("a", "b"):
        client.post("/services/register", json={**INSTANCE, "service_name": f"svc-{name}", "instance_id": name})
    hot = ProbeResult(True, 200, 30.0, None, {"cpu_percent": 92.0, "memory_percent": 60.0, "process_memory_mb": 400})
    probe_round(FakeClient(hot), datetime.now(UTC))
    [host] = client.get("/monitoring/infra/hosts").json()
    assert host["hostname"] == "vps-1" and host["services"] == ["svc-a", "svc-b"]
    assert host["system_p95"]["cpu_percent"] == 92.0 and host["process_memory_mb_total"] == 800.0
    assert any("CPU p95" in f for f in host["findings"]) and any("share this host" in f for f in host["findings"])


def test_stopped_instances_are_not_probed(client):
    sid = client.post("/services/register", json=INSTANCE).json()["service_id"]
    client.post(f"/services/{sid}/heartbeat", json={"instance_id": "img-1", "stopping": True})
    assert probe_round(FakeClient(UP), datetime.now(UTC)).checked == 0


def test_old_probe_history_is_purged_and_purged_instances_take_their_checks(client):
    client.post("/services/register", json=INSTANCE)
    now = datetime.now(UTC)
    probe_round(FakeClient(UP), now - timedelta(days=30))
    session = get_database().session()
    try:
        assert HealthRepository(session).purge_before(now - timedelta(days=14)) == 1
        session.commit()
    finally:
        session.close()
    assert client.get("/monitoring/infra/instances", params={"window_hours": 720}).json()[0]["checks"] == 0


def test_infra_reads_are_open_and_the_url_change_needs_a_key(anon_client, client):
    sid = client.post("/services/register", json=INSTANCE).json()["service_id"]
    assert anon_client.get("/monitoring/infra/hosts").status_code == 200
    assert anon_client.put(f"/services/{sid}/instances/img-1/health-url", json={"health_url": None}).status_code == 401


def test_purging_a_stopped_instance_removes_its_probe_history(client):
    from sqlalchemy import func, select

    from app.db.models import HealthCheckRow
    from app.registry.retention import RegistryRetention
    from app.db.registry_repository import RegistryRepository

    sid = client.post("/services/register", json=INSTANCE).json()["service_id"]
    probe_round(FakeClient(UP), datetime.now(UTC))
    client.post(f"/services/{sid}/heartbeat", json={"instance_id": "img-1", "stopping": True})
    session = get_database().session()
    try:
        later = datetime.now(UTC) + timedelta(days=30)
        sweep = RegistryRetention(session, RegistryRepository(session), IncidentRepository(session), 3600, 7200)
        assert sweep.sweep(later).instances_purged == 1
        assert session.scalar(select(func.count()).select_from(HealthCheckRow)) == 0
    finally:
        session.close()
