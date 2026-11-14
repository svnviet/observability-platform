from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query

from app.core.config import default_page_size, jaeger_url, max_page_size, perses_url, prometheus_url
from app.monitoring.deps import get_infra_analytics, get_monitoring_service
from app.monitoring.infra import InfraAnalytics
from app.monitoring.service import MonitoringService
from app.registry.deps import get_heartbeat_monitor
from app.registry.heartbeat import HeartbeatMonitor, ScanResult
from app.schemas.enums import WorkerStatus
from app.schemas.infra import InfraHost, InfraInstance
from app.schemas.ops import ErrorGroup, LinksRead, MetricSummary, OverviewRead, QueueStat
from app.schemas.registry import ServiceRead, WorkerRead

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/overview", response_model=OverviewRead)
def overview(svc: MonitoringService = Depends(get_monitoring_service)):
    return svc.overview()


@router.get("/links", response_model=LinksRead)
def links():
    """Where the trace and dashboard tools live, for the UI's deep links."""
    return LinksRead(jaeger_url=jaeger_url(), perses_url=perses_url(), prometheus_url=prometheus_url())


@router.get("/services", response_model=list[ServiceRead])
def services(svc: MonitoringService = Depends(get_monitoring_service)):
    return svc.services()


@router.get("/workers", response_model=list[WorkerRead])
def workers(
    status: WorkerStatus | None = None,
    service: str | None = None,
    limit: int = Query(default_factory=default_page_size, ge=1, le=max_page_size()),
    offset: int = Query(0, ge=0),
    svc: MonitoringService = Depends(get_monitoring_service),
):
    return svc.workers(status=status, service=service, limit=limit, offset=offset)


@router.get("/queues", response_model=list[QueueStat])
def queues(svc: MonitoringService = Depends(get_monitoring_service)):
    return svc.queues()


@router.get("/errors", response_model=list[ErrorGroup])
def errors(
    window_hours: int = Query(24, ge=1, le=24 * 90),
    limit: int = Query(50, ge=1, le=500),
    svc: MonitoringService = Depends(get_monitoring_service),
):
    return svc.errors(window_hours, limit)


@router.get("/metrics", response_model=MetricSummary)
def metrics(
    window_hours: int = Query(24, ge=1, le=24 * 90), svc: MonitoringService = Depends(get_monitoring_service)
):
    return svc.metrics(window_hours)


@router.post("/scan", response_model=ScanResult)
def scan_heartbeats(monitor: HeartbeatMonitor = Depends(get_heartbeat_monitor)):
    """Run the missed-heartbeat scan now (the background scheduler does this on a timer)."""
    return monitor.scan(datetime.now(UTC))


@router.get("/infra/instances", response_model=list[InfraInstance])
def infra_instances(
    window_hours: int = Query(24, ge=1, le=24 * 30), svc: InfraAnalytics = Depends(get_infra_analytics)
):
    """Per instance: uptime, outages, probe latency and the infra figures it reported."""
    return svc.instances(window_hours, datetime.now(UTC))


@router.get("/infra/hosts", response_model=list[InfraHost])
def infra_hosts(
    window_hours: int = Query(24, ge=1, le=24 * 30), svc: InfraAnalytics = Depends(get_infra_analytics)
):
    """Per host: which services share it, how hot it runs and what that suggests."""
    return svc.hosts(window_hours, datetime.now(UTC))
