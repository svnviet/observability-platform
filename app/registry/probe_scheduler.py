import logging
import threading
from datetime import UTC, datetime, timedelta

from app.core.config import (
    health_fail_threshold,
    health_probe_interval_s,
    health_probe_timeout_s,
    health_retention_days,
)
from app.db.health_repository import HealthRepository
from app.db.incident_repository import IncidentRepository
from app.db.session import Database, get_database
from app.registry.health_client import HealthClient
from app.registry.prober import HealthProber

log = logging.getLogger("observability_platform.probe")


class HealthProbeScheduler:
    """Runs HealthProber.run on a timer in a daemon thread and trims old probe history."""

    def __init__(self, database: Database, interval_s: float) -> None:
        self._database = database
        self._interval = interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @classmethod
    def from_config(cls) -> "HealthProbeScheduler":
        return cls(get_database(), health_probe_interval_s())

    def start(self) -> None:
        if self._interval <= 0:
            return
        self._thread = threading.Thread(target=self._run, name="health-probe", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        client = HealthClient(health_probe_timeout_s())
        while not self._stop.wait(self._interval):
            session = self._database.session()
            try:
                health = HealthRepository(session)
                now = datetime.now(UTC)
                HealthProber(session, health, IncidentRepository(session), client, health_fail_threshold()).run(now)
                if health_retention_days():
                    health.purge_before(now - timedelta(days=health_retention_days()))
                    session.commit()
            except Exception:  # a failed round must not end the loop
                log.exception("health probe round failed")
                session.rollback()
            finally:
                session.close()
