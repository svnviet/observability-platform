import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.db.health_repository import HealthRepository
from app.db.incident_repository import IncidentRepository
from app.db.models import ServiceInstanceRow
from app.registry.health_client import HealthClient
from app.schemas.enums import Severity


def instance_health_key(instance_row_id: uuid.UUID) -> str:
    return f"instance-health-failing:{instance_row_id}"


@dataclass
class ProbeSummary:
    checked: int
    down: int


class HealthProber:
    """Probes every instance that registered a health_url and records the result.

    An incident opens after `fail_threshold` consecutive failures and closes on the next success.
    """

    def __init__(
        self,
        session: Session,
        health: HealthRepository,
        incidents: IncidentRepository,
        client: HealthClient,
        fail_threshold: int,
        max_parallel: int = 8,
    ) -> None:
        self._session = session
        self._health = health
        self._incidents = incidents
        self._client = client
        self._threshold = max(1, fail_threshold)
        self._parallel = max_parallel

    def run(self, now: datetime) -> ProbeSummary:
        targets = self._health.targets()
        if not targets:
            return ProbeSummary(0, 0)
        urls = [t.metadata_["health_url"] for t in targets]
        with ThreadPoolExecutor(max_workers=min(self._parallel, len(urls))) as pool:
            results = list(pool.map(self._client.probe, urls))  # network only; DB writes stay on this thread
        down = 0
        for target, result in zip(targets, results):
            self._health.add(
                target.id, now, result.ok, result.status_code, result.latency_ms, result.error, result.system
            )
            self._evaluate(target, now)
            down += not result.ok
        self._session.commit()
        return ProbeSummary(len(targets), down)

    def _evaluate(self, instance: ServiceInstanceRow, now: datetime) -> None:
        recent = self._health.recent(instance.id, self._threshold)
        if recent and recent[0].ok:
            self._incidents.resolve_by_key(instance_health_key(instance.id), now)
        elif len(recent) == self._threshold and not any(c.ok for c in recent):
            self._incidents.open_incident(
                dedupe_key=instance_health_key(instance.id),
                severity=Severity.HIGH,
                title=f"{instance.service.name} instance {instance.instance_id} health check failing",
                description=f"{self._threshold} consecutive probes of {instance.metadata_['health_url']} failed: "
                f"{recent[0].error}",
                service_id=instance.service_id,
                now=now,
            )
