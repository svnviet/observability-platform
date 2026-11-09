import logging
import threading
from datetime import UTC, datetime

from app.core.config import heartbeat_scan_interval_s, heartbeat_timeout_s
from app.db.incident_repository import IncidentRepository
from app.db.registry_repository import RegistryRepository
from app.db.session import Database, get_database
from app.registry.heartbeat import HeartbeatMonitor

log = logging.getLogger("observability_platform.heartbeat")


class HeartbeatScheduler:
    """Runs HeartbeatMonitor.scan on a timer in a daemon thread."""

    def __init__(self, database: Database, interval_s: float, timeout_s: float) -> None:
        self._database = database
        self._interval = interval_s
        self._timeout = timeout_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @classmethod
    def from_config(cls) -> "HeartbeatScheduler":
        return cls(get_database(), heartbeat_scan_interval_s(), heartbeat_timeout_s())

    def start(self) -> None:
        if self._interval <= 0:
            return
        self._thread = threading.Thread(target=self._run, name="heartbeat-scan", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            session = self._database.session()
            try:
                monitor = HeartbeatMonitor(
                    session, RegistryRepository(session), IncidentRepository(session), self._timeout
                )
                monitor.scan(datetime.now(UTC))
            except Exception:  # a failed scan must not end the loop
                log.exception("heartbeat scan failed")
                session.rollback()
            finally:
                session.close()
