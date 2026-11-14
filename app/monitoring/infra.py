import math
from collections import defaultdict
from datetime import datetime, timedelta

from app.db.health_repository import HealthRepository
from app.db.models import HealthCheckRow, ServiceInstanceRow
from app.schemas.infra import InfraHost, InfraInstance, Outage

_HOST_KEYS = ("cpu_percent", "memory_percent", "disk_percent", "load_1m")
# Thresholds behind the findings that suggest moving a service off a host.
_CPU_HOT, _MEMORY_HOT, _DISK_HOT = 80.0, 85.0, 85.0


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(pct / 100 * len(ordered)) - 1)]


class InfraAnalytics:
    """Turns probe history into uptime, outages and capacity figures, per instance and per host."""

    def __init__(self, health: HealthRepository, fail_threshold: int) -> None:
        self._health = health
        self._threshold = max(1, fail_threshold)

    def instances(self, window_hours: int, now: datetime) -> list[InfraInstance]:
        checks = self._health.since(now - timedelta(hours=window_hours))
        by_instance: dict = defaultdict(list)
        for check in checks:
            by_instance[check.service_instance_id].append(check)
        rows = self._health.instances_with_history_or_url(set(by_instance))
        result = [self._instance(row, by_instance.get(row.id, []), now) for row in rows]
        return sorted(result, key=lambda i: (i.service_name, i.instance_id))

    def hosts(self, window_hours: int, now: datetime) -> list[InfraHost]:
        by_host: dict[str, list[InfraInstance]] = defaultdict(list)
        for instance in self.instances(window_hours, now):
            if instance.checks:
                by_host[instance.hostname or "unknown"].append(instance)
        hosts = [self._host(name, members) for name, members in by_host.items()]
        return sorted(hosts, key=lambda h: h.hostname)

    # ------------------------------------------------------------------------------------------

    def _instance(self, row: ServiceInstanceRow, checks: list[HealthCheckRow], now: datetime) -> InfraInstance:
        ok_latencies = [c.latency_ms for c in checks if c.ok and c.latency_ms is not None]
        last = checks[-1] if checks else None
        outages = self._outages(checks, now)
        return InfraInstance(
            service_name=row.service.name,
            environment=row.service.environment,
            instance_id=row.instance_id,
            hostname=row.hostname,
            health_url=row.metadata_.get("health_url"),
            state="UNKNOWN" if last is None else ("UP" if last.ok else "DOWN"),
            checks=len(checks),
            uptime_pct=round(100 * sum(c.ok for c in checks) / len(checks), 2) if checks else None,
            latency_p50_ms=percentile(ok_latencies, 50),
            latency_p95_ms=percentile(ok_latencies, 95),
            last_checked_at=last.checked_at if last else None,
            last_error=last.error if last and not last.ok else None,
            down_since=outages[-1].started_at if outages and outages[-1].ended_at is None else None,
            outages=outages,
            system_latest=dict(last.system) if last else {},
            system_p95=self._system(checks, lambda v: percentile(v, 95)),
            system_peak=self._system(checks, max),
        )

    def _outages(self, checks: list[HealthCheckRow], now: datetime) -> list[Outage]:
        """A run of at least `fail_threshold` failed probes in a row, ended by the next success."""
        outages: list[Outage] = []
        run: list[HealthCheckRow] = []

        def close(ended: HealthCheckRow | None) -> None:
            if len(run) >= self._threshold:
                end_at = ended.checked_at if ended else None
                outages.append(
                    Outage(
                        started_at=run[0].checked_at,
                        ended_at=end_at,
                        duration_s=((end_at or now) - run[0].checked_at).total_seconds(),
                        error=run[-1].error,
                    )
                )

        for check in checks:
            if check.ok:
                close(check)
                run = []
            else:
                run.append(check)
        close(None)
        return outages

    @staticmethod
    def _system(checks: list[HealthCheckRow], reduce) -> dict[str, float]:
        series: dict[str, list[float]] = defaultdict(list)
        for check in checks:
            for key, value in check.system.items():
                series[key].append(float(value))
        return {key: round(reduce(values), 2) for key, values in series.items() if values}

    @staticmethod
    def _host(name: str, members: list[InfraInstance]) -> InfraHost:
        p95: dict[str, float] = {}
        for key in _HOST_KEYS:
            values = [m.system_p95[key] for m in members if key in m.system_p95]
            if values:
                p95[key] = max(values)
        memory = [m.system_latest["process_memory_mb"] for m in members if "process_memory_mb" in m.system_latest]
        uptimes = [m.uptime_pct for m in members if m.uptime_pct is not None]
        outages = sum(len(m.outages) for m in members)
        services = sorted({m.service_name for m in members})
        findings = []
        if p95.get("cpu_percent", 0) >= _CPU_HOT:
            findings.append(f"CPU p95 {p95['cpu_percent']:.0f}% is above {_CPU_HOT:.0f}%: no headroom for a spike")
        if p95.get("memory_percent", 0) >= _MEMORY_HOT:
            findings.append(f"Memory p95 {p95['memory_percent']:.0f}% is above {_MEMORY_HOT:.0f}%")
        if p95.get("disk_percent", 0) >= _DISK_HOT:
            findings.append(f"Disk p95 {p95['disk_percent']:.0f}% is above {_DISK_HOT:.0f}%")
        if outages:
            findings.append(f"{outages} outage(s) in the window")
        if findings and len(services) > 1:
            findings.append(f"{len(services)} services share this host: candidates to move apart")
        if not p95:
            findings.append("No infra figures reported: add cpu/memory/disk to the health response")
        return InfraHost(
            hostname=name,
            services=services,
            instances=len(members),
            uptime_pct_min=min(uptimes) if uptimes else None,
            outages_total=outages,
            system_p95=p95,
            process_memory_mb_total=round(sum(memory), 1) if memory else None,
            findings=findings,
        )
