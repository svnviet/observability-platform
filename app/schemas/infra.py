from datetime import datetime

from pydantic import BaseModel


class Outage(BaseModel):
    started_at: datetime
    ended_at: datetime | None  # null while it is still going on
    duration_s: float
    error: str | None


class InfraInstance(BaseModel):
    service_name: str
    environment: str
    instance_id: str
    hostname: str | None
    health_url: str | None
    state: str  # UP, DOWN or UNKNOWN (never probed)
    checks: int
    uptime_pct: float | None
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    last_checked_at: datetime | None
    last_error: str | None
    down_since: datetime | None
    outages: list[Outage]
    system_latest: dict[str, float]
    system_p95: dict[str, float]
    system_peak: dict[str, float]


class InfraHost(BaseModel):
    hostname: str
    services: list[str]
    instances: int
    uptime_pct_min: float | None
    outages_total: int
    system_p95: dict[str, float]  # host-level figures: the highest 95th percentile any instance on the host saw
    process_memory_mb_total: float | None  # sum of what each service says it uses
    findings: list[str]
