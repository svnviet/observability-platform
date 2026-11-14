import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

# Infra figures a service may report in its health response (top level or under "system"). Host-level
# keys describe the machine; process_* keys describe this service alone. Anything else is ignored.
SYSTEM_KEYS = (
    "cpu_percent",
    "memory_percent",
    "disk_percent",
    "load_1m",
    "cpu_count",
    "memory_total_mb",
    "memory_used_mb",
    "disk_total_gb",
    "disk_used_gb",
    "process_cpu_percent",
    "process_memory_mb",
    "active_requests",
    "queue_depth",
)
_BODY_LIMIT = 65536
_DOWN_WORDS = {"down", "error", "fail", "failed", "unhealthy"}


@dataclass
class ProbeResult:
    ok: bool
    status_code: int | None = None
    latency_ms: float | None = None
    error: str | None = None
    system: dict[str, float] = field(default_factory=dict)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # a health URL must answer itself, not bounce elsewhere
        return None


def extract_system(body: object) -> dict[str, float]:
    if not isinstance(body, dict):
        return {}
    source = body.get("system") if isinstance(body.get("system"), dict) else body
    return {
        key: float(value)
        for key, value in source.items()
        if key in SYSTEM_KEYS and isinstance(value, int | float) and not isinstance(value, bool)
    }


class HealthClient:
    """Outbound GET of a service's health_url. Fail-soft by design: every problem becomes a failed ProbeResult."""

    def __init__(self, timeout_s: float) -> None:
        self._timeout = timeout_s
        self._opener = urllib.request.build_opener(_NoRedirect)

    def probe(self, url: str) -> ProbeResult:
        if not url.startswith(("http://", "https://")):
            return ProbeResult(False, error="health_url must be http or https")
        started = time.monotonic()
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "obskit-platform-probe/1"})
            with self._opener.open(request, timeout=self._timeout) as response:
                status, raw = response.status, response.read(_BODY_LIMIT)
        except urllib.error.HTTPError as exc:
            return ProbeResult(False, exc.code, self._ms(started), f"HTTP {exc.code}")
        except Exception as exc:  # noqa: BLE001 - DNS, refused, timeout, TLS: all mean "not healthy"
            return ProbeResult(False, None, self._ms(started), f"{type(exc).__name__}: {exc}"[:300])
        latency = self._ms(started)
        try:
            body = json.loads(raw)
        except ValueError:
            body = None
        reported = str(body.get("status", "")).lower() if isinstance(body, dict) else ""
        if not 200 <= status < 300:
            return ProbeResult(False, status, latency, f"HTTP {status}")
        if reported in _DOWN_WORDS:
            return ProbeResult(False, status, latency, f"service reports status={reported}", extract_system(body))
        return ProbeResult(True, status, latency, None, extract_system(body))

    @staticmethod
    def _ms(started: float) -> float:
        return round((time.monotonic() - started) * 1000, 1)
